import { describe, expect, it } from "vitest";
import { buildEffectiveMemoryConfig } from "../src/agents/nodes/memory_writer.js";
import {
  appendTickerToInput,
  backendDisplay,
  buildExecutionSummary,
  clampRound,
  extractPriceRows,
  initState,
  libraryTickers,
  nextSectionId,
  normalizeBacktestResult,
  parseTickers,
  priceRuler,
  reducer,
  reportDisplayViewport,
  reportsForTicker,
  reportViewport,
  selectedAnalystIds,
  sortByTicker,
  sortReports,
  summarizeReportBody,
  wrapToWidth,
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

  it("skips uncommented Key-snapshot summary lines and finds the real CSV header", () => {
    // Mirrors etfagents.dataflows.tushare._to_csv_with_header: a "# Key snapshot"
    // block whose summary lines are written WITHOUT a leading "#".
    const rows = extractPriceRows(`# Daily ETF Price Data
# Total records: 2
# Data retrieved on: 2026-05-29 10:00:00

# Key snapshot
Ticker: 510300.SH
Trade Date: 2026-05-29
Close: 3.927

trade_date,open,high,low,close,vol
2026-05-28,3.800,3.900,3.700,3.850,1000
2026-05-29,3.850,3.980,3.840,3.927,1250
`);

    expect(rows).toHaveLength(2);
    expect(rows[1]).toMatchObject({ date: "2026-05-29", close: 3.927, volume: 1250 });
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

  it("builds a Python-style execution summary from structured trigger rules", () => {
    const summary = buildExecutionSummary({
      trader_backtest_signal: {
        rating: "OVERWEIGHT",
        target_weight_pct: 25,
        target_weight_min_pct: 20,
        target_weight_max_pct: 30,
        execution_delay: "next_open",
        add_triggers: [
          {
            metric: "close",
            op: ">=",
            threshold: 3.95,
            action: "add",
            note: "放量突破后加仓",
          },
        ],
        reduce_triggers: [],
        exit_triggers: [],
        risk_rules: [
          {
            metric: "close",
            op: "<",
            threshold: 3.72,
            action: "exit",
            note: "跌破支撑止损",
          },
        ],
        add_conditions: ["价格站上3.95元后加仓"],
        reduce_conditions: [],
        risk_controls: ["跌破3.72元止损"],
      },
    });

    expect(summary).toMatchObject({
      rating: "OVERWEIGHT",
      targetWeightPct: 25,
      targetWeightMinPct: 20,
      targetWeightMaxPct: 30,
      targetPrice: 3.95,
      stopPrice: 3.72,
      executionDelay: "next_open",
    });
    expect(summary?.addConditions[0]).toContain("close >= 3.950");
    expect(summary?.riskControls[0]).toContain("close < 3.720");
  });

  it("falls back to Chinese condition text when trigger prices are not structured", () => {
    const summary = buildExecutionSummary({
      trader_backtest_signal: {
        rating: "HOLD",
        add_conditions: ["若价格突破3.95元并维持两日，可小幅加仓。"],
        reduce_conditions: ["若价格跌破3.72元，先降低仓位。"],
        risk_controls: [],
      },
    });

    expect(summary?.targetPrice).toBe(3.95);
    expect(summary?.stopPrice).toBe(3.72);
  });

  it("draws a sorted price ruler with the current marker", () => {
    expect(priceRuler(3.72, 3.88, 3.95, 12)).toContain("止损价 3.720");
    expect(priceRuler(3.72, 3.88, 3.95, 12)).toContain("╋ 现价 3.880");
    expect(priceRuler(3.72, 3.88, 3.95, 12)).toContain("目标价 3.950");
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

  it("stores the discovered vLLM backend URL for the analysis runner", () => {
    const state = reducer(initState(), {
      type: "vllmModelsFetched",
      models: ["local-model"],
      baseUrl: "http://127.0.0.1:8020/v1",
    });

    expect(state.vllmModels).toEqual(["local-model"]);
    expect(state.backendUrl).toBe("http://127.0.0.1:8020/v1");
    expect(backendDisplay("vllm", state.backendUrl)).toBe("http://127.0.0.1:8020/v1");
  });

  it("clears a stale backend URL when switching providers", () => {
    const state = reducer(
      {
        ...initState(),
        provider: "vllm",
        backendUrl: "http://127.0.0.1:8020/v1",
        selectOpen: "provider",
        selectIdx: 0,
      },
      { type: "selectPick" },
    );

    expect(state.provider).toBe("openai");
    expect(state.backendUrl).toBe("");
  });

  it("resets per-ticker section state when the next ticker starts", () => {
    let state = reducer({ ...initState(), ticker: "510300.SH,159915.SZ" }, { type: "openConfig" });
    state = reducer(state, { type: "startAnalysis" });
    // Ticker 1 runs and completes every section.
    state = reducer(state, { type: "queueTickerStarted", index: 0 });
    for (const id of [
      "market_flow",
      "catalyst_sentiment",
      "macro_regime",
      "meso_commodity",
      "holdings_industry",
      "top_holdings",
      "research_debate",
      "research",
      "trader",
      "risk_debate",
      "portfolio_manager",
    ]) {
      state = reducer(state, { type: "sectionDone", sectionId: id });
    }
    state = reducer(state, { type: "queueTickerDone", index: 0 });
    expect(state.sectionDone.size).toBe(11);

    // Ticker 2 starting must clear the aggregate so counters reflect the new run.
    state = reducer(state, { type: "queueTickerStarted", index: 1 });
    expect(state.sectionDone.size).toBe(0);
    expect(state.reports).toEqual({});
    expect(state.rating).toBe("");
    expect(state.executionSummary).toBeNull();
    // Queue history for the finished ticker is preserved.
    expect(state.queue[0]?.status).toBe("done");
    expect(state.queue[1]?.status).toBe("running");
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

  it("keeps team-section selection behind a detail overlay", () => {
    let state = reducer(initState(), { type: "startAnalysis" });
    expect(state.showTeamDetail).toBe(false);

    state = reducer(state, { type: "toggleTeamDetail" });
    expect(state.showTeamDetail).toBe(true);

    state = reducer(state, { type: "closeTeamDetail" });
    expect(state.showTeamDetail).toBe(false);
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

  it("renders markdown report structure without visible heading markers", () => {
    const view = reportDisplayViewport(
      [
        "### 市场与资金流",
        "",
        "资金净流入扩大，成交额同步放大。",
        "",
        "#### 1. 结论",
        "研究结论: **买入**",
      ].join("\n"),
      0,
      20,
      40,
    );

    expect(view.lines.map((line) => line.text)).toEqual([
      "市场与资金流",
      "",
      "资金净流入扩大，成交额同步放大。",
      "",
      "1. 结论",
      "研究结论: 买入",
    ]);
    expect(view.lines[0]?.kind).toBe("subheading");
    expect(view.lines[4]?.kind).toBe("subheading");
  });

  it("treats standalone bold Chinese numbered lines as headings", () => {
    const view = reportDisplayViewport(
      "**一、宏观暴露适配：从“金融溢价”向“真实需求”的切换**\n正文段落。",
      0,
      10,
      80,
    );

    expect(view.lines[0]).toMatchObject({
      kind: "subheading",
      text: "一、宏观暴露适配：从“金融溢价”向“真实需求”的切换",
    });
    expect(view.lines[1]?.text).toBe("正文段落。");
  });

  it("treats standalone Chinese numbered lines as headings", () => {
    const view = reportDisplayViewport(
      "二、真实需求确认：成交与份额同步改善\n正文段落。",
      0,
      10,
      80,
    );

    expect(view.lines[0]).toMatchObject({
      kind: "subheading",
      text: "二、真实需求确认：成交与份额同步改善",
    });
    expect(view.lines[1]?.kind).toBe("paragraph");
  });

  it("renders fenced code blocks as code lines", () => {
    const view = reportDisplayViewport("```text\nrating: buy\nweight: 20%\n```\n后续。", 0, 10, 40);

    expect(view.lines[0]).toMatchObject({ kind: "code", text: "rating: buy" });
    expect(view.lines[1]).toMatchObject({ kind: "code", text: "weight: 20%" });
    expect(view.lines[2]?.kind).toBe("paragraph");
  });

  it("wraps list items with continuation indentation", () => {
    const view = reportDisplayViewport(
      "- 资金流连续改善但仍需要等待成交量确认后再提高仓位",
      0,
      10,
      18,
    );

    expect(view.lines[0]?.kind).toBe("bullet");
    expect(view.lines[0]?.text.startsWith("• ")).toBe(true);
    expect(view.lines[1]?.text.startsWith("  ")).toBe(true);
  });

  it("wraps plain text at word-ish boundaries when available", () => {
    expect(wrapToWidth("alpha beta gamma", 10)).toEqual(["alpha beta", "gamma"]);
  });

  it("renders markdown tables as aligned terminal rows", () => {
    const view = reportDisplayViewport(
      [
        "| 指标 | 数值 | 说明 |",
        "| --- | ---: | --- |",
        "| 成交额 | 12.3亿元 | 放量 |",
        "| 净流入 | +2.1% | 改善 |",
      ].join("\n"),
      0,
      10,
      48,
    );

    const lines = view.lines.map((line) => line.text);
    expect(lines[0]).toContain("指标");
    expect(lines[0]).toContain("数值");
    expect(lines[0]).toContain("说明");
    expect(lines.some((line) => line.includes("| ---"))).toBe(false);
    expect(lines.some((line) => line.includes("成交额"))).toBe(true);
    expect(view.lines.every((line) => line.kind === "table")).toBe(true);
  });

  it("preserves section scroll when appending above the reader's current position", () => {
    let state = reducer(initState(), { type: "startAnalysis" });
    state = reducer(state, { type: "setTab", tab: "research" });
    state = reducer(state, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "看多",
      body: Array.from({ length: 60 }, (_, i) => `l${i}`).join("\n"),
    });
    state = reducer(state, { type: "scrollReport", delta: -999 });
    expect(state.reportScrollBySection.research_debate).toBe(0);
    // appending new content preserves the user's scroll when they are reading above the bottom
    state = reducer(state, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "看空",
      body: "more",
    });
    expect(state.reportScrollBySection.research_debate).toBe(0);
  });

  it("follows appended report content when the reader is already at the bottom", () => {
    let state = reducer(initState(), { type: "startAnalysis" });
    state = reducer(state, { type: "setTab", tab: "research" });
    state = reducer(state, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "看多",
      body: Array.from({ length: 60 }, (_, i) => `l${i}`).join("\n"),
    });
    const bottom = state.reportScrollBySection.research_debate ?? 0;
    expect(state.reportScrollBySection.research_debate).toBeGreaterThan(0);
    state = reducer(state, {
      type: "sectionReport",
      sectionId: "research_debate",
      nodeLabel: "看空",
      body: Array.from({ length: 20 }, (_, i) => `m${i}`).join("\n"),
    });
    expect(state.reportScrollBySection.research_debate).toBeGreaterThan(bottom);
  });
});

// ===========================================================================
// P1: Analysis config parity
// ===========================================================================

describe("P1 analysis config", () => {
  it("defaults to all analysts enabled and standard depth rounds", () => {
    const s = initState();
    expect(Object.values(s.selectedAnalysts).every(Boolean)).toBe(true);
    expect(s.depth).toBe("standard");
    expect(s.debateRounds).toBe(2);
    expect(s.riskRounds).toBe(2);
  });

  it("applies depth presets and marks manual round changes as custom", () => {
    let s = reducer(initState(), { type: "setFocus", focus: "depth" });
    s = reducer(s, { type: "openSelect" });
    s = reducer(s, { type: "selectDown" });
    s = reducer(s, { type: "selectPick" });
    expect(s.depth).toBe("deep");
    expect(s.debateRounds).toBe(3);
    expect(s.riskRounds).toBe(3);

    s = reducer(s, { type: "stepRounds", field: "riskRounds", delta: -1 });
    expect(s.depth).toBe("custom");
    expect(s.riskRounds).toBe(2);
  });

  it("does not open a select just because focus moves onto a select field", () => {
    let s = reducer(initState(), { type: "setFocus", focus: "depth" });
    expect(s.selectOpen).toBeNull();
    expect(s.selectIdx).toBe(0);

    s = reducer(s, { type: "openSelect" });
    expect(s.selectOpen).toBe("depth");
    // Current default depth is "standard", the second depth option.
    expect(s.selectIdx).toBe(1);
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

  it("overlays provider/model/rounds overrides into the effective memory config", () => {
    const base = {
      llm_provider: "openai",
      deep_think_llm: "gpt-x",
      quick_think_llm: "gpt-x-mini",
      max_debate_rounds: 1,
      results_dir: "/d",
    };
    const eff = buildEffectiveMemoryConfig(base, {
      provider: "deepseek",
      model: "deepseek-chat",
      baseUrl: "https://api.example/v1",
      debateRounds: 2,
      riskRounds: 3,
    });
    expect(eff).toMatchObject({
      llm_provider: "deepseek",
      // A model override applies to both tiers, so both keys must reflect it.
      deep_think_llm: "deepseek-chat",
      quick_think_llm: "deepseek-chat",
      backend_url: "https://api.example/v1",
      max_debate_rounds: 2,
      max_risk_discuss_rounds: 3,
      results_dir: "/d", // untouched runtime keys preserved
    });
    // Empty provider/model leave the base values intact.
    const eff2 = buildEffectiveMemoryConfig(base, {
      provider: "",
      model: "",
      debateRounds: 1,
      riskRounds: 1,
    });
    expect(eff2.llm_provider).toBe("openai");
    expect(eff2.deep_think_llm).toBe("gpt-x");
  });

  it("derives the selected analyst id list, reflecting toggles", () => {
    expect(selectedAnalystIds(initState().selectedAnalysts)).toEqual([
      "market_flow",
      "catalyst_sentiment",
      "macro_regime",
      "meso_commodity",
      "holdings_industry",
      "top_holdings",
    ]);
    const s = reducer(initState(), { type: "toggleAnalyst", id: "top_holdings" });
    expect(selectedAnalystIds(s.selectedAnalysts)).not.toContain("top_holdings");
  });

  it("refuses to toggle off the last remaining analyst", () => {
    // Turn every analyst off except market_flow.
    let s = initState();
    for (const id of [
      "catalyst_sentiment",
      "macro_regime",
      "meso_commodity",
      "holdings_industry",
      "top_holdings",
    ]) {
      s = reducer(s, { type: "toggleAnalyst", id });
    }
    expect(selectedAnalystIds(s.selectedAnalysts)).toEqual(["market_flow"]);
    // The last one cannot be turned off.
    const blocked = reducer(s, { type: "toggleAnalyst", id: "market_flow" });
    expect(selectedAnalystIds(blocked.selectedAnalysts)).toEqual(["market_flow"]);
  });

  it("hides a deselected analyst section from the dashboard tab", () => {
    let s = reducer(initState(), { type: "toggleAnalyst", id: "macro_regime" });
    s = reducer(s, { type: "startAnalysis" });
    // The analysts tab should no longer surface the deselected section.
    const onAnalysts = reducer(s, { type: "setTab", tab: "analysts" });
    expect(onAnalysts.selectedSectionByTab.analysts).not.toBe("macro_regime");
  });
});

// ===========================================================================
// Home / navigation
// ===========================================================================

describe("Home navigation", () => {
  it("starts at the home phase and opens the selected entry", () => {
    let s = initState();
    expect(s.phase).toBe("home");
    s = reducer(s, { type: "homeOpen" });
    expect(s.phase).toBe("ticker");
  });

  it("moves through home entries and opens report library", () => {
    let s = reducer(initState(), { type: "homeMove", delta: 1 });
    s = reducer(s, { type: "homeOpen" });
    expect(s.phase).toBe("library");
  });
});

// ===========================================================================
// P2: Report library
// ===========================================================================

describe("P2 report library", () => {
  it("sorts reports by ticker, then newest date within each ticker", () => {
    const sorted = sortReports([
      { ticker: "510300.SH", date: "2026-01-01", path: "a" },
      { ticker: "159915.SZ", date: "2026-05-01", path: "b" },
      { ticker: "510300.SH", date: "2026-03-01", path: "c" },
    ]);
    expect(sorted.map((r) => `${r.ticker}:${r.date}`)).toEqual([
      "159915.SZ:2026-05-01",
      "510300.SH:2026-03-01",
      "510300.SH:2026-01-01",
    ]);
    expect(libraryTickers(sorted)).toEqual(["159915.SZ", "510300.SH"]);
    expect(reportsForTicker(sorted, "510300.SH").map((r) => r.date)).toEqual([
      "2026-03-01",
      "2026-01-01",
    ]);
  });

  it("renders an empty state instead of throwing for no reports", () => {
    const s = reducer(initState(), { type: "libraryLoaded", reports: [] });
    expect(s.library.reports).toEqual([]);
    expect(s.library.bodyLoading).toBe(false);
  });

  it("moves between ticker groups and selectable report cards", () => {
    let s = reducer(initState(), {
      type: "libraryLoaded",
      reports: [
        { ticker: "510300.SH", date: "2026-01-01", path: "a" },
        { ticker: "159915.SZ", date: "2026-05-01", path: "b" },
        { ticker: "510300.SH", date: "2026-03-01", path: "c" },
      ],
    });
    expect(s.library.reports[s.library.selectedIdx]?.ticker).toBe("159915.SZ");

    s = reducer(s, { type: "librarySelect", delta: 1 });
    expect(s.library.reports[s.library.selectedIdx]).toMatchObject({
      ticker: "510300.SH",
      date: "2026-03-01",
    });

    s = reducer(s, { type: "libraryPane", pane: "reports" });
    s = reducer(s, { type: "librarySelect", delta: 1 });
    expect(s.library.reports[s.library.selectedIdx]).toMatchObject({
      ticker: "510300.SH",
      date: "2026-01-01",
    });
  });

  it("opens a selected report in a reader overlay using the shared viewport state", () => {
    let s = reducer(initState(), {
      type: "libraryLoaded",
      reports: [{ ticker: "510300.SH", date: "2026-05-01", path: "p" }],
    });
    s = reducer(s, { type: "libraryOpenReader" });
    expect(s.library.readerOpen).toBe(true);
    expect(s.library.bodyLoading).toBe(true);
    s = reducer(s, { type: "libraryBody", body: "line a\nline b" });
    expect(s.library.body).toContain("line a");
    expect(s.library.scroll).toBe(0);
    const view = reportViewport(s.library.body, s.library.scroll);
    expect(view.lines).toContain("line a");

    s = reducer(s, { type: "libraryCloseReader" });
    expect(s.library.readerOpen).toBe(false);
  });

  it("extracts report-card summaries from markdown body", () => {
    const summary = summarizeReportBody(
      [
        "## 投资组合经理决策",
        "Trade Date: 2026-06-03",
        "研究结论: **增持**，建议维持核心仓位。后续等待成交确认后再逐步提高暴露，不在卡片中展示整段原文。",
        "## 持仓建议",
        "目标仓位 20%-30%，回踩支撑后加仓。若高开过多则延后执行。",
        "## 再平衡与风险控制",
        "跌破 3.72 元先减仓，放量跌破止损。",
      ].join("\n"),
    );

    expect(summary.analysisDate).toBe("2026-06-03");
    expect(summary.rating).toBe("增持");
    expect(summary.recommendation).toContain("增持");
    expect(summary.recommendation).not.toContain("整段原文");
    expect(summary.strategy).toContain("目标仓位");
    expect(summary.riskControls).toContain("3.72");
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
