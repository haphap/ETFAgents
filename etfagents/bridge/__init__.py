"""ETFAgents JSON-RPC sidecar.

A Python process exposed over stdio so a TypeScript CLI can drive the existing
Python codebase as a black box. The bridge does not modify any code outside of
``etfagents/bridge/`` — it only re-exports the existing Python surface as
JSON-RPC methods.

Run as ``python -m etfagents.bridge``. Protocol details: see ``docs/bridge.md``.
"""

from __future__ import annotations

__all__ = ["serve"]


def serve() -> None:
    """Entry point used by ``__main__`` and integration tests."""
    # Imported lazily so simple ``import etfagents.bridge`` stays cheap
    # (LangChain/Pandas only loaded when the server actually starts).
    from .server import run_stdio_server

    run_stdio_server()
