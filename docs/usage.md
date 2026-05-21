# CLI Usage Guide

## Interactive Analysis (`etfagents analyze`)

```bash
etfagents analyze
```

Interactive walkthrough covering ticker selection, analysis date, LLM provider, model choice, research depth, output language, and analyst selection. Live streaming of graph execution in the terminal.

```bash
etfagents analyze --checkpoint                # Resume interrupted runs
etfagents analyze --clear-checkpoints --checkpoint
etfagents analyze --watchlist tech            # Analyze all tickers in a watchlist group
etfagents analyze --memory-mode lesson        # Memory mode: disabled|continuity-only|lesson|full
```

### Multi-Ticker (Candidate Pool)

Enter multiple tickers (comma-separated) or use `--watchlist` to run sequential analysis:

```bash
etfagents analyze --watchlist my_pool
```

The CLI displays a startup panel, per-ticker progress (`[N/3] TICKER ─ RATING · Score N · time`), and a batch comparison table with color-coded ratings (green BUY/OVERWEIGHT, red SELL/UNDERWEIGHT).

## Backtest (`etfagents backtest`)

```bash
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 \
  --end-date 2026-03-31
```

### Full Option Reference

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--tickers` | TEXT | — | Comma-separated ETF tickers |
| `--watchlist` / `-w` | TEXT | — | Use tickers from a watchlist group |
| `--benchmark-tickers` | TEXT | — | Comma-separated benchmark tickers, or `equal_weight_pool` |
| `--start-date` * | TEXT | — | Start date (YYYY-MM-DD) |
| `--end-date` * | TEXT | — | End date (YYYY-MM-DD) |
| `--rebalance-interval-days` | INT | 21 | Days between rebalances |
| `--top-k` | INT | 3 | Number of top candidates to hold |
| `--execution-timing` | TEXT | same_close | `same_close` \| `next_open` \| `next_close` |
| `--initial-cash` | FLOAT | 1,000,000 | Initial portfolio cash |
| `--commission` | FLOAT | 0.0 | Per-trade commission rate |
| `--slippage-perc` | FLOAT | 0.0 | Slippage percentage |
| `--cash-buffer-pct` | FLOAT | 0.0 | Cash reserve percentage |
| `--force-refresh` | FLAG | off | Bypass signal cache and recompute |
| `--research-depth` | INT | 1 | Debate rounds per ticker |
| `--llm-provider` | TEXT | openai | LLM provider |
| `--deep-think-llm` | TEXT | gpt-5.4 | Model for deep reasoning |
| `--quick-think-llm` | TEXT | gpt-5.4-mini | Model for quick tasks |
| `--output-language` | TEXT | Chinese | Report output language |
| `--memory-mode` | TEXT | full | `disabled` \| `continuity-only` \| `lesson` \| `full` |
| `--memory-in-backtest` / `--no-memory-in-backtest` | FLAG | off | Enable memory during backtests |
| `--backend-url` | TEXT | — | Custom LLM backend URL |
| `--save-path` | PATH | auto | Custom output directory |

\* required

### Examples

```bash
# Basic
etfagents backtest --tickers 510300.SH,159915.SZ --start-date 2026-01-02 --end-date 2026-03-31

# With benchmarks and custom rebalance schedule
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --benchmark-tickers equal_weight_pool,510300.SH \
  --start-date 2026-01-02 --end-date 2026-03-31 \
  --rebalance-interval-days 7 \
  --top-k 5 \
  --commission 0.0003 --slippage-perc 0.001

# Force refresh (ignore cached signals)
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 --end-date 2026-03-31 \
  --force-refresh

# Custom models and deeper research
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 --end-date 2026-03-31 \
  --llm-provider anthropic \
  --deep-think-llm claude-sonnet-4-20250514 \
  --research-depth 2

# Local Ollama backend
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 --end-date 2026-03-31 \
  --llm-provider ollama --backend-url http://localhost:11434/v1

# With memory enabled
etfagents backtest \
  --tickers 510300.SH,159915.SZ \
  --start-date 2026-01-02 --end-date 2026-03-31 \
  --memory-mode lesson --memory-in-backtest
