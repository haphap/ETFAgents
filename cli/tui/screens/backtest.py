"""Backtest viewer and runner screen."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
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
    BacktestEvent,
    BacktestFailed,
    BacktestFinished,
    BacktestRecord,
    BacktestRunner,
    BacktestStarted,
    BacktestViewer,
    BacktestViewModel,
)
from cli.tui.screens.research import _safe_call_from_thread


class BacktestScreen(Screen):
    """View existing backtest results and run new backtests.

    Left pane: list of runs + refresh button + run inputs.
    Right-top: metrics table + sparkline.
    Right-bottom: summary markdown.
    """

    def __init__(self, viewer: BacktestViewer | None = None, runner: BacktestRunner | None = None) -> None:
        super().__init__()
        self._viewer = viewer
        self._runner = runner
        self.records: list[BacktestRecord] = []
        self.current: BacktestRecord | None = None
        self._load_count = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("回测结果", classes="pane-title")
                yield ListView(id="bt_list")
                yield Button("刷新", id="btn_bt_refresh", variant="primary")
                yield Static("运行新回测", classes="pane-title")
                yield Input(placeholder="ETF代码（逗号分隔）", id="bt_run_tickers")
                yield Input(placeholder="开始日期 (YYYY-MM-DD)", id="bt_run_start")
                yield Input(placeholder="结束日期 (YYYY-MM-DD)", id="bt_run_end")
                yield Button("运行回测", id="btn_bt_run", variant="success")
                yield Static("", id="bt_run_status")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("NAV走势", classes="pane-title")
                    yield Static("", id="bt_sparkline")
                    yield DataTable(id="bt_metrics")
                with Vertical(classes="right-bottom"):
                    yield Static("摘要", classes="pane-title")
                    yield Markdown(id="bt_summary")
        yield Footer()

    def on_mount(self) -> None:
        self._start_loading()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_bt_refresh":
            self._start_loading()
        elif event.button.id == "btn_bt_run":
            self._start_backtest()

    async def action_refresh_reports(self) -> None:
        self._start_loading()

    def _start_backtest(self) -> None:
        tickers_str = self.query_one("#bt_run_tickers", Input).value.strip()
        start = self.query_one("#bt_run_start", Input).value.strip()
        end = self.query_one("#bt_run_end", Input).value.strip()
        if not tickers_str or not start or not end:
            self.query_one("#bt_run_status", Static).update("请填写所有字段")
            return
        tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
        self.query_one("#bt_run_status", Static).update("回测运行中...")
        self.query_one("#btn_bt_run", Button).disabled = True
        runner = self._runner or BacktestRunner()
        threading.Thread(
            target=self._run_backtest,
            args=(runner, tickers, start, end),
            daemon=True,
            name="etfagents-tui-backtest",
        ).start()

    def _run_backtest(self, runner: BacktestRunner, tickers: list[str], start: str, end: str) -> None:
        for event in runner.run(tickers, start, end):
            _safe_call_from_thread(self, self._apply_backtest_event, event)

    def _apply_backtest_event(self, event: BacktestEvent) -> None:
        status = self.query_one("#bt_run_status", Static)
        if isinstance(event, BacktestStarted):
            status.update(f"回测中: {','.join(event.tickers)} {event.start_date}~{event.end_date}")
        elif isinstance(event, BacktestFinished):
            status.update(f"回测完成: {event.output_dir.name}")
            self.query_one("#btn_bt_run", Button).disabled = False
            self._start_loading()
        elif isinstance(event, BacktestFailed):
            status.update(f"回测失败: {event.error}")
            self.query_one("#btn_bt_run", Button).disabled = False

    def _start_loading(self) -> None:
        self.query_one("#bt_sparkline", Static).update("加载中...")
        self.run_worker(self._fetch_records, thread=True, exclusive=True)

    def _fetch_records(self) -> None:
        try:
            viewer = self._viewer or BacktestViewer()
            records = viewer.list_results()
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))
            return
        _safe_call_from_thread(self, self._apply_records, records)

    def _apply_records(self, records: list[BacktestRecord]) -> None:
        self.records = records
        bt_list = self.query_one("#bt_list", ListView)
        self._load_count += 1

        for item in list(bt_list.children):
            item.remove()

        if not records:
            self.query_one("#bt_sparkline", Static).update("暂无回测结果")
            self.query_one("#bt_metrics", DataTable).clear(columns=True)
            self.query_one("#bt_summary", Markdown).update("")
            return

        for i, record in enumerate(records):
            tickers_str = ",".join(record.tickers[:2]) + ("…" if len(record.tickers) > 2 else "")
            ret_str = ""
            if record.cumulative_return is not None:
                ret_str = f" {record.cumulative_return:+.1%}"
            label_text = f"{tickers_str} {record.start_date}~{record.end_date}{ret_str}"
            bt_list.append(ListItem(
                Label(label_text),
                id=f"btr_{self._load_count}_{i}",
            ))

        self._show_record(records[0])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id and event.item.id.startswith("btr_"):
            try:
                parts = event.item.id[4:].split("_")
                if len(parts) >= 2:
                    idx = int(parts[-1])
                    if 0 <= idx < len(self.records):
                        self._show_record(self.records[idx])
            except (ValueError, IndexError):
                pass

    def _show_record(self, record: BacktestRecord) -> None:
        self.current = record
        self.run_worker(
            lambda: self._fetch_detail(record.output_dir),
            thread=True,
            exclusive=True,
        )

    def _fetch_detail(self, output_dir: Path) -> None:
        try:
            viewer = self._viewer or BacktestViewer()
            vm = viewer.load(output_dir)
            _safe_call_from_thread(self, self._apply_detail, vm)
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))

    def _apply_detail(self, vm: BacktestViewModel) -> None:
        if self.current is None or vm.output_dir != self.current.output_dir:
            return

        sparkline_text = vm.sparkline or "─"
        self.query_one("#bt_sparkline", Static).update(f"[{sparkline_text}]")

        metrics_table = self.query_one("#bt_metrics", DataTable)
        metrics_table.clear(columns=True)
        metrics_table.add_columns("指标", "值")

        if vm.metrics and "metrics" in vm.metrics:
            m = vm.metrics["metrics"]
            metrics_to_show = [
                ("累计收益", "cumulative_return"),
                ("年化收益", "annualized_return"),
                ("年化波动", "annualized_volatility"),
                ("最大回撤", "max_drawdown"),
                ("Sharpe比率", "sharpe_ratio"),
                ("总交易数", "total_trades"),
            ]
            for label, key in metrics_to_show:
                val = m.get(key)
                if val is not None:
                    if isinstance(val, float) and key in ["cumulative_return", "annualized_return", "max_drawdown"]:
                        val_str = f"{val:+.1%}"
                    elif isinstance(val, float) and key == "annualized_volatility":
                        val_str = f"{val:.1%}"
                    elif isinstance(val, float):
                        val_str = f"{val:.2f}"
                    else:
                        val_str = str(val)
                    metrics_table.add_row(label, val_str)

        summary_md = vm.summary or "无摘要"
        self.query_one("#bt_summary", Markdown).update(summary_md)

    def _show_error(self, error: str) -> None:
        self.query_one("#bt_sparkline", Static).update(f"加载失败：{error}")
