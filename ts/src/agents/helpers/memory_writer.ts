/**
 * Memory write path helpers (bridge RPC stubs).
 *
 * Port of ``etfagents.agents.utils.analysis_memory`` write-side
 * and ``etfagents.agents.utils.memory.TradingMemoryLog``.
 *
 * Sub-step 4: TS-side plumbing that calls Python bridge RPCs for
 * persistent memory storage. RPC methods implemented in Python
 * bridge handlers (``analysis_memory.store_decision``, etc.).
 */

import type { BacktestSignal } from "./backtest_signal.js";

// ===========================================================================
// Bridge RPC stubs (deferred to Python sidecar implementation)
// ===========================================================================

/**
 * Store a trader decision in the analysis memory store.
 * RPC: ``analysis_memory.store_decision``
 */
export async function storeMemoryDecision(
  ticker: string,
  decisionDate: string,
  renderedPlan: string,
  signal: BacktestSignal,
): Promise<void> {
  // Bridge RPC: POST analysis_memory.store_decision
  // Payload: { ticker, decision_date, rendered_plan, signal }
  // Deferred until Python AnalysisMemoryStore RPC handler is ready.
  void ticker;
  void decisionDate;
  void renderedPlan;
  void signal;
}

/**
 * Store a post-trade reflection in the memory log.
 * RPC: ``analysis_memory.append_outcome``
 */
export async function storeOutcomeReflection(
  ticker: string,
  decisionDate: string,
  reflection: string,
  rawReturn: number,
  alphaReturn: number,
): Promise<void> {
  void ticker;
  void decisionDate;
  void reflection;
  void rawReturn;
  void alphaReturn;
}

// ===========================================================================
// In-memory cache (fallback when bridge is unavailable)
// ===========================================================================

const pendingDecisions: Array<{
  ticker: string;
  date: string;
  plan: string;
  signal: BacktestSignal;
}> = [];

export function cachePendingDecision(
  ticker: string,
  date: string,
  plan: string,
  signal: BacktestSignal,
): void {
  pendingDecisions.push({ ticker, date, plan, signal });
}

export function getCachedDecisions(): ReadonlyArray<{
  ticker: string;
  date: string;
  plan: string;
  signal: BacktestSignal;
}> {
  return pendingDecisions;
}

export function clearCachedDecisions(): void {
  pendingDecisions.length = 0;
}
