/**
 * Full analysis graph: 6 analysts → bull/bear debate → research manager →
 * trader → risk debate → portfolio manager → memory writer.
 *
 * Analyst order mirrors Python ETFGraphSetup.DEFAULT_SELECTED_ANALYSTS:
 *
 *   START → market_flow → catalyst_sentiment → macro_regime → meso_commodity →
 *           holdings_industry → top_holdings →
 *           bull_researcher ⇄ bear_researcher → research_manager →
 *           trader →
 *           aggressive_debator → conservative_debator → neutral_debator →
 *           portfolio_manager → memory_writer → END
 *
 * Tool-using analysts run their own tool loop (analyst → ToolNode → analyst)
 * via ``routeAnalystTools``. catalyst_sentiment is a deterministic pre-fetch
 * analyst (no tool loop), matching Python's create_social_media_analyst.
 *
 * The bull/bear and aggressive/conservative/neutral debates loop via
 * ``routeDebate`` / ``routeRiskDebate`` honouring ``maxDebateRounds`` /
 * ``maxRiskRounds`` (default 1 = single pass). Each debator turn is wrapped by
 * ``withDebateTurn`` to advance the investment_debate_state / risk_debate_state
 * accounting (count, latestSpeaker, per-role histories, current responses)
 * that the routers and downstream nodes read.
 *
 * ``selectedAnalysts`` gates which analysts execute (deselected ones are
 * skipped). The memory_writer node persists an analysis entry via the optional
 * ``persistMemory`` callback before END.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import type { AIMessage, BaseMessage } from "@langchain/core/messages";
import { HumanMessage, RemoveMessage } from "@langchain/core/messages";
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
import { createMemoryWriterNode, type PersistMemory } from "../agents/nodes/memory_writer.js";
import { createMesoCommodityNode } from "../agents/nodes/meso_commodity.js";
import { createNeutralDebatorNode } from "../agents/nodes/neutral_debator.js";
import { createPortfolioManagerNode } from "../agents/nodes/portfolio_manager.js";
import { createResearchManagerNode } from "../agents/nodes/research_manager.js";
import { createTopHoldingsNode } from "../agents/nodes/top_holdings.js";
import { createTraderNode } from "../agents/nodes/trader.js";
import type { PromptContext } from "../agents/prompts/shared.js";
import {
  type DebateState,
  SpineState,
  type SpineStateType,
  type SpineStateUpdate,
} from "../agents/state.js";
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
  /** Deep-tier LLM: research manager, trader, portfolio manager. */
  llm: BaseChatModel;
  /** Quick-tier LLM for analysts/researchers/risk debators (defaults to `llm`). */
  quickLlm?: BaseChatModel;
  tools: FullGraphToolSets;
  promptContext: PromptContext;
  /** Bull/bear debate rounds (default 1 = single pass, matching Python). */
  maxDebateRounds?: number;
  /** Risk-debate rounds (default 1 = single pass, matching Python). */
  maxRiskRounds?: number;
  /**
   * Which of the six analysts run. Defaults to all. Deselected analysts are
   * skipped (their node returns an empty update without an LLM call), matching
   * Python's selected_analysts gating while keeping the graph topology static.
   */
  selectedAnalysts?: readonly string[];
  /**
   * Optional persistence callback for the Memory Writer node (graph end).
   * When supplied, the node sends a state payload to it (wired to the bridge
   * memory.append_analysis RPC) and records the returned entry. When omitted,
   * the node is a no-op, matching a disabled memory store.
   */
  persistMemory?: PersistMemory;
  /** Effective runtime config forwarded to the memory store (so user/runtime
   * memory settings reach AnalysisMemoryStore instead of DEFAULT_CONFIG). */
  memoryConfig?: Record<string, unknown>;
}

/** Canonical analyst order, mirroring Python ETFGraphSetup.DEFAULT_SELECTED_ANALYSTS. */
export const ALL_ANALYSTS = [
  "market_flow",
  "catalyst_sentiment",
  "macro_regime",
  "meso_commodity",
  "holdings_industry",
  "top_holdings",
] as const;

