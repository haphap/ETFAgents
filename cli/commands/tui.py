"""Textual TUI command entrypoint."""

from __future__ import annotations

import typer


def tui() -> None:
    """Launch the Textual TUI alongside the existing analyze/backtest/paper CLI commands."""
    try:
        from cli.tui.app import main as tui_main
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            typer.echo(
                "Textual is not installed. Install the TUI dependency with "
                "`pip install 'etfagents[tui]'`. Other CLI commands "
                "(`etfagents analyze`, `etfagents backtest`, `etfagents paper`) "
                "work without Textual.",
                err=True,
            )
            raise SystemExit(1) from exc
        raise

    tui_main()
