"""Stream-state merging utilities.

Extracted from cli.main so cli.tui.services can merge LangGraph chunks
without triggering the full CLI module load.
"""

from __future__ import annotations

import copy
from typing import Any

from etfagents.agents.utils.state_keys import (
    CANONICAL_TO_LEGACY_STATE_KEYS,
    canonical_state_key,
    get_state_value,
)

STREAM_STATE_KEYS: set[str] = {
    *CANONICAL_TO_LEGACY_STATE_KEYS.keys(),
    *(
        legacy
        for legacy_keys in CANONICAL_TO_LEGACY_STATE_KEYS.values()
        for legacy in legacy_keys
    ),
    "investment_debate_state",
    "risk_debate_state",
    "trader_backtest_signal",
    "portfolio_backtest_signal",
    "backtest_signal",
    "analysis_memory_entry",
}


def _looks_like_state_delta(value: object) -> bool:
    return isinstance(value, dict) and any(
        canonical_state_key(str(key)) in STREAM_STATE_KEYS or str(key) in STREAM_STATE_KEYS
        for key in value
    )


def iter_stream_state_updates(update: dict) -> Any:
    """Yield the top-level update and any nested node-output dicts."""
    if not isinstance(update, dict):
        return
    yield update
    for value in update.values():
        if _looks_like_state_delta(value):
            yield value


def chunk_state_value(chunk: dict, key: str, default: Any = None) -> Any:
    """Extract a state value from a stream chunk, checking nested node outputs."""
    for update in iter_stream_state_updates(chunk):
        value = get_state_value(update, key, None)
        if value not in (None, ""):
            return value
    return default


def merge_stream_state(
    accumulated: dict, update: dict, *, filter_state_keys: bool = True
) -> dict:
    """Keep non-empty values from earlier stream chunks for final report output."""
    if not isinstance(update, dict):
        return accumulated

    for state_update in iter_stream_state_updates(update):
        for raw_key, value in state_update.items():
            key = canonical_state_key(raw_key)
            if value in (None, ""):
                continue
            if filter_state_keys and key not in STREAM_STATE_KEYS:
                continue
            if isinstance(value, dict) and isinstance(accumulated.get(key), dict):
                merge_stream_state(
                    accumulated[key],
                    value,
                    filter_state_keys=False,
                )
                continue
            accumulated[key] = copy.deepcopy(value)
    return accumulated