```

## Cache Management (`etfagents cache`)

```bash
etfagents cache stats                         # Show cache statistics (4 categories)
etfagents cache stats --json                  # JSON output
etfagents cache cleanup --days 7              # Remove entries older than 7 days
etfagents cache cleanup --days 30 --type api  # Clean API cache only
etfagents cache cleanup --days 0              # Clear all cached entries
etfagents cache clear --type signals          # Clear signal cache only
etfagents cache clear --type all --yes        # Clear everything (skip prompt)
```

Cache categories: `api`, `signals`, `snapshots`, `checkpoints`, `all`.

## Watchlist (`etfagents watchlist`)

SQLite-backed ETF watchlist with groups and tags (`~/.etfagents/watchlist.db`):

```bash
# Add tickers
etfagents watchlist add 510300.SH,159915.SZ
etfagents watchlist add 513100.SH --group tech --tags china,internet
etfagents watchlist add 518880.SH --notes "Gold ETF"

# List
etfagents watchlist list
etfagents watchlist list --group tech
etfagents watchlist list --tags china,internet
etfagents watchlist list --json

# Remove
etfagents watchlist remove 510300.SH                # All groups
etfagents watchlist remove 159915.SZ --group tech   # Specific group only

# Groups
etfagents watchlist group list
etfagents watchlist group add tech
etfagents watchlist group rename tech technology
etfagents watchlist group remove tech
```

Watchlist groups can be used directly with `analyze` and `backtest`:

```bash
etfagents analyze --watchlist tech
etfagents backtest --watchlist tech --start-date 2026-01-02 --end-date 2026-03-31
```

## ETF Detail (`etfagents detail`)

```bash
etfagents detail 510300.SH
etfagents detail 159915.SZ --date 2026-05-18
```

Displays a Rich panel with: latest price (open/high/low/close), NAV and premium/discount, fund share changes, top 10 holdings, fund type, manager, benchmark, and historical analysis reports from the results directory.

## Paper Trading (`etfagents paper`)

Multi-user paper trading simulation. Rules: A-share ETF — commission 0.025% (min ¥5), lot size 100, no stamp duty, T+1 settlement.

### Account Management

```bash
# First-time setup
etfagents paper register alice
etfagents paper login alice

# Account overview
etfagents paper account
etfagents paper account --json

# Switch users
etfagents paper login bob
etfagents paper logout                    # Back to default account
etfagents paper login default             # Explicit default (no password)
```

### Trading

```bash
etfagents paper buy 510300.SH 1000
etfagents paper buy 159915.SZ 500 --user bob
etfagents paper buy 513100.SH 1000 --analysis-id /reports/r1

etfagents paper sell 510300.SH 500
# T+1 note: shares bought today cannot be sold until next day

etfagents paper positions                  # Live P&L
etfagents paper positions --json

etfagents paper history                    # Recent 20 trades
etfagents paper history --limit 50

