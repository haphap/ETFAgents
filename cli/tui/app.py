"""Textual application for ETFAgents."""

from __future__ import annotations

import datetime as _dt
import inspect

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, ListItem, ListView, Markdown, Static

from cli.tui.services import (
    ANALYST_KEYS,
    AnalysisEvent,
    AnalysisRunner,
    BacktestRunner,
    IdRegistry,
    PaperTradingViewModel,
    ReportRecord,
    ReportRepository,
    SECTION_DEFINITIONS,
    TickerState,
)


class HomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="home"):
            yield Static("ETFAgents TUI", id="title")
            yield Static(
                "研究分析 · 研究报告库 · 回测 · 模拟交易",
                classes="subtitle",
            )
            yield Button("研究分析", id="research", variant="primary")
            yield Button("研究报告库", id="reports")
            yield Button("回测", id="backtest")
            yield Button("模拟交易", id="paper")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        targets = {
            "research": "research",
            "reports": "reports",
            "backtest": "backtest",
            "paper": "paper",
        }
        screen = targets.get(event.button.id or "")
        if screen:
            self.app.push_screen(screen)


class HelpScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Markdown(
            "\n".join(
                [
                    "# ETFAgents TUI 快捷键",
                    "",
                    "- `q`: 退出 TUI",
                    "- `Escape`: 返回上一层",
                    "- `?`: 显示帮助",
                    "- `Tab` / `Shift+Tab`: 切换焦点",
                    "- `PgUp` / `PgDn` / `Home` / `End`: 滚动长内容",
                    "",
                    "TUI 与 `etfagents analyze`、`etfagents backtest`、`etfagents paper` 并存，不替换现有 CLI 命令。",
                ]
            )
        )
        yield Footer()


