/**
 * Shared analyst tool sets used by CLI commands.
 * Extracted to avoid duplication between analyze.ts and analyze-pool.ts.
 */

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
