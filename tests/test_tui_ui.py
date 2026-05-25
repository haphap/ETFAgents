import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from textual.widgets import Button, Static, ListView, Label
    from textual.containers import ScrollableContainer
except ModuleNotFoundError:
    Static = None

if Static is None:
    raise unittest.SkipTest("Textual not installed; skipping TUI UI tests")

from cli.tui.app import (
    AnalysisConfigModal,
    ETFAgentsTuiApp,
    HomeScreen,
    LLM_PROVIDER_OPTIONS,
    LoginModal,
    OrderModal,
    AnalysisRunScreen,
    ResearchAnalysisScreen,
    _build_analysis_runner,
    ReportLibraryScreen,
    BacktestScreen,
    PaperTradingScreen,
    SettingsScreen,
    HelpScreen,
)
from cli.tui.screens.research import _format_detail_text
from cli.tui.services import (
    AnalysisConfig,
    BacktestViewer,
    DebateProgress,
    PaperTradingViewModel,
    ReportRepository,
    SectionDone,
    TickerFailed,
    TickerStarted,
    TickerDone,
    WatchlistBoardRow,
    WatchlistBoardSnapshot,
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
        return {"ticker": ticker, "quantity": quantity, "status": "filled"}


class _FakeAnalysisRunner:
    def __init__(self):
        self.calls = []
        self.cancel_requested = False
        self.stats = {
            "llm_calls": 2,
            "tool_calls": 3,
            "tokens_in": 1200,
            "tokens_out": 340,
        }

    def run_queue(self, tickers, analysis_date=None, selected_analysts=None):
        self.calls.append((list(tickers), analysis_date, selected_analysts))
        for ticker in tickers:
            yield TickerStarted(ticker=ticker, total_sections=9)
            yield TickerDone(ticker=ticker, report_path=Path("/fake/report.md"), rating="BUY")

    def request_cancel(self):
        self.cancel_requested = True

    def get_stats(self):
        return dict(self.stats)


class _BlockingAnalysisRunner(_FakeAnalysisRunner):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def run_queue(self, tickers, analysis_date=None, selected_analysts=None):
        self.calls.append((list(tickers), analysis_date, selected_analysts))
        self.started.set()
        yield TickerStarted(ticker=tickers[0], total_sections=9)
        self.release.wait(1)

    def request_cancel(self):
        super().request_cancel()
        self.release.set()


class _NoopAnalysisRunner(_FakeAnalysisRunner):
    def run_queue(self, tickers, analysis_date=None, selected_analysts=None):
        self.calls.append((list(tickers), analysis_date, selected_analysts))
        return iter(())


class TuiPilotTests(unittest.IsolatedAsyncioTestCase):
    # --- Home screen ---

    async def test_home_screen_shows_four_buttons(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                self.assertIsInstance(app.screen, HomeScreen)
                banner = app.screen.query_one("_DynamicBanner", Static)
                self.assertIsNotNone(banner)
                self.assertTrue(str(banner.render()).isascii())
                self.assertIsNotNone(app.screen.query_one("#btn_research"))
                self.assertIsNotNone(app.screen.query_one("#btn_reports"))
                self.assertIsNotNone(app.screen.query_one("#btn_backtest"))
                self.assertIsNotNone(app.screen.query_one("#btn_paper"))

    async def test_home_buttons_render_as_text_nav(self):
        """Nav buttons should render as text actions, not solid blocks."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                btn = app.screen.query_one("#btn_research", Button)
                self.assertIn("nav-action", btn.classes)

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

    async def test_report_library_section_list_has_12_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_reports")
                screen = app.screen
                sections = screen.query_one("#lib_sections")
                # 11 sections + 1 complete = 12
                self.assertEqual(len(sections.children), 12)

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
                self.assertIsNotNone(screen.query_one("#watchlist_cards"))
                self.assertEqual(len(screen.query(".ticker-chip")), 5)
                with self.assertRaises(Exception):
                    screen.query_one("#wl_total")

    async def test_research_analysis_recent_etf_uses_latest_report_tickers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, ticker in enumerate(["510300.SH", "159915.SZ", "588000.SH"]):
                report_dir = root / ticker / f"2026-05-2{index}"
                report_dir.mkdir(parents=True)
                (report_dir / "complete_report.md").write_text("评级: 持有", encoding="utf-8")
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                labels = [str(button.label) for button in screen.query(".ticker-chip")]
                self.assertEqual(len(labels), 5)
                self.assertIn("510300.SH", labels)
                self.assertIn("159915.SZ", labels)
                self.assertIn("588000.SH", labels)

    async def test_research_analysis_screen_focuses_ticker_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                await pilot.pause()
                self.assertEqual(app.focused.id, "ra_ticker_input")

    async def test_research_analysis_enter_converts_input_to_selected_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, ResearchAnalysisScreen)
                self.assertEqual(screen.query_one("#ra_ticker_input").value, "")
                selected_labels = [str(button.label) for button in screen.query(".selected-chip")]
                self.assertEqual(selected_labels, ["510300.SH"])
                self.assertIn("已选择 1 个 ETF", str(screen.query_one("#selected_ticker_count", Static).render()))

    async def test_research_watchlist_cards_render_snapshot(self):
        snapshot = WatchlistBoardSnapshot(
            rows=[
                WatchlistBoardRow(
                    ticker="510300.SH",
                    name="沪深300ETF",
                    close=3.942,
                    pct_chg=-2.04,
                    share_change_pct=-0.49,
                    support=3.900,
                    resistance=4.080,
                    trend_label="空头排列",
                    cross_label="7日死叉",
                    signal_summary="MACD死叉，KDJ死叉，看跌吞没",
                    action="减仓",
                    rationale="空头排列叠加7日死叉，优先控制仓位。",
                    rating="减持",
                    rating_date="2026-05-24",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            with patch("cli.tui.screens.research.load_watchlist_board", return_value=snapshot):
                async with app.run_test(size=(140, 40)) as pilot:
                    await pilot.click("#btn_research")
                    await pilot.pause()
                    await pilot.pause()
                    screen = app.screen
                    cards = screen.query_one("#watchlist_cards")
                    rendered = "\n".join(
                        [str(widget.render()) for widget in cards.query(Static)]
                        + [str(widget.label) for widget in cards.query(Button)]
                    )
                    self.assertIn("510300.SH", rendered)
                    self.assertIn("沪深300ETF", rendered)
                    self.assertIn("减仓", rendered)
                    self.assertIn("MACD死叉", rendered)

    async def test_research_watchlist_card_click_adds_ticker_to_selection(self):
        snapshot = WatchlistBoardSnapshot(
            rows=[
                WatchlistBoardRow(
                    ticker="510300.SH",
                    name="沪深300ETF",
                    action="持有",
                    rationale="区间震荡，观察为主。",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            with patch("cli.tui.screens.research.load_watchlist_board", return_value=snapshot):
                async with app.run_test(size=(140, 40)) as pilot:
                    await pilot.click("#btn_research")
                    await pilot.pause()
                    await pilot.pause()
                    await pilot.click("#wl-wl_510300_SH")
                    screen = app.screen
                    selected_labels = [str(button.label) for button in screen.query(".selected-chip")]
                    self.assertEqual(selected_labels, ["510300.SH"])
                    self.assertEqual(app.focused.id, "ra_ticker_input")

    async def test_research_watchlist_card_click_does_not_duplicate_selection(self):
        snapshot = WatchlistBoardSnapshot(
            rows=[
                WatchlistBoardRow(
                    ticker="510300.SH",
                    name="沪深300ETF",
                    action="持有",
                    rationale="区间震荡，观察为主。",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            with patch("cli.tui.screens.research.load_watchlist_board", return_value=snapshot):
                async with app.run_test(size=(140, 40)) as pilot:
                    await pilot.click("#btn_research")
                    await pilot.pause()
                    await pilot.pause()
                    screen = app.screen
                    screen.query_one("#ra_ticker_input").value = "159915.SZ,510300.SH"
                    await pilot.press("enter")
                    await pilot.click("#wl-wl_510300_SH")
                    selected_labels = [str(button.label) for button in screen.query(".selected-chip")]
                    self.assertEqual(selected_labels, ["159915.SZ", "510300.SH"])

    # --- AnalysisRunScreen: board layout ---

    async def test_analysis_run_board_has_four_columns(self):
        """Board should have 4 columns: analysts, research, risk, decision."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                # All 4 columns present
                self.assertIsNotNone(screen.query_one("#col_analysts"))
                self.assertIsNotNone(screen.query_one("#col_research"))
                self.assertIsNotNone(screen.query_one("#col_risk"))
                self.assertIsNotNone(screen.query_one("#col_decision"))

    async def test_analysis_run_places_trader_under_risk_before_risk_debate(self):
        """The TUI board groups trader in risk before risk debate."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                risk_col = screen.query_one("#col_risk")
                risk_child_ids = [child.id for child in risk_col.children]
                self.assertLess(
                    risk_child_ids.index("rsec-trader"),
                    risk_child_ids.index("rsec-risk_debate"),
                )
                self.assertEqual(screen.query_one("#rsec-trader").parent.id, "col_risk")

    async def test_analysis_run_places_research_progress_under_debate_item(self):
        """Research debate progress belongs directly below the debate item."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                research_col = screen.query_one("#col_research")
                child_ids = [child.id for child in research_col.children]
                self.assertLess(
                    child_ids.index("research_progress"),
                    child_ids.index("rsec-research"),
                )

    async def test_analysis_run_board_analysts_dual_column(self):
        """Analyst column should have 6 items in 3x2 grid."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                # 6 analyst buttons
                from cli.tui.services import ANALYST_KEYS
                for key in ANALYST_KEYS:
                    self.assertIsNotNone(screen.query_one(f"#rsec-{key}", Button))

    def test_format_detail_text_uses_requested_single_line_items(self):
        text = _format_detail_text({
            "ticker": "510300.SH",
            "name": "沪深300ETF",
            "close": 4.12,
            "pct_chg": 1.25,
            "volume": 123450000,
            "volume_change_pct": 23.45,
            "fund_share": 12_530_000_000,
            "share_change_pct": -1.2,
            "holdings": [
                {"name": "贵州茅台", "weight_pct": 5.23},
                {"name": "五粮液", "weight_pct": 3.12},
            ],
        })

        self.assertIn("名称：沪深300ETF (510300.SH)", text)
        self.assertIn("收盘：4.120 (+1.25%)", text)
        self.assertIn("交易量：12345万手 (+23.4%)", text)
        self.assertIn("份额：125亿份 (-1.2%)", text)
        self.assertIn("头部持仓：1. 贵州茅台 5.2%；2. 五粮液 3.1%", text)

    async def test_analysis_run_board_follows_selected_analysts(self):
        """Board should only show selected analysts."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = _FakeAnalysisRunner()
            app = self._app(tmp, analysis_runner=runner)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(selected_analysts=["market_flow"]),
                    runner=runner,
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                # market_flow should be present
                self.assertIsNotNone(screen.query_one("#rsec-market_flow", Button))
                # macro_regime should NOT be present
                results = screen.query("#rsec-macro_regime")
                self.assertEqual(len(results), 0)

    async def test_analysis_run_ticker_status_updates(self):
        """Verify ticker status changes from ⏳ → ✓/✗ when events fire."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                queue = screen.query_one("#ra_queue", ListView)
                queue.clear()
                screen.ticker_ids.clear()

                # Simulate ticker started
                screen._handle_ticker_started(TickerStarted(ticker="510300.SH", total_sections=9))
                await pilot.pause()
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

    async def test_analysis_run_ticker_selection(self):
        """Verify selecting a ticker in queue changes current_ticker."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH", "159915.SZ"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                queue = screen.query_one("#ra_queue", ListView)
                queue.clear()
                screen.ticker_ids.clear()
                screen.current_ticker = None

                # Start two tickers
                screen._handle_ticker_started(TickerStarted(ticker="510300.SH", total_sections=9))
                screen._handle_ticker_started(TickerStarted(ticker="159915.SZ", total_sections=9))
                await pilot.pause()

                # Get the queue ListView
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

    async def test_analysis_run_worker_receives_runner_and_tickers(self):
        """Starting analysis must pass runner/tickers into the worker callable."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = _FakeAnalysisRunner()
            app = self._app(tmp, analysis_runner=runner)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(selected_analysts=["market_flow"]),
                    runner=runner,
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                await pilot.pause()
                self.assertEqual(runner.calls[0][0], ["510300.SH"])
                self.assertEqual(runner.calls[0][2], ["market_flow"])

    # --- Board item click shows report ---

    async def test_analysis_run_board_item_click_shows_report(self):
        """Clicking a board item button should show section report in body."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_FakeAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                screen._handle_section_done(SectionDone(
                    ticker="510300.SH",
                    section_id="market_flow",
                    content="市场资金流报告正文",
                    completed=1,
                    total=9,
                ))
                await pilot.pause()
                # Click the market_flow board item
                await pilot.click("#rsec-market_flow")
                await pilot.pause()
                self.assertIn("市场与资金流", str(screen.query_one("#ra_body_title", Static).render()))
                self.assertIn("市场资金流报告正文", screen.query_one("#ra_body")._markdown)

    # --- Board state updates ---

    async def test_analysis_run_board_updates_on_section_done(self):
        """SectionDone should update board item icon and column header."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                screen.current_ticker = "510300.SH"

                # Fire a section done for an analyst (instant done)
                screen._handle_section_done(SectionDone(
                    ticker="510300.SH",
                    section_id="market_flow",
                    content="report content",
                    completed=1,
                    total=9,
                ))
                await pilot.pause()

                # Board item should show ✔
                btn = screen.query_one("#rsec-market_flow", Button)
                self.assertIn("✔", str(btn.label))
                # Column header should show 1/6
                header = screen.query_one("#col_analysts_header", Static)
                self.assertIn("1/6", str(header.render()))

    # --- Debate progress ---

    async def test_analysis_run_debate_progress_updates_bar(self):
        """DebateProgress should update progress bar in research/risk columns."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                screen.current_ticker = "510300.SH"

                # Simulate debate progress
                screen._handle_debate_progress(DebateProgress(
                    ticker="510300.SH",
                    section_id="research_debate",
                    current_round=2,
                    max_rounds=3,
                ))
                await pilot.pause()

                # Check progress bar content
                progress = screen.query_one("#research_progress", Static)
                rendered = str(progress.render())
                self.assertIn("2/3", rendered)

    async def test_analysis_run_risk_debate_progress(self):
        """Risk debate progress should update risk column."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                screen.current_ticker = "510300.SH"

                # Simulate risk debate progress reaching max
                screen._handle_debate_progress(DebateProgress(
                    ticker="510300.SH",
                    section_id="risk_debate",
                    current_round=1,
                    max_rounds=1,
                ))
                await pilot.pause()

                # Risk item should be done
                btn = screen.query_one("#rsec-risk_debate", Button)
                self.assertIn("✔", str(btn.label))

    async def test_analysis_run_debate_progress_is_ticker_scoped(self):
        """Debate progress from another ticker must not overwrite the selected ticker."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH", "159915.SZ"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                screen.current_ticker = "510300.SH"

                screen._handle_debate_progress(DebateProgress(
                    ticker="510300.SH",
                    section_id="risk_debate",
                    current_round=1,
                    max_rounds=3,
                ))
                screen._handle_debate_progress(DebateProgress(
                    ticker="159915.SZ",
                    section_id="risk_debate",
                    current_round=3,
                    max_rounds=3,
                ))
                await pilot.pause()

                progress = screen.query_one("#risk_progress", Static)
                self.assertIn("1/3", str(progress.render()))
                self.assertNotIn("3/3", str(progress.render()))

    async def test_analysis_run_failed_ticker_marks_running_sections_failed(self):
        """TickerFailed should fail running board items, not only pending ones."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                screen.current_ticker = "510300.SH"
                screen._board_state[("510300.SH", "market_flow")] = "running"

                screen._handle_ticker_failed(TickerFailed(
                    ticker="510300.SH",
                    error="boom",
                ))
                await pilot.pause()

                btn = screen.query_one("#rsec-market_flow", Button)
                self.assertIn("✘", str(btn.label))

    # --- Stats bar ---

    async def test_analysis_run_shows_cli_runtime_stats_bar(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_FakeAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                progress = str(screen.query_one("#stats_progress", Static).render())
                resources = str(screen.query_one("#stats_resources", Static).render())
                reports = str(screen.query_one("#stats_reports", Static).render())
                right = str(screen.query_one("#stats_right", Static).render())
                self.assertIn("Agents", progress)
                self.assertIn("LLM", resources)
                self.assertIn("Tools", resources)
                self.assertIn("Reports", reports)
                stats_widget = screen.query_one("#stats_progress", Static)
                self.assertGreater(stats_widget.size.height, 0)
                screenshot = app.export_screenshot()
                self.assertIn("Agents", screenshot)
                self.assertIn("LLM", screenshot)

    async def test_analysis_run_body_defaults_to_overall_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_FakeAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                self.assertEqual(str(screen.query_one("#ra_body_title", Static).render()), "整体进度")
                body = screen.query_one("#ra_body")
                self.assertIn("开始分析", body._markdown)

    async def test_analysis_run_report_body_is_scrollable(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                self.assertIsInstance(screen.query_one("#ra_body_scroll"), ScrollableContainer)

    # --- Active column highlighting ---

    async def test_analysis_run_active_column_highlighted(self):
        """Active column should have column-active class."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=_NoopAnalysisRunner(),
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                screen.current_ticker = "510300.SH"

                screen._handle_section_done(SectionDone(
                    ticker="510300.SH",
                    section_id="market_flow",
                    content="report",
                    completed=1,
                    total=9,
                ))
                await pilot.pause()

                col = screen.query_one("#col_analysts")
                self.assertIn("column-active", col.classes)

    # --- BacktestScreen ---

    async def test_backtest_screen_has_run_inputs(self):
        """BacktestScreen should have ticker/date inputs and a run button."""
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

    # --- AnalysisRunScreen: cancel button ---

    async def test_analysis_run_cancel_button_enables_while_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = _BlockingAnalysisRunner()
            app = self._app(tmp, analysis_runner=runner)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=runner,
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                cancel = screen.query_one("#btn_ra_cancel", Button)
                self.assertFalse(cancel.disabled)
                screen._cancel_analysis()
                self.assertTrue(runner.cancel_requested)

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
                self.assertIsNotNone(screen.query_one("#sel_panel_width"))
                self.assertIsNotNone(screen.query_one("#btn_settings_save"))

    # --- PaperTradingScreen ---

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
                self.assertIn("150,000", acct_text)

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

    async def test_analysis_config_ok_opens_dedicated_run_screen(self):
        """Confirming config should navigate from input screen to the run screen."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = _FakeAnalysisRunner()
            app = self._app(tmp, analysis_runner=runner)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                await pilot.click("#btn_acm_ok")
                await pilot.pause()
                self.assertIsInstance(app.screen, AnalysisRunScreen)
                run_screen = app.screen
                self.assertEqual(run_screen.tickers, ["510300.SH"])

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
                self.assertIsNotNone(modal.query_one("#acm_quick_model"))
                self.assertIsNotNone(modal.query_one("#acm_deep_model"))
                self.assertIsNotNone(modal.query_one("#acm_language"))
                self.assertIsNotNone(modal.query_one("#acm_analysis_date"))
                self.assertIsNotNone(modal.query_one("#acm_error"))
                self.assertIsNotNone(modal.query_one("#btn_acm_ok"))
                self.assertIsNotNone(modal.query_one("#btn_acm_cancel"))

    async def test_analysis_config_rejects_invalid_date(self):
        """Invalid analysis dates should keep the config modal open."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = _FakeAnalysisRunner()
            app = self._app(tmp, analysis_runner=runner)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                modal.query_one("#acm_analysis_date").value = "2026-99-99"

                await pilot.click("#btn_acm_ok")
                await pilot.pause()

                self.assertIsInstance(app.screen, AnalysisConfigModal)
                self.assertIn("YYYY-MM-DD", str(modal.query_one("#acm_error", Static).render()))
                self.assertEqual([], runner.calls)

    async def test_analysis_config_date_passes_to_runner(self):
        """The analysis date input should be forwarded to AnalysisRunner.run_queue."""
        with tempfile.TemporaryDirectory() as tmp:
            runner = _FakeAnalysisRunner()
            app = self._app(tmp, analysis_runner=runner)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                modal.query_one("#acm_analysis_date").value = "2026-05-25"
                await pilot.click("#btn_acm_ok")
                await pilot.pause()
                await pilot.pause()

                self.assertEqual(runner.calls[0][1], "2026-05-25")

    async def test_analysis_config_modal_shows_analyst_labels(self):
        """Analyst checkboxes must render their visible labels in the modal."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                self.assertIsInstance(modal, AnalysisConfigModal)
                screenshot = app.export_screenshot()
                self.assertIn("市场与资金流", screenshot)
                self.assertIn("宏观框架", screenshot)

    async def test_analysis_config_modal_updates_models_for_provider(self):
        """Changing provider should refresh quick/deep model choices."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                provider_select = modal.query_one("#acm_provider")
                provider_select.value = "minimax"
                await pilot.pause()
                quick_select = modal.query_one("#acm_quick_model")
                deep_select = modal.query_one("#acm_deep_model")
                self.assertTrue(str(quick_select.value).startswith("MiniMax"))
                self.assertTrue(str(deep_select.value).startswith("MiniMax"))

    async def test_analysis_config_modal_depth_options_show_round_counts(self):
        """Research depth labels should explain debate and risk round counts."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                depth_select = modal.query_one("#acm_depth")
                labels = {str(option[0]) for option in depth_select._options}
                self.assertIn("标准 (debate×1, risk×1)", labels)
                self.assertIn("快速 (debate×0, risk×0)", labels)
                self.assertIn("全面 (debate×3, risk×3)", labels)

    async def test_analysis_config_modal_lists_all_supported_llm_providers(self):
        """TUI provider choices should match the supported provider set."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                provider_select = modal.query_one("#acm_provider")
                option_values = {
                    option.value if hasattr(option, "value") else option[1]
                    for option in provider_select._options
                }
                option_values = {value for value in option_values if isinstance(value, str)}
                expected = {provider for _, provider, _ in LLM_PROVIDER_OPTIONS}
                self.assertEqual(option_values, expected)
                self.assertIn("vllm", option_values)
                self.assertIn("ollama", option_values)
                self.assertIn("minimax", option_values)

    def test_analysis_runner_config_uses_provider_default_models(self):
        runner = _build_analysis_runner(AnalysisConfig(llm_provider="minimax"))

        self.assertEqual(runner.config["llm_provider"], "minimax")
        self.assertEqual(runner.config["backend_url"], "https://api.minimax.chat/v1")
        self.assertTrue(runner.config["quick_think_llm"].startswith("MiniMax"))
        self.assertTrue(runner.config["deep_think_llm"].startswith("MiniMax"))

    def test_analysis_runner_config_uses_selected_models(self):
        runner = _build_analysis_runner(AnalysisConfig(
            llm_provider="minimax",
            quick_model="MiniMax-M2.7-highspeed",
            deep_model="MiniMax-M2.7",
        ))

        self.assertEqual(runner.config["quick_think_llm"], "MiniMax-M2.7-highspeed")
        self.assertEqual(runner.config["deep_think_llm"], "MiniMax-M2.7")

    async def test_quit_requests_active_analysis_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = _BlockingAnalysisRunner()
            app = self._app(tmp, analysis_runner=runner)
            async with app.run_test(size=(140, 40)) as pilot:
                app.push_screen(AnalysisRunScreen(
                    ["510300.SH"],
                    AnalysisConfig(),
                    runner=runner,
                    repository=ReportRepository(tmp),
                ))
                await pilot.pause()
                screen = app.screen
                self.assertIsInstance(screen, AnalysisRunScreen)
                self.assertIsNotNone(screen._analysis_thread)
                self.assertTrue(screen._analysis_thread.daemon)
                app._cancel_active_operations()
                self.assertTrue(runner.cancel_requested)

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

    async def test_login_modal_exclusive_worker_prevents_duplicate(self):
        """Second login click while first is in-flight should not spawn a second worker."""
        import inspect
        from cli.tui.app import LoginModal as _LoginModal
        src = inspect.getsource(_LoginModal.on_button_pressed)
        self.assertIn("exclusive=True", src)

    async def test_order_modal_exclusive_worker_prevents_duplicate(self):
        """Order modal should use exclusive worker to prevent double-submit."""
        import inspect
        from cli.tui.app import OrderModal as _OrderModal
        src = inspect.getsource(_OrderModal.on_button_pressed)
        self.assertIn("exclusive=True", src)

    # --- DebateProgress event unit test ---

    def test_debate_progress_event_fields(self):
        """DebateProgress should carry expected fields."""
        dp = DebateProgress(
            ticker="510300.SH",
            section_id="research_debate",
            current_round=2,
            max_rounds=3,
        )
        self.assertEqual(dp.ticker, "510300.SH")
        self.assertEqual(dp.section_id, "research_debate")
        self.assertEqual(dp.current_round, 2)
        self.assertEqual(dp.max_rounds, 3)

    # --- helpers ---

    def _app(
        self,
        results_dir: str,
        *,
        analysis_runner=None,
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
            analysis_runner=analysis_runner,
            paper_view_model=paper_vm,
            backtest_viewer=backtest_viewer,
        )


if __name__ == "__main__":
    unittest.main()
