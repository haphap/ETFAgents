from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from io import StringIO
import json
from math import sqrt
from pathlib import Path
from typing import Any, Callable

import backtrader as bt
import pandas as pd
from etfagents.dataflows.config import backtest_context
from etfagents.dataflows.interface import route_to_vendor


@dataclass
class BacktraderRebalanceRecord:
    decision_date: str
    execution_date: str
    selected_tickers: list[str]
    weights: dict[str, float]
    ratings: dict[str, str]
    turnover: float
    signals: list[dict[str, Any]]


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
class BacktraderBacktestResult:
    tickers: list[str]
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
    orders: list[BacktraderOrderRecord]
    trades: list[BacktraderTradeRecord]
    analyzer_outputs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def _compute_metrics(
    nav_records: list[BacktraderNavRecord],
    initial_cash: float,
    rebalances: list[BacktraderRebalanceRecord],
    trade_count: int,
) -> BacktraderMetrics:
    final_value = nav_records[-1].nav if nav_records else initial_cash
    cumulative_return = final_value / initial_cash - 1 if initial_cash else 0.0
    returns = pd.Series(
        [
            nav_records[index].nav / nav_records[index - 1].nav - 1
            for index in range(1, len(nav_records))
            if nav_records[index - 1].nav
        ],
        dtype="float64",
    )
    periods = max(len(returns), 1)
    annualized_return = (1 + cumulative_return) ** (252 / periods) - 1 if periods and final_value > 0 else 0.0
    annualized_volatility = float(returns.std(ddof=0) * sqrt(252)) if not returns.empty else 0.0
    sharpe_ratio = (
        float((returns.mean() / returns.std(ddof=0)) * sqrt(252))
        if len(returns) > 1 and returns.std(ddof=0) > 0
        else 0.0
    )
    nav_series = pd.Series([record.nav for record in nav_records], dtype="float64")
    running_peak = nav_series.cummax()
    drawdowns = nav_series / running_peak - 1 if not nav_series.empty else pd.Series(dtype="float64")
    max_drawdown = float(drawdowns.min()) if not drawdowns.empty else 0.0
    average_turnover = (
        float(pd.Series([record.turnover for record in rebalances[1:]], dtype="float64").mean())
        if len(rebalances) > 1
        else 0.0
    )
    return BacktraderMetrics(
        final_value=float(final_value),
        cumulative_return=float(cumulative_return),
        annualized_return=float(annualized_return),
        annualized_volatility=float(annualized_volatility),
        max_drawdown=max_drawdown,
        sharpe_ratio=float(sharpe_ratio),
        total_trades=int(trade_count),
        average_turnover=float(average_turnover),
    )


class ETFAgentsBacktraderStrategy(bt.Strategy):
    params = dict(
        graph=None,
        tickers=None,
        rebalance_dates=None,
        execution_dates=None,
        top_k=3,
        execution_timing="same_close",
        cash_buffer_pct=0.0,
    )

    def __init__(self):
        self._processed_rebalances: set[str] = set()
        self._pending_rebalances: dict[str, dict[str, Any]] = {}
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
            )
        )

    def next(self):
        current_date = self.datas[0].datetime.date(0).isoformat()
        self._record_daily_nav(current_date)
        if current_date not in self.p.rebalance_dates or current_date in self._processed_rebalances:
            return
        self._processed_rebalances.add(current_date)
        self._rebalance(current_date)

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
            ranked_candidates = self.p.graph.analyze_candidate_pool(self.p.tickers, decision_date)
        weights = _normalize_candidate_weights(ranked_candidates, self.p.top_k)
        weights = {
            ticker: weight * max(0.0, 1.0 - float(self.p.cash_buffer_pct))
            for ticker, weight in weights.items()
        }
        ratings = {
            str(candidate["ticker"]): str(candidate.get("rating", ""))
            for candidate in ranked_candidates[: max(1, self.p.top_k)]
        }
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
            "signals": [
                dict(candidate.get("backtest_signal", {}))
                for candidate in ranked_candidates[: max(1, self.p.top_k)]
            ],
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
    price_loader: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> BacktraderBacktestResult:
    unique_tickers = list(dict.fromkeys(tickers))
    if not unique_tickers:
        raise ValueError("Backtest requires at least one ETF ticker.")

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
        top_k=max(1, int(top_k)),
        execution_timing=timing,
        cash_buffer_pct=float(cash_buffer_pct),
    )
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    results = cerebro.run()
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

    return BacktraderBacktestResult(
        tickers=unique_tickers,
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
        orders=strategy.order_records,
        trades=strategy.trade_records,
        analyzer_outputs=analyzer_outputs,
    )


def save_backtest_result(result: BacktraderBacktestResult, output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "tickers": result.tickers,
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
    return path
