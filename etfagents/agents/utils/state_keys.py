from __future__ import annotations

from typing import Any, Mapping


CANONICAL_TO_LEGACY_STATE_KEYS: dict[str, tuple[str, ...]] = {
    "asset_of_interest": ("company_of_interest",),
    "market_flow_report": ("market_report", "etf_flow_report", "research_report"),
    "catalyst_sentiment_report": ("sentiment_report",),
    "macro_regime_report": ("news_report",),
    "meso_commodity_report": ("etf_structure_report", "fundamentals_report"),
    "holdings_industry_report": ("etf_macro_report", "stock_report"),
    "top_holdings_report": ("etf_stock_research_report",),
    "research_allocation_plan": ("investment_plan",),
    "trader_allocation_plan": ("trader_investment_plan",),
    "final_allocation_decision": ("final_trade_decision",),
}

LEGACY_TO_CANONICAL_STATE_KEYS: dict[str, str] = {
    legacy: canonical
    for canonical, legacy_keys in CANONICAL_TO_LEGACY_STATE_KEYS.items()
    for legacy in legacy_keys
}


def canonical_state_key(key: str) -> str:
    return LEGACY_TO_CANONICAL_STATE_KEYS.get(key, key)


def get_state_value(state: Mapping[str, Any], key: str, default: Any = None) -> Any:
    canonical = canonical_state_key(key)
    candidates = (canonical, *CANONICAL_TO_LEGACY_STATE_KEYS.get(canonical, ()))
    empty_seen = False
    for candidate in candidates:
        if candidate not in state:
            continue
        value = state[candidate]
        if value not in (None, ""):
            return value
        empty_seen = True
    return "" if empty_seen and default is None else default


def get_asset_symbol(state: Mapping[str, Any], default: str = "unknown") -> str:
    return str(get_state_value(state, "asset_of_interest", default) or default)


def with_state_aliases(updates: Mapping[str, Any]) -> dict[str, Any]:
    mirrored: dict[str, Any] = {}
    for raw_key, value in updates.items():
        canonical = canonical_state_key(raw_key)
        mirrored[canonical] = value
        for legacy in CANONICAL_TO_LEGACY_STATE_KEYS.get(canonical, ()):
            mirrored[legacy] = value
    return mirrored
