# ETFAgents

Multi-agent ETF research and allocation framework built on LangGraph. Coordinates
6 specialist analyst agents, a bull/bear research debate, a trader, risk
debaters, and a portfolio manager to produce structured ETF allocation
decisions.

> ETFAgents is for research and experimentation only. It is not financial advice.

## Architecture

```
TypeScript (ts/)              JSON-RPC over stdio        Python (etfagents/)
─────────────────────         ───────────────────         ───────────────────
CLI (commander) + TUI (Ink)   newline-delimited           bridge sidecar
LangGraph.js + 6 analyst ⇄    请求/响应                    ⇄ 22 @tool functions
  nodes + trader                                          数据层 (tushare/yfinance)
LLM (ChatOpenAI)                                          回测 (backtrader)
BacktestSignal extraction                                  paper trading
Memory injection                                          cache manager
```

## Highlights

- **TypeScript CLI + Ink TUI** — 8 CLI commands, interactive terminal UI
- **6 specialist analysts** — market flow, macro regime, meso commodity, catalyst sentiment, holdings industry, top holdings
- **Research debate** — bull/bear researchers + research manager
- **Risk management** — 3 risk debators (aggressive/conservative/neutral) + portfolio manager
- **Backtrader-powered backtests** with structured triggers and benchmarks
- **Backtest signal extraction** from rendered prose + structured plan
- **Paper trading** with multi-user support, A-share ETF rules (T+1, commission, lot size)
- **Agent memory** — continuity, lessons, and reusable method playbooks
- **Multiple LLM providers** — OpenAI, Google, Anthropic, xAI, MiniMax, OpenRouter, Ollama, DeepSeek
- **Vendor-routed market data** — Tushare, yfinance, qlib, Brave Search, OpenCLI
- **Layered report validation** — static structural checks + optional LLM judge
- **English / Chinese output**

## Quick Start

### Python sidecar

```bash
python -m venv .venv && source .venv/bin/activate
pip install .
cp .env.example .env   # Set TUSHARE_TOKEN + LLM API keys
```

### TypeScript CLI

```bash
cd ts
pnpm install
pnpm dev analyze-mini 510300.SH          # Minimal 1-analyst pipeline
pnpm dev analyze 510300.SH               # Full 6-analyst pipeline
pnpm dev analyze-pool 510300.SH 159915.SZ # Multi-ticker ranking
pnpm dev backtest 510300.SH --start-date 2024-01-01 --end-date 2024-06-01
pnpm dev paper account                   # Paper trading
pnpm dev detail 510300.SH               # ETF info lookup
pnpm dev cache stats                     # Cache management
```

### TUI

```bash
cd ts && pnpm dev tui
```

Interactive terminal UI with tab routing (Research / Results / Cache).

## Configuration

```bash
cp .env.example .env
```

Key environment variables:

```bash
TUSHARE_TOKEN=          # Required for A-share ETF data
MINIMAX_API_KEY=        # Optional: provider keys
OPENROUTER_API_KEY=
DEEPSEEK_API_KEY=
ETFAGENTS_RESULTS_DIR=  # Default: ~/.etfagents/logs
ETFAGENTS_CACHE_DIR=    # Default: ~/.etfagents/cache
```

## Development

```bash
# Python tests
python -m unittest discover -s tests -q

# TypeScript tests
cd ts && pnpm test       # 288 tests, 18 files
cd ts && pnpm typecheck  # Strict mode, 0 errors
cd ts && pnpm lint       # Biome
```

See [`ts/README.md`](ts/README.md) for the TS project layout and
[`docs/bridge.md`](docs/bridge.md) for the JSON-RPC protocol.

## License

Add a license file before publishing.
