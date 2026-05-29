/**
 * holdings_industry analyst node.
 * Sub-step 3 — created via the shared analyst factory.
 */

import {
  buildHoldingsIndustrySystemMessage,
  HOLDINGS_INDUSTRY_REPORT_SPEC,
} from "../prompts/holdings_industry.js";
import { createAnalystNode } from "./analyst_factory.js";
import type { AnalystNodeOptions } from "./market_flow.js";
import { assembleSystemFrame } from "./market_flow.js";

export function createHoldingsIndustryNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "holdings_industry",
      stateKey: "holdings_industry_report",
      buildSystemBody: buildHoldingsIndustrySystemMessage,
      tools: opts.tools,
      reportSpec: HOLDINGS_INDUSTRY_REPORT_SPEC,
      memoryRole: { role: "holdings_industry", aliases: ["industry_research"] },
    },
    assembleSystemFrame,
  );
}
