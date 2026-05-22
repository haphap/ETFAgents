import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input

from cli.tui.app import ETFAgentsTuiApp, BacktestScreen, PaperTradingScreen, ReportLibraryScreen, ResearchAnalysisScreen
from cli.tui.services import (
    AnalysisEvent,
    BacktestViewModel,
    PaperTradingSnapshot,
    ReportRepository,
    TickerState,
)


class _FakeAnalysisRunner:
    def run_queue(self, tickers, analysis_date=None, selected_analysts=None):
        ticker = list(tickers)[0]
        yield AnalysisEvent(
            "ticker_started",
            ticker,
            status=TickerState.RUNNING,
            states={ticker: TickerState.RUNNING},
            completed_sections=0,
            total_sections=18,
        )
        yield AnalysisEvent(
            "section_update",
            ticker,
            status=TickerState.SECTION_DONE,
            section="analyst.market_flow",
            content="fake market report",
            states={ticker: TickerState.SECTION_DONE},
            completed_sections=1,
            total_sections=18,
        )
        yield AnalysisEvent(
            "ticker_done",
            ticker,
            status=TickerState.DONE,
            states={ticker: TickerState.DONE},
            completed_sections=1,
            total_sections=18,
        )
        yield AnalysisEvent(
            "report_persisted",
            ticker,
            status=TickerState.DONE,
            states={ticker: TickerState.DONE},
        )


class _FakeBacktestRunner:
    def run(self, tickers, start_date, end_date, rebalance_interval_days=20, top_k=1):
        return BacktestViewModel(
            output_dir=Path("."),
            summary="# Fake backtest",
            metrics={"metrics": {"sharpe": 1.0}},
            nav=[{"date": "2026-01-01", "value": "100"}],
            orders=[],
            trades=[],
            sparkline="▁",
        )


class _FakePaperViewModel:
    def snapshot(self, user_id=None, trade_limit=20):
        return PaperTradingSnapshot(
            account={
                "cash": 1000.0,
                "market_value": 200.0,
                "total_assets": 1200.0,
                "unrealized_pnl": 12.0,
            },
            positions=[
                {
                    "ticker": "510300.SH",
                    "quantity": 100,
                    "avg_cost": 1.0,
                    "current_price": 1.12,
                    "unrealized_pnl": 12.0,
                }
            ],
            trades=[],
        )


class TuiPilotTests(unittest.IsolatedAsyncioTestCase):
    async def test_home_menu_navigates_to_research_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#research")
                self.assertIsInstance(app.screen, ResearchAnalysisScreen)

    async def test_report_library_empty_then_refreshes_non_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#reports")
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, ReportLibraryScreen)
                self.assertEqual(screen.records, [])

                report_dir = Path(tmp) / "510300.SH" / "2026-05-22"
                report_dir.mkdir(parents=True)
                (report_dir / "complete_report.md").write_text("BUY", encoding="utf-8")
                await pilot.press("r")
                self.assertEqual(len(screen.records), 1)

    async def test_research_screen_fake_runner_updates_section_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#research")
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, ResearchAnalysisScreen)
                screen.query_one("#tickers", Input).value = "510300.SH"
                await pilot.click("#start")
                await pilot.pause(0.1)
                self.assertEqual(screen.states["510300.SH"], TickerState.DONE)
                self.assertEqual(screen.events[("510300.SH", "analyst.market_flow")], "fake market report")

    async def test_backtest_screen_validates_integer_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "510300.SH" / "2026-05-22"
            report_dir.mkdir(parents=True)
            (report_dir / "complete_report.md").write_text("BUY", encoding="utf-8")
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#backtest")
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, BacktestScreen)
                screen.selected_ticker = "510300.SH"
                screen.query_one("#rebalance", Input).value = "bad"
                await pilot.click("#run_backtest")
                await pilot.pause()
                self.assertIn("必须是整数", screen.query_one("#backtest_summary").source)

    async def test_paper_screen_renders_account_and_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#paper")
                await pilot.pause()
                self.assertIsInstance(app.screen, PaperTradingScreen)
                self.assertEqual(app.screen.query_one("#paper_table").row_count, 1)
                self.assertEqual(app.screen._pnl_text(1).style, "green")
                self.assertEqual(app.screen._pnl_text(-1).style, "red")

    def _app(self, results_dir: str) -> ETFAgentsTuiApp:
        return ETFAgentsTuiApp(
            repository=ReportRepository(results_dir),
            analysis_runner=_FakeAnalysisRunner(),
            backtest_runner=_FakeBacktestRunner(),
            paper_view_model=_FakePaperViewModel(),
        )


if __name__ == "__main__":
    unittest.main()
