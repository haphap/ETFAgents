"""Textual TUI command entrypoint."""

from __future__ import annotations

import typer


def tui() -> None:
    """Launch the Textual TUI alongside the existing analyze/backtest/paper CLI commands."""
    try:
        from cli.tui.app import ETFAgentsTuiApp
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            raise typer.BadParameter(
                "Textual is not installed. Install the TUI dependency with "
                "`pip install 'etfagents[tui]'`. Other CLI commands "
                "(`etfagents analyze`, `etfagents backtest`, `etfagents paper`) "
                "work without Textual."
            ) from exc
        raise

    ETFAgentsTuiApp().run()
