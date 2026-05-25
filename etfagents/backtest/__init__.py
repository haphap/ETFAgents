"""ETFAgents backtesting package.

All public names are lazily imported via PEP 562 ``__getattr__`` so that
``import etfagents.backtest`` no longer triggers heavy transitive dependencies
(backtrader, pandas, etc.) at package load time.
"""

from __future__ import annotations

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # signals
    "BacktestSignal": (".signals", "BacktestSignal"),
    "build_candidate_backtest_signal": (".signals", "build_candidate_backtest_signal"),
    "build_portfolio_backtest_signal": (".signals", "build_portfolio_backtest_signal"),
    "build_state_backtest_signal": (".signals", "build_state_backtest_signal"),
    "build_trader_backtest_signal": (".signals", "build_trader_backtest_signal"),
    # backtrader_engine
    "BacktestHealthMetrics": (".backtrader_engine", "BacktestHealthMetrics"),
    "BacktraderBacktestResult": (".backtrader_engine", "BacktraderBacktestResult"),
    "BacktraderBenchmarkMetrics": (".backtrader_engine", "BacktraderBenchmarkMetrics"),
    "BacktraderBenchmarkRecord": (".backtrader_engine", "BacktraderBenchmarkRecord"),
    "BacktraderMetrics": (".backtrader_engine", "BacktraderMetrics"),
    "BacktraderNavRecord": (".backtrader_engine", "BacktraderNavRecord"),
    "BacktraderOrderRecord": (".backtrader_engine", "BacktraderOrderRecord"),
    "BacktraderPositionRecord": (".backtrader_engine", "BacktraderPositionRecord"),
    "BacktraderRebalanceRecord": (".backtrader_engine", "BacktraderRebalanceRecord"),
    "BacktraderTradeRecord": (".backtrader_engine", "BacktraderTradeRecord"),
    "EQUAL_WEIGHT_BENCHMARK": (".backtrader_engine", "EQUAL_WEIGHT_BENCHMARK"),
    "run_candidate_pool_backtest": (".backtrader_engine", "run_candidate_pool_backtest"),
    "save_backtest_result": (".backtrader_engine", "save_backtest_result"),
    # cache
    "BacktestSignalStore": (".cache", "BacktestSignalStore"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path, __package__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
