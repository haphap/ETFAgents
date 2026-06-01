"""``memory.*`` JSON-RPC handlers for analysis-memory write-back.

The TypeScript Memory Writer node (graph end) sends a state payload here; we
build and persist the analysis entry with the existing Python
``AnalysisMemoryStore`` so memory write-back stays single-sourced.
"""

from __future__ import annotations

import copy
from typing import Any

from ..protocol import INVALID_PARAMS, RpcError
from ..registry import method

_DEFAULT_ANALYSTS = (
    "market_flow",
    "catalyst_sentiment",
    "macro_regime",
    "meso_commodity",
    "holdings_industry",
    "top_holdings",
)


@method("memory.append_analysis")
def memory_append_analysis(params: dict[str, Any]) -> dict[str, Any]:
    state = params.get("state")
    if not isinstance(state, dict):
        raise RpcError(INVALID_PARAMS, "'state' must be an object")
    # Only default when the key is absent / null; an explicit empty list means
    # "no analysts selected" and must be preserved so the stored entry's
    # config hash matches what the graph actually ran.
    selected = params.get("selected_analysts")
    if selected is None:
        selected = list(_DEFAULT_ANALYSTS)
    elif not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
        raise RpcError(INVALID_PARAMS, "'selected_analysts' must be a list of strings")

    from etfagents.agents.utils.analysis_memory import (
        AnalysisMemoryStore,
        build_analysis_memory_entry,
    )
    from etfagents.default_config import DEFAULT_CONFIG

    config = copy.deepcopy(DEFAULT_CONFIG)
    overrides = params.get("config")
    if isinstance(overrides, dict):
        config.update(overrides)

    store = AnalysisMemoryStore(config, selected)
    if not store.is_enabled():
        return {"written": False, "entry": {}}

    entry = build_analysis_memory_entry(state, config=config, selected_analysts=selected)
    store.append_analysis(entry)
    return {"written": True, "entry": entry.to_dict()}


@method("memory.build_context")
def memory_build_context(params: dict[str, Any]) -> dict[str, Any]:
    """Build the per-role memory context bundle (continuity / lesson / method)
    that the TS graph injects into its initial state — the read side of memory,
    mirroring Python's MemoryContextBuilder.build()."""
    ticker = params.get("ticker")
    trade_date = params.get("trade_date")
    if not isinstance(ticker, str) or not isinstance(trade_date, str):
        raise RpcError(INVALID_PARAMS, "'ticker' and 'trade_date' must be strings")
    selected = params.get("selected_analysts")
    if selected is None:
        selected = list(_DEFAULT_ANALYSTS)
    elif not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
        raise RpcError(INVALID_PARAMS, "'selected_analysts' must be a list of strings")

    from etfagents.agents.utils.analysis_memory import (
        AnalysisMemoryStore,
        MemoryContextBuilder,
    )
    from etfagents.default_config import DEFAULT_CONFIG

    config = copy.deepcopy(DEFAULT_CONFIG)
    overrides = params.get("config")
    if isinstance(overrides, dict):
        config.update(overrides)

    store = AnalysisMemoryStore(config, selected)
    bundle = MemoryContextBuilder(store, config, selected).build(ticker, trade_date)
    return {
        "continuity_context": bundle.continuity_context,
        "lesson_context": bundle.lesson_context,
        "method_context": bundle.method_context,
        "past_context": bundle.past_context,
    }
