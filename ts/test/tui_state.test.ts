import { describe, expect, it } from "vitest";
import {
  analystSelectionUnsupported,
  appendTickerToInput,
  clampRound,
  extractPriceRows,
  initState,
  multiRoundUnsupported,
  nextSectionId,
  normalizeBacktestResult,
  parseTickers,
  reducer,
  reportViewport,
  sortByTicker,
  sortReports,
} from "../src/tui/index.js";

describe("TUI state model", () => {
  it("parses bridge CSV price payloads and computes daily pct change", () => {
    const rows = extractPriceRows(`# ETF price data
Date,Open,High,Low,Close,Volume
2026-05-28,3.800,3.900,3.700,3.850,1000
2026-05-29,3.850,3.980,3.840,3.927,1250
`);

    expect(rows).toHaveLength(2);
    expect(rows[1]).toMatchObject({
      date: "2026-05-29",
      close: 3.927,
      high: 3.98,
      low: 3.84,
      volume: 1250,
    });
    expect(rows[1]?.pctChg).toBeCloseTo(2, 5);
  });

  it("keeps JSON row support for future bridge payloads", () => {
    const rows = extractPriceRows(
      JSON.stringify({
        rows: [
          { trade_date: "2026-05-28", close: 10, high: 11, low: 9, vol: 100 },
          { trade_date: "2026-05-29", close: 11, high: 12, low: 10, vol: 120 },
        ],
      }),
    );

    expect(rows[1]?.pctChg).toBeCloseTo(10, 5);
    expect(rows[1]?.volume).toBe(120);
  });

  it("parses and deduplicates multi-ticker input for the research queue", () => {
    expect(parseTickers("510300.SH, 159915.SZ 510300.sh；SPY")).toEqual([
      "510300.SH",
      "159915.SZ",
      "SPY",
    ]);
  });

  it("initializes queue items from parsed tickers when analysis starts", () => {
    const configured = reducer(
      { ...initState(), ticker: "510300.SH,159915.SZ" },
      { type: "openConfig" },
    );
    const running = reducer(configured, { type: "startAnalysis" });

    expect(running.tickers).toEqual(["510300.SH", "159915.SZ"]);
    expect(running.queue).toEqual([
      { ticker: "510300.SH", status: "pending" },
      { ticker: "159915.SZ", status: "pending" },
    ]);
  });

  it("appends multi-role debate reports instead of overwriting the section body", () => {
    const initial = reducer(initState(), { type: "startAnalysis" });
    const afterBull = reducer(initial, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "多空辩论 · 看多",
      body: "bull case",
    });
    const afterBear = reducer(afterBull, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "多空辩论 · 看空",
      body: "bear case",
    });

    expect(afterBear.reports.research_debate).toContain("bull case");
    expect(afterBear.reports.research_debate).toContain("bear case");
    expect(afterBear.reportNodes.research_debate).toEqual(["多空辩论 · 看多", "多空辩论 · 看空"]);
  });

  it("does not mark unfinished sections done when the analysis completes", () => {
    const initial = reducer(initState(), { type: "startAnalysis" });
    const withOneDone = reducer(initial, { type: "sectionDone", sectionId: "market_flow" });
    const done = reducer(withOneDone, { type: "analysisDone", result: "final" });

    expect(done.status).toBe("done");
    expect(done.sectionDone.has("market_flow")).toBe(true);
    expect(done.sectionDone.has("portfolio_manager")).toBe(false);
  });
});

// ===========================================================================
// P0: Full report reader
// ===========================================================================

describe("P0 report reader", () => {
  it("selects the first section when switching to a tab with no prior selection", () => {
    const start = reducer(initState(), { type: "startAnalysis" });
    const onResearch = reducer(start, { type: "setTab", tab: "research" });
    expect(onResearch.selectedSectionByTab.research).toBe("research_debate");
  });

  it("moves and wraps section selection within the active tab", () => {
    const ids = ["research_debate", "research"];
    expect(nextSectionId(ids, undefined, 1)).toBe("research_debate");
    expect(nextSectionId(ids, "research_debate", 1)).toBe("research");
    // wraps forward
    expect(nextSectionId(ids, "research", 1)).toBe("research_debate");
    // wraps backward
    expect(nextSectionId(ids, "research_debate", -1)).toBe("research");
  });

  it("clamps report scroll at the top and bottom", () => {
    const body = Array.from({ length: 50 }, (_, i) => `line ${i}`).join("\n");
    const top = reportViewport(body, -10, 18, 120);
    expect(top.scroll).toBe(0);
    expect(top.atTop).toBe(true);
    const bottom = reportViewport(body, 9999, 18, 120);
    expect(bottom.scroll).toBe(50 - 18);
    expect(bottom.atBottom).toBe(true);
  });

  it("resets section scroll when a report body is appended", () => {
    let state = reducer(initState(), { type: "startAnalysis" });
    state = reducer(state, { type: "setTab", tab: "research" });
    state = reducer(state, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "看多",
      body: Array.from({ length: 60 }, (_, i) => `l${i}`).join("\n"),
    });
    state = reducer(state, { type: "scrollReport", delta: 18 });
    expect(state.reportScrollBySection.research_debate).toBeGreaterThan(0);
    // appending new content resets the scroll back to the top
    state = reducer(state, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "看空",
      body: "more",
    });
    expect(state.reportScrollBySection.research_debate).toBe(0);
  });
});