class ResearchAnalysisScreen(Screen):
    def __init__(self, runner: AnalysisRunner | None = None, repository: ReportRepository | None = None):
        super().__init__()
        self.runner = runner or AnalysisRunner()
        self.repository = repository
        self.events: dict[tuple[str, str], str] = {}
        self.selected_ticker = ""
        self.selected_section = "analyst.market_flow"
        self.states: dict[str, TickerState] = {}
        self.section_states: dict[str, dict[str, TickerState]] = {}
        self.progress: dict[str, tuple[int, int]] = {}
        self.queue_ids = IdRegistry("ticker")
        self.section_ids = IdRegistry("section")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("ETF 队列", classes="pane-title")
                yield ListView(id="queue", classes="fill-list")
                yield Static("分析配置", classes="pane-title")
                yield Input(placeholder="ETF 代码，逗号分隔，例如 510300.SH,159915.SZ", id="tickers")
                yield Input(value=_dt.date.today().isoformat(), placeholder="YYYY-MM-DD", id="analysis_date")
                yield Button("开始分析", id="start", variant="primary")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("报告章节", classes="pane-title")
                    yield ListView(id="sections", classes="section-list")
                with Vertical(classes="right-bottom"):
                    yield Static("报告正文", classes="pane-title")
                    yield Markdown("选择 ETF 和报告 section 后查看正文。", id="body")
        yield Footer()

    def on_mount(self) -> None:
        sections = self.query_one("#sections", ListView)
        self.section_ids.clear()
        for definition in SECTION_DEFINITIONS:
            sections.append(ListItem(Label(f"{definition.team} / {definition.title}"), id=self.section_ids.register(definition.key)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "start":
            return
        raw = self.query_one("#tickers", Input).value
        tickers = [ticker.strip().upper() for ticker in raw.replace("\n", ",").split(",") if ticker.strip()]
        if not tickers:
            self.query_one("#body", Markdown).update("请先输入至少一个 ETF 代码。")
            return
        date = self.query_one("#analysis_date", Input).value.strip() or _dt.date.today().isoformat()
        queue = self.query_one("#queue", ListView)
        queue.clear()
        self.states = {ticker: TickerState.PENDING for ticker in tickers}
        self.progress = {ticker: (0, 0) for ticker in tickers}
        self.queue_ids.clear()
        for ticker in tickers:
            item_id = self.queue_ids.register(ticker)
            queue.append(ListItem(Label(f"{ticker}  等待  0/0"), id=item_id))
        self.selected_ticker = tickers[0]
        self.run_worker(lambda: self._run_analysis(tickers, date), exclusive=True, thread=True)

    def _run_analysis(self, tickers: list[str], date: str) -> None:
        for event in self.runner.run_queue(tickers, date, ANALYST_KEYS):
            self.app.call_from_thread(self._apply_event, event)

    def _apply_event(self, event: AnalysisEvent) -> None:
        if event.states:
            self.states = event.states
        if event.section_states:
            self.section_states = event.section_states
        elif event.status:
            self.states[event.ticker] = event.status
        if event.completed_sections is not None and event.total_sections is not None:
            self.progress[event.ticker] = (event.completed_sections, event.total_sections)
        if event.section and event.content is not None:
            self.events[(event.ticker, event.section)] = event.content
            self.selected_ticker = self.selected_ticker or event.ticker
            self.selected_section = event.section
            self._refresh_body()
        if event.event_type == "report_persisted" and self.repository is not None:
            self.repository.invalidate()
        self._refresh_queue(event)
        self._refresh_sections()
        if event.error:
            self.query_one("#body", Markdown).update(f"分析失败：{event.error}")

    def _refresh_queue(self, event: AnalysisEvent) -> None:
        queue = self.query_one("#queue", ListView)
        tickers = list(self.states.keys())
        for ticker in tickers:
            done, total = self.progress.get(ticker, (0, 0))
            item_id = self.queue_ids.register(ticker)
            label_text = f"{ticker}  {self._state_label(self.states[ticker])}  {done}/{total}"
            try:
                queue.query_one(f"#{item_id}", ListItem).query_one(Label).update(label_text)
            except Exception:
                queue.append(ListItem(Label(label_text), id=item_id))

    def _refresh_body(self) -> None:
        content = self.events.get((self.selected_ticker, self.selected_section))
        if not content:
            content = f"{self.selected_ticker} / {self.selected_section} 尚未生成。"
        self.query_one("#body", Markdown).update(content)

    def _refresh_sections(self) -> None:
        states = self.section_states.get(self.selected_ticker, {})
        sections = self.query_one("#sections", ListView)
        for definition in SECTION_DEFINITIONS:
            item_id = self.section_ids.register(definition.key)
            label_text = (
                f"{self._section_marker(states.get(definition.key, TickerState.PENDING))} "
                f"{definition.team} / {definition.title}"
            )
            try:
                sections.query_one(f"#{item_id}", ListItem).query_one(Label).update(label_text)
            except Exception:
                pass

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id in self.queue_ids:
            self.selected_ticker = self.queue_ids.resolve(item_id)
        elif item_id in self.section_ids:
            self.selected_section = self.section_ids.resolve(item_id)
        else:
            self.selected_section = item_id
        self._refresh_sections()
        self._refresh_body()

    def _state_label(self, state: TickerState) -> str:
        return {
            TickerState.PENDING: "等待",
            TickerState.RUNNING: "分析中",
            TickerState.SECTION_RUNNING: "生成中",
            TickerState.SECTION_DONE: "已完成",
            TickerState.DONE: "完成",
            TickerState.FAILED: "失败",
            TickerState.CANCELLED: "已取消",
        }[state]

    def _section_marker(self, state: TickerState) -> str:
        return {
            TickerState.PENDING: "○",
            TickerState.RUNNING: "⏳",
            TickerState.SECTION_RUNNING: "⏳",
            TickerState.SECTION_DONE: "✓",
            TickerState.DONE: "✓",
            TickerState.FAILED: "✗",
            TickerState.CANCELLED: "–",
        }[state]


class ReportLibraryScreen(Screen):
    def __init__(self, repository: ReportRepository | None = None):
        super().__init__()
        self.repository = repository or ReportRepository()
        self.records: list[ReportRecord] = []
        self.current: ReportRecord | None = None
        self.current_section = "final.allocation_decision"
        self.report_ids = IdRegistry("report")
        self.report_lookup: dict[str, tuple[str, str]] = {}
        self.section_ids = IdRegistry("section")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("报告列表", classes="pane-title")
                yield ListView(id="reports", classes="fill-list")
                yield Static("按 r 刷新本地报告", classes="hint")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("报告章节", classes="pane-title")
                    yield ListView(id="library_sections", classes="section-list")
                with Vertical(classes="right-bottom"):
                    yield Static("Markdown 正文", classes="pane-title")
                    yield Markdown("暂无报告。", id="report_body")
        yield Footer()

    def on_mount(self) -> None:
        self._load_reports()

    def _load_reports(self) -> None:
        self.records = self.repository.list_reports()
        reports = self.query_one("#reports", ListView)
        self.report_ids.clear()
        self.report_lookup = {}
        for index, record in enumerate(self.records):
            rating = f"  {record.rating}" if record.rating else ""
            item_id = self.report_ids.register(f"report_{index}_{record.ticker}_{record.date}")
            self.report_lookup[item_id] = (record.ticker, record.date)
            reports.append(ListItem(Label(f"{record.ticker}  {record.date}{rating}"), id=item_id))
        sections = self.query_one("#library_sections", ListView)
        if not sections.children:
            self.section_ids.clear()
            for definition in SECTION_DEFINITIONS:
                sections.append(ListItem(Label(f"{definition.team} / {definition.title}"), id=self.section_ids.register(definition.key)))
        if self.records:
            self.current = self.records[0]
            self._refresh_body()
        else:
            self.current = None
            self.query_one("#report_body", Markdown).update("暂无报告。")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id in self.report_ids:
            ticker, date = self.report_lookup[item_id]
            self.current = next((record for record in self.records if record.ticker == ticker and record.date == date), None)
        elif item_id in self.section_ids:
            self.current_section = self.section_ids.resolve(item_id)
        else:
            self.current_section = item_id
        self._refresh_body()

    async def action_refresh_reports(self) -> None:
        self.repository.invalidate()
        await self.query_one("#reports", ListView).clear()
        self._load_reports()

    def _refresh_body(self) -> None:
        if self.current is None:
            return
        self.query_one("#report_body", Markdown).update(
            self.repository.read_section(self.current, self.current_section) or "该 section 暂无内容。"
        )


class BacktestScreen(Screen):
    def __init__(self, repository: ReportRepository | None = None, runner: BacktestRunner | None = None):
        super().__init__()
        self.repository = repository or ReportRepository()
        self.runner = runner or BacktestRunner()
        self.selected_ticker = ""
        self.ticker_ids = IdRegistry("ticker")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("ETF Selection", classes="pane-title")
                yield ListView(id="backtest_tickers", classes="fill-list")
                yield Static("Parameters", classes="pane-title")
                yield Input(placeholder="start_date YYYY-MM-DD", id="start_date")
                yield Input(placeholder="end_date YYYY-MM-DD", id="end_date")
                yield Input(value="20", placeholder="rebalance_interval_days", id="rebalance")
                yield Input(value="1", placeholder="top_k", id="top_k")
                yield Button("运行回测", id="run_backtest", variant="primary")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("NAV / Summary", classes="pane-title")
                    yield Markdown("选择已有报告 ETF 后运行回测。", id="backtest_summary")
                with Vertical(classes="right-bottom"):
                    yield Static("Results", classes="pane-title")
                    yield DataTable(id="backtest_table")
        yield Footer()

    def on_mount(self) -> None:
        tickers = self.query_one("#backtest_tickers", ListView)
        self.ticker_ids.clear()
        for record in self.repository.latest_by_ticker():
            item_id = self.ticker_ids.register(record.ticker)
            tickers.append(ListItem(Label(f"{record.ticker}  {record.date}"), id=item_id))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        self.selected_ticker = self.ticker_ids.resolve(item_id) if item_id in self.ticker_ids else ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "run_backtest" or not self.selected_ticker:
            return
        start = self.query_one("#start_date", Input).value.strip()
        end = self.query_one("#end_date", Input).value.strip()
        try:
            rebalance = int(self.query_one("#rebalance", Input).value.strip() or "20")
            top_k = int(self.query_one("#top_k", Input).value.strip() or "1")
        except ValueError:
            self.query_one("#backtest_summary", Markdown).update("回测参数必须是整数。")
            return
        self.run_worker(lambda: self._run_backtest(start, end, rebalance, top_k), exclusive=True, thread=True)

    def _run_backtest(self, start: str, end: str, rebalance: int, top_k: int) -> None:
        model = self.runner.run([self.selected_ticker], start, end, rebalance_interval_days=rebalance, top_k=top_k)
        self.app.call_from_thread(self._show_backtest, model.summary, model.sparkline, model.metrics, model.orders, model.trades)

    def _show_backtest(self, summary: str | None, sparkline: str, metrics: dict | None, orders: list[dict] | None, trades: list[dict] | None) -> None:
        self.query_one("#backtest_summary", Markdown).update(f"## NAV\n\n{sparkline or 'N/A'}\n\n{summary or 'N/A'}")
        table = self.query_one("#backtest_table", DataTable)
        table.clear(columns=True)
        table.add_columns("类型", "数量")
        table.add_row("指标组", str(len(metrics)) if metrics is not None else "N/A")
        table.add_row("订单", str(len(orders)) if orders is not None else "N/A")
        table.add_row("成交", str(len(trades)) if trades is not None else "N/A")


class PaperTradingScreen(Screen):
    def __init__(self, view_model: PaperTradingViewModel | None = None):
        super().__init__()
        self.view_model = view_model or PaperTradingViewModel()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("账户总览", classes="pane-title")
                yield Button("刷新", id="refresh_paper", variant="primary")
                yield Markdown("模拟账户", id="paper_account")
            with Vertical(classes="right-pane"):
                yield Static("持仓", classes="pane-title")
                yield DataTable(id="paper_table")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh_paper":
            self._refresh()

    def _refresh(self) -> None:
        snapshot = self.view_model.snapshot()
        account = snapshot.account
        self.query_one("#paper_account", Markdown).update(
            "\n".join(
                [
                    f"现金: {account.get('cash', 0):,.2f}",
                    f"持仓市值: {account.get('market_value', 0):,.2f}",
                    f"账户净值: {account.get('total_assets', 0):,.2f}",
                    f"未实现盈亏: {account.get('unrealized_pnl', 0):,.2f}",
                ]
            )
        )
        table = self.query_one("#paper_table", DataTable)
        table.clear(columns=True)
        table.add_columns("Ticker", "数量", "成本", "现价", "盈亏")
        for position in snapshot.positions:
            table.add_row(
                str(position.get("ticker", "")),
                str(position.get("quantity", "")),
                str(position.get("avg_cost", "")),
                str(position.get("current_price", "")),
                self._pnl_text(position.get("unrealized_pnl")),
            )

    def _pnl_text(self, value: object) -> Text:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return Text("N/A", style="dim")
        style = "green" if number >= 0 else "red"
        return Text(f"{number:,.2f}", style=style)


class ETFAgentsTuiApp(App):
    CSS = """
    #home {
        align: center middle;
        height: 100%;
    }
    #title {
        text-style: bold;
        margin: 1 0;
    }
    .subtitle {
        color: $text-muted;
        margin-bottom: 1;
    }
    .screen-body {
        height: 1fr;
    }
    .left-pane {
        width: 30%;
        min-width: 30;
        height: 100%;
        padding: 0 1;
        border: solid $primary;
    }
    .right-pane {
        width: 70%;
        height: 100%;
        padding: 0 1;
    }
    .right-top {
        height: 35%;
        border: solid $primary;
        margin-bottom: 1;
    }
    .right-bottom {
        height: 1fr;
        border: solid $primary;
    }
    .pane-title {
        text-style: bold;
        color: $accent;
        height: 1;
        margin: 0 0 1 0;
    }
    .hint {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    .fill-list {
        height: 1fr;
    }
    .section-list {
        height: 1fr;
    }
    #tickers {
        width: 100%;
    }
    #analysis_date {
        width: 100%;
    }
    ListView {
        width: 100%;
    }
    Markdown {
        height: 1fr;
    }
    DataTable {
        height: 1fr;
    }
    """
    BINDINGS = [
        ("q", "quit", "退出"),
        ("escape", "pop_screen", "返回"),
        ("?", "show_help", "帮助"),
        ("r", "refresh_reports", "刷新报告"),
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        analysis_runner: AnalysisRunner | None = None,
        backtest_runner: BacktestRunner | None = None,
        paper_view_model: PaperTradingViewModel | None = None,
    ):
        super().__init__()
        self.report_repository = repository or ReportRepository()
        self.analysis_runner = analysis_runner
        self.backtest_runner = backtest_runner
        self.paper_view_model = paper_view_model

    def on_mount(self) -> None:
        self.install_screen(HomeScreen(), name="home")
        self.install_screen(ResearchAnalysisScreen(runner=self.analysis_runner, repository=self.report_repository), name="research")
        self.install_screen(ReportLibraryScreen(repository=self.report_repository), name="reports")
        self.install_screen(BacktestScreen(repository=self.report_repository, runner=self.backtest_runner), name="backtest")
        self.install_screen(PaperTradingScreen(view_model=self.paper_view_model), name="paper")
        self.install_screen(HelpScreen(), name="help")
        self.push_screen("home")

    def action_pop_screen(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def action_show_help(self) -> None:
        self.push_screen("help")

    async def action_refresh_reports(self) -> None:
        screen = self.screen
        if hasattr(screen, "action_refresh_reports"):
            result = screen.action_refresh_reports()
            if inspect.isawaitable(result):
                await result