etfagents paper reset --yes                # Reset to 1,000,000
etfagents paper reset --yes --cash 2000000 # Reset with custom cash
```

### Post-Analysis Suggestion

After a single-ticker `etfagents analyze` run with a BUY or OVERWEIGHT rating, the CLI offers an interactive paper trade suggestion:

```
┌ Paper Trade Suggestion ─────────────────────────────┐
│ BUY 510300.SH 8500 shares (@ 4.120, target weight    │
│ 35.0%)                                                │
└──────────────────────────────────────────────────────┘
Execute this trade? (Y/n)
```

## Memory (`etfagents memory`)

The layered agent memory system tracks analysis continuity, resolved lessons, and reusable method playbooks across runs.

```bash
etfagents memory promote-playbook --id <entry-id>
etfagents memory promote-playbook --id <entry-id> --expires-days 30 --max-active 20
etfagents memory promote-playbook --id <entry-id> --results-dir /custom/path
```

### Memory Modes

| Mode | Description |
|------|-------------|
| `disabled` | No memory retrieval or storage |
| `continuity-only` | Latest-analysis continuity brief |
| `lesson` | Continuity + resolved outcome lessons |
| `full` (default) | Continuity + lessons + reusable method reminders |

Set via `--memory-mode` on `analyze` or `backtest`:

```bash
etfagents analyze --memory-mode lesson
etfagents backtest --tickers ... --memory-mode disabled
```

For backtests, memory is off by default for reproducibility; enable with `--memory-in-backtest`:

```bash
etfagents backtest --tickers ... --memory-mode lesson --memory-in-backtest
```

Note: enabling memory in backtests makes cache keys depend on memory state, reducing cache hit rate.

## Research Depth & Model Recommendation

The interactive CLI (Step 5) offers five research depth levels:

| Level | Key | Debate Rounds | Risk Rounds | Min Capability |
|-------|-----|---------------|-------------|----------------|
| Fast / 快速 | `快速` | 0 | 0 | Basic (L1) |
| Basic / 基础 | `基础` | 1 | 0 | Basic (L1) |
| Standard / 标准 | `标准` | 1 | 1 | Capable (L2) |
| Deep / 深度 | `深度` | 2 | 2 | Strong (L3) |
| Full / 全面 | `全面` | 3 | 3 | Strong (L3) w/ reasoning |

Deeper levels trigger more debate rounds between bull/bear researchers and risk analysts.

### Configuration Keys

```python
config["research_depth_name"] = "标准"
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
```

### Model Catalog Python API

```python
from etfagents.llm_clients.model_catalog import get_depth_config, recommend_models

depth = get_depth_config("标准")
# {"min_level": 2, "debate_rounds": 1, "risk_rounds": 1, ...}

models = recommend_models("标准", "openai")
# {"quick_model": "gpt-5.4-mini", "deep_model": "gpt-5.4",
#  "quick_reason": "...", "deep_reason": "...", "depth": "标准"}
```

## Report Validation

Analyst reports undergo layered validation before acceptance:

| Mode | Description |
|------|-------------|
| `disabled` | No validation — accept all outputs as-is |
| `static_only` | Deterministic structural checks only (sections, indicators, format). No LLM cost. |
| `static_plus_llm` (default) | Static checks first, then structured-output LLM judge with refine pass |
| `llm_only` | LLM judge only, skipping static checks |

Set via `validation_mode` in config or wire through analyst calls. `static_only` is useful for cost-sensitive or backtest runs.

## Checkpoint / Resume

```bash
etfagents analyze --checkpoint                # Enable checkpointing
etfagents analyze --clear-checkpoints --checkpoint  # Fresh start
```

When enabled, the graph saves progress after each node. Interrupted runs can resume from the last completed state.

## LLM Providers

Supported providers and configuration:

```bash
# OpenAI
etfagents analyze  # Select "openai" in interactive prompt

# Anthropic
etfagents analyze  # Select "anthropic"

# Google (Gemini)
etfagents analyze  # Select "google" — configure thinking mode

# OpenRouter
etfagents analyze  # Select "openrouter"