// ===========================================================================
// P1: Analysis config parity
// ===========================================================================

describe("P1 analysis config", () => {
  it("defaults to all analysts enabled, standard depth, single round", () => {
    const s = initState();
    expect(Object.values(s.selectedAnalysts).every(Boolean)).toBe(true);
    expect(s.depth).toBe("standard");
    expect(s.debateRounds).toBe(1);
    expect(s.riskRounds).toBe(1);
  });

  it("toggles an analyst without mutating the default set", () => {
    const s = initState();
    const next = reducer(s, { type: "toggleAnalyst", id: "market_flow" });
    expect(next.selectedAnalysts.market_flow).toBe(false);
    // original state is untouched
    expect(s.selectedAnalysts.market_flow).toBe(true);
  });

  it("clamps debate/risk rounds to the supported range", () => {
    expect(clampRound(0)).toBe(1);
    expect(clampRound(99)).toBe(3);
    const s = reducer(initState(), { type: "stepRounds", field: "debateRounds", delta: -5 });
    expect(s.debateRounds).toBe(1);
  });

  it("flags multi-round and analyst-deselection as unsupported by the single-pass graph", () => {
    expect(multiRoundUnsupported(1, 1)).toBe(false);
    expect(multiRoundUnsupported(2, 1)).toBe(true);
    const s = reducer(initState(), { type: "toggleAnalyst", id: "top_holdings" });
    expect(analystSelectionUnsupported(initState().selectedAnalysts)).toBe(false);
    expect(analystSelectionUnsupported(s.selectedAnalysts)).toBe(true);
  });
});

// ===========================================================================
// P2: Report library
// ===========================================================================

describe("P2 report library", () => {
  it("sorts discovered reports newest-first", () => {
    const sorted = sortReports([
      { ticker: "510300.SH", date: "2026-01-01", path: "a" },
      { ticker: "159915.SZ", date: "2026-05-01", path: "b" },
      { ticker: "510300.SH", date: "2026-03-01", path: "c" },
    ]);
    expect(sorted.map((r) => r.date)).toEqual(["2026-05-01", "2026-03-01", "2026-01-01"]);
  });

  it("renders an empty state instead of throwing for no reports", () => {
    const s = reducer(initState(), { type: "libraryLoaded", reports: [] });
    expect(s.library.reports).toEqual([]);
    expect(s.library.bodyLoading).toBe(false);
  });

  it("opens a report body using the shared viewport state", () => {
    let s = reducer(initState(), {
      type: "libraryLoaded",
      reports: [{ ticker: "510300.SH", date: "2026-05-01", path: "p" }],
    });
    s = reducer(s, { type: "libraryBody", body: "line a\nline b" });
    expect(s.library.body).toContain("line a");
    expect(s.library.scroll).toBe(0);
    const view = reportViewport(s.library.body, s.library.scroll);
    expect(view.lines).toContain("line a");
  });
});

// ===========================================================================
// P3: Watchlist entry
// ===========================================================================

describe("P3 watchlist", () => {
  it("deduplicates a watchlist ticker against existing input", () => {
    expect(appendTickerToInput("510300.SH", "510300.SH")).toBe("510300.SH");
    expect(appendTickerToInput("510300.SH", "159915.SZ")).toBe("510300.SH,159915.SZ");
  });

  it("uses the shared parser so watchlist additions match manual input", () => {
    const merged = appendTickerToInput("510300.sh 159915.SZ", "159915.sz");
    expect(parseTickers(merged)).toEqual(["510300.SH", "159915.SZ"]);
  });

  it("adds the selected watchlist ticker to the input via the reducer", () => {
    let s = reducer(initState(), { type: "watchlistLoaded", tickers: ["510300.SH", "159915.SZ"] });
    s = reducer(s, { type: "watchlistMove", delta: 1 });
    s = reducer(s, { type: "watchlistAddToInput" });
    expect(s.ticker).toContain("159915.SZ");
  });
});

