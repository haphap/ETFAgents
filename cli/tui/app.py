"""Textual application for ETFAgents — M1: Report Library + Paper Trading."""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
)

from cli.tui.services import (
    AnalysisEvent,
    AnalysisRunner,
    BacktestViewer,
    IdRegistry,
    PaperTradingSnapshot,
    PaperTradingViewModel,
    ReportRepository,
    SECTION_DEFINITIONS,
    SectionDone,
    TickerCancelled,
    TickerDone,
    TickerFailed,
    TickerStarted,
)


# ---------------------------------------------------------------------------
# HomeScreen
# ---------------------------------------------------------------------------

class HomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="home"):
            yield Static("ETFAgents TUI", id="title")
            yield Static(
                "研究分析 · 研究报告库 · 回测 · 模拟交易",
                classes="subtitle",
            )
            yield Button("研究分析", id="btn_research", variant="primary")
            yield Button("研究报告库", id="btn_reports")
            yield Button("回测", id="btn_backtest")
            yield Button("模拟交易", id="btn_paper")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "btn_research": "research",
            "btn_reports": "reports",
            "btn_backtest": "backtest",
            "btn_paper": "paper",
        }
        screen = mapping.get(event.button.id or "")
        if screen:
            self.app.push_screen(screen)


# ---------------------------------------------------------------------------
# ResearchAnalysisScreen (M2)
# ---------------------------------------------------------------------------

class ResearchAnalysisScreen(Screen):
    """Run ETF analysis and stream results in real-time.

    Left pane: ticker input + start button + status list.
    Right-top: section status circles (○●).
    Right-bottom: Markdown body for selected section.
    """

    def __init__(self, runner: AnalysisRunner | None = None, repository: ReportRepository | None = None):
        super().__init__()
        self.runner = runner
        self.repository = repository or ReportRepository()
        self.ticker_ids = IdRegistry("ticker")
        self.section_contents: dict[tuple[str, str], str] = {}
        self.section_status: dict[tuple[str, str], bool] = {}
        self.current_ticker: str | None = None
        self.current_section: str = "portfolio_manager"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("研究分析", classes="pane-title")
                yield Static("输入 ETF 代码（逗号分隔）:", id="ra_label")
                yield Input(id="ra_ticker_input", classes="fill-list")
                yield Button("开始分析", id="btn_ra_start", variant="primary")
                yield Static("分析队列", classes="pane-title")
                yield ListView(id="ra_queue")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("报告章节", classes="pane-title")
                    yield ListView(id="ra_sections")
                with Vertical(classes="right-bottom"):
                    yield Static("报告正文", classes="pane-title")
                    yield Markdown("请输入 ETF 代码并点击开始分析。", id="ra_body")
        yield Footer()

    def on_mount(self) -> None:
        sections = self.query_one("#ra_sections", ListView)
        for defn in SECTION_DEFINITIONS:
            sections.append(ListItem(
                Label(f"{defn.team} / {defn.title}"),
                id=f"rsec-{defn.section_id}",
            ))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ra_start":
            self._start_analysis()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("rsec-"):
            self.current_section = item_id[5:]
            self._refresh_body()
        elif item_id.startswith("rtk-"):
            if item_id in self.ticker_ids:
                self.current_ticker = self.ticker_ids.resolve(item_id)
                self._refresh_body()

    def _start_analysis(self) -> None:
        input_widget = self.query_one("#ra_ticker_input", Input)
        tickers_str = input_widget.value.strip()
        if not tickers_str:
            return

        tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
        self.section_contents.clear()
        self.section_status.clear()
        self.ticker_ids.clear()
        self.current_ticker = tickers[0] if tickers else None
        self.current_section = "portfolio_manager"

        queue = self.query_one("#ra_queue", ListView)
        queue.clear()

        runner = self.runner or AnalysisRunner()
        self.run_worker(self._run_analysis, runner, tickers, thread=True, exclusive=True)

    def _run_analysis(self, runner: AnalysisRunner, tickers: list[str]) -> None:
        """Worker thread: stream analysis events."""
        try:
            for event in runner.run_queue(tickers):
                self.app.call_from_thread(self._apply_event, event)
        except Exception as exc:
            self.app.call_from_thread(self._show_error, str(exc))

    def _apply_event(self, event: AnalysisEvent) -> None:
        """UI thread: handle event."""
        if isinstance(event, TickerStarted):
            self._handle_ticker_started(event)
        elif isinstance(event, SectionDone):
            self._handle_section_done(event)
        elif isinstance(event, TickerDone):
            self._handle_ticker_done(event)
        elif isinstance(event, TickerFailed):
            self._handle_ticker_failed(event)
        elif isinstance(event, TickerCancelled):
            self._handle_ticker_cancelled(event)

    def _handle_ticker_started(self, event: TickerStarted) -> None:
        """Mark ticker as running in queue."""
        ticker_id = self.ticker_ids.register(event.ticker)
        queue = self.query_one("#ra_queue", ListView)
        queue.append(ListItem(Label(f"⏳ {event.ticker}"), id=ticker_id))
        if self.current_ticker is None:
            self.current_ticker = event.ticker

    def _handle_section_done(self, event: SectionDone) -> None:
        """Cache section content and update status."""
        self.section_contents[(event.ticker, event.section_id)] = event.content
        self.section_status[(event.ticker, event.section_id)] = True
        self._refresh_body()

    def _handle_ticker_done(self, event: TickerDone) -> None:
        """Mark ticker complete."""
        ticker_id = self.ticker_ids.register(event.ticker)
        rating_str = f" {event.rating}" if event.rating else ""
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            item.update(Label(f"✓ {event.ticker}{rating_str}"))
        except Exception:
            pass
        self.repository.invalidate()

    def _handle_ticker_failed(self, event: TickerFailed) -> None:
        """Mark ticker failed."""
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            item.update(Label(f"✗ {event.ticker}"))
        except Exception:
            pass
        body = self.query_one("#ra_body", Markdown)
        body.update(f"分析失败：{event.error}")

    def _handle_ticker_cancelled(self, event: TickerCancelled) -> None:
        """Mark ticker cancelled."""
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            item.update(Label(f"⊘ {event.ticker}"))
        except Exception:
            pass

    def _refresh_body(self) -> None:
        """Update Markdown body based on current selection."""
        if not self.current_ticker:
            self.query_one("#ra_body", Markdown).update("请选择一个 ticker。")
            return
        content = self.section_contents.get((self.current_ticker, self.current_section))
        if content:
            self.query_one("#ra_body", Markdown).update(content)
        else:
            self.query_one("#ra_body", Markdown).update("该章节暂无内容。")

    def _show_error(self, error: str) -> None:
        """Show error in body."""
        self.query_one("#ra_body", Markdown).update(f"分析出错：{error}")


