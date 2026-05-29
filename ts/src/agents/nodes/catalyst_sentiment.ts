/**
 * catalyst_sentiment analyst node.
 *
 * Unlike the other analysts, catalyst_sentiment pre-fetches ETF info,
 * holdings, and news data before making a single LLM call (no tool loop).
 *
 * Sub-step 3: initial wiring — pre-fetched data blocks are embedded directly
 * into the system message. Full bridge RPC integration deferred.
 */

import { AIMessage, HumanMessage, SystemMessage } from "@langchain/core/messages";
import { buildMemoryPromptSection, injectMemoryPromptSection } from "../helpers/memory.js";
import { postJudgeClean, preJudgeClean } from "../helpers/report_leads.js";
import { normalizeChineseRoleTerms } from "../helpers/role_terms.js";
import { validateAndRefine } from "../helpers/validate_refine.js";
import {
  buildCatalystSentimentSystemMessage,
  CATALYST_SENTIMENT_REPORT_SPEC,
  type CatalystSentimentData,
} from "../prompts/catalyst_sentiment.js";
import type { SpineStateType, SpineStateUpdate } from "../state.js";
import { type AnalystNodeOptions, assembleSystemFrame } from "./market_flow.js";

export function createCatalystSentimentNode(opts: AnalystNodeOptions) {
  return async function catalystSentimentNode(state: SpineStateType): Promise<SpineStateUpdate> {
    const ticker = state.asset_of_interest;
    const ctx = opts.promptContext;

    // Build pre-fetched data blocks. In sub-step 3 the data comes from
    // upstream reports already in state; full bridge RPC fetching
    // (get_etf_info, get_etf_holdings, get_news, etc.) deferred.
    const data: CatalystSentimentData = {
      etfInfo: `ETF: ${ticker}`,
      etfHoldings: state.top_holdings_report || "暂无持仓数据",
      tickerNews: "",
      holdingsNews: "",
      globalNews: "",
    };

    const systemBody = buildCatalystSentimentSystemMessage(ctx, data);
    const memorySection = buildMemoryPromptSection(
      state,
      { role: "catalyst_sentiment", aliases: ["social"] },
      ctx.language,
    );
    const enrichedSystem = injectMemoryPromptSection(systemBody, memorySection);

    const messages = [new SystemMessage(enrichedSystem), new HumanMessage(ticker)];
    const result = await opts.llm.invoke(messages);

    let report = typeof result.content === "string" ? result.content.trim() : "";
    if (report) {
      report = normalizeChineseRoleTerms(report);
      report = preJudgeClean(report);
      const refined = await validateAndRefine(report, opts.llm, CATALYST_SENTIMENT_REPORT_SPEC);
      if (refined) report = refined;
      report = postJudgeClean(report);
    }

    return {
      messages: [new AIMessage(report)],
      catalyst_sentiment_report: report,
      sender: "CatalystSentiment",
    } as SpineStateUpdate;
  };
}
