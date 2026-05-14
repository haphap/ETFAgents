from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from html import escape
import inspect
from io import StringIO
import json
from math import sqrt
from pathlib import Path
import re
from typing import Any, Callable

import backtrader as bt
import pandas as pd
from etfagents.dataflows.config import (
    backtest_context,
    backtest_health_context,
    get_backtest_health_state,
)
from etfagents.dataflows.interface import route_to_vendor

EQUAL_WEIGHT_BENCHMARK = "equal_weight_pool"


@dataclass
class BacktraderRebalanceRecord:
    decision_date: str
    execution_date: str
    selected_tickers: list[str]
    weights: dict[str, float]
    ratings: dict[str, str]
    turnover: float
    signals: list[dict[str, Any]]
    reason: str = "scheduled"
    trigger_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BacktraderOrderRecord:
    execution_date: str
    ticker: str
    side: str
    size: float
    price: float
    value: float
    commission: float


@dataclass
class BacktraderTradeRecord:
    ticker: str
    open_date: str
    close_date: str
    pnl: float
    pnlcomm: float


@dataclass
class BacktraderNavRecord:
    date: str
    nav: float
    cash: float
    gross_exposure: float


@dataclass
class BacktraderPositionRecord:
    date: str
    ticker: str
    size: float
    value: float
    weight: float


@dataclass
class BacktraderBenchmarkRecord:
    date: str
    benchmark: str
    nav: float


@dataclass
class BacktraderBenchmarkMetrics:
    benchmark: str
    final_value: float
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    sharpe_ratio: float
    excess_cumulative_return: float
    tracking_error: float
    information_ratio: float


@dataclass
class BacktraderMetrics:
    final_value: float
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    average_turnover: float


@dataclass
class BacktestHealthMetrics:
    weight_source_counts: dict[str, int]
    trigger_bucket_counts: dict[str, int]
    structured_trigger_count: int
    risk_rule_count: int
    execution_timing_mismatch_count: int
    dynamic_rebalance_count: int
    trigger_event_count: int
    unsupported_trigger_count: int
    missing_price_rows: int
    clamp_hit_count: int
    blocked_call_count: int


@dataclass
class BacktraderBacktestResult:
    tickers: list[str]
    benchmarks: list[str]
    start_date: str
    end_date: str
    rebalance_interval_days: int
    top_k: int
    execution_timing: str
    initial_cash: float
    commission: float
    slippage_perc: float
    cash_buffer_pct: float
    metrics: BacktraderMetrics
    rebalances: list[BacktraderRebalanceRecord]
    nav: list[BacktraderNavRecord]
    positions: list[BacktraderPositionRecord]
    benchmark_nav: list[BacktraderBenchmarkRecord]
    benchmark_metrics: list[BacktraderBenchmarkMetrics]
    orders: list[BacktraderOrderRecord]
    trades: list[BacktraderTradeRecord]
    analyzer_outputs: dict[str, Any]
    health: BacktestHealthMetrics

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def rebalance_summary_rows(self) -> list[dict[str, Any]]:
        return _build_rebalance_summary_rows(self)


class FractionalETFCommissionInfo(bt.CommInfoBase):
    params = (
        ("commission", 0.0),
        ("stocklike", True),
        ("commtype", bt.CommInfoBase.COMM_PERC),
        ("percabs", True),
    )

    def getsize(self, price, cash):
        if not price:
            return 0.0
        return float(cash) / float(price)

    def getoperationcost(self, size, price):
        return abs(float(size)) * float(price)

    def getvaluesize(self, size, price):
        return float(size) * float(price)

    def getvalue(self, position, price):
        return float(position.size) * float(price)


