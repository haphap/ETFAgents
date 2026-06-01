/**
 * Memory Writer node — graph-end write-back, mirroring Python's
 * ``create_memory_writer`` (Portfolio Manager → Memory Writer → END).
 *
 * The node assembles a Python-compatible state payload (snake_case keys, the
 * shape ``build_analysis_memory_entry`` expects) and hands it to an optional
 * ``persist`` callback — wired by the caller to the bridge
 * ``memory.append_analysis`` RPC, which builds and stores the entry using the
 * existing Python AnalysisMemoryStore. The returned entry dict is written to
 * ``analysis_memory_entry`` so it is visible in the final state.
 *
 * When no ``persist`` callback is supplied (e.g. tests, or a caller that opts
 * out), the node is a no-op that leaves ``analysis_memory_entry`` empty —
 * keeping the graph topology identical regardless of persistence wiring.
 */

import type { SpineStateType, SpineStateUpdate } from "../state.js";

/** Persist callback: receives the Python-shaped state payload, returns the stored entry. */
export type PersistMemory = (payload: Record<string, unknown>) => Promise<Record<string, unknown>>;

/**
 * Overlay provider/model/round overrides onto the bridge config so memory
 * write-back's config hash describes the run that actually executed. Mirrors
 * the keys ETFAgents' config hash reads (llm_provider, deep_think_llm,
 * max_debate_rounds, max_risk_discuss_rounds).
 */
export function buildEffectiveMemoryConfig(
  config: Record<string, unknown>,
  opts: { provider?: string; model?: string; debateRounds: number; riskRounds: number },
): Record<string, unknown> {
  return {
    ...config,
    ...(opts.provider ? { llm_provider: opts.provider } : {}),
    ...(opts.model ? { deep_think_llm: opts.model } : {}),
    max_debate_rounds: opts.debateRounds,
    max_risk_discuss_rounds: opts.riskRounds,
  };
}

/** Build the snake_case state payload that build_analysis_memory_entry reads. */
export function buildMemoryPayload(state: SpineStateType): Record<string, unknown> {
  const inv = state.investment_debate_state;
  const risk = state.risk_debate_state;
  return {
    asset_of_interest: state.asset_of_interest,
    trade_date: state.trade_date,
    market_flow_report: state.market_flow_report,
    catalyst_sentiment_report: state.catalyst_sentiment_report,
    macro_regime_report: state.macro_regime_report,
    meso_commodity_report: state.meso_commodity_report,
    holdings_industry_report: state.holdings_industry_report,
    top_holdings_report: state.top_holdings_report,
    research_allocation_plan: state.research_allocation_plan,
    trader_allocation_plan: state.trader_allocation_plan,
    final_allocation_decision: state.final_allocation_decision,
    // Intentionally NOT sending trader_backtest_signal: the TS portfolio
    // manager produces no structured signal, and build_state_backtest_signal
    // prefers trader_backtest_signal over final_allocation_decision. Omitting it
    // lets Python derive the stored signal from the PM's final decision (the
    // actual outcome) instead of the trader's earlier view.
    investment_debate_state: {
      current_bull_response: inv.currentBullResponse,
      current_bear_response: inv.currentBearResponse,
    },
    risk_debate_state: {
      current_aggressive_response: risk.currentAggressiveResponse,
      current_conservative_response: risk.currentConservativeResponse,
      current_neutral_response: risk.currentNeutralResponse,
    },
  };
}

export function createMemoryWriterNode(opts: {
  persist?: PersistMemory;
  selectedAnalysts?: readonly string[];
  /** Effective runtime config forwarded to the store (memory_mode, results_dir, …). */
  config?: Record<string, unknown>;
}) {
  return async function memoryWriterNode(state: SpineStateType): Promise<SpineStateUpdate> {
    if (!opts.persist) return {} as SpineStateUpdate;
    try {
      const entry = await opts.persist({
        state: buildMemoryPayload(state),
        selected_analysts: opts.selectedAnalysts ?? null,
        ...(opts.config ? { config: opts.config } : {}),
      });
      return { analysis_memory_entry: entry } as SpineStateUpdate;
    } catch {
      // Persistence is best-effort: never fail the run because memory write failed.
      return {} as SpineStateUpdate;
    }
  };
}
