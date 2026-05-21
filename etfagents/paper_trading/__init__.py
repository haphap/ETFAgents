"""Paper trading simulation package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from etfagents.paper_trading.engine import PaperTradingEngine
from etfagents.paper_trading.rules import (
    calc_commission,
    calc_stamp_duty,
    COMMISSION_RATE,
    estimate_trade_cost,
    get_t1_available,
    LOT_SIZE,
    MIN_COMMISSION,
    STAMP_DUTY_RATE,
    validate_quantity,
)


def suggest_order_from_signal(
    ticker: str,
    state: dict,
    user_id: str | None = None,
    db_path: Path | None = None,
    config: dict | None = None,
) -> dict | None:
    """Module-level convenience wrapper for PaperTradingEngine.suggest_order_from_signal."""
    engine = PaperTradingEngine(db_path=db_path, config=config)
    return engine.suggest_order_from_signal(ticker, state, user_id=user_id)


__all__ = [
    "PaperTradingEngine",
    "suggest_order_from_signal",
    "calc_commission",
    "calc_stamp_duty",
    "COMMISSION_RATE",
    "estimate_trade_cost",
    "get_t1_available",
    "LOT_SIZE",
    "MIN_COMMISSION",
    "STAMP_DUTY_RATE",
    "validate_quantity",
]
