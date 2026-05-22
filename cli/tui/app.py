"""Textual application for ETFAgents."""

from __future__ import annotations

import datetime as _dt

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, ListItem, ListView, Markdown, Static

from cli.tui.services import (
    ANALYST_KEYS,
    AnalysisEvent,
    AnalysisRunner,
    BacktestRunner,
    PaperTradingViewModel,
    ReportRecord,
    ReportRepository,
    SECTION_DEFINITIONS,
)


def _safe_widget_id(prefix: str, value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in value)
    if not safe or safe[0].isdigit():
        safe = f"{prefix}_{safe}"
    return safe


class HomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="home"):
            yield Static("ETFAgents TUI", id="title")
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


class ResearchAnalysisScreen(Screen):
    def __init__(self, runner: AnalysisRunner | None = None):
        super().__init__()
        self.runner = runner or AnalysisRunner()
        self.events: dict[tuple[str, str], str] = {}
        self.selected_ticker = ""
        self.selected_section = "market_flow_report"
        self.status: dict[str, str] = {}
        self.queue_ids: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            with Horizontal(classes="toolbar"):
                yield Input(placeholder="ETF 代码，逗号分隔，例如 510300.SH,159915.SZ", id="tickers")
                yield Input(value=_dt.date.today().isoformat(), placeholder="YYYY-MM-DD", id="analysis_date")
                yield Button("开始分析", id="start", variant="primary")
            with Horizontal():
                yield ListView(id="queue")
                with Vertical():
                    yield ListView(id="sections")
                    yield Markdown("选择 ETF 和报告 section 后查看正文。", id="body")
        yield Footer()

    def on_mount(self) -> None:
        sections = self.query_one("#sections", ListView)
        for definition in SECTION_DEFINITIONS:
            sections.append(ListItem(Label(f"{definition.team} / {definition.title}"), id=definition.key))

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
        self.status = {ticker: "等待" for ticker in tickers}
        self.queue_ids = {}
        for ticker in tickers:
            item_id = _safe_widget_id("ticker", ticker)
            self.queue_ids[item_id] = ticker
            queue.append(ListItem(Label(f"{ticker}  等待  0/0"), id=item_id))
        self.selected_ticker = tickers[0]
        self.run_worker(lambda: self._run_analysis(tickers, date), exclusive=True, thread=True)

    def _run_analysis(self, tickers: list[str], date: str) -> None:
        for event in self.runner.run_queue(tickers, date, ANALYST_KEYS):
            self.call_from_thread(self._apply_event, event)

    def _apply_event(self, event: AnalysisEvent) -> None:
        if event.status:
            self.status[event.ticker] = event.status
        if event.section and event.content is not None:
            self.events[(event.ticker, event.section)] = event.content
            self.selected_ticker = self.selected_ticker or event.ticker
            self.selected_section = event.section
            self._refresh_body()
        self._refresh_queue(event)
        if event.error:
            self.query_one("#body", Markdown).update(f"分析失败：{event.error}")

    def _refresh_queue(self, event: AnalysisEvent) -> None:
        queue = self.query_one("#queue", ListView)
        queue.clear()
        tickers = list(self.status.keys())
        for ticker in tickers:
            done = event.completed_sections if ticker == event.ticker and event.completed_sections is not None else 0
            total = event.total_sections if ticker == event.ticker and event.total_sections is not None else 0
            item_id = _safe_widget_id("ticker", ticker)
            self.queue_ids[item_id] = ticker
            queue.append(ListItem(Label(f"{ticker}  {self.status[ticker]}  {done}/{total}"), id=item_id))

    def _refresh_body(self) -> None:
        content = self.events.get((self.selected_ticker, self.selected_section))
        if not content:
            content = f"{self.selected_ticker} / {self.selected_section} 尚未生成。"
        self.query_one("#body", Markdown).update(content)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id in self.queue_ids:
            self.selected_ticker = self.queue_ids[item_id]
        else:
            self.selected_section = item_id
        self._refresh_body()


