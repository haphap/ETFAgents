/**
 * Graph routing and state utilities.
 *
 * Port of ``etfagents.graph.conditional_logic`` routing functions +
 * ``etfagents.graph.signal_processing`` rating parser.
 *
 * Sub-step 3.4 ports the routing machinery needed for the full
 * 6-analyst + debate + risk-debate graph.
 */

import type { AIMessage } from "@langchain/core/messages";
import type { SpineStateType } from "../agents/state.js";

// ===========================================================================
// Analyst tool-loop routing (reusable)
// ===========================================================================

/**
 * Return the tools node if the last message has pending tool calls,
 * otherwise return the next node. Every analyst with a tool loop
 * reuses this pattern.
 */
export function routeAnalystTools(
  state: SpineStateType,
  toolsNode: string,
  continueNode: string,
): string {
  const last = state.messages[state.messages.length - 1] as AIMessage | undefined;
  return (last?.tool_calls?.length ?? 0) > 0 ? toolsNode : continueNode;
}

// ===========================================================================
// Debate routing (bull ↔ bear → research_manager)
// ===========================================================================

export interface DebateRoutingState {
  /** Number of debate rounds completed (2 messages per round). */
  count: number;
  /** Which researcher spoke last (starts with "Bull" or "Bear"). */
  latestSpeaker: string;
}

export function routeDebate(
  debateState: DebateRoutingState,
  maxDebateRounds: number,
): "Bull Researcher" | "Bear Researcher" | "Research Manager" {
  if (debateState.count >= 2 * maxDebateRounds) {
    return "Research Manager";
  }
  if (debateState.latestSpeaker.startsWith("Bull")) {
    return "Bear Researcher";
  }
  return "Bull Researcher";
}

// ===========================================================================
// Risk-debate routing (aggressive → conservative → neutral → PM)
// ===========================================================================

export interface RiskDebateRoutingState {
  count: number;
  latestSpeaker: string;
}

export function routeRiskDebate(
  debateState: RiskDebateRoutingState,
  maxRiskDiscussRounds: number,
): "Aggressive Analyst" | "Conservative Analyst" | "Neutral Analyst" | "Portfolio Manager" {
  if (debateState.count >= 3 * maxRiskDiscussRounds) {
    return "Portfolio Manager";
  }
  if (debateState.latestSpeaker.startsWith("Aggressive")) {
    return "Conservative Analyst";
  }
  if (debateState.latestSpeaker.startsWith("Conservative")) {
    return "Neutral Analyst";
  }
  return "Aggressive Analyst";
}

// ===========================================================================
// Signal processing (trivial — parse rating from trader output)
// ===========================================================================

const RATING_KEYWORDS: ReadonlyArray<readonly [string, RegExp]> = [
  ["Buy", /(?:buy|买入)/i],
  ["Overweight", /(?:overweight|增持)/i],
  ["Hold", /(?:hold|持有)/i],
  ["Underweight", /(?:underweight|减持)/i],
  ["Sell", /(?:sell|卖出)/i],
];

export function parseSignalRating(fullSignal: string): string {
  for (const [rating, pattern] of RATING_KEYWORDS) {
    if (pattern.test(fullSignal)) return rating;
  }
  return "Hold";
}
