"""Regression tests for the ``memory.append_analysis`` bridge handler.

Proves that a non-default runtime config (forwarded by the TS Memory Writer
node) reaches ``AnalysisMemoryStore`` instead of being silently replaced by
``DEFAULT_CONFIG``.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from etfagents.bridge.handlers.memory import _DEFAULT_ANALYSTS, memory_append_analysis


_STATE = {"asset_of_interest": "510300.SH", "trade_date": "2026-05-29"}


class MemoryAppendAnalysisConfigTests(unittest.TestCase):
    def test_runtime_results_dir_is_honoured(self) -> None:
        """A custom results_dir in the passed config must drive where memory is stored."""
        with tempfile.TemporaryDirectory() as tmp:
            result = memory_append_analysis(
                {
                    "state": _STATE,
                    "config": {"results_dir": tmp, "memory_mode": "full"},
                }
            )
            self.assertTrue(result["written"])
            memory_dir = Path(tmp) / "memory"
            # The entry must land under the runtime results_dir, not DEFAULT_CONFIG's.
            self.assertTrue(memory_dir.exists())
            self.assertTrue(any(memory_dir.rglob("*")))

    def test_runtime_memory_mode_disabled_is_honoured(self) -> None:
        """memory_mode=disabled in the passed config must short-circuit the write."""
        with tempfile.TemporaryDirectory() as tmp:
            result = memory_append_analysis(
                {
                    "state": _STATE,
                    "config": {"results_dir": tmp, "memory_mode": "disabled"},
                }
            )
            self.assertFalse(result["written"])
            self.assertEqual(result["entry"], {})
            self.assertFalse((Path(tmp) / "memory").exists())

    def test_empty_selected_analysts_is_preserved_not_defaulted(self) -> None:
        """An explicit empty selected_analysts must NOT be coerced to the full default.

        The config hash is derived from selected_analysts, so coercing [] to the
        full set would make the stored entry disagree with what the graph ran.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"results_dir": tmp, "memory_mode": "full"}
            empty = memory_append_analysis(
                {"state": _STATE, "selected_analysts": [], "config": cfg}
            )
            full = memory_append_analysis(
                {
                    "state": _STATE,
                    "selected_analysts": list(_DEFAULT_ANALYSTS),
                    "config": cfg,
                }
            )
            self.assertTrue(empty["written"])
            self.assertTrue(full["written"])
            # Distinct selections must yield distinct config hashes.
            self.assertNotEqual(empty["entry"]["config_hash"], full["entry"]["config_hash"])

    def test_non_list_selected_analysts_is_rejected(self) -> None:
        """A string (or other non-list) selected_analysts must raise INVALID_PARAMS."""
        from etfagents.bridge.protocol import INVALID_PARAMS, RpcError

        for bad in ("market_flow", 123, ["market_flow", 5]):
            with self.assertRaises(RpcError) as cm:
                memory_append_analysis({"state": _STATE, "selected_analysts": bad})
            self.assertEqual(cm.exception.code, INVALID_PARAMS)

    def test_build_context_returns_per_role_bundle(self) -> None:
        """build_context returns continuity/lesson/method dicts keyed by the run's roles."""
        from etfagents.bridge.handlers.memory import memory_build_context

        with tempfile.TemporaryDirectory() as tmp:
            result = memory_build_context(
                {
                    "ticker": "510300.SH",
                    "trade_date": "2026-05-29",
                    "selected_analysts": ["market_flow"],
                    "config": {"results_dir": tmp, "memory_mode": "full"},
                }
            )
            for key in ("continuity_context", "lesson_context", "method_context"):
                self.assertIn(key, result)
                # Roles include the selected analyst plus the managers/trader.
                self.assertIn("market_flow", result[key])
                self.assertIn("portfolio_manager", result[key])
            self.assertIn("past_context", result)

    def test_agent_signal_sidecars_are_written(self) -> None:
        """Parsed TS agent signals should be stored outside visible markdown reports."""
        with tempfile.TemporaryDirectory() as tmp:
            state = {
                **_STATE,
                "agent_signals": {
                    "market_flow": {
                        "source": "market_flow",
                        "agent": "market_flow",
                        "fields": {"price_regime": "TREND_UP", "confidence": 0.8},
                        "raw": "agent: market_flow\nprice_regime: TREND_UP\nconfidence: 0.8",
                        "decision_summary": {"方向": "偏多"},
                    }
                },
            }
            result = memory_append_analysis(
                {
                    "state": state,
                    "config": {"results_dir": tmp, "memory_mode": "full"},
                }
            )
            self.assertTrue(result["written"])
            report_dir = Path(tmp) / "510300.SH" / "2026-05-29"
            signals = json.loads((report_dir / "agent_signals.json").read_text(encoding="utf-8"))
            summaries = json.loads(
                (report_dir / "decision_signal_summaries.json").read_text(encoding="utf-8")
            )
            self.assertEqual(signals["market_flow"]["fields"]["price_regime"], "TREND_UP")
            self.assertEqual(summaries["market_flow"]["方向"], "偏多")


if __name__ == "__main__":
    unittest.main()
