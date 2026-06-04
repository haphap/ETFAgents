"""``memory.*`` JSON-RPC handlers for analysis-memory write-back.

The TypeScript Memory Writer node (graph end) sends a state payload here; we
build and persist the analysis entry with the existing Python
``AnalysisMemoryStore`` so memory write-back stays single-sourced.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
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


def _write_signal_sidecars(state: dict[str, Any], config: dict[str, Any]) -> None:
    signals = state.get("agent_signals")
    if not isinstance(signals, dict) or not signals:
        return
    ticker = str(state.get("asset_of_interest") or "").strip()
    trade_date = str(state.get("trade_date") or "").strip()
    results_dir = str(config.get("results_dir") or "").strip()
    if not ticker or not trade_date or not results_dir:
        return
    report_dir = Path(results_dir) / ticker / trade_date
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "agent_signals.json").write_text(
        json.dumps(signals, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summaries = {
        source: signal.get("decision_summary")
        for source, signal in signals.items()
        if isinstance(signal, dict) and signal.get("decision_summary")
    }
    if summaries:
        (report_dir / "decision_signal_summaries.json").write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
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
    _write_signal_sidecars(state, config)
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