/**
 * Validate, dedupe, and canonicalize an analyst selection. Returns all six in
 * canonical order when undefined; throws on an empty selection or any unknown
 * id (parity with Python GraphSetup, which rejects unsupported analysts and
 * dedupes). Output preserves ALL_ANALYSTS order regardless of input order.
 */
export function normalizeAnalystSelection(selected: readonly string[] | undefined): string[] {
  if (selected === undefined) return [...ALL_ANALYSTS];
  if (selected.length === 0) {
    throw new Error("buildFullGraph: selectedAnalysts must contain at least one analyst");
  }
  const allowed = new Set<string>(ALL_ANALYSTS);
  for (const id of selected) {
    if (!allowed.has(id)) {
      throw new Error(`buildFullGraph: unknown analyst '${id}'`);
    }
  }
  const chosen = new Set(selected);
  return ALL_ANALYSTS.filter((id) => chosen.has(id));
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
    const current = `${speaker}: ${response}`;
    // Per-role history + latest-response fields, mirroring the Python debator
    // nodes' investment_debate_state / risk_debate_state updates.
    const roleFields: Record<string, Partial<DebateState>> = {
      Bull: { bullHistory: append(prev.bullHistory, turn), currentBullResponse: current },
      Bear: { bearHistory: append(prev.bearHistory, turn), currentBearResponse: current },
      Aggressive: {
        aggressiveHistory: append(prev.aggressiveHistory, turn),
        currentAggressiveResponse: current,
      },
      Conservative: {
        conservativeHistory: append(prev.conservativeHistory, turn),
        currentConservativeResponse: current,
      },
      Neutral: {
        neutralHistory: append(prev.neutralHistory, turn),
        currentNeutralResponse: current,
      },
    };
    return {
      ...update,
      [field]: {
        ...prev,
        count: prev.count + 1,
        latestSpeaker: speaker,
        history: append(prev.history, turn),
        currentResponse: current,
        ...(roleFields[speaker] ?? {}),
      },
    } as SpineStateUpdate;
  };
}

/** Append a turn to a running transcript with a blank-line separator. */
function append(history: string, turn: string): string {
  return history ? `${history}\n\n${turn}` : turn;
}

/**
 * Wrap an analyst node so it is a no-op when its id is not in `selected`.
 * A skipped analyst makes no LLM call and writes no report; the conditional
 * tool router then advances to the next analyst (no pending tool calls).
 */
function skipIfDeselected(node: NodeFn, id: string, selected: ReadonlySet<string>): NodeFn {
  if (selected.has(id)) return node;
  return async () => ({}) as SpineStateUpdate;
}

/**
 * Clear the accumulated message history between analysts (Python's "Msg Clear"
 * nodes via create_msg_delete). Prevents one analyst's tool chatter / report
 * from bloating the next analyst's context. Report content survives in the
 * dedicated *_report state keys, and debators/managers read explicit context
 * blocks, so clearing messages here is safe. A placeholder keeps providers
 * (e.g. Anthropic) that require a non-empty history happy.
 */
function createMsgDeleteNode(): NodeFn {
  return async (state) => {
    const removals = (state.messages ?? [])
      .filter((m): m is BaseMessage & { id: string } => typeof m.id === "string")
      .map((m) => new RemoveMessage({ id: m.id }));
    return { messages: [...removals, new HumanMessage("Continue")] } as SpineStateUpdate;
  };
}

/**
 * Wrap a manager node so its decision is recorded into the debate state's
 * judgeDecision + latestSpeaker (mirrors Python's research/portfolio managers,
 * which update investment_debate_state / risk_debate_state on top of writing
 * their plan field).
 */
