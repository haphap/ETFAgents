/**
 * top_holdings analyst node.
 * Sub-step 3 — created via the shared analyst factory.
 */

import {
  buildTopHoldingsSystemMessage,
  TOP_HOLDINGS_REPORT_SPEC,
} from "../prompts/top_holdings.js";
import { createAnalystNode } from "./analyst_factory.js";
import type { AnalystNodeOptions } from "./market_flow.js";
import { assembleSystemFrame } from "./market_flow.js";

export function createTopHoldingsNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "top_holdings",
      stateKey: "top_holdings_report",
      buildSystemBody: buildTopHoldingsSystemMessage,
      tools: opts.tools,
      reportSpec: TOP_HOLDINGS_REPORT_SPEC,
      memoryRole: { role: "top_holdings", aliases: ["stock_research"] },
    },
    assembleSystemFrame,
  );
}
