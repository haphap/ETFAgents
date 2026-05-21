# CLI Usage Guide

## Interactive Analysis

```bash
etfagents analyze
```

The CLI walks through ticker selection, analysis date, LLM provider, model choice, research depth, output language, and analyst selection, then streams the graph execution live in the terminal.

```bash
etfagents analyze --checkpoint                # Resume interrupted runs
etfagents analyze --clear-checkpoints --checkpoint
```

## Cache Management (`etfagents cache`)

```bash
etfagents cache stats                         # Show cache statistics (4 categories)
etfagents cache stats --json                  # JSON output
etfagents cache cleanup --days 7              # Remove entries older than 7 days
etfagents cache cleanup --days 0              # Clear all cached entries
etfagents cache clear --type signals          # Clear signal cache only
etfagents cache clear --type all --yes        # Clear everything (skip prompt)
```

## Watchlist (`etfagents watchlist`)

Manage ETF tickers with groups and tags in a SQLite database (`~/.etfagents/watchlist.db`):

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
etfagents watchlist remove 510300.SH
etfagents watchlist remove 159915.SZ --group tech

# Groups
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

## ETF Detail (`etfagents detail`)

```bash
etfagents detail 510300.SH
etfagents detail 159915.SZ --date 2026-05-18
```

Displays: latest price, NAV, premium/discount, fund share changes, top 10 holdings, fund type, manager, benchmark, and historical analysis reports.

## Candidate-Pool (Batch) Analysis

Enter multiple tickers or use a watchlist group:

```bash
etfagents analyze --watchlist my_pool
```

The CLI shows a startup panel, per-ticker progress (`[N/3] TICKER ─ RATING · Score N · time`), and a batch comparison table with color-coded ratings.

## Backtest

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

## Paper Trading (`etfagents paper`)

Multi-user paper trading simulation with A-share ETF rules (commission 0.025% / min ¥5, lot size 100, no stamp duty, T+1 settlement):

```bash
# Register and login
etfagents paper register alice
etfagents paper login alice

# Account
etfagents paper account
etfagents paper account --json

# Trade
etfagents paper buy 510300.SH 1000
etfagents paper buy 159915.SZ 500 --analysis-id /reports/r1

# Positions with live P&L
etfagents paper positions
etfagents paper positions --json

# Sell (T+1: today's buys lock until next day)
etfagents paper sell 510300.SH 500

# History
etfagents paper history
etfagents paper history --limit 50

# Reset
etfagents paper reset --yes --cash 2000000

# Multi-user
etfagents paper register bob
etfagents paper buy 510300.SH 500 --user bob

# Switch users
etfagents paper logout
etfagents paper login default
```

After a single-ticker analysis with a BUY/OVERWEIGHT rating, the CLI offers a post-analysis trade suggestion:

```
Paper Trade Suggestion: BUY 510300.SH 8500 shares (@ 4.120, target weight 35.0%)
Execute this trade? (Y/n)
```

## Memory

```bash
etfagents memory promote-playbook --id <entry-id>
etfagents memory promote-playbook --id <entry-id> --expires-days 30 --max-active 20
```

## Smart Model Recommendation

The interactive CLI (Step 5: Research Depth) triggers capability-based model selection:

| Depth | Debate Rounds | Risk Rounds | Target Capability |
|-------|---------------|-------------|-------------------|
| Quick / 快速 | 1 | 1 | Balanced |
| Standard / 标准 | 2 | 1 | Capable |
| Deep / 深入 | 3 | 2 | Strong |

### Python API

```python
from etfagents.llm_clients.model_catalog import get_depth_config, recommend_models

depth_config = get_depth_config("标准")
# {"debate_rounds": 2, "risk_rounds": 1, ...}

models = recommend_models("标准", "openai")
# {"quick": "gpt-5.4-mini", "deep": "gpt-5.4"}
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

graph = EtfAgentsGraph(debug=True, config=config)
state, decision = graph.propagate("510300.SH", "2024-05-10")

# Backtest
result = graph.backtest_candidate_pool(
    ["510300.SH", "159915.SZ"],
    "2026-01-02", "2026-03-31",
    execution_timing="same_close",
    benchmark_tickers=["equal_weight_pool"],
)
print(result.metrics.cumulative_return)
```

### Module APIs

```python
# Cache
from etfagents.cache_manager import CacheManager
cm = CacheManager()
cm.stats()
cm.cleanup(max_age_days=30)

# Watchlist
from etfagents.watchlist import WatchlistManager
wl = WatchlistManager()
wl.add("510300.SH", group="tech", tags=["china"])
tickers = wl.get_tickers_for_analysis("tech")

# ETF detail
from etfagents.detail import get_etf_detail
detail = get_etf_detail("510300.SH")
print(detail["close"], detail["name"])

# Paper trading
from etfagents.paper_trading import PaperTradingEngine
engine = PaperTradingEngine()
engine.register("alice", "mypassword")
engine.buy("510300.SH", 1000, user_id="alice")
suggestion = engine.suggest_order_from_signal("510300.SH", final_state)
```
