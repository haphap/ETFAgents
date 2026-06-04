"""``watchlist.*`` JSON-RPC handlers."""

from __future__ import annotations

from typing import Any

from ..protocol import INVALID_PARAMS, RpcError
from ..registry import method


@method("watchlist.list")
def watchlist_list(params: dict[str, Any]) -> list[dict[str, Any]]:
    group = params.get("group", "default")
    db_path = params.get("db_path")
    if group is not None and not isinstance(group, str):
        raise RpcError(INVALID_PARAMS, "'group' must be a string")
    if db_path is not None and not isinstance(db_path, str):
        raise RpcError(INVALID_PARAMS, "'db_path' must be a string")

    from pathlib import Path

    from etfagents.watchlist import WatchlistManager

    manager = WatchlistManager(Path(db_path).expanduser() if db_path else None)
    return manager.list_tickers(group=group)
