import { describe, expect, it } from "vitest";
import { extractPriceRows, initState, parseTickers, reducer } from "../src/tui/index.js";

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
