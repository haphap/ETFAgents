# ETFAgents

ETFAgents is a multi-agent ETF research and allocation framework built on LangGraph. It extends the TradingAgents architecture toward ETF-specific analysis, candidate-pool ranking, portfolio construction, and rebalance workflows.

The project coordinates specialist analyst agents, a bull/bear research debate, a trader, risk debaters, and a portfolio manager to produce structured ETF allocation decisions.

> ETFAgents is for research and experimentation only. It is not financial advice.

## Highlights

- **ETF-focused workflow** for allocation, rebalance, and candidate-pool analysis
- **Interactive CLI** with Rich-based live output
- **Multiple LLM providers** including OpenAI, Google, Anthropic, xAI, MiniMax, OpenRouter, and Ollama/OpenAI-compatible backends
- **Vendor-routed market data** with fallback across Tushare, yfinance, qlib, Brave Search, and OpenCLI news aggregation
- **Backtrader-powered backtests** of candidate-pool decisions with structured triggers, configurable execution timing, and benchmark comparison
- **Layered analyst report validation** with static structural checks first, then an optional structured-output LLM judge / refine pass
- **Checkpoint/resume support** for long-running runs
- **Cache management** with `etfagents cache stats/cleanup/clear` across API, signal, snapshot, and checkpoint categories
- **ETF watchlist** with SQLite-backed groups and tags, usable from `analyze` and `backtest`
- **Smart model recommendation** with capability-level rating and research-depth-aware model selection
- **ETF detail panel** with Rich rendering of price, NAV, holdings, fund info, and historical reports
- **Batch candidate-pool analysis** with sequential per-ticker progress, comparison table, and color-coded ratings
- **Paper trading simulation** with multi-user support (bcrypt auth), A-share ETF rules (T+1, commission, lot size), and post-analysis trade suggestions
- **Layered agent memory** with latest-analysis continuity, resolved lessons, and reusable method reminders
- **English and Chinese output** for reports and final decisions

See also: [`docs/recent-backtesting-and-memory-notes.md`](docs/recent-backtesting-and-memory-notes.md) for a concise delivery summary of the recent backtesting and memory-system work.

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
- Set `validation_mode` (or wire it through analyst calls) to one of `disabled`, `static_only`, `static_plus_llm` (default), or `llm_only`. `static_only` keeps the deterministic structural / token / format-artifact checks but skips the LLM judge, useful for cost-sensitive or backtest runs.
- `etfagents backtest --force-refresh` bypasses the agent-output signal cache when the underlying LLM model, prompts, or vendor routing change.

## CLI Usage

Run the interactive CLI:

```bash
etfagents
```

Or run directly from source:

```bash
python -m cli.main
```

### Interactive Analysis

The CLI walks through ticker selection, analysis date, LLM provider, model choice, research depth, output language, and analyst selection, then streams the graph execution live in the terminal.

```bash
etfagents analyze
```

Enable checkpointing for resumable runs:

```bash
etfagents analyze --checkpoint
etfagents analyze --clear-checkpoints --checkpoint
```

### Cache Management (`etfagents cache`)

```bash
etfagents cache stats                    # Show cache statistics (4 categories)
etfagents cache stats --json             # JSON output
etfagents cache cleanup --days 7         # Remove entries older than 7 days
etfagents cache cleanup --days 0         # Clear all cached entries
etfagents cache clear --type signals     # Clear signal cache only
etfagents cache clear --type all --yes   # Clear everything (skip prompt)
```

### Watchlist (`etfagents watchlist`)

Manage ETF tickers with groups and tags in a SQLite database (`~/.etfagents/watchlist.db`):