# ---------------------------------------------------------------------------
# ReportLibraryScreen (M1)
# ---------------------------------------------------------------------------

class ReportLibraryScreen(Screen):
    """Browse locally saved single-ETF reports.

    Left pane: report list (ticker + date + rating).
    Right-top: section list (fixed 9 + complete).
    Right-bottom: selected section Markdown body.
    """

    def __init__(self, repository: ReportRepository) -> None:
        super().__init__()
        self.repository = repository
        self.records: list[Any] = []
        self.current: Any | None = None
        self.current_section: str = "portfolio_manager"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("报告列表", classes="pane-title")
                yield ListView(id="reports")
                yield Static("按 r 刷新本地报告", classes="hint")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("报告章节", classes="pane-title")
                    yield ListView(id="lib_sections")
                with Vertical(classes="right-bottom"):
                    yield Static("报告正文", classes="pane-title")
                    yield Markdown("暂无报告。", id="lib_body")
        yield Footer()

    def on_mount(self) -> None:
        sections = self.query_one("#lib_sections", ListView)
        for defn in SECTION_DEFINITIONS:
            sections.append(ListItem(
                Label(f"{defn.team} / {defn.title}"),
                id=f"lsec-{defn.section_id}",
            ))
        sections.append(ListItem(Label("完整报告"), id="lsec-complete"))
        self._load_reports()

    def _load_reports(self) -> None:
        self.records = self.repository.list_reports()
        reports = self.query_one("#reports", ListView)
        reports.clear()
        if not self.records:
            self.query_one("#lib_body", Markdown).update(
                "暂无报告。使用 `etfagents analyze` 生成首份报告。"
            )
            return
        for i, rec in enumerate(self.records):
            rating_str = f"  {rec.rating}" if rec.rating else ""
            reports.append(ListItem(
                Label(f"{rec.ticker}  {rec.date}{rating_str}"),
                id=f"rpt-{i}",
            ))
        self.current = self.records[0]
        self._refresh_body()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("rpt-"):
            idx = int(item_id[4:])
            if 0 <= idx < len(self.records):
                self.current = self.records[idx]
                self._refresh_body()
        elif item_id.startswith("lsec-"):
            self.current_section = item_id[5:]
            self._refresh_body()

    async def action_refresh_reports(self) -> None:
        self.repository.invalidate()
        self._load_reports()

    def _refresh_body(self) -> None:
        if self.current is None:
            return
        content = self.repository.read_section(self.current, self.current_section)
        self.query_one("#lib_body", Markdown).update(content or "该章节暂无内容。")


