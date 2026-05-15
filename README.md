# ETFAgents

ETFAgents is a multi-agent ETF research and allocation framework built on LangGraph. It extends the TradingAgents architecture toward ETF-specific analysis, candidate-pool ranking, portfolio construction, and rebalance workflows.

The project coordinates specialist analyst agents, a bull/bear research debate, a trader, risk debaters, and a portfolio manager to produce structured ETF allocation decisions.

> ETFAgents is for research and experimentation only. It is not financial advice.

## Highlights

- **ETF-focused workflow** for allocation, rebalance, and candidate-pool analysis
- **Interactive CLI** with Rich-based live output
- **Multiple LLM providers** including OpenAI, Google, Anthropic, xAI, MiniMax, OpenRouter, and Ollama/OpenAI-compatible backends
- **Vendor-routed market data** with fallback across Tushare, yfinance, qlib, Brave Search, and OpenCLI news aggregation
- **Checkpoint/resume support** for long-running runs
- **Layered agent memory** with latest-analysis continuity, resolved lessons, and reusable method reminders
- **English and Chinese output** for reports and final decisions

## Analyst Stack

ETFAgents decomposes ETF research into specialized roles:

- **Market & Flow Analyst**: ETF price action, turnover, MACD, RSI, Bollinger Bands, VWMA, and flow signals
- **Sentiment & Catalyst Analyst**: public sentiment and short-term catalysts
- **Macro Regime Analyst**: macro conditions, policy shifts, and cross-asset context
- **Meso Commodity Analyst**: sector, industry, and commodity context
- **ETF Holdings-Industry Research Analyst**: holdings structure and industry mapping
- **ETF Top Holdings Research Analyst**: top constituent research
- **Bull / Bear Researchers**: structured debate over upside and downside
- **Trader**: translates research into allocation and rebalance plans
- **Risk Debate Team**: aggressive, neutral, and conservative risk views
- **Portfolio Manager**: final allocation decision

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install .
```

You can also install in an existing environment:

```bash
pip install .
```

## Configuration

Copy the example environment file and fill in the keys you need:

```bash
cp .env.example .env
```

Common environment variables:

```bash
MINIMAX_API_KEY=
OPENROUTER_API_KEY=
DEEPSEEK_API_KEY=

TUSHARE_TOKEN=

ETFAGENTS_RESULTS_DIR=
ETFAGENTS_CACHE_DIR=
```

Notes:

- `TUSHARE_TOKEN` is important for the ETF-specific China-market workflow.
- Local OpenAI-compatible backends can be used by setting `llm_provider` to `ollama` and configuring `backend_url`.
- Runtime logs default to `~/.etfagents/logs`; cache defaults to `~/.etfagents/cache`.
- Structured continuity memory is stored under `<results_dir>/memory/`; `memory_mode` defaults to `full`, while memory stays disabled in backtests unless `memory_in_backtest=True`.
- Enabling `--memory-in-backtest` makes cache keys depend on retrievable memory state, so cache hit rate drops and backtests can take noticeably longer.
- Memory briefs are generated with rule-based summarization plus configurable `role_brief_specs`, so different analyst/manager roles receive different continuity fields without an extra LLM summarizer call.
- Use `--memory-mode` on `etfagents analyze` / `etfagents backtest` to compare `disabled`, `continuity-only`, `lesson`, and `full`; promoted method rules can be activated with `etfagents memory promote-playbook --id <entry-id>`.

## CLI Usage

Run the interactive CLI:

```bash
etfagents
```

Or run directly from source:

```bash
python -m cli.main
```

Enable checkpointing for resumable runs:

```bash
etfagents analyze --checkpoint
etfagents analyze --clear-checkpoints --checkpoint
```

The CLI walks through ticker selection, analysis date, LLM provider, model choices, research depth, output language, and analyst selection, then streams the graph execution live in the terminal.

Run a candidate-pool backtest from the CLI:

```bash
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 \
  --end-date 2026-03-31 \
  --execution-timing same_close
```

## Python Usage

```python
import copy

from dotenv import load_dotenv

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.graph.etf_graph import EtfAgentsGraph

load_dotenv()

config = copy.deepcopy(DEFAULT_CONFIG)
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-5.4"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1

graph = EtfAgentsGraph(debug=True, config=config)
state, decision = graph.propagate("510300.SH", "2024-05-10")
print(decision)

backtest = graph.backtest_candidate_pool(
    ["510300.SH", "159915.SZ"],
    "2026-01-02",
    "2026-03-31",
    execution_timing="same_close",
    benchmark_tickers=["equal_weight_pool"],
)
print(backtest.metrics.cumulative_return)
```

There is also a thin script example:

```bash
python scripts/backtest_example.py --help
etfagents backtest --tickers 510300.SH,159915.SZ --benchmark-tickers equal_weight_pool --start-date 2026-01-02 --end-date 2026-03-31
```

Saved backtest artifacts now include `summary.md`, `report.html`, `nav_chart.svg`, `benchmarks.csv`, and the existing machine-readable JSON/CSV outputs. The CLI also prints a data-health table plus a rebalance summary table, and structured trigger/risk-rule fields can drive dynamic mid-cycle rebalances inside the Backtrader engine.

## Repository Layout

```text
cli/                  Interactive CLI entrypoint and terminal UI
etfagents/agents/     Analyst, researcher, trader, risk, and manager agents
etfagents/dataflows/  Data vendor integrations and routing
etfagents/graph/      LangGraph orchestration, setup, replay, checkpoints
etfagents/llm_clients/Provider abstraction and model handling
tests/                Unit test suite
main.py               Minimal programmatic example
```

## Core Architecture

- `cli/main.py` builds the runtime config from user selections and streams execution into the terminal UI.
- `etfagents/graph/etf_graph.py` defines the ETF-specific graph on top of the shared trading graph base.
- `etfagents/graph/setup.py` assembles the LangGraph workflow.
- `etfagents/agents/utils/analysis_memory.py` stores structured analysis snapshots, resolved outcome lessons, and reusable method rules, then builds role-aware continuity / lesson / method briefs for later runs.
- `etfagents/dataflows/interface.py` routes tool calls to the configured data vendors with fallback behavior.
- `etfagents/llm_clients/factory.py` normalizes LLM provider setup behind a single client factory.

## Development

Run the test suite:

```bash
python -m unittest discover -s tests -q
```

Run a single test:

```bash
python -m unittest tests.test_data_vendor_routing.DataVendorRoutingTests.test_fallback_when_primary_vendor_unavailable -q
```

## License

Add a license file before publishing if you want the repository to have an explicit open-source license.
