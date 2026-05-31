/**
 * Bull Researcher node — Phase 2 sub-step 3.2.
 *
 * Wires the bull researcher prompt through the shared analyst-node
 * factory (createAnalystNode).  The bull researcher advocates for
 * increasing ETF exposure.
 */

import { buildBullContext } from "../helpers/debate_context.js";
import { BULL_REPORT_SPEC, buildBullResearcherSystemMessage } from "../prompts/bull_researcher.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createBullResearcherNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "bull_researcher",
      stateKey: "bull_researcher_report",
      buildSystemBody: (ctx) => buildBullResearcherSystemMessage(ctx),
      tools: opts.tools,
      reportSpec: BULL_REPORT_SPEC,
      memoryRole: { role: "bull" },
      buildContextBlock: buildBullContext,
    },
    assembleSystemFrame,
  );
}
