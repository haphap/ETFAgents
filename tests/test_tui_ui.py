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
from cli.tui.screens.research import (
    _extract_price_from_text,
    _format_detail_rich,
    _format_detail_text,
    _format_execution_summary,
    _highlight_report_numbers,
    _price_ruler,
    _truncate_condition,
    _weight_bar,
)
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


def _list_view_labels(list_view: ListView) -> list[str]:
    return [str(item.query_one(Label).render()) for item in list_view.children]


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
                self.assertEqual(len(screen.query(".recent-card")), 5)
                self.assertTrue(screen.query_one("#btn_ra_start", Button).disabled)
                with self.assertRaises(Exception):
                    screen.query_one("#wl_total")

    async def test_research_analysis_recent_cards_use_latest_report_metadata(self):
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
                labels = [str(button.label) for button in screen.query(".recent-card")]
                self.assertEqual(len(labels), 5)
                self.assertTrue(any("510300.SH" in label and "沪深300ETF" in label for label in labels))
                self.assertTrue(any("159915.SZ" in label and "创业板ETF" in label for label in labels))
                self.assertTrue(any("588000.SH" in label and "2026-05-22" in label for label in labels))

    async def test_research_analysis_recent_card_click_adds_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                await pilot.click("#recent-recent_510300_SH")
                screen = app.screen
                selected_labels = [str(button.label) for button in screen.query(".selected-chip")]
                self.assertEqual(selected_labels, ["510300.SH ×"])

    async def test_research_analysis_adding_second_recent_card_keeps_unique_tag_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                await pilot.click("#recent-recent_510300_SH")
                await pilot.click("#recent-recent_159915_SZ")
                await pilot.pause()
                screen = app.screen
                selected_labels = [str(button.label) for button in screen.query(".selected-chip")]
                self.assertEqual(selected_labels, ["510300.SH ×", "159915.SZ ×"])

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
                self.assertEqual(selected_labels, ["510300.SH ×"])
                self.assertIn("已选择 1 个 ETF", str(screen.query_one("#selected_ticker_count", Static).render()))
                self.assertFalse(screen.query_one("#btn_ra_start", Button).disabled)

    async def test_research_analysis_selected_tag_click_removes_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.press("enter")
                await pilot.pause()
                chip = screen.query_one(".selected-chip", Button)
                await pilot.click(f"#{chip.id}")
                self.assertEqual([str(button.label) for button in screen.query(".selected-chip")], [])
                self.assertTrue(screen.query_one("#btn_ra_start", Button).disabled)
                self.assertIn("已选择 0 个 ETF", str(screen.query_one("#selected_ticker_count", Static).render()))

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
                    self.assertEqual(selected_labels, ["510300.SH ×"])
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
                    self.assertEqual(selected_labels, ["159915.SZ ×", "510300.SH ×"])

    # --- AnalysisRunScreen: tab layout ---

    async def test_analysis_run_board_has_four_tabs(self):
        """Analysis run should expose compact team tabs."""
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
                self.assertIsNotNone(screen.query_one("#rtab-analysts", Button))
                self.assertIsNotNone(screen.query_one("#rtab-research", Button))
                self.assertIsNotNone(screen.query_one("#rtab-risk", Button))
                self.assertIsNotNone(screen.query_one("#rtab-decision", Button))

    async def test_analysis_run_groups_trader_under_risk_before_risk_debate(self):
        """The risk tab groups trader before risk debate."""
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
                risk_ids = [defn.section_id for defn in screen._section_group_defs()["risk"]]
                self.assertLess(risk_ids.index("trader"), risk_ids.index("risk_debate"))

    async def test_analysis_run_research_tab_contains_debate_and_manager(self):
        """Research tab contains debate before manager."""
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
                research_ids = [defn.section_id for defn in screen._section_group_defs()["research"]]
                self.assertEqual(research_ids[:2], ["research_debate", "research"])

    async def test_analysis_run_analysts_tab_contains_selected_analysts(self):
        """Analyst tab should include configured analyst sections."""
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
                from cli.tui.services import ANALYST_KEYS
                analyst_ids = [defn.section_id for defn in screen._section_group_defs()["analysts"]]
                self.assertEqual(analyst_ids, ANALYST_KEYS)

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

    def test_format_detail_rich_uses_readable_holding_names_without_icons(self):
        components = _format_detail_rich({
            "ticker": "510300.SH",
            "name": "沪深300ETF",
            "close": 4.12,
            "pct_chg": 1.25,
            "volume": 123450000,
            "volume_change_pct": 23.45,
            "turnover_rate": 3.5,
            "fund_share": 12_530_000_000,
            "share_change_pct": -1.2,
            "holdings": [
                {"name": "中国石油", "weight_pct": 5.23},
            ],
        })

        self.assertIn("代码: 沪深300ETF", str(components["name_text"]))
        self.assertIn("换手: 3.5%", components["metrics_text"])
        self.assertIn("中国石油 5.2%", str(components["holdings_bars"]))
        self.assertNotIn("🏭 中国", str(components["holdings_bars"]))

    def test_analysis_run_config_summary_uses_provider_not_model(self):
        screen = AnalysisRunScreen(
            ["510300.SH"],
            AnalysisConfig(
                analysis_date="2026-05-25",
                llm_provider="deepseek",
                quick_model="gpt-5.4-mini",
                deep_model="gpt-5.4",
            ),
            runner=_NoopAnalysisRunner(),
        )

        summary = screen._config_summary()

        self.assertIn("日期: 2026-05-25", summary)
        self.assertIn("提供商: deepseek", summary)
        self.assertIn("深度:", summary)
        self.assertNotIn("模型", summary)
        self.assertNotIn("日:", summary)

    def test_highlight_report_numbers_skips_tables_and_code(self):
        text = _highlight_report_numbers(
            "目标价 2.058，仓位 2.0%\n"
            "| 指标 | 数值 |\n"
            "| close | 1.966 |\n"
            "代码 `price 1.23` 保持\n"
            "```\n"
            "stop 1.850\n"
            "```"
        )

        self.assertIn("目标价 **2.058**，仓位 **2.0%**", text)
        self.assertIn("| close | 1.966 |", text)
        self.assertIn("`price 1.23`", text)
        self.assertIn("stop 1.850", text)

    def test_weight_bar_renders_blocks(self):
        rendered = _weight_bar(25.0)
        self.assertIn("█", rendered)
        self.assertIn("░", rendered)
        self.assertIn("25.0%", rendered)

    def test_weight_bar_none_returns_dash(self):
        self.assertEqual(_weight_bar(None), "--")

    def test_price_ruler_shows_marker(self):
        rendered = _price_ruler(1.85, 1.966, 2.058)
        self.assertIn("╋", rendered)
        self.assertIn("1.85", rendered)
        self.assertIn("2.058", rendered)
        self.assertIn("止损", rendered)
        self.assertIn("目标", rendered)

    def test_price_ruler_degenerate_range_returns_empty(self):
        self.assertEqual(_price_ruler(2.0, 1.5, 2.0), "")

    def test_extract_price_from_text_finds_stop(self):
        signal = {
            "risk_controls": [
                "严格锚定2.025元动态止损线防范尾部流动性踩踏",
            ],
        }
        price = _extract_price_from_text(signal, ("risk_controls",), ("止损", "跌破"))
        self.assertEqual(price, 2.025)

    def test_extract_price_from_text_finds_add_target(self):
        signal = {
            "add_conditions": [
                "价格放量突破2.110元且份额连续3个交易日净流入",
            ],
        }
        price = _extract_price_from_text(signal, ("add_conditions",), ("突破", "加仓"))
        self.assertEqual(price, 2.110)

    def test_extract_price_from_text_returns_none_without_hint(self):
        signal = {"risk_controls": ["监控焦煤仓单异动"]}
        price = _extract_price_from_text(signal, ("risk_controls",), ("止损",))
        self.assertIsNone(price)

    def test_truncate_condition_at_sentence_break(self):
        text = "仅当价格回踩20日均线1.79元支撑带，且成交量达到近20日均量1.3倍以上时生效"
        truncated = _truncate_condition(text, 30)
        self.assertTrue(len(truncated) <= 31)  # may include the break char
        self.assertTrue(truncated.endswith("，") or truncated.endswith("…"))

    def test_truncate_condition_short_text_unchanged(self):
        self.assertEqual(_truncate_condition("短句。", 50), "短句。")

    def test_format_execution_summary_no_signal(self):
        rendered = str(_format_execution_summary(None))
        self.assertIn("等待", rendered)

    def test_format_execution_summary_rating_and_visuals(self):
        result = _format_execution_summary(
            {
                "rating": "OVERWEIGHT",
                "target_weight_pct": 25.0,
                "target_weight_min_pct": 20.0,
                "target_weight_max_pct": 30.0,
                "add_triggers": [{"metric": "close", "op": ">", "threshold": 2.058, "action": "add"}],
                "risk_rules": [{"metric": "close", "op": "<", "threshold": 1.85, "action": "stop"}],
            },
            {"close": 1.966},
        )
        self.assertIsInstance(result, str)
        # Rating
        self.assertIn("增持", result)
        self.assertIn("🟢", result)
        # Weight bar
        self.assertIn("█", result)
        self.assertIn("░", result)
        self.assertIn("25.0%", result)
        # Price ruler
        self.assertIn("╋", result)
        self.assertIn("2.058", result)
        self.assertIn("1.85", result)
        # Target/stop with emoji
        self.assertIn("🎯", result)
        self.assertIn("🛡", result)

    def test_format_execution_summary_extracts_prices_from_condition_text(self):
        """When structured triggers are empty, prices should be extracted from conditions."""
        result = _format_execution_summary(
            {
                "rating": "OVERWEIGHT",
                "target_weight_pct": 30.0,
                "add_triggers": [],
                "risk_rules": [],
                "add_conditions": [
                    "加仓触发条件为价格放量突破2.110元且份额连续3个交易日净流入",
                ],
                "risk_controls": [
                    "严格锚定2.025元动态止损线防范尾部流动性踩踏",
                ],
            },
            {"close": 2.084},
        )
        self.assertIn("2.11", result)
        self.assertIn("2.025", result)
        self.assertIn("╋", result)  # price ruler should appear

    async def test_analysis_run_renders_execution_summary_from_signal(self):
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
                screen._etf_details["510300.SH"] = {"ticker": "510300.SH", "close": 1.966}

                screen._handle_section_done(SectionDone(
                    ticker="510300.SH",
                    section_id="portfolio_manager",
                    content="持仓建议",
                    completed=9,
                    total=9,
                    backtest_signal={
                        "rating": "OVERWEIGHT",
                        "target_weight_pct": 2.0,
                        "target_weight_min_pct": 1.0,
                        "target_weight_max_pct": 3.0,
                        "execution_delay": "next_open",
                        "add_triggers": [{"metric": "close", "op": ">", "threshold": 2.058, "action": "add", "note": "突破加仓"}],
                        "risk_rules": [{"metric": "close", "op": "<", "threshold": 1.85, "action": "stop", "note": "跌破止损"}],
                    },
                ))
                await pilot.pause()

                screen._on_section_picked("execution_summary")
                await pilot.pause()
                rendered = screen.query_one("#ra_body")._markdown
                self.assertIn("增持", rendered)
                self.assertIn("2.0%", rendered)
                self.assertIn("2.058", rendered)
                self.assertIn("1.85", rendered)

    async def test_analysis_run_exec_summary_toggles_back_to_report(self):
        """Switching from execution summary to a report section shows the report."""
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
                    section_id="portfolio_manager",
                    content="PM report body",
                    completed=9,
                    total=9,
                    backtest_signal={"rating": "HOLD", "target_weight_pct": 2.0},
                ))
                await pilot.pause()

                screen._on_section_picked("execution_summary")
                await pilot.pause()
                self.assertIn("持有", screen.query_one("#ra_body")._markdown)

                screen._on_section_picked("portfolio_manager")
                await pilot.pause()
                self.assertIn("PM report body", screen.query_one("#ra_body")._markdown)

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
                analyst_ids = [defn.section_id for defn in screen._section_group_defs()["analysts"]]
                self.assertEqual(analyst_ids, ["market_flow"])

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

    # --- Tab section selection shows report ---

    async def test_analysis_run_section_picker_selection_shows_report(self):
        """Selecting a section from the tab picker should show its report."""
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
                await pilot.click("#rtab-analysts")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                self.assertIn("市场与资金流", str(screen.query_one("#ra_body_title", Static).render()))
                self.assertIn("市场资金流报告正文", screen.query_one("#ra_body")._markdown)
                self.assertIn("hidden-widget", screen.query_one("#ra_section_picker").classes)

    async def test_analysis_run_section_picker_closes_when_clicking_elsewhere(self):
        """The inline picker should behave like a popover, not a sticky modal."""
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
                await pilot.click("#rtab-analysts")
                await pilot.pause()
                self.assertNotIn("hidden-widget", screen.query_one("#ra_section_picker").classes)

                await pilot.click("#ra_body")
                await pilot.pause()
                self.assertIn("hidden-widget", screen.query_one("#ra_section_picker").classes)

    async def test_analysis_run_decision_picker_lists_execution_summary_under_pm(self):
        """Core summary is a decision subitem instead of a separate card."""
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
                    section_id="portfolio_manager",
                    content="PM",
                    completed=9,
                    total=9,
                    backtest_signal={"rating": "HOLD", "target_weight_pct": 2.0},
                ))
                await pilot.click("#rtab-decision")
                await pilot.pause()

                labels = _list_view_labels(screen.query_one("#section_picker_list", ListView))
                self.assertEqual(labels[:2], ["✓ 投资组合经理", "✓   核心执行摘要"])

    # --- Board state updates ---

    async def test_analysis_run_tabs_update_on_section_done(self):
        """SectionDone should update tab counts and active state."""
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

                tab = screen.query_one("#rtab-analysts", Button)
                self.assertIn("1/6", str(tab.label))
                self.assertIn("section-tab-active", tab.classes)

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

                screen._open_section_picker("research")
                await pilot.pause()
                labels = _list_view_labels(screen.app.screen.query_one("#section_picker_list", ListView))
                self.assertTrue(any("多空辩论" in label for label in labels))

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

                tab = screen.query_one("#rtab-risk", Button)
                self.assertIn("1/2", str(tab.label))

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

                self.assertEqual(screen._debate_rounds[("510300.SH", "risk_debate")], (1, 3))
                self.assertEqual(screen._debate_rounds[("159915.SZ", "risk_debate")], (3, 3))

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

                screen._open_section_picker("analysts")
                await pilot.pause()
                labels = _list_view_labels(screen.app.screen.query_one("#section_picker_list", ListView))
                self.assertTrue(any("✗ 市场与资金流" in label for label in labels))

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

    # --- Active tab highlighting ---

    async def test_analysis_run_active_tab_highlighted(self):
        """Active team tab should have section-tab-active class."""
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

                tab = screen.query_one("#rtab-analysts")
                self.assertIn("section-tab-active", tab.classes)

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
                self.assertIsNotNone(modal.query_one("#acm_summary"))
                self.assertIsNotNone(modal.query_one("#acm_error"))
                self.assertIsNotNone(modal.query_one("#btn_acm_ok"))
                self.assertIsNotNone(modal.query_one("#btn_acm_cancel"))
                self.assertEqual(str(modal.query_one("#btn_acm_ok", Button).label), "确认分析")
                self.assertEqual(str(modal.query_one("#btn_acm_cancel", Button).label), "取消")
                config_rows = modal.query(".acm-row")
                self.assertEqual(len(config_rows), 3)
                self.assertTrue(all(len(row.children) == 2 for row in config_rows))

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
                group_titles = [str(widget.render()) for widget in modal.query(".analyst-group-title")]
                self.assertIn("基本面 / 宏观", group_titles)
                self.assertIn("市场 / 微观", group_titles)

    async def test_analysis_config_modal_uses_short_model_labels_and_summary(self):
        """Collapsed model selectors should use short labels and show a config summary."""
        with tempfile.TemporaryDirectory() as tmp:
            app = self._app(tmp)
            async with app.run_test(size=(140, 40)) as pilot:
                await pilot.click("#btn_research")
                screen = app.screen
                screen.query_one("#ra_ticker_input").value = "510300.SH"
                await pilot.click("#btn_ra_start")
                await pilot.pause()
                modal = app.screen
                quick_select = modal.query_one("#acm_quick_model")
                quick_labels = {str(option[0]) for option in quick_select._options}
                self.assertTrue(all(" - " not in label for label in quick_labels))
                summary = str(modal.query_one("#acm_summary", Static).render())
                self.assertIn("已选择：", summary)
                self.assertIn("深度：标准", summary)

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
                self.assertIn("标准 (多空×1, 风控×1)", labels)
                self.assertIn("快速 (多空×0, 风控×0)", labels)
                self.assertIn("全面 (多空×3, 风控×3)", labels)

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