# ---------------------------------------------------------------------------
# BacktestScreen (M0 placeholder — full implementation in M3)
# ---------------------------------------------------------------------------

class BacktestScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="screen-body"):
            yield Static("回测（待实现）", classes="pane-title")
            yield Static("此功能将在后续版本中完成。", classes="hint")
        yield Footer()


# ---------------------------------------------------------------------------
# PaperTradingScreen (M1)
# ---------------------------------------------------------------------------

class PaperTradingScreen(Screen):
    """Read-only paper trading dashboard.

    Left pane: account summary + refresh button.
    Right-top: positions DataTable.
    Right-bottom: trade history DataTable.
    """

    def __init__(self, view_model: PaperTradingViewModel | None = None) -> None:
        super().__init__()
        self._view_model = view_model

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("模拟交易", classes="pane-title")
                yield Static("加载中...", id="pt_account")
                yield Button("刷新", id="btn_pt_refresh", variant="primary")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("持仓", classes="pane-title")
                    yield DataTable(id="pt_positions")
                with Vertical(classes="right-bottom"):
                    yield Static("交易历史", classes="pane-title")
                    yield DataTable(id="pt_trades")
        yield Footer()

    def on_mount(self) -> None:
        self._start_loading()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_pt_refresh":
            self._start_loading()

    async def action_refresh_reports(self) -> None:
        self._start_loading()

    def _start_loading(self) -> None:
        self.query_one("#pt_account", Static).update("加载中...")
        self.run_worker(self._fetch_snapshot, thread=True, exclusive=True)

    @property
    def view_model(self) -> PaperTradingViewModel:
        if self._view_model is None:
            self._view_model = PaperTradingViewModel()
        return self._view_model

    def _fetch_snapshot(self) -> None:
        try:
            snap = self.view_model.snapshot()
        except Exception as exc:
            self._safe_call_from_thread(self._show_error, str(exc))
            return
        self._safe_call_from_thread(self._apply_snapshot, snap)

    def _safe_call_from_thread(self, callback: Any, *args: Any) -> None:
        """call_from_thread that silently exits if the app is shutting down."""
        try:
            if not self.app._running:
                return
            self.app.call_from_thread(callback, *args)
        except Exception:
            pass

    def _apply_snapshot(self, snap: PaperTradingSnapshot) -> None:
        acct = snap.account
        self.query_one("#pt_account", Static).update(
            f"总资产: {acct.get('total_assets', 'N/A')}\n"
            f"现金: {acct.get('cash', 'N/A')}\n"
            f"市值: {acct.get('market_value', 'N/A')}\n"
            f"未实现盈亏: {acct.get('unrealized_pnl', 'N/A')}\n"
            f"已实现盈亏: {acct.get('realized_pnl', 'N/A')}"
        )

        # Positions table
        pos_table = self.query_one("#pt_positions", DataTable)
        pos_table.clear(columns=True)
        pos_table.add_columns("代码", "名称", "数量", "成本", "现价", "市值", "盈亏", "盈亏%")
        for p in snap.positions:
            pnl = p.get("unrealized_pnl", 0)
            pnl_pct = p.get("pnl_pct", 0)
            try:
                pnl = float(pnl)
            except (TypeError, ValueError):
                pnl = 0.0
            try:
                pnl_pct = float(pnl_pct)
            except (TypeError, ValueError):
                pnl_pct = 0.0
            pnl_str = f"{pnl:+.2f}"
            pct_str = f"{pnl_pct:+.2f}%"
            avg_cost = p.get("avg_cost", "")
            cur_price = p.get("current_price", "")
            mkt_val = p.get("market_value", "")
            pos_table.add_row(
                str(p.get("ticker", "")),
                str(p.get("name", "")),
                str(p.get("quantity", "")),
                f"{avg_cost:.4f}" if isinstance(avg_cost, (int, float)) else str(avg_cost),
                f"{cur_price:.4f}" if isinstance(cur_price, (int, float)) else str(cur_price),
                f"{mkt_val:.2f}" if isinstance(mkt_val, (int, float)) else str(mkt_val),
                pnl_str,
                pct_str,
            )

        # Trade history table
        trade_table = self.query_one("#pt_trades", DataTable)
        trade_table.clear(columns=True)
        trade_table.add_columns("时间", "代码", "方向", "数量", "价格", "金额", "盈亏")
        for t in snap.trades:
            trade_table.add_row(
                str(t.get("created_at", "")),
                str(t.get("ticker", "")),
                str(t.get("side", "")),
                str(t.get("quantity", "")),
                str(t.get("price", "")),
                str(t.get("amount", "")),
                str(t.get("pnl", "")),
            )

    def _show_error(self, error: str) -> None:
        self.query_one("#pt_account", Static).update(f"加载失败：{error}")


