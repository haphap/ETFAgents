# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

- Install from source: `pip install .`
- Run the interactive CLI: `etfagents` (installed) or `python -m cli.main` (from source)
- Run a non-interactive candidate-pool backtest: `etfagents backtest --tickers 510300.SH,159915.SZ --benchmark-tickers equal_weight_pool --start-date 2026-01-02 --end-date 2026-03-31`
- Run the full test suite: `python -m unittest discover -s tests -q`
- Run a single test: `python -m unittest tests.test_data_vendor_routing.DataVendorRoutingTests.test_fallback_when_primary_vendor_unavailable -q`
- Smoke test structured output: `python scripts/smoke_structured_output.py <provider>`
- Backtesting example: `python scripts/backtest_example.py --help`

## Architecture

ETFAgents is a multi-agent LLM ETF investment framework built on LangGraph. It decomposes ETF allocation into specialized agent roles: analysts, researchers (bull/bear debate), trader, risk debaters (aggressive/conservative/neutral), research manager, and portfolio manager.

### Key entry points

- **`cli/main.py`** — Typer-based interactive CLI. `run_analysis()` gathers ticker/date/language/provider/model/depth selections, builds config from `DEFAULT_CONFIG`, and streams the graph with `StatsCallbackHandler` into a Rich live UI.
- **`main.py`** — Minimal programmatic usage example.
- **`EtfAgentsGraph.propagate(ticker, date)`** — Core method returning `(final_state, decision_string)`.

### Graph orchestration

- `etfagents/graph/trading_graph.py` — `TradingAgentsGraph` base class. Pushes config into `etfagents.dataflows.config`, creates quick/deep LLM clients via `etfagents.llm_clients`, resolves deferred reflections via `TradingMemoryLog`, builds structured continuity/lesson/method memory via `AnalysisMemoryStore` and `MemoryContextBuilder`, adds a post-PM memory writer node, and compiles the workflow.
- `etfagents/graph/etf_graph.py` — `EtfAgentsGraph(TradingAgentsGraph)` adds ETF-specific analyst mappings, tool nodes, and `analyze_candidate_pool()` / `replay_candidate_pool()`.
- `etfagents/graph/setup.py` / `etfsetup.py` — LangGraph `StateGraph` assembly: selected analyst nodes run first (sequentially), then bull/bear research debate loops, `Research Manager`, `Trader`, aggressive/conservative/neutral risk debate loop, and `Portfolio Manager`.
- `etfagents/graph/conditional_logic.py` — Controls debate round counts and handoff between stages.
- `etfagents/graph/propagation.py` — Handles graph invocation and state streaming.
- `etfagents/graph/reflection.py` — Manages deferred memory log reflections resolved on later runs.
- `etfagents/graph/signal_processing.py` — Post-processing of allocation signals.
- `etfagents/graph/checkpointer.py` — SQLite-backed checkpoint/resume support.

### LLM provider abstraction

- `etfagents/llm_clients/factory.py` — `create_llm_client(provider, model)` dispatches to provider-specific clients. OpenAI-compatible providers (openai, xai, openrouter, ollama, minimax, vllm) share `OpenAIClient`; Anthropic and Google have dedicated clients.
- Do not instantiate provider-specific LangChain clients directly. Always use `create_llm_client()` — it handles provider differences like OpenAI Responses API normalization and Google `api_key`/thinking-level mapping.

### Data access

- `etfagents/dataflows/interface.py` — `route_to_vendor()` dispatches agent-facing tool calls (e.g. `get_stock_data`, `get_indicators`, `get_news`, `get_etf_holdings`) to vendor implementations based on `data_vendors` + `tool_vendors` config, with fallback across remaining vendors on `DataVendorUnavailable`.
- Vendor implementations: `tushare.py`, `y_finance.py`, `qlib_local.py`, `alpha_vantage*.py`, `brave_news.py`, `opencli_news.py`.
- `opencli_news.py` is a multi-source aggregator (Xueqiu, Weibo, Xiaohongshu, Sina Finance, Google) that dedupes results and expands Chinese tickers into company aliases via Tushare.
- `etfagents/dataflows/config.py` — Global config singleton accessed via `set_config()` / `get_config()`.

### Agent definitions

