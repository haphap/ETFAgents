import json
import sys
import tempfile
import unittest
from pathlib import Path

_textual_modules_before = {m for m in sys.modules if m == "textual" or m.startswith("textual.")}

from cli.tui.services import (
    BacktestFailed,
    BacktestRunner,
    BacktestStarted,
    BacktestViewer,
    IdRegistry,
    PaperTradingViewModel,
    ReportRepository,
    TuiSettings,
)

_textual_modules_after = {m for m in sys.modules if m == "textual" or m.startswith("textual.")}
assert _textual_modules_after == _textual_modules_before, (
    f"Importing cli.tui.services pulled in textual as a side-effect: "
    f"{_textual_modules_after - _textual_modules_before}"
)


class ReportRepositoryTests(unittest.TestCase):
    def test_scans_single_etf_reports_and_reads_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "510300.SH" / "2026-05-22"
            (report_dir / "1_analysts").mkdir(parents=True)
            (report_dir / "5_portfolio").mkdir()
            (report_dir / "complete_report.md").write_text("BUY\n完整报告", encoding="utf-8")
            (report_dir / "1_analysts" / "market_flow.md").write_text("市场正文", encoding="utf-8")
            (report_dir / "5_portfolio" / "decision.md").write_text("最终决策", encoding="utf-8")
            pool_dir = root / "_candidate_pools" / "2026-05-22"
            pool_dir.mkdir(parents=True)
            (pool_dir / "complete_report.md").write_text("忽略", encoding="utf-8")

            repo = ReportRepository(root)
            reports = repo.list_reports()

            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].ticker, "510300.SH")
            self.assertEqual(reports[0].date, "2026-05-22")
            self.assertEqual(reports[0].rating, "BUY")
            self.assertEqual(repo.read_section(reports[0], "market_flow"), "市场正文")
            self.assertIn("最终决策", repo.read_section(reports[0], "portfolio_manager"))
            self.assertIn("完整报告", repo.read_section(reports[0], "complete"))

    def test_invalidate_refreshes_cached_report_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = ReportRepository(root)

            self.assertEqual(repo.list_reports(), [])

            report_dir = root / "510300.SH" / "2026-05-22"
            report_dir.mkdir(parents=True)
            (report_dir / "complete_report.md").write_text("BUY", encoding="utf-8")

            self.assertEqual(repo.list_reports(), [])
            repo.invalidate()
            self.assertEqual(len(repo.list_reports()), 1)


class IdRegistryTests(unittest.TestCase):
    def test_register_resolve_and_collision_handling(self):
        registry = IdRegistry("ticker")

        dotted = registry.register("510300.SH")
        underscored = registry.register("510300_SH")

        self.assertNotEqual(dotted, underscored)
        self.assertIn(dotted, registry)
        self.assertEqual(registry.resolve(dotted), "510300.SH")
        self.assertEqual(registry.resolve(underscored), "510300_SH")


class BacktestViewerTests(unittest.TestCase):
    def test_loads_backtest_artifacts_into_view_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "summary.md").write_text("# Summary", encoding="utf-8")
            (output / "metrics.json").write_text(json.dumps({"metrics": {"sharpe_ratio": 1.2}}), encoding="utf-8")
            (output / "nav.csv").write_text("date,value\n2026-01-01,100\n2026-01-02,110\n", encoding="utf-8")
            (output / "orders.csv").write_text("date,ticker\n2026-01-02,510300.SH\n", encoding="utf-8")
            (output / "trades.csv").write_text("date,ticker\n2026-01-02,510300.SH\n", encoding="utf-8")

            model = BacktestViewer(results_dir=tmp).load(output)

            self.assertEqual(model.summary, "# Summary")
            self.assertEqual(model.metrics["metrics"]["sharpe_ratio"], 1.2)
            self.assertEqual(len(model.nav), 2)
            self.assertEqual(len(model.orders), 1)
            self.assertTrue(model.sparkline)

    def test_bad_or_missing_artifacts_degrade_per_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "metrics.json").write_text("{bad json", encoding="utf-8")
            (output / "nav.csv").write_text("date,value\n2026-01-01,abc\n2026-01-02,120\n", encoding="utf-8")

            model = BacktestViewer(results_dir=tmp).load(output)

            self.assertIsNone(model.summary)
            self.assertIsNone(model.metrics)
            self.assertIsNone(model.orders)
            self.assertEqual(len(model.nav), 2)
            self.assertTrue(model.sparkline)


