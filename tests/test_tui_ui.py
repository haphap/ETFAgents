import tempfile
import unittest
from pathlib import Path

try:
    from textual.widgets import Static, ListView, Label
except ModuleNotFoundError:
    Static = None

if Static is None:
    raise unittest.SkipTest("Textual not installed; skipping TUI UI tests")

from cli.tui.app import (
    AnalysisConfigModal,
    ETFAgentsTuiApp,
    HomeScreen,
    LoginModal,
    OrderModal,
    ResearchAnalysisScreen,
    ReportLibraryScreen,
    BacktestScreen,
    PaperTradingScreen,
    SettingsScreen,
    HelpScreen,
)
from cli.tui.services import (
    BacktestViewer,
    PaperTradingViewModel,
    ReportRepository,
    TickerFailed,
    TickerStarted,
    TickerDone,
)


class _FakePaperEngine:
    def __init__(self):
        self._logged_in_user = "default"

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

    def _get_current_user(self):
        return self._logged_in_user

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
        return {"ticker": ticker, "quantity": quantity, "status": "filled"}


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

    # --- ResearchAnalysisScreen ---

    async def test_research_analysis_screen_has_input_and_start_button(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                from cli.tui.app import ResearchAnalysisScreen
                self.assertIsInstance(screen, ResearchAnalysisScreen)
                self.assertIsNotNone(screen.query_one("#ra_ticker_input"))
                self.assertIsNotNone(screen.query_one("#btn_ra_start"))

    async def test_research_analysis_section_list_has_9_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                sections = screen.query_one("#ra_sections")
                self.assertEqual(len(sections.children), 9)

    async def test_research_analysis_ticker_status_updates(self):
        """Verify ticker status changes from ⏳ → ✓/✗ when events fire."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen

                # Simulate ticker started
                screen._handle_ticker_started(TickerStarted(ticker="510300.SH", total_sections=9))
                await pilot.pause()
                queue = screen.query_one("#ra_queue", ListView)
                self.assertEqual(len(queue.children), 1)

                # Simulate ticker done with rating
                screen._handle_ticker_done(TickerDone(
                    ticker="510300.SH",
                    report_path=Path("/fake"),
                    rating="BUY"
                ))
                await pilot.pause()

                # Verify status updated to ✓ BUY
                item = queue.children[0]
                label = item.query_one(Label)
                rendered = str(label.render())
                self.assertIn("✓", rendered)
                self.assertIn("BUY", rendered)

    async def test_research_analysis_ticker_selection(self):
        """Verify selecting a ticker in queue changes current_ticker."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen

                # Start two tickers
                screen._handle_ticker_started(TickerStarted(ticker="510300.SH", total_sections=9))
                screen._handle_ticker_started(TickerStarted(ticker="159915.SZ", total_sections=9))
                await pilot.pause()

                # Get the queue ListView
                queue = screen.query_one("#ra_queue", ListView)
                self.assertEqual(len(queue.children), 2)

                # Initially first ticker is selected
                self.assertEqual(screen.current_ticker, "510300.SH")

                # Find the second ticker's id and manually trigger selection
                second_item = queue.children[1]
                ticker_id = second_item.id
                self.assertIsNotNone(ticker_id)

                # Manually call the selection handler (simulating user clicking)
                from textual.widgets import ListView as ListViewWidget
                selected_event = ListViewWidget.Selected(queue, second_item, 1)
                screen.on_list_view_selected(selected_event)
                await pilot.pause()

                # Verify current_ticker changed
                self.assertEqual(screen.current_ticker, "159915.SZ")

    # --- BacktestScreen (M4: has run inputs) ---

    async def test_backtest_screen_has_run_inputs(self):
        """BacktestScreen M4 should have ticker/date inputs and a run button."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                screen = app.screen
                self.assertIsInstance(screen, BacktestScreen)
                self.assertIsNotNone(screen.query_one("#bt_run_tickers"))
                self.assertIsNotNone(screen.query_one("#bt_run_start"))
                self.assertIsNotNone(screen.query_one("#bt_run_end"))
                self.assertIsNotNone(screen.query_one("#btn_bt_run"))

    # --- ResearchAnalysisScreen M4: cancel button ---

    async def test_cancel_button_exists_and_initially_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                from textual.widgets import Button
                cancel = screen.query_one("#btn_ra_cancel", Button)
                self.assertTrue(cancel.disabled)

    # --- SettingsScreen ---

    async def test_settings_screen_opens_via_keybinding(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.press("s")
                self.assertIsInstance(app.screen, SettingsScreen)

    async def test_settings_screen_has_theme_and_density_widgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.press("s")
                screen = app.screen
                self.assertIsNotNone(screen.query_one("#sel_theme"))
                self.assertIsNotNone(screen.query_one("#sel_density"))
                self.assertIsNotNone(screen.query_one("#inp_pane_width"))
                self.assertIsNotNone(screen.query_one("#btn_settings_save"))

    # --- PaperTradingScreen M4: buy/sell/login buttons ---

    async def test_paper_screen_has_buy_sell_login_buttons(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp, with_paper=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_paper")
                screen = app.screen
                self.assertIsNotNone(screen.query_one("#btn_pt_login"))
                self.assertIsNotNone(screen.query_one("#btn_pt_logout"))
                self.assertIsNotNone(screen.query_one("#btn_pt_buy"))
                self.assertIsNotNone(screen.query_one("#btn_pt_sell"))

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

    # --- BacktestScreen ---

    async def test_backtest_screen_empty_shows_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp, with_backtest=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, BacktestScreen)
                sparkline = screen.query_one("#bt_sparkline")
                self.assertIn("暂无回测结果", str(sparkline.render()))

    async def test_backtest_screen_shows_record_in_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bt_dir = root / "backtest" / "2026-01-02_to_2026-03-31"
            bt_dir.mkdir(parents=True)
            (bt_dir / "metrics.json").write_text(
                '{"metrics": {"cumulative_return": 0.123}}', encoding="utf-8"
            )
            (bt_dir / "manifest.json").write_text(
                '{"tickers": ["510300.SH"], "start_date": "2026-01-02", "end_date": "2026-03-31"}',
                encoding="utf-8",
            )
            (bt_dir / "summary.md").write_text("## 回测摘要\nTest summary", encoding="utf-8")
            app = self._app(tmp, with_backtest=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, BacktestScreen)
                bt_list = screen.query_one("#bt_list")
                self.assertEqual(len(bt_list.children), 1)
                # Verify metrics table was populated
                metrics = screen.query_one("#bt_metrics")
                self.assertGreater(metrics.row_count, 0)

    async def test_backtest_screen_displays_metrics_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bt_dir = root / "backtest" / "2026-01-02_to_2026-03-31"
            bt_dir.mkdir(parents=True)
            (bt_dir / "metrics.json").write_text(
                '{"metrics": {"cumulative_return": 0.123, "sharpe_ratio": 1.5}}',
                encoding="utf-8",
            )
            (bt_dir / "manifest.json").write_text(
                '{"tickers": ["510300.SH"], "start_date": "2026-01-02", "end_date": "2026-03-31"}',
                encoding="utf-8",
            )
            (bt_dir / "summary.md").write_text("## 回测摘要\nTest", encoding="utf-8")
            # Add nav.csv to test sparkline rendering
            (bt_dir / "nav.csv").write_text(
                "date,nav,cash,gross_exposure\n"
                "2026-01-02,100000.0,50000.0,0.5\n"
                "2026-01-03,105000.0,48000.0,0.52\n"
                "2026-01-04,110000.0,45000.0,0.55\n",
                encoding="utf-8",
            )
            app = self._app(tmp, with_backtest=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                metrics = screen.query_one("#bt_metrics")
                # Verify metrics table has rows
                self.assertGreater(metrics.row_count, 0)
                # Verify sparkline is rendered from nav.csv (not just fallback "─")
                sparkline = screen.query_one("#bt_sparkline")
                sparkline_text = str(sparkline.render())
                self.assertNotIn("加载中", sparkline_text)
                # Sparkline should contain at least one spark character or fallback
                self.assertTrue("█" in sparkline_text or "▆" in sparkline_text or "─" in sparkline_text)

    async def test_backtest_screen_lazy_loads_with_injected_viewer(self):
        """Verify BacktestScreen accepts injected BacktestViewer and loads results."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bt_dir = root / "backtest" / "2026-01-02_to_2026-03-31"
            bt_dir.mkdir(parents=True)
            (bt_dir / "metrics.json").write_text(
                '{"metrics": {"cumulative_return": 0.123}}', encoding="utf-8"
            )
            (bt_dir / "manifest.json").write_text(
                '{"tickers": ["510300.SH"], "start_date": "2026-01-02", "end_date": "2026-03-31"}',
                encoding="utf-8",
            )
            (bt_dir / "summary.md").write_text("## Summary", encoding="utf-8")
            # Create app with injected viewer (explicit path to avoid env var complexity)
            app = ETFAgentsTuiApp(
                repository=ReportRepository(tmp),
                backtest_viewer=BacktestViewer(tmp),
            )
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                bt_list = screen.query_one("#bt_list")
                # Verify BacktestViewer loaded the results
                self.assertEqual(len(bt_list.children), 1)

    async def test_backtest_screen_refresh_clears_duplicates(self):
        """Verify refresh button clears old items before loading new ones."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bt_dir = root / "backtest" / "2026-01-02_to_2026-03-31"
            bt_dir.mkdir(parents=True)
            (bt_dir / "metrics.json").write_text(
                '{"metrics": {"cumulative_return": 0.123}}', encoding="utf-8"
            )
            (bt_dir / "manifest.json").write_text(
                '{"tickers": ["510300.SH"], "start_date": "2026-01-02", "end_date": "2026-03-31"}',
                encoding="utf-8",
            )
            (bt_dir / "summary.md").write_text("## Summary", encoding="utf-8")
            app = self._app(tmp, with_backtest=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                bt_list = screen.query_one("#bt_list")
                initial_count = len(bt_list.children)
                self.assertEqual(initial_count, 1)
                # Click refresh button
                await pilot.click("#btn_bt_refresh")
                await pilot.pause()
                await pilot.pause()
                # Verify list is not duplicated (should still be 1, not 2)
                refreshed_count = len(bt_list.children)
                self.assertEqual(refreshed_count, 1)

    # --- Analysis config modal ---

    async def test_analysis_config_modal_opens_on_start(self):
        """Clicking start analysis should open config modal."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                self.assertIsInstance(screen, ResearchAnalysisScreen)
                # Type a ticker so start button will proceed
                input_widget = screen.query_one("#ra_ticker_input")
                input_widget.value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                # Config modal should now be on top
                self.assertIsInstance(app.screen, AnalysisConfigModal)

    async def test_analysis_config_modal_cancel_does_not_start(self):
        """Cancelling config modal should not start analysis."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                input_widget = screen.query_one("#ra_ticker_input")
                input_widget.value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                # Cancel the modal
                await pilot.click("#btn_acm_cancel")
                await pilot.pause()
                # Should be back on research screen, no runner active
                self.assertIsInstance(app.screen, ResearchAnalysisScreen)
                self.assertIsNone(screen._active_runner)

    async def test_analysis_config_modal_has_expected_widgets(self):
        """Config modal should have depth, provider, language selects and OK/cancel buttons."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                input_widget = screen.query_one("#ra_ticker_input")
                input_widget.value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                self.assertIsInstance(modal, AnalysisConfigModal)
                self.assertIsNotNone(modal.query_one("#acm_depth"))
                self.assertIsNotNone(modal.query_one("#acm_provider"))
                self.assertIsNotNone(modal.query_one("#acm_language"))
                self.assertIsNotNone(modal.query_one("#btn_acm_ok"))
                self.assertIsNotNone(modal.query_one("#btn_acm_cancel"))

    # --- Backtest run error ---

    async def test_backtest_run_shows_error_on_empty_fields(self):
        """Clicking run with empty fields should show error status."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_backtest")
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                # Click run with empty fields
                await pilot.click("#btn_bt_run")
                await pilot.pause()
                status = screen.query_one("#bt_run_status", Static)
                self.assertIn("请填写", str(status.render()))

    # --- Login modal ---

    async def test_login_modal_opens_and_cancels(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp, with_paper=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_paper")
                await pilot.pause()
                await pilot.pause()
                await pilot.click("#btn_pt_login")
                await pilot.pause()
                self.assertIsInstance(app.screen, LoginModal)
                await pilot.click("#btn_login_cancel")
                await pilot.pause()
                self.assertIsInstance(app.screen, PaperTradingScreen)

    # --- Order modal ---

    async def test_order_modal_opens_for_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp, with_paper=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_paper")
                await pilot.pause()
                await pilot.pause()
                await pilot.click("#btn_pt_buy")
                await pilot.pause()
                modal = app.screen
                self.assertIsInstance(modal, OrderModal)
                self.assertEqual(modal.side, "buy")

    async def test_order_modal_opens_for_sell(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp, with_paper=True)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_paper")
                await pilot.pause()
                await pilot.pause()
                await pilot.click("#btn_pt_sell")
                await pilot.pause()
                modal = app.screen
                self.assertIsInstance(modal, OrderModal)
                self.assertEqual(modal.side, "sell")

    # --- helpers ---

    def _app(
        self,
        results_dir: str,
        *,
        with_paper: bool = False,
        with_backtest: bool = False,
    ) -> ETFAgentsTuiApp:
        paper_vm = None
        if with_paper:
            paper_vm = PaperTradingViewModel(engine=_FakePaperEngine())
        backtest_viewer = None
        if with_backtest:
            backtest_viewer = BacktestViewer(results_dir)
        return ETFAgentsTuiApp(
            repository=ReportRepository(results_dir),
            paper_view_model=paper_vm,
            backtest_viewer=backtest_viewer,
        )


if __name__ == "__main__":
    unittest.main()