def _read_tool_csv(payload: str) -> pd.DataFrame:
    csv_lines = [
        line for line in (payload or "").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not csv_lines:
        return pd.DataFrame()
    return pd.read_csv(StringIO("\n".join(csv_lines)))


def _load_price_frame(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    payload = route_to_vendor("get_etf_price_data", ticker, start_date, end_date)
    df = _read_tool_csv(payload)
    if df.empty or "Date" not in df.columns or "Close" not in df.columns:
        raise ValueError(f"No backtest price history available for '{ticker}'.")
    return _normalize_price_frame(df, ticker)


def _normalize_price_frame(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    output = df.copy()
    output["Date"] = pd.to_datetime(output["Date"], errors="coerce")
    for column in ("Open", "Close"):
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce")
    output = output.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)
    if output.empty:
        raise ValueError(f"No usable price rows available for '{ticker}'.")
    return output


def _validate_execution_timing(execution_timing: str) -> str:
    normalized = (execution_timing or "same_close").strip().lower()
    if normalized not in {"same_close", "next_open", "next_close"}:
        raise ValueError(
            "execution_timing must be one of: same_close, next_open, next_close."
        )
    return normalized


def _extend_loader_end_date(end_date: str, execution_timing: str) -> str:
    timing = _validate_execution_timing(execution_timing)
    if timing == "same_close":
        return end_date
    return (pd.to_datetime(end_date) + timedelta(days=7)).strftime("%Y-%m-%d")


def _build_rebalance_schedule(dates: list[str], rebalance_interval_days: int) -> list[str]:
    if len(dates) < 2:
        raise ValueError("Backtest requires at least two trading dates.")
    step = max(1, int(rebalance_interval_days))
    schedule = [dates[index] for index in range(0, len(dates), step)]
    if schedule[-1] != dates[-1]:
        schedule.append(dates[-1])
    if len(schedule) < 2:
        raise ValueError("Backtest schedule must contain at least one holding window.")
    return schedule


def _normalize_candidate_weights(candidates: list[dict[str, object]], top_k: int) -> dict[str, float]:
    selected = candidates[: max(1, top_k)]
    raw_weights: dict[str, float] = {}
    for candidate in selected:
        ticker = str(candidate["ticker"])
        raw_weight = candidate.get("suggested_weight_pct", 0.0)
        try:
            raw_weights[ticker] = max(float(raw_weight), 0.0)
        except (TypeError, ValueError):
            raw_weights[ticker] = 0.0

    total_weight = sum(raw_weights.values())
    if total_weight <= 0:
        equal_weight = round(1 / len(raw_weights), 6)
        return {ticker: equal_weight for ticker in raw_weights}
    return {ticker: value / total_weight for ticker, value in raw_weights.items()}


def _analyze_candidate_pool(graph, tickers: list[str], decision_date: str, force_refresh: bool):
    analyze = graph.analyze_candidate_pool
    try:
        signature = inspect.signature(analyze)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and "force_refresh" in signature.parameters:
        return analyze(tickers, decision_date, force_refresh=force_refresh)
    return analyze(tickers, decision_date)


def _to_backtrader_feed(df: pd.DataFrame, ticker: str) -> bt.feeds.PandasData:
    normalized = _normalize_price_frame(df, ticker).copy()
    if "Open" not in normalized.columns:
        normalized["Open"] = normalized["Close"]
    if "High" not in normalized.columns:
        normalized["High"] = normalized["Close"]
    if "Low" not in normalized.columns:
        normalized["Low"] = normalized["Close"]
    if "Volume" not in normalized.columns:
        normalized["Volume"] = 0.0
    normalized = normalized.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    normalized["openinterest"] = 0.0
    feed_frame = normalized.set_index("Date")[
        ["open", "high", "low", "close", "volume", "openinterest"]
    ]
    return bt.feeds.PandasData(dataname=feed_frame, name=ticker)


def _execution_order_kwargs(execution_timing: str) -> dict[str, Any]:
    if execution_timing == "next_close":
        return {"exectype": bt.Order.Close}
    return {}


def _portfolio_turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    if not previous:
        return 0.0
    universe = set(previous) | set(current)
    return sum(abs(current.get(ticker, 0.0) - previous.get(ticker, 0.0)) for ticker in universe) / 2


def _safe_iso_date(value: Any) -> str:
    if value in (None, 0):
        return ""
    try:
        return bt.num2date(value).date().isoformat()
    except Exception:
        return ""


def _extract_trade_count(analysis: Any) -> int:
    if not analysis:
        return 0
    total = analysis.get("total", {})
    if isinstance(total, dict):
        try:
            return int(total.get("closed") or total.get("total") or 0)
        except (TypeError, ValueError):
            return 0
    try:
        return int(total or 0)
    except (TypeError, ValueError):
        return 0


def _compute_return_series(nav_values: list[float]) -> pd.Series:
    returns = pd.Series(
        [
            nav_values[index] / nav_values[index - 1] - 1
            for index in range(1, len(nav_values))
            if nav_values[index - 1]
        ],
        dtype="float64",
    )
    return returns


def _compute_nav_statistics(nav_values: list[float], initial_cash: float) -> dict[str, float]:
    final_value = nav_values[-1] if nav_values else initial_cash
    cumulative_return = final_value / initial_cash - 1 if initial_cash else 0.0
    returns = _compute_return_series(nav_values)
    periods = max(len(returns), 1)
    annualized_return = (1 + cumulative_return) ** (252 / periods) - 1 if periods and final_value > 0 else 0.0
    annualized_volatility = float(returns.std(ddof=0) * sqrt(252)) if not returns.empty else 0.0
    sharpe_ratio = (
        float((returns.mean() / returns.std(ddof=0)) * sqrt(252))
        if len(returns) > 1 and returns.std(ddof=0) > 0
        else 0.0
    )
    nav_series = pd.Series(nav_values, dtype="float64")
    running_peak = nav_series.cummax()
    drawdowns = nav_series / running_peak - 1 if not nav_series.empty else pd.Series(dtype="float64")
    max_drawdown = float(drawdowns.min()) if not drawdowns.empty else 0.0
    return {
        "final_value": float(final_value),
        "cumulative_return": float(cumulative_return),
        "annualized_return": float(annualized_return),
        "annualized_volatility": float(annualized_volatility),
        "max_drawdown": max_drawdown,
        "sharpe_ratio": float(sharpe_ratio),
    }


def _compute_metrics(
    nav_records: list[BacktraderNavRecord],
    initial_cash: float,
    rebalances: list[BacktraderRebalanceRecord],
    trade_count: int,
) -> BacktraderMetrics:
    stats = _compute_nav_statistics([record.nav for record in nav_records], initial_cash)
    average_turnover = (
        float(pd.Series([record.turnover for record in rebalances[1:]], dtype="float64").mean())
        if len(rebalances) > 1
        else 0.0
    )
    return BacktraderMetrics(
        final_value=stats["final_value"],
        cumulative_return=stats["cumulative_return"],
        annualized_return=stats["annualized_return"],
        annualized_volatility=stats["annualized_volatility"],
        max_drawdown=stats["max_drawdown"],
        sharpe_ratio=stats["sharpe_ratio"],
        total_trades=int(trade_count),
        average_turnover=float(average_turnover),
    )


def _normalize_benchmark_list(
    graph: Any,
    tickers: list[str],
    benchmark_tickers: list[str] | None,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    requested = benchmark_tickers
    if requested is None:
        if len(tickers) > 1:
            requested = [EQUAL_WEIGHT_BENCHMARK]
        elif hasattr(graph, "_resolve_benchmark_ticker"):
            requested = [str(graph._resolve_benchmark_ticker(tickers[0]))]
        else:
            requested = []
    for raw in requested:
        value = str(raw or "").strip()
        if not value:
            continue
        benchmark = (
            EQUAL_WEIGHT_BENCHMARK
            if value.lower() == EQUAL_WEIGHT_BENCHMARK
            else value.upper()
        )
        if benchmark in seen:
            continue
        seen.add(benchmark)
        normalized.append(benchmark)
    return normalized


def _align_close_series(df: pd.DataFrame, nav_dates: list[str], ticker: str) -> pd.Series:
    nav_frame = pd.DataFrame({"Date": pd.to_datetime(nav_dates)})
    price_frame = _normalize_price_frame(df, ticker)[["Date", "Close"]].sort_values("Date")
    aligned = pd.merge_asof(nav_frame, price_frame, on="Date", direction="backward")
    if aligned["Close"].isna().any():
        raise ValueError(
            f"Benchmark '{ticker}' does not have prices available for the full backtest window."
        )
    return aligned["Close"].astype("float64")


def _build_benchmark_nav_records(
    benchmark: str,
    nav_dates: list[str],
    initial_cash: float,
    price_cache: dict[str, pd.DataFrame],
) -> list[BacktraderBenchmarkRecord]:
    if not nav_dates:
        return []

    if benchmark == EQUAL_WEIGHT_BENCHMARK:
        aligned = pd.DataFrame(
            {
                ticker: _align_close_series(frame, nav_dates, ticker)
                for ticker, frame in price_cache.items()
            }
        )
        base = aligned.iloc[0]
        if (base <= 0).any():
            raise ValueError("Equal-weight benchmark requires positive starting prices.")
        nav_values = aligned.divide(base).mean(axis=1) * float(initial_cash)
    else:
        closes = _align_close_series(price_cache[benchmark], nav_dates, benchmark)
        base_price = float(closes.iloc[0])
        if base_price <= 0:
            raise ValueError(f"Benchmark '{benchmark}' requires a positive starting price.")
        nav_values = closes / base_price * float(initial_cash)

    return [
        BacktraderBenchmarkRecord(
            date=decision_date,
            benchmark=benchmark,
            nav=float(nav_value),
        )
        for decision_date, nav_value in zip(nav_dates, nav_values.tolist())
    ]


def _compute_benchmark_metrics(
    benchmark: str,
    benchmark_nav: list[BacktraderBenchmarkRecord],
    portfolio_nav: list[BacktraderNavRecord],
    initial_cash: float,
) -> BacktraderBenchmarkMetrics:
    benchmark_values = [record.nav for record in benchmark_nav]
    portfolio_values = [record.nav for record in portfolio_nav]
    stats = _compute_nav_statistics(benchmark_values, initial_cash)
    benchmark_returns = _compute_return_series(benchmark_values)
    portfolio_returns = _compute_return_series(portfolio_values)
    active_returns = portfolio_returns - benchmark_returns
    tracking_error = (
        float(active_returns.std(ddof=0) * sqrt(252))
        if len(active_returns) > 1 and active_returns.std(ddof=0) > 0
        else 0.0
    )
    information_ratio = (
        float((active_returns.mean() / active_returns.std(ddof=0)) * sqrt(252))
        if len(active_returns) > 1 and active_returns.std(ddof=0) > 0
        else 0.0
    )
    return BacktraderBenchmarkMetrics(
        benchmark=benchmark,
        final_value=stats["final_value"],
        cumulative_return=stats["cumulative_return"],
        annualized_return=stats["annualized_return"],
        annualized_volatility=stats["annualized_volatility"],
        max_drawdown=stats["max_drawdown"],
        sharpe_ratio=stats["sharpe_ratio"],
        excess_cumulative_return=(
            portfolio_nav[-1].nav / initial_cash - 1 - stats["cumulative_return"]
            if portfolio_nav and initial_cash
            else 0.0
        ),
        tracking_error=tracking_error,
        information_ratio=information_ratio,
    )


def _count_missing_price_rows(df: pd.DataFrame, execution_timing: str) -> int:
    if df is None or df.empty:
        return 0
    working = df.copy()
    if "Date" in working.columns:
        working["Date"] = pd.to_datetime(working["Date"], errors="coerce")
    missing = working["Date"].isna() if "Date" in working.columns else pd.Series(False, index=working.index)
    if "Close" in working.columns:
        missing = missing | pd.to_numeric(working["Close"], errors="coerce").isna()
    if execution_timing == "next_open" and "Open" in working.columns:
        missing = missing | pd.to_numeric(working["Open"], errors="coerce").isna()
    return int(missing.sum())


def _nav_on_or_before(nav_records: list[BacktraderNavRecord], date_str: str) -> float | None:
    target = pd.to_datetime(date_str)
    eligible = [
        record.nav for record in nav_records
        if pd.to_datetime(record.date) <= target
    ]
    if not eligible:
        return None
    return float(eligible[-1])


def _build_rebalance_summary_rows(result: BacktraderBacktestResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(result.rebalances):
        start_nav = _nav_on_or_before(result.nav, record.execution_date)
        next_execution = (
            result.rebalances[index + 1].execution_date
            if index + 1 < len(result.rebalances)
            else result.nav[-1].date if result.nav else record.execution_date
        )
        end_nav = _nav_on_or_before(result.nav, next_execution)
        period_return = (
            (end_nav / start_nav - 1.0)
            if start_nav and end_nav and start_nav > 0
            else 0.0
        )
        cumulative_return = (
            (end_nav / result.initial_cash - 1.0)
            if end_nav and result.initial_cash > 0
            else 0.0
        )
        weight_sources = sorted(
            {
                str(signal.get("weight_source", "unknown"))
                for signal in record.signals
                if isinstance(signal, dict)
            }
        )
        rows.append(
            {
                "decision_date": record.decision_date,
                "execution_date": record.execution_date,
                "reason": record.reason,
                "selected_tickers": list(record.selected_tickers),
                "weights": dict(record.weights),
                "ratings": dict(record.ratings),
                "weight_sources": weight_sources,
                "trigger_events": len(record.trigger_events),
                "period_return": float(period_return),
                "cumulative_return": float(cumulative_return),
            }
        )
    return rows


def _build_health_metrics(
    execution_timing: str,
    rebalances: list[BacktraderRebalanceRecord],
    missing_price_rows: int,
    unsupported_trigger_count: int,
    routing_health: Any,
) -> BacktestHealthMetrics:
    scheduled_records = [record for record in rebalances if record.reason == "scheduled"]
    signals = [
        signal
        for record in scheduled_records
        for signal in record.signals
        if isinstance(signal, dict)
    ]
    weight_source_counts: dict[str, int] = {}
    trigger_bucket_counts = {
        "add": 0,
        "reduce": 0,
        "exit": 0,
        "rebalance": 0,
        "risk": 0,
    }
    structured_trigger_count = 0
    risk_rule_count = 0
    execution_timing_mismatch_count = 0
    for signal in signals:
        weight_source = str(signal.get("weight_source", "unknown"))
        weight_source_counts[weight_source] = weight_source_counts.get(weight_source, 0) + 1
        trigger_bucket_counts["add"] += len(signal.get("add_triggers", []))
        trigger_bucket_counts["reduce"] += len(signal.get("reduce_triggers", []))
        trigger_bucket_counts["exit"] += len(signal.get("exit_triggers", []))
        trigger_bucket_counts["rebalance"] += len(signal.get("rebalance_triggers", []))
        trigger_bucket_counts["risk"] += len(signal.get("risk_rules", []))
        structured_trigger_count += (
            len(signal.get("add_triggers", []))
            + len(signal.get("reduce_triggers", []))
            + len(signal.get("exit_triggers", []))
            + len(signal.get("rebalance_triggers", []))
        )
        risk_rule_count += len(signal.get("risk_rules", []))
        if str(signal.get("execution_delay", execution_timing)) != execution_timing:
            execution_timing_mismatch_count += 1

    trigger_event_count = sum(len(record.trigger_events) for record in rebalances)
    dynamic_rebalance_count = sum(1 for record in rebalances if record.reason == "trigger")
    return BacktestHealthMetrics(
        weight_source_counts=weight_source_counts,
        trigger_bucket_counts=trigger_bucket_counts,
        structured_trigger_count=structured_trigger_count,
        risk_rule_count=risk_rule_count,
        execution_timing_mismatch_count=execution_timing_mismatch_count,
        dynamic_rebalance_count=dynamic_rebalance_count,
        trigger_event_count=trigger_event_count,
        unsupported_trigger_count=int(unsupported_trigger_count),
        missing_price_rows=int(missing_price_rows),
        clamp_hit_count=int(routing_health.clamp_hits),
        blocked_call_count=int(routing_health.blocked_calls),
    )


def _format_pct(value: float) -> str:
    return f"{float(value):.2%}"


def _build_backtest_summary_markdown(result: BacktraderBacktestResult) -> str:
    lines = [
        "# Backtest Summary",
        "",
        "## Run Configuration",
        "",
        f"- Tickers: {', '.join(result.tickers)}",
        f"- Benchmarks: {', '.join(result.benchmarks) if result.benchmarks else 'None'}",
        f"- Window: {result.start_date} -> {result.end_date}",
        f"- Rebalance interval days: {result.rebalance_interval_days}",
        f"- Top K: {result.top_k}",
        f"- Execution timing: {result.execution_timing}",
        f"- Initial cash: {result.initial_cash:,.2f}",
        f"- Commission: {_format_pct(result.commission)}",
        f"- Slippage: {_format_pct(result.slippage_perc)}",
        f"- Cash buffer: {_format_pct(result.cash_buffer_pct)}",
        "",
        "## Strategy Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Cumulative return | {_format_pct(result.metrics.cumulative_return)} |",
        f"| Annualized return | {_format_pct(result.metrics.annualized_return)} |",
        f"| Annualized volatility | {_format_pct(result.metrics.annualized_volatility)} |",
        f"| Max drawdown | {_format_pct(result.metrics.max_drawdown)} |",
        f"| Sharpe ratio | {result.metrics.sharpe_ratio:.4f} |",
        f"| Average turnover | {result.metrics.average_turnover:.4f} |",
        f"| Total trades | {result.metrics.total_trades} |",
        "",
    ]
    if result.benchmark_metrics:
        lines.extend(
            [
                "## Benchmark Comparison",
                "",
                "| Benchmark | Return | Excess Return | Max Drawdown | Tracking Error | Information Ratio |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for metric in result.benchmark_metrics:
            lines.append(
                "| "
                f"{metric.benchmark} | {_format_pct(metric.cumulative_return)} | "
                f"{_format_pct(metric.excess_cumulative_return)} | {_format_pct(metric.max_drawdown)} | "
                f"{_format_pct(metric.tracking_error)} | {metric.information_ratio:.4f} |"
        )
        lines.append("")
    if result.health.weight_source_counts:
        lines.extend(
            [
                "## Data Health",
                "",
                "| Check | Value |",
                "| --- | --- |",
                f"| Weight source distribution | {', '.join(f'{key}:{value}' for key, value in sorted(result.health.weight_source_counts.items()))} |",
                f"| Structured trigger count | {result.health.structured_trigger_count} |",
                f"| Risk rule count | {result.health.risk_rule_count} |",
                f"| Execution timing mismatches | {result.health.execution_timing_mismatch_count} |",
                f"| Clamp hits | {result.health.clamp_hit_count} |",
                f"| Missing price rows | {result.health.missing_price_rows} |",
                f"| Unsupported trigger rules | {result.health.unsupported_trigger_count} |",
                "",
            ]
        )
    summary_rows = _build_rebalance_summary_rows(result)
    if summary_rows:
        lines.extend(
            [
                "## Rebalance Summary",
                "",
                "| Decision Date | Reason | Selected Tickers | Weight Sources | Period Return | Cumulative Return |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in summary_rows:
            lines.append(
                "| "
                f"{row['decision_date']} | {row['reason']} | {', '.join(row['selected_tickers']) or '-'} | "
                f"{', '.join(row['weight_sources']) or 'unknown'} | {_format_pct(row['period_return'])} | {_format_pct(row['cumulative_return'])} |"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_nav_chart_svg(result: BacktraderBacktestResult) -> str:
    series_map: dict[str, list[tuple[str, float]]] = {
        "strategy": [(record.date, record.nav) for record in result.nav]
    }
    for benchmark in result.benchmarks:
        series_map[benchmark] = [
            (record.date, record.nav)
            for record in result.benchmark_nav
            if record.benchmark == benchmark
        ]

    width = 960
    height = 360
    padding_left = 64
    padding_right = 24
    padding_top = 24
    padding_bottom = 48
    palette = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c"]
    all_values = [value for series in series_map.values() for _, value in series]
    min_value = min(all_values) if all_values else 0.0
    max_value = max(all_values) if all_values else 1.0
    if max_value <= min_value:
        max_value = min_value + 1.0
    chart_width = width - padding_left - padding_right
    chart_height = height - padding_top - padding_bottom

    def _point(index: int, value: float, total_points: int) -> tuple[float, float]:
        x = padding_left if total_points <= 1 else padding_left + chart_width * index / (total_points - 1)
        y = padding_top + chart_height * (1 - (value - min_value) / (max_value - min_value))
        return x, y

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Backtest NAV chart">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<line x1="{padding_left}" y1="{padding_top}" x2="{padding_left}" y2="{padding_top + chart_height}" stroke="#cbd5e1" />',
        f'<line x1="{padding_left}" y1="{padding_top + chart_height}" x2="{padding_left + chart_width}" y2="{padding_top + chart_height}" stroke="#cbd5e1" />',
    ]

    for idx, label in enumerate(series_map):
        series = series_map[label]
        if not series:
            continue
        color = palette[idx % len(palette)]
        points = [
            _point(point_index, value, len(series))
            for point_index, (_, value) in enumerate(series)
        ]
        path = " ".join(
            f"{'M' if point_index == 0 else 'L'} {x:.2f} {y:.2f}"
            for point_index, (x, y) in enumerate(points)
        )
        lines.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        last_x, last_y = points[-1]
        lines.append(
            f'<text x="{last_x + 8:.2f}" y="{last_y + 4:.2f}" font-size="12" fill="{color}">{escape(label)}</text>'
        )

    if result.nav:
        first_date = result.nav[0].date
        last_date = result.nav[-1].date
        lines.append(
            f'<text x="{padding_left}" y="{height - 16}" font-size="12" fill="#475569">{escape(first_date)}</text>'
        )
        lines.append(
            f'<text x="{padding_left + chart_width - 72}" y="{height - 16}" font-size="12" fill="#475569">{escape(last_date)}</text>'
        )
    lines.append(
        f'<text x="16" y="{padding_top + 12}" font-size="12" fill="#475569">{min_value:,.0f} - {max_value:,.0f}</text>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


def _build_backtest_report_html(result: BacktraderBacktestResult) -> str:
    benchmark_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(metric.benchmark)}</td>"
            f"<td>{_format_pct(metric.cumulative_return)}</td>"
            f"<td>{_format_pct(metric.excess_cumulative_return)}</td>"
            f"<td>{_format_pct(metric.max_drawdown)}</td>"
            f"<td>{_format_pct(metric.tracking_error)}</td>"
            f"<td>{metric.information_ratio:.4f}</td>"
            "</tr>"
        )
        for metric in result.benchmark_metrics
    ) or '<tr><td colspan="6">No benchmark configured.</td></tr>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>ETFAgents Backtest Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #0f172a; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 16px 0 24px; }}
    .card {{ border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; background: #f8fafc; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; }}
    th {{ background: #e2e8f0; }}
    .meta {{ color: #475569; }}
  </style>
</head>
<body>
  <h1>ETFAgents Backtest Report</h1>
  <p class="meta">{escape(', '.join(result.tickers))} | {escape(result.start_date)} to {escape(result.end_date)} | {escape(result.execution_timing)}</p>
  <div class="grid">
    <div class="card"><strong>Cumulative return</strong><br />{_format_pct(result.metrics.cumulative_return)}</div>
    <div class="card"><strong>Annualized return</strong><br />{_format_pct(result.metrics.annualized_return)}</div>
    <div class="card"><strong>Max drawdown</strong><br />{_format_pct(result.metrics.max_drawdown)}</div>
    <div class="card"><strong>Sharpe ratio</strong><br />{result.metrics.sharpe_ratio:.4f}</div>
    <div class="card"><strong>Average turnover</strong><br />{result.metrics.average_turnover:.4f}</div>
    <div class="card"><strong>Total trades</strong><br />{result.metrics.total_trades}</div>
  </div>
  <h2>NAV Chart</h2>
  <img src="nav_chart.svg" alt="Backtest NAV chart" />
  <h2>Benchmark Comparison</h2>
  <table>
    <thead>
      <tr>
        <th>Benchmark</th>
        <th>Return</th>
        <th>Excess Return</th>
        <th>Max Drawdown</th>
        <th>Tracking Error</th>
        <th>Information Ratio</th>
      </tr>
    </thead>
    <tbody>
      {benchmark_rows}
    </tbody>
  </table>
  <h2>Data Health</h2>
  <table>
    <tbody>
      <tr><th>Weight source distribution</th><td>{escape(', '.join(f"{key}:{value}" for key, value in sorted(result.health.weight_source_counts.items())) or 'none')}</td></tr>
      <tr><th>Structured trigger count</th><td>{result.health.structured_trigger_count}</td></tr>
      <tr><th>Risk rule count</th><td>{result.health.risk_rule_count}</td></tr>
      <tr><th>Execution timing mismatches</th><td>{result.health.execution_timing_mismatch_count}</td></tr>
      <tr><th>Clamp hits</th><td>{result.health.clamp_hit_count}</td></tr>
      <tr><th>Missing price rows</th><td>{result.health.missing_price_rows}</td></tr>
      <tr><th>Unsupported trigger rules</th><td>{result.health.unsupported_trigger_count}</td></tr>
    </tbody>
  </table>
</body>
</html>
"""


class ETFAgentsBacktraderStrategy(bt.Strategy):
    params = dict(
        graph=None,
        tickers=None,
        rebalance_dates=None,
        execution_dates=None,
        trading_dates=None,
        top_k=3,
        execution_timing="same_close",
        cash_buffer_pct=0.0,
        force_refresh=False,
    )

    def __init__(self):
        self._processed_rebalances: set[str] = set()
        self._pending_rebalances: dict[str, dict[str, Any]] = {}
        self._data_by_ticker = {data._name: data for data in self.datas}
        self._active_signals: dict[str, dict[str, Any]] = {}
        self._active_target_weights: dict[str, float] = {}
        self._base_target_weights: dict[str, float] = {}
        self._triggered_rule_keys: set[str] = set()
        self._unsupported_rule_keys: set[str] = set()
        self.unsupported_trigger_count: int = 0
        self.rebalance_records: list[BacktraderRebalanceRecord] = []
        self.order_records: list[BacktraderOrderRecord] = []
        self.trade_records: list[BacktraderTradeRecord] = []
        self.nav_records: list[BacktraderNavRecord] = []
        self.position_records: list[BacktraderPositionRecord] = []

    def next_open(self):
        if self.p.execution_timing != "next_open":
            return
        current_date = self.datas[0].datetime.date(0).isoformat()
        payload = self._pending_rebalances.pop(current_date, None)
        if payload is None:
            return
        self._submit_target_orders(payload["weights"])
        self.rebalance_records.append(
            BacktraderRebalanceRecord(
                decision_date=payload["decision_date"],
                execution_date=current_date,
                selected_tickers=payload["selected_tickers"],
                weights=payload["weights"],
                ratings=payload["ratings"],
                turnover=payload["turnover"],
                signals=payload["signals"],
                reason=payload.get("reason", "scheduled"),
                trigger_events=list(payload.get("trigger_events", [])),
            )
        )

    def next(self):
        current_date = self.datas[0].datetime.date(0).isoformat()
        self._record_daily_nav(current_date)
        if current_date in self.p.rebalance_dates and current_date not in self._processed_rebalances:
            self._processed_rebalances.add(current_date)
            self._rebalance(current_date)
            return
        self._evaluate_dynamic_triggers(current_date)

    def notify_order(self, order):
        if order.status != order.Completed:
            return
        self.order_records.append(
            BacktraderOrderRecord(
                execution_date=_safe_iso_date(order.executed.dt),
                ticker=order.data._name,
                side="BUY" if order.isbuy() else "SELL",
                size=float(order.executed.size),
                price=float(order.executed.price),
                value=float(order.executed.value),
                commission=float(order.executed.comm),
            )
        )

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.trade_records.append(
            BacktraderTradeRecord(
                ticker=trade.data._name,
                open_date=_safe_iso_date(trade.dtopen),
                close_date=_safe_iso_date(trade.dtclose),
                pnl=float(trade.pnl),
                pnlcomm=float(trade.pnlcomm),
            )
        )

    def stop(self):
        final_date = self.datas[0].datetime.date(0).isoformat()
        if not self.nav_records or self.nav_records[-1].date != final_date:
            self._record_daily_nav(final_date)

    def _record_daily_nav(self, current_date: str) -> None:
        nav = float(self.broker.getvalue())
        cash = float(self.broker.getcash())
        gross_exposure = 0.0
        for data in self.datas:
            position = self.getposition(data)
            position_value = float(position.size) * float(data.close[0]) if position.size else 0.0
            gross_exposure += abs(position_value)
            self.position_records.append(
                BacktraderPositionRecord(
                    date=current_date,
                    ticker=data._name,
                    size=float(position.size),
                    value=position_value,
                    weight=(position_value / nav) if nav else 0.0,
                )
            )
        self.nav_records.append(
            BacktraderNavRecord(
                date=current_date,
                nav=nav,
                cash=cash,
                gross_exposure=gross_exposure,
            )
        )

    def _rebalance(self, decision_date: str) -> None:
        with backtest_context(decision_date):
            ranked_candidates = _analyze_candidate_pool(
                self.p.graph,
                self.p.tickers,
                decision_date,
                bool(self.p.force_refresh),
            )
        weights = _normalize_candidate_weights(ranked_candidates, self.p.top_k)
        weights = {
            ticker: weight * max(0.0, 1.0 - float(self.p.cash_buffer_pct))
            for ticker, weight in weights.items()
        }
        signals = {
            str(candidate["ticker"]): dict(candidate.get("backtest_signal", {}))
            for candidate in ranked_candidates[: max(1, self.p.top_k)]
        }
        ratings = {
            str(candidate["ticker"]): str(candidate.get("rating", ""))
            for candidate in ranked_candidates[: max(1, self.p.top_k)]
        }
        self._active_signals = signals
        self._base_target_weights = dict(weights)
        self._active_target_weights = dict(weights)
        self._triggered_rule_keys.clear()
        self._unsupported_rule_keys.clear()
        current_weights = self._current_weights()
        turnover = _portfolio_turnover(current_weights, weights)
        execution_date = self.p.execution_dates.get(decision_date, decision_date)
        record = {
            "decision_date": decision_date,
            "execution_date": execution_date,
            "selected_tickers": list(weights.keys()),
            "weights": {ticker: round(weight, 6) for ticker, weight in weights.items()},
            "ratings": ratings,
            "turnover": round(float(turnover), 6),
            "signals": list(signals.values()),
            "reason": "scheduled",
            "trigger_events": [],
        }
        if self.p.execution_timing == "next_open":
            self._pending_rebalances[execution_date] = record
            return
        self._submit_target_orders(record["weights"])
        self.rebalance_records.append(
            BacktraderRebalanceRecord(
                decision_date=decision_date,
                execution_date=execution_date,
                selected_tickers=record["selected_tickers"],
                weights=record["weights"],
                ratings=record["ratings"],
                turnover=record["turnover"],
                signals=record["signals"],
                reason=record["reason"],
                trigger_events=record["trigger_events"],
            )
        )

    def _evaluate_dynamic_triggers(self, current_date: str) -> None:
        if not self._active_signals:
            return

        updated_weights = dict(self._active_target_weights)
        trigger_events: list[dict[str, Any]] = []
        for ticker, signal in self._active_signals.items():
            data = self._data_by_ticker.get(ticker)
            if data is None:
                continue
            current_target = float(updated_weights.get(ticker, 0.0))
            base_target = float(self._base_target_weights.get(ticker, current_target))
            current_target, events = self._apply_signal_rules(
                current_date=current_date,
                ticker=ticker,
                signal=signal,
                data=data,
                current_target=current_target,
                base_target=base_target,
            )
            updated_weights[ticker] = current_target
            trigger_events.extend(events)

        if not trigger_events:
            return

        normalized_weights = self._normalize_target_weights(updated_weights)
        if self._weights_equal(normalized_weights, self._active_target_weights):
            return
        self._active_target_weights = dict(normalized_weights)
        current_weights = self._current_weights()
        turnover = _portfolio_turnover(current_weights, normalized_weights)
        execution_date = (
            current_date
            if self.p.execution_timing == "same_close"
            else self._next_trading_date(current_date)
        )
        record = {
            "decision_date": current_date,
            "execution_date": execution_date,
            "selected_tickers": [ticker for ticker, weight in normalized_weights.items() if weight > 1e-9],
            "weights": {ticker: round(weight, 6) for ticker, weight in normalized_weights.items()},
            "ratings": {
                ticker: str(signal.get("rating", ""))
                for ticker, signal in self._active_signals.items()
            },
            "turnover": round(float(turnover), 6),
            "signals": list(self._active_signals.values()),
            "reason": "trigger",
            "trigger_events": trigger_events,
        }
        if self.p.execution_timing == "next_open":
            self._pending_rebalances[execution_date] = record
            return
        self._submit_target_orders(record["weights"])
        self.rebalance_records.append(
            BacktraderRebalanceRecord(
                decision_date=record["decision_date"],
                execution_date=record["execution_date"],
                selected_tickers=record["selected_tickers"],
                weights=record["weights"],
                ratings=record["ratings"],
                turnover=record["turnover"],
                signals=record["signals"],
                reason=record["reason"],
                trigger_events=record["trigger_events"],
            )
        )

    def _current_weights(self) -> dict[str, float]:
        total_value = float(self.broker.getvalue())
        if total_value <= 0:
            return {}
        weights: dict[str, float] = {}
        for data in self.datas:
            position = self.getposition(data)
            if not position.size:
                continue
            weights[data._name] = float(position.size) * float(data.close[0]) / total_value
        return weights

    def _portfolio_value_at_open(self) -> float:
        total_value = float(self.broker.getcash())
        for data in self.datas:
            position = self.getposition(data)
            if not position.size:
                continue
            total_value += float(position.size) * float(data.open[0])
        return total_value

    def _submit_target_orders(self, weights: dict[str, float]) -> None:
        if self.p.execution_timing == "next_open":
            portfolio_value = self._portfolio_value_at_open()
            sell_orders: list[tuple[float, Any]] = []
            buy_orders: list[tuple[float, Any]] = []
            for data in self.datas:
                open_price = float(data.open[0])
                if open_price <= 0:
                    continue
                current_size = float(self.getposition(data).size)
                current_value = current_size * open_price
                target_value = portfolio_value * float(weights.get(data._name, 0.0))
                delta_size = (target_value - current_value) / open_price
                if abs(delta_size) <= 1e-12:
                    continue
                if delta_size < 0:
                    sell_orders.append((delta_size, data))
                else:
                    buy_orders.append((delta_size, data))
            for delta_size, data in sell_orders:
                self.sell(data=data, size=abs(delta_size))
            for delta_size, data in buy_orders:
                self.buy(data=data, size=delta_size)
            return
        order_kwargs = _execution_order_kwargs(self.p.execution_timing)
        for data in self.datas:
            self.order_target_percent(
                data=data,
                target=float(weights.get(data._name, 0.0)),
                **order_kwargs,
            )

    def _apply_signal_rules(
        self,
        *,
        current_date: str,
        ticker: str,
        signal: dict[str, Any],
        data: Any,
        current_target: float,
        base_target: float,
    ) -> tuple[float, list[dict[str, Any]]]:
        events: list[dict[str, Any]] = []
        for bucket in ("add_triggers", "reduce_triggers", "exit_triggers", "rebalance_triggers"):
            for trigger in signal.get(bucket, []):
                current_target, event = self._evaluate_trigger_rule(
                    current_date=current_date,
                    ticker=ticker,
                    data=data,
                    signal=signal,
                    bucket=bucket,
                    trigger=trigger,
                    current_target=current_target,
                    base_target=base_target,
                )
                if event is not None:
                    events.append(event)
        for rule in signal.get("risk_rules", []):
            current_target, event = self._evaluate_risk_rule(
                current_date=current_date,
                ticker=ticker,
                data=data,
                signal=signal,
                rule=rule,
                current_target=current_target,
                base_target=base_target,
            )
            if event is not None:
                events.append(event)
        return current_target, events

    def _evaluate_trigger_rule(
        self,
        *,
        current_date: str,
        ticker: str,
        data: Any,
        signal: dict[str, Any],
        bucket: str,
        trigger: dict[str, Any],
        current_target: float,
        base_target: float,
    ) -> tuple[float, dict[str, Any] | None]:
        rule_key = self._rule_key(signal, bucket, trigger)
        if rule_key in self._triggered_rule_keys:
            return current_target, None
        observed_value = self._metric_value(data, str(trigger.get("metric", "")), ticker)
        if observed_value is None:
            if rule_key not in self._unsupported_rule_keys:
                self._unsupported_rule_keys.add(rule_key)
                self.unsupported_trigger_count += 1
            return current_target, None
        if not self._compare_value(observed_value, trigger.get("op"), trigger.get("threshold")):
            return current_target, None
        new_target = self._apply_trigger_action(trigger, current_target, base_target)
        if new_target is None or abs(new_target - current_target) <= 1e-12:
            return current_target, None
        self._triggered_rule_keys.add(rule_key)
        return new_target, {
            "date": current_date,
            "ticker": ticker,
            "kind": bucket.replace("_triggers", ""),
            "metric": trigger.get("metric"),
            "op": trigger.get("op"),
            "threshold": trigger.get("threshold"),
            "observed_value": round(float(observed_value), 6),
            "action": trigger.get("action"),
            "resulting_target_pct": round(new_target * 100, 4),
            "note": str(trigger.get("note", "")),
        }

    def _evaluate_risk_rule(
        self,
        *,
        current_date: str,
        ticker: str,
        data: Any,
        signal: dict[str, Any],
        rule: dict[str, Any],
        current_target: float,
        base_target: float,
    ) -> tuple[float, dict[str, Any] | None]:
        rule_key = self._rule_key(signal, "risk_rules", rule)
        if rule_key in self._triggered_rule_keys:
            return current_target, None
        observed_value = self._metric_value(data, str(rule.get("metric", "")), ticker)
        if observed_value is None:
            if rule_key not in self._unsupported_rule_keys:
                self._unsupported_rule_keys.add(rule_key)
                self.unsupported_trigger_count += 1
            return current_target, None
        if not self._compare_value(observed_value, rule.get("op"), rule.get("threshold")):
            return current_target, None
        new_target = self._apply_risk_action(rule, current_target, base_target)
        if new_target is None or abs(new_target - current_target) <= 1e-12:
            return current_target, None
        self._triggered_rule_keys.add(rule_key)
        return new_target, {
            "date": current_date,
            "ticker": ticker,
            "kind": "risk",
            "metric": rule.get("metric"),
            "op": rule.get("op"),
            "threshold": rule.get("threshold"),
            "observed_value": round(float(observed_value), 6),
            "action": rule.get("action"),
            "resulting_target_pct": round(new_target * 100, 4),
            "note": str(rule.get("note", "")),
        }

    def _rule_key(self, signal: dict[str, Any], bucket: str, rule: dict[str, Any]) -> str:
        return json.dumps(
            {
                "ticker": signal.get("ticker"),
                "decision_date": signal.get("decision_date"),
                "bucket": bucket,
                "rule": rule,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def _metric_value(self, data: Any, metric: str, ticker: str) -> float | None:
        normalized = (metric or "").strip().lower()
        if not normalized:
            return None
        if normalized in {"close", "open", "high", "low", "volume"}:
            line = getattr(data, normalized, None)
            if line is None:
                return None
            return float(line[0])
        if normalized in {"weight", "weight_pct", "current_weight_pct"}:
            return float(self._current_weights().get(ticker, 0.0) * 100)
        if normalized == "pnl_pct":
            position = self.getposition(data)
            if not position.size or float(position.price) <= 0:
                return None
            return (float(data.close[0]) / float(position.price) - 1.0) * 100
        sma_match = re.fullmatch(r"(?:sma|ma)_(\d+)|close_(\d+)_sma", normalized)
        if sma_match:
            window = int(next(value for value in sma_match.groups() if value))
            closes = list(data.close.get(size=window))
            if len(closes) < window:
                return None
            return float(sum(closes) / window)
        volume_match = re.fullmatch(r"volume_ratio_(\d+)d?", normalized)
        if volume_match:
            window = int(volume_match.group(1))
            volumes = list(data.volume.get(size=window))
            if len(volumes) < window:
                return None
            average_volume = sum(volumes) / window
            if average_volume <= 0:
                return None
            return float(volumes[-1] / average_volume)
        return None

    def _compare_value(self, value: float, op: Any, threshold: Any) -> bool:
        if op == "in_range":
            if not isinstance(threshold, (tuple, list)) or len(threshold) != 2:
                return False
            low, high = float(threshold[0]), float(threshold[1])
            return min(low, high) <= value <= max(low, high)
        if isinstance(threshold, (tuple, list)):
            return False
        threshold_value = float(threshold)
        if op == "<":
            return value < threshold_value
        if op == "<=":
            return value <= threshold_value
        if op == ">":
            return value > threshold_value
        if op == ">=":
            return value >= threshold_value
        if op == "==":
            return abs(value - threshold_value) <= 1e-9
        return False

    def _apply_trigger_action(self, trigger: dict[str, Any], current_target: float, base_target: float) -> float | None:
        action = str(trigger.get("action", "")).strip().lower()
        target_override = trigger.get("target_weight_pct")
        target_fraction = float(target_override) / 100 if target_override is not None else None
        delta_value = trigger.get("delta_pct")
        delta_fraction = float(delta_value) / 100 if delta_value is not None else None
        if action == "add":
            if target_fraction is not None:
                return target_fraction
            if delta_fraction is not None:
                return current_target + delta_fraction
            return None
        if action == "reduce":
            if target_fraction is not None:
                return target_fraction
            if delta_fraction is not None:
                return max(0.0, current_target - delta_fraction)
            return None
        if action == "exit":
            return 0.0
        if action == "rebalance":
            if target_fraction is not None:
                return target_fraction
            return base_target
        return None

    def _apply_risk_action(self, rule: dict[str, Any], current_target: float, base_target: float) -> float | None:
        action = str(rule.get("action", "")).strip().lower()
        max_weight_pct = rule.get("max_weight_pct")
        min_weight_pct = rule.get("min_weight_pct")
        if action == "cap":
            if max_weight_pct is None:
                return None
            return min(current_target, float(max_weight_pct) / 100)
        if action == "floor":
            if min_weight_pct is None:
                return None
            return max(current_target, float(min_weight_pct) / 100)
        if action == "exit":
            return 0.0
        if action == "hold":
            return base_target
        return None

    def _normalize_target_weights(self, weights: dict[str, float]) -> dict[str, float]:
        sanitized = {
            ticker: max(0.0, float(weight))
            for ticker, weight in weights.items()
        }
        max_total = max(0.0, 1.0 - float(self.p.cash_buffer_pct))
        total_weight = sum(sanitized.values())
        if total_weight > max_total > 0:
            scale = max_total / total_weight
            sanitized = {
                ticker: weight * scale
                for ticker, weight in sanitized.items()
            }
        return sanitized

    def _weights_equal(self, left: dict[str, float], right: dict[str, float]) -> bool:
        universe = set(left) | set(right)
        return all(abs(float(left.get(ticker, 0.0)) - float(right.get(ticker, 0.0))) <= 1e-9 for ticker in universe)

    def _next_trading_date(self, current_date: str) -> str:
        trading_dates = list(self.p.trading_dates or [])
        if current_date not in trading_dates:
            return current_date
        index = trading_dates.index(current_date)
        if index + 1 < len(trading_dates):
            return trading_dates[index + 1]
        return current_date


def run_candidate_pool_backtest(
    graph,
    tickers: list[str],
    start_date: str,
    end_date: str,
    rebalance_interval_days: int = 21,
    top_k: int = 3,
    execution_timing: str = "same_close",
    initial_cash: float = 1_000_000.0,
    commission: float = 0.0,
    slippage_perc: float = 0.0,
    cash_buffer_pct: float = 0.0,
    benchmark_tickers: list[str] | None = None,
    force_refresh: bool = False,
    price_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> BacktraderBacktestResult:
    unique_tickers = list(dict.fromkeys(tickers))
    if not unique_tickers:
        raise ValueError("Backtest requires at least one ETF ticker.")

    timing = _validate_execution_timing(execution_timing)
    loader = price_loader or _load_price_frame
    loader_end_date = _extend_loader_end_date(end_date, timing)
    missing_price_rows = 0
    price_cache: dict[str, pd.DataFrame] = {}
    for ticker in unique_tickers:
        raw_frame = loader(ticker, start_date, loader_end_date)
        missing_price_rows += _count_missing_price_rows(raw_frame, timing)
        price_cache[ticker] = _normalize_price_frame(raw_frame, ticker)
    benchmarks = _normalize_benchmark_list(graph, unique_tickers, benchmark_tickers)
    benchmark_price_cache: dict[str, pd.DataFrame] = {}
    for benchmark in benchmarks:
        if benchmark == EQUAL_WEIGHT_BENCHMARK:
            continue
        if benchmark in price_cache:
            benchmark_price_cache[benchmark] = price_cache[benchmark]
            continue
        raw_frame = loader(benchmark, start_date, loader_end_date)
        missing_price_rows += _count_missing_price_rows(raw_frame, timing)
        benchmark_price_cache[benchmark] = _normalize_price_frame(raw_frame, benchmark)
    reference_dates = [
        ts.strftime("%Y-%m-%d")
        for ts in price_cache[unique_tickers[0]]
        .loc[price_cache[unique_tickers[0]]["Date"] <= pd.to_datetime(end_date), "Date"]
        .tolist()
    ]
    schedule = _build_rebalance_schedule(reference_dates, rebalance_interval_days)
    rebalance_dates = schedule[:-1]
    execution_dates = {
        decision_date: (
            decision_date
            if timing == "same_close"
            else next(
                (
                    candidate
                    for candidate in reference_dates
                    if candidate > decision_date
                ),
                decision_date,
            )
        )
        for decision_date in rebalance_dates
    }

    cerebro = bt.Cerebro(stdstats=False, cheat_on_open=(timing == "next_open"))
    cerebro.broker.setcash(float(initial_cash))
    cerebro.broker.addcommissioninfo(
        FractionalETFCommissionInfo(commission=float(commission))
    )
    if timing == "same_close":
        cerebro.broker.set_coc(True)
    if timing == "next_open":
        cerebro.broker.set_coo(True)
    if slippage_perc:
        cerebro.broker.set_slippage_perc(
            perc=float(slippage_perc),
            slip_open=True,
            slip_match=True,
            slip_out=False,
        )

    for ticker, df in price_cache.items():
        cerebro.adddata(_to_backtrader_feed(df, ticker), name=ticker)

    cerebro.addstrategy(
        ETFAgentsBacktraderStrategy,
        graph=graph,
        tickers=unique_tickers,
        rebalance_dates=set(rebalance_dates),
        execution_dates=execution_dates,
        trading_dates=reference_dates,
        top_k=max(1, int(top_k)),
        execution_timing=timing,
        cash_buffer_pct=float(cash_buffer_pct),
        force_refresh=bool(force_refresh),
    )
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    with backtest_health_context():
        results = cerebro.run()
        routing_health = get_backtest_health_state()
    strategy = results[0]

    analyzer_outputs = {
        "returns": dict(strategy.analyzers.returns.get_analysis() or {}),
        "drawdown": dict(strategy.analyzers.drawdown.get_analysis() or {}),
        "sharpe": dict(strategy.analyzers.sharpe.get_analysis() or {}),
        "trades": strategy.analyzers.trades.get_analysis() or {},
    }
    trade_count = _extract_trade_count(analyzer_outputs["trades"])
    metrics = _compute_metrics(
        strategy.nav_records,
        float(initial_cash),
        strategy.rebalance_records,
        trade_count,
    )
    nav_dates = [record.date for record in strategy.nav_records]
    benchmark_nav: list[BacktraderBenchmarkRecord] = []
    benchmark_metrics: list[BacktraderBenchmarkMetrics] = []
    for benchmark in benchmarks:
        records = _build_benchmark_nav_records(
            benchmark,
            nav_dates,
            float(initial_cash),
            price_cache if benchmark == EQUAL_WEIGHT_BENCHMARK else benchmark_price_cache,
        )
        benchmark_nav.extend(records)
        benchmark_metrics.append(
            _compute_benchmark_metrics(
                benchmark,
                records,
                strategy.nav_records,
                float(initial_cash),
            )
        )
    health = _build_health_metrics(
        timing,
        strategy.rebalance_records,
        missing_price_rows,
        strategy.unsupported_trigger_count,
        routing_health,
    )

    return BacktraderBacktestResult(
        tickers=unique_tickers,
        benchmarks=benchmarks,
        start_date=start_date,
        end_date=end_date,
        rebalance_interval_days=max(1, int(rebalance_interval_days)),
        top_k=max(1, int(top_k)),
        execution_timing=timing,
        initial_cash=float(initial_cash),
        commission=float(commission),
        slippage_perc=float(slippage_perc),
        cash_buffer_pct=float(cash_buffer_pct),
        metrics=metrics,
        rebalances=strategy.rebalance_records,
        nav=strategy.nav_records,
        positions=strategy.position_records,
        benchmark_nav=benchmark_nav,
        benchmark_metrics=benchmark_metrics,
        orders=strategy.order_records,
        trades=strategy.trade_records,
        analyzer_outputs=analyzer_outputs,
        health=health,
    )


def save_backtest_result(result: BacktraderBacktestResult, output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "tickers": result.tickers,
                "benchmarks": result.benchmarks,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "rebalance_interval_days": result.rebalance_interval_days,
                "top_k": result.top_k,
                "execution_timing": result.execution_timing,
                "initial_cash": result.initial_cash,
                "commission": result.commission,
                "slippage_perc": result.slippage_perc,
                "cash_buffer_pct": result.cash_buffer_pct,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (path / "metrics.json").write_text(
        json.dumps(
            {
                "metrics": asdict(result.metrics),
                "benchmark_metrics": [asdict(record) for record in result.benchmark_metrics],
                "health": asdict(result.health),
                "analyzer_outputs": result.analyzer_outputs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (path / "rebalances.json").write_text(
        json.dumps([asdict(record) for record in result.rebalances], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame(asdict(record) for record in result.nav).to_csv(path / "nav.csv", index=False)
    pd.DataFrame(asdict(record) for record in result.benchmark_nav).to_csv(path / "benchmarks.csv", index=False)
    pd.DataFrame(asdict(record) for record in result.positions).to_csv(path / "positions.csv", index=False)
    pd.DataFrame(asdict(record) for record in result.orders).to_csv(path / "orders.csv", index=False)
    pd.DataFrame(asdict(record) for record in result.trades).to_csv(path / "trades.csv", index=False)
    signals_dir = path / "signals"
    signals_dir.mkdir(exist_ok=True)
    for record in result.rebalances:
        (signals_dir / f"{record.decision_date}.json").write_text(
            json.dumps(record.signals, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (path / "summary.md").write_text(
        _build_backtest_summary_markdown(result),
        encoding="utf-8",
    )
    (path / "nav_chart.svg").write_text(
        _build_nav_chart_svg(result),
        encoding="utf-8",
    )
    (path / "report.html").write_text(
        _build_backtest_report_html(result),
        encoding="utf-8",
    )
    return path