class TuiSettingsTests(unittest.TestCase):
    def test_default_values(self):
        s = TuiSettings()
        self.assertEqual(s.theme, "catppuccin-mocha")
        self.assertEqual(s.density, "normal")
        self.assertEqual(s.panel_width, "normal")
        self.assertEqual(s.left_pane_pct, 25)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            s = TuiSettings(theme="nord", density="compact", panel_width="wide")
            s.save(path)
            loaded = TuiSettings.load(path)
            self.assertEqual(loaded.theme, "nord")
            self.assertEqual(loaded.density, "compact")
            self.assertEqual(loaded.panel_width, "wide")
            self.assertEqual(loaded.left_pane_pct, 30)

    def test_corrupt_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("{bad json", encoding="utf-8")
            loaded = TuiSettings.load(path)
            self.assertEqual(loaded.theme, "catppuccin-mocha")

    def test_missing_file_returns_defaults(self):
        loaded = TuiSettings.load(Path("/nonexistent/settings.json"))
        self.assertEqual(loaded.theme, "catppuccin-mocha")

    def test_non_dict_json_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("[]", encoding="utf-8")
            loaded = TuiSettings.load(path)
            self.assertEqual(loaded.theme, "catppuccin-mocha")

    def test_validate_clamps_invalid_values(self):
        s = TuiSettings(theme="nonexistent", density="invalid", panel_width="huge")
        s.validate()
        self.assertEqual(s.theme, "catppuccin-mocha")
        self.assertEqual(s.density, "normal")
        self.assertEqual(s.panel_width, "normal")


class _FakePaperEngine:
    def __init__(self):
        self._logged_in_user = "default"

    def get_account(self, user_id=None):
        return {"user_id": user_id or "default", "cash": 100.0}

    def get_positions(self, user_id=None):
        return [{"ticker": "510300.SH", "quantity": 100}]

    def get_trades(self, user_id=None, limit=20):
        return [{"ticker": "510300.SH", "quantity": 100, "limit": limit}]

    def _get_current_user(self):
        return self._logged_in_user

    @property
    def current_user(self):
        return self._get_current_user()

    def login(self, username, password):
        if password == "correct":
            self._logged_in_user = username
            return True
        return False

    def logout(self):
        name = self._logged_in_user
        self._logged_in_user = "default"
        return name

    def buy(self, ticker, quantity, user_id=None, analysis_id=None):
        return {"ticker": ticker, "quantity": quantity, "status": "filled"}

    def sell(self, ticker, quantity, user_id=None, analysis_id=None):
        if quantity > 500:
            raise ValueError("Insufficient quantity")
        return {"ticker": ticker, "quantity": quantity, "status": "filled"}


class PaperTradingViewModelTests(unittest.TestCase):
    def test_snapshot_uses_engine(self):
        view_model = PaperTradingViewModel(_FakePaperEngine())

        snapshot = view_model.snapshot(user_id="alice", trade_limit=5)

        self.assertEqual(snapshot.account["user_id"], "alice")
        self.assertEqual(snapshot.positions[0]["ticker"], "510300.SH")
        self.assertEqual(snapshot.trades[0]["limit"], 5)

    def test_login_success(self):
        vm = PaperTradingViewModel(_FakePaperEngine())
        self.assertTrue(vm.login("alice", "correct"))
        self.assertEqual(vm.current_user(), "alice")

    def test_login_failure(self):
        vm = PaperTradingViewModel(_FakePaperEngine())
        self.assertFalse(vm.login("alice", "wrong"))
        self.assertEqual(vm.current_user(), "default")

    def test_logout(self):
        vm = PaperTradingViewModel(_FakePaperEngine())
        vm.login("alice", "correct")
        result = vm.logout()
        self.assertEqual(result, "alice")
        self.assertEqual(vm.current_user(), "default")

    def test_buy_success(self):
        vm = PaperTradingViewModel(_FakePaperEngine())
        result = vm.buy("510300.SH", 100)
        self.assertTrue(result.success)
        self.assertEqual(result.message, "买入成功")

    def test_sell_failure_propagates(self):
        vm = PaperTradingViewModel(_FakePaperEngine())
        result = vm.sell("510300.SH", 1000)
        self.assertFalse(result.success)
        self.assertIn("Insufficient", result.message)


