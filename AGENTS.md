# Repository Guidelines

## Project Structure & Module Organization

ETFAgents is a Python 3.10+ multi-agent ETF research framework. Core package code lives in `etfagents/`: `agents/` contains analyst, researcher, trader, risk, and manager roles; `graph/` contains LangGraph orchestration, checkpointing, replay, and signal processing; `dataflows/` contains market/news vendor integrations; `llm_clients/` normalizes provider access; `backtest/` contains Backtrader-based execution; and `cache_manager.py` provides unified cache statistics and cleanup. The Typer/Rich CLI lives in `cli/`, with subcommand modules in `cli/commands/` and static terminal assets in `cli/static/`. Tests are in `tests/`, examples in `main.py` and `scripts/`, and additional design notes in `docs/`.

## Build, Test, and Development Commands

- `python -m venv .venv && source .venv/bin/activate`: create and activate a local environment.
- `pip install .`: install the package and the `etfagents` console script.
- `python -m cli.main` or `etfagents`: run the interactive CLI.
- `etfagents cache stats`: show cache statistics across all categories.
- `etfagents cache cleanup --days 30`: remove cache entries older than 30 days.
- `etfagents cache clear --type all --yes`: clear all cached data.
- `etfagents backtest --tickers 510300.SH,159915.SZ --benchmark-tickers equal_weight_pool --start-date 2026-01-02 --end-date 2026-03-31`: run a non-interactive candidate-pool backtest.
- `python -m unittest discover -s tests -q`: run the full test suite.
- `python -m unittest tests.test_data_vendor_routing.DataVendorRoutingTests.test_fallback_when_primary_vendor_unavailable -q`: run one focused test.

## Coding Style & Naming Conventions

Follow existing Python style: four-space indentation, snake_case modules/functions, PascalCase classes, and clear constant-like config keys. Prefer repository helpers over ad hoc logic: use `create_llm_client()` for LLMs, `route_to_vendor()` for data access, localization helpers for translated labels, and `copy.deepcopy(DEFAULT_CONFIG)` before mutating config. Preserve full ticker symbols and exchange suffixes such as `510300.SH` or `7203.T`.

## Testing Guidelines

Tests use the standard `unittest` framework with files named `tests/test_*.py` and test classes ending in `Tests` or `Test...`. Add focused tests near the changed behavior, especially for vendor routing, prompt formatting, localization, memory, checkpointing, and backtest signal logic. Mock network, LLM, and vendor calls unless a test is explicitly integration-oriented.

## Commit & Pull Request Guidelines

Recent history uses short imperative commit subjects, sometimes with a conventional prefix, for example `Fix Chinese output paragraph breaks` or `refactor: hoist leaked rating regex to module scope`. Keep commits scoped to one behavior change. Pull requests should describe the user-visible change, list tests run, mention config/env impacts, and include screenshots or sample CLI output when terminal rendering changes.

## Security & Configuration Tips

Copy `.env.example` to `.env` and keep secrets such as `TUSHARE_TOKEN`, provider API keys, and backend URLs out of commits. Runtime logs default to `~/.etfagents/logs`, cache to `~/.etfagents/cache`, and can be overridden with `ETFAGENTS_RESULTS_DIR` and `ETFAGENTS_CACHE_DIR`.

## Project-Wide Rules

These rules apply to every task in this project unless explicitly overridden. Bias toward caution over speed on non-trivial work. Use judgment on trivial tasks.

### Rule 1 - Think Before Coding

State assumptions explicitly. If uncertain, ask rather than guess. Present multiple interpretations when ambiguity exists. Push back when a simpler approach exists. Stop when confused and name what is unclear.

### Rule 2 - Simplicity First

Write the minimum code that solves the problem. Add nothing speculative, no features beyond what was asked, and no abstractions for single-use code. If a senior engineer would call it overcomplicated, simplify.

### Rule 3 - Surgical Changes

Touch only what you must. Clean up only your own mess. Do not improve adjacent code, comments, or formatting. Do not refactor what is not broken. Match existing style.

### Rule 4 - Goal-Driven Execution

Define success criteria and loop until verified. Do not follow steps blindly; define success and iterate. Strong success criteria should support independent progress.

### Rule 5 - Use the Model Only for Judgment Calls

Use the model for classification, drafting, summarization, and extraction. Do not use it for routing, retries, or deterministic transforms. If code can answer, code answers.

### Rule 6 - Token Budgets Are Not Advisory

Per-task budget is 4,000 tokens. Per-session budget is 30,000 tokens. If approaching budget, summarize and start fresh. Surface the breach; do not silently overrun.

### Rule 7 - Surface Conflicts, Do Not Average Them

If two patterns contradict, pick one, favoring the more recent or more tested pattern. Explain why and flag the other for cleanup. Do not blend conflicting patterns.

### Rule 8 - Read Before You Write

Before adding code, read exports, immediate callers, and shared utilities. "Looks orthogonal" is dangerous. If unsure why code is structured a certain way, ask.

### Rule 9 - Tests Verify Intent, Not Just Behavior

Tests must encode why behavior matters, not just what it does. A test that cannot fail when business logic changes is wrong.

### Rule 10 - Checkpoint After Every Significant Step

Summarize what was done, what is verified, and what remains. Do not continue from a state you cannot describe back. If you lose track, stop and restate.

### Rule 11 - Match the Codebase's Conventions, Even If You Disagree

Conformance is more important than taste inside the codebase. If a convention seems genuinely harmful, surface it. Do not fork silently.

### Rule 12 - Fail Loud

"Completed" is wrong if anything was skipped silently. "Tests pass" is wrong if any were skipped. Default to surfacing uncertainty, not hiding it.
