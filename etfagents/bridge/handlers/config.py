"""``config.*`` JSON-RPC handlers.

Wraps ``etfagents.dataflows.config`` so the TS side can read ``DEFAULT_CONFIG``
once at startup and push back any merged overrides before issuing tool calls.
"""

from __future__ import annotations

import copy
from typing import Any

from ..protocol import CONFIG_ERROR, INVALID_PARAMS, RpcError
from ..registry import method


@method("config.default")
def config_default(_params: dict[str, Any]) -> dict[str, Any]:
    """Return ``etfagents.default_config.DEFAULT_CONFIG`` (deep-copied)."""
    from etfagents.default_config import DEFAULT_CONFIG

    return copy.deepcopy(DEFAULT_CONFIG)


@method("config.get")
def config_get(_params: dict[str, Any]) -> dict[str, Any]:
    """Return the active runtime config for this bridge process."""
    from etfagents.dataflows.config import get_config

    return get_config()


@method("config.set")
def config_set(params: dict[str, Any]) -> dict[str, Any]:
    """Replace the active runtime config. Shape::

        { "config": { ... } }

    Returns the new active config (post-merge with defaults).
    """
    cfg = params.get("config")
    if cfg is None:
        raise RpcError(INVALID_PARAMS, "config.set requires a 'config' object")
    if not isinstance(cfg, dict):
        raise RpcError(INVALID_PARAMS, "'config' must be an object")

    from etfagents.dataflows.config import get_config, set_config

    try:
        set_config(cfg)
    except Exception as exc:
        raise RpcError(CONFIG_ERROR, f"{type(exc).__name__}: {exc}") from exc
    return get_config()
