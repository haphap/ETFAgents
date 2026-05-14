from __future__ import annotations

from dataclasses import asdict, dataclass
from io import StringIO
from datetime import timedelta
from typing import Callable

import pandas as pd

from etfagents.dataflows.config import backtest_context
from etfagents.dataflows.interface import route_to_vendor


@dataclass
class ReplayWindowResult:
    rebalance_date: str
    end_date: str
    selected_tickers: list[str]
    weights: dict[str, float]
    ratings: dict[str, str]
    period_return: float
    cumulative_nav: float
    turnover: float


@dataclass
class ReplayMetrics:
    periods: int
    cumulative_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    average_turnover: float


@dataclass
class ReplayResult:
    tickers: list[str]
    start_date: str
    end_date: str
    rebalance_interval_days: int
    top_k: int
    execution_timing: str
    metrics: ReplayMetrics
    windows: list[ReplayWindowResult]

    def to_dict(self) -> dict:
        return asdict(self)


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
        raise ValueError(f"No replay price history available for '{ticker}'.")
    return _normalize_price_frame(df, ticker)


def _normalize_price_frame(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    output = df.copy()
    output["Date"] = pd.to_datetime(output["Date"], errors="coerce")
    for column in ("Open", "Close"):
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce")
    output = output.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)
    if output.empty:
        raise ValueError(f"No usable replay price rows available for '{ticker}'.")
    return output


def _validate_execution_timing(execution_timing: str) -> str:
    normalized = (execution_timing or "same_close").strip().lower()
    if normalized not in {"same_close", "next_open", "next_close"}:
        raise ValueError(
            "execution_timing must be one of: same_close, next_open, next_close."
        )
    return normalized


def _price_at_execution(df: pd.DataFrame, date_str: str, execution_timing: str) -> float:
    timing = _validate_execution_timing(execution_timing)
    date_value = pd.to_datetime(date_str)
    if timing == "same_close":
        matches = df[df["Date"] <= date_value]
        if matches.empty:
            raise ValueError(f"No close price available on or before {date_str}.")
        return float(matches.iloc[-1]["Close"])

    if timing == "next_close":
        matches = df[df["Date"] > date_value]
        if matches.empty:
            raise ValueError(f"No next close price available after {date_str}.")
        return float(matches.iloc[0]["Close"])

    if "Open" not in df.columns:
        raise ValueError("Replay requested next_open execution but price frame has no Open column.")
    matches = df[df["Date"] > date_value].dropna(subset=["Open"])
    if matches.empty:
        raise ValueError(f"No next open price available after {date_str}.")
    return float(matches.iloc[0]["Open"])


def _extend_loader_end_date(end_date: str, execution_timing: str) -> str:
    timing = _validate_execution_timing(execution_timing)
    if timing == "same_close":
        return end_date
    return (pd.to_datetime(end_date) + timedelta(days=7)).strftime("%Y-%m-%d")


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


def _portfolio_turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    if not previous:
        return 0.0
    universe = set(previous) | set(current)
    return sum(abs(current.get(ticker, 0.0) - previous.get(ticker, 0.0)) for ticker in universe) / 2


def _build_rebalance_schedule(dates: list[str], rebalance_interval_days: int) -> list[str]:
    if len(dates) < 2:
        raise ValueError("Replay requires at least two trading dates.")
    step = max(1, int(rebalance_interval_days))
    schedule = [dates[index] for index in range(0, len(dates), step)]
    if schedule[-1] != dates[-1]:
        schedule.append(dates[-1])
    if len(schedule) < 2:
        raise ValueError("Replay schedule must contain at least one holding window.")
    return schedule


