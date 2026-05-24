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
    Screen {
        background: $surface;
        color: $text;
    }

    Header {
        background: $surface;
        color: $text;
        border: solid $panel;
        height: 3;
        text-style: bold;
    }

    Footer {
        height: 1;
        text-style: bold;
    }

    #title {
        color: $accent;
        text-style: bold;
        height: 1;
        margin: 0 0 1 0;
    }

    .subtitle {
        color: $text-muted;
        margin-bottom: 1;
        text-style: italic;
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

    Input {
        background: $background;
        color: $text;
        border: tall $accent;
        margin: 0 0 1 0;
    }

    Select {
        background: $background;
        color: $text;
        border: tall $panel;
        margin: 0 0 1 0;
    }

    Button {
        background: $panel;
        color: $text;
        text-style: bold;
        border: none;
        margin: 0 0 1 0;
    }

    Button:hover {
        background: $accent;
        color: $surface;
    }

    Button.-primary {
        background: $accent;
        color: $surface;
    }

    Button.-warning {
        background: $warning;
        color: $surface;
    }

    Button.-success {
        background: $success;
        color: $surface;
    }

    ListView {
        width: 100%;
        background: $surface;
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

    Markdown {
        height: auto;
        background: $surface;
        color: $text;
    }

    #ra_body_scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-background: $background;
        scrollbar-color: $accent;
    }

    #ra_body {
        height: auto;
    }

    #ra_stats_bar {
        height: 3;
        margin: 0 1 1 1;
        padding: 0 2;
        border: solid $panel;
        background: $background;
        color: $accent;
        text-style: bold;
    }

    DataTable {
        height: 1fr;
        background: $surface;
        color: $text;
    }

    .left-pane {
        height: 100%;
        width: 30%;
        min-width: 34;
        border: solid $accent;
        padding: 1 2;
        background: $surface;
    }

    .right-pane {
        height: 100%;
        width: 70%;
        padding: 0 1;
        border: solid $accent;
        background: $surface;
    }

    .right-top {
        height: 35%;
        border: solid $panel;
        padding: 1 2;
        margin-bottom: 1;
        background: $surface;
    }

    .right-bottom {
        height: 1fr;
        border: solid $panel;
        padding: 1 2;
        background: $surface;
    }

    /* Panel width presets */
    .panel-narrow .left-pane  { width: 30%; }
    .panel-narrow .right-pane { width: 70%; }
    .panel-normal .left-pane  { width: 35%; }
    .panel-normal .right-pane { width: 65%; }
    .panel-wide .left-pane    { width: 40%; }
    .panel-wide .right-pane   { width: 60%; }

    /* Density options */
    .density-compact .left-pane,  .density-compact .right-pane  { padding: 0 0; }
    .density-normal .left-pane,   .density-normal .right-pane   { padding: 0 1; }
    .density-spacious .left-pane, .density-spacious .right-pane { padding: 1 2; }

    .nav-pane {
        width: 22%;
        min-width: 28;
    }

    .dashboard-pane {
        width: 78%;
        padding: 1 3;
    }

    .nav-button {
        width: 100%;
        content-align: left middle;
        background: $surface;
        color: $text;
    }

    .nav-button:hover {
        background: $accent;
        color: $surface;
    }

    .dashboard-card {
        height: auto;
        border: solid $panel;
        padding: 1 2;
        margin: 1 0;
        background: $surface;
    }

    .ascii-logo {
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
        text-style: bold;
    }
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