# Local backends
etfagents backtest --tickers ... --llm-provider ollama --backend-url http://localhost:11434/v1
```

Provider-specific thinking configuration:

| Provider | Config Key | Values |
|----------|-----------|--------|
| Google | `google_thinking_level` | `high`, `minimal`, etc. |
| OpenAI | `openai_reasoning_effort` | `low`, `medium`, `high` |
| Anthropic | `anthropic_effort` | `low`, `medium`, `high` |

## Configuration Reference

### Environment Variables

```bash
TUSHARE_TOKEN=              # Required for A-share ETF data
MINIMAX_API_KEY=            # MiniMax provider
OPENROUTER_API_KEY=          # OpenRouter provider
DEEPSEEK_API_KEY=            # DeepSeek provider
ETFAGENTS_RESULTS_DIR=       # Default: ~/.etfagents/logs
ETFAGENTS_CACHE_DIR=         # Default: ~/.etfagents/cache
ETFAGENTS_BENCHMARK_TICKER=  # Default benchmark
```

### Data Vendor Routing

```python
config["data_vendors"] = {
    "etf_market_data": "tushare",
    "news_data": "opencli,brave,yfinance",
    ...
}
config["tool_vendors"] = {
    "get_etf_price_data": "tushare",
    "get_news": "opencli",
    ...
}
```

Vendors are tried in listed order with automatic fallback. Tools-level config takes precedence over category-level.

### Cache Configuration

```python
config["data_cache_dir"]       # Default: ~/.etfagents/cache
config["snapshot_max_age_days"] = 30
config["backtest_cache_max_age_days"] = 90
config["checkpoint_max_age_days"] = 30
```

### Output Language

```python
config["output_language"] = "Chinese"  # or "English"
```

Internal agent debate always runs in English for reasoning quality; only analyst reports and final decisions use the configured output language.

## Python API Reference

### Main Graph

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
config["max_debate_rounds"] = 2
config["output_language"] = "Chinese"

graph = EtfAgentsGraph(debug=True, config=config)

# Single-ticker analysis
state, decision = graph.propagate("510300.SH", "2024-05-10")

# Candidate-pool analysis
ranked = graph.analyze_candidate_pool(
    ["510300.SH", "159915.SZ"],
    "2024-05-10",
    per_ticker_callback=lambda ticker, idx, total, result: print(f"[{idx+1}/{total}] {ticker}")
)

# Backtest
result = graph.backtest_candidate_pool(
    ["510300.SH", "159915.SZ"],
    "2026-01-02", "2026-03-31",
    execution_timing="same_close",
    benchmark_tickers=["equal_weight_pool"],
    rebalance_interval_days=21,
    top_k=3,
)
print(result.metrics.cumulative_return)
```

### Cache Manager

```python
from etfagents.cache_manager import CacheManager
from etfagents.default_config import DEFAULT_CONFIG
import copy
cm = CacheManager(copy.deepcopy(DEFAULT_CONFIG))
cm.stats()                          # {"api": {...}, "signals": {...}, ...}
cm.cleanup(days=30)
cm.clear(category="signals")
```

### Watchlist Manager

```python
from etfagents.watchlist import WatchlistManager
wl = WatchlistManager()
wl.add("510300.SH", group="tech", tags=["china"], notes="CSI 300 ETF")
tickers = wl.get_tickers_for_analysis("tech")   # ["510300.SH"]
wl.list_tickers(group="tech")
wl.remove("510300.SH")
```

### ETF Detail

```python
from etfagents.detail import get_etf_detail, get_etf_history_reports
detail = get_etf_detail("510300.SH")
print(detail["close"], detail["name"], detail["premium_discount_bps"])
reports = get_etf_history_reports("510300.SH", "/path/to/results")
```

### Paper Trading Engine

```python
from etfagents.paper_trading import PaperTradingEngine
engine = PaperTradingEngine()

# Auth
engine.register("alice", "mypassword")
engine.login("alice", "mypassword")

# Trade
engine.buy("510300.SH", 1000, user_id="alice")
engine.sell("510300.SH", 500, user_id="alice")

# Query
account = engine.get_account(user_id="alice")
positions = engine.get_positions(user_id="alice")
trades = engine.get_trades(user_id="alice", limit=50)

# Signal → order suggestion
suggestion = engine.suggest_order_from_signal("510300.SH", final_state)
if suggestion:
    engine._execute_suggestion(suggestion)

engine.reset_account(user_id="alice", initial_cash=2_000_000)
```

### Model Catalog

```python
from etfagents.llm_clients.model_catalog import get_depth_config, recommend_models

depth = get_depth_config("标准")
# {"min_level": 2, "debate_rounds": 1, "risk_rounds": 1, ...}

models = recommend_models("标准", "openai")
# {"quick_model": "gpt-5.4-mini", "deep_model": "gpt-5.4",
#  "quick_reason": "...", "deep_reason": "...", "depth": "标准"}
```

### Trading Rules

```python
from etfagents.paper_trading.rules import (
    COMMISSION_RATE, MIN_COMMISSION, LOT_SIZE, STAMP_DUTY_RATE,
    calc_commission, validate_quantity, estimate_trade_cost,
)

validate_quantity(500)                        # Raises if not multiple of 100
cost = estimate_trade_cost(4.12, 500, "buy")  # {"amount", "commission", "total_cost"}
```
