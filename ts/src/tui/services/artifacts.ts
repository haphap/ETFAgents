import type { AppDispatch, BacktestMeta, ReportMeta } from "../model.js";
import { extractPriceRows, normalizeBacktestResult, parseCsvLine } from "../model.js";

// ===========================================================================
// Local artifact discovery (P2 report library, P3 watchlist, P4 backtest)
// ===========================================================================
//
// Mirrors cli/tui/services.py ReportRepository / BacktestViewer, reading the
// same on-disk conventions under results_dir. We do not invent a new TS-only
// persistence format; we read what the Python pipeline already writes.

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
    const { readdir, stat } = await import("node:fs/promises");
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
        try {
          await stat(`${path}/complete_report.md`);
          reports.push({ ticker, date, path });
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
