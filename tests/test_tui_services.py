import json
import sys
import tempfile
import unittest
from pathlib import Path

_textual_modules_before = {m for m in sys.modules if m == "textual" or m.startswith("textual.")}

from cli.tui.services import (
    BacktestViewer,
    IdRegistry,
    PaperTradingViewModel,
    ReportRepository,
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


class _FakePaperEngine:
    def get_account(self, user_id=None):
        return {"user_id": user_id or "default", "cash": 100.0}

    def get_positions(self, user_id=None):
        return [{"ticker": "510300.SH", "quantity": 100}]

    def get_trades(self, user_id=None, limit=20):
        return [{"ticker": "510300.SH", "quantity": 100, "limit": limit}]


class PaperTradingViewModelTests(unittest.TestCase):
    def test_snapshot_uses_engine(self):
        view_model = PaperTradingViewModel(_FakePaperEngine())

        snapshot = view_model.snapshot(user_id="alice", trade_limit=5)

        self.assertEqual(snapshot.account["user_id"], "alice")
        self.assertEqual(snapshot.positions[0]["ticker"], "510300.SH")
        self.assertEqual(snapshot.trades[0]["limit"], 5)


if __name__ == "__main__":
    unittest.main()
