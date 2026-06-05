import type { AppDispatch, BacktestMeta, ReportMeta } from "../model.js";
import {
  extractPriceRows,
  normalizeBacktestResult,
  normalizeReportSummary,
  parseCsvLine,
  REPORT_SUMMARY_VERSION,
  reportSummaryToMeta,
  summarizeReportBody,
} from "../model.js";

// ===========================================================================
// Local artifact discovery (P2 report library, P3 watchlist, P4 backtest)
// ===========================================================================
//
// Mirrors cli/tui/services.py ReportRepository / BacktestViewer, reading the
// same on-disk report/backtest conventions under results_dir. Report cards may
// additionally write a small TS-side `summary.json` cache next to legacy
// `complete_report.md`; stale cache versions are rebuilt from the markdown.

const SKIP_REPORT_DIRS = new Set(["backtest", "memory"]);

export function resultsDir(): string {
  const env = process.env.ETFAGENTS_RESULTS_DIR ?? process.env.TRADINGAGENTS_RESULTS_DIR;
  if (env) return env;
  const home = process.env.HOME ?? process.env.USERPROFILE ?? ".";
  return `${home}/.etfagents/logs`;
}

export async function loadLibrary(dispatch: AppDispatch): Promise<void> {
  dispatch({ type: "libraryLoading" });
  try {
    const { readFile, readdir, stat, writeFile } = await import("node:fs/promises");
    const root = resultsDir();
    const reports: ReportMeta[] = [];
    let tickerDirs: string[] = [];
    try {
      tickerDirs = await readdir(root);
    } catch {
      dispatch({ type: "libraryLoaded", reports: [] });
      return;
    }
    for (const ticker of tickerDirs) {
      if (ticker.startsWith("_") || SKIP_REPORT_DIRS.has(ticker)) continue;
      const tickerPath = `${root}/${ticker}`;
      let dates: string[] = [];
      try {
        if (!(await stat(tickerPath)).isDirectory()) continue;
        dates = await readdir(tickerPath);
      } catch {
        continue;
      }
      for (const date of dates) {
        const path = `${tickerPath}/${date}`;
        const reportFile = `${path}/complete_report.md`;
        const summaryFile = `${path}/summary.json`;
        try {
          await stat(reportFile);
          let summary: Partial<ReportMeta> = {};
          try {
            const cached = normalizeReportSummary(
              JSON.parse(await readFile(summaryFile, "utf-8")),
              {
                ticker,
                reportDate: date,
              },
            );
            if (!cached || cached.schemaVersion !== REPORT_SUMMARY_VERSION) {
              throw new Error("stale report summary");
            }
            summary = reportSummaryToMeta(cached);
          } catch {
            try {
              const derived = summarizeReportBody(await readFile(reportFile, "utf-8"), {
                ticker,
                reportDate: date,
              });
              summary = reportSummaryToMeta(derived);
              try {
                await writeFile(summaryFile, JSON.stringify(derived, null, 2), "utf-8");
              } catch {
                /* derived summary remains usable even if the directory is read-only */
              }
            } catch {
              /* summary is optional; the reader can still open the full report */
            }
          }
          reports.push({ ticker, date, path, ...summary });
        } catch {
          /* no complete report in this date dir */
        }
      }
    }
    dispatch({ type: "libraryLoaded", reports });
  } catch (e) {
    dispatch({ type: "libraryError", error: (e as Error).message });
  }
}

export async function loadLibraryBody(record: ReportMeta, dispatch: AppDispatch): Promise<void> {
  dispatch({ type: "libraryBodyLoading" });
  try {
    const { readFile } = await import("node:fs/promises");
    const body = await readFile(`${record.path}/complete_report.md`, "utf-8");
    dispatch({ type: "libraryBody", body });
  } catch (e) {
    dispatch({ type: "libraryBody", body: `读取报告失败: ${(e as Error).message}` });
  }
}

function textField(state: Record<string, unknown>, key: string): string {
  const value = state[key];
  return typeof value === "string" ? value.trim() : "";
}

function debateField(debate: unknown, camelKey: string, snakeKey: string): string {
  if (!debate || typeof debate !== "object") return "";
  const record = debate as Record<string, unknown>;
  const value = record[camelKey] ?? record[snakeKey];
  return typeof value === "string" ? value.trim() : "";
}

function section(title: string, body: string): string {
  if (!body.trim()) return "";
  return `## ${title}\n\n${body.trim()}`;
}

function subsection(title: string, body: string): string {
  if (!body.trim()) return "";
  return `### ${title}\n\n${body.trim()}`;
}

