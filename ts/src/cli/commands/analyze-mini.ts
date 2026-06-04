/**
 * `analyze-mini <ticker>` — Phase 2 sub-step 1 demo.
 *
 * Drives the minimal market_flow → trader graph against the running bridge
 * and prints the trader allocation plan markdown.
 */

import { HumanMessage } from "@langchain/core/messages";
import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, pickBridgeTools, RpcError } from "../../bridge/index.js";
import { buildMiniSpineGraph } from "../../graph/mini_spine.js";
import { createLlmFromConfig } from "../../llm/factory.js";

const MARKET_FLOW_TOOLS = [
  "get_etf_price_data",
  "get_etf_indicators",
  "get_etf_share",
  "get_etf_nav",
  "get_etf_universe",
];

interface AnalyzeMiniOptions {
  date?: string;
  model?: string;
  asOfDate?: string;
  provider?: string;
  baseUrl?: string;
  maxTokens?: string;
}

function positionSizingFromConfig(config: Record<string, unknown>) {
  const budget = Number(config.max_drawdown_budget);
  return Number.isFinite(budget) && budget > 0 ? { maxDrawdownBudget: budget } : {};
}

export function registerAnalyzeMini(program: Command): void {
  program
    .command("analyze-mini <ticker>")
    .description("Phase 2 demo: market_flow → trader minimal graph for one ticker")
    .option("--date <yyyy-mm-dd>", "Trade date the analysis is anchored to (default: today)")
    .option("--model <name>", "Override LLM model from bridge config")
    .option("--provider <name>", "Override LLM provider (openai, ollama, vllm, deepseek, ...)")
    .option("--base-url <url>", "Override LLM base URL (e.g. http://127.0.0.1:8020/v1)")
    .option("--max-tokens <n>", "Per-request max_tokens budget (useful for reasoning models)")
    .option("--as-of-date <yyyy-mm-dd>", "Run tool calls in backtest mode pinned to this date")
    .action(async (ticker: string, opts: AnalyzeMiniOptions) => {
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

        const tools = await pickBridgeTools(api, MARKET_FLOW_TOOLS, {
          ...(opts.asOfDate ? { context: { mode: "backtest", as_of_date: opts.asOfDate } } : {}),
        });

        const charLimit = Number(config.report_context_char_limit);
        const promptContext = {
          language: String(config.output_language ?? "Chinese"),
          ...(Number.isFinite(charLimit) && charLimit > 0
            ? { reportContextCharLimit: charLimit }
            : {}),
        };

        const graph = buildMiniSpineGraph({
          llm: llmHandle.llm,
          marketFlowTools: tools,
          promptContext,
          positionSizing: positionSizingFromConfig(config as Record<string, unknown>),
        });

        console.log(
          pc.dim(
            `provider=${llmHandle.provider} model=${llmHandle.model} ticker=${ticker} trade_date=${tradeDate}`,
          ),
        );

        const final = await graph.invoke({
          messages: [new HumanMessage(ticker)],
          asset_of_interest: ticker,
          trade_date: tradeDate,
        });

        console.log(pc.cyan("\n=== market_flow_report ==="));
        console.log(final.market_flow_report || pc.dim("(empty)"));
        console.log(pc.cyan("\n=== trader_allocation_plan ==="));
        console.log(final.trader_allocation_plan || pc.dim("(empty)"));
      } catch (err) {
        if (err instanceof RpcError) {
          console.error(pc.red(`bridge error [${err.code}]: ${err.message}`));
        } else {
          console.error(pc.red(`error: ${(err as Error).message}`));
        }
        const tail = client.stderrTail.trim();
        if (tail) {
          console.error(pc.dim("\n--- bridge stderr (tail) ---"));
          console.error(pc.dim(tail.slice(-2000)));
        }
        process.exitCode = 1;
      } finally {
        await client.close();
      }
    });
}
