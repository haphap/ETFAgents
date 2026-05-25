"""Home dashboard screen."""

from __future__ import annotations

from pathlib import Path

from rich.align import Align
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

_BANNER_TEXT = (
    Path(__file__).resolve().parent.parent.parent / "static" / "welcome.txt"
).read_text(encoding="utf-8").rstrip("\n")


class _DynamicBanner(Static):

    DEFAULT_CSS = """
    _DynamicBanner {
        width: 100%;
        height: auto;
        padding: 1 0;
        color: $accent;
    }
    """

    def render(self) -> Align:
        lines = _BANNER_TEXT.splitlines()
        banner = Text("\n".join(lines), style="bold", justify="center")
        subtitle = Text("Multi-agent ETF research workspace", style="dim", justify="center")
        body = Text.assemble(banner, "\n", subtitle)
        return Align.center(body)


class HomeScreen(Screen):

    DEFAULT_CSS = """
    HomeScreen { align: center middle; }
    #home_body { width: auto; min-width: 46; max-width: 80; height: auto; }
    #home_body .nav-action { width: 100%; content-align: center middle; }
    #home_hints { color: $text-muted; text-align: center; width: 100%; margin-top: 2; }
    """

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                with Vertical(id="home_body"):
                    yield _DynamicBanner()
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
