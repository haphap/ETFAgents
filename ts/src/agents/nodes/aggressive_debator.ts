/**
 * Aggressive Debator node — Phase 2 sub-step 3.2.
 *
 * Wires the aggressive risk debator prompt through the shared
 * analyst-node factory (createAnalystNode).  The Aggressive
 * Analyst champions high-reward ETF allocation opportunities.
 *
 * Debators typically have no tools; pass an empty array.
 */

import {
  AGGRESSIVE_DEBATOR_REPORT_SPEC,
  buildAggressiveDebatorSystemMessage,
} from "../prompts/aggressive_debator.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createAggressiveDebatorNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "aggressive_debator",
      stateKey: "aggressive_debator_response",
      buildSystemBody: (ctx) => buildAggressiveDebatorSystemMessage(ctx),
      tools: opts.tools,
      reportSpec: AGGRESSIVE_DEBATOR_REPORT_SPEC,
      memoryRole: { role: "aggressive" },
    },
    assembleSystemFrame,
  );
}
