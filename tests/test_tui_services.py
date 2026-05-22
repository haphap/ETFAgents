import json
import tempfile
import unittest
from pathlib import Path

from cli.tui.services import (
    AnalysisRunner,
    BacktestRunner,
    PaperTradingViewModel,
    ReportRepository,
)


class ReportRepositoryTests(unittest.TestCase):
    def test_scans_single_etf_reports_and_reads_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "510300.SH" / "2026-05-22"
            (report_dir / "1_analysts").mkdir(parents=True)
            (report_dir / "5_portfolio").mkdir()
            (report_dir / "complete_report.md").write_text("评级：BUY\n完整报告", encoding="utf-8")
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
            self.assertEqual(repo.read_section(reports[0], "market_flow_report"), "市场正文")
            self.assertEqual(repo.read_section(reports[0], "final_allocation_decision"), "最终决策")


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, _state, **_kwargs):
        yield from self._chunks


class _FakeGraph:
    def __init__(self, config=None, debug=False):
        self.config = config
        self.debug = debug
        self.graph = _FakeStream(
            [
                {"market_flow_report": "市场报告", "current_agent": "Market & Flow Analyst"},
                {"trader_allocation_plan": "交易计划"},
                {"risk_debate_state": {"judge_decision": "BUY，目标仓位 20%"}},
            ]
        )
        self.finalized = False
        self.closed = False

    def prepare_run(self, ticker, analysis_date):
        return {"ticker": ticker, "trade_date": analysis_date}, {"config": {}}, False

    def finalize_run(self, analysis_date, final_state):
        self.finalized = True
        self.analysis_date = analysis_date
        self.final_state = final_state

    def close_run(self):
        self.closed = True


class AnalysisRunnerTests(unittest.TestCase):
    def test_fake_graph_stream_emits_progress_and_saves_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = AnalysisRunner(
                config={"results_dir": tmp},
                graph_factory=lambda **kwargs: _FakeGraph(**kwargs),
            )

            events = list(runner.run_queue(["510300.SH"], "2026-05-22", ["market_flow"]))

            self.assertEqual(events[0].event_type, "ticker_started")
            sections = [event.section for event in events if event.event_type == "section_update"]
            self.assertIn("market_flow_report", sections)
            self.assertIn("trader_allocation_plan", sections)
            self.assertEqual(events[-1].event_type, "ticker_done")
            self.assertTrue((Path(tmp) / "510300.SH" / "2026-05-22" / "reports" / "market_flow_report.md").exists())
            self.assertTrue((Path(tmp) / "510300.SH" / "2026-05-22" / "complete_report.md").exists())


class BacktestRunnerTests(unittest.TestCase):
    def test_loads_backtest_artifacts_into_view_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "summary.md").write_text("# Summary", encoding="utf-8")
            (output / "metrics.json").write_text(json.dumps({"metrics": {"sharpe_ratio": 1.2}}), encoding="utf-8")
            (output / "nav.csv").write_text("date,value\n2026-01-01,100\n2026-01-02,110\n", encoding="utf-8")
            (output / "orders.csv").write_text("date,ticker\n2026-01-02,510300.SH\n", encoding="utf-8")
            (output / "trades.csv").write_text("date,ticker\n2026-01-02,510300.SH\n", encoding="utf-8")

            model = BacktestRunner(config={"results_dir": tmp}).load(output)

            self.assertEqual(model.summary, "# Summary")
            self.assertEqual(model.metrics["metrics"]["sharpe_ratio"], 1.2)
            self.assertEqual(len(model.nav), 2)
            self.assertEqual(len(model.orders), 1)
            self.assertTrue(model.sparkline)


class _FakePaperEngine:
    def get_account(self, user_id=None):
        return {"user_id": user_id or "default", "cash": 100.0}

    def get_positions(self, user_id=None):
        return [{"ticker": "510300.SH", "quantity": 100}]

    def get_trades(self, user_id=None, limit=20):
        return [{"ticker": "510300.SH", "quantity": 100, "limit": limit}]

    def buy(self, ticker, quantity, user_id=None, analysis_id=None):
        return {"side": "buy", "ticker": ticker, "quantity": quantity}

    def sell(self, ticker, quantity, user_id=None, analysis_id=None):
        return {"side": "sell", "ticker": ticker, "quantity": quantity}


class PaperTradingViewModelTests(unittest.TestCase):
    def test_snapshot_and_trade_delegation_use_engine(self):
        view_model = PaperTradingViewModel(_FakePaperEngine())

        snapshot = view_model.snapshot(user_id="alice", trade_limit=5)

        self.assertEqual(snapshot.account["user_id"], "alice")
        self.assertEqual(snapshot.positions[0]["ticker"], "510300.SH")
        self.assertEqual(snapshot.trades[0]["limit"], 5)
        self.assertEqual(view_model.buy("510300.SH", 100)["side"], "buy")
        self.assertEqual(view_model.sell("510300.SH", 100)["side"], "sell")


if __name__ == "__main__":
    unittest.main()