class BacktestRunnerTests(unittest.TestCase):
    def test_yields_started_then_failed_on_graph_error(self):
        from unittest.mock import patch
        runner = BacktestRunner()
        with patch("etfagents.graph.etf_graph.EtfAgentsGraph", side_effect=RuntimeError("no graph")):
            events = list(runner.run(["510300.SH"], "2026-01-01", "2026-03-31"))
        self.assertIsInstance(events[0], BacktestStarted)
        self.assertEqual(events[0].tickers, ["510300.SH"])
        self.assertIsInstance(events[1], BacktestFailed)
        self.assertIn("no graph", events[1].error)

    def test_yields_finished_with_output_dir(self):
        from unittest.mock import MagicMock, patch
        from cli.tui.services import BacktestFinished
        with tempfile.TemporaryDirectory() as tmp:
            fake_result = MagicMock()
            mock_graph = MagicMock()
            mock_graph.backtest_candidate_pool.return_value = fake_result
            with patch("etfagents.graph.etf_graph.EtfAgentsGraph", return_value=mock_graph):
                with patch("etfagents.backtest.save_backtest_result") as mock_save:
                    import copy
                    from etfagents.default_config import DEFAULT_CONFIG
                    cfg = copy.deepcopy(DEFAULT_CONFIG)
                    cfg["results_dir"] = tmp
                    events = list(BacktestRunner().run(
                        ["510300.SH"], "2026-01-01", "2026-03-31",
                        config=cfg,
                    ))
            self.assertIsInstance(events[0], BacktestStarted)
            finished = [e for e in events if isinstance(e, BacktestFinished)]
            self.assertEqual(len(finished), 1)
            self.assertTrue(finished[0].output_dir.is_relative_to(Path(tmp)))
            mock_save.assert_called_once()

    def test_output_dir_slug_matches_cli_flow(self):
        """output_dir must encode ticker slug, date range, and timestamp."""
        from unittest.mock import MagicMock, patch
        from cli.tui.services import BacktestFinished
        with tempfile.TemporaryDirectory() as tmp:
            mock_graph = MagicMock()
            mock_graph.backtest_candidate_pool.return_value = MagicMock()
            with patch("etfagents.graph.etf_graph.EtfAgentsGraph", return_value=mock_graph):
                with patch("etfagents.backtest.save_backtest_result"):
                    import copy
                    from etfagents.default_config import DEFAULT_CONFIG
                    cfg = copy.deepcopy(DEFAULT_CONFIG)
                    cfg["results_dir"] = tmp
                    events = list(BacktestRunner().run(
                        ["510300.SH", "159915.SZ", "510050.SH", "510500.SH"],
                        "2026-01-01", "2026-03-31",
                        config=cfg,
                    ))
            finished = [e for e in events if isinstance(e, BacktestFinished)][0]
            parts = finished.output_dir.relative_to(Path(tmp) / "backtest").parts
            # slug: first 3 tickers + "plus_1", dots replaced by _
            self.assertIn("510300", parts[0])
            self.assertIn("plus_1", parts[0])
            # date range subfolder
            self.assertEqual(parts[1], "2026-01-01_to_2026-03-31")
            # timestamp subfolder (YYYYMMDD_HHMMSS)
            import re
            self.assertRegex(parts[2], r"^\d{8}_\d{6}$")


if __name__ == "__main__":
    unittest.main()
