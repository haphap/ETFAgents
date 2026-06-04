# 📊 ETFAgents Wiki

A multi-agent ETF research & allocation framework built on LangGraph, with a
hybrid **Python sidecar + TypeScript front-end** architecture connected by
**newline-delimited JSON-RPC over stdio**.

> ⚠️ ETFAgents is for research and experimentation only — **not financial advice.**

## Pages

- **[Architecture](Architecture)** — hybrid sidecar/front-end design and the JSON-RPC bridge.
- **[Agent Pipeline](Agent-Pipeline)** — the full LangGraph pipeline: 6 analysts → debate → trader → risk → portfolio manager → memory.
- **[CLI & TUI](CLI-and-TUI)** — command reference and the Ink terminal dashboard.
- **[Bridge Protocol](Bridge-Protocol)** — the JSON-RPC methods the front-end calls.
- **[Configuration](Configuration)** — environment variables, config keys, and memory modes.
- **[Development](Development)** — setup, the verification matrix, and conventions.

## What it does

ETFAgents coordinates a layered team of agents to produce a **structured
allocation decision** for an ETF (A-share and global broad-based):

```
6 analysts → bull/bear research debate → research manager → trader
           → risk debate (aggressive / conservative / neutral) → portfolio manager → memory write-back
```

Heavy logic (market/financial data, Backtrader backtests, paper trading, memory
store) lives in the Python sidecar (`etfagents/` + `cli/`). Orchestration, the
LLM factory, the CLI and the Ink TUI live in the TypeScript front-end (`ts/`).

## Quick start

```bash
git clone https://github.com/haphap/ETFAgents.git && cd ETFAgents
python -m venv .venv && source .venv/bin/activate && pip install .
cp .env.example .env          # fill TUSHARE_TOKEN + an LLM provider key
cd ts && pnpm install --frozen-lockfile
pnpm dev analyze 510300.SH    # full pipeline for one ETF
pnpm dev tui                  # interactive dashboard (or: pnpm tui)
```

See **[CLI & TUI](CLI-and-TUI)** for the full command set and **[Configuration](Configuration)** for environment setup.
