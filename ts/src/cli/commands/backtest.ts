/**
 * `backtest <tickers>` — non-interactive candidate-pool backtest.
 *
 * Phase 4.1: collects signals per (rebalance_date, ticker), submits to
 * Python backtest runner via bridge RPC, and renders the results.
 */

import type { Command } from "commander";
import pc from "picocolors";
import { BridgeApi, BridgeClient, RpcError } from "../../bridge/index.js";

export function registerBacktest(program: Command): void {
  program
    .command("backtest <tickers...>")
    .description("Run candidate-pool backtest over a date range")
    .option("--start-date <yyyy-mm-dd>", "Start date (required)")
    .option("--end-date <yyyy-mm-dd>", "End date (required)")
    .option("--benchmark-tickers <list>", "Comma-separated benchmark tickers", "equal_weight_pool")
    .option("--output <path>", "Write CSV result to path")
    .action(async (tickers: string[], opts: Record<string, string>) => {
      if (!opts.startDate || !opts.endDate) {
        console.error(pc.red("--start-date and --end-date are required"));
        process.exit(1);
      }

      const client = new BridgeClient();
      const api = new BridgeApi(client);
      try {
        await client.start();

        const benchmarks = (opts.benchmarkTickers ?? "equal_weight_pool")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        console.log(pc.dim(`Backtest: ${tickers.join(",")} vs ${benchmarks.join(",")}`));
        console.log(pc.dim(`${opts.startDate} → ${opts.endDate}`));

        const result = await api.backtestRunCandidatePool({
          tickers,
          start_date: opts.startDate,
          end_date: opts.endDate,
          signals: {},
          benchmark_tickers: benchmarks.length > 0 ? benchmarks : null,
        });

        // Render results
        if (result.nav_curves) {
          console.log(pc.cyan("\n=== NAV Curve (last 5 points) ==="));
          const curves = result.nav_curves as Record<string, number[]>;
          for (const [name, values] of Object.entries(curves)) {
            const tail = values
              .slice(-5)
              .map((v) => v.toFixed(4))
              .join(" → ");
            console.log(`  ${name}: ${pc.dim("...→")} ${tail}`);
          }
        }

        if (result.metrics) {
          console.log(pc.cyan("\n=== Performance Metrics ==="));
          for (const [name, metrics] of Object.entries(
            result.metrics as Record<string, Record<string, number>>,
          )) {
            console.log(`  ${pc.bold(name)}:`);
            for (const [key, value] of Object.entries(metrics)) {
              const fmt = typeof value === "number" ? value.toFixed(4) : String(value);
              console.log(`    ${key}: ${fmt}`);
            }
          }
        }

        if (result.rankings) {
          console.log(pc.cyan("\n=== Rankings ==="));
          const rankings = result.rankings as Array<{ ticker: string; score: number }>;
          for (let i = 0; i < rankings.length; i++) {
            const r = rankings[i];
            if (!r) continue;
            console.log(`  ${i + 1}. ${r.ticker}  score=${r.score.toFixed(4)}`);
          }
        }

        if (opts.output && result.csv) {
          const fs = await import("node:fs/promises");
          await fs.writeFile(opts.output, String(result.csv));
          console.log(pc.green(`\nCSV written to ${opts.output}`));
        }
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