class ReportLibraryScreen(Screen):
    def __init__(self, repository: ReportRepository | None = None):
        super().__init__()
        self.repository = repository or ReportRepository()
        self.records: list[ReportRecord] = []
        self.current: ReportRecord | None = None
        self.current_section = "final_allocation_decision"
        self.report_ids: dict[str, tuple[str, str]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield ListView(id="reports")
            with Vertical():
                yield ListView(id="library_sections")
                yield Markdown("暂无报告。", id="report_body")
        yield Footer()

    def on_mount(self) -> None:
        self.records = self.repository.list_reports()
        reports = self.query_one("#reports", ListView)
        self.report_ids = {}
        for index, record in enumerate(self.records):
            rating = f"  {record.rating}" if record.rating else ""
            item_id = _safe_widget_id("report", f"report_{index}_{record.ticker}_{record.date}")
            self.report_ids[item_id] = (record.ticker, record.date)
            reports.append(ListItem(Label(f"{record.ticker}  {record.date}{rating}"), id=item_id))
        sections = self.query_one("#library_sections", ListView)
        for definition in SECTION_DEFINITIONS:
            sections.append(ListItem(Label(f"{definition.team} / {definition.title}"), id=definition.key))
        if self.records:
            self.current = self.records[0]
            self._refresh_body()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id in self.report_ids:
            ticker, date = self.report_ids[item_id]
            self.current = next((record for record in self.records if record.ticker == ticker and record.date == date), None)
        else:
            self.current_section = item_id
        self._refresh_body()

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
        self.ticker_ids: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            with Horizontal(classes="toolbar"):
                yield ListView(id="backtest_tickers")
                with Vertical():
                    yield Input(placeholder="start_date YYYY-MM-DD", id="start_date")
                    yield Input(placeholder="end_date YYYY-MM-DD", id="end_date")
                    yield Input(value="20", placeholder="rebalance_interval_days", id="rebalance")
                    yield Input(value="1", placeholder="top_k", id="top_k")
                    yield Button("运行回测", id="run_backtest", variant="primary")
            yield Markdown("选择已有报告 ETF 后运行回测。", id="backtest_summary")
            yield DataTable(id="backtest_table")
        yield Footer()

    def on_mount(self) -> None:
        tickers = self.query_one("#backtest_tickers", ListView)
        self.ticker_ids = {}
        for record in self.repository.latest_by_ticker():
            item_id = _safe_widget_id("ticker", record.ticker)
            self.ticker_ids[item_id] = record.ticker
            tickers.append(ListItem(Label(f"{record.ticker}  {record.date}"), id=item_id))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self.selected_ticker = self.ticker_ids.get(event.item.id or "", "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "run_backtest" or not self.selected_ticker:
            return
        start = self.query_one("#start_date", Input).value.strip()
        end = self.query_one("#end_date", Input).value.strip()
        rebalance = int(self.query_one("#rebalance", Input).value.strip() or "20")
        top_k = int(self.query_one("#top_k", Input).value.strip() or "1")
        self.run_worker(lambda: self._run_backtest(start, end, rebalance, top_k), exclusive=True, thread=True)

    def _run_backtest(self, start: str, end: str, rebalance: int, top_k: int) -> None:
        model = self.runner.run([self.selected_ticker], start, end, rebalance_interval_days=rebalance, top_k=top_k)
        self.call_from_thread(self._show_backtest, model.summary, model.sparkline, model.metrics, model.orders, model.trades)

    def _show_backtest(self, summary: str, sparkline: str, metrics: dict, orders: list[dict], trades: list[dict]) -> None:
        self.query_one("#backtest_summary", Markdown).update(f"## NAV\n\n{sparkline}\n\n{summary}")
        table = self.query_one("#backtest_table", DataTable)
        table.clear(columns=True)
        table.add_columns("类型", "数量")
        table.add_row("指标组", str(len(metrics)))
        table.add_row("订单", str(len(orders)))
        table.add_row("成交", str(len(trades)))


class PaperTradingScreen(Screen):
    def __init__(self, view_model: PaperTradingViewModel | None = None):
        super().__init__()
        self.view_model = view_model or PaperTradingViewModel()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Button("刷新", id="refresh_paper", variant="primary")
            yield Markdown("模拟账户", id="paper_account")
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
                str(position.get("unrealized_pnl", "")),
            )


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
    .toolbar {
        height: auto;
    }
    ListView {
        width: 34;
        border: solid $primary;
    }
    Markdown {
        border: solid $primary;
        height: 1fr;
    }
    DataTable {
        height: 1fr;
    }
    """
    BINDINGS = [("q", "quit", "退出"), ("escape", "pop_screen", "返回")]

    def on_mount(self) -> None:
        self.install_screen(HomeScreen(), name="home")
        self.install_screen(ResearchAnalysisScreen(), name="research")
        self.install_screen(ReportLibraryScreen(), name="reports")
        self.install_screen(BacktestScreen(), name="backtest")
        self.install_screen(PaperTradingScreen(), name="paper")
        self.push_screen("home")

    def action_pop_screen(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()
