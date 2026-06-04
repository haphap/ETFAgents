/**
 * trader node — Path A port of ``etfagents.agents.trader.trader.create_trader``.
 *
 * Flow (sub-step 2.5c-3):
 *   1. Build context message from upstream reports (truncated for prompt).
 *   2. Delegate to ``invokeStructuredOrFreetext`` which:
 *      a. Tries structured output via ``withStructuredOutput`` + render.
 *      b. Falls back to free text with stripped system message + fallback
 *         instruction on any failure.
 *   3. Post-process the rendered output (heading polish, constituent strip).
 *   4. Return rendered plan + structured result for backtest signal extraction.
 */

import type { BaseChatModel } from "@langchain/core/language_models/chat_models";
import { AIMessage, HumanMessage, SystemMessage } from "@langchain/core/messages";
import { buildTraderBacktestSignal } from "../helpers/backtest_signal.js";
import { buildMemoryPromptSection, injectMemoryPromptSection } from "../helpers/memory.js";
import {
  formatAgentSignalsForPrompt,
  signalUpdate,
  stripAgentMachineBlocks,
} from "../helpers/output_schema.js";
import type { PositionSizingOptions } from "../helpers/position_sizing.js";
import { appendTraderOutputSchema, renderTraderProposal } from "../helpers/render.js";
import { normalizeChineseManagerTerms } from "../helpers/role_terms.js";
import { invokeStructuredOrFreetext } from "../helpers/structured_output.js";
import {
  demoteTraderH1Headings,
  normalizeTraderConfigLogicHeading,
  restoreTraderExecutionBiasSection,
  stripConstituentTradeInstructions,
} from "../helpers/trader_format.js";
import {
  buildInstrumentContext,
  type PromptContext,
  reportForDecisionContext,
} from "../prompts/shared.js";
import {
  buildTraderContextMessage,
  buildTraderSystemMessage,
  TRADER_FREETEXT_FALLBACK_INSTRUCTION,
} from "../prompts/trader.js";
import type { TraderProposal } from "../schemas/trader_proposal.js";
import { TraderProposalSchema } from "../schemas/trader_proposal.js";
import type { SpineStateType, SpineStateUpdate } from "../state.js";

export interface TraderNodeOptions {
  llm: BaseChatModel;
  promptContext: PromptContext;
  positionSizing?: PositionSizingOptions;
}

export function createTraderNode(opts: TraderNodeOptions) {
  return async function traderNode(state: SpineStateType): Promise<SpineStateUpdate> {
    const ticker = state.asset_of_interest;
    const instrumentContext = buildInstrumentContext(ticker);
    const ctx = opts.promptContext;

    const contextMessage = buildTraderContextMessage({
      asset: ticker,
      instrumentContext,
      structuredSignals: formatAgentSignalsForPrompt(state.agent_signals, {
        language: ctx.language,
        include: [
          "market_flow",
          "catalyst_sentiment",
          "macro_regime",
          "meso_commodity",
          "holdings_industry",
          "top_holdings",
          "bull_researcher",
          "bear_researcher",
          "research_manager",
        ],
      }),
      researchPlan: reportForDecisionContext(state.research_allocation_plan, ctx, 4_000),
      marketFlowReport: reportForDecisionContext(state.market_flow_report, ctx, 5_000),
      catalystSentimentReport: reportForDecisionContext(
        state.catalyst_sentiment_report,
        ctx,
        5_000,
      ),
      macroRegimeReport: reportForDecisionContext(state.macro_regime_report, ctx, 5_000),
      mesoCommodityReport: reportForDecisionContext(state.meso_commodity_report, ctx, 5_000),
      holdingsIndustryReport: reportForDecisionContext(state.holdings_industry_report, ctx, 5_000),
      topHoldingsReport: reportForDecisionContext(state.top_holdings_report, ctx, 5_000),
    });

    const systemMessage = buildTraderSystemMessage(ctx);

    // Inject memory context (graceful no-op when memory is empty).
    const memorySection = buildMemoryPromptSection(state, { role: "trader" }, ctx.language);
    const enrichedSystem = injectMemoryPromptSection(systemMessage, memorySection);

    const { rendered, structured: _structured } = await invokeStructuredOrFreetext<TraderProposal>({
      llm: opts.llm,
      schema: TraderProposalSchema,
      messages: [new SystemMessage(enrichedSystem), new HumanMessage(contextMessage)],
      render: (proposal: TraderProposal) =>
        renderTraderProposal(proposal, {
          language: ctx.language,
          ...(state.market_flow_report ? { contextText: state.market_flow_report } : {}),
        }),
      agentName: "Trader",
      fallbackInstruction: TRADER_FREETEXT_FALLBACK_INSTRUCTION,
    });

    // Post-processing chain (applied to both structured and free-text paths).
    // Order mirrors Python trader.py:
    //   normalize_chinese_manager_terms  (manager-section headings + role terms)
    //     → _demote_trader_h1_headings  (drop accidental H1s)
    //     → _normalize_trader_config_logic_heading (canonicalize 一、配置逻辑)
    //     → _restore_trader_execution_bias_section (ensure 四、执行倾向 + rating)
    //     → strip_constituent_trade_instructions  (ETF-only discipline)
    let postProcessed = demoteTraderH1Headings(normalizeChineseManagerTerms(rendered));
    postProcessed = normalizeTraderConfigLogicHeading(postProcessed, ctx.language);
    postProcessed = restoreTraderExecutionBiasSection(postProcessed, ctx.language);
    postProcessed = stripConstituentTradeInstructions(postProcessed, ctx.language);
    postProcessed = appendTraderOutputSchema(postProcessed, _structured, ctx.language);
    const signalSourceReport = postProcessed;
    const visibleReport = stripAgentMachineBlocks(postProcessed);

    return {
      messages: [new AIMessage(visibleReport)],
      trader_allocation_plan: visibleReport,
      agent_signals: signalUpdate("trader", signalSourceReport),
      trader_backtest_signal: buildTraderBacktestSignal(
        ticker,
        state.trade_date ?? "",
        signalSourceReport,
        _structured,
        {
          agentSignals: state.agent_signals,
          ...(opts.positionSizing?.maxDrawdownBudget !== undefined
            ? { maxDrawdownBudget: opts.positionSizing.maxDrawdownBudget }
            : {}),
        },
      ) as unknown as Record<string, unknown>,
      sender: "Trader",
    };
  };
}
