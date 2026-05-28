"""``cache.*`` JSON-RPC handlers wrapping ``etfagents.cache_manager.CacheManager``."""

from __future__ import annotations

from typing import Any

from ..protocol import INVALID_PARAMS, RpcError
from ..registry import method


_VALID_CATEGORIES = {"api", "signals", "snapshots", "checkpoints", "all"}


def _manager():
    # Imported lazily so importing the bridge doesn't import the cache layer.
    from etfagents.cache_manager import CacheManager
    from etfagents.dataflows.config import get_config

    return CacheManager(get_config())


@method("cache.stats")
def cache_stats(_params: dict[str, Any]) -> dict[str, Any]:
    return _manager().stats()


@method("cache.cleanup")
def cache_cleanup(params: dict[str, Any]) -> dict[str, Any]:
    days = params.get("days")
    category = params.get("category", "all")
    if not isinstance(days, int) or days < 0:
        raise RpcError(INVALID_PARAMS, "'days' must be a non-negative integer")
    if category not in _VALID_CATEGORIES:
        raise RpcError(
            INVALID_PARAMS,
            f"'category' must be one of {sorted(_VALID_CATEGORIES)}",
        )
    return _manager().cleanup(days, category)


@method("cache.clear")
def cache_clear(params: dict[str, Any]) -> dict[str, Any]:
    category = params.get("category")
    if category not in _VALID_CATEGORIES:
        raise RpcError(
            INVALID_PARAMS,
            f"'category' must be one of {sorted(_VALID_CATEGORIES)}",
        )
    return _manager().clear(category)


@method("cache.details")
def cache_details(params: dict[str, Any]) -> dict[str, Any]:
    category = params.get("category")
    page = params.get("page", 1)
    page_size = params.get("page_size", 20)
    if category not in _VALID_CATEGORIES - {"all"}:
        raise RpcError(
            INVALID_PARAMS,
            "'category' must be one of api/signals/snapshots/checkpoints",
        )
    if not isinstance(page, int) or page < 1:
        raise RpcError(INVALID_PARAMS, "'page' must be a positive integer")
    if not isinstance(page_size, int) or page_size < 1:
        raise RpcError(INVALID_PARAMS, "'page_size' must be a positive integer")
    return _manager().details(category, page=page, page_size=page_size)