# ---------------------------------------------------------------------------
# HelpScreen
# ---------------------------------------------------------------------------

class HelpScreen(Screen):
    HELP_TEXT = """\
# ETFAgents TUI 帮助

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `q` | 退出 |
| `Escape` | 返回上一屏 |
| `r` | 刷新当前数据 |
| `?` | 显示本帮助 |

## 功能

- **研究分析**：输入 ETF 代码，运行多 agent 分析，实时查看进度和报告。
- **研究报告库**：浏览历史分析报告，按 ticker/日期/章节切换。
- **回测**：查看已有回测结果，包括 NAV 走势和关键指标。
- **模拟交易**：查看模拟账户持仓和交易历史。
"""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Markdown(self.HELP_TEXT)
        yield Footer()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class ETFAgentsTuiApp(App):
    CSS = """
    #home { align: center middle; height: 100%; }
    #title { text-style: bold; margin: 1 0; }
    .subtitle { color: $text-muted; margin-bottom: 1; }
    .screen-body { height: 1fr; }
    .pane-title { text-style: bold; color: $accent; height: 1; margin: 0 0 1 0; }
    .hint { color: $text-muted; height: 1; margin-top: 1; }
    .fill-list { height: 1fr; }
    ListView { width: 100%; }
    Markdown { height: 1fr; }
    DataTable { height: 1fr; }

    /* Two-pane layout */
    .left-pane  { height: 100%; width: 35%; min-width: 36; border: solid $primary; padding: 0 1; }
    .right-pane { height: 100%; width: 65%; padding: 0 1; }
    .right-top    { height: 35%; border: solid $primary; margin-bottom: 1; }
    .right-bottom { height: 1fr; border: solid $primary; }
    """

    BINDINGS = [
        ("q", "quit", "退出"),
        ("escape", "pop_screen", "返回"),
        ("?", "show_help", "帮助"),
        ("r", "refresh_reports", "刷新"),
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        analysis_runner: Any | None = None,
        backtest_viewer: BacktestViewer | None = None,
        paper_view_model: PaperTradingViewModel | None = None,
    ):
        super().__init__()
        self.report_repository = repository or ReportRepository()
        self.analysis_runner = analysis_runner
        self.backtest_viewer = backtest_viewer
        self.paper_view_model = paper_view_model

    def on_mount(self) -> None:
        self.install_screen(HomeScreen(), name="home")
        self.install_screen(
            ResearchAnalysisScreen(
                runner=self.analysis_runner,
                repository=self.report_repository,
            ),
            name="research",
        )
        self.install_screen(
            ReportLibraryScreen(repository=self.report_repository),
            name="reports",
        )
        self.install_screen(BacktestScreen(), name="backtest")
        self.install_screen(
            PaperTradingScreen(view_model=self.paper_view_model),
            name="paper",
        )
        self.install_screen(HelpScreen(), name="help")
        self.push_screen("home")

    def action_show_help(self) -> None:
        self.push_screen("help")

    async def action_refresh_reports(self) -> None:
        screen = self.screen
        if hasattr(screen, "action_refresh_reports"):
            result = screen.action_refresh_reports()
            if result is not None:
                await result


def main() -> None:
    app = ETFAgentsTuiApp()
    app.run()