// ===========================================================================
// P4: Backtest viewer
// ===========================================================================

describe("P4 backtest viewer", () => {
  it("normalizes the bridge result shape with flat metrics", () => {
    const view = normalizeBacktestResult({
      metrics: { final_value: 1_050_000, cumulative_return: 0.05 },
      benchmark_metrics: [{ benchmark: "equal_weight_pool", cumulative_return: 0.03 }],
      nav: [{ nav: 1 }, { nav: 1.02 }, { nav: 1.05 }],
      trades: [{}, {}],
    });
    expect(view.metrics.final_value).toBe(1_050_000);
    expect(view.benchmarkMetrics).toHaveLength(1);
    expect(view.nav).toEqual([1, 1.02, 1.05]);
    expect(view.trades).toBe(2);
  });

  it("renders gracefully when benchmark and nav data are missing", () => {
    const view = normalizeBacktestResult({ metrics: { final_value: 1 } });
    expect(view.benchmarkMetrics).toEqual([]);
    expect(view.nav).toEqual([]);
    expect(view.health).toBeNull();
  });

  it("accepts the on-disk metrics.json shape and an explicit nav series", () => {
    const view = normalizeBacktestResult(
      { metrics: { sharpe_ratio: 1.2 }, health: { warnings: ["low coverage"] } },
      [1, 1.1, 1.2],
    );
    expect(view.metrics.sharpe_ratio).toBe(1.2);
    expect(view.nav).toEqual([1, 1.1, 1.2]);
    expect(view.health?.warnings).toEqual(["low coverage"]);
  });
});

// ===========================================================================
// P5: Paper trading
// ===========================================================================

describe("P5 paper trading", () => {
  it("sorts positions deterministically by ticker and clears prior errors", () => {
    let s = reducer(initState(), { type: "paperError", error: "boom" });
    s = reducer(s, {
      type: "paperLoaded",
      user: "u1",
      account: { total_assets: 1000 },
      positions: [{ ticker: "510300.SH" }, { ticker: "159915.SZ" }],
      trades: [],
    });
    expect(s.paper.error).toBeUndefined();
    expect(s.paper.positions.map((p) => p.ticker)).toEqual(["159915.SZ", "510300.SH"]);
  });

  it("renders an empty account cleanly", () => {
    const s = reducer(initState(), {
      type: "paperLoaded",
      account: null,
      positions: [],
      trades: [],
    });
    expect(s.paper.positions).toEqual([]);
    expect(s.paper.account).toBeNull();
  });

  it("sortByTicker is a stable deterministic order", () => {
    expect(sortByTicker([{ ticker: "B" }, { ticker: "A" }, { ticker: "C" }])).toEqual([
      { ticker: "A" },
      { ticker: "B" },
      { ticker: "C" },
    ]);
  });
});

// ===========================================================================
// P6: Error detail view
// ===========================================================================

describe("P6 error detail", () => {
  it("preserves the full message while exposing a short summary", () => {
    const long = "x".repeat(500);
    const s = reducer(initState(), {
      type: "setErrorDetail",
      detail: { message: long, ticker: "510300.SH", timestamp: "2026-05-31T00:00:00Z" },
    });
    expect(s.errorDetail?.message).toHaveLength(500);
    expect(s.errorDetail?.ticker).toBe("510300.SH");
  });

  it("toggles the detail overlay without losing the stored detail", () => {
    let s = reducer(initState(), {
      type: "setErrorDetail",
      detail: { message: "no stack here", timestamp: "2026-05-31T00:00:00Z" },
    });
    s = reducer(s, { type: "toggleErrorDetail" });
    expect(s.showErrorDetail).toBe(true);
    expect(s.errorDetail?.stack).toBeUndefined();
    s = reducer(s, { type: "toggleErrorDetail" });
    expect(s.showErrorDetail).toBe(false);
  });

  it("shows cancellation separately from a failure", () => {
    const start = reducer(initState(), { type: "startAnalysis" });
    const cancelled = reducer(start, { type: "queueCancelled" });
    expect(cancelled.status).toBe("error");
    expect(cancelled.errorMsg).toContain("取消");
    // a cancellation does not populate the structured error detail
    expect(cancelled.errorDetail).toBeNull();
  });
});
