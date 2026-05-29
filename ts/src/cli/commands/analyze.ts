/**
 * `analyze <ticker>` — full 6-analyst pipeline → trader.
 *
 * Phase 3.2: replaces analyze-mini with the full analyst suite.
 */

import { HumanMessage } from "@langchain/core/messages";
import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, pickBridgeTools, RpcError } from "../../bridge/index.js";
import { buildFullGraph } from "../../graph/full_graph.js";
import { createLlmFromConfig } from "../../llm/factory.js";

// Tool sets for each analyst (matching tsplan §7.1).
const ANALYST_TOOLS = {
  marketFlow: ["get_etf_price_data", "get_etf_indicators", "get_etf_share", "get_etf_nav"],
  macroRegime: [
    "get_etf_info",
    "get_etf_holdings",
    "get_macro_regime_data",
    "get_global_news",
    "get_news",
  ],
  mesoCommodity: ["get_commodity_cluster_data"],
  catalystSentiment: [] as string[],
  holdingsIndustry: ["get_etf_holdings", "get_etf_industry_research"],
  topHoldings: ["get_etf_holdings", "get_etf_top_holdings_research"],
  bullBear: [] as string[],
  riskDebate: [] as string[],
} as const;

interface AnalyzeOptions {
  date?: string;
  model?: string;
  provider?: string;
  baseUrl?: string;
  maxTokens?: string;
}

export function registerAnalyze(program: Command): void {
  program
    .command("analyze <ticker>")
    .description("Run the full 6-analyst pipeline for one ETF ticker")
    .option("--date <yyyy-mm-dd>", "Trade date (default: today)")
    .option("--model <name>", "Override LLM model")
    .option("--provider <name>", "Override LLM provider")
    .option("--base-url <url>", "Override LLM base URL")
    .option("--max-tokens <n>", "Per-request max_tokens budget")
    .action(async (ticker: string, opts: AnalyzeOptions) => {
      const tradeDate = opts.date ?? new Date().toISOString().slice(0, 10);
      const client = new BridgeClient();
      const api = new BridgeApi(client);
      try {
        await client.start();
        const config = await api.configGet();
        const llmHandle = createLlmFromConfig(config, {
          tier: "deep",
          ...(opts.model ? { model: opts.model } : {}),
          ...(opts.provider ? { provider: opts.provider } : {}),
          ...(opts.baseUrl ? { baseUrl: opts.baseUrl } : {}),
          ...(opts.maxTokens ? { maxTokens: Number(opts.maxTokens) } : {}),
        });

        // Pick tools for each analyst.
        const toolSets = {
          marketFlow: await pickBridgeTools(
            api,
            ANALYST_TOOLS.marketFlow as unknown as readonly string[],
          ),
          macroRegime: await pickBridgeTools(
            api,
            ANALYST_TOOLS.macroRegime as unknown as readonly string[],
          ),
          mesoCommodity: await pickBridgeTools(
            api,
            ANALYST_TOOLS.mesoCommodity as unknown as readonly string[],
          ),
          catalystSentiment: [],
          holdingsIndustry: await pickBridgeTools(
            api,
            ANALYST_TOOLS.holdingsIndustry as unknown as readonly string[],
          ),
          topHoldings: await pickBridgeTools(
            api,
            ANALYST_TOOLS.topHoldings as unknown as readonly string[],
          ),
          bullBear: [],
          riskDebate: [],
        };

        const charLimit = Number(config.report_context_char_limit);
        const promptContext = {
          language: String(config.output_language ?? "Chinese"),
          ...(Number.isFinite(charLimit) && charLimit > 0
            ? { reportContextCharLimit: charLimit }
            : {}),
        };

        const graph = buildFullGraph({
          llm: llmHandle.llm,
          tools: toolSets,
          promptContext,
        });

        console.log(
          pc.dim(
            `provider=${llmHandle.provider} model=${llmHandle.model} ticker=${ticker} trade_date=${tradeDate}`,
          ),
        );
        console.log(pc.yellow("Running 6-analyst pipeline..."));

        const final = await graph.invoke({
          messages: [new HumanMessage(ticker)],
          asset_of_interest: ticker,
          trade_date: tradeDate,
        });

        console.log(pc.cyan("\n=== trader_allocation_plan ==="));
        console.log(final.trader_allocation_plan || pc.dim("(empty)"));
        console.log(pc.dim(`\nrating=${final.trader_backtest_signal?.rating ?? "?"}`));
      } catch (err) {
        if (err instanceof RpcError) {
          console.error(pc.red(`bridge error [${err.code}]: ${err.message}`));
        } else {
          console.error(pc.red(`error: ${(err as Error).message}`));
        }
        process.exitCode = 1;
      } finally {
        await client.close();
      }
    });
}
