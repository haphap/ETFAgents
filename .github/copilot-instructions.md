# ETFAgents Copilot Instructions

## Commands

- Install from source: `pip install .`
- Run the interactive CLI from source: `python -m cli.main`
- Run the installed CLI entrypoint: `etfagents`
- Run the test suite: `python -m unittest discover -s tests -q`
- Run a single test: `python -m unittest tests.test_data_vendor_routing.DataVendorRoutingTests.test_fallback_when_primary_vendor_unavailable -q`

## Architecture

- `cli.main` is the operational entrypoint. `run_analysis()` gathers ticker/date/language/provider/model/depth selections, normalizes analyst order, builds a config from `DEFAULT_CONFIG`, and streams the graph with `StatsCallbackHandler` into the Rich live UI.
- `cli.main` runs the ETF workflow through `etfagents.graph.etf_graph.EtfAgentsGraph`. The shared base orchestrator remains `etfagents.graph.trading_graph.TradingAgentsGraph`, which pushes config into `etfagents.dataflows.config`, creates quick/deep LLM clients through `etfagents.llm_clients`, resolves and stores deferred reflections through `etfagents.agents.utils.memory.TradingMemoryLog`, builds LangGraph tool nodes from the abstract tool wrappers in `etfagents.agents.utils.agent_utils`, and compiles the workflow.
- The LangGraph workflow is assembled in `etfagents/graph/setup.py`: selected analyst nodes run first and sequentially, then the bull/bear research debate loops until `ConditionalLogic` hands off to `Research Manager`, then `Trader`, then the aggressive/conservative/neutral risk loop, and finally `Portfolio Manager`.
- Data access is routed through `etfagents.dataflows.interface.route_to_vendor()`. Agent-facing tools like `get_stock_data`, `get_indicators`, `get_news`, and `get_fundamentals` are vendor-agnostic wrappers; vendor choice comes from global `data_vendors` plus per-tool `tool_vendors`, and routing falls back across remaining vendors on `DataVendorUnavailable`.
- Runtime artifacts are rooted at `results_dir` (default `~/.etfagents/logs`). The CLI writes streaming logs, report sections, and snapshots under `<results_dir>/<ticker>/<date>/`; snapshot helpers save full markdown snapshots there; `TradingAgentsGraph._log_state()` writes JSON state logs under `<results_dir>/<ticker>/ETFAgentsStrategy_logs/`.
- `etfagents.dataflows.opencli_news` is a multi-source aggregator, not a single API call. It fans out to Xueqiu, Weibo, Xiaohongshu, Sina Finance, and Google commands, dedupes results, and expands Chinese tickers into company aliases via Tushare before querying.

## Key conventions

- Preserve exact ticker symbols, including exchange suffixes (`7203.T`, `0700.HK`, `002155.SZ`). CLI normalization only trims and uppercases; prompts, vendor routing, and instrument context depend on the full symbol.
- Config is global state. `EtfAgentsGraph` and the shared `TradingAgentsGraph` base call `set_config(config)`, and helpers read through `get_config()`. When mutating nested config in code or tests, start from `copy.deepcopy(DEFAULT_CONFIG)` or replace nested dicts before editing; `DEFAULT_CONFIG.copy()` is shallow.
- Do not instantiate provider-specific LangChain clients directly in graph or agent code. Use `create_llm_client()` plus the normalized wrappers in `etfagents.llm_clients`; they hide provider differences such as OpenAI Responses API content normalization, OpenAI-compatible base URLs, and Google `api_key` / thinking-level mapping.
- User-visible debate outputs intentionally carry structured trailer blocks: `Decision Summary` / `决策摘要` and `FEEDBACK SNAPSHOT` / `反馈快照`. Use helpers like `extract_analyst_decision_summary()`, `strip_analyst_decision_summary()`, `extract_feedback_snapshot()`, `strip_feedback_snapshot()`, `build_debate_brief()`, and `make_display_snapshot()` instead of ad hoc parsing.
- Snapshot files are part of the workflow, not just UI formatting. Researchers and risk debaters save full snapshots to disk, keep abbreviated versions in state, and managers reload the full files to synthesize multi-round position reports. Preserve both the `*_snapshot` and `*_snapshot_path` fields when changing debate state.
- Localization is helper-driven. `output_language` affects prompts, report formatting, role labels, rating terms, and snapshot parsing. Use `localize_role_name()`, `localize_label()`, `localize_rating_term()`, `get_language_instruction()`, and `normalize_chinese_role_terms()` instead of embedding alternate Chinese role names by hand.
- Debate history format matters to the CLI. `format_research_team_history()` and `format_risk_management_history()` expect speaker-prefixed turns with structured snapshot blocks preserved, then render round-by-round output by splitting the visible body from decision-summary/snapshot metadata with the helper functions.
- Prompt context size is intentionally constrained. Use `truncate_for_prompt()` / `truncate_response_for_prompt()` and the config limits (`report_context_char_limit`, `debate_history_char_limit`, `memory_min_similarity`) instead of manual slicing or separate memory plumbing.
- The market analyst is expected to cover a fixed indicator set. If the final report misses MACD/RSI/Bollinger/VWMA coverage, the implementation backfills those tool calls before producing `market_report`.
