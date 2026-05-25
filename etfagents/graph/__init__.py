"""ETFAgents graph orchestration.

All public names are lazily imported via PEP 562 ``__getattr__`` so that
``import etfagents.graph`` no longer triggers heavy transitive dependencies
(langgraph, langchain_core, etc.) at package load time.
"""

from __future__ import annotations

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "EtfAgentsGraph": (".etf_graph", "EtfAgentsGraph"),
    "TradingAgentsGraph": (".trading_graph", "TradingAgentsGraph"),
    "ConditionalLogic": (".conditional_logic", "ConditionalLogic"),
    "GraphSetup": (".setup", "GraphSetup"),
    "Propagator": (".propagation", "Propagator"),
    "Reflector": (".reflection", "Reflector"),
    "SignalProcessor": (".signal_processing", "SignalProcessor"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path, __package__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
