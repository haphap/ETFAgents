"""Paper trading simulation package.

All public names are lazily imported via PEP 562 ``__getattr__`` so that
``import etfagents.paper_trading`` no longer triggers heavy transitive
dependencies at package load time.
"""

from __future__ import annotations

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "PaperTradingEngine": (".engine", "PaperTradingEngine"),
    "calc_commission": (".rules", "calc_commission"),
    "calc_stamp_duty": (".rules", "calc_stamp_duty"),
    "COMMISSION_RATE": (".rules", "COMMISSION_RATE"),
    "estimate_trade_cost": (".rules", "estimate_trade_cost"),
    "get_t1_available": (".rules", "get_t1_available"),
    "LOT_SIZE": (".rules", "LOT_SIZE"),
    "MIN_COMMISSION": (".rules", "MIN_COMMISSION"),
    "STAMP_DUTY_RATE": (".rules", "STAMP_DUTY_RATE"),
    "validate_quantity": (".rules", "validate_quantity"),
}

# suggest_order_from_signal is defined locally — not lazy
_LOCAL_NAMES = {"suggest_order_from_signal"}

__all__ = list(_LAZY_IMPORTS.keys()) + list(_LOCAL_NAMES)


def suggest_order_from_signal(
    ticker: str,
    state: dict,
    user_id: str | None = None,
    db_path=None,
    config: dict | None = None,
) -> dict | None:
    """Module-level convenience wrapper for PaperTradingEngine.suggest_order_from_signal."""
    from pathlib import Path

    from etfagents.paper_trading.engine import PaperTradingEngine

    engine = PaperTradingEngine(db_path=db_path, config=config)
    return engine.suggest_order_from_signal(ticker, state, user_id=user_id)


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path, __package__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
