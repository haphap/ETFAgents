# ETFAgents Copilot Instructions

## Build and test commands

- Install from source: `pip install .`
- Run the interactive CLI from source: `python -m cli.main`
- Run the installed CLI entrypoint: `etfagents`
- Run the full test suite: `python -m unittest discover -s tests -q`
- Run a single test: `python -m unittest tests.test_data_vendor_routing.DataVendorRoutingTests.test_fallback_when_primary_vendor_unavailable -q`

## High-level architecture

- `cli/main.py` is the operational entrypoint. `run_analysis()` gathers ticker/date/provider/model/depth/language/analyst selections, starts from `copy.deepcopy(DEFAULT_CONFIG)`, normalizes analyst aliases/order, and streams the graph through the Rich terminal UI via `StatsCallbackHandler`.
- `etfagents.graph.etf_graph.EtfAgentsGraph` is the ETF-specific facade. It inherits the shared runtime from `TradingAgentsGraph`, swaps in ETF tool nodes and ETF-default vendor config, normalizes legacy analyst aliases to canonical ETF roles, and also owns candidate-pool ranking and historical replay helpers.
- `etfagents.graph.trading_graph.TradingAgentsGraph` is the runtime spine. It deep-copies config, calls `set_config(config)` so helpers can read global runtime settings, creates quick/deep LLMs through `etfagents.llm_clients.create_llm_client()`, wires memory via `TradingMemoryLog`, compiles the LangGraph workflow, optionally recompiles it with a SQLite checkpointer, and persists final state logs plus memory entries.
- `etfagents/graph/setup.py` assembles the graph shape: selected analyst nodes run sequentially, then the bull/bear research loop hands off to `Research Manager`, then `Trader`, then the aggressive/conservative/neutral risk loop, and finally `Portfolio Manager`.
- `etfagents/graph/propagation.py` seeds the workflow state with both report slots and nested debate state objects. Those state objects include `*_snapshot` and `*_snapshot_path` fields that later manager nodes and CLI rendering depend on.
- `etfagents.dataflows.interface.route_to_vendor()` is the single routing layer for agent-facing tools. Category defaults come from `data_vendors`, tool-specific overrides come from `tool_vendors`, Chinese tickers are reordered toward China/local vendors first, and failures fall through a vendor chain on `DataVendorUnavailable`.
- Runtime artifacts are split across `results_dir` and `data_cache_dir`. The CLI writes reports and snapshots under `<results_dir>/<ticker>/<date>/`; `TradingAgentsGraph._log_state()` writes JSON state logs under `<results_dir>/<ticker>/ETFAgentsStrategy_logs/`; checkpoint databases live under `<data_cache_dir>/checkpoints/`.
- `etfagents.dataflows.opencli_news` is a multi-source aggregator rather than a single API call. It fans out to Xueqiu, Weibo, Xiaohongshu, Sina Finance, and Google commands, dedupes the results, and expands Chinese tickers into company aliases via Tushare before querying.

## Key conventions

- Preserve exact ticker symbols, including exchange suffixes (`7203.T`, `0700.HK`, `002155.SZ`). CLI normalization only trims and uppercases; prompts, instrument context, and vendor routing depend on the full symbol.
- Do not mutate `DEFAULT_CONFIG` via a shallow copy. The nested vendor maps are mutable, so start from `copy.deepcopy(DEFAULT_CONFIG)` or replace nested dicts before editing them.
- Treat config as global runtime state. Graph constructors call `set_config()`, and helpers read through `get_config()`.
- Do not instantiate provider-specific LangChain clients directly in graph or agent code. Use `create_llm_client()` so OpenAI-compatible backends, Google thinking-level mapping, Anthropic effort, and base-URL handling stay normalized.
- The ETF workflow still accepts legacy analyst names, but it normalizes them to canonical ETF roles (`market_flow`, `catalyst_sentiment`, `macro_regime`, `meso_commodity`, `holdings_industry`, `top_holdings`). Reuse the alias/normalization helpers instead of hardcoding both naming schemes.
- Broker/stock research are A-share-only in the shared graph. `resolve_selected_analysts()` filters those analysts out for non-A-share tickers instead of forcing each caller to special-case that compatibility check.
- User-visible debate outputs intentionally carry structured trailer blocks: `DECISION SUMMARY` / `决策摘要` and `FEEDBACK SNAPSHOT` / `反馈快照`. Use helpers like `extract_analyst_decision_summary()`, `strip_analyst_decision_summary()`, `extract_feedback_snapshot()`, `strip_feedback_snapshot()`, `build_debate_brief()`, `make_display_snapshot()`, `format_research_team_history()`, and `format_risk_management_history()` instead of ad hoc parsing.
- Snapshot files are workflow artifacts, not just UI formatting. Researchers and risk debaters save full snapshots to disk, keep abbreviated versions in state, and managers reload the full files to synthesize multi-round position reports. Preserve both the `*_snapshot` and `*_snapshot_path` fields when changing debate state.
- Localization is helper-driven. `output_language` affects prompts, role labels, rating terms, heading numbering, and snapshot/history formatting. Use `localize_role_name()`, `localize_label()`, `localize_rating_term()`, `get_language_instruction()`, and `normalize_chinese_role_terms()` instead of embedding bilingual strings by hand.
- Prompt context size is intentionally constrained. Use `truncate_for_prompt()` / `truncate_response_for_prompt()` and the config limits (`report_context_char_limit`, `debate_history_char_limit`, `memory_min_similarity`) instead of manual slicing or separate memory plumbing.
- The market/flow analyst is expected to cover a fixed indicator set. If the final report misses MACD, RSI, Bollinger, or VWMA coverage, the implementation backfills those tool calls before finalizing `market_flow_report`.
