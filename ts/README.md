# etfagents-ts

TypeScript front-end for ETFAgents. Drives the Python codebase as a JSON-RPC
sidecar (`etfagents/bridge`) with a full 6-analyst LangGraph pipeline.

## Quick Start

```bash
cd ts
pnpm install
pnpm dev analyze-mini 510300.SH          # minimal 1-analyst pipeline
pnpm dev analyze 510300.SH               # full 6-analyst pipeline
pnpm dev analyze-pool 510300.SH 159915.SZ # multi-ticker ranking
pnpm dev backtest 510300.SH --start-date 2024-01-01 --end-date 2024-06-01
pnpm dev detail 510300.SH               # ETF info lookup
pnpm dev cache stats                     # cache management
pnpm dev paper account                   # paper trading
pnpm dev tui                             # Ink terminal dashboard
```

## TUI

```bash
pnpm tui          # direct TUI script
pnpm dev tui      # same TUI through the Commander CLI
```

Interactive terminal UI with home navigation for research, reports, backtests,
and paper-trading views. The TUI keeps the app shell in `src/tui/index.tsx`,
state/reducer helpers in `src/tui/model.ts`, graph execution in
`src/tui/runner.ts`, artifact loading in `src/tui/services/`, and Ink screens
in `src/tui/screens.tsx`.

## Project Layout

```
ts/
├── src/
│   ├── agents/
│   │   ├── helpers/       # Post-processing (sanitize, format, validate, signals, memory)
│   │   ├── nodes/         # LangGraph nodes (6 analysts, trader, debate, risk)
│   │   ├── prompts/       # System message builders (bilingual)
│   │   ├── schemas/       # Zod schemas (TraderProposal, rating, triggers)
│   │   └── state.ts       # LangGraph state annotation
│   ├── bridge/            # JSON-RPC client, types, tool factories
│   ├── cli/               # Commander CLI commands
│   ├── graph/             # StateGraph builders (mini_spine, full_graph, routing)
│   ├── llm/               # ChatOpenAI from bridge config
│   └── tui/               # Ink TUI shell, model, runner, services, screens
└── test/                  # Vitest
```

## Testing

```bash
pnpm typecheck              # TypeScript strict mode
pnpm lint                   # Biome (no errors)
pnpm test                   # Vitest (24 files, 349 tests)
python -m unittest tests.test_bridge_protocol -q  # Python bridge (15 tests)
```

## Architecture

```
TypeScript (ts/)              JSON-RPC over stdio        Python (etfagents/)
─────────────────────         ───────────────────         ───────────────────
CLI (commander) + TUI (Ink)   newline-delimited           bridge sidecar
LangGraph.js + agent nodes ⇄  请求/响应                    ⇄ tools (langchain @tool)
LLM (ChatOpenAI)                                          数据层 (tushare/yfinance)
BacktestSignal extraction                                  backtest (backtrader)
Memory injection                                           cache_manager
```
