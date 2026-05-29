/**
 * meso_commodity (commodity cluster) analyst node.
 * Sub-step 3 — created via the shared analyst factory.
 */

import {
  buildMesoCommoditySystemMessage,
  MESO_COMMODITY_REPORT_SPEC,
} from "../prompts/meso_commodity.js";
import { createAnalystNode } from "./analyst_factory.js";
import type { AnalystNodeOptions } from "./market_flow.js";
import { assembleSystemFrame } from "./market_flow.js";

export function createMesoCommodityNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "meso_commodity",
      stateKey: "meso_commodity_report",
      buildSystemBody: buildMesoCommoditySystemMessage,
      tools: opts.tools,
      reportSpec: MESO_COMMODITY_REPORT_SPEC,
      memoryRole: { role: "meso_commodity", aliases: ["etf_structure"] },
    },
    assembleSystemFrame,
  );
}
