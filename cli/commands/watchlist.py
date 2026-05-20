from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from etfagents.watchlist import WatchlistManager

_console = Console()

watchlist_app = typer.Typer(help="ETF watchlist management.")


@watchlist_app.command("add")
def watchlist_add(
    tickers: str = typer.Argument(..., help="Comma-separated ETF tickers."),
    group: str = typer.Option("default", "--group", "-g", help="Group name."),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags."),
    notes: str = typer.Option("", "--notes", "-n", help="Notes."),
) -> None:
    wl = WatchlistManager()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    added = 0
    for ticker in tickers.split(","):
        ticker = ticker.strip()
        if not ticker:
            continue
        try:
            wl.add(ticker, group=group, tags=tag_list, notes=notes)
            added += 1
        except ValueError as exc:
            _console.print(f"[red]{exc}[/red]")
    _console.print(f"Added {added} ticker(s) to group '{group}'")


@watchlist_app.command("remove")
def watchlist_remove(
    tickers: str = typer.Argument(..., help="Comma-separated ETF tickers."),
    group: Optional[str] = typer.Option(None, "--group", "-g",
        help="Remove from specific group only. Default: all groups."),
) -> None:
    wl = WatchlistManager()
    total = 0
    for ticker in tickers.split(","):
        ticker = ticker.strip()
        if not ticker:
            continue
        total += wl.remove(ticker, group=group)
    _console.print(f"Removed {total} entry/entries")


@watchlist_app.command("list")
def watchlist_list(
    group: Optional[str] = typer.Option(None, "--group", "-g",
        help="Filter by group."),
    tags: Optional[str] = typer.Option(None, "--tags", "-t",
        help="Filter by tags (comma-separated, any match)."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    wl = WatchlistManager()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    entries = wl.list_tickers(group=group, tags=tag_list)

    if json_output:
        _console.print_json(data=entries)
        return

    table = Table(title="Watchlist", show_lines=True)
    table.add_column("Ticker", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Group", style="yellow")
    table.add_column("Tags", style="magenta")
    table.add_column("Added", style="dim")

    for e in entries:
        table.add_row(e["ticker"], e["name"], e["group"], ", ".join(e["tags"]), e["added_at"])
    _console.print(table)


@watchlist_app.command("group")
def watchlist_group_cmd(
    action: str = typer.Argument(..., help="add|remove|rename|list"),
    name: str = typer.Argument("", help="Group name (empty for list)."),
    new_name: Optional[str] = typer.Argument(None, help="New name (for rename action)."),
) -> None:
    wl = WatchlistManager()
    if action == "list":
        groups = wl.list_groups()
        table = Table(title="Watchlist Groups")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Count", style="yellow", justify="right")
        table.add_column("Sort Order", style="dim", justify="right")
        for g in groups:
            table.add_row(str(g["id"]), g["name"], str(g["count"]), str(g["sort_order"]))
        _console.print(table)
    elif action == "add":
        if not name:
            _console.print("[red]Group name required[/red]")
            raise typer.Exit(code=1)
        try:
            wl.add_group(name)
            _console.print(f"Added group '{name}'")
        except ValueError as exc:
            _console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1)
    elif action == "remove":
        if not name:
            _console.print("[red]Group name required[/red]")
            raise typer.Exit(code=1)
        try:
            removed = wl.remove_group(name)
        except ValueError as exc:
            _console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1)
        _console.print(f"Removed {removed} group(s)")
    elif action == "rename":
        if not name or not new_name:
            _console.print("[red]Both old and new name required[/red]")
            raise typer.Exit(code=1)
        try:
            wl.rename_group(name, new_name)
        except ValueError as exc:
            _console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1)
        _console.print(f"Renamed '{name}' to '{new_name}'")
    else:
        _console.print(f"[red]Unknown action '{action}'. Use add|remove|rename|list[/red]")
        raise typer.Exit(code=1)
