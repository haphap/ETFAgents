"""Paper trading CLI commands."""

import json
from typing import Optional

import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from etfagents.paper_trading.engine import PaperTradingEngine

console = Console()
paper_app = typer.Typer(help="Paper trading simulation.")


def _engine() -> PaperTradingEngine:
    return PaperTradingEngine()


@paper_app.command("register")
def paper_register(
    username: str = typer.Argument(..., help="Username to register."),
):
    """Register a new paper trading user."""
    engine = _engine()
    pw1 = questionary.password("Password:").ask()
    if pw1 is None or not pw1.strip():
        console.print("[red]Password cannot be empty.[/red]")
        raise typer.Exit(code=1)
    pw2 = questionary.password("Confirm password:").ask()
    if pw1 != pw2:
        console.print("[red]Passwords do not match.[/red]")
        raise typer.Exit(code=1)
    try:
        engine.register(username, pw1)
        console.print(f"[green]User '{username}' registered successfully.[/green]")
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)


@paper_app.command("login")
def paper_login(
    username: str = typer.Argument(..., help="Username to login as."),
):
    """Login to paper trading account."""
    engine = _engine()
    if username == "default":
        logged_out = engine.logout()
        if logged_out:
            console.print(f"[green]Logged out from '{logged_out}'. Using default account.[/green]")
        else:
            console.print("[dim]Switched to default account.[/dim]")
        return
    pw = questionary.password("Password:").ask()
    if pw is None:
        raise typer.Exit(code=1)
    ok = engine.login(username, pw)
    if ok:
        console.print(f"[green]Logged in as '{username}'.[/green]")
    else:
        console.print("[red]Invalid username or password.[/red]")
        raise typer.Exit(code=1)


@paper_app.command("logout")
def paper_logout():
    """Logout from paper trading account."""
    engine = _engine()
    logged_out = engine.logout()
    if logged_out:
        console.print(f"[green]Logged out from '{logged_out}'. Using default account.[/green]")
    else:
        console.print("[dim]No active session. Already using default account.[/dim]")


