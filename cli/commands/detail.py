from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text

from etfagents.detail import get_etf_detail, get_etf_history_reports
from etfagents.default_config import DEFAULT_CONFIG

_console = Console()


def _fmt_pct(value: float | None, suffix: str = "%") -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}{suffix}"


def _fmt_float(value: float | None, decimals: int = 4) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def _fmt_bps(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f} bps"


def detail(
    ticker: str = typer.Argument(..., help="ETF ticker, e.g. 510300.SH"),
    date: Optional[str] = typer.Option(None, "--date", "-d",
        help="As-of date (YYYY-MM-DD). Default: today."),
) -> None:
    """Show comprehensive ETF detail panel."""
    data = get_etf_detail(ticker, curr_date=date)

    if not data.get("name") and not data.get("close"):
        _console.print(f"[red]No data found for ticker '{ticker}'. Check the ticker symbol and try again.[/red]")
        raise typer.Exit(code=1)

    name = data.get("name") or ticker
    market = data.get("market") or ""

    # Header
    header_text = Text()
    header_text.append(f"{ticker}  ", style="bold cyan")
    header_text.append(f"{name}  ", style="bold green")
    if market:
        header_text.append(market, style="dim")
    header_text.append("\n")
    if data.get("latest_date"):
        header_text.append(f"{data['latest_date']}  ", style="dim")
    if data.get("close") is not None:
        header_text.append(f"收盘: {_fmt_float(data['close'])}", style="white")
        if data.get("pct_chg") is not None:
            pct_style = "green" if data["pct_chg"] >= 0 else "red"
            header_text.append(f"  涨跌: {_fmt_pct(data['pct_chg'])}", style=pct_style)

    # Price & NAV panel
    price_items = []
    if data.get("volume") is not None:
        price_items.append(f"成交量: {_fmt_float(data['volume'], 0)}")
    if data.get("amount") is not None:
        price_items.append(f"成交额: {_fmt_float(data['amount'], 0)}")
    if data.get("unit_nav") is not None:
        price_items.append(f"单位净值: {_fmt_float(data['unit_nav'])}")
    if data.get("premium_discount_bps") is not None:
        pd_style = "green" if data["premium_discount_bps"] <= 0 else "red"
        price_items.append(f"溢价率: [{pd_style}]{_fmt_bps(data['premium_discount_bps'])}[/{pd_style}]")
    if data.get("fund_share") is not None:
        # Tushare fd_share is in 亿 (100M) units
        price_items.append(f"份额: {_fmt_float(data['fund_share'], 2)}亿份")
    if data.get("share_change_pct") is not None:
        sc_style = "green" if data["share_change_pct"] >= 0 else "red"
        price_items.append(f"份额变化: [{sc_style}]{_fmt_pct(data['share_change_pct'])}[/{sc_style}]")

    price_panel = Panel(
        "\n".join(price_items) if price_items else "No price/NAV data",
        title="行情与净值",
        border_style="blue",
        padding=(1, 2),
    )

    # Fund info panel
    info_items = []
    if data.get("fund_type"):
        info_items.append(f"类型: {data['fund_type']}")
    if data.get("establish_date"):
        info_items.append(f"成立日: {data['establish_date']}")
    if data.get("manager"):
        info_items.append(f"基金经理: {data['manager']}")
    if data.get("benchmark"):
        info_items.append(f"业绩基准: {data['benchmark']}")

    info_panel = Panel(
        "\n".join(info_items) if info_items else "No fund info",
        title="基金档案",
        border_style="blue",
        padding=(1, 2),
    )

    # Holdings table
    holdings_table = Table(
        title="Top-10 持仓",
        show_header=True,
        header_style="bold magenta",
        show_lines=True,
    )
    holdings_table.add_column("Code", style="cyan")
    holdings_table.add_column("Name", style="green")
    holdings_table.add_column("Weight(%)", style="yellow", justify="right")

    if data.get("holdings"):
        for h in data["holdings"]:
            holdings_table.add_row(
                h.get("code", ""),
                h.get("name", ""),
                _fmt_float(h.get("weight_pct"), 2) if h.get("weight_pct") is not None else "N/A",
            )
    else:
        holdings_table.add_row("[dim]No holdings data[/dim]", "", "")

    # History reports
    from etfagents.dataflows.config import get_config
    config = get_config()
    results_dir = (config if config is not None else DEFAULT_CONFIG).get("results_dir", "")
    history = get_etf_history_reports(ticker, results_dir)

    history_table = Table(
        title="历史分析报告",
        show_header=True,
        header_style="bold magenta",
    )
    history_table.add_column("Date", style="cyan")
    history_table.add_column("Rating", style="yellow")
    history_table.add_column("Size", style="dim", justify="right")

    if history:
        _GREEN_RATINGS = {"BUY", "OVERWEIGHT", "买入", "增持"}
        _RED_RATINGS = {"SELL", "UNDERWEIGHT", "卖出", "减持"}
        for r in history[:20]:
            rating = r.get("rating") or "-"
            rating_style = "green" if rating in _GREEN_RATINGS else "red" if rating in _RED_RATINGS else "yellow"
            history_table.add_row(
                r.get("date", ""),
                Text(str(rating), style=rating_style),
                f"{r.get('size_kb', 0):.1f} KB",
            )
    else:
        history_table.add_row("[dim]暂无分析记录[/dim]", "", "")

    # Render
    _console.print()
    _console.print(Panel(header_text, border_style="green", padding=(1, 2)))
    _console.print(Columns([price_panel, info_panel], equal=True, expand=True))
    _console.print(holdings_table)
    _console.print(history_table)
