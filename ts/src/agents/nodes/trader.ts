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
import { renderTraderProposal } from "../helpers/render.js";
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
  truncateForPrompt,
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
}

export function createTraderNode(opts: TraderNodeOptions) {
  return async function traderNode(state: SpineStateType): Promise<SpineStateUpdate> {
    const ticker = state.asset_of_interest;
    const instrumentContext = buildInstrumentContext(ticker);
    const ctx = opts.promptContext;

    const contextMessage = buildTraderContextMessage({
      asset: ticker,
      instrumentContext,
      researchPlan: truncateForPrompt(state.research_allocation_plan, ctx),
      marketFlowReport: truncateForPrompt(state.market_flow_report, ctx),
      catalystSentimentReport: truncateForPrompt(state.catalyst_sentiment_report, ctx),
      macroRegimeReport: truncateForPrompt(state.macro_regime_report, ctx),
      mesoCommodityReport: truncateForPrompt(state.meso_commodity_report, ctx),
      holdingsIndustryReport: state.holdings_industry_report,
      topHoldingsReport: state.top_holdings_report,
    });

    const systemMessage = buildTraderSystemMessage(ctx);

    const { rendered, structured: _structured } = await invokeStructuredOrFreetext<TraderProposal>({
      llm: opts.llm,
      schema: TraderProposalSchema,
      messages: [new SystemMessage(systemMessage), new HumanMessage(contextMessage)],
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

    return {
      messages: [new AIMessage(postProcessed)],
      trader_allocation_plan: postProcessed,
      // TODO sub-step 2.6: build_trader_backtest_signal from `structured`
      trader_backtest_signal: {},
      sender: "Trader",
    };
  };
}
