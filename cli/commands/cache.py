from __future__ import annotations

import copy
from enum import Enum
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.cache_manager import CacheManager

_console = Console()

cache_app = typer.Typer(help="Cache management utilities.")


class _CacheTypeAll(str, Enum):
    # cleanup uses Optional[_CacheTypeAll] (None=all default); clear requires explicit choice including "all"
    api = "api"
    signals = "signals"
    snapshots = "snapshots"
    checkpoints = "checkpoints"
    all = "all"


_CacheType = _CacheTypeAll


@cache_app.command("stats")
def cache_stats(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    config = copy.deepcopy(DEFAULT_CONFIG)
    mgr = CacheManager(config)
    s = mgr.stats()

    if json_output:
        _console.print_json(data=s)
        return

    table = Table(title="Cache Statistics", show_footer=True)
    table.add_column("Category", style="cyan")
    table.add_column("Files", justify="right", style="green")
    table.add_column("Size (MB)", justify="right", style="yellow")

    total_files = 0
    for cat in CacheManager.CATEGORIES:
        info = s[cat]
        total_files += info["count"]
        table.add_row(cat, str(info["count"]), f"{info['size_mb']:.2f}")

    table.add_row("[bold]Total[/bold]", f"[bold]{total_files}[/bold]", f"[bold]{s['total_mb']:.2f}[/bold]")
    _console.print(table)


@cache_app.command("cleanup")
def cache_cleanup(
    days: int = typer.Option(7, "--days", min=0, help="Remove entries older than N days. 0=clear all."),
    category: Optional[_CacheType] = typer.Option(None, "--type", help="Cache category. Default: all."),
) -> None:
    config = copy.deepcopy(DEFAULT_CONFIG)
    mgr = CacheManager(config)
    cat = category.value if category else "all"
    result = mgr.cleanup(days, cat)
    _console.print(f"Deleted {result['deleted_files']} file(s), freed {result['freed_mb']:.2f} MB")


@cache_app.command("clear")
def cache_clear(
    category: _CacheTypeAll = typer.Option(_CacheTypeAll.all, "--type", help="Cache category to clear."),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    if not confirm:
        if category.value == "all":
            message = "Clear ALL cache categories? This cannot be undone"
        else:
            message = f"Clear all '{category.value}' cache? This cannot be undone"
        confirmed = typer.confirm(message)
        if not confirmed:
            raise typer.Exit(code=0)

    config = copy.deepcopy(DEFAULT_CONFIG)
    mgr = CacheManager(config)
    result = mgr.clear(category.value)
    _console.print(f"Cleared {result['deleted_files']} file(s), freed {result['freed_mb']:.2f} MB")
