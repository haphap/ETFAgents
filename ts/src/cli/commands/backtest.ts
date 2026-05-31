/**
 * `backtest <tickers>` — non-interactive candidate-pool backtest.
 *
 * The Python Backtrader engine owns the rebalance schedule: it decides which
 * decision dates it queries while running. The TypeScript side therefore has
 * to *precompute* a signal payload for every one of those decision dates and
 * submit the whole bundle up front (the bridge does not call back into TS
 * mid-run). Signals are supplied via `--signals-file`; an empty bundle would
 * fail at the first rebalance date, so we require the file rather than silently
 * submitting `{}`.
 *
 * Generating the signals bundle (running the analyst pipeline for each
 * rebalance date) requires a rebalance-schedule RPC that is not implemented
 * yet — see the PR description / docs for the follow-up.
 */

import { readFileSync } from "node:fs";
import type { Command } from "commander";
import pc from "picocolors";
import {
  type BacktestSignalsByDate,
  BridgeApi,
  BridgeClient,
  RpcError,
} from "../../bridge/index.js";

function loadSignalsFile(path: string): BacktestSignalsByDate {
  const parsed = JSON.parse(readFileSync(path, "utf-8")) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("signals file must be a JSON object keyed by decision date (yyyy-mm-dd)");
  }
  for (const [date, bucket] of Object.entries(parsed as Record<string, unknown>)) {
    if (!Array.isArray(bucket)) {
      throw new Error(`signals['${date}'] must be an array of signal payloads`);
    }
  }
  return parsed as BacktestSignalsByDate;
}

export function registerBacktest(program: Command): void {
  program
    .command("backtest <tickers...>")
    .description("Run candidate-pool backtest over a date range")
    .option("--start-date <yyyy-mm-dd>", "Start date (required)")
    .option("--end-date <yyyy-mm-dd>", "End date (required)")
    .option(
      "--signals-file <path>",
      "JSON file of precomputed signals keyed by decision date (required)",
    )
    .option("--benchmark-tickers <list>", "Comma-separated benchmark tickers", "equal_weight_pool")
    .option("--timeout <seconds>", "Bridge RPC timeout in seconds (0 disables)", "900")
    .option("--output <path>", "Write CSV result to path")
    .action(async (tickers: string[], opts: Record<string, string>) => {
      if (!opts.startDate || !opts.endDate) {
        console.error(pc.red("--start-date and --end-date are required"));
        process.exit(1);
      }
      if (!opts.signalsFile) {
        console.error(
          pc.red(
            "--signals-file is required: a JSON object keyed by decision date (yyyy-mm-dd) → " +
              "array of analyze_candidate_pool signal payloads. The Python engine looks up a " +
              "signal for every rebalance date it visits, so all of them must be precomputed.",
          ),
        );
        process.exit(1);
      }

      let signals: BacktestSignalsByDate;
      try {
        signals = loadSignalsFile(opts.signalsFile);
      } catch (err) {
        console.error(pc.red(`Failed to load --signals-file: ${(err as Error).message}`));
        process.exit(1);
      }

      const timeoutSec = Number(opts.timeout);
      const timeoutMs = Number.isFinite(timeoutSec) && timeoutSec > 0 ? timeoutSec * 1000 : 0;

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

        const result = await api.backtestRunCandidatePool(
          {
            tickers,
            start_date: opts.startDate,
            end_date: opts.endDate,
            signals,
            benchmark_tickers: benchmarks.length > 0 ? benchmarks : null,
          },
          { timeoutMs },
        );

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