function withManagerJudge(
  node: NodeFn,
  planKey: "research_allocation_plan" | "final_allocation_decision",
  field: "investment_debate_state" | "risk_debate_state",
  speaker: string,
): NodeFn {
  return async (state) => {
    const update = await node(state);
    const plan = (update as Record<string, unknown>)[planKey];
    if (typeof plan !== "string" || !plan.trim()) return update;
    const prev = state[field];
    return {
      ...update,
      [field]: { ...prev, judgeDecision: plan, latestSpeaker: speaker },
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
  // Validate, dedupe, and canonicalize the analyst selection (Python's
  // GraphSetup rejects unknown analysts and the graph dedupes the list).
  const selectedList = normalizeAnalystSelection(opts.selectedAnalysts);
  const selected = new Set(selectedList);
  // Quick LLM for analysts/researchers/risk-debators; deep LLM (opts.llm) for
  // research manager, trader, and portfolio manager — matching Python's tier
  // split. Falls back to the single deep LLM when no quick LLM is supplied.
  const quick = opts.quickLlm ?? opts.llm;

  // --- Analyst nodes (quick tier) ---
  const marketFlow = createMarketFlowNode({
    llm: quick,
    tools: opts.tools.marketFlow,
    promptContext: ctx,
  });
  const macroRegime = createMacroRegimeNode({
    llm: quick,
    tools: opts.tools.macroRegime,
    promptContext: ctx,
  });
  const mesoCommodity = createMesoCommodityNode({
    llm: quick,
    tools: opts.tools.mesoCommodity,
    promptContext: ctx,
  });
  const catalystSentiment = createCatalystSentimentNode({
    llm: quick,
    tools: opts.tools.catalystSentiment,
    promptContext: ctx,
  });
  const holdingsIndustry = createHoldingsIndustryNode({
    llm: quick,
    tools: opts.tools.holdingsIndustry,
    promptContext: ctx,
  });
  const topHoldings = createTopHoldingsNode({
    llm: quick,
    tools: opts.tools.topHoldings,
    promptContext: ctx,
  });

  // --- Researchers (quick tier) ---
  const bullResearcher = createBullResearcherNode({
    llm: quick,
    tools: opts.tools.bullBear,
    promptContext: ctx,
  });
  const bearResearcher = createBearResearcherNode({
    llm: quick,
    tools: opts.tools.bullBear,
    promptContext: ctx,
  });

  // --- Research manager + trader (deep tier) ---
  const researchManager = createResearchManagerNode({
    llm: opts.llm,
    tools: opts.tools.bullBear,
    promptContext: ctx,
  });

  const trader = createTraderNode({ llm: opts.llm, promptContext: ctx });

  // --- Risk debators (quick tier) + portfolio manager (deep tier) ---
  const aggressiveDebator = createAggressiveDebatorNode({
    llm: quick,
    tools: opts.tools.riskDebate,
    promptContext: ctx,
  });
  const conservativeDebator = createConservativeDebatorNode({
    llm: quick,
    tools: opts.tools.riskDebate,
    promptContext: ctx,
  });
  const neutralDebator = createNeutralDebatorNode({
    llm: quick,
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

  // Wrap managers so their decision is recorded in the debate state.
  const researchManagerNode = withManagerJudge(
    researchManager,
    "research_allocation_plan",
    "investment_debate_state",
    "Research Manager",
  );
  const portfolioManagerNode = withManagerJudge(
    portfolioManager,
    "final_allocation_decision",
    "risk_debate_state",
    "Portfolio Manager",
  );

  const memoryWriter = createMemoryWriterNode({
    ...(opts.persistMemory ? { persist: opts.persistMemory } : {}),
    selectedAnalysts: selectedList,
    ...(opts.memoryConfig ? { config: opts.memoryConfig } : {}),
  });

  // --- Tool nodes (one per analyst that calls tools) ---
  const mfTools = new ToolNode(opts.tools.marketFlow as StructuredToolInterface[]);
  const macroTools = new ToolNode(opts.tools.macroRegime as StructuredToolInterface[]);
  const mesoTools = new ToolNode(opts.tools.mesoCommodity as StructuredToolInterface[]);
  const holdingsTools = new ToolNode(opts.tools.holdingsIndustry as StructuredToolInterface[]);
  const topTools = new ToolNode(opts.tools.topHoldings as StructuredToolInterface[]);

  // --- Build graph ---
  const graph = new StateGraph(SpineState)
    .addNode("market_flow", skipIfDeselected(marketFlow, "market_flow", selected))
    .addNode("market_flow_tools", mfTools)
    .addNode("market_flow_clear", createMsgDeleteNode())
    .addNode("macro_regime", skipIfDeselected(macroRegime, "macro_regime", selected))
    .addNode("macro_regime_tools", macroTools)
    .addNode("macro_regime_clear", createMsgDeleteNode())
    .addNode("meso_commodity", skipIfDeselected(mesoCommodity, "meso_commodity", selected))
    .addNode("meso_commodity_tools", mesoTools)
    .addNode("meso_commodity_clear", createMsgDeleteNode())
    .addNode(
      "catalyst_sentiment",
      skipIfDeselected(catalystSentiment, "catalyst_sentiment", selected),
    )
    .addNode("catalyst_sentiment_clear", createMsgDeleteNode())
    .addNode("holdings_industry", skipIfDeselected(holdingsIndustry, "holdings_industry", selected))
    .addNode("holdings_industry_tools", holdingsTools)
    .addNode("holdings_industry_clear", createMsgDeleteNode())
    .addNode("top_holdings", skipIfDeselected(topHoldings, "top_holdings", selected))
    .addNode("top_holdings_tools", topTools)
    .addNode("top_holdings_clear", createMsgDeleteNode())
    .addNode("bull_researcher", bullTurn)
    .addNode("bear_researcher", bearTurn)
    .addNode("research_manager", researchManagerNode)
    .addNode("trader", trader)
    .addNode("aggressive_debator", aggressiveTurn)
    .addNode("conservative_debator", conservativeTurn)
    .addNode("neutral_debator", neutralTurn)
    .addNode("portfolio_manager", portfolioManagerNode)
    .addNode("memory_writer", memoryWriter)

    // --- Analyst pipeline (each analyst clears messages before the next) ---
    // Order mirrors Python ETFGraphSetup.DEFAULT_SELECTED_ANALYSTS:
    // market_flow → catalyst_sentiment → macro_regime → meso_commodity →
    // holdings_industry → top_holdings. After each analyst (and its tool loop),
    // a Msg Clear node resets the message history so the next analyst starts
    // clean (Python parity, prevents cross-analyst token bloat).
    .addEdge(START, "market_flow")
    .addConditionalEdges("market_flow", toolLoopRouter("market_flow_tools", "market_flow_clear"), {
      market_flow_tools: "market_flow_tools",
      market_flow_clear: "market_flow_clear",
    })
    .addEdge("market_flow_tools", "market_flow")
    .addEdge("market_flow_clear", "catalyst_sentiment")

    // catalyst_sentiment pre-fetches its data deterministically (no tool loop).
    .addEdge("catalyst_sentiment", "catalyst_sentiment_clear")
    .addEdge("catalyst_sentiment_clear", "macro_regime")

    .addConditionalEdges(
      "macro_regime",
      toolLoopRouter("macro_regime_tools", "macro_regime_clear"),
      {
        macro_regime_tools: "macro_regime_tools",
        macro_regime_clear: "macro_regime_clear",
      },
    )
    .addEdge("macro_regime_tools", "macro_regime")
    .addEdge("macro_regime_clear", "meso_commodity")

    .addConditionalEdges(
      "meso_commodity",
      toolLoopRouter("meso_commodity_tools", "meso_commodity_clear"),
      {
        meso_commodity_tools: "meso_commodity_tools",
        meso_commodity_clear: "meso_commodity_clear",
      },
    )
    .addEdge("meso_commodity_tools", "meso_commodity")
    .addEdge("meso_commodity_clear", "holdings_industry")

    .addConditionalEdges(
      "holdings_industry",
      toolLoopRouter("holdings_industry_tools", "holdings_industry_clear"),
      {
        holdings_industry_tools: "holdings_industry_tools",
        holdings_industry_clear: "holdings_industry_clear",
      },
    )
    .addEdge("holdings_industry_tools", "holdings_industry")
    .addEdge("holdings_industry_clear", "top_holdings")

    .addConditionalEdges(
      "top_holdings",
      toolLoopRouter("top_holdings_tools", "top_holdings_clear"),
      {
        top_holdings_tools: "top_holdings_tools",
        top_holdings_clear: "top_holdings_clear",
      },
    )
    .addEdge("top_holdings_tools", "top_holdings")
    .addEdge("top_holdings_clear", "bull_researcher")

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
    .addEdge("portfolio_manager", "memory_writer")
    .addEdge("memory_writer", END)

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
