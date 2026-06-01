/**
 * Research Manager node — Phase 2 sub-step 3.2.
 *
 * Wires the research manager prompt through the shared analyst-node
 * factory (createAnalystNode).  The Research Manager evaluates the
 * full Bull vs Bear debate and produces the ``research_allocation_plan``.
 */

import { buildResearchManagerContext } from "../helpers/debate_context.js";
import {
  buildResearchManagerSystemMessage,
  RESEARCH_MANAGER_REPORT_SPEC,
} from "../prompts/research_manager.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createResearchManagerNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "research_manager",
      stateKey: "research_allocation_plan",
      buildSystemBody: (ctx) => buildResearchManagerSystemMessage(ctx),
      tools: opts.tools,
      reportSpec: RESEARCH_MANAGER_REPORT_SPEC,
      memoryRole: { role: "research_manager" },
      buildContextBlock: buildResearchManagerContext,
      appendMessage: false,
    },
    assembleSystemFrame,
  );
}
