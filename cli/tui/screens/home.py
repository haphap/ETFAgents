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
                yield Static("Navigation", classes="pane-title")
                yield Button("▌ Research Analysis", id="btn_research", variant="primary", classes="nav-action")
                yield Button("  Reports Library", id="btn_reports", classes="nav-action")
                yield Button("  Backtest", id="btn_backtest", classes="nav-action")
                yield Button("  Paper Trading", id="btn_paper", classes="nav-action")
                yield Static("? Help   s Settings", classes="hint")
                yield Static("q Quit", classes="hint")
            with Vertical(classes="right-pane dashboard-pane"):
                yield Static("ETFAgents Interactive Mode", id="title")
                yield Static(
                    "Multi-agent ETF research workspace",
                    classes="subtitle",
                )
                with Horizontal(classes="dashboard-grid"):
                    with Vertical(classes="workspace-card"):
                        yield Static("Research", classes="workspace-card-title")
                        yield Static("Configure ETFs\nProvider/model selection", classes="muted")
                    with Vertical(classes="workspace-card"):
                        yield Static("Reports", classes="workspace-card-title")
                        yield Static("Local reports\nSection view", classes="muted")
                with Horizontal(classes="dashboard-grid"):
                    with Vertical(classes="workspace-card"):
                        yield Static("Backtest", classes="workspace-card-title")
                        yield Static("NAV / metrics\nRun validation", classes="muted")
                    with Vertical(classes="workspace-card"):
                        yield Static("Paper", classes="workspace-card-title")
                        yield Static("Account/PnL\nOrders", classes="muted")
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
