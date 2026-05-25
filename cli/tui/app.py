"""Textual application for ETFAgents TUI.

Screen and modal implementations live in ``cli.tui.screens``.
This module defines only the top-level ``ETFAgentsTuiApp`` and the ``main``
entry-point.  All screen/modal classes are re-exported here for backward
compatibility so that ``from cli.tui.app import HomeScreen`` continues to work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App

from cli.tui.services import (
    BacktestViewer,
    ReportRepository,
    TuiSettings,
)

# Re-export all screens/modals so existing imports keep working.
from cli.tui.screens import (  # noqa: F401
    AnalysisConfigModal,
    AnalysisRunScreen,
    BacktestScreen,
    HelpScreen,
    HomeScreen,
    LLM_PROVIDER_OPTIONS,
    LoginModal,
    OrderModal,
    PaperTradingScreen,
    ReportLibraryScreen,
    ResearchAnalysisScreen,
    SettingsScreen,
    _apply_pane_settings,
    _build_analysis_runner,
    _safe_call_from_thread,
)
from cli.tui.services import PaperTradingViewModel  # noqa: F401


class ETFAgentsTuiApp(App):
    CSS = """
    /* ── Base ─────────────────────────────────────────────── */
    Screen {
        background: transparent;
        color: $text;
    }

    .screen-body,
    .screen-body Vertical,
    .screen-body Horizontal,
    .run-layout,
    .run-layout Vertical,
    .run-layout Horizontal,
    .run-layout ScrollableContainer {
        background: transparent;
    }

    Header {
        background: transparent;
        color: $text;
        border-bottom: solid $panel;
        height: 1;
        text-style: bold;
    }

    Footer {
        height: 1;
        text-style: bold;
        background: transparent;
        color: $text-muted;
    }

    .screen-body {
        height: 1fr;
        margin: 1;
    }

    .run-layout {
        height: 1fr;
    }

    .run-main {
        height: 1fr;
        margin-bottom: 0;
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

    Static {
        color: $text;
    }

    /* ── Form controls ───────────────────────────────────── */
    Input {
        background: $surface;
        color: $text;
        border: tall $panel;
        margin: 0 0 1 0;
    }

    Input:focus {
        border: tall $accent;
    }

    Select {
        background: $surface;
        color: $text;
        border: tall $panel;
        margin: 0 0 1 0;
    }

    Select:focus {
        border: tall $accent;
    }

    /* ── Buttons — minimal text actions ───────────────────── */
    Button {
        background: transparent;
        color: $text-muted;
        text-style: bold;
        border: none;
        min-width: 0;
        height: 1;
        margin: 0 0 1 0;
        padding: 0 1;
        content-align: left middle;
    }

    Button:hover {
        color: $accent;
        background: transparent;
        text-style: bold underline;
    }

    Button:focus {
        color: $accent;
        background: $panel;
    }

    Button.-primary {
        color: $accent;
        background: transparent;
    }

    Button.-warning {
        color: $warning;
        background: transparent;
    }

    Button.-success {
        color: $success;
        background: transparent;
    }

    Button:disabled {
        color: $text-disabled;
        background: transparent;
        text-style: none;
    }

    /* ── Text-action / nav-action button classes ─────────── */
    .text-action {
        background: transparent;
        color: $accent;
        min-width: 0;
        height: 1;
        padding: 0 1;
    }

    .text-action:hover {
        text-style: bold underline;
        background: transparent;
    }

    .nav-action {
        width: 100%;
        background: transparent;
        color: $text-muted;
        min-width: 0;
        height: 1;
        padding: 0 1;
        content-align: left middle;
    }

    .nav-action:hover {
        color: $accent;
        background: transparent;
    }

    .nav-action:focus {
        color: $accent;
        background: $panel;
    }

    /* ── Lists ────────────────────────────────────────────── */
    ListView {
        width: 100%;
        background: transparent;
    }

    ListItem {
        color: $text;
        height: 1;
    }

    ListView > ListItem.--highlight {
        background: $accent;
        color: $surface;
        text-style: bold;
    }

    /* ── Markdown ─────────────────────────────────────────── */
    Markdown {
        height: auto;
        background: transparent;
        color: $text;
    }

    /* ── DataTable ────────────────────────────────────────── */
    DataTable {
        height: 1fr;
        background: transparent;
        color: $text;
    }

    /* ── Panel layout ─────────────────────────────────────── */
    .left-pane {
        height: 100%;
        width: 20%;
        min-width: 22;
        border: solid $panel;
        padding: 1 1;
        background: transparent;
    }

    .right-pane {
        height: 100%;
        width: 80%;
        padding: 0 1;
        border: solid $panel;
        background: transparent;
    }

    .right-top {
        height: auto;
        max-height: 40%;
        border: none;
        padding: 0 1;
        margin-bottom: 1;
        background: transparent;
    }

    .right-bottom {
        height: 1fr;
        border: none;
        padding: 1 1;
        background: transparent;
    }

    /* Panel width presets */
    .panel-narrow .left-pane  { width: 15%; }
    .panel-narrow .right-pane { width: 85%; }
    .panel-normal .left-pane  { width: 20%; }
    .panel-normal .right-pane { width: 80%; }
    .panel-wide .left-pane    { width: 25%; }
    .panel-wide .right-pane   { width: 75%; }

    /* Density options */
    .density-compact .left-pane,  .density-compact .right-pane  { padding: 0 0; }
    .density-normal .left-pane,   .density-normal .right-pane   { padding: 0 1; }
    .density-spacious .left-pane, .density-spacious .right-pane { padding: 1 2; }

    /* ── Home: nav + dashboard ────────────────────────────── */
    /* ── Research entry: input + watchlist cards ──────────── */
    .research-entry-pane {
        width: 34%;
        min-width: 48;
        padding: 1 1;
    }

    .research-board-pane {
        width: 66%;
    }

    .input-label {
        height: 1;
        color: $text;
        text-style: bold;
        margin: 1 0 0 0;
    }

    .entry-help {
        height: 1;
        color: $text-muted;
        margin: 0 0 1 0;
    }

    .selected-tags {
        height: 3;
        margin: 0 0 1 0;
        border: solid $surface;
        padding: 0 1;
    }

    .selected-empty {
        height: 1;
        color: $text-muted;
        content-align: left middle;
    }

    .selected-chip {
        width: auto;
        height: 1;
        min-width: 10;
        margin: 0 1 0 0;
        padding: 0 1;
        border: none;
        background: $surface;
        color: $accent;
        content-align: center middle;
    }

    .selected-chip:hover,
    .selected-chip:focus {
        color: $surface;
        background: $accent;
        text-style: bold;
    }

    .selected-count {
        height: 1;
        color: $success;
        margin: 0 0 1 0;
    }

    .entry-actions {
        height: 3;
        margin: 1 0 1 0;
    }

    .entry-primary {
        width: 1fr;
        height: 3;
        margin: 0 1 0 0;
        background: $accent;
        color: $surface;
        text-style: bold;
        content-align: center middle;
    }

    .entry-primary:hover,
    .entry-primary:focus {
        background: $accent;
        color: $surface;
        text-style: bold underline;
    }

    .entry-primary:disabled {
        background: $surface;
        color: $text-disabled;
        text-style: none;
    }

    .entry-config {
        width: 1fr;
        height: 3;
        border: solid $panel;
        background: transparent;
        color: $text-muted;
        content-align: center middle;
    }

    .entry-config:hover,
    .entry-config:focus {
        border: solid $accent;
        color: $accent;
        background: transparent;
        text-style: bold;
    }

    .entry-section-title {
        height: 1;
        color: $accent;
        text-style: bold;
        margin: 1 0 1 0;
    }

    .recent-etf-grid {
        height: auto;
    }

    .recent-etf-row {
        height: 3;
        margin: 0 0 1 0;
    }

    .ticker-chip {
        width: 1fr;
        height: 3;
        min-width: 10;
        margin: 0 1 0 0;
        padding: 0;
        border: solid $panel;
        background: transparent;
        color: $text-muted;
        content-align: center middle;
    }

    .ticker-chip:hover,
    .ticker-chip:focus {
        border: solid $accent;
        color: $accent;
        background: transparent;
        text-style: bold;
    }

    .recent-task-list {
        height: auto;
        margin: 0 0 1 0;
        border: solid $surface;
        padding: 0 1;
    }

    .recent-task-item {
        height: 1;
        color: $text-muted;
    }

    .recent-task-empty {
        height: 1;
        color: $text-muted;
    }

    #watchlist_cards {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-background: transparent;
        scrollbar-color: $accent;
        overflow-x: hidden;
        overflow-y: auto;
    }

    .watchlist-status {
        height: auto;
        color: $text-muted;
        padding: 1 2;
    }

    .watchlist-card {
        width: 100%;
        height: auto;
        min-height: 10;
        margin: 0 0 1 0;
        padding: 1 2;
        border: solid $panel;
        background: transparent;
    }

    .watchlist-card-title {
        width: 100%;
        height: 1;
        min-width: 0;
        padding: 0;
        margin: 0;
        background: transparent;
        color: $text;
        text-style: bold;
        content-align: left middle;
    }

    .watchlist-card-title:hover,
    .watchlist-card-title:focus {
        color: $accent;
        background: transparent;
        text-style: bold underline;
    }

    .watchlist-card-name {
        height: 1;
        color: $text-muted;
        margin: 0 0 1 0;
    }

    .watchlist-card-price {
        height: 1;
        text-style: bold;
        margin: 0 0 1 0;
    }

    .watchlist-card-tags {
        height: auto;
        color: $text-muted;
        margin: 0 0 1 0;
    }

    .watchlist-card-action {
        height: auto;
        padding: 0 1;
        text-style: bold;
        margin: 0 0 1 0;
    }

    .watchlist-card-rationale {
        height: auto;
        color: $text-muted;
    }

    .a-share-up {
        color: $error;
    }

    .a-share-down {
        color: $success;
    }

    .action-risk {
        background: $success;
        color: $surface;
    }

    .action-opportunity {
        background: $error;
        color: $surface;
    }

    .action-neutral {
        background: $surface;
        color: $text;
    }

    /* ── Analysis run: board layout ───────────────────────── */
    #ra_run_config {
        color: $text-muted;
        height: auto;
        margin-bottom: 0;
        padding: 0 1;
        border: solid $surface;
    }

    #ra_etf_detail {
        color: $text;
        height: auto;
        margin-bottom: 1;
        padding: 0 1;
        border: solid $surface;
    }

    #ra_body_scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-background: transparent;
        scrollbar-color: $accent;
        overflow-x: auto;
        overflow-y: auto;
    }

    #lib_body_scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-background: transparent;
        scrollbar-color: $accent;
        overflow-x: auto;
        overflow-y: auto;
    }

    #ra_body {
        height: auto;
    }

    .stats-bar {
        height: 1;
        width: 100%;
        background: transparent;
    }

    .stats-bar > Static {
        width: 1fr;
        height: 1;
        padding: 0 1;
    }

    .stats-seg-accent {
        background: $accent;
        color: $surface;
        text-style: bold;
        content-align: left middle;
    }

    .stats-seg-panel {
        background: $panel;
        color: $text;
        content-align: center middle;
    }

    .stats-seg-success {
        background: $success;
        color: $surface;
        content-align: center middle;
    }

    .stats-seg-surface {
        background: $surface;
        color: $text-muted;
        content-align: center middle;
    }

    .board-column {
        height: 9;
        width: 1fr;
        padding: 0 1;
        border: solid $panel;
        margin-right: 1;
    }

    .board-column:last-of-type {
        margin-right: 0;
    }

    .column-active {
        border: solid $accent;
    }

    .column-inactive {
        border: solid $panel;
    }

    .column-header {
        text-style: bold;
        color: $text;
        height: 1;
        margin-bottom: 1;
        content-align: center middle;
    }

    .board-col-wide {
        width: 2fr;
    }

    .board-row {
        height: auto;
    }

    .board-item {
        width: 1fr;
        height: 1;
        min-width: 0;
        padding: 0;
        margin: 0;
        background: transparent;
        color: $text-muted;
        text-style: none;
        content-align: left middle;
    }

    .board-item:hover {
        color: $accent;
        background: transparent;
        text-style: none;
    }

    .board-item:focus {
        color: $accent;
        background: $panel;
        text-style: bold;
    }

    .board-item-done {
        color: $success;
    }

    .board-item-failed {
        color: $error;
    }

    .debate-progress {
        color: $text-muted;
        height: auto;
    }

    /* ── Semantic text classes ─────────────────────────────── */
    .muted {
        color: $text-muted;
    }

    .success-text {
        color: $success;
    }

    .warning-text {
        color: $warning;
    }

    .error-text {
        color: $error;
    }

    .status-strip {
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }

    .section-card {
        height: auto;
        border: solid $panel;
        padding: 1 2;
        margin: 0 0 1 0;
        background: transparent;
    }

    /* ── Placeholder panel ────────────────────────────────── */
    .placeholder-panel {
        height: auto;
        border: dashed $panel;
        padding: 1 2;
        color: $text-muted;
        content-align: center middle;
    }

    /* ── Config modal (layout in AnalysisConfigModal.DEFAULT_CSS) ── */
    """

    BINDINGS = [
        ("q", "quit", "退出"),
        ("escape", "pop_screen", "返回"),
        ("?", "show_help", "帮助"),
        ("r", "refresh_reports", "刷新"),
        ("s", "open_settings", "设置"),
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        analysis_runner: Any | None = None,
        backtest_viewer: BacktestViewer | None = None,
        paper_view_model: PaperTradingViewModel | None = None,
        settings_path: Path | None = None,
    ):
        super().__init__()
        self.report_repository = repository or ReportRepository()
        self.analysis_runner = analysis_runner
        self._backtest_viewer = backtest_viewer
        self.paper_view_model = paper_view_model
        self._settings_path = settings_path
        self._settings = TuiSettings.load(settings_path) if settings_path else TuiSettings.load()

    @property
    def backtest_viewer(self) -> BacktestViewer:
        """Lazily instantiate BacktestViewer if not injected."""
        if self._backtest_viewer is None:
            self._backtest_viewer = BacktestViewer()
        return self._backtest_viewer

    def on_mount(self) -> None:
        self.theme = self._settings.theme
        self._tui_settings = self._settings
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
        self.install_screen(
            BacktestScreen(viewer=self.backtest_viewer),
            name="backtest",
        )
        self.install_screen(
            PaperTradingScreen(view_model=self.paper_view_model),
            name="paper",
        )
        self.install_screen(SettingsScreen(settings_path=self._settings_path), name="settings")
        self.install_screen(HelpScreen(), name="help")
        self.push_screen("home")

    def on_screen_resume(self) -> None:
        """Apply layout settings when a screen becomes active."""
        _apply_pane_settings(self, self._tui_settings)

    def action_show_help(self) -> None:
        self.push_screen("help")

    def action_open_settings(self) -> None:
        self.push_screen("settings")

    def action_quit(self) -> None:
        self._cancel_active_operations()
        self.exit()

    def _cancel_active_operations(self) -> None:
        for screen in self.screen_stack:
            if isinstance(screen, AnalysisRunScreen):
                screen._cancel_analysis()
        current = self.screen
        if isinstance(current, AnalysisRunScreen):
            current._cancel_analysis()

    async def action_refresh_reports(self) -> None:
        screen = self.screen
        if hasattr(screen, "action_refresh_reports"):
            result = screen.action_refresh_reports()
            if result is not None:
                await result


def main() -> None:
    app = ETFAgentsTuiApp()
    app.run()