def _compute_replay_metrics(
    windows: list[ReplayWindowResult],
    start_date: str,
    end_date: str,
) -> ReplayMetrics:
    cumulative_return = windows[-1].cumulative_nav - 1 if windows else 0.0
    total_days = max((pd.to_datetime(end_date) - pd.to_datetime(start_date)).days, 1)
    years = total_days / 365.25
    annualized_return = (
        (1 + cumulative_return) ** (1 / years) - 1
        if years > 0 and 1 + cumulative_return > 0
        else 0.0
    )
    returns = pd.Series([window.period_return for window in windows], dtype="float64")
    annualized_volatility = (
        float(returns.std(ddof=0) * (252 / max(len(returns), 1)) ** 0.5)
        if not returns.empty
        else 0.0
    )
    nav_series = pd.Series([1.0, *[window.cumulative_nav for window in windows]], dtype="float64")
    running_peak = nav_series.cummax()
    drawdowns = nav_series / running_peak - 1
    max_drawdown = float(drawdowns.min()) if not drawdowns.empty else 0.0
    average_turnover = (
        float(pd.Series([window.turnover for window in windows[1:]], dtype="float64").mean())
        if len(windows) > 1
        else 0.0
    )
    return ReplayMetrics(
        periods=len(windows),
        cumulative_return=float(cumulative_return),
        annualized_return=float(annualized_return),
        annualized_volatility=annualized_volatility,
        max_drawdown=max_drawdown,
        average_turnover=average_turnover,
    )


def run_candidate_pool_replay(
    graph,
    tickers: list[str],
    start_date: str,
    end_date: str,
    rebalance_interval_days: int = 21,
    top_k: int = 3,
    execution_timing: str = "same_close",
    price_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> ReplayResult:
    unique_tickers = list(dict.fromkeys(tickers))
    if not unique_tickers:
        raise ValueError("Replay requires at least one ETF ticker.")

    timing = _validate_execution_timing(execution_timing)
    loader = price_loader or _load_price_frame
    loader_end_date = _extend_loader_end_date(end_date, timing)
    price_cache = {
        ticker: _normalize_price_frame(loader(ticker, start_date, loader_end_date), ticker)
        for ticker in unique_tickers
    }
    reference_dates = [
        ts.strftime("%Y-%m-%d")
        for ts in price_cache[unique_tickers[0]]
        .loc[price_cache[unique_tickers[0]]["Date"] <= pd.to_datetime(end_date), "Date"]
        .tolist()
    ]
    schedule = _build_rebalance_schedule(reference_dates, rebalance_interval_days)

    windows: list[ReplayWindowResult] = []
    previous_weights: dict[str, float] = {}
    cumulative_nav = 1.0

    for rebalance_date, window_end in zip(schedule[:-1], schedule[1:]):
        with backtest_context(rebalance_date):
            ranked_candidates = graph.analyze_candidate_pool(unique_tickers, rebalance_date)
        weights = _normalize_candidate_weights(ranked_candidates, top_k)
        selected_tickers = list(weights.keys())
        ratings = {
            str(candidate["ticker"]): str(candidate.get("rating", ""))
            for candidate in ranked_candidates[: max(1, top_k)]
        }
        period_return = 0.0
        for ticker, weight in weights.items():
            entry_price = _price_at_execution(price_cache[ticker], rebalance_date, timing)
            exit_price = _price_at_execution(price_cache[ticker], window_end, timing)
            period_return += weight * (exit_price / entry_price - 1)
        cumulative_nav *= 1 + period_return
        turnover = _portfolio_turnover(previous_weights, weights)
        windows.append(
            ReplayWindowResult(
                rebalance_date=rebalance_date,
                end_date=window_end,
                selected_tickers=selected_tickers,
                weights={ticker: round(weight, 6) for ticker, weight in weights.items()},
                ratings=ratings,
                period_return=round(float(period_return), 6),
                cumulative_nav=round(float(cumulative_nav), 6),
                turnover=round(float(turnover), 6),
            )
        )
        previous_weights = weights

    return ReplayResult(
        tickers=unique_tickers,
        start_date=start_date,
        end_date=end_date,
        rebalance_interval_days=max(1, int(rebalance_interval_days)),
        top_k=max(1, int(top_k)),
        execution_timing=timing,
        metrics=_compute_replay_metrics(windows, start_date, end_date),
        windows=windows,
    )
