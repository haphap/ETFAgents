/**
 * Neutral Debator node — Phase 2 sub-step 3.2.
 *
 * Wires the neutral risk debator prompt through the shared
 * analyst-node factory (createAnalystNode).  The Neutral
 * Analyst provides a balanced perspective, weighing both
 * benefits and risks.
 *
 * Debators typically have no tools; pass an empty array.
 */

import {
  buildNeutralDebatorSystemMessage,
  NEUTRAL_DEBATOR_REPORT_SPEC,
} from "../prompts/neutral_debator.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createNeutralDebatorNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "neutral_debator",
      stateKey: "neutral_debator_response",
      buildSystemBody: (ctx) => buildNeutralDebatorSystemMessage(ctx),
      tools: opts.tools,
      reportSpec: NEUTRAL_DEBATOR_REPORT_SPEC,
      memoryRole: { role: "neutral" },
    },
    assembleSystemFrame,
  );
}