@paper_app.command("account")
def paper_account(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """Show paper trading account overview."""
    engine = _engine()
    try:
        acc = engine.get_account(user_id=user)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    if json_output:
        console.print(json.dumps(acc, ensure_ascii=False, indent=2))
        return
    table = Table(title=f"Account: {acc['user_id']}", show_header=False, border_style="cyan")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")
    table.add_row("Cash", f"{acc['cash']:,.2f}")
    table.add_row("Market Value", f"{acc['market_value']:,.2f}")
    table.add_row("Total Assets", f"{acc['total_assets']:,.2f}")
    table.add_row("Realized P&L", f"{acc['realized_pnl']:,.2f}")
    table.add_row("Unrealized P&L", _fmt_pnl(acc["unrealized_pnl"]))
    table.add_row("Total Commission", f"{acc['total_commission']:,.2f}")
    table.add_row("Updated", acc["updated_at"])
    console.print(table)


@paper_app.command("buy")
def paper_buy(
    ticker: str = typer.Argument(..., help="ETF ticker."),
    quantity: int = typer.Argument(..., help="Number of shares (multiple of 100)."),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    analysis_id: Optional[str] = typer.Option(None, "--analysis-id",
        help="Link to analysis report directory."),
):
    """Buy ETF at market price."""
    engine = _engine()
    try:
        result = engine.buy(ticker, quantity, user_id=user, analysis_id=analysis_id)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    table = Table(title="Trade Executed", show_header=False, border_style="green")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green", justify="right")
    table.add_row("Ticker", result["ticker"])
    table.add_row("Side", "BUY")
    table.add_row("Quantity", str(result["quantity"]))
    table.add_row("Price", f"{result['price']:.4f}")
    table.add_row("Amount", f"{result['amount']:,.2f}")
    table.add_row("Commission", f"{result['commission']:.2f}")
    table.add_row("Total Cost", f"{result['total_cost']:,.2f}")
    console.print(table)


@paper_app.command("sell")
def paper_sell(
    ticker: str = typer.Argument(..., help="ETF ticker."),
    quantity: int = typer.Argument(..., help="Number of shares (multiple of 100)."),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    analysis_id: Optional[str] = typer.Option(None, "--analysis-id",
        help="Link to analysis report directory."),
):
    """Sell ETF at market price."""
    engine = _engine()
    try:
        result = engine.sell(ticker, quantity, user_id=user, analysis_id=analysis_id)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    table = Table(title="Trade Executed", show_header=False, border_style="green")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green", justify="right")
    table.add_row("Ticker", result["ticker"])
    table.add_row("Side", "SELL")
    table.add_row("Quantity", str(result["quantity"]))
    table.add_row("Price", f"{result['price']:.4f}")
    table.add_row("Amount", f"{result['amount']:,.2f}")
    table.add_row("Commission", f"{result['commission']:.2f}")
    table.add_row("P&L", _fmt_pnl(result["pnl"]))
    console.print(table)


@paper_app.command("positions")
def paper_positions(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
):
    """List all positions with live P&L."""
    engine = _engine()
    try:
        positions = engine.get_positions(user_id=user)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    if json_output:
        console.print(json.dumps(positions, ensure_ascii=False, indent=2))
        return
    if not positions:
        console.print("[dim]No positions.[/dim]")
        return
    table = Table(title="Positions", show_header=True, header_style="bold cyan", border_style="cyan")
    table.add_column("Ticker", style="cyan")
    table.add_column("Name")
    table.add_column("Quantity", justify="right")
    table.add_column("Avail Qty", justify="right", style="dim")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Market Value", justify="right", style="green")
    table.add_column("Unreal. P&L", justify="right")
    table.add_column("P&L %", justify="right")
    for p in positions:
        table.add_row(
            p["ticker"],
            p["name"] or p["ticker"],
            str(p["quantity"]),
            str(p["available_qty"]),
            f"{p['avg_cost']:.4f}",
            f"{p['current_price']:.4f}",
            f"{p['market_value']:,.2f}",
            _fmt_pnl(p["unrealized_pnl"]),
            f"{p['pnl_pct']:+.2f}%",
        )
    console.print(table)


@paper_app.command("history")
def paper_history(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent trades."),
):
    """Show trade history."""
    engine = _engine()
    try:
        trades = engine.get_trades(user_id=user, limit=limit)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    if not trades:
        console.print("[dim]No trade history.[/dim]")
        return
    table = Table(title="Trade History", show_header=True, header_style="bold cyan", border_style="cyan")
    table.add_column("Time", style="dim")
    table.add_column("Side", style="cyan")
    table.add_column("Ticker")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Amount", justify="right")
    table.add_column("Commission", justify="right")
    table.add_column("P&L", justify="right")
    for t in trades:
        side_color = "green" if t["side"] == "buy" else "red"
        pnl_str = _fmt_pnl(t["pnl"]) if t["pnl"] is not None else "-"
        table.add_row(
            t["created_at"],
            f"[{side_color}]{t['side'].upper()}[/{side_color}]",
            t["ticker"],
            str(t["quantity"]),
            f"{t['price']:.4f}",
            f"{t['amount']:,.2f}",
            f"{t['commission']:.2f}",
            pnl_str,
        )
    console.print(table)


@paper_app.command("reset")
def paper_reset(
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Paper trading user."),
    confirm: bool = typer.Option(False, "--yes", "-y",
        help="Skip confirmation. This deletes ALL paper trading data."),
    cash: float = typer.Option(1_000_000.0, "--cash",
        help="Initial cash after reset."),
):
    """Reset paper trading account."""
    if not confirm:
        ok = questionary.confirm(
            "This will delete ALL positions and trade history for this account. Continue?"
        ).ask()
        if not ok:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit()
    engine = _engine()
    try:
        engine.reset_account(user_id=user, initial_cash=cash)
        uid = user or engine._get_current_user()
        console.print(f"[green]Account '{uid}' reset with {cash:,.2f} cash.[/green]")
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)


def _fmt_pnl(value: float | None) -> str:
    if value is None:
        return "-"
    color = "green" if value >= 0 else "red"
    return f"[{color}]{value:+,.2f}[/{color}]"
