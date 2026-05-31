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
import type { AIMessage, BaseMessage } from "@langchain/core/messages";
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
import { SpineState, type SpineStateType, type SpineStateUpdate } from "../agents/state.js";
import { routeAnalystTools, routeDebate, routeRiskDebate } from "./routing.js";

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
  /** Bull/bear debate rounds (default 1 = single pass, matching Python). */
  maxDebateRounds?: number;
  /** Risk-debate rounds (default 1 = single pass, matching Python). */
  maxRiskRounds?: number;
}

type NodeFn = (state: SpineStateType) => Promise<SpineStateUpdate>;

/** Maps routeDebate's display-name returns to the graph's node ids. */
const DEBATE_ROUTE_MAP = {
  "Bull Researcher": "bull_researcher",
  "Bear Researcher": "bear_researcher",
  "Research Manager": "research_manager",
} as const;

/** Maps routeRiskDebate's display-name returns to the graph's node ids. */
const RISK_ROUTE_MAP = {
  "Aggressive Analyst": "aggressive_debator",
  "Conservative Analyst": "conservative_debator",
  "Neutral Analyst": "neutral_debator",
  "Portfolio Manager": "portfolio_manager",
} as const;

/**
 * Wrap a debator/researcher node so each completed turn advances the debate
 * accounting (`count`, `latestSpeaker`, appended `history`) that the
 * conditional routers read. Tool rounds (the model emitted tool calls instead
 * of an argument) do not count. `field` selects the research vs risk debate.
 */
export function withDebateTurn(
  node: NodeFn,
  speaker: string,
  field: "investment_debate_state" | "risk_debate_state",
): NodeFn {
  return async (state) => {
    const update = await node(state);
    const messages = (update as { messages?: BaseMessage[] }).messages ?? [];
    const last = messages[messages.length - 1] as AIMessage | undefined;
    if (last && (last.tool_calls?.length ?? 0) > 0) return update; // tool round
    const response = typeof last?.content === "string" ? last.content : "";
    const prev = state[field];
    const turn = response ? `${speaker}: ${response}` : speaker;
    return {
      ...update,
      [field]: {
        count: prev.count + 1,
        latestSpeaker: speaker,
        history: prev.history ? `${prev.history}\n\n${turn}` : turn,
      },
    } as SpineStateUpdate;
  };
}

// ===========================================================================
// Graph builder
// ===========================================================================

export function buildFullGraph(opts: BuildFullGraphOptions) {
  const ctx = opts.promptContext;
  const maxDebateRounds = opts.maxDebateRounds ?? 1;
  const maxRiskRounds = opts.maxRiskRounds ?? 1;

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

  // Wrap debators so each completed turn advances the debate accounting that
  // routeDebate / routeRiskDebate read to decide whether to loop.
  const bullTurn = withDebateTurn(bullResearcher, "Bull", "investment_debate_state");
  const bearTurn = withDebateTurn(bearResearcher, "Bear", "investment_debate_state");
  const aggressiveTurn = withDebateTurn(aggressiveDebator, "Aggressive", "risk_debate_state");
  const conservativeTurn = withDebateTurn(conservativeDebator, "Conservative", "risk_debate_state");
  const neutralTurn = withDebateTurn(neutralDebator, "Neutral", "risk_debate_state");

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
    .addNode("bull_researcher", bullTurn)
    .addNode("bear_researcher", bearTurn)
    .addNode("research_manager", researchManager)
    .addNode("trader", trader)
    .addNode("aggressive_debator", aggressiveTurn)
    .addNode("conservative_debator", conservativeTurn)
    .addNode("neutral_debator", neutralTurn)
    .addNode("portfolio_manager", portfolioManager)

    // --- Analyst pipeline (each tool-using analyst gets a tool loop) ---
    // Order mirrors Python ETFGraphSetup.DEFAULT_SELECTED_ANALYSTS:
    // market_flow → catalyst_sentiment → macro_regime → meso_commodity →
    // holdings_industry → top_holdings.
    .addEdge(START, "market_flow")
    .addConditionalEdges("market_flow", toolLoopRouter("market_flow_tools", "catalyst_sentiment"), {
      market_flow_tools: "market_flow_tools",
      catalyst_sentiment: "catalyst_sentiment",
    })
    .addEdge("market_flow_tools", "market_flow")

    // catalyst_sentiment pre-fetches its data (no LLM tool loop).
    .addEdge("catalyst_sentiment", "macro_regime")

    .addConditionalEdges("macro_regime", toolLoopRouter("macro_regime_tools", "meso_commodity"), {
      macro_regime_tools: "macro_regime_tools",
      meso_commodity: "meso_commodity",
    })
    .addEdge("macro_regime_tools", "macro_regime")

    .addConditionalEdges(
      "meso_commodity",
      toolLoopRouter("meso_commodity_tools", "holdings_industry"),
      {
        meso_commodity_tools: "meso_commodity_tools",
        holdings_industry: "holdings_industry",
      },
    )
    .addEdge("meso_commodity_tools", "meso_commodity")

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

    // --- Bull/Bear debate (loops until 2*maxDebateRounds turns) → manager ---
    .addConditionalEdges(
      "bull_researcher",
      (state: SpineStateType) => routeDebate(state.investment_debate_state, maxDebateRounds),
      DEBATE_ROUTE_MAP,
    )
    .addConditionalEdges(
      "bear_researcher",
      (state: SpineStateType) => routeDebate(state.investment_debate_state, maxDebateRounds),
      DEBATE_ROUTE_MAP,
    )
    .addEdge("research_manager", "trader")

    // --- Trader → risk debate (loops until 3*maxRiskRounds turns) → PM ---
    .addEdge("trader", "aggressive_debator")
    .addConditionalEdges(
      "aggressive_debator",
      (state: SpineStateType) => routeRiskDebate(state.risk_debate_state, maxRiskRounds),
      RISK_ROUTE_MAP,
    )
    .addConditionalEdges(
      "conservative_debator",
      (state: SpineStateType) => routeRiskDebate(state.risk_debate_state, maxRiskRounds),
      RISK_ROUTE_MAP,
    )
    .addConditionalEdges(
      "neutral_debator",
      (state: SpineStateType) => routeRiskDebate(state.risk_debate_state, maxRiskRounds),
      RISK_ROUTE_MAP,
    )
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
