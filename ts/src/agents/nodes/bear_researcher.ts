/**
 * Bear Researcher node — Phase 2 sub-step 3.2.
 *
 * Wires the bear researcher prompt through the shared analyst-node
 * factory (createAnalystNode).  The bear researcher makes the case
 * against increasing ETF exposure.
 */

import { buildBearContext } from "../helpers/debate_context.js";
import { BEAR_REPORT_SPEC, buildBearResearcherSystemMessage } from "../prompts/bear_researcher.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createBearResearcherNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "bear_researcher",
      stateKey: "bear_researcher_report",
      buildSystemBody: (ctx) => buildBearResearcherSystemMessage(ctx),
      tools: opts.tools,
      reportSpec: BEAR_REPORT_SPEC,
      memoryRole: { role: "bear" },
      buildContextBlock: buildBearContext,
    },
    assembleSystemFrame,
  );
}
