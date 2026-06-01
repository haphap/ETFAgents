/**
 * Shared analyst tool sets used by CLI commands.
 * Extracted to avoid duplication between analyze.ts and analyze-pool.ts.
 */

import type { BridgeApi } from "../../bridge/index.js";

/**
 * Read side of analysis memory: fetch the per-role continuity/lesson/method
 * context to hydrate the graph's initial state. Best-effort — a memory outage
 * degrades to empty context rather than failing the analysis.
 */
export async function fetchMemoryContext(
  api: BridgeApi,
  ticker: string,
  tradeDate: string,
  config: Record<string, unknown>,
  selectedAnalysts?: readonly string[],
): Promise<{
  continuity_context: Record<string, string>;
  lesson_context: Record<string, string>;
  method_context: Record<string, string>;
}> {
  try {
    const r = await api.memoryBuildContext({
      ticker,
      trade_date: tradeDate,
      config,
      ...(selectedAnalysts ? { selected_analysts: selectedAnalysts } : {}),
    });
    return {
      continuity_context: r.continuity_context,
      lesson_context: r.lesson_context,
      method_context: r.method_context,
    };
  } catch {
    return { continuity_context: {}, lesson_context: {}, method_context: {} };
  }
}

export const ANALYST_TOOLS = {
  marketFlow: ["get_etf_price_data", "get_etf_indicators", "get_etf_share", "get_etf_nav"],
  macroRegime: [
    "get_etf_info",
    "get_etf_holdings",
    "get_macro_regime_data",
    "get_global_news",
    "get_news",
  ],
  mesoCommodity: ["get_commodity_cluster_data"],
  // catalyst_sentiment pre-fetches these (no LLM tool loop) — see
  // createCatalystSentimentNode.
  catalystSentiment: ["get_etf_info", "get_etf_holdings", "get_news", "get_global_news"],
  holdingsIndustry: ["get_etf_holdings", "get_etf_industry_research"],
  topHoldings: ["get_etf_holdings", "get_etf_top_holdings_research"],
  bullBear: [] as string[],
  riskDebate: [] as string[],
} as const;
