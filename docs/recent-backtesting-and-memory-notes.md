# Recent Backtesting and Memory Delivery Notes

This document summarizes the major repository changes delivered across the recent `feat/backtrader-backtesting` and `feat/memory-system` branches, plus the follow-up fixes that landed afterward.

## 1. Backtesting delivery

### 1.1 Structured signal layer

The backtesting path no longer depends on ad hoc portfolio-report parsing alone.

- Added framework-agnostic signal models in `etfagents/backtest/signals.py`
- Extended agent schemas so `TraderProposal` / `PortfolioDecision` can emit structured fields such as:
  - `target_weight_pct`
  - `target_weight_band`
  - `execution_timing`
  - structured trigger / risk-rule payloads
- Signal extraction now prefers structured fields and only falls back to text parsing when needed

### 1.2 Backtrader engine

Candidate-pool decisions can now be replayed inside a formal Backtrader engine.

- Added `etfagents/backtest/backtrader_engine.py`
- Supports `same_close`, `next_open`, and `next_close`
- Supports benchmark comparison, order/trade logs, position history, and NAV series
- Structured triggers and risk rules can drive dynamic mid-cycle rebalances

### 1.3 Historical safety and reproducibility

Several safeguards were added so historical backtests do not see future data.

- Added `BacktestContext`
- Vendor routing now clamps requests by `as_of_date`
- Unsafe backtest methods are explicitly blocked instead of silently leaking future information
- `get_news` / `get_global_news` are blocked in backtest mode by default
- Added `BacktestSignalStore` for cached historical signal reuse
- Added `--force-refresh` to bypass cached agent outputs when prompts, models, or routing change

### 1.4 Reporting and CLI surfaces

The backtest flow now has both Python and CLI entrypoints plus persistent artifacts.

- Added `EtfAgentsGraph.backtest_candidate_pool(...)`
- Added `etfagents backtest`
- Added `scripts/backtest_example.py`
- Saved artifacts now include:
  - `summary.md`
  - `report.html`
  - `nav_chart.svg`
  - `benchmarks.csv`
  - machine-readable JSON / CSV outputs for signals, positions, trades, orders, and rebalances
- CLI output now includes benchmark metrics, a data-health table, and a rebalance summary table

## 2. Memory-system delivery

### 2.1 New memory model

Repeated ETF analysis now has a structured continuity layer instead of behaving like a fresh run every day.

Added `etfagents/agents/utils/analysis_memory.py` with:

- `AnalysisMemoryEntry`
- `OutcomeLessonEntry`
- `MethodPlaybookEntry`
- `AnalysisMemoryStore`
- `MemoryContextBuilder`

The memory model is split into three layers:

1. **Continuity memory**: latest same-ticker analysis snapshot
2. **Outcome memory**: resolved lessons once returns are known
3. **Method memory / playbook**: reusable analysis rules

### 2.2 Prompt integration

Memory is now injected across the actual research and decision chain, not just the final manager.

- ETF analysts receive continuity and method reminders
- Research Manager receives continuity plus lesson context
- Trader receives prior execution context plus lessons / method reminders
- Portfolio Manager receives the full continuity / lesson / method combination

Prompt injection was later normalized through a shared helper so the various agents prepend memory context consistently.

### 2.3 Memory writing and learning loop

Each completed live run now writes a structured analysis snapshot. Later, once returns are available, the graph can resolve that snapshot into a structured lesson and a draft playbook rule.

- Added a graph-end `memory_writer` node
- Extended deferred reflection flow to create `OutcomeLessonEntry`
- Added automatic `MethodPlaybookEntry` generation as **draft**

### 2.4 CLI and runtime controls

Memory behavior is now configurable from the CLI.

- `etfagents analyze --memory-mode ...`
- `etfagents backtest --memory-mode ...`
- `etfagents backtest --memory-in-backtest`
- `etfagents memory promote-playbook --id ...`

Supported memory modes:

- `disabled`
- `continuity-only`
- `lesson`
- `full`

## 3. Follow-up hardening after review

Several review-driven fixes landed after the initial memory-system implementation.

### 3.1 Safer playbook activation

Playbooks no longer enter prompts immediately after lesson resolution.

- New playbooks start as `draft`
- Only `active` playbooks are injected into prompts
- Promotion is explicit through `promote-playbook`
- Active playbooks carry `expires_at`
- Per-scope active count is capped

### 3.2 Future-leak prevention

Lesson retrieval now clamps on both:

- `trade_date`
- `created_at`

This prevents historical runs from seeing lessons that were only discovered later.

### 3.3 Role-aware continuity briefs

Continuity brief construction is now configurable through `role_brief_specs`.

Default behavior:

- analysts get thesis + key drivers + watch items + invalidation signals
- trader gets execution-oriented continuity fields
- research / portfolio managers get richer continuity summaries

The current implementation uses rule-based summarization rather than an extra LLM summarizer call.

### 3.4 Backtest cache sensitivity to memory state

When `memory_in_backtest=True`, cache keys now include a `memory_signature` derived from the retrievable memory state. This preserves correctness, but it also means:

- cache hit rates drop
- backtests can take noticeably longer

### 3.5 Playbook audit metadata

Promoted playbooks now distinguish between:

- `created_at`: promotion / activation time, used for backtest cutoff semantics
- `first_seen_at`: original draft creation time, used for audit / human traceability

Also, playbook scope labels are localized so Chinese output uses `通用` instead of `General`.

### 3.6 NDJSON update behavior

Analysis-memory updates now use upsert / rewrite semantics instead of repeated append-only duplication for outcome-status changes. This keeps retrieval stable and reduces unbounded growth from the same entry being updated repeatedly.

## 4. Key files added or changed

Backtesting:

- `etfagents/backtest/signals.py`
- `etfagents/backtest/backtrader_engine.py`
- `etfagents/backtest/cache.py`
- `etfagents/graph/replay.py`
- `etfagents/graph/etf_graph.py`
- `etfagents/dataflows/interface.py`
- `cli/main.py`
- `scripts/backtest_example.py`

Memory:

- `etfagents/agents/utils/analysis_memory.py`
- `etfagents/graph/trading_graph.py`
- `etfagents/graph/setup.py`
- `etfagents/graph/propagation.py`
- `etfagents/agents/trader/trader.py`
- `etfagents/agents/managers/research_manager.py`
- `etfagents/agents/managers/portfolio_manager.py`
- ETF analyst prompt files under `etfagents/agents/analysts/`
- `etfagents/default_config.py`
- `cli/main.py`

Tests:

- `tests/test_backtest_signals.py`
- `tests/test_backtrader_engine.py`
- `tests/test_data_vendor_routing.py`
- `tests/test_etf_extensions.py`
- `tests/test_analysis_memory.py`
- `tests/test_memory_cli.py`

## 5. Current deferred items / known limits

- **Qlib recorder integration** remains intentionally deferred
- `AnalysisMemoryStore._upsert_entry()` still rewrites a whole NDJSON file; acceptable for now, but a SQLite-backed index layer is the likely next scalability step
- Backtest memory is opt-in because enabling it trades away cache density and strict reproducibility against richer historical context

## 6. Operational note

Recent PR commits were re-signed to satisfy protected-branch requirements. If merge is still blocked after commit verification, the remaining issue is repository branch-protection / ruleset permissions rather than code state.
