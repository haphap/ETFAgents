"""Textual TUI command entrypoint."""

from __future__ import annotations

import typer


def tui() -> None:
    """Launch the ETFAgents Textual TUI."""
    try:
        from cli.tui.app import ETFAgentsTuiApp
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            raise typer.BadParameter(
                "Textual is not installed. Install the package with current dependencies, then run 'etfagents tui' again."
            ) from exc
        raise

    ETFAgentsTuiApp().run()

