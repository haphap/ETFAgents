/**
 * Portfolio Manager node — Phase 2 sub-step 3.3.
 *
 * Wires the portfolio manager prompt through the shared analyst-node
 * factory (createAnalystNode).  The Portfolio Manager synthesizes
 * the full risk debate and delivers the final ETF portfolio
 * allocation decision (``final_allocation_decision``).
 */

import { buildPortfolioManagerContext } from "../helpers/debate_context.js";
import {
  buildPortfolioManagerSystemMessage,
  PORTFOLIO_MANAGER_REPORT_SPEC,
} from "../prompts/portfolio_manager.js";
import { createAnalystNode } from "./analyst_factory.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createPortfolioManagerNode(opts: AnalystNodeOptions) {
  return createAnalystNode(
    opts.llm,
    opts.promptContext,
    {
      name: "portfolio_manager",
      stateKey: "final_allocation_decision",
      buildSystemBody: (ctx) => buildPortfolioManagerSystemMessage(ctx),
      tools: opts.tools,
      reportSpec: PORTFOLIO_MANAGER_REPORT_SPEC,
      memoryRole: { role: "portfolio_manager" },
      buildContextBlock: buildPortfolioManagerContext,
    },
    assembleSystemFrame,
  );
}
