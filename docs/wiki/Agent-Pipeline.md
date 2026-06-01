# Agent Pipeline

The full pipeline is a LangGraph.js graph assembled in
`ts/src/graph/full_graph.ts` (`buildFullGraph`). It mirrors the Python
`EtfAgentsGraph`.

```text
START
 → market_flow → catalyst_sentiment → macro_regime → meso_commodity
 → holdings_industry → top_holdings                         (6 analysts)
 → bull_researcher ⇄ bear_researcher → research_manager     (research debate)
 → trader
 → aggressive_debator → conservative_debator → neutral_debator → portfolio_manager   (risk debate)
 → memory_writer → END
```

## Analysts (6)

| id                   | focus (中文)        |
| -------------------- | ------------------- |
| `market_flow`        | 市场与资金流        |
| `catalyst_sentiment` | 舆情与事件          |
| `macro_regime`       | 宏观框架            |
| `meso_commodity`     | 中观大宗            |
| `holdings_industry`  | 持仓行业            |
| `top_holdings`       | 头部持仓            |

- Order mirrors Python `ETFGraphSetup.DEFAULT_SELECTED_ANALYSTS`.
- Tool-using analysts run a **tool loop** (`analyst → ToolNode → analyst`) via
  `routeAnalystTools`. `catalyst_sentiment` is a **deterministic pre-fetch**
  analyst (ETF info/holdings + ticker/holdings/global news), matching Python's
  `create_social_media_analyst` — no tool loop.
- A **Msg Clear** node runs after each analyst to reset the message history, so
  one analyst's tool chatter never bloats the next (report content survives in
  the `*_report` state keys).

## Research debate → manager → trader

- `bull_researcher` and `bear_researcher` loop via `routeDebate` until
  `count >= 2 * maxDebateRounds`, then hand off to `research_manager`.
- `research_manager` produces `research_allocation_plan`; `trader` produces
  `trader_allocation_plan` + a structured `trader_backtest_signal`.

## Risk debate → portfolio manager

- `aggressive_debator → conservative_debator → neutral_debator` loop via
  `routeRiskDebate` until `count >= 3 * maxRiskRounds`, then
  `portfolio_manager` produces `final_allocation_decision`.

## Debate state

`investment_debate_state` / `risk_debate_state` carry `{ count, latestSpeaker,
history, per-role histories, current responses, judgeDecision }`. The
`withDebateTurn` wrapper advances the counter every turn (so the loop always
terminates), and `withManagerJudge` records each manager's decision +
`latestSpeaker`. Debators/managers do **not** append chat messages; they read
explicit context blocks built by `ts/src/agents/helpers/debate_context.ts`.

## LLM tiers

Quick LLM for analysts / researchers / risk debators; deep LLM for the research
manager, trader, and portfolio manager — matching Python's quick/deep split.
A `--model` override applies to both tiers.

## Memory (read + write)

- **Read**: before a run, `memory.build_context` returns per-role
  continuity / lesson / method context, injected into the graph initial state.
- **Write**: at graph end, the `memory_writer` node persists an
  `analysis_memory_entry` via `memory.append_analysis` (best-effort).

## Configurable controls

`maxDebateRounds`, `maxRiskRounds`, and `selectedAnalysts` are passed into
`buildFullGraph` (the TUI exposes them in the config screen). An empty analyst
selection is rejected; unknown ids are rejected and duplicates are deduped.