- `etfagents/agents/analysts/` — Analyst agents (market, news, social media, fundamentals, ETF-specific analysts, broker/stock research).
- `etfagents/agents/researchers/` — Bull and bear researchers for structured debate.
- `etfagents/agents/risk_mgmt/` — Aggressive, conservative, and neutral risk debaters.
- `etfagents/agents/managers/` — Research manager and portfolio manager.
- `etfagents/agents/trader/` — Allocation trader.
- `etfagents/agents/utils/agent_utils.py` — Abstract tool wrappers, debate formatting helpers, localization utilities, snapshot extraction/strip functions.
- `etfagents/agents/utils/agent_states.py` — `InvestDebateState`, `RiskDebateState`, and main `AgentState` TypedDicts.
- `etfagents/agents/utils/state_keys.py` — Canonical state key accessors.
- `etfagents/agents/utils/memory.py` — `TradingMemoryLog` for persistent trading decision memory.
- `etfagents/agents/utils/analysis_memory.py` — Structured `AnalysisMemoryEntry` / `OutcomeLessonEntry` / `MethodPlaybookEntry` storage plus role-aware prompt-brief construction.
- `etfagents/agents/utils/rating.py` — Five-tier rating system (BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL).
- `etfagents/agents/utils/structured.py` — Structured output helpers for manager/trader agents.

### Configuration

- `etfagents/default_config.py` — `DEFAULT_CONFIG` dict. Key fields: `llm_provider`, `deep_think_llm`, `quick_think_llm`, `max_debate_rounds`, `output_language`, `data_vendors`, `tool_vendors`, `checkpoint_enabled`, `memory_log_path`, `memory_mode`, `memory_in_backtest`, `continuity_brief_char_limit`, `lesson_brief_char_limit`, `method_brief_char_limit`, `role_brief_specs`, `report_context_char_limit`, `debate_history_char_limit`.
- CLI memory controls: `etfagents analyze --memory-mode ...`, `etfagents backtest --memory-mode ... [--memory-in-backtest]`, and `etfagents memory promote-playbook --id ...`.
- Config is global state. `set_config(config)` is called by the graph constructors; helpers read via `get_config()`. When mutating nested config, always start from `copy.deepcopy(DEFAULT_CONFIG)` — `DEFAULT_CONFIG.copy()` is shallow.

### Output and localization

- `output_language` affects prompts, report formatting, role labels, rating terms, and snapshot parsing. Internal agent debate stays in English for reasoning quality.
- Use `localize_role_name()`, `localize_label()`, `localize_rating_term()`, `get_language_instruction()`, `normalize_chinese_role_terms()` — never embed alternate Chinese role names by hand.
- Debate outputs carry structured trailer blocks: `Decision Summary`/`决策摘要` and `FEEDBACK SNAPSHOT`/`反馈快照`. Use `extract_analyst_decision_summary()`, `strip_analyst_decision_summary()`, `extract_feedback_snapshot()`, `strip_feedback_snapshot()`, `build_debate_brief()`, `make_display_snapshot()` — no ad-hoc parsing.

### Runtime artifacts

- Logs/reports default to `~/.etfagents/logs` (override with `ETFAGENTS_RESULTS_DIR`). Cache data defaults to `~/.etfagents/cache` (override with `ETFAGENTS_CACHE_DIR`). Legacy `TRADINGAGENTS_*` env vars are supported as fallbacks.
- Snapshot files are workflow artifacts, not just UI formatting. Researchers and risk debaters save full snapshots to disk; managers reload them to synthesize multi-round position reports. Preserve both `*_snapshot` and `*_snapshot_path` state fields.
- Structured memory artifacts live under `<results_dir>/memory/` as NDJSON files per ticker/playbook; live runs use them by default, while backtests keep memory disabled unless explicitly re-enabled in config. Auto-generated playbooks start as `draft` and only enter prompts after explicit promotion. Prompt briefs are built with rule-based summarization and `role_brief_specs`, not an extra summarizer LLM call.

## Key conventions

- Preserve exact ticker symbols including exchange suffixes (`7203.T`, `0700.HK`, `002155.SZ`). CLI normalization only trims and uppercases.
- Prompt context size is intentionally constrained. Use `truncate_for_prompt()` / `truncate_response_for_prompt()` and config limits (`report_context_char_limit`, `debate_history_char_limit`, `memory_min_similarity`) instead of manual slicing.
- The market analyst must cover a fixed indicator set (MACD, RSI, Bollinger, VWMA). If the final report misses coverage, the implementation backfills those tool calls.
- Snapshot files are part of the workflow — researchers/debaters save full snapshots to disk and keep abbreviated versions in state; managers reload full files for synthesis. Preserve both `*_snapshot` and `*_snapshot_path` fields in debate state.