```bash
# Add tickers to the default group
etfagents watchlist add 510300.SH,159915.SZ

# Add to a named group (auto-created)
etfagents watchlist add 513100.SH --group tech --tags china,internet

# Add with notes
etfagents watchlist add 518880.SH --notes "Gold ETF"

# List all watchlist entries
etfagents watchlist list

# List with filters
etfagents watchlist list --group tech
etfagents watchlist list --tags china,internet
etfagents watchlist list --json

# Remove tickers
etfagents watchlist remove 510300.SH
etfagents watchlist remove 159915.SZ --group tech

# Group management
etfagents watchlist group list
etfagents watchlist group add tech
etfagents watchlist group rename tech technology
etfagents watchlist group remove tech
```

Use watchlist groups directly in analysis and backtests:

```bash
etfagents analyze --watchlist tech
etfagents backtest --watchlist tech --start-date 2026-01-02 --end-date 2026-03-31
```

### ETF Detail (`etfagents detail`)

Show a comprehensive Rich panel for an ETF:

```bash
etfagents detail 510300.SH
etfagents detail 159915.SZ --date 2026-05-18
```

Displays: latest price, NAV, premium/discount, fund share changes, top 10 holdings, fund type, manager, benchmark, and historical analysis reports from the results directory.

### Candidate-Pool (Batch) Analysis

Enter multiple tickers or use a watchlist group to run sequential analysis across a pool:

```bash
etfagents analyze --watchlist my_pool
```

The CLI shows:
- A startup panel with tickers, date, analysts, and progress
- Per-ticker progress lines: `[N/3] TICKER ─ RATING · Score N · time`
- A batch summary comparison table after completion (ticker, rating, weight, elapsed time)
- Color-coded ratings (green for BUY/OVERWEIGHT, red for SELL/UNDERWEIGHT)

### Backtest

Run a candidate-pool backtest:

```bash
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 \
  --end-date 2026-03-31 \
  --execution-timing same_close \
  --top-k 3 \
  --benchmark-tickers equal_weight_pool \
  --rebalance-interval-days 21

etfagents backtest \
  --watchlist tech \
  --start-date 2026-01-02 \
  --end-date 2026-03-31 \
  --force-refresh
```

### Paper Trading (`etfagents paper`)

Multi-user paper trading simulation with A-share ETF rules:

```bash
# Register and login
etfagents paper register alice
etfagents paper login alice

# Check account
etfagents paper account
etfagents paper account --json

# Trade (lot size = 100, commission 0.025% / min ¥5, no stamp duty)
etfagents paper buy 510300.SH 1000
etfagents paper buy 159915.SZ 500 --analysis-id /reports/r1

# View positions with live P&L
etfagents paper positions
etfagents paper positions --json

# Sell (T+1: shares bought today cannot be sold until next day)
etfagents paper sell 510300.SH 500

# Trade history
etfagents paper history
etfagents paper history --limit 50

# Reset account
etfagents paper reset --yes --cash 2000000

# Multi-user isolation
etfagents paper register bob
etfagents paper buy 510300.SH 500 --user bob

# Logout / switch
etfagents paper logout
etfagents paper login default   # uses default (no-password) account
```

After a single-ticker `analyze` run with a BUY or OVERWEIGHT rating, the CLI offers a post-analysis paper trade suggestion:

```
Paper Trade Suggestion: BUY 510300.SH 8500 shares (@ 4.120, target weight 35.0%)
Execute this trade? (Y/n)
```

### Memory

```bash
etfagents memory promote-playbook --id <entry-id>
etfagents memory promote-playbook --id <entry-id> --expires-days 30 --max-active 20
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

Other Python APIs:

```python
# Cache management
from etfagents.cache_manager import CacheManager
cm = CacheManager()
print(cm.stats())          # {"api": {...}, "signals": {...}, ...}
cm.cleanup(max_age_days=30)
cm.clear(category="all")

# Watchlist
from etfagents.watchlist import WatchlistManager
wl = WatchlistManager()
wl.add("510300.SH", group="tech", tags=["china"], notes="CSI 300 ETF")
wl.add("159915.SZ", group="tech")
tickers = wl.get_tickers_for_analysis("tech")
# ["510300.SH", "159915.SZ"]

