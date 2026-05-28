"""``tools.*`` JSON-RPC handlers.

Auto-discover every LangChain ``@tool``-decorated function in the codebase
and expose:

* ``tools.list``   → metadata (name, description, JSON Schema for args)
* ``tools.call``   → invoke a tool with ``{name, args, context}``

The handler applies a backtest date-bounds context per call so the bridge
caller (TS) can pin every tool invocation to an ``as_of_date``. This reuses
the existing ``etfagents.dataflows.config.backtest_context`` context manager,
so the underlying ``route_to_vendor`` clamping logic stays untouched.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any, Dict, Iterable

from langchain_core.tools import BaseTool

from ..protocol import (
    DATA_VENDOR_UNAVAILABLE,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    TOOL_EXECUTION_ERROR,
    RpcError,
)
from ..registry import method

# Modules to scan for @tool-decorated functions. Adding a new tool module to
# the codebase requires adding its dotted path here.
_TOOL_MODULES: tuple[str, ...] = (
    "etfagents.agents.utils.core_stock_tools",
    "etfagents.agents.utils.technical_indicators_tools",
    "etfagents.agents.utils.fundamental_data_tools",
    "etfagents.agents.utils.news_data_tools",
    "etfagents.agents.utils.research_report_tools",
    "etfagents.agents.utils.etf_data_tools",
)


def _iter_module_tools(module_path: str) -> Iterable[BaseTool]:
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover - import failure logged elsewhere
        import logging

        logging.getLogger("etfagents.bridge").warning(
            "Failed to import tool module %s: %s", module_path, exc
        )
        return ()

    seen_ids: set[int] = set()
    found: list[BaseTool] = []
    for value in vars(module).values():
        if isinstance(value, BaseTool) and id(value) not in seen_ids:
            seen_ids.add(id(value))
            found.append(value)
    return found


def _build_registry() -> Dict[str, BaseTool]:
    registry: Dict[str, BaseTool] = {}
    for module_path in _TOOL_MODULES:
        for tool_obj in _iter_module_tools(module_path):
            # First module wins on duplicates (etf_data_tools re-exports a few)
            registry.setdefault(tool_obj.name, tool_obj)
    return registry


# Built once at module import. The bridge runs as a long-lived process, so we
# pay the LangChain import cost exactly once and serve cheap dict lookups.
_TOOLS: Dict[str, BaseTool] = _build_registry()


def _tool_metadata(tool_obj: BaseTool) -> dict[str, Any]:
    schema_cls = getattr(tool_obj, "args_schema", None)
    if schema_cls is not None and hasattr(schema_cls, "model_json_schema"):
        json_schema = schema_cls.model_json_schema()
    elif schema_cls is not None and hasattr(schema_cls, "schema"):
        # Pydantic v1 fallback (project pins v2 today)
        json_schema = schema_cls.schema()
    else:
        json_schema = {"type": "object", "properties": {}}
    return {
        "name": tool_obj.name,
        "description": (tool_obj.description or "").strip(),
        "args_schema": json_schema,
    }


@method("tools.list")
def tools_list(_params: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all available tools sorted by name."""
    return [_tool_metadata(_TOOLS[name]) for name in sorted(_TOOLS)]


@method("tools.call")
def tools_call(params: dict[str, Any]) -> dict[str, Any]:
    """Invoke a tool by name. ``params`` shape::

        {
          "name": "get_news",
          "args": {"ticker": "510300.SH", "start_date": "...", "end_date": "..."},
          "context": {"as_of_date": null, "mode": "live"}   // optional
        }

    Returns ``{"text": <tool output as str>}``.
    """
    name = params.get("name")
    if not isinstance(name, str) or not name:
        raise RpcError(INVALID_PARAMS, "tools.call requires a non-empty 'name'")

    tool_obj = _TOOLS.get(name)
    if tool_obj is None:
        raise RpcError(METHOD_NOT_FOUND, f"No registered tool named {name!r}")

    args = params.get("args", {}) or {}
    if not isinstance(args, dict):
        raise RpcError(INVALID_PARAMS, "'args' must be an object")

    context = params.get("context") or {}
    if not isinstance(context, dict):
        raise RpcError(INVALID_PARAMS, "'context' must be an object")
    as_of_date = context.get("as_of_date")
    mode = context.get("mode") or ("backtest" if as_of_date else "live")

    # Lazy import — keeps top-level import cheap and avoids a circular path.
    from etfagents.dataflows.config import backtest_context
    from etfagents.dataflows.exceptions import (
        DataVendorUnavailable,
        MissingEtfHoldings,
    )

    try:
        with backtest_context(as_of_date, mode=mode):
            result = tool_obj.invoke(args)
    except DataVendorUnavailable as exc:
        raise RpcError(DATA_VENDOR_UNAVAILABLE, str(exc)) from exc
    except MissingEtfHoldings as exc:
        raise RpcError(
            TOOL_EXECUTION_ERROR,
            str(exc),
            {"kind": "MissingEtfHoldings"},
        ) from exc
    except RpcError:
        raise
    except Exception as exc:
        raise RpcError(
            TOOL_EXECUTION_ERROR,
            f"{type(exc).__name__}: {exc}",
        ) from exc

    if not isinstance(result, str):
        # Every existing @tool returns a str; future tools could break this.
        # Coerce defensively rather than dropping the payload.
        result = str(result)
    return {"text": result}
