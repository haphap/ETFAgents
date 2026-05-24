"""Home dashboard screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class HomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane nav-pane"):
                yield Static("Menu", classes="pane-title")
                yield Button("⌂  研究分析", id="btn_research", variant="primary", classes="nav-button")
                yield Button("▤  研究报告库", id="btn_reports", classes="nav-button")
                yield Button("⌁  回测", id="btn_backtest", classes="nav-button")
                yield Button("◈  模拟交易", id="btn_paper", classes="nav-button")
            with Vertical(classes="right-pane dashboard-pane"):
                yield Static("ETFAgents Interactive Mode", id="title")
                yield Static(
                    "多智能体 ETF 研究 · 报告复盘 · 回测验证 · 模拟交易",
                    classes="subtitle",
                )
                with Vertical(classes="dashboard-card"):
                    yield Static("Connection Details", classes="pane-title")
                    yield Static("Provider      : local config\nResearch Graph: ready\nReports       : local repository")
                with Vertical(classes="dashboard-card"):
                    yield Static("Workflow", classes="pane-title")
                    yield Static("1. 选择研究分析并输入 ETF\n2. 配置 provider / model / 研究深度\n3. 在运行页查看整体进度与团队报告")
                yield Static("ETFAgents", classes="ascii-logo")
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
