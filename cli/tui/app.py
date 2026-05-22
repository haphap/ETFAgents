"""Textual application for ETFAgents — M0 skeleton."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
)

from cli.tui.services import (
    BacktestViewer,
    PaperTradingViewModel,
    ReportRepository,
    SECTION_DEFINITIONS,
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
# Placeholder screens (M0 — to be implemented in M1–M3)
# ---------------------------------------------------------------------------

class ResearchAnalysisScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="screen-body"):
            yield Static("研究分析（待实现）", classes="pane-title")
            yield Static("此功能将在后续版本中完成。", classes="hint")
        yield Footer()


class ReportLibraryScreen(Screen):
    def __init__(self, repository: ReportRepository) -> None:
        super().__init__()
        self.repository = repository

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="screen-body"):
            yield Static("研究报告库（待实现）", classes="pane-title")
            yield Static("此功能将在后续版本中完成。", classes="hint")
        yield Footer()


class BacktestScreen(Screen):
    def __init__(self, viewer: BacktestViewer) -> None:
        super().__init__()
        self.viewer = viewer

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="screen-body"):
            yield Static("回测（待实现）", classes="pane-title")
            yield Static("此功能将在后续版本中完成。", classes="hint")
        yield Footer()


class PaperTradingScreen(Screen):
    def __init__(self, view_model: PaperTradingViewModel) -> None:
        super().__init__()
        self.view_model = view_model

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="screen-body"):
            yield Static("模拟交易（待实现）", classes="pane-title")
            yield Static("此功能将在后续版本中完成。", classes="hint")
        yield Footer()


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
    /* === 基础布局 === */
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

    /* === 左侧面板宽度（通过 App CSS class 切换） === */
    .left-pane  { height: 100%; border: solid $primary; }
    .right-pane { height: 100%; }

    .panel-narrow .left-pane  { width: 30%; min-width: 30; }
    .panel-narrow .right-pane { width: 70%; }
    .panel-normal .left-pane  { width: 35%; min-width: 36; }
    .panel-normal .right-pane { width: 65%; }
    .panel-wide .left-pane    { width: 40%; min-width: 42; }
    .panel-wide .right-pane   { width: 60%; }

    /* === 布局密度（通过 App CSS class 切换） === */

    /* compact */
    .density-compact .left-pane  { padding: 0; }
    .density-compact .right-pane { padding: 0; }
    .density-compact .right-top  { height: 35%; border: round $primary; margin-bottom: 0; }
    .density-compact .right-bottom { height: 1fr; border: round $primary; }

    /* normal */
    .density-normal .left-pane  { padding: 0 1; }
    .density-normal .right-pane { padding: 0 1; }
    .density-normal .right-top  { height: 35%; border: solid $primary; margin-bottom: 1; }
    .density-normal .right-bottom { height: 1fr; border: solid $primary; }

    /* spacious */
    .density-spacious .left-pane  { padding: 1 2; }
    .density-spacious .right-pane { padding: 1 2; }
    .density-spacious .right-top  { height: 35%; border: double $primary; margin-bottom: 2; }
    .density-spacious .right-bottom { height: 1fr; border: double $primary; }
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
        backtest_viewer: BacktestViewer | None = None,
        paper_view_model: PaperTradingViewModel | None = None,
    ):
        super().__init__()
        self.report_repository = repository or ReportRepository()
        self.backtest_viewer = backtest_viewer
        self.paper_view_model = paper_view_model

    def on_mount(self) -> None:
        self.add_class("density-normal")
        self.add_class("panel-normal")

        self.install_screen(HomeScreen(), name="home")
        self.install_screen(
            ResearchAnalysisScreen(),
            name="research",
        )
        self.install_screen(
            ReportLibraryScreen(repository=self.report_repository),
            name="reports",
        )
        self.install_screen(
            BacktestScreen(
                viewer=self.backtest_viewer or BacktestViewer(),
            ),
            name="backtest",
        )
        self.install_screen(
            PaperTradingScreen(
                view_model=self.paper_view_model or PaperTradingViewModel(),
            ),
            name="paper",
        )
        self.install_screen(HelpScreen(), name="help")
        self.push_screen("home")

    def action_show_help(self) -> None:
        self.push_screen("help")

    def action_refresh_reports(self) -> None:
        pass  # screens override this via their own action_refresh_reports


def main() -> None:
    app = ETFAgentsTuiApp()
    app.run()
