
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from etfagents.agents.utils.memory import TradingMemoryLog
from etfagents.graph.propagation import Propagator
from etfagents.graph.trading_graph import TradingAgentsGraph

class TradingMemoryLogTests(unittest.TestCase):
    def make_log(self, path: Path, **extra):
        cfg = {"memory_log_path": str(path)}
        cfg.update(extra)
        return TradingMemoryLog(cfg)

    def test_store_decision_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self.make_log(Path(tmpdir) / "trading_memory.md")
            decision = "Rating: Buy\nEnter on pullbacks."
            log.store_decision("NVDA", "2026-01-10", decision)
            log.store_decision("NVDA", "2026-01-10", decision)

            entries = log.load_entries()
            self.assertEqual(1, len(entries))
            self.assertTrue(entries[0]["pending"])
            self.assertEqual("Buy", entries[0]["rating"])

    def test_update_with_outcome_adds_reflection_and_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self.make_log(Path(tmpdir) / "trading_memory.md")
            log.store_decision("NVDA", "2026-01-10", "Rating: Buy\nStay constructive.")
            self.assertEqual("", log.get_past_context("NVDA"))

            log.update_with_outcome("NVDA", "2026-01-10", 0.042, 0.021, 5, "Momentum confirmed.")

            entries = log.load_entries()
            self.assertFalse(entries[0]["pending"])
            self.assertEqual("+4.2%", entries[0]["raw"])
            self.assertEqual("+2.1%", entries[0]["alpha"])
            self.assertEqual("5d", entries[0]["holding"])
            self.assertEqual("Momentum confirmed.", entries[0]["reflection"])
            self.assertIn("Past analyses of NVDA", log.get_past_context("NVDA"))

    def test_past_context_keeps_same_ticker_full_and_cross_ticker_reflection_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self.make_log(Path(tmpdir) / "trading_memory.md")
            log.store_decision("NVDA", "2026-01-10", "Rating: Buy\nEnter on pullbacks.")
            log.update_with_outcome("NVDA", "2026-01-10", 0.042, 0.021, 5, "Momentum confirmed.")
            log.store_decision("AAPL", "2026-01-12", "Rating: Hold\nWait for clearer setup.")
            log.update_with_outcome("AAPL", "2026-01-12", 0.010, -0.005, 5, "Patience mattered.")

            context = log.get_past_context("NVDA")

            self.assertIn("Past analyses of NVDA (most recent first):", context)
            self.assertIn("DECISION:\nRating: Buy\nEnter on pullbacks.", context)
            self.assertIn("Recent cross-ticker lessons:", context)
            self.assertIn("[2026-01-12 | AAPL | Hold | +1.0%]", context)
            self.assertIn("Patience mattered.", context)
            self.assertNotIn("DECISION:\nRating: Hold\nWait for clearer setup.", context)

    def test_rotation_keeps_recent_resolved_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = self.make_log(
                Path(tmpdir) / "trading_memory.md",
                memory_log_max_entries=2,
            )
            for day in ("01", "02", "03"):
                date = f"2026-01-{day}"
                log.store_decision("NVDA", date, "Rating: Buy\nStay constructive.")
                log.update_with_outcome("NVDA", date, 0.01, 0.0, 5, f"Lesson {day}")

            entries = log.load_entries()
            self.assertEqual(["2026-01-02", "2026-01-03"], [entry["date"] for entry in entries])

    def test_no_log_path_is_noop(self):
        log = TradingMemoryLog(config=None)
        log.store_decision("NVDA", "2026-01-10", "Rating: Buy")
        self.assertEqual([], log.load_entries())
        self.assertEqual("", log.get_past_context("NVDA"))

    def test_memory_log_path_expands_user_home(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            with patch.dict(os.environ, {"HOME": str(home)}):
                log = TradingMemoryLog({"memory_log_path": "~/memory/trading_memory.md"})
            self.assertEqual(home / "memory" / "trading_memory.md", log.log_path)

class DeferredReflectionTests(unittest.TestCase):
    def test_propagator_initial_state_includes_past_context(self):
        state = Propagator().create_initial_state("NVDA", "2026-01-10", past_context="resolved lesson")
        self.assertEqual("resolved lesson", state["past_context"])

    def test_fetch_returns_handles_common_window(self):
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {}
        stock_prices = pd.DataFrame({"Close": [100.0, 102.0, 104.0]})
        spy_prices = pd.DataFrame({"Close": [400.0, 401.0, 402.0]})
        with patch("yfinance.Ticker") as mock_ticker_cls:
            def _make_ticker(symbol):
                ticker = MagicMock()
                ticker.history.return_value = spy_prices if symbol == "SPY" else stock_prices
                return ticker

            mock_ticker_cls.side_effect = _make_ticker
            raw, alpha, days = TradingAgentsGraph._fetch_returns(graph, "NVDA", "2026-01-05")

        self.assertAlmostEqual(0.04, raw)
        self.assertAlmostEqual(0.035, alpha)
        self.assertEqual(2, days)

    def test_fetch_returns_uses_configured_benchmark(self):
        graph = object.__new__(TradingAgentsGraph)
        graph.config = {"benchmark_ticker": "QQQ"}
        stock_prices = pd.DataFrame({"Close": [100.0, 105.0]})
        benchmark_prices = pd.DataFrame({"Close": [200.0, 202.0]})

        with patch("yfinance.Ticker") as mock_ticker_cls:
            def _make_ticker(symbol):
                ticker = MagicMock()
                ticker.history.return_value = benchmark_prices if symbol == "QQQ" else stock_prices
                return ticker

            mock_ticker_cls.side_effect = _make_ticker
            raw, alpha, days = TradingAgentsGraph._fetch_returns(graph, "NVDA", "2026-01-05", holding_days=1)

        self.assertAlmostEqual(0.05, raw)
        self.assertAlmostEqual(0.04, alpha)
        self.assertEqual(1, days)

if __name__ == "__main__":
    unittest.main()
