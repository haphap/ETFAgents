/**
 * Full analysis graph with 6 parallel analysts → trader.
 *
 * Phase 2 sub-step 3.5: sequential pipeline (parallel fan-out deferred to
 * Phase 3 when the Ink TUI needs streaming progress per analyst).
 *
 *   START → market_flow → macro_regime → meso_commodity →
 *           catalyst_sentiment → holdings_industry → top_holdings →
 *           trader → END
 *
 * Debate flow (bull/bear/research_manager) and risk-debate flow
 * (aggressive/conservative/neutral → portfolio_manager) deferred.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { AIMessage } from "@langchain/core/messages";
import type { StructuredToolInterface } from "@langchain/core/tools";
import { END, START, StateGraph } from "@langchain/langgraph";
import { ToolNode } from "@langchain/langgraph/prebuilt";
import { createAggressiveDebatorNode } from "../agents/nodes/aggressive_debator.js";
import { createBearResearcherNode } from "../agents/nodes/bear_researcher.js";
import { createBullResearcherNode } from "../agents/nodes/bull_researcher.js";
import { createCatalystSentimentNode } from "../agents/nodes/catalyst_sentiment.js";
import { createConservativeDebatorNode } from "../agents/nodes/conservative_debator.js";
import { createHoldingsIndustryNode } from "../agents/nodes/holdings_industry.js";
import { createMacroRegimeNode } from "../agents/nodes/macro_regime.js";
import type { AnalystNodeOptions } from "../agents/nodes/market_flow.js";
import { createMarketFlowNode } from "../agents/nodes/market_flow.js";
import { createMesoCommodityNode } from "../agents/nodes/meso_commodity.js";
import { createNeutralDebatorNode } from "../agents/nodes/neutral_debator.js";
import { createPortfolioManagerNode } from "../agents/nodes/portfolio_manager.js";
import { createResearchManagerNode } from "../agents/nodes/research_manager.js";
import { createTopHoldingsNode } from "../agents/nodes/top_holdings.js";
import { createTraderNode } from "../agents/nodes/trader.js";
import type { PromptContext } from "../agents/prompts/shared.js";
import { SpineState, type SpineStateType } from "../agents/state.js";

// ===========================================================================
// Tool sets
// ===========================================================================

export interface FullGraphToolSets {
  marketFlow: ReadonlyArray<StructuredToolInterface>;
  macroRegime: ReadonlyArray<StructuredToolInterface>;
  mesoCommodity: ReadonlyArray<StructuredToolInterface>;
  catalystSentiment: ReadonlyArray<StructuredToolInterface>;
  holdingsIndustry: ReadonlyArray<StructuredToolInterface>;
  topHoldings: ReadonlyArray<StructuredToolInterface>;
  bullBear: ReadonlyArray<StructuredToolInterface>;
  riskDebate: ReadonlyArray<StructuredToolInterface>;
}

export interface BuildFullGraphOptions {
  llm: BaseChatModel;
  tools: FullGraphToolSets;
  promptContext: PromptContext;
}

// ===========================================================================
// Graph builder
// ===========================================================================

export function buildFullGraph(opts: BuildFullGraphOptions) {
  const ctx = opts.promptContext;

  // --- Analyst nodes ---
  const marketFlow = createMarketFlowNode({
    llm: opts.llm,
    tools: opts.tools.marketFlow,
    promptContext: ctx,
  });
  const macroRegime = createMacroRegimeNode({
    llm: opts.llm,
    tools: opts.tools.macroRegime,
    promptContext: ctx,
  });
  const mesoCommodity = createMesoCommodityNode({
    llm: opts.llm,
    tools: opts.tools.mesoCommodity,
    promptContext: ctx,
  });
  const catalystSentiment = createCatalystSentimentNode({
    llm: opts.llm,
    tools: opts.tools.catalystSentiment,
    promptContext: ctx,
  });
  const holdingsIndustry = createHoldingsIndustryNode({
    llm: opts.llm,
    tools: opts.tools.holdingsIndustry,
    promptContext: ctx,
  });
  const topHoldings = createTopHoldingsNode({
    llm: opts.llm,
    tools: opts.tools.topHoldings,
    promptContext: ctx,
  });
  const trader = createTraderNode({ llm: opts.llm, promptContext: ctx });

  // --- Tool nodes (for analysts that call tools) ---
  const mfTools = new ToolNode(opts.tools.marketFlow as StructuredToolInterface[]);

  // --- Build graph ---
  const graph = new StateGraph(SpineState)
    .addNode("market_flow", marketFlow)
    .addNode("market_flow_tools", mfTools)
    .addNode("macro_regime", macroRegime)
    .addNode("meso_commodity", mesoCommodity)
    .addNode("catalyst_sentiment", catalystSentiment)
    .addNode("holdings_industry", holdingsIndustry)
    .addNode("top_holdings", topHoldings)
    .addNode("trader", trader)

    // Sequential pipeline: START → market_flow (with tool loop) → ...
    .addEdge(START, "market_flow")
    .addConditionalEdges("market_flow", routeToolsOrNext("market_flow_tools", "macro_regime"), {
      market_flow_tools: "market_flow_tools",
      continue: "macro_regime",
    })
    .addEdge("market_flow_tools", "market_flow")

    // Remaining analysts run sequentially (no tool loops yet)
    .addEdge("macro_regime", "meso_commodity")
    .addEdge("meso_commodity", "catalyst_sentiment")
    .addEdge("catalyst_sentiment", "holdings_industry")
    .addEdge("holdings_industry", "top_holdings")
    .addEdge("top_holdings", "trader")
    .addEdge("trader", END)

    .compile();

  return graph;
}

// ===========================================================================
// Routing
// ===========================================================================

function routeToolsOrNext(
  toolsNode: string,
  nextNode: string,
): (state: SpineStateType) => typeof toolsNode | "continue" {
  return (state: SpineStateType) => {
    const last = state.messages[state.messages.length - 1] as AIMessage | undefined;
    const toolCalls = (last?.tool_calls ?? []) as ReadonlyArray<unknown>;
    return toolCalls.length > 0 ? toolsNode : "continue";
  };
}
