/**
 * catalyst_sentiment analyst node.
 *
 * Deterministic pre-fetch (mirrors Python create_social_media_analyst): fetch
 * ETF info + holdings, derive top-holding names from the holdings, then fetch
 * ticker news, per-holding news, and global news in parallel, embed all blocks
 * into the system message, and make a single LLM call — no tool loop.
 */

import { AIMessage, HumanMessage, SystemMessage } from "@langchain/core/messages";
import type { StructuredToolInterface } from "@langchain/core/tools";
import { buildMemoryPromptSection, injectMemoryPromptSection } from "../helpers/memory.js";
import { signalUpdate, stripAgentMachineBlocks } from "../helpers/output_schema.js";
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

/** Holdings CSV columns that carry the constituent company name (Python parity). */
const HOLDING_NAME_COLUMNS = ["name", "stk_name", "sec_name"];

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

/** Port of Python _extract_holding_names: top-N constituent names from holdings CSV. */
export function extractHoldingNames(holdingsCsv: string, maxNames = 3): string[] {
  if (!holdingsCsv || holdingsCsv.includes("No ETF holdings")) return [];
  const lines = holdingsCsv
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));
  const header = lines[0];
  if (!header) return [];
  const cols = parseCsvLine(header).map((c) => c.toLowerCase());
  const nameIdx = cols.findIndex((c) => HOLDING_NAME_COLUMNS.includes(c));
  if (nameIdx < 0) return [];
  const names: string[] = [];
  for (const line of lines.slice(1)) {
    const name = parseCsvLine(line)[nameIdx]?.trim();
    if (name && !names.includes(name)) names.push(name);
    if (names.length >= maxNames) break;
  }
  return names;
}

/** Parse one CSV line, honouring double-quoted fields with embedded commas. */
function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      cells.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current);
  return cells.map((cell) => cell.trim());
}

/** Replicate Python get_news_for_queries: get_news per query, concatenated with labels. */
async function fetchHoldingsNews(
  byName: Map<string, StructuredToolInterface>,
  names: string[],
  startDate: string,
  endDate: string,
): Promise<string> {
  if (names.length === 0) return "<无重仓股搜索词>";
  const blocks = await Promise.all(
    names.map(async (name) => {
      const news = await prefetchTool(byName, "get_news", {
        ticker: name,
        start_date: startDate,
        end_date: endDate,
      });
      return news ? `## ${name}\n${news}` : "";
    }),
  );
  const joined = blocks.filter(Boolean).join("\n\n");
  return joined || "<无重仓股新闻>";
}

export function createCatalystSentimentNode(opts: AnalystNodeOptions) {
  return async function catalystSentimentNode(state: SpineStateType): Promise<SpineStateUpdate> {
    const ticker = state.asset_of_interest;
    const tradeDate = state.trade_date;
    const ctx = opts.promptContext;

    const byName = new Map(opts.tools.map((t) => [t.name, t] as const));
    const newsStart = tradeDate ? dateDaysBefore(tradeDate, 7) : tradeDate;

    // Phase 1: ETF context, then derive holding names from the holdings block.
    const [etfInfo, etfHoldings] = await Promise.all([
      prefetchTool(byName, "get_etf_info", { ticker, curr_date: tradeDate }),
      prefetchTool(byName, "get_etf_holdings", { ticker, curr_date: tradeDate }),
    ]);
    const holdingNames = extractHoldingNames(etfHoldings);

    // Phase 2: parallel news fetch (ticker, per-holding, global).
    const [tickerNews, holdingsNews, globalNews] = await Promise.all([
      prefetchTool(byName, "get_news", { ticker, start_date: newsStart, end_date: tradeDate }),
      fetchHoldingsNews(byName, holdingNames, newsStart, tradeDate),
      prefetchTool(byName, "get_global_news", {
        curr_date: tradeDate,
        look_back_days: 7,
        limit: 10,
      }),
    ]);

    const data: CatalystSentimentData = {
      etfInfo: etfInfo || `ETF: ${ticker}`,
      etfHoldings: etfHoldings || state.top_holdings_report || "暂无持仓数据",
      tickerNews,
      holdingsNews,
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
    const signalSourceReport = report;
    const visibleReport = stripAgentMachineBlocks(report);

    return {
      messages: [new AIMessage(visibleReport)],
      catalyst_sentiment_report: visibleReport,
      agent_signals: signalUpdate(CATALYST_SENTIMENT_REPORT_SPEC.analystName, signalSourceReport),
      sender: "CatalystSentiment",
    } as SpineStateUpdate;
  };
}