function collapseMarkdown(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function buildCompleteReportMarkdown(args: {
  ticker: string;
  tradeDate: string;
  state: Record<string, unknown>;
}): string {
  const { ticker, tradeDate, state } = args;
  const analystBlocks = [
    subsection("市场与资金流", textField(state, "market_flow_report")),
    subsection("舆情与事件", textField(state, "catalyst_sentiment_report")),
    subsection("宏观框架", textField(state, "macro_regime_report")),
    subsection("中观大宗", textField(state, "meso_commodity_report")),
    subsection("持仓行业", textField(state, "holdings_industry_report")),
    subsection("头部持仓", textField(state, "top_holdings_report")),
  ].filter(Boolean);

  const investmentDebate = state.investment_debate_state;
  const researchBlocks = [
    subsection("多方观点", debateField(investmentDebate, "bullHistory", "bull_history")),
    subsection("空方观点", debateField(investmentDebate, "bearHistory", "bear_history")),
    subsection("研究经理", textField(state, "research_allocation_plan")),
  ].filter(Boolean);

  const riskDebate = state.risk_debate_state;
  const riskBlocks = [
    subsection("激进风险观点", debateField(riskDebate, "aggressiveHistory", "aggressive_history")),
    subsection(
      "保守风险观点",
      debateField(riskDebate, "conservativeHistory", "conservative_history"),
    ),
    subsection("中性风险观点", debateField(riskDebate, "neutralHistory", "neutral_history")),
  ].filter(Boolean);

  const blocks = [
    `# ETF配置分析报告: ${ticker}`,
    `分析日期: ${tradeDate}`,
    `生成时间: ${new Date().toISOString()}`,
    section("I. 分析团队报告", analystBlocks.join("\n\n")),
    section("II. 研究团队结论", researchBlocks.join("\n\n")),
    section("III. 配置团队计划", subsection("交易员", textField(state, "trader_allocation_plan"))),
    section("IV. 风险管理团队结论", riskBlocks.join("\n\n")),
    section(
      "V. 投资组合经理决策",
      subsection("投资组合经理", textField(state, "final_allocation_decision")),
    ),
  ].filter(Boolean);

  return collapseMarkdown(blocks.join("\n\n"));
}

export async function saveAnalysisReportArtifact(args: {
  ticker: string;
  tradeDate: string;
  state: Record<string, unknown>;
  config?: Record<string, unknown>;
}): Promise<string> {
  const { mkdir, writeFile } = await import("node:fs/promises");
  const libraryRoot = resultsDir();
  const configuredRoot =
    typeof args.config?.results_dir === "string" && args.config.results_dir.trim()
      ? args.config.results_dir.trim()
      : libraryRoot;
  const roots = Array.from(new Set([libraryRoot, configuredRoot]));
  const markdown = buildCompleteReportMarkdown(args);
  const primaryDir = `${libraryRoot}/${args.ticker}/${args.tradeDate}`;

  for (const root of roots) {
    const dir = `${root}/${args.ticker}/${args.tradeDate}`;
    await mkdir(dir, { recursive: true });
    await writeFile(`${dir}/complete_report.md`, markdown, "utf-8");

    const signals = args.state.agent_signals;
    if (signals && typeof signals === "object") {
      await writeFile(`${dir}/agent_signals.json`, JSON.stringify(signals, null, 2), "utf-8");
      const summaries = Object.fromEntries(
        Object.entries(signals as Record<string, unknown>)
          .map(([source, signal]) => [
            source,
            signal && typeof signal === "object"
              ? (signal as Record<string, unknown>).decision_summary
              : undefined,
          ])
          .filter((entry): entry is [string, unknown] => entry[1] !== undefined),
      );
      if (Object.keys(summaries).length > 0) {
        await writeFile(
          `${dir}/decision_signal_summaries.json`,
          JSON.stringify(summaries, null, 2),
          "utf-8",
        );
      }
    }
  }
  return `${primaryDir}/complete_report.md`;
}

export async function loadRecentReportTickers(): Promise<string[]> {
  const { readdir, stat } = await import("node:fs/promises");
  const root = resultsDir();
  let tickerDirs: string[] = [];
  try {
    tickerDirs = await readdir(root);
  } catch {
    return [];
  }
  const tickers: string[] = [];
  for (const ticker of tickerDirs) {
    if (ticker.startsWith("_") || SKIP_REPORT_DIRS.has(ticker)) continue;
    try {
      if ((await stat(`${root}/${ticker}`)).isDirectory()) tickers.push(ticker.toUpperCase());
    } catch {
      /* skip */
    }
  }
  return tickers.slice(0, 12);
}

/** P3: prefer the real watchlist, falling back to recent report tickers. */
export async function loadWatchlist(dispatch: AppDispatch): Promise<void> {
  try {
    const { BridgeApi, BridgeClient } = await import("../../bridge/index.js");
    const client = new BridgeClient({ defaultTimeoutMs: 10_000 });
    try {
      await client.start();
      const api = new BridgeApi(client);
      const entries = await api.watchlistList({ group: "default" });
      const tickers = entries
        .map((entry) => entry.ticker?.toUpperCase())
        .filter((ticker): ticker is string => Boolean(ticker));
      if (tickers.length > 0) {
        dispatch({ type: "watchlistLoaded", tickers: tickers.slice(0, 12) });
        return;
      }
    } catch {
      /* fall back to recent report history */
    } finally {
      await client.close();
    }
    dispatch({ type: "watchlistLoaded", tickers: await loadRecentReportTickers() });
  } catch {
    dispatch({ type: "watchlistLoaded", tickers: [] });
  }
}

export async function walkForFile(root: string, target: string): Promise<string[]> {
  const { readdir, stat } = await import("node:fs/promises");
  const found: string[] = [];
  async function recurse(dir: string): Promise<void> {
    let entries: string[];
    try {
      entries = await readdir(dir);
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = `${dir}/${entry}`;
      try {
        const info = await stat(full);
        if (info.isDirectory()) await recurse(full);
        else if (entry === target) found.push(full);
      } catch {
        /* skip */
      }
    }
  }
  await recurse(root);
  return found;
}

export async function loadBacktests(dispatch: AppDispatch): Promise<void> {
  dispatch({ type: "backtestLoading" });
  try {
    const { readFile, stat } = await import("node:fs/promises");
    const metricsFiles = await walkForFile(`${resultsDir()}/backtest`, "metrics.json");
    const records: Array<BacktestMeta & { mtime: number }> = [];
    for (const metricsPath of metricsFiles) {
      const dir = metricsPath.slice(0, metricsPath.lastIndexOf("/"));
      let manifest: Record<string, unknown> = {};
      let cumulativeReturn: number | undefined;
      try {
        manifest = JSON.parse(await readFile(`${dir}/manifest.json`, "utf-8"));
      } catch {
        /* manifest optional */
      }
      try {
        const m = JSON.parse(await readFile(metricsPath, "utf-8"));
        const cr = (m.metrics as Record<string, unknown> | undefined)?.cumulative_return;
        if (typeof cr === "number") cumulativeReturn = cr;
      } catch {
        /* metrics optional */
      }
      let mtime = 0;
      try {
        mtime = (await stat(metricsPath)).mtimeMs;
      } catch {
        /* ignore */
      }
      records.push({
        path: dir,
        tickers: Array.isArray(manifest.tickers) ? (manifest.tickers as string[]) : [],
        startDate: String(manifest.start_date ?? ""),
        endDate: String(manifest.end_date ?? ""),
        ...(cumulativeReturn !== undefined ? { cumulativeReturn } : {}),
        mtime,
      });
    }
    records.sort((a, b) => b.mtime - a.mtime);
    dispatch({
      type: "backtestLoaded",
      records: records.map(({ mtime: _m, ...rest }) => rest),
    });
  } catch (e) {
    dispatch({ type: "backtestError", error: (e as Error).message });
  }
}

export async function loadBacktestView(record: BacktestMeta, dispatch: AppDispatch): Promise<void> {
  try {
    const { readFile } = await import("node:fs/promises");
    const metrics = JSON.parse(await readFile(`${record.path}/metrics.json`, "utf-8"));
    let nav: number[] = [];
    try {
      const navCsv = await readFile(`${record.path}/nav.csv`, "utf-8");
      const rows = extractPriceRows(navCsv);
      nav = rows.map((r) => r.close).filter((v): v is number => v !== undefined);
      if (nav.length === 0) {
        // nav.csv uses a `nav` column, not `close`; parse it directly.
        const lines = navCsv.trim().split("\n");
        const header = parseCsvLine(lines[0] ?? "");
        const navIdx = header.findIndex((h) => h.toLowerCase() === "nav");
        if (navIdx >= 0) {
          nav = lines
            .slice(1)
            .map((l) => Number(parseCsvLine(l)[navIdx]))
            .filter((v) => Number.isFinite(v));
        }
      }
    } catch {
      /* nav optional */
    }
    let trades = 0;
    try {
      const tradesCsv = await readFile(`${record.path}/trades.csv`, "utf-8");
      trades = Math.max(0, tradesCsv.trim().split("\n").length - 1);
    } catch {
      /* trades optional */
    }
    const view = normalizeBacktestResult(metrics, nav);
    view.trades = trades;
    dispatch({ type: "backtestView", view });
  } catch (e) {
    dispatch({ type: "backtestError", error: (e as Error).message });
  }
}

export async function loadPaper(dispatch: AppDispatch): Promise<void> {
  dispatch({ type: "paperLoading" });
  const { BridgeApi, BridgeClient } = await import("../../bridge/index.js");
  const client = new BridgeClient();
  try {
    await client.start();
    const api = new BridgeApi(client);
    const [user, account, positions, trades] = await Promise.all([
      api.paperCurrentUser().then((r) => r.user),
      api.paperGetAccount(),
      api.paperGetPositions(),
      api.paperGetTrades({ limit: 20 }),
    ]);
    dispatch({
      type: "paperLoaded",
      user,
      account: account as unknown as Record<string, unknown>,
      positions: positions as unknown as Array<Record<string, unknown>>,
      trades: trades as unknown as Array<Record<string, unknown>>,
    });
  } catch (e) {
    const msg = (e as Error).message;
    dispatch({
      type: "paperError",
      error:
        msg.includes("ECONNREFUSED") || msg.includes("connect")
          ? "Bridge 未运行。请先启动 Python bridge。"
          : msg,
    });
  } finally {
    await client.close();
  }
}
