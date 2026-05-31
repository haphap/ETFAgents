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
    .option("--output <path>", "Write the full result JSON to path")
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

        // Render results. The bridge returns BacktraderBacktestResult.to_dict()
        // (asdict), so the shape is the dataclass fields: a flat `metrics`
        // object, `nav` / `benchmark_nav` records, `benchmark_metrics`,
        // `trades`, etc. See etfagents/backtest/backtrader_engine.py.
        const fmtNum = (v: unknown): string =>
          typeof v === "number" && Number.isFinite(v) ? v.toFixed(4) : String(v ?? "—");
        const fmtPct = (v: unknown): string =>
          typeof v === "number" && Number.isFinite(v)
            ? `${(v * 100).toFixed(2)}%`
            : String(v ?? "—");

        // Strategy NAV curve (list of {date, nav, cash, gross_exposure}).
        const nav = result.nav as Array<{ date?: string; nav?: number }> | undefined;
        if (Array.isArray(nav) && nav.length > 0) {
          console.log(pc.cyan("\n=== NAV Curve (last 5 points) ==="));
          for (const row of nav.slice(-5)) {
            console.log(`  ${row.date ?? "?"}: ${fmtNum(row.nav)}`);
          }
        }

        // Strategy performance metrics (flat BacktraderMetrics object).
        const metrics = result.metrics as Record<string, unknown> | undefined;
        if (metrics && typeof metrics === "object") {
          console.log(pc.cyan("\n=== Performance Metrics ==="));
          console.log(`  ${pc.bold("最终净值")}: ${fmtNum(metrics.final_value)}`);
          console.log(`  ${pc.bold("累计收益")}: ${fmtPct(metrics.cumulative_return)}`);
          console.log(`  ${pc.bold("年化收益")}: ${fmtPct(metrics.annualized_return)}`);
          console.log(`  ${pc.bold("年化波动")}: ${fmtPct(metrics.annualized_volatility)}`);
          console.log(`  ${pc.bold("最大回撤")}: ${fmtPct(metrics.max_drawdown)}`);
          console.log(`  ${pc.bold("夏普比率")}: ${fmtNum(metrics.sharpe_ratio)}`);
          console.log(`  ${pc.bold("交易笔数")}: ${metrics.total_trades ?? "—"}`);
          console.log(`  ${pc.bold("平均换手")}: ${fmtPct(metrics.average_turnover)}`);
        }

        // Benchmark comparison (list of BacktraderBenchmarkMetrics).
        const benchMetrics = result.benchmark_metrics as Array<Record<string, unknown>> | undefined;
        if (Array.isArray(benchMetrics) && benchMetrics.length > 0) {
          console.log(pc.cyan("\n=== Benchmark Comparison ==="));
          for (const b of benchMetrics) {
            console.log(
              `  ${pc.bold(String(b.benchmark ?? "?"))}: ` +
                `累计 ${fmtPct(b.cumulative_return)} · ` +
                `超额 ${fmtPct(b.excess_cumulative_return)} · ` +
                `信息比率 ${fmtNum(b.information_ratio)}`,
            );
          }
        }

        const trades = result.trades as unknown[] | undefined;
        if (Array.isArray(trades)) {
          console.log(pc.dim(`\ntrades=${trades.length}`));
        }

        // --output writes the full result JSON (the bridge does not emit CSV).
        if (opts.output) {
          const fs = await import("node:fs/promises");
          await fs.writeFile(opts.output, JSON.stringify(result, null, 2));
          console.log(pc.green(`\nResult JSON written to ${opts.output}`));
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
