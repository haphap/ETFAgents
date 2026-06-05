/**
 * Minimal StateGraph for the market_flow → trader spine.
 *
 *   START → market_flow → (tool calls?) → market_flow_tools → market_flow
 *                       └── (no tools) → trader → END
 *
 * The conditional edge from ``market_flow`` mirrors the Python pattern in
 * ``etfagents.graph.setup.GraphSetup.setup_graph`` but only routes to the
 * tools node or the trader, not the rest of the analyst chain.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { AIMessage } from "@langchain/core/messages";
import type { StructuredToolInterface } from "@langchain/core/tools";
import { END, START, StateGraph } from "@langchain/langgraph";
import { ToolNode } from "@langchain/langgraph/prebuilt";
import type { PositionSizingOptions } from "../agents/helpers/position_sizing.js";
import { createMarketFlowNode } from "../agents/nodes/market_flow.js";
import { createTraderNode } from "../agents/nodes/trader.js";
import type { PromptContext } from "../agents/prompts/shared.js";
import { SpineState, type SpineStateType } from "../agents/state.js";

export interface BuildMiniSpineOptions {
  llm: BaseChatModel;
  marketFlowTools: ReadonlyArray<StructuredToolInterface>;
  promptContext: PromptContext;
  positionSizing?: PositionSizingOptions;
}

export function buildMiniSpineGraph(opts: BuildMiniSpineOptions) {
  const marketFlowNode = createMarketFlowNode({
    llm: opts.llm,
    tools: opts.marketFlowTools,
    promptContext: opts.promptContext,
  });
  const traderNode = createTraderNode({
    llm: opts.llm,
    promptContext: opts.promptContext,
    ...(opts.positionSizing ? { positionSizing: opts.positionSizing } : {}),
  });
  const marketFlowTools = new ToolNode(opts.marketFlowTools as StructuredToolInterface[]);

  return new StateGraph(SpineState)
    .addNode("market_flow", marketFlowNode)
    .addNode("market_flow_tools", marketFlowTools)
    .addNode("trader", traderNode)
    .addEdge(START, "market_flow")
    .addConditionalEdges("market_flow", routeFromMarketFlow, {
      market_flow_tools: "market_flow_tools",
      trader: "trader",
    })
    .addEdge("market_flow_tools", "market_flow")
    .addEdge("trader", END)
    .compile();
}

function routeFromMarketFlow(state: SpineStateType): "market_flow_tools" | "trader" {
  const last = state.messages[state.messages.length - 1] as AIMessage | undefined;
  const toolCalls = (last?.tool_calls ?? []) as ReadonlyArray<unknown>;
  return toolCalls.length > 0 ? "market_flow_tools" : "trader";
}
