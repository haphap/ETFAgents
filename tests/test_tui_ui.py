import tempfile
import unittest
from pathlib import Path

try:
    from textual.widgets import Static
except ModuleNotFoundError:
    Static = None

if Static is None:
    raise unittest.SkipTest("Textual not installed; skipping TUI UI tests")

from cli.tui.app import ETFAgentsTuiApp, HomeScreen, ResearchAnalysisScreen, ReportLibraryScreen, BacktestScreen, PaperTradingScreen, HelpScreen
from cli.tui.services import ReportRepository


class TuiPilotTests(unittest.IsolatedAsyncioTestCase):
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

    def _app(self, results_dir: str) -> ETFAgentsTuiApp:
        return ETFAgentsTuiApp(
            repository=ReportRepository(results_dir),
        )


if __name__ == "__main__":
    unittest.main()
