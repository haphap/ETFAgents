import tempfile
import unittest
from pathlib import Path

try:
    from textual.widgets import Static
except ModuleNotFoundError:
    Static = None

if Static is None:
    raise unittest.SkipTest("Textual not installed; skipping TUI UI tests")

from cli.tui.app import (
    ETFAgentsTuiApp,
    HomeScreen,
    ResearchAnalysisScreen,
    ReportLibraryScreen,
    BacktestScreen,
    PaperTradingScreen,
    HelpScreen,
)
from cli.tui.services import (
    PaperTradingViewModel,
    ReportRepository,
)


class _FakePaperEngine:
    def get_account(self, user_id=None):
        return {
            "user_id": user_id or "default",
            "cash": 100_000.0,
            "total_assets": 150_000.0,
            "market_value": 50_000.0,
            "unrealized_pnl": 1234.56,
            "realized_pnl": -200.0,
        }

    def get_positions(self, user_id=None):
        return [
            {
                "ticker": "510300.SH",
                "name": "沪深300ETF",
                "quantity": 1000,
                "avg_cost": 4.5,
                "current_price": 4.8,
                "market_value": 4800.0,
                "unrealized_pnl": 300.0,
                "pnl_pct": 6.67,
            },
            {
                "ticker": "159915.SZ",
                "name": "创业板ETF",
                "quantity": 500,
                "avg_cost": 2.1,
                "current_price": 1.9,
                "market_value": 950.0,
                "unrealized_pnl": -100.0,
                "pnl_pct": -9.52,
            },
        ]

    def get_trades(self, user_id=None, limit=20):
        return [
            {
                "created_at": "2026-05-20 10:30",
                "ticker": "510300.SH",
                "side": "BUY",
                "quantity": 1000,
                "price": 4.5,
                "amount": 4500.0,
                "pnl": 0,
            },
        ]


class TuiPilotTests(unittest.IsolatedAsyncioTestCase):
    # --- Home screen ---

    async def test_home_screen_shows_four_buttons(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                self.assertIsInstance(app.screen, HomeScreen)
                self.assertIsNotNone(app.screen.query_one("#btn_research"))
                self.assertIsNotNone(app.screen.query_one("#btn_reports"))
                self.assertIsNotNone(app.screen.query_one("#btn_backtest"))
                self.assertIsNotNone(app.screen.query_one("#btn_paper"))

    async def test_home_menu_navigates_to_research_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                self.assertIsInstance(app.screen, ResearchAnalysisScreen)

    async def test_home_menu_navigates_to_reports_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_reports")
                self.assertIsInstance(app.screen, ReportLibraryScreen)

    async def test_home_menu_navigates_to_backtest_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                self.assertIsInstance(app.screen, BacktestScreen)

    async def test_home_menu_navigates_to_paper_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_paper")
                self.assertIsInstance(app.screen, PaperTradingScreen)

    async def test_help_screen_via_keybinding(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.press("?")
                self.assertIsInstance(app.screen, HelpScreen)

    async def test_escape_pops_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_reports")
                self.assertIsInstance(app.screen, ReportLibraryScreen)
                await pilot.press("escape")
                self.assertIsInstance(app.screen, HomeScreen)

    # --- ReportLibraryScreen ---

    async def test_report_library_empty_shows_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_reports")
                screen = app.screen
                self.assertIsInstance(screen, ReportLibraryScreen)
                body = screen.query_one("#lib_body")
                self.assertIn("暂无报告", body._markdown)

    async def test_report_library_shows_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_dir = root / "510300.SH" / "2026-05-22"
            report_dir.mkdir(parents=True)
            (report_dir / "complete_report.md").write_text(
                "BUY\nFull report", encoding="utf-8"
            )
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_reports")
                screen = app.screen
                self.assertIsInstance(screen, ReportLibraryScreen)
                self.assertEqual(len(screen.records), 1)
                self.assertEqual(screen.records[0].ticker, "510300.SH")

    async def test_report_library_section_list_has_10_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_reports")
                screen = app.screen
                sections = screen.query_one("#lib_sections")
                # 9 sections + 1 complete = 10
                self.assertEqual(len(sections.children), 10)

    # --- BacktestScreen ---

    async def test_backtest_screen_is_view_only(self):
        """BacktestScreen (M0 placeholder) should not contain Input or run-backtest Button."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                screen = app.screen
                self.assertIsInstance(screen, BacktestScreen)
                from textual.widgets import Input, Button
                inputs = screen.query(Input)
                self.assertEqual(len(inputs), 0)
                run_buttons = [
                    b for b in screen.query(Button)
                    if "运行" in (b.label or "")
                ]
                self.assertEqual(len(run_buttons), 0)

    # --- PaperTradingScreen ---

    async def test_paper_trading_shows_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp, with_paper=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_paper")
                screen = app.screen
                self.assertIsInstance(screen, PaperTradingScreen)
                # Wait for worker thread to complete
                await pilot.pause()
                await pilot.pause()
                acct_text = str(screen.query_one("#pt_account", Static).render())
                self.assertIn("150000", acct_text)

    async def test_paper_trading_positions_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp, with_paper=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_paper")
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                pos_table = screen.query_one("#pt_positions")
                self.assertGreater(pos_table.row_count, 0)

    # --- helpers ---

    def _app(self, results_dir: str, *, with_paper: bool = False) -> ETFAgentsTuiApp:
        paper_vm = None
        if with_paper:
            paper_vm = PaperTradingViewModel(engine=_FakePaperEngine())
        return ETFAgentsTuiApp(
            repository=ReportRepository(results_dir),
            paper_view_model=paper_vm,
        )


if __name__ == "__main__":
    unittest.main()
