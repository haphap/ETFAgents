/**
 * catalyst_sentiment analyst node.
 *
 * Unlike the other analysts, catalyst_sentiment pre-fetches ETF info,
 * holdings, and news data before making a single LLM call (no tool loop).
 * The data blocks are fetched up front via the bridge tools and embedded
 * directly into the system message, mirroring the Python
 * ``create_social_media_analyst`` pre-fetch flow.
 */

import { AIMessage, HumanMessage, SystemMessage } from "@langchain/core/messages";
import type { StructuredToolInterface } from "@langchain/core/tools";
import { buildMemoryPromptSection, injectMemoryPromptSection } from "../helpers/memory.js";
import { postJudgeClean, preJudgeClean } from "../helpers/report_leads.js";
import { normalizeChineseRoleTerms } from "../helpers/role_terms.js";
import { validateAndRefine } from "../helpers/validate_refine.js";
import {
  buildCatalystSentimentSystemMessage,
  CATALYST_SENTIMENT_REPORT_SPEC,
  type CatalystSentimentData,
} from "../prompts/catalyst_sentiment.js";
import { dateDaysBefore } from "../prompts/shared.js";
import type { SpineStateType, SpineStateUpdate } from "../state.js";
import type { AnalystNodeOptions } from "./market_flow.js";

/**
 * Invoke a pre-fetch tool by name, returning its string output. Missing tools
 * or runtime failures degrade gracefully to an empty string so a single data
 * source outage never aborts the whole analysis.
 */
async function prefetchTool(
  byName: Map<string, StructuredToolInterface>,
  name: string,
  args: Record<string, unknown>,
): Promise<string> {
  const tool = byName.get(name);
  if (!tool) return "";
  try {
    const output = await tool.invoke(args);
    return typeof output === "string" ? output : String(output);
  } catch {
    return "";
  }
}

export function createCatalystSentimentNode(opts: AnalystNodeOptions) {
  return async function catalystSentimentNode(state: SpineStateType): Promise<SpineStateUpdate> {
    const ticker = state.asset_of_interest;
    const tradeDate = state.trade_date;
    const ctx = opts.promptContext;

    // Pre-fetch the data blocks through the bridge tools. News uses a 7-day
    // look-back window ending on the trade date.
    const byName = new Map(opts.tools.map((t) => [t.name, t] as const));
    const newsStart = tradeDate ? dateDaysBefore(tradeDate, 7) : tradeDate;
    const [etfInfo, etfHoldings, tickerNews, globalNews] = await Promise.all([
      prefetchTool(byName, "get_etf_info", { ticker, curr_date: tradeDate }),
      prefetchTool(byName, "get_etf_holdings", { ticker, curr_date: tradeDate }),
      prefetchTool(byName, "get_news", { ticker, start_date: newsStart, end_date: tradeDate }),
      prefetchTool(byName, "get_global_news", { curr_date: tradeDate, look_back_days: 7 }),
    ]);

    const data: CatalystSentimentData = {
      etfInfo: etfInfo || `ETF: ${ticker}`,
      etfHoldings: etfHoldings || state.top_holdings_report || "暂无持仓数据",
      tickerNews,
      // No dedicated holdings-news tool in the catalyst tool set; the global +
      // ticker news blocks already cover the cross-source narrative.
      holdingsNews: "",
      globalNews,
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
