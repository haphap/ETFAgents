/**
 * `analyze --candidate-pool <tickers>` — multi-ticker analysis.
 *
 * Phase 3.3: runs the full graph per ticker, collects backtest signals,
 * ranks by rating and target weight, and prints a table.
 */

import { HumanMessage } from "@langchain/core/messages";
import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, pickBridgeTools, RpcError } from "../../bridge/index.js";
import { buildFullGraph } from "../../graph/full_graph.js";
import { createLlmFromConfig } from "../../llm/factory.js";

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
  holdingsIndustry: ["get_etf_holdings", "get_etf_industry_research"],
  topHoldings: ["get_etf_holdings", "get_etf_top_holdings_research"],
} as const;

interface CandidateResult {
  ticker: string;
  rating: string;
  weightPct: number;
  planPreview: string;
  signal: Record<string, unknown>;
}

export function registerAnalyzeCandidatePool(program: Command): void {
  program
    .command("analyze-pool <tickers...>")
    .description("Run full pipeline on multiple tickers and rank results")
    .option("--date <yyyy-mm-dd>", "Trade date")
    .option("--model <name>", "Override LLM model")
    .option("--provider <name>", "Override LLM provider")
    .option("--base-url <url>", "Override LLM base URL")
    .option("--max-tokens <n>", "Per-request max_tokens")
    .action(async (tickers: string[], opts: Record<string, string>) => {
      const tradeDate = opts.date ?? new Date().toISOString().slice(0, 10);
      const client = new BridgeClient();
      const api = new BridgeApi(client);
      const results: CandidateResult[] = [];

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

        const charLimit = Number(config.report_context_char_limit);
        const promptContext = {
          language: String(config.output_language ?? "Chinese"),
          ...(Number.isFinite(charLimit) && charLimit > 0
            ? { reportContextCharLimit: charLimit }
            : {}),
        };

        // Pick tools once (shared across all tickers).
        const toolNames = [
          ...ANALYST_TOOLS.marketFlow,
          ...ANALYST_TOOLS.macroRegime,
          ...ANALYST_TOOLS.mesoCommodity,
          ...ANALYST_TOOLS.holdingsIndustry,
          ...ANALYST_TOOLS.topHoldings,
        ];
        const allTools = await pickBridgeTools(api, toolNames);

        const toolSets = {
          marketFlow: allTools.filter((t) =>
            (ANALYST_TOOLS.marketFlow as readonly string[]).includes(t.name),
          ),
          macroRegime: allTools.filter((t) =>
            (ANALYST_TOOLS.macroRegime as readonly string[]).includes(t.name),
          ),
          mesoCommodity: allTools.filter((t) =>
            (ANALYST_TOOLS.mesoCommodity as readonly string[]).includes(t.name),
          ),
          catalystSentiment: [] as typeof allTools,
          holdingsIndustry: allTools.filter((t) =>
            (ANALYST_TOOLS.holdingsIndustry as readonly string[]).includes(t.name),
          ),
          topHoldings: allTools.filter((t) =>
            (ANALYST_TOOLS.topHoldings as readonly string[]).includes(t.name),
          ),
          bullBear: [] as typeof allTools,
          riskDebate: [] as typeof allTools,
        };

        console.log(
          pc.dim(
            `${llmHandle.provider}/${llmHandle.model} — ${tickers.length} tickers — ${tradeDate}`,
          ),
        );

        for (const ticker of tickers) {
          process.stdout.write(pc.yellow(`  ${ticker}... `));
          const graph = buildFullGraph({ llm: llmHandle.llm, tools: toolSets, promptContext });

          const final = await graph.invoke({
            messages: [new HumanMessage(ticker)],
            asset_of_interest: ticker,
            trade_date: tradeDate,
          });

          const signal = (final.trader_backtest_signal ?? {}) as Record<string, unknown>;
          const plan = String(final.trader_allocation_plan ?? "");
          const preview = plan.slice(0, 120).replace(/\n/g, " ");

          results.push({
            ticker,
            rating: String(signal.rating ?? "?"),
            weightPct: Number(signal.target_weight_pct ?? 0),
            planPreview: preview,
            signal,
          });

          console.log(pc.green(`${signal.rating ?? "?"} ${signal.target_weight_pct ?? "—"}%`));
        }

        // Rank: Buy > Overweight > Hold > Underweight > Sell; tie-break by weight
        const rankOrder: Record<string, number> = {
          Buy: 0,
          BUY: 0,
          Overweight: 1,
          OVERWEIGHT: 1,
          Hold: 2,
          HOLD: 2,
          Underweight: 3,
          UNDERWEIGHT: 3,
          Sell: 4,
          SELL: 4,
        };
        results.sort((a, b) => {
          const ra = rankOrder[a.rating] ?? 5;
          const rb = rankOrder[b.rating] ?? 5;
          return ra !== rb ? ra - rb : b.weightPct - a.weightPct;
        });

        console.log(pc.cyan("\n=== Ranked Results ==="));
        for (const r of results) {
          const tag = ["Buy", "BUY"].includes(r.rating)
            ? pc.green
            : ["Sell", "SELL"].includes(r.rating)
              ? pc.red
              : pc.white;
          console.log(
            `${tag(r.rating.padEnd(12))} ${r.weightPct.toFixed(1).padStart(6)}%  ${r.ticker}  ${pc.dim(r.planPreview)}`,
          );
        }
      } catch (err) {
        if (err instanceof RpcError) {
          console.error(pc.red(`bridge error: ${err.message}`));
        } else {
          console.error(pc.red(`error: ${(err as Error).message}`));
        }
        process.exitCode = 1;
      } finally {
        await client.close();
      }
    });
}
