/**
 * Conservative Debator node — Phase 2 sub-step 3.2.
 *
 * Wires the conservative risk debator prompt through the shared
 * analyst-node factory (createAnalystNode).  The Conservative
 * Analyst prioritizes protecting assets and minimizing volatility.
 *
 * Debators typically have no tools; pass an empty array.
 */

import {
  buildConservativeDebatorSystemMessage,
  CONSERVATIVE_DEBATOR_REPORT_SPEC,
} from "../prompts/conservative_debator.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createConservativeDebatorNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "conservative_debator",
      stateKey: "conservative_debator_response",
      buildSystemBody: (ctx) => buildConservativeDebatorSystemMessage(ctx),
      tools: opts.tools,
      reportSpec: CONSERVATIVE_DEBATOR_REPORT_SPEC,
      memoryRole: { role: "conservative" },
    },
    assembleSystemFrame,
  );
}
