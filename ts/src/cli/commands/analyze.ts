/**
 * `analyze <ticker>` — full 6-analyst pipeline → trader.
 *
 * Phase 3.2: replaces analyze-mini with the full analyst suite.
 */

import { HumanMessage } from "@langchain/core/messages";
import type { Command } from "commander";
import pc from "picocolors";
import { buildEffectiveMemoryConfig } from "../../agents/nodes/memory_writer.js";
import { BridgeApi, BridgeClient, pickBridgeTools, RpcError } from "../../bridge/index.js";
import { buildFullGraph } from "../../graph/full_graph.js";
import { createLlmFromConfig } from "../../llm/factory.js";
import { ANALYST_TOOLS, fetchMemoryContext } from "./shared_tools.js";

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
        // Quick-tier LLM for analysts/researchers/risk debators (deep stays for
        // research manager, trader, PM). An explicit --model applies to both.
        const quickHandle = createLlmFromConfig(config, {
          tier: "quick",
          ...(opts.model ? { model: opts.model } : {}),
          ...(opts.provider ? { provider: opts.provider } : {}),
          ...(opts.baseUrl ? { baseUrl: opts.baseUrl } : {}),
          ...(opts.maxTokens ? { maxTokens: Number(opts.maxTokens) } : {}),
        });

        // Pick tools for each analyst.
        const toolSets = {
          marketFlow: await pickBridgeTools(api, ANALYST_TOOLS.marketFlow),
          macroRegime: await pickBridgeTools(api, ANALYST_TOOLS.macroRegime),
          mesoCommodity: await pickBridgeTools(api, ANALYST_TOOLS.mesoCommodity),
          catalystSentiment: await pickBridgeTools(api, ANALYST_TOOLS.catalystSentiment),
          holdingsIndustry: await pickBridgeTools(api, ANALYST_TOOLS.holdingsIndustry),
          topHoldings: await pickBridgeTools(api, ANALYST_TOOLS.topHoldings),
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

        // Effective config drives both memory write-back and the read-side
        // context build, so both describe the same run.
        const memoryConfig = buildEffectiveMemoryConfig(config as Record<string, unknown>, {
          ...(opts.provider ? { provider: opts.provider } : {}),
          ...(opts.model ? { model: opts.model } : {}),
          ...(opts.baseUrl ? { baseUrl: opts.baseUrl } : {}),
          debateRounds: 1,
          riskRounds: 1,
        });

        const graph = buildFullGraph({
          llm: llmHandle.llm,
          quickLlm: quickHandle.llm,
          tools: toolSets,
          promptContext,
          memoryConfig,
          persistMemory: async (payload) => {
            const res = await api.memoryAppendAnalysis(
              payload as {
                state: Record<string, unknown>;
                selected_analysts?: readonly string[] | null;
                config?: Record<string, unknown>;
              },
            );
            return res.entry;
          },
        });

        console.log(
          pc.dim(
            `provider=${llmHandle.provider} model=${llmHandle.model} ticker=${ticker} trade_date=${tradeDate}`,
          ),
        );
        console.log(pc.yellow("Running full pipeline: analysts → debate → trader → risk → PM"));

        // Read side of memory: hydrate continuity/lesson/method context.
        const memCtx = await fetchMemoryContext(api, ticker, tradeDate, memoryConfig);

        const final = await graph.invoke({
          messages: [new HumanMessage(ticker)],
          asset_of_interest: ticker,
          trade_date: tradeDate,
          ...memCtx,
        });

        if (final.research_allocation_plan) {
          console.log(pc.cyan("\n=== research_allocation_plan ==="));
          console.log(final.research_allocation_plan);
        }

        console.log(pc.cyan("\n=== trader_allocation_plan ==="));
        console.log(final.trader_allocation_plan || pc.dim("(empty)"));

        console.log(pc.cyan("\n=== final_allocation_decision (portfolio manager) ==="));
        console.log(final.final_allocation_decision || pc.dim("(empty)"));

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
