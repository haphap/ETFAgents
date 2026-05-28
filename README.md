# ETFAgents

Multi-agent ETF research and allocation framework built on LangGraph. Coordinates specialist analyst agents, a bull/bear research debate, a trader, risk debaters, and a portfolio manager to produce structured ETF allocation decisions.

> ETFAgents is for research and experimentation only. It is not financial advice.

## Highlights

- **Multi-agent ETF workflow** — analyst reports → research debate → trader plan → risk management → portfolio decision
- **Candidate-pool ranking** with sequential batch analysis and comparison tables
- **Backtrader-powered backtests** with structured triggers, configurable execution timing, and benchmarks
- **Paper trading simulation** with multi-user support, A-share ETF rules (T+1, commission, lot size)
- **ETF watchlist** with SQLite-backed groups and tags
- **ETF detail panel** — price, NAV, holdings, fund info, historical reports
- **Cache management** across API, signal, snapshot, and checkpoint categories
- **Smart model recommendation** with capability rating and research-depth awareness
- **Multiple LLM providers** — OpenAI, Google, Anthropic, xAI, MiniMax, OpenRouter, Ollama
- **Vendor-routed market data** — Tushare, yfinance, qlib, Brave Search, OpenCLI
- **Layered report validation** — static structural checks + optional LLM judge
- **Checkpoint/resume** for long-running runs
- **Agent memory** — continuity, lessons, and reusable method playbooks
- **English / Chinese output**

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

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

## Quick Start

```bash
etfagents                 # Interactive CLI
etfagents analyze         # Single-ticker analysis
etfagents analyze --checkpoint   # Resumable runs
etfagents detail 510300.SH       # ETF detail panel

etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 --end-date 2026-03-31
```

For all commands and usage examples, see [docs/usage.md](docs/usage.md).

## Development

```bash
python -m unittest discover -s tests -q
```

The TypeScript front-end (CLI + future Ink TUI) lives under [`ts/`](ts/) and
drives the Python codebase as a JSON-RPC sidecar. See [`ts/README.md`](ts/README.md)
and [`docs/bridge.md`](docs/bridge.md).

## License

Add a license file before publishing if you want the repository to have an explicit open-source license.
