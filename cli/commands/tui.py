"""Legacy Python TUI command entrypoint."""

from __future__ import annotations

import typer


def tui() -> None:
    """Show the migration path from the legacy Textual TUI to the Ink TUI."""
    typer.echo(
        "\n".join(
            [
                "The Python Textual TUI is deprecated.",
                "",
                "Use the TypeScript Ink TUI instead:",
                "  cd ts",
                "  pnpm dev tui",
                "",
                "The Python CLI remains available for non-TUI commands such as:",
                "  etfagents analyze",
                "  etfagents backtest",
                "  etfagents paper",
            ]
        )
    )
