"""Report library screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Markdown, Static

from cli.tui.services import (
    ReportRecord,
    ReportRepository,
    SECTION_DEFINITIONS,
)


class ReportLibraryScreen(Screen):
    """Browse locally saved single-ETF reports.

    Left pane: report list (ticker + date + rating).
    Right-top: section list (fixed 9 + complete).
    Right-bottom: selected section Markdown body.
    """

    def __init__(self, repository: ReportRepository) -> None:
        super().__init__()
        self.repository = repository
        self.records: list[ReportRecord] = []
        self.current: ReportRecord | None = None
        self.current_section: str = "portfolio_manager"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("Report List", classes="pane-title")
                yield ListView(id="reports")
                yield Static("r Refresh", classes="hint")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("Sections", classes="pane-title")
                    yield ListView(id="lib_sections")
                with Vertical(classes="right-bottom"):
                    yield Static("Body", classes="pane-title")
                    with ScrollableContainer(id="lib_body_scroll"):
                        yield Markdown("", id="lib_body")
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
            self.current = None
            self.current_section = "portfolio_manager"
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
