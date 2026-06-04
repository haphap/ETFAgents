# Architecture

ETFAgents is a **hybrid** system. Heavy, stateful logic stays in Python; the
orchestration / LLM / UX layer is TypeScript. The two halves talk over
**newline-delimited JSON-RPC 2.0 over stdio**.

```text
TypeScript front-end (ts/)         JSON-RPC / stdio        Python sidecar (etfagents/ + cli/)
─────────────────────────          ───────────────         ──────────────────────────────────
CLI (commander) + TUI (Ink)                                bridge/    (JSON-RPC server + handlers)
LangGraph.js full pipeline:                                agents/ · graph/ · dataflows/
  6 analysts → bull/bear debate ⇄  newline JSON  ⇄         backtest/ (Backtrader) · paper_trading/
  → research mgr → trader                                  llm_clients/ · cache_manager · watchlist
  → risk debate → PM → memory                              persistence: SQLite checkpoint + results dir
LLM factory · backtest signal extraction
```

## Why hybrid?

- **Python owns the data and execution layer**: vendor-routed market/financial
  data (Tushare / akshare / yfinance / FRED / Brave), the Backtrader engine, the
  paper-trading engine, and the analysis-memory store.
- **TypeScript owns orchestration and UX**: the LangGraph.js pipeline, the
  OpenAI-compatible LLM factory, the `commander` CLI, and the Ink TUI.

## The bridge

The front-end spawns the Python sidecar as a subprocess
(`python -m etfagents.bridge`) and exchanges one JSON object per line:

- Interpreter discovery: `ETFAGENTS_PYTHON` → `<repo>/.venv/bin/python` → fail loud.
- Every tool/data call crosses the boundary as **strings / JSON** — no
  cross-language DataFrame transfer.
- `BridgeClient` (TS) issues requests with unique ids; the Python server
  processes them serially. See **[Bridge Protocol](Bridge-Protocol)** for the
  method list.

## Repository layout

```text
etfagents/        # Python sidecar
  bridge/         #   JSON-RPC server + handlers (tools/config/cache/paper/backtest/memory/watchlist)
  agents/         #   analyst / researcher / trader / risk / manager roles + utils
  graph/          #   LangGraph orchestration, checkpointing, replay, signal processing
  dataflows/      #   vendor integrations + route_to_vendor()
  llm_clients/    #   provider normalization (OpenAI / Anthropic / Google / ...)
  backtest/       #   Backtrader engine + result artifacts
  paper_trading/  #   A-share ETF paper trading
cli/              # Typer/Rich Python CLI (etfagents console script)
ts/src/
  bridge/         #   BridgeClient + typed RPC wrappers
  llm/            #   OpenAI-compatible LLM factory
  agents/         #   nodes · helpers · prompts · schemas · state
  graph/          #   full_graph LangGraph.js assembly
  cli/commands/   #   analyze / analyze-pool / backtest / paper / detail / cache / ...
  tui/            #   Ink TUI shell + model / runner / services / screens
```

## Design principles

- Tool-call boundaries are strings/JSON only.
- Reuse repository helpers (`create_llm_client()`, `route_to_vendor()`,
  localization helpers, `copy.deepcopy(DEFAULT_CONFIG)` before mutating config).
- Preserve full ticker symbols and exchange suffixes (`510300.SH`, `7203.T`).
