/**
 * State annotation for the market_flow → trader spine (Phase 2 sub-step 1).
 *
 * Mirrors the canonical keys read/written along this slice of AgentState in
 * ``etfagents/agents/utils/agent_states.py``. Legacy aliases (e.g. market_report,
 * etf_flow_report) are NOT mirrored on the TS side — the bridge boundary uses
 * canonical names only. If the TS state ever needs to round-trip with Python,
 * apply ``with_state_aliases`` on the bridge boundary.
 */

import { Annotation, MessagesAnnotation } from "@langchain/langgraph";

/** Accumulating debate accounting shared by the research and risk debates. */
export interface DebateState {
  /** Number of completed debator turns. */
  count: number;
  /** Role label of the most recent speaker (e.g. "Bull", "Aggressive"). */
  latestSpeaker: string;
  /** Concatenated debate transcript, appended one turn at a time. */
  history: string;
}

export const SpineState = Annotation.Root({
  ...MessagesAnnotation.spec,

  asset_of_interest: Annotation<string>(),
  trade_date: Annotation<string>(),

  // Reports written by analysts; downstream nodes read with empty-string
  // defaults so missing reports do not break trader.
  market_flow_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  catalyst_sentiment_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  macro_regime_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  meso_commodity_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  holdings_industry_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  top_holdings_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),

  research_allocation_plan: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),

  // Trader outputs
  trader_allocation_plan: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  trader_backtest_signal: Annotation<Record<string, unknown>>({
    reducer: (_prev, next) => next,
    default: () => ({}),
  }),

  sender: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),

  // Researcher/Debator reports (Phase 2 sub-step 3.2-3.3)
  bull_researcher_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  bear_researcher_report: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  // Multi-round debate accounting. `count` is the number of completed turns
  // (bull+bear, or aggressive+conservative+neutral); `latestSpeaker` drives the
  // conditional routers (routeDebate / routeRiskDebate). Mirrors the Python
  // investment_debate_state / risk_debate_state used by ConditionalLogic.
  investment_debate_state: Annotation<DebateState>({
    reducer: (_prev, next) => next,
    default: () => ({ count: 0, latestSpeaker: "", history: "" }),
  }),
  risk_debate_state: Annotation<DebateState>({
    reducer: (_prev, next) => next,
    default: () => ({ count: 0, latestSpeaker: "", history: "" }),
  }),
  aggressive_debator_response: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  conservative_debator_response: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  neutral_debator_response: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),
  final_allocation_decision: Annotation<string>({
    reducer: (_prev, next) => next,
    default: () => "",
  }),

  // Memory context (populated by Python AnalysisMemoryStore in sub-step 4).
  // Each dict is keyed by role name → context string.
  continuity_context: Annotation<Record<string, string>>({
    reducer: (_prev, next) => next,
    default: () => ({}),
  }),
  lesson_context: Annotation<Record<string, string>>({
    reducer: (_prev, next) => next,
    default: () => ({}),
  }),
  method_context: Annotation<Record<string, string>>({
    reducer: (_prev, next) => next,
    default: () => ({}),
  }),
});

export type SpineStateType = typeof SpineState.State;
export type SpineStateUpdate = typeof SpineState.Update;
