/**
 * Full analysis graph: 6 analysts → bull/bear debate → research manager →
 * trader → risk debate → portfolio manager.
 *
 * Sequential single-pass pipeline (parallel analyst fan-out deferred to a
 * future phase when the Ink TUI needs per-analyst streaming progress):
 *
 *   START → market_flow → macro_regime → meso_commodity →
 *           catalyst_sentiment → holdings_industry → top_holdings →
 *           bull_researcher → bear_researcher → research_manager →
 *           trader →
 *           aggressive_debator → conservative_debator → neutral_debator →
 *           portfolio_manager → END
 *
 * Every analyst that is given tools runs its own tool loop (analyst →
 * ToolNode → analyst) via the shared ``routeAnalystTools`` router. The
 * researchers, debators, research manager and portfolio manager read the
 * accumulated message history / state keys and produce their reports in a
 * single pass — matching the contracts of their node factories, which write
 * flat string state keys (research_allocation_plan, final_allocation_decision,
 * …) rather than an accumulating debate-state object.
 *
 * Multi-round debate looping (``routeDebate`` / ``routeRiskDebate`` honouring
 * ``max_debate_rounds`` > 1) is a follow-up: it requires the debator nodes to
 * accumulate a debate-state structure with round counts and a latest-speaker
 * marker, which the current single-pass factory nodes do not emit.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
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
import { createMarketFlowNode } from "../agents/nodes/market_flow.js";
import { createMesoCommodityNode } from "../agents/nodes/meso_commodity.js";
import { createNeutralDebatorNode } from "../agents/nodes/neutral_debator.js";
import { createPortfolioManagerNode } from "../agents/nodes/portfolio_manager.js";
import { createResearchManagerNode } from "../agents/nodes/research_manager.js";
import { createTopHoldingsNode } from "../agents/nodes/top_holdings.js";
import { createTraderNode } from "../agents/nodes/trader.js";
import type { PromptContext } from "../agents/prompts/shared.js";
import { SpineState, type SpineStateType } from "../agents/state.js";
import { routeAnalystTools } from "./routing.js";

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

  // --- Debate / research-manager nodes (no tools) ---
  const bullResearcher = createBullResearcherNode({
    llm: opts.llm,
    tools: opts.tools.bullBear,
    promptContext: ctx,
  });
  const bearResearcher = createBearResearcherNode({
    llm: opts.llm,
    tools: opts.tools.bullBear,
    promptContext: ctx,
  });
  const researchManager = createResearchManagerNode({
    llm: opts.llm,
    tools: opts.tools.bullBear,
    promptContext: ctx,
  });

  const trader = createTraderNode({ llm: opts.llm, promptContext: ctx });

  // --- Risk-debate / portfolio-manager nodes (no tools) ---
  const aggressiveDebator = createAggressiveDebatorNode({
    llm: opts.llm,
    tools: opts.tools.riskDebate,
    promptContext: ctx,
  });
  const conservativeDebator = createConservativeDebatorNode({
    llm: opts.llm,
    tools: opts.tools.riskDebate,
    promptContext: ctx,
  });
  const neutralDebator = createNeutralDebatorNode({
    llm: opts.llm,
    tools: opts.tools.riskDebate,
    promptContext: ctx,
  });
  const portfolioManager = createPortfolioManagerNode({
    llm: opts.llm,
    tools: opts.tools.riskDebate,
    promptContext: ctx,
  });

  // --- Tool nodes (one per analyst that calls tools) ---
  const mfTools = new ToolNode(opts.tools.marketFlow as StructuredToolInterface[]);
  const macroTools = new ToolNode(opts.tools.macroRegime as StructuredToolInterface[]);
  const mesoTools = new ToolNode(opts.tools.mesoCommodity as StructuredToolInterface[]);
  const holdingsTools = new ToolNode(opts.tools.holdingsIndustry as StructuredToolInterface[]);
  const topTools = new ToolNode(opts.tools.topHoldings as StructuredToolInterface[]);

  // --- Build graph ---
  const graph = new StateGraph(SpineState)
    .addNode("market_flow", marketFlow)
    .addNode("market_flow_tools", mfTools)
    .addNode("macro_regime", macroRegime)
    .addNode("macro_regime_tools", macroTools)
    .addNode("meso_commodity", mesoCommodity)
    .addNode("meso_commodity_tools", mesoTools)
    .addNode("catalyst_sentiment", catalystSentiment)
    .addNode("holdings_industry", holdingsIndustry)
    .addNode("holdings_industry_tools", holdingsTools)
    .addNode("top_holdings", topHoldings)
    .addNode("top_holdings_tools", topTools)
    .addNode("bull_researcher", bullResearcher)
    .addNode("bear_researcher", bearResearcher)
    .addNode("research_manager", researchManager)
    .addNode("trader", trader)
    .addNode("aggressive_debator", aggressiveDebator)
    .addNode("conservative_debator", conservativeDebator)
    .addNode("neutral_debator", neutralDebator)
    .addNode("portfolio_manager", portfolioManager)

    // --- Analyst pipeline (each tool-using analyst gets a tool loop) ---
    .addEdge(START, "market_flow")
    .addConditionalEdges("market_flow", toolLoopRouter("market_flow_tools", "macro_regime"), {
      market_flow_tools: "market_flow_tools",
      macro_regime: "macro_regime",
    })
    .addEdge("market_flow_tools", "market_flow")

    .addConditionalEdges("macro_regime", toolLoopRouter("macro_regime_tools", "meso_commodity"), {
      macro_regime_tools: "macro_regime_tools",
      meso_commodity: "meso_commodity",
    })
    .addEdge("macro_regime_tools", "macro_regime")

    .addConditionalEdges(
      "meso_commodity",
      toolLoopRouter("meso_commodity_tools", "catalyst_sentiment"),
      {
        meso_commodity_tools: "meso_commodity_tools",
        catalyst_sentiment: "catalyst_sentiment",
      },
    )
    .addEdge("meso_commodity_tools", "meso_commodity")

    // catalyst_sentiment pre-fetches its data (no LLM tool loop).
    .addEdge("catalyst_sentiment", "holdings_industry")

    .addConditionalEdges(
      "holdings_industry",
      toolLoopRouter("holdings_industry_tools", "top_holdings"),
      {
        holdings_industry_tools: "holdings_industry_tools",
        top_holdings: "top_holdings",
      },
    )
    .addEdge("holdings_industry_tools", "holdings_industry")

    .addConditionalEdges("top_holdings", toolLoopRouter("top_holdings_tools", "bull_researcher"), {
      top_holdings_tools: "top_holdings_tools",
      bull_researcher: "bull_researcher",
    })
    .addEdge("top_holdings_tools", "top_holdings")

    // --- Bull/Bear debate → research manager → trader ---
    .addEdge("bull_researcher", "bear_researcher")
    .addEdge("bear_researcher", "research_manager")
    .addEdge("research_manager", "trader")

    // --- Trader → risk debate → portfolio manager ---
    .addEdge("trader", "aggressive_debator")
    .addEdge("aggressive_debator", "conservative_debator")
    .addEdge("conservative_debator", "neutral_debator")
    .addEdge("neutral_debator", "portfolio_manager")
    .addEdge("portfolio_manager", END)

    .compile();

  return graph;
}

// ===========================================================================
// Routing
// ===========================================================================

/**
 * Build a conditional-edge router that sends the graph to ``toolsNode`` when
 * the analyst emitted pending tool calls, otherwise to ``nextNode``. Thin
 * wrapper around the shared ``routeAnalystTools`` helper.
 */
function toolLoopRouter(toolsNode: string, nextNode: string): (state: SpineStateType) => string {
  return (state: SpineStateType) => routeAnalystTools(state, toolsNode, nextNode);
}