# ETF detail
from etfagents.detail import get_etf_detail
detail = get_etf_detail("510300.SH")
print(detail["close"], detail["name"], detail["premium_discount_bps"])

# Paper trading engine
from etfagents.paper_trading import PaperTradingEngine
engine = PaperTradingEngine()
engine.register("alice", "mypassword")
engine.buy("510300.SH", 1000, user_id="alice")
engine.sell("510300.SH", 500, user_id="alice")
positions = engine.get_positions(user_id="alice")
account = engine.get_account(user_id="alice")

# Signal → order suggestion
suggestion = engine.suggest_order_from_signal("510300.SH", final_state)
if suggestion:
    engine._execute_suggestion(suggestion)
```

## Smart Model Recommendation

The interactive CLI (Step 5: Research Depth) triggers capability-based model selection:

| Depth | Debate Rounds | Risk Rounds | Target Capability |
|-------|---------------|-------------|-------------------|
| Quick / 快速 | 1 | 1 | Balanced |
| Standard / 标准 | 2 | 1 | Capable |
| Deep / 深入 | 3 | 2 | Strong |

```python
from etfagents.llm_clients.model_catalog import get_depth_config, recommend_models

depth_config = get_depth_config("标准")
# {"debate_rounds": 2, "risk_rounds": 1, ...}

models = recommend_models("标准", "openai")
# {"quick": "gpt-5.4-mini", "deep": "gpt-5.4"}
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
cli/commands/         CLI subcommand modules (cache, watchlist, detail, paper)
etfagents/agents/     Analyst, researcher, trader, risk, and manager agents
etfagents/backtest/   Backtrader engine, candidate-pool runner, signal cache
etfagents/cache_manager.py  Unified cache statistics and cleanup
etfagents/dataflows/  Data vendor integrations and routing
etfagents/graph/      LangGraph orchestration, setup, replay, checkpoints
etfagents/llm_clients/Provider abstraction and model catalog
etfagents/paper_trading/ Paper trading engine, A-share ETF rules, session auth
etfagents/detail.py   ETF detail data aggregation
etfagents/watchlist.py SQLite-backed watchlist manager
tests/                Unit test suite
main.py               Minimal programmatic example
```

## Core Architecture

- `cli/main.py` builds the runtime config from user selections and streams execution into the terminal UI.
- `etfagents/graph/etf_graph.py` defines the ETF-specific graph on top of the shared trading graph base.
- `etfagents/graph/setup.py` assembles the LangGraph workflow.
- `etfagents/agents/utils/analysis_memory.py` stores structured analysis snapshots, resolved outcome lessons, and reusable method rules, then builds role-aware continuity / lesson / method briefs for later runs.
- `etfagents/agents/utils/validate_refine.py` runs the layered report validator (static structural checks first, optional structured-output LLM judge / refine), driven by per-analyst `AnalystReportSpec` definitions.
- `etfagents/agents/utils/report_leads.py` provides the `pre_judge_clean` / `post_judge_clean` regex pipeline that strips refine preambles, H1 titles, QA labels, meta openers, and self-referential leads.
- `etfagents/backtest/` contains the Backtrader engine, candidate-pool runner, signal cache, and the structured `BacktestSignal` / `Trigger` / `RiskRule` data models that drive dynamic mid-cycle rebalances. The `BACKTEST_SIGNAL_PROMPT_VERSION` constant in `backtest/cache.py` must be bumped when prompt or signal-extraction logic changes semantically, to invalidate stale cached signals.
- `etfagents/cache_manager.py` aggregates four cache categories (api, signals, snapshots, checkpoints) for statistics, age-based cleanup, and full clear. It is wired into the CLI as `etfagents cache stats|cleanup|clear`.
- `etfagents/dataflows/interface.py` routes tool calls to the configured data vendors with fallback behavior, and applies the `as_of_date` clamp that prevents future-data leakage during backtests.
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
