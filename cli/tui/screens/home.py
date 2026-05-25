"""Home dashboard screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Static


class HomeScreen(Screen):

    DEFAULT_CSS = """
    HomeScreen { align: center middle; }
    #home_body { width: auto; min-width: 46; max-width: 72; height: auto; }
    #home_banner { color: $accent; text-align: center; width: 100%; height: 6; margin-bottom: 1; }
    #home_title { text-style: bold; color: $accent; text-align: center; width: 100%; margin-bottom: 1; }
    #home_subtitle { color: $text-muted; text-align: center; width: 100%; margin-bottom: 2; }
    #home_body .nav-action { width: 100%; content-align: center middle; }
    #home_hints { color: $text-muted; text-align: center; width: 100%; margin-top: 2; }
    """

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="home_body"):
                    yield Static(
                        "  _____ _____ _____    _                    _       \n"
                        " | ____|_   _|  ___|  / \\   __ _  ___ _ __ | |_ ___ \n"
                        " |  _|   | | | |_    / _ \\ / _` |/ _ \\ '_ \\| __/ __|\n"
                        " | |___  | | |  _|  / ___ \\ (_| |  __/ | | | |_\\__ \\\n"
                        " |_____| |_| |_|   /_/   \\_\\__, |\\___|_| |_|\\__|___/\n"
                        "                           |___/                    ",
                        id="home_banner",
                    )
                    yield Static("ETFAgents", id="home_title")
                    yield Static("Multi-agent ETF research workspace", id="home_subtitle")
                    yield Button("Research Analysis", id="btn_research", classes="nav-action")
                    yield Button("Reports Library", id="btn_reports", classes="nav-action")
                    yield Button("Backtest", id="btn_backtest", classes="nav-action")
                    yield Button("Paper Trading", id="btn_paper", classes="nav-action")
                    yield Static("? Help   s Settings   q Quit", id="home_hints")
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
