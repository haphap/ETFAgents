import copy
from contextvars import ContextVar
from typing import Any, Dict, Mapping

import etfagents.default_config as default_config

_DEFAULT_CONFIG = copy.deepcopy(default_config.DEFAULT_CONFIG)
_config_var: ContextVar[Dict[str, Any]] = ContextVar(
    "etfagents_config",
    default=copy.deepcopy(_DEFAULT_CONFIG),
)


def _merged_config(config: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    merged = copy.deepcopy(_DEFAULT_CONFIG)
    if config:
        for key, value in config.items():
            merged[key] = copy.deepcopy(value)
    return merged


def initialize_config() -> None:
    """Initialize the current execution context with default values."""
    _config_var.set(_merged_config())


def set_config(config: Mapping[str, Any] | None) -> None:
    """Set the configuration for the current execution context."""
    _config_var.set(_merged_config(config))


def get_config() -> Dict[str, Any]:
    """Return a deep-copied configuration for the current execution context."""
    return copy.deepcopy(_config_var.get())


initialize_config()
