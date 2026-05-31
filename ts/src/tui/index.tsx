#!/usr/bin/env node
/**
 * etfagents-ts TUI — Python-aligned analysis console.
 *
 * Drives the full pipeline graph (buildFullGraph): 6 analysts → bull/bear
 * debate → research manager → trader → risk debate → portfolio manager.
 * Streams per-node updates so each team tab fills in live.
 *
 * Layout matches cli/tui/screens/research.py AnalysisRunScreen:
 *   Left pane (22ch): ETF card, metadata, cancel, queue
 *   Right top: team tabs (分析团队|研究|交易|风险|决策) with counts
 *   Right bottom: selected tab's section checklist + reports / progress log
 *   Stats bar: Stages | rating | Reports | timer
 */

import { pathToFileURL } from "node:url";
import { Box, render, Text, useInput } from "ink";
import { useEffect, useReducer, useRef, useState } from "react";
import type { LlmOptions } from "../llm/factory.js";

// ===========================================================================
// Banner
// ===========================================================================

const BANNER = [
  "╔══════════════════════════════════════════════╗",
  "║                                              ║",
  "║   _____ _____ _____ _                    _   ║",
  "║  | ____|_   _|  ___/ \\   __ _  ___ _ __ | |_ ║",
  "║  |  _|   | | | |_ / _ \\ / _` |/ _ \\ '_ \\| __|║",
  "║  | |___  | | |  _/ ___ \\ (_| |  __/ | | | |_ ║",
  "║  |_____| |_| |_|/_/   \\_\\__, |\\___|_| |_|\\__|║",
  "║                         |___/                 ║",
  "║                                              ║",
  "║      Multi-Agent ETF Investment Framework     ║",
  "║               TypeScript Edition              ║",
  "║                                              ║",
  "╚══════════════════════════════════════════════╝",
];

// ===========================================================================
// Provider / Model catalog
// ===========================================================================

const PROVIDERS = ["openai", "deepseek", "ollama", "xai", "openrouter", "minimax", "vllm"] as const;

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o3", "o4-mini"],
  deepseek: ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro"],
  ollama: ["llama3.2", "qwen2.5", "mistral", "gemma3"],
  xai: ["grok-3-beta", "grok-3-mini"],
  openrouter: [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-chat",
  ],
  minimax: ["abab6.5s-chat", "abab7-chat"],
  vllm: [],
};

// ===========================================================================
// Analysis config catalog (P1) — mirrors cli/tui/services.py AnalysisConfig.
// ===========================================================================

/** Six analyst sections, in pipeline order. Toggleable in the config modal. */
const ANALYST_IDS = [
  "market_flow",
  "catalyst_sentiment",
  "macro_regime",
  "meso_commodity",
  "holdings_industry",
  "top_holdings",
] as const;

const DEPTH_OPTIONS = ["quick", "standard", "deep"] as const;
type Depth = (typeof DEPTH_OPTIONS)[number];
const DEPTH_LABELS: Record<Depth, string> = {
  quick: "快速",
  standard: "标准",
  deep: "深度",
};

/** Report body viewport (lines) and wrap width used by the P0 reader. */
const REPORT_VIEWPORT = 18;
const REPORT_WIDTH = 116;

// ===========================================================================
// Pipeline section model — mirrors cli/tui/services.py SECTION_DEFINITIONS
// and the node graph built by buildFullGraph (PR #86 full pipeline).
// ===========================================================================

type Team = "分析师" | "研究" | "交易" | "风险" | "决策";

interface SectionDef {
  id: string;
  title: string;
  team: Team;
}

const DEFAULT_SECTIONS: SectionDef[] = [
  { id: "market_flow", title: "市场与资金流", team: "分析师" },
  { id: "catalyst_sentiment", title: "舆情与事件", team: "分析师" },
  { id: "macro_regime", title: "宏观框架", team: "分析师" },
  { id: "meso_commodity", title: "中观大宗", team: "分析师" },
  { id: "holdings_industry", title: "持仓行业", team: "分析师" },
  { id: "top_holdings", title: "头部持仓", team: "分析师" },
  { id: "research_debate", title: "多空辩论", team: "研究" },
  { id: "research", title: "研究经理", team: "研究" },
  { id: "trader", title: "交易员", team: "交易" },
  { id: "risk_debate", title: "风险辩论", team: "风险" },
  { id: "portfolio_manager", title: "投资组合经理", team: "决策" },
];

/** Tab groups rendered in the dashboard (order matters). */
const TEAM_TABS: ReadonlyArray<{ key: string; team: Team; label: string }> = [
  { key: "analysts", team: "分析师", label: "📊 分析团队" },
  { key: "research", team: "研究", label: "📖 研究" },
  { key: "trader", team: "交易", label: "💹 交易" },
  { key: "risk", team: "风险", label: "⚠️ 风险" },
  { key: "decision", team: "决策", label: "🎯 决策" },
];

function sectionGroups(selected?: Record<string, boolean>): Record<string, SectionDef[]> {
  const groups: Record<string, SectionDef[]> = {};
  for (const tab of TEAM_TABS) {
    groups[tab.key] = DEFAULT_SECTIONS.filter(
      (d) =>
        d.team === tab.team &&
        // Hide analyst sections that the user deselected in the config.
        (d.team !== "分析师" || !selected || selected[d.id] !== false),
    );
  }
  return groups;
}

/**
 * Maps each graph node to the UI section it advances, the state key it writes,
 * and a progress label. `completes` marks the node that finishes a multi-node
 * section (e.g. the debate group is "done" only after its last debator runs).
 * Nodes absent here (e.g. the per-analyst `*_tools` ToolNodes) are tool rounds.
 */
const NODE_INFO: Record<
  string,
  { section: string; key: string; label: string; completes: boolean }
> = {
  market_flow: {
    section: "market_flow",
    key: "market_flow_report",
    label: "市场与资金流",
    completes: true,
  },
  macro_regime: {
    section: "macro_regime",
    key: "macro_regime_report",
    label: "宏观框架",
    completes: true,
  },
  meso_commodity: {
    section: "meso_commodity",
    key: "meso_commodity_report",
    label: "中观大宗",
    completes: true,
  },
  catalyst_sentiment: {
    section: "catalyst_sentiment",
    key: "catalyst_sentiment_report",
    label: "舆情与事件",
    completes: true,
  },
  holdings_industry: {
    section: "holdings_industry",
    key: "holdings_industry_report",
    label: "持仓行业",
    completes: true,
  },
  top_holdings: {
    section: "top_holdings",
    key: "top_holdings_report",
    label: "头部持仓",
    completes: true,
  },
  bull_researcher: {
    section: "research_debate",
    key: "bull_researcher_report",
    label: "多空辩论 · 看多",
    completes: false,
  },
  bear_researcher: {
    section: "research_debate",
    key: "bear_researcher_report",
    label: "多空辩论 · 看空",
    completes: true,
  },
  research_manager: {
    section: "research",
    key: "research_allocation_plan",
    label: "研究经理",
    completes: true,
  },
  trader: {
    section: "trader",
    key: "trader_allocation_plan",
    label: "交易员",
    completes: true,
  },
  aggressive_debator: {
    section: "risk_debate",
    key: "aggressive_debator_response",
    label: "风险辩论 · 激进",
    completes: false,
  },
  conservative_debator: {
    section: "risk_debate",
    key: "conservative_debator_response",
    label: "风险辩论 · 保守",
    completes: false,
  },
  neutral_debator: {
    section: "risk_debate",
    key: "neutral_debator_response",
    label: "风险辩论 · 中性",
    completes: true,
  },
  portfolio_manager: {
    section: "portfolio_manager",
    key: "final_allocation_decision",
    label: "投资组合经理",
    completes: true,
  },
};

// ===========================================================================
// State
// ===========================================================================

type Phase = "ticker" | "config" | "dashboard" | "library" | "backtest" | "paper";
type ConfigField =
  | "date"
  | "provider"
  | "model"
  | "depth"
  | "analysts"
  | "debateRounds"
  | "riskRounds";
type SectionStatus = "pending" | "running" | "done" | "failed";

/** Structured failure detail surfaced in the P6 error overlay. */
interface ErrorDetail {
  ticker?: string;
  section?: string;
  message: string;
  stack?: string;
  timestamp: string;
}

/** A discovered historical report (P2) or backtest artifact (P4). */
interface ReportMeta {
  ticker: string;
  date: string;
  path: string;
  rating?: string;
}

interface BacktestMeta {
  path: string;
  tickers: string[];
  startDate: string;
  endDate: string;
  cumulativeReturn?: number;
}

interface BacktestView {
  metrics: Record<string, unknown>;
  benchmarkMetrics: Array<Record<string, unknown>>;
  health: Record<string, unknown> | null;
  nav: number[];
  trades: number;
}

interface QueueItem {
  ticker: string;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
}

interface ExecutionSummary {
  rating?: string;
  targetWeightPct?: number;
  targetWeightMinPct?: number;
  targetWeightMaxPct?: number;
  executionDelay?: string;
  addConditions: string[];
  reduceConditions: string[];
  riskControls: string[];
}

interface PriceRow {
  date?: string;
  name?: string;
  close?: number;
  pctChg?: number;
  high?: number;
  low?: number;
  volume?: number;
}

interface AppState {
  phase: Phase;
  ticker: string;
  tickers: string[];
  queue: QueueItem[];
  currentTickerIdx: number;
  date: string;
  provider: string;
  model: string;
  /** Analysis config (P1) */
  selectedAnalysts: Record<string, boolean>;
  depth: Depth;
  debateRounds: number;
  riskRounds: number;
  backendUrl: string;
  /** Config modal state */
  focus: ConfigField;
  selectOpen: ConfigField | null;
  selectIdx: number;
  /** Cursor over analyst toggles when the "analysts" row is focused. */
  analystCursor: number;
  /** Dashboard state */
  status: "idle" | "running" | "done" | "error";
  result: string;
  errorMsg: string;
  logs: string[];
  /** Section completion tracking */
  sectionDone: Set<string>;
  sectionStatus: Record<string, SectionStatus>;
  activeSection: string;
  /** Per-section report bodies, keyed by section id (filled as nodes finish). */
  reports: Record<string, string>;
  reportNodes: Record<string, string[]>;
  /** Which team tab is focused in the dashboard. */
  activeTab: string;
  /** P0 report reader: selected section per tab + scroll offset per section. */
  selectedSectionByTab: Record<string, string>;
  reportScrollBySection: Record<string, number>;
  /** Final portfolio-manager rating extracted from the trader signal. */
  rating: string;
  /** Stats from analysis runner */
  stats: { llm_calls: number; tool_calls: number; tokens: number };
  executionSummary: ExecutionSummary | null;
  /** ETF detail loaded from bridge (basic info card) */
  etfDetail: {
    name?: string;
    close?: number;
    pctChg?: number;
    high?: number;
    low?: number;
    volume?: number;
    volumeChangePct?: number;
    history?: number[];
    loading: boolean;
    error?: string;
  } | null;
  /** vllm */
  vllmModels: string[] | null;
  /** P6 structured error detail + overlay visibility. */
  errorDetail: ErrorDetail | null;
  showErrorDetail: boolean;
  /** P3 watchlist (read-only, derived from discovered report history). */
  watchlist: string[];
  watchlistIdx: number;
  /** P2 report library. */
  library: {
    loading: boolean;
    error?: string;
    reports: ReportMeta[];
    selectedIdx: number;
    body: string;
    bodyLoading: boolean;
    scroll: number;
  };
  /** P4 backtest viewer. */
  backtest: {
    loading: boolean;
    error?: string;
    records: BacktestMeta[];
    selectedIdx: number;
    view: BacktestView | null;
  };
  /** P5 paper trading snapshot. */
  paper: {
    loading: boolean;
    error?: string;
    user?: string;
    account: Record<string, unknown> | null;
    positions: Array<Record<string, unknown>>;
    trades: Array<Record<string, unknown>>;
  };
}

type Action =
  | { type: "appendTicker"; char: string }
  | { type: "deleteTicker" }
  | { type: "openConfig" }
  | { type: "setFocus"; focus: ConfigField }
  | { type: "appendChar"; char: string }
  | { type: "deleteChar" }
  | { type: "openSelect" }
  | { type: "closeSelect" }
  | { type: "selectUp" }
  | { type: "selectDown" }
  | { type: "selectPick" }
  | { type: "startAnalysis" }
  | { type: "appendLog"; msg: string }
  | { type: "queueTickerStarted"; index: number }
  | { type: "queueTickerDone"; index: number }
  | { type: "queueTickerFailed"; index: number; msg: string }
  | { type: "queueCancelled" }
  | { type: "sectionStarted"; sectionId: string }
  | { type: "sectionDone"; sectionId: string }
  | { type: "sectionFailed"; sectionId: string }
  | { type: "sectionReport"; sectionId: string; nodeLabel: string; body: string }
  | { type: "setRating"; rating: string }
  | { type: "setStats"; stats: { llm_calls?: number; tool_calls?: number; tokens?: number } }
  | { type: "setExecutionSummary"; summary: ExecutionSummary }
  | { type: "setTab"; tab: string }
  | { type: "analysisDone"; result: string }
  | { type: "analysisError"; msg: string }
  | { type: "backToTicker" }
  | { type: "etfDetailLoading" }
  | {
      type: "etfDetailLoaded";
      name?: string;
      close?: number;
      pctChg?: number;
      high?: number;
      low?: number;
      volume?: number;
      volumeChangePct?: number;
      history?: number[];
    }
  | { type: "etfDetailError"; error: string }
  | { type: "vllmModelsFetched"; models: string[] }
  | { type: "vllmModelsFailed" }
  // P1 config
  | { type: "toggleAnalyst"; id: string }
  | { type: "moveAnalystCursor"; delta: number }
  | { type: "stepRounds"; field: "debateRounds" | "riskRounds"; delta: number }
  | { type: "setBackend"; url: string }
  // P0 report reader
  | { type: "selectSection"; delta: number }
  | { type: "scrollReport"; delta: number }
  // P2 / P4 / P5 navigation
  | { type: "goPhase"; phase: Phase }
  // P2 library
  | { type: "libraryLoading" }
  | { type: "libraryLoaded"; reports: ReportMeta[] }
  | { type: "libraryError"; error: string }
  | { type: "librarySelect"; delta: number }
  | { type: "libraryBodyLoading" }
  | { type: "libraryBody"; body: string }
  | { type: "libraryScroll"; delta: number }
  // P3 watchlist
  | { type: "watchlistLoaded"; tickers: string[] }
  | { type: "watchlistMove"; delta: number }
  | { type: "watchlistAddToInput" }
  // P4 backtest
  | { type: "backtestLoading" }
  | { type: "backtestLoaded"; records: BacktestMeta[] }
  | { type: "backtestError"; error: string }
  | { type: "backtestSelect"; delta: number }
  | { type: "backtestView"; view: BacktestView }
  // P5 paper
  | { type: "paperLoading" }
  | {
      type: "paperLoaded";
      user?: string;
      account: Record<string, unknown> | null;
      positions: Array<Record<string, unknown>>;
      trades: Array<Record<string, unknown>>;
    }
  | { type: "paperError"; error: string }
  // P6 error detail
  | { type: "setErrorDetail"; detail: ErrorDetail }
  | { type: "toggleErrorDetail" };

type AppDispatch = (action: Action) => void;

// ===========================================================================
// Helpers
// ===========================================================================

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function initSectionStatus(): Record<string, SectionStatus> {
  return Object.fromEntries(DEFAULT_SECTIONS.map((s) => [s.id, "pending" as const]));
}

function initSelectedAnalysts(): Record<string, boolean> {
  return Object.fromEntries(ANALYST_IDS.map((id) => [id, true]));
}

/** Section ids belonging to a team tab, in pipeline order. */
function sectionsForTab(tab: string, selected?: Record<string, boolean>): string[] {
  return (sectionGroups(selected)[tab] ?? []).map((s) => s.id);
}

/** P0: move section selection within a tab, wrapping at the ends. */
export function nextSectionId(
  sectionIds: readonly string[],
  current: string | undefined,
  delta: number,
): string | undefined {
  if (sectionIds.length === 0) return undefined;
  const i = current ? sectionIds.indexOf(current) : -1;
  if (i < 0) return delta >= 0 ? sectionIds[0] : sectionIds[sectionIds.length - 1];
  const next = (i + delta + sectionIds.length) % sectionIds.length;
  return sectionIds[next];
}

/** Wrap a single logical line to a max width, preserving word-ish breaks. */
function wrapToWidth(line: string, width: number): string[] {
  if (line.length <= width) return [line];
  const out: string[] = [];
  for (let i = 0; i < line.length; i += width) out.push(line.slice(i, i + width));
  return out;
}

/**
 * P0: produce the visible report viewport. Returns the wrapped lines, the
 * clamped scroll offset, the total wrapped-line count, and edge flags so the
 * caller can render a scroll indicator without recomputing.
 */
export function reportViewport(
  body: string,
  scroll: number,
  viewport = REPORT_VIEWPORT,
  width = REPORT_WIDTH,
): { lines: string[]; scroll: number; total: number; atTop: boolean; atBottom: boolean } {
  const wrapped = body.split("\n").flatMap((line) => wrapToWidth(line, width));
  const total = wrapped.length;
  const maxScroll = Math.max(0, total - viewport);
  const clamped = Math.max(0, Math.min(scroll, maxScroll));
  return {
    lines: wrapped.slice(clamped, clamped + viewport),
    scroll: clamped,
    total,
    atTop: clamped === 0,
    atBottom: clamped >= maxScroll,
  };
}

/** P1: rounds clamp to the supported range (graph is single-pass: max 1 active). */
export function clampRound(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.max(1, Math.min(3, Math.round(n)));
}

/** P0/P5: the analyst section ids that are currently selected. */
export function selectedAnalystIds(selected: Record<string, boolean>): string[] {
  return ANALYST_IDS.filter((id) => selected[id] !== false);
}

/**
 * P4: accept either the bridge result shape (flat `metrics`) or the on-disk
 * metrics.json shape ({ metrics, benchmark_metrics, health }) and normalize.
 */
export function normalizeBacktestResult(
  obj: Record<string, unknown>,
  nav: number[] = [],
): BacktestView {
  const metrics = (obj.metrics as Record<string, unknown> | undefined) ?? {};
  const benchmarkMetrics = Array.isArray(obj.benchmark_metrics)
    ? (obj.benchmark_metrics as Array<Record<string, unknown>>)
    : [];
  const health = (obj.health as Record<string, unknown> | undefined) ?? null;
  const navFromResult = Array.isArray(obj.nav)
    ? (obj.nav as Array<{ nav?: number }>)
        .map((r) => (typeof r.nav === "number" ? r.nav : undefined))
        .filter((v): v is number => v !== undefined)
    : [];
  const trades = Array.isArray(obj.trades) ? (obj.trades as unknown[]).length : 0;
  return {
    metrics,
    benchmarkMetrics,
    health,
    nav: nav.length > 0 ? nav : navFromResult,
    trades,
  };
}

/** P2/P4: newest-first ordering by date then ticker. */
export function sortReports(reports: ReportMeta[]): ReportMeta[] {
  return [...reports].sort((a, b) =>
    b.date !== a.date ? b.date.localeCompare(a.date) : a.ticker.localeCompare(b.ticker),
  );
}

/** P5: deterministic position ordering by ticker. */
export function sortByTicker<T extends { ticker?: unknown }>(rows: T[]): T[] {
  return [...rows].sort((a, b) => String(a.ticker ?? "").localeCompare(String(b.ticker ?? "")));
}

/** P3: merge a watchlist ticker into the current input, deduplicating. */
export function appendTickerToInput(input: string, ticker: string): string {
  const merged = parseTickers(`${input} ${ticker}`);
  return merged.join(",");
}

export function parseTickers(input: string): string[] {
  const seen = new Set<string>();
  const tickers: string[] = [];
  for (const raw of input.split(/[\s,，;；]+/)) {
    const ticker = raw.trim().toUpperCase();
    if (!ticker || seen.has(ticker)) continue;
    seen.add(ticker);
    tickers.push(ticker);
  }
  return tickers;
}

function dateDaysBefore(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return isoDate;
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        current += '"';
        i += 1;
      } else {
        quoted = !quoted;
      }
    } else if (char === "," && !quoted) {
      cells.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current);
  return cells.map((cell) => cell.trim());
}

function valueByKeys(row: Record<string, unknown>, keys: readonly string[]): unknown {
  for (const key of keys) {
    if (row[key] !== undefined) return row[key];
  }
  const lowerMap = new Map(Object.entries(row).map(([key, value]) => [key.toLowerCase(), value]));
  for (const key of keys) {
    const value = lowerMap.get(key.toLowerCase());
    if (value !== undefined) return value;
  }
  return undefined;
}

function normalizePriceRows(rows: Array<Record<string, unknown>>): PriceRow[] {
  const normalized = rows
    .map((row) => {
      const name = valueByKeys(row, ["name", "Name", "fund_name"]);
      const close = asNumber(valueByKeys(row, ["Close", "close"]));
      const pctChg = asNumber(valueByKeys(row, ["pct_chg", "PctChg", "ChangePct"]));
      const high = asNumber(valueByKeys(row, ["High", "high"]));
      const low = asNumber(valueByKeys(row, ["Low", "low"]));
      const volume = asNumber(valueByKeys(row, ["Volume", "vol", "volume"]));
      return {
        date: String(valueByKeys(row, ["Date", "trade_date", "date"]) ?? ""),
        ...(typeof name === "string" && name ? { name } : {}),
        ...(close !== undefined ? { close } : {}),
        ...(pctChg !== undefined ? { pctChg } : {}),
        ...(high !== undefined ? { high } : {}),
        ...(low !== undefined ? { low } : {}),
        ...(volume !== undefined ? { volume } : {}),
      };
    })
    .filter((row) => row.close !== undefined || row.high !== undefined || row.low !== undefined);

  for (let i = 1; i < normalized.length; i += 1) {
    const row = normalized[i];
    const prev = normalized[i - 1];
    if (
      row?.pctChg === undefined &&
      row?.close !== undefined &&
      prev?.close !== undefined &&
      prev.close !== 0
    ) {
      row.pctChg = ((row.close - prev.close) / prev.close) * 100;
    }
  }
  return normalized;
}

/** Column names that identify the real tabular header in a price CSV payload. */
const PRICE_COLUMN_KEYS = new Set([
  "date",
  "trade_date",
  "close",
  "open",
  "high",
  "low",
  "vol",
  "volume",
  "amount",
  "pct_chg",
]);

export function extractPriceRows(text: string): PriceRow[] {
  try {
    const raw = JSON.parse(text) as { rows?: Array<Record<string, unknown>> };
    return normalizePriceRows(raw.rows ?? []);
  } catch {
    const lines = text
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#"));
    // _to_csv_with_header() appends un-commented summary lines (e.g.
    // "Ticker: 510300.SH", "Close: 3.927") before the real CSV table, so the
    // first non-comment line is not necessarily the header. Find the actual
    // tabular header: a comma-separated row containing a known column name.
    const headerIdx = lines.findIndex((line) => {
      const cells = parseCsvLine(line).map((cell) => cell.trim().toLowerCase());
      return cells.length >= 2 && cells.some((cell) => PRICE_COLUMN_KEYS.has(cell));
    });
    const headerLine = headerIdx >= 0 ? lines[headerIdx] : undefined;
    if (!headerLine) return [];
    const headers = parseCsvLine(headerLine);
    const rows = lines.slice(headerIdx + 1).map((line) => {
      const values = parseCsvLine(line);
      return Object.fromEntries(headers.map((header, i) => [header, values[i] ?? ""]));
    });
    return normalizePriceRows(rows);
  }
}

function sparkline(values: readonly number[], width = 16): string {
  if (values.length === 0) return "";
  const sample = values.slice(-width);
  const min = Math.min(...sample);
  const max = Math.max(...sample);
  const blocks = "▁▂▃▄▅▆▇█";
  if (max === min) return "▁".repeat(sample.length);
  return sample
    .map((value) => {
      const idx = Math.round(((value - min) / (max - min)) * (blocks.length - 1));
      return blocks[idx] ?? "▁";
    })
    .join("");
}

function listFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item))
    .filter(Boolean)
    .slice(0, 3);
}

function queueStatusLabel(status: QueueItem["status"]): string {
  switch (status) {
    case "pending":
      return "等待";
    case "running":
      return "分析中";
    case "done":
      return "已完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
  }
}

function buildExecutionSummary(finalState: Record<string, unknown>): ExecutionSummary | null {
  const signal = finalState.trader_backtest_signal as Record<string, unknown> | undefined;
  if (!signal) return null;
  const summary: ExecutionSummary = {
    addConditions: listFromUnknown(signal.add_conditions),
    reduceConditions: listFromUnknown(signal.reduce_conditions),
    riskControls: listFromUnknown(signal.risk_controls),
  };
  const rating = signal.rating;
  if (typeof rating === "string" && rating) summary.rating = rating;
  const target = asNumber(signal.target_weight_pct);
  if (target !== undefined) summary.targetWeightPct = target;
  const targetMin = asNumber(signal.target_weight_min_pct);
  if (targetMin !== undefined) summary.targetWeightMinPct = targetMin;
  const targetMax = asNumber(signal.target_weight_max_pct);
  if (targetMax !== undefined) summary.targetWeightMaxPct = targetMax;
  const delay = signal.execution_delay;
  if (typeof delay === "string" && delay) summary.executionDelay = delay;
  return summary;
}

export function initState(): AppState {
  return {
    phase: "ticker",
    ticker: "",
    tickers: [],
    queue: [],
    currentTickerIdx: 0,
    date: today(),
    provider: "",
    model: "",
    selectedAnalysts: initSelectedAnalysts(),
    depth: "standard",
    debateRounds: 1,
    riskRounds: 1,
    backendUrl: "",
    focus: "date",
    selectOpen: null,
    selectIdx: 0,
    analystCursor: 0,
    status: "idle",
    result: "",
    errorMsg: "",
    logs: [],
    sectionDone: new Set(),
    sectionStatus: initSectionStatus(),
    activeSection: "",
    reports: {},
    reportNodes: {},
    activeTab: "analysts",
    selectedSectionByTab: {},
    reportScrollBySection: {},
    rating: "",
    stats: { llm_calls: 0, tool_calls: 0, tokens: 0 },
    executionSummary: null,
    etfDetail: null,
    vllmModels: null,
    errorDetail: null,
    showErrorDetail: false,
    watchlist: [],
    watchlistIdx: 0,
    library: {
      loading: false,
      reports: [],
      selectedIdx: 0,
      body: "",
      bodyLoading: false,
      scroll: 0,
    },
    backtest: { loading: false, records: [], selectedIdx: 0, view: null },
    paper: { loading: false, account: null, positions: [], trades: [] },
  };
}

function focusValue(state: AppState): string {
  switch (state.focus) {
    case "date":
      return state.date;
    case "provider":
      return state.provider;
    case "model":
      return state.model;
    case "depth":
      return state.depth;
    default:
      return "";
  }
}

function selectOptions(state: AppState): string[] {
  if (state.selectOpen === "provider") return [...PROVIDERS];
  if (state.selectOpen === "model") {
    const p = state.provider.toLowerCase();
    if (p === "vllm") return state.vllmModels ?? [];
    return MODELS_BY_PROVIDER[p] ?? [];
  }
  if (state.selectOpen === "depth") return [...DEPTH_OPTIONS];
  return [];
}

function modelHasOptions(state: AppState): boolean {
  if (!state.provider) return false;
  const p = state.provider.toLowerCase();
  if (p === "vllm") return (state.vllmModels?.length ?? 0) > 0;
  return (MODELS_BY_PROVIDER[p]?.length ?? 0) > 0;
}

function isSelectField(state: AppState, field: ConfigField): boolean {
  if (field === "provider") return true;
  if (field === "depth") return true;
  if (field === "model") return modelHasOptions(state);
  return false;
}

const FOCUS_ORDER: ConfigField[] = [
  "date",
  "provider",
  "model",
  "depth",
  "analysts",
  "debateRounds",
  "riskRounds",
];
function nextFocus(current: ConfigField): ConfigField {
  const i = FOCUS_ORDER.indexOf(current);
  return FOCUS_ORDER[i + 1] ?? FOCUS_ORDER[0] ?? "date";
}

// ===========================================================================
// Reducer
// ===========================================================================

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "appendTicker":
      return { ...state, ticker: state.ticker + action.char };
    case "deleteTicker":
      return { ...state, ticker: state.ticker.slice(0, -1) };
    case "openConfig":
      return {
        ...state,
        phase: "config",
        tickers: parseTickers(state.ticker),
        focus: "date",
        selectOpen: null,
        selectIdx: 0,
        analystCursor: 0,
        vllmModels: null,
        errorMsg: "",
        status: "idle",
        logs: [],
        result: "",
        sectionDone: new Set(),
        sectionStatus: initSectionStatus(),
        activeSection: "",
        reports: {},
        reportNodes: {},
        activeTab: "analysts",
        selectedSectionByTab: {},
        reportScrollBySection: {},
        rating: "",
        stats: { llm_calls: 0, tool_calls: 0, tokens: 0 },
        executionSummary: null,
        etfDetail: null,
        errorDetail: null,
        showErrorDetail: false,
      };
    case "setFocus":
      return {
        ...state,
        focus: action.focus,
        selectOpen: isSelectField(state, action.focus) ? action.focus : null,
        selectIdx: 0,
      };
    case "appendChar": {
      if (state.selectOpen !== null) return state;
      const key = state.focus;
      return { ...state, [key]: focusValue(state) + action.char };
    }
    case "deleteChar": {
      if (state.selectOpen !== null) return state;
      const key = state.focus;
      return { ...state, [key]: focusValue(state).slice(0, -1) };
    }
    case "openSelect": {
      if (!isSelectField(state, state.focus)) return state;
      const idx = selectOptions({ ...state, selectOpen: state.focus }).indexOf(focusValue(state));
      return { ...state, selectOpen: state.focus, selectIdx: idx >= 0 ? idx : 0 };
    }
    case "closeSelect":
      return { ...state, selectOpen: null, selectIdx: 0 };
    case "selectUp": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      if (opts.length === 0) return state;
      return { ...state, selectIdx: state.selectIdx > 0 ? state.selectIdx - 1 : opts.length - 1 };
    }
    case "selectDown": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      if (opts.length === 0) return state;
      return { ...state, selectIdx: state.selectIdx < opts.length - 1 ? state.selectIdx + 1 : 0 };
    }
    case "selectPick": {
      if (state.selectOpen === null) return state;
      const opts = selectOptions(state);
      const value = opts[state.selectIdx];
      if (value === undefined) return { ...state, selectOpen: null, selectIdx: 0 };
      const newProvider = state.selectOpen === "provider" ? value : state.provider;
      const newModel = state.selectOpen === "provider" ? "" : state.model;
      const vllmModels =
        state.selectOpen === "provider" && newProvider.toLowerCase() !== "vllm"
          ? null
          : state.vllmModels;
      return {
        ...state,
        provider: newProvider,
        model: newModel,
        [state.selectOpen]: value,
        selectOpen: null,
        selectIdx: 0,
        vllmModels,
      };
    }
    case "startAnalysis": {
      const tickers = state.tickers.length > 0 ? state.tickers : parseTickers(state.ticker);
      return {
        ...state,
        phase: "dashboard",
        status: "running",
        tickers,
        queue: tickers.map((ticker) => ({ ticker, status: "pending" })),
        currentTickerIdx: 0,
        result: "",
        errorMsg: "",
        logs: [],
        sectionDone: new Set(),
        sectionStatus: initSectionStatus(),
        activeSection: "",
        reports: {},
        reportNodes: {},
        activeTab: "analysts",
        selectedSectionByTab: {},
        reportScrollBySection: {},
        rating: "",
        stats: { llm_calls: 0, tool_calls: 0, tokens: 0 },
        executionSummary: null,
        etfDetail: { loading: true },
        errorDetail: null,
        showErrorDetail: false,
      };
    }
    case "appendLog":
      return { ...state, logs: [...state.logs, action.msg] };
    case "queueTickerStarted":
      return {
        ...state,
        currentTickerIdx: action.index,
        queue: state.queue.map((item, i) =>
          i === action.index ? { ...item, status: "running" } : item,
        ),
        // Section/report state is per-ticker: clear it when a new ticker starts
        // so tab counters and "Agents N/N" reflect the current run, not the
        // aggregate of tickers already finished.
        sectionDone: new Set(),
        sectionStatus: initSectionStatus(),
        activeSection: "",
        reports: {},
        reportNodes: {},
        selectedSectionByTab: {},
        reportScrollBySection: {},
        rating: "",
        executionSummary: null,
      };
    case "queueTickerDone":
      return {
        ...state,
        queue: state.queue.map((item, i) =>
          i === action.index ? { ...item, status: "done" } : item,
        ),
      };
    case "queueTickerFailed":
      return {
        ...state,
        errorMsg: action.msg,
        queue: state.queue.map((item, i) =>
          i === action.index ? { ...item, status: "failed" } : item,
        ),
      };
    case "queueCancelled":
      return {
        ...state,
        status: "error",
        errorMsg: "分析已取消。",
        queue: state.queue.map((item) =>
          item.status === "pending" || item.status === "running"
            ? { ...item, status: "cancelled" }
            : item,
        ),
      };
    case "sectionStarted":
      return {
        ...state,
        activeSection: action.sectionId,
        sectionStatus: { ...state.sectionStatus, [action.sectionId]: "running" },
      };
    case "sectionDone": {
      const next = new Set(state.sectionDone);
      next.add(action.sectionId);
      return {
        ...state,
        sectionDone: next,
        sectionStatus: { ...state.sectionStatus, [action.sectionId]: "done" },
      };
    }
    case "sectionFailed":
      return {
        ...state,
        sectionStatus: { ...state.sectionStatus, [action.sectionId]: "failed" },
      };
    case "sectionReport": {
      const previous = state.reports[action.sectionId];
      const nextBody = previous
        ? `${previous.trim()}\n\n### ${action.nodeLabel}\n\n${action.body.trim()}`
        : `### ${action.nodeLabel}\n\n${action.body.trim()}`;
      return {
        ...state,
        reports: { ...state.reports, [action.sectionId]: nextBody },
        reportNodes: {
          ...state.reportNodes,
          [action.sectionId]: [...(state.reportNodes[action.sectionId] ?? []), action.nodeLabel],
        },
        // P0: reset scroll so freshly appended content is visible from the top.
        reportScrollBySection: { ...state.reportScrollBySection, [action.sectionId]: 0 },
      };
    }
    case "setRating":
      return { ...state, rating: action.rating };
    case "setStats":
      return {
        ...state,
        stats: {
          llm_calls: state.stats.llm_calls + (action.stats.llm_calls ?? 0),
          tool_calls: state.stats.tool_calls + (action.stats.tool_calls ?? 0),
          tokens: state.stats.tokens + (action.stats.tokens ?? 0),
        },
      };
    case "setExecutionSummary":
      return { ...state, executionSummary: action.summary };
    case "setTab": {
      // P0: when entering a tab with no prior selection, select its first section.
      const ids = sectionsForTab(action.tab, state.selectedAnalysts);
      const selectedSectionByTab =
        state.selectedSectionByTab[action.tab] || ids.length === 0
          ? state.selectedSectionByTab
          : { ...state.selectedSectionByTab, [action.tab]: ids[0] as string };
      return { ...state, activeTab: action.tab, selectedSectionByTab };
    }
    case "analysisDone": {
      return { ...state, status: "done", result: action.result };
    }
    case "analysisError":
      return { ...state, status: "error", errorMsg: action.msg };
    case "backToTicker":
      return { ...state, phase: "ticker", errorMsg: "", selectOpen: null, selectIdx: 0 };
    case "etfDetailLoading":
      return { ...state, etfDetail: { loading: true } };
    case "etfDetailLoaded":
      return {
        ...state,
        etfDetail: {
          loading: false,
          ...(action.name !== undefined ? { name: action.name } : {}),
          ...(action.close !== undefined ? { close: action.close } : {}),
          ...(action.pctChg !== undefined ? { pctChg: action.pctChg } : {}),
          ...(action.high !== undefined ? { high: action.high } : {}),
          ...(action.low !== undefined ? { low: action.low } : {}),
          ...(action.volume !== undefined ? { volume: action.volume } : {}),
          ...(action.volumeChangePct !== undefined
            ? { volumeChangePct: action.volumeChangePct }
            : {}),
          ...(action.history !== undefined ? { history: action.history } : {}),
        },
      };
    case "etfDetailError":
      return { ...state, etfDetail: { loading: false, error: action.error } };
    case "vllmModelsFetched":
      return { ...state, vllmModels: action.models };
    case "vllmModelsFailed":
      return { ...state, vllmModels: [] };

    // --- P1 config ---
    case "toggleAnalyst":
      return {
        ...state,
        selectedAnalysts: {
          ...state.selectedAnalysts,
          [action.id]: !state.selectedAnalysts[action.id],
        },
      };
    case "moveAnalystCursor": {
      const n = ANALYST_IDS.length;
      return { ...state, analystCursor: (state.analystCursor + action.delta + n) % n };
    }
    case "stepRounds":
      return { ...state, [action.field]: clampRound(state[action.field] + action.delta) };
    case "setBackend":
      return { ...state, backendUrl: action.url };

    // --- P0 report reader ---
    case "selectSection": {
      const ids = sectionsForTab(state.activeTab, state.selectedAnalysts);
      const current = state.selectedSectionByTab[state.activeTab];
      const next = nextSectionId(ids, current, action.delta);
      if (next === undefined) return state;
      return {
        ...state,
        selectedSectionByTab: { ...state.selectedSectionByTab, [state.activeTab]: next },
      };
    }
    case "scrollReport": {
      const sectionId = state.selectedSectionByTab[state.activeTab];
      if (!sectionId) return state;
      const body = state.reports[sectionId] ?? "";
      const current = state.reportScrollBySection[sectionId] ?? 0;
      const { scroll } = reportViewport(body, current + action.delta);
      return {
        ...state,
        reportScrollBySection: { ...state.reportScrollBySection, [sectionId]: scroll },
      };
    }

    // --- navigation ---
    case "goPhase":
      return { ...state, phase: action.phase, errorMsg: "", selectOpen: null, selectIdx: 0 };

    // --- P2 library ---
    case "libraryLoading": {
      const { error: _e, ...lib } = state.library;
      return { ...state, library: { ...lib, loading: true } };
    }
    case "libraryLoaded": {
      const { error: _e, ...lib } = state.library;
      const reports = sortReports(action.reports);
      return {
        ...state,
        library: {
          ...lib,
          loading: false,
          reports,
          selectedIdx: 0,
          body: "",
          bodyLoading: reports.length > 0,
          scroll: 0,
        },
      };
    }
    case "libraryError":
      return {
        ...state,
        library: { ...state.library, loading: false, error: action.error, reports: [] },
      };
    case "librarySelect": {
      const n = state.library.reports.length;
      if (n === 0) return state;
      const selectedIdx = (state.library.selectedIdx + action.delta + n) % n;
      return {
        ...state,
        library: { ...state.library, selectedIdx, body: "", bodyLoading: true, scroll: 0 },
      };
    }
    case "libraryBodyLoading":
      return { ...state, library: { ...state.library, bodyLoading: true } };
    case "libraryBody":
      return {
        ...state,
        library: { ...state.library, body: action.body, bodyLoading: false, scroll: 0 },
      };
    case "libraryScroll": {
      const { scroll } = reportViewport(state.library.body, state.library.scroll + action.delta);
      return { ...state, library: { ...state.library, scroll } };
    }

    // --- P3 watchlist ---
    case "watchlistLoaded":
      return { ...state, watchlist: action.tickers, watchlistIdx: 0 };
    case "watchlistMove": {
      const n = state.watchlist.length;
      if (n === 0) return state;
      return { ...state, watchlistIdx: (state.watchlistIdx + action.delta + n) % n };
    }
    case "watchlistAddToInput": {
      const ticker = state.watchlist[state.watchlistIdx];
      if (!ticker) return state;
      return { ...state, ticker: appendTickerToInput(state.ticker, ticker) };
    }

    // --- P4 backtest ---
    case "backtestLoading": {
      const { error: _e, ...bt } = state.backtest;
      return { ...state, backtest: { ...bt, loading: true } };
    }
    case "backtestLoaded": {
      const { error: _e, ...bt } = state.backtest;
      return {
        ...state,
        backtest: {
          ...bt,
          loading: false,
          records: action.records,
          selectedIdx: 0,
          view: null,
        },
      };
    }
    case "backtestError":
      return {
        ...state,
        backtest: { ...state.backtest, loading: false, error: action.error, records: [] },
      };
    case "backtestSelect": {
      const n = state.backtest.records.length;
      if (n === 0) return state;
      const selectedIdx = (state.backtest.selectedIdx + action.delta + n) % n;
      return { ...state, backtest: { ...state.backtest, selectedIdx, view: null } };
    }
    case "backtestView":
      return { ...state, backtest: { ...state.backtest, view: action.view } };

    // --- P5 paper ---
    case "paperLoading": {
      const { error: _e, ...paper } = state.paper;
      return { ...state, paper: { ...paper, loading: true } };
    }
    case "paperLoaded":
      return {
        ...state,
        paper: {
          loading: false,
          ...(action.user !== undefined ? { user: action.user } : {}),
          account: action.account,
          positions: sortByTicker(action.positions),
          trades: action.trades,
        },
      };
    case "paperError":
      return { ...state, paper: { ...state.paper, loading: false, error: action.error } };

    // --- P6 error detail ---
    case "setErrorDetail":
      return { ...state, errorDetail: action.detail };
    case "toggleErrorDetail":
      return { ...state, showErrorDetail: !state.showErrorDetail };
  }
}

// ===========================================================================
// vllm model discovery
// ===========================================================================

const VLLM_URLS = ["http://127.0.0.1:8020/v1/models", "http://localhost:8000/v1/models"];

async function fetchVllmModels(dispatch: AppDispatch) {
  for (const url of VLLM_URLS) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) continue;
      const data = (await res.json()) as { data?: { id: string }[] };
      const models = (data.data ?? []).map((m) => m.id);
      if (models.length > 0) {
        dispatch({ type: "vllmModelsFetched", models });
        return;
      }
    } catch {
      /* try next */
    }
  }
  dispatch({ type: "vllmModelsFailed" });
}

// ===========================================================================
// Analysis runner
// ===========================================================================

async function runAnalysis(
  state: AppState,
  dispatch: AppDispatch,
  isCurrent: () => boolean,
  signal: AbortSignal,
) {
  const dispatchIfCurrent = (action: Action) => {
    if (isCurrent()) dispatch(action);
  };
  const ensureActive = () => {
    if (signal.aborted) throw new Error("分析已取消。");
    return isCurrent();
  };

  const tickers = state.tickers.length > 0 ? state.tickers : parseTickers(state.ticker);
  dispatchIfCurrent({ type: "appendLog", msg: `开始分析 ${tickers.join(", ")}` });
  try {
    const [{ HumanMessage }] = await Promise.all([import("@langchain/core/messages")]);
    const { BridgeApi, BridgeClient, pickBridgeTools } = await import("../bridge/index.js");
    const { buildFullGraph } = await import("../graph/full_graph.js");
    const { ANALYST_TOOLS } = await import("../cli/commands/shared_tools.js");
    const { createLlmFromConfig } = await import("../llm/factory.js");

    dispatchIfCurrent({ type: "appendLog", msg: "── 连接 Bridge…" });
    const client = new BridgeClient();
    await client.start();
    try {
      if (!ensureActive()) return;
      const api = new BridgeApi(client);
      const config = await api.configGet();
      if (!ensureActive()) return;
      const llmOpts: LlmOptions = { tier: "deep" };
      if (state.provider) llmOpts.provider = state.provider;
      if (state.model) llmOpts.model = state.model;
      dispatchIfCurrent({
        type: "appendLog",
        msg: `── LLM: ${llmOpts.provider ?? config.llm_provider}/${llmOpts.model ?? "default"}`,
      });

      const llmHandle = createLlmFromConfig(config, llmOpts);

      // Resolve each analyst's tool set (deduped) for the full pipeline.
      const uniqueToolNames = Array.from(
        new Set<string>([
          ...ANALYST_TOOLS.marketFlow,
          ...ANALYST_TOOLS.macroRegime,
          ...ANALYST_TOOLS.mesoCommodity,
          ...ANALYST_TOOLS.catalystSentiment,
          ...ANALYST_TOOLS.holdingsIndustry,
          ...ANALYST_TOOLS.topHoldings,
        ]),
      );
      const allTools = await pickBridgeTools(api, uniqueToolNames);
      if (!ensureActive()) return;
      const byName = new Map(allTools.map((t) => [t.name, t] as const));
      const pick = (names: ReadonlyArray<string>) =>
        names.map((n) => byName.get(n)).filter((t): t is NonNullable<typeof t> => t !== undefined);
      dispatchIfCurrent({ type: "appendLog", msg: `── 已加载 ${allTools.length} 个数据工具` });
      dispatchIfCurrent({ type: "setStats", stats: { tool_calls: allTools.length } });

      const charLimit = Number(config.report_context_char_limit);
      const promptContext = {
        language: String(config.output_language ?? "Chinese"),
        ...(Number.isFinite(charLimit) && charLimit > 0
          ? { reportContextCharLimit: charLimit }
          : {}),
      };

      const graph = buildFullGraph({
        llm: llmHandle.llm,
        tools: {
          marketFlow: pick(ANALYST_TOOLS.marketFlow),
          macroRegime: pick(ANALYST_TOOLS.macroRegime),
          mesoCommodity: pick(ANALYST_TOOLS.mesoCommodity),
          catalystSentiment: pick(ANALYST_TOOLS.catalystSentiment),
          holdingsIndustry: pick(ANALYST_TOOLS.holdingsIndustry),
          topHoldings: pick(ANALYST_TOOLS.topHoldings),
          bullBear: [],
          riskDebate: [],
        },
        promptContext,
        maxDebateRounds: state.debateRounds,
        maxRiskRounds: state.riskRounds,
        selectedAnalysts: ANALYST_IDS.filter((id) => state.selectedAnalysts[id] !== false),
        persistMemory: async (payload) => {
          const res = await api.memoryAppendAnalysis(
            payload as {
              state: Record<string, unknown>;
              selected_analysts?: readonly string[] | null;
            },
          );
          return res.entry;
        },
      });

      let lastDecision = "";
      for (const [index, ticker] of tickers.entries()) {
        if (!ensureActive()) return;
        dispatchIfCurrent({ type: "queueTickerStarted", index });
        dispatchIfCurrent({ type: "appendLog", msg: `开始分析 ${ticker}` });

        // Load the ETF basic-info card via the same bridge connection.
        // NOTE: get_etf_price_data's parameter is `symbol`, not `ticker`.
        try {
          const detailResult = await api.toolsCall("get_etf_price_data", {
            symbol: ticker,
            start_date: dateDaysBefore(state.date, 365),
            end_date: state.date,
          });
          const rows = extractPriceRows(detailResult.text);
          const last = rows[rows.length - 1];
          const prev = rows[rows.length - 2];
          if (last) {
            const close = last.close;
            const pctChg = last.pctChg;
            const high = last.high;
            const low = last.low;
            const volume = last.volume;
            const prevVolume = prev?.volume;
            const volumeChangePct =
              volume !== undefined && prevVolume !== undefined && prevVolume !== 0
                ? ((volume - prevVolume) / prevVolume) * 100
                : undefined;
            dispatchIfCurrent({
              type: "etfDetailLoaded",
              ...(last.name ? { name: last.name } : { name: ticker }),
              ...(close !== undefined ? { close } : {}),
              ...(pctChg !== undefined ? { pctChg } : {}),
              ...(high !== undefined ? { high } : {}),
              ...(low !== undefined ? { low } : {}),
              ...(volume !== undefined ? { volume } : {}),
              ...(volumeChangePct !== undefined ? { volumeChangePct } : {}),
              history: rows.map((row) => row.close).filter((v): v is number => v !== undefined),
            });
          } else {
            dispatchIfCurrent({ type: "etfDetailLoaded", name: ticker });
          }
        } catch (e) {
          dispatchIfCurrent({ type: "etfDetailError", error: (e as Error).message });
        }
        if (!ensureActive()) return;

        dispatchIfCurrent({
          type: "appendLog",
          msg: "── 启动完整流水线：分析师 → 辩论 → 交易 → 风控 → 决策",
        });

        // Stream the graph so the dashboard updates per node instead of waiting
        // for the whole pipeline. Each chunk is { nodeName: stateUpdate }.
        const stream = await graph.stream(
          {
            messages: [new HumanMessage(ticker)],
            asset_of_interest: ticker,
            trade_date: state.date,
          },
          { recursionLimit: 100, signal } as { recursionLimit: number; signal: AbortSignal },
        );

        let finalState: Record<string, unknown> = {};
        try {
          for await (const chunk of stream) {
            if (!ensureActive()) return;
            for (const [node, update] of Object.entries(chunk as Record<string, unknown>)) {
              if (!update || typeof update !== "object") continue;
              finalState = { ...finalState, ...(update as Record<string, unknown>) };
              const info = NODE_INFO[node];
              if (!info) continue; // tool-loop node (e.g. *_tools) — no UI section
              dispatchIfCurrent({ type: "sectionStarted", sectionId: info.section });
              const body = (update as Record<string, unknown>)[info.key];
              const hasBody = typeof body === "string" && body.trim().length > 0;
              // Analyst nodes re-enter via their ToolNode while fetching data; those
              // intermediate passes only carry { messages } and no report body, so
              // skip them — we only advance the UI once real output is produced.
              if (!hasBody) continue;
              dispatchIfCurrent({
                type: "sectionReport",
                sectionId: info.section,
                nodeLabel: tickers.length > 1 ? `${ticker} · ${info.label}` : info.label,
                body: body as string,
              });
              dispatchIfCurrent({ type: "setStats", stats: { llm_calls: 1 } });
              if (info.completes) {
                dispatchIfCurrent({ type: "sectionDone", sectionId: info.section });
              }
              dispatchIfCurrent({ type: "appendLog", msg: `✓ ${ticker} · ${info.label}` });
              // Surface the trader rating as soon as the trader node lands.
              if (node === "trader") {
                const traderSignal = (update as Record<string, unknown>).trader_backtest_signal as
                  | Record<string, unknown>
                  | undefined;
                const rating = traderSignal?.rating;
                if (typeof rating === "string" && rating) {
                  dispatchIfCurrent({ type: "setRating", rating });
                }
              }
            }
          }
          const summary = buildExecutionSummary(finalState);
          if (summary) dispatchIfCurrent({ type: "setExecutionSummary", summary });
          const decision =
            (finalState.final_allocation_decision as string) ||
            (finalState.trader_allocation_plan as string) ||
            "(无最终决策)";
          lastDecision = decision;
          dispatchIfCurrent({ type: "queueTickerDone", index });
        } catch (e) {
          const msg = (e as Error).message;
          dispatchIfCurrent({ type: "queueTickerFailed", index, msg });
          throw e;
        }
      }

      dispatchIfCurrent({ type: "appendLog", msg: "✓ 流水线完成" });
      dispatchIfCurrent({ type: "analysisDone", result: lastDecision || "(无最终决策)" });
    } finally {
      await client.close();
    }
  } catch (err) {
    const error = err as Error;
    const msg = error.message;
    if (signal.aborted || msg === "分析已取消。") {
      dispatchIfCurrent({ type: "appendLog", msg: "✗ 分析已取消" });
      dispatchIfCurrent({ type: "queueCancelled" });
      return;
    }
    dispatchIfCurrent({ type: "appendLog", msg: `✗ 错误: ${msg.slice(0, 120)}` });
    // P6: preserve a structured detail object for the error overlay.
    dispatchIfCurrent({
      type: "setErrorDetail",
      detail: {
        message: msg,
        ...(state.tickers[0] ? { ticker: state.tickers[0] } : {}),
        ...(error.stack ? { stack: error.stack } : {}),
        timestamp: new Date().toISOString(),
      },
    });
    dispatchIfCurrent({
      type: "analysisError",
      msg:
        msg.includes("ECONNREFUSED") || msg.includes("connect")
          ? "Bridge 未运行。请先启动 Python bridge。"
          : msg,
    });
  }
}

// ===========================================================================
// Local artifact discovery (P2 report library, P3 watchlist, P4 backtest)
// ===========================================================================
//
// Mirrors cli/tui/services.py ReportRepository / BacktestViewer, reading the
// same on-disk conventions under results_dir. We do not invent a new TS-only
// persistence format; we read what the Python pipeline already writes.

const SKIP_REPORT_DIRS = new Set(["backtest", "memory"]);

function resultsDir(): string {
  const env = process.env.ETFAGENTS_RESULTS_DIR ?? process.env.TRADINGAGENTS_RESULTS_DIR;
  if (env) return env;
  const home = process.env.HOME ?? process.env.USERPROFILE ?? ".";
  return `${home}/.etfagents/logs`;
}

async function loadLibrary(dispatch: AppDispatch): Promise<void> {
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

async function loadLibraryBody(record: ReportMeta, dispatch: AppDispatch): Promise<void> {
  dispatch({ type: "libraryBodyLoading" });
  try {
    const { readFile } = await import("node:fs/promises");
    const body = await readFile(`${record.path}/complete_report.md`, "utf-8");
    dispatch({ type: "libraryBody", body });
  } catch (e) {
    dispatch({ type: "libraryBody", body: `读取报告失败: ${(e as Error).message}` });
  }
}

/** P3: derive a read-only watchlist from the most recent distinct report tickers. */
async function loadWatchlist(dispatch: AppDispatch): Promise<void> {
  try {
    const { readdir, stat } = await import("node:fs/promises");
    const root = resultsDir();
    let tickerDirs: string[] = [];
    try {
      tickerDirs = await readdir(root);
    } catch {
      dispatch({ type: "watchlistLoaded", tickers: [] });
      return;
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
    dispatch({ type: "watchlistLoaded", tickers: tickers.slice(0, 12) });
  } catch {
    dispatch({ type: "watchlistLoaded", tickers: [] });
  }
}

async function walkForFile(root: string, target: string): Promise<string[]> {
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

async function loadBacktests(dispatch: AppDispatch): Promise<void> {
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

async function loadBacktestView(record: BacktestMeta, dispatch: AppDispatch): Promise<void> {
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

async function loadPaper(dispatch: AppDispatch): Promise<void> {
  dispatch({ type: "paperLoading" });
  const { BridgeApi, BridgeClient } = await import("../bridge/index.js");
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

// ===========================================================================
// App
// ===========================================================================

function App() {
  const [state, dispatch] = useReducer(reducer, undefined, initState);

  const stateRef = useRef(state);
  stateRef.current = state;
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;
  const runSeqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  // vllm discovery
  const vllmFetchedRef = useRef(false);
  useEffect(() => {
    if (state.provider.toLowerCase() === "vllm" && state.vllmModels === null) {
      if (vllmFetchedRef.current) return;
      vllmFetchedRef.current = true;
      fetchVllmModels(dispatch);
    }
    if (state.provider.toLowerCase() !== "vllm") vllmFetchedRef.current = false;
  }, [state.provider, state.vllmModels]);

  // Elapsed timer
  const [elapsed, setElapsed] = useState(0);
  const startTimeRef = useRef<number | null>(null);
  useEffect(() => {
    if (state.phase === "dashboard" && state.status === "running") {
      startTimeRef.current = Date.now();
      const id = setInterval(() => {
        if (startTimeRef.current)
          setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
      }, 1000);
      return () => clearInterval(id);
    }
    if (state.status === "done" || state.status === "error") {
      // Freeze the timer — keep the last elapsed value visible.
      if (startTimeRef.current !== null) {
        setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
        startTimeRef.current = null;
      }
      return undefined;
    }
    setElapsed(0);
    startTimeRef.current = null;
    return undefined;
  }, [state.phase, state.status]);

  // P3: load the read-only watchlist once at startup.
  const watchlistLoadedRef = useRef(false);
  useEffect(() => {
    if (watchlistLoadedRef.current) return;
    watchlistLoadedRef.current = true;
    loadWatchlist(dispatch);
  }, []);

  // P2: discover reports when entering the library.
  useEffect(() => {
    if (state.phase === "library") loadLibrary(dispatch);
  }, [state.phase]);

  // P2: load the selected report body when the selection changes.
  const libSel = state.library.reports[state.library.selectedIdx];
  useEffect(() => {
    if (state.phase === "library" && libSel) loadLibraryBody(libSel, dispatch);
  }, [state.phase, libSel]);

  // P4: discover backtest artifacts when entering the screen.
  useEffect(() => {
    if (state.phase === "backtest") loadBacktests(dispatch);
  }, [state.phase]);

  // P4: load the selected backtest view when the selection changes.
  const btSel = state.backtest.records[state.backtest.selectedIdx];
  useEffect(() => {
    if (state.phase === "backtest" && btSel) loadBacktestView(btSel, dispatch);
  }, [state.phase, btSel]);

  // P5: load paper-trading snapshot when entering the screen.
  useEffect(() => {
    if (state.phase === "paper") loadPaper(dispatch);
  }, [state.phase]);

  useInput((input, key) => {
    const s = stateRef.current;
    const d = dispatchRef.current;

    // P6: an open error-detail overlay swallows the next key (close on any).
    if (s.showErrorDetail) {
      d({ type: "toggleErrorDetail" });
      return;
    }

    if (key.escape) {
      if (s.phase === "config") {
        d({ type: "backToTicker" });
        return;
      }
      if (s.phase === "dashboard") {
        abortRef.current?.abort();
        runSeqRef.current += 1;
        d({ type: "backToTicker" });
        return;
      }
      if (s.phase === "library" || s.phase === "backtest" || s.phase === "paper") {
        d({ type: "goPhase", phase: "ticker" });
        return;
      }
      process.exit(0);
    }

    if (s.phase === "ticker") {
      // Top-level screen navigation (Ctrl+L/B/P avoids clashing with ticker chars).
      if (key.ctrl && input === "l") {
        d({ type: "goPhase", phase: "library" });
        return;
      }
      if (key.ctrl && input === "b") {
        d({ type: "goPhase", phase: "backtest" });
        return;
      }
      if (key.ctrl && input === "p") {
        d({ type: "goPhase", phase: "paper" });
        return;
      }
      // Watchlist: arrows select, Tab appends the selected ticker to the input.
      if (s.watchlist.length > 0) {
        if (key.upArrow) {
          d({ type: "watchlistMove", delta: -1 });
          return;
        }
        if (key.downArrow) {
          d({ type: "watchlistMove", delta: 1 });
          return;
        }
        if (key.tab) {
          d({ type: "watchlistAddToInput" });
          return;
        }
      }
      if (key.return && parseTickers(s.ticker).length > 0) {
        d({ type: "openConfig" });
        return;
      }
      if (key.backspace || key.delete) {
        d({ type: "deleteTicker" });
        return;
      }
      if (input.length === 1 && /[a-zA-Z0-9._,\-，;；\s]/.test(input))
        d({ type: "appendTicker", char: input });
      return;
    }

    if (s.phase === "config") {
      if (s.selectOpen !== null) {
        if (key.upArrow) {
          d({ type: "selectUp" });
          return;
        }
        if (key.downArrow) {
          d({ type: "selectDown" });
          return;
        }
        if (key.return) {
          d({ type: "selectPick" });
          return;
        }
        if (key.tab) {
          d({ type: "setFocus", focus: nextFocus(s.focus) });
          return;
        }
        d({ type: "closeSelect" });
        return;
      }
      if (key.tab) {
        d({ type: "setFocus", focus: nextFocus(s.focus) });
        return;
      }
      // Analyst toggle row: arrows move cursor, space toggles current analyst.
      if (s.focus === "analysts") {
        if (key.leftArrow) {
          d({ type: "moveAnalystCursor", delta: -1 });
          return;
        }
        if (key.rightArrow) {
          d({ type: "moveAnalystCursor", delta: 1 });
          return;
        }
        if (input === " ") {
          const id = ANALYST_IDS[s.analystCursor];
          if (id) d({ type: "toggleAnalyst", id });
          return;
        }
      }
      // Round steppers: left/right adjust the count.
      if (s.focus === "debateRounds" || s.focus === "riskRounds") {
        if (key.leftArrow) {
          d({ type: "stepRounds", field: s.focus, delta: -1 });
          return;
        }
        if (key.rightArrow) {
          d({ type: "stepRounds", field: s.focus, delta: 1 });
          return;
        }
      }
      if (key.return) {
        if (isSelectField(s, s.focus)) {
          d({ type: "openSelect" });
        } else {
          const runId = runSeqRef.current + 1;
          runSeqRef.current = runId;
          abortRef.current?.abort();
          const controller = new AbortController();
          abortRef.current = controller;
          d({ type: "startAnalysis" });
          runAnalysis(s, d, () => runSeqRef.current === runId, controller.signal);
        }
        return;
      }
      if (key.downArrow && isSelectField(s, s.focus)) {
        d({ type: "openSelect" });
        return;
      }
      if (key.backspace || key.delete) {
        if (s.focus === "date" || s.focus === "model") d({ type: "deleteChar" });
        return;
      }
      // Free text entry only for the date and (option-less) model fields.
      if (
        (s.focus === "date" || s.focus === "model") &&
        input.length === 1 &&
        /[a-zA-Z0-9._\-\u4e00-\u9fff/:]/.test(input)
      )
        d({ type: "appendChar", char: input });
      return;
    }

    if (s.phase === "dashboard") {
      // P6: open error detail when a failure is recorded.
      if (input === "e" && s.errorDetail) {
        d({ type: "toggleErrorDetail" });
        return;
      }
      // Cycle team tabs with Tab / left-right arrows.
      if (key.tab || key.rightArrow) {
        const i = TEAM_TABS.findIndex((t) => t.key === s.activeTab);
        const next = TEAM_TABS[(i + 1) % TEAM_TABS.length];
        if (next) d({ type: "setTab", tab: next.key });
        return;
      }
      if (key.leftArrow) {
        const i = TEAM_TABS.findIndex((t) => t.key === s.activeTab);
        const prev = TEAM_TABS[(i - 1 + TEAM_TABS.length) % TEAM_TABS.length];
        if (prev) d({ type: "setTab", tab: prev.key });
        return;
      }
      // P0: up/down select a section, PageUp/PageDown scroll its body.
      if (key.upArrow) {
        d({ type: "selectSection", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "selectSection", delta: 1 });
        return;
      }
      if (key.pageUp) {
        d({ type: "scrollReport", delta: -REPORT_VIEWPORT });
        return;
      }
      if (key.pageDown) {
        d({ type: "scrollReport", delta: REPORT_VIEWPORT });
        return;
      }
      if (key.return && (s.status === "done" || s.status === "error")) {
        abortRef.current?.abort();
        runSeqRef.current += 1;
        d({ type: "backToTicker" });
      }
      return;
    }

    if (s.phase === "library") {
      if (input === "r") {
        loadLibrary(d);
        return;
      }
      if (key.upArrow) {
        d({ type: "librarySelect", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "librarySelect", delta: 1 });
        return;
      }
      if (key.pageUp) {
        d({ type: "libraryScroll", delta: -REPORT_VIEWPORT });
        return;
      }
      if (key.pageDown) {
        d({ type: "libraryScroll", delta: REPORT_VIEWPORT });
        return;
      }
      return;
    }

    if (s.phase === "backtest") {
      if (input === "r") {
        loadBacktests(d);
        return;
      }
      if (key.upArrow) {
        d({ type: "backtestSelect", delta: -1 });
        return;
      }
      if (key.downArrow) {
        d({ type: "backtestSelect", delta: 1 });
        return;
      }
      return;
    }

    if (s.phase === "paper") {
      if (input === "r") loadPaper(d);
      return;
    }
  });

  return (
    <Box flexDirection="column" padding={1} flexGrow={1}>
      {/* Banner */}
      <Box flexDirection="column" alignItems="center" marginBottom={1}>
        {BANNER.map((line) => (
          <Text key={line} bold color="cyan">
            {line}
          </Text>
        ))}
      </Box>

      {/* Main content */}
      <Box flexDirection="row" flexGrow={1} borderStyle="single">
        {state.phase === "ticker" && <TickerScreen state={state} />}
        {state.phase === "config" && <ConfigModal state={state} />}
        {state.phase === "dashboard" && <Dashboard state={state} elapsed={elapsed} />}
        {state.phase === "library" && <ReportLibrary state={state} />}
        {state.phase === "backtest" && <BacktestScreen state={state} />}
        {state.phase === "paper" && <PaperScreen state={state} />}
      </Box>

      {/* P6: error detail overlay */}
      {state.showErrorDetail && state.errorDetail && (
        <ErrorDetailOverlay detail={state.errorDetail} />
      )}
    </Box>
  );
}

// ===========================================================================
// Ticker screen
// ===========================================================================

function TickerScreen({ state }: { state: AppState }) {
  const tickers = parseTickers(state.ticker);
  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Text bold>创建研究任务</Text>
      <Box marginY={1}>
        <Text dimColor>ETF 代码 </Text>
        <Text color="yellow">{state.ticker || "▌"}</Text>
      </Box>
      <Text dimColor>
        支持多个代码，用逗号或空格分隔
        {tickers.length > 0 ? ` · 已识别 ${tickers.length} 个` : ""}
      </Text>
      <Text dimColor>输入代码后按 Enter 配置分析参数</Text>

      {/* P3: watchlist cards derived from recent report history. */}
      {state.watchlist.length > 0 && (
        <Box flexDirection="column" marginTop={1} borderStyle="round" paddingX={2}>
          <Text bold>⭐ 自选 / 最近研究</Text>
          <Box marginTop={1} flexWrap="wrap">
            {state.watchlist.map((ticker, i) => (
              <Box key={ticker} marginRight={1}>
                <Text
                  {...(i === state.watchlistIdx ? { color: "cyan" as const, bold: true } : {})}
                  dimColor={i !== state.watchlistIdx}
                >
                  {i === state.watchlistIdx ? "▶ " : "  "}
                  {ticker.split(".")[0] ?? ticker}
                </Text>
              </Box>
            ))}
          </Box>
          <Text dimColor>↑↓ 选择 · Tab 加入输入</Text>
        </Box>
      )}
      <Box marginTop={1}>
        <Text dimColor>Ctrl+L 报告库 · Ctrl+B 回测 · Ctrl+P 模拟盘 · Esc 退出</Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// Config modal
// ===========================================================================

function ConfigModal({ state }: { state: AppState }) {
  const showModelSelect = modelHasOptions(state);
  const vllmPending = state.provider.toLowerCase() === "vllm" && state.vllmModels === null;
  const focus = (f: ConfigField) => state.focus === f;

  return (
    <Box flexDirection="column" flexGrow={1} justifyContent="center" alignItems="center">
      <Box flexDirection="column" borderStyle="round" paddingX={4} paddingY={1}>
        <Box marginBottom={1}>
          <Text bold>分析配置</Text>
          <Text dimColor> — {state.ticker}</Text>
        </Box>
        <FieldRow label="日期" value={state.date} focused={focus("date")} hint="YYYY-MM-DD" />
        <SelectFieldRow
          label="提供商"
          value={state.provider}
          focused={focus("provider")}
          open={state.selectOpen === "provider"}
          options={PROVIDERS}
          selectedIdx={state.selectIdx}
          hint="选择 LLM 提供商"
        />
        {showModelSelect ? (
          <SelectFieldRow
            label="模型"
            value={state.model}
            focused={focus("model")}
            open={state.selectOpen === "model"}
            options={
              state.provider.toLowerCase() === "vllm"
                ? (state.vllmModels ?? [])
                : (MODELS_BY_PROVIDER[state.provider.toLowerCase()] ?? [])
            }
            selectedIdx={state.selectIdx}
            hint="选择模型"
          />
        ) : vllmPending ? (
          <Box>
            <Text dimColor>{"模型".padEnd(6)}</Text>
            <Text color="yellow">正在获取 vllm 模型列表…</Text>
          </Box>
        ) : (
          <FieldRow
            label="模型"
            value={state.model}
            focused={focus("model")}
            hint={state.provider ? "输入模型名称" : "请先选择提供商"}
          />
        )}
        <SelectFieldRow
          label="研究深度"
          value={DEPTH_LABELS[state.depth]}
          focused={focus("depth")}
          open={state.selectOpen === "depth"}
          options={DEPTH_OPTIONS.map((opt) => DEPTH_LABELS[opt])}
          selectedIdx={state.selectIdx}
          hint="选择研究深度"
        />
        <AnalystToggleRow state={state} focused={focus("analysts")} />
        <RoundStepperRow
          label="辩论轮数"
          value={state.debateRounds}
          focused={focus("debateRounds")}
        />
        <RoundStepperRow label="风险轮数" value={state.riskRounds} focused={focus("riskRounds")} />
        <Box>
          <Text dimColor>{"后端".padEnd(8)}</Text>
          <Text dimColor>{state.backendUrl || "(默认 / 由 bridge 配置)"}</Text>
        </Box>

        <Box marginTop={1} justifyContent="center">
          <Text color="green">Tab 切换字段 · Enter 开始分析</Text>
        </Box>
      </Box>
    </Box>
  );
}

function AnalystToggleRow({ state, focused }: { state: AppState; focused: boolean }) {
  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>{"分析师".padEnd(6)}</Text>
        {focused ? (
          <Text color="yellow" dimColor>
            (←→ 移动 · 空格 开关)
          </Text>
        ) : (
          <Text dimColor>
            已选 {ANALYST_IDS.filter((id) => state.selectedAnalysts[id]).length}/
            {ANALYST_IDS.length}
          </Text>
        )}
      </Box>
      {focused && (
        <Box flexWrap="wrap" marginLeft={2}>
          {ANALYST_IDS.map((id, i) => {
            const on = state.selectedAnalysts[id] !== false;
            const title = DEFAULT_SECTIONS.find((s) => s.id === id)?.title ?? id;
            const isCursor = i === state.analystCursor;
            return (
              <Box key={id} marginRight={1}>
                <Text
                  {...(isCursor ? { color: "cyan" as const, bold: true } : {})}
                  dimColor={!isCursor}
                >
                  {on ? "☑" : "☐"} {title}
                </Text>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

function RoundStepperRow({
  label,
  value,
  focused,
}: {
  label: string;
  value: number;
  focused: boolean;
}) {
  return (
    <Box>
      <Text dimColor>{label.padEnd(8)}</Text>
      {focused ? (
        <Text color="yellow">
          ◀ {value} ▶ <Text dimColor>(←→ 调整)</Text>
        </Text>
      ) : (
        <Text>{value}</Text>
      )}
    </Box>
  );
}

function FieldRow({
  label,
  value,
  focused,
  hint,
}: {
  label: string;
  value: string;
  focused: boolean;
  hint: string;
}) {
  return (
    <Box>
      <Text dimColor>{label.padEnd(8)}</Text>
      {focused ? <Text color="yellow">{value || "▌"}</Text> : <Text>{value || hint}</Text>}
    </Box>
  );
}

function SelectFieldRow({
  label,
  value,
  focused,
  open,
  options,
  selectedIdx,
  hint,
}: {
  label: string;
  value: string;
  focused: boolean;
  open: boolean;
  options: readonly string[];
  selectedIdx: number;
  hint: string;
}) {
  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>{label.padEnd(8)}</Text>
        {focused ? (
          <Text color="yellow">
            {value || (open ? "▾" : "▸")}{" "}
            <Text dimColor>{open ? "(↑↓ 选择, Enter 确认)" : "(Enter 展开)"}</Text>
          </Text>
        ) : (
          <Text>{value || hint}</Text>
        )}
      </Box>
      {open && (
        <Box flexDirection="column" marginLeft={2}>
          {options.map((opt, i) => {
            const color = i === selectedIdx ? "cyan" : undefined;
            return (
              <Text key={opt} {...(color ? { color } : {})}>
                {i === selectedIdx ? "▶ " : "  "}
                {opt === value ? (
                  <Text bold color="green">
                    {opt}
                  </Text>
                ) : (
                  <Text>{opt}</Text>
                )}
              </Text>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

// ===========================================================================
// Dashboard (Python-aligned layout)
// ===========================================================================

function Dashboard({ state, elapsed }: { state: AppState; elapsed: number }) {
  const groups = sectionGroups(state.selectedAnalysts);
  const done = state.sectionDone;

  function countDone(key: string): number {
    return (groups[key] ?? []).filter((s) => done.has(s.id)).length;
  }
  function total(key: string): number {
    return (groups[key] ?? []).length;
  }

  const el = fmtElapsed(elapsed);

  // Totals reflect only the sections active for the current analyst selection.
  const activeSectionIds = Object.values(groups).flat();
  const agentsTotal = activeSectionIds.length;
  const agentsDone = activeSectionIds.filter((s) => done.has(s.id)).length;
  const reportsTotal = agentsTotal;
  const reportsDone = agentsDone;

  return (
    <Box flexDirection="column" flexGrow={1}>
      {/* Main two-column layout */}
      <Box flexDirection="row" flexGrow={1}>
        {/* Left pane — 22ch */}
        <Box flexDirection="column" width={22} borderStyle="single" paddingX={1}>
          {/* ETF card */}
          <Box flexDirection="column" marginBottom={1}>
            <Text bold>📊 基本信息</Text>
            {state.etfDetail?.loading ? (
              <Text dimColor>加载中…</Text>
            ) : state.etfDetail?.error ? (
              <Text color="red">{state.etfDetail.error.slice(0, 18)}</Text>
            ) : (
              <>
                <Text>{state.etfDetail?.name || state.ticker}</Text>
                {state.etfDetail?.close !== undefined && (
                  <Text>
                    现价: <Text bold>{state.etfDetail.close.toFixed(3)}</Text>
                    {state.etfDetail.pctChg !== undefined && (
                      <Text
                        {...(state.etfDetail.pctChg > 0
                          ? { color: "red" as const }
                          : state.etfDetail.pctChg < 0
                            ? { color: "green" as const }
                            : {})}
                      >
                        {" "}
                        {state.etfDetail.pctChg > 0 ? "+" : ""}
                        {state.etfDetail.pctChg.toFixed(2)}%
                      </Text>
                    )}
                  </Text>
                )}
                {state.etfDetail?.history && state.etfDetail.history.length > 1 && (
                  <Text color="cyan">{sparkline(state.etfDetail.history)}</Text>
                )}
                {(state.etfDetail?.high !== undefined || state.etfDetail?.low !== undefined) && (
                  <Text dimColor>
                    H/L: {state.etfDetail.high?.toFixed(3) ?? "—"}/
                    {state.etfDetail.low?.toFixed(3) ?? "—"}
                  </Text>
                )}
                {state.etfDetail?.volume !== undefined && (
                  <Text dimColor>
                    量: {Math.round(state.etfDetail.volume).toLocaleString()}
                    {state.etfDetail.volumeChangePct !== undefined
                      ? ` (${state.etfDetail.volumeChangePct > 0 ? "+" : ""}${state.etfDetail.volumeChangePct.toFixed(1)}%)`
                      : ""}
                  </Text>
                )}
                <Text dimColor>{state.date}</Text>
              </>
            )}
            {state.status === "running" ? (
              <Text color="yellow">分析中…</Text>
            ) : state.status === "done" ? (
              <Text color="green">分析完成</Text>
            ) : state.status === "error" ? (
              <Text color="red">分析失败</Text>
            ) : (
              <Text dimColor>等待中</Text>
            )}
          </Box>

          {/* Metadata */}
          <Box flexDirection="column" marginBottom={1}>
            <Text bold>📋 分析元数据</Text>
            <Text dimColor>日期: {state.date}</Text>
            <Text dimColor>提供商: {state.provider || "—"}</Text>
            <Text dimColor>模型: {state.model || "—"}</Text>
            <Text dimColor>标的: {state.tickers.length || parseTickers(state.ticker).length}</Text>
          </Box>

          {/* Cancel button */}
          <Box marginBottom={1}>
            {state.status === "running" ? (
              <Text dimColor>⏹ 取消分析</Text>
            ) : (
              <Text dimColor>⏹ 分析已结束</Text>
            )}
          </Box>

          {/* Queue — shows tickers being analyzed */}
          <Box flexDirection="column" flexGrow={1}>
            <Text bold>🧠 研究队列</Text>
            <Text dimColor>
              状态:{" "}
              {state.status === "error"
                ? "🔴"
                : state.status === "done"
                  ? "🟢"
                  : state.status === "running"
                    ? "🟡"
                    : "⚪"}{" "}
              {state.queue.filter((item) => item.status === "done").length}/
              {state.queue.length || 1}
              {state.status === "error"
                ? " 有失败"
                : state.status === "done"
                  ? " 已完成"
                  : state.status === "running"
                    ? " 分析中"
                    : " 等待中"}
            </Text>
            <Box flexDirection="column" marginTop={1}>
              {state.queue.length > 0 ? (
                state.queue.slice(0, 8).map((item, index) => (
                  <Text key={item.ticker}>
                    <Text
                      {...(() => {
                        const color =
                          item.status === "done"
                            ? "green"
                            : item.status === "failed" || item.status === "cancelled"
                              ? "red"
                              : item.status === "running"
                                ? "yellow"
                                : undefined;
                        return color ? { color: color as "green" | "red" | "yellow" } : {};
                      })()}
                    >
                      {index === state.currentTickerIdx ? "> " : "  "}
                      {item.ticker.split(".")[0] ?? item.ticker}
                    </Text>
                    <Text dimColor> ({queueStatusLabel(item.status)})</Text>
                  </Text>
                ))
              ) : (
                <Text dimColor>等待分析启动…</Text>
              )}
            </Box>
          </Box>
        </Box>

        {/* Right pane */}
        <Box flexDirection="column" flexGrow={1} paddingLeft={1}>
          {/* Team tabs (top) */}
          <Box marginBottom={1}>
            {TEAM_TABS.map((tab) => (
              <Box key={tab.key} marginRight={1}>
                <TabButton
                  label={tab.label}
                  done={countDone(tab.key)}
                  total={total(tab.key)}
                  active={state.activeTab === tab.key}
                />
              </Box>
            ))}
          </Box>

          {/* Tabbed section view + progress (bottom) */}
          <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1}>
            <TabContent state={state} groups={groups} />
          </Box>
        </Box>
      </Box>

      {/* Stats bar */}
      <Box marginTop={1} justifyContent="space-between">
        <Text color="cyan">
          ◎ Agents {agentsDone}/{agentsTotal}{" "}
          {state.status === "running"
            ? "· 分析中"
            : state.status === "done"
              ? "· 完成"
              : state.status === "error"
                ? "· 错误"
                : "· 等待"}
        </Text>
        <Text dimColor>
          {state.activeSection
            ? `当前 ${DEFAULT_SECTIONS.find((s) => s.id === state.activeSection)?.title ?? state.activeSection}`
            : state.rating
              ? `评级 ${state.rating}`
              : "完整流水线"}
        </Text>
        <Text color="green">
          Nodes {state.stats.llm_calls} · Toolset {state.stats.tool_calls} · Reports {reportsDone}/
          {reportsTotal}
        </Text>
        <Text dimColor>{el} ←→ 团队 · ↑↓ 章节 · PgUp/PgDn 滚动 · e 错误 · Enter 返回</Text>
      </Box>
    </Box>
  );
}

/**
 * Right-pane body. Shows the progress log for the analysts tab while running,
 * and the per-section report content for the selected team tab. Falls back to
 * the progress log until a section has produced output.
 */
function TabContent({ state, groups }: { state: AppState; groups: Record<string, SectionDef[]> }) {
  const sections = groups[state.activeTab] ?? [];
  const tabMeta = TEAM_TABS.find((t) => t.key === state.activeTab);

  // P0: the selected section for this tab (default to the first section).
  const selectedId = state.selectedSectionByTab[state.activeTab] ?? sections[0]?.id;
  const selected = sections.find((s) => s.id === selectedId);
  const selectedStatus = selectedId ? (state.sectionStatus[selectedId] ?? "pending") : "pending";
  const selectedBody = selectedId ? (state.reports[selectedId] ?? "") : "";
  const scroll = selectedId ? (state.reportScrollBySection[selectedId] ?? 0) : 0;
  const view = reportViewport(selectedBody, scroll);

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Text bold>{tabMeta?.label ?? "整体进度"}</Text>

      {/* P0: section checklist with the selected section highlighted. */}
      <Box flexDirection="column" marginTop={1}>
        {sections.map((s) => {
          const status = state.sectionStatus[s.id] ?? "pending";
          const isDone = status === "done";
          const hasBody = Boolean(state.reports[s.id]?.trim());
          const isSelected = s.id === selectedId;
          const mark =
            status === "done"
              ? "✓"
              : status === "failed"
                ? "×"
                : status === "running"
                  ? "◐"
                  : state.status === "running"
                    ? "○"
                    : "·";
          const colorProps = isSelected
            ? { color: "cyan" as const }
            : isDone
              ? { color: "green" as const }
              : status === "failed"
                ? { color: "red" as const }
                : hasBody || status === "running"
                  ? { color: "yellow" as const }
                  : {};
          return (
            <Text
              key={s.id}
              bold={isSelected}
              dimColor={!isSelected && !isDone && !hasBody}
              {...colorProps}
            >
              {isSelected ? "▶ " : "  "}
              {mark} {s.title}
            </Text>
          );
        })}
      </Box>

      {/* Decision tab keeps the structured execution-summary panel. */}
      {state.activeTab === "decision" && state.executionSummary && (
        <ExecutionSummaryView summary={state.executionSummary} />
      )}

      {/* P0: selected section body viewport, or status/progress fallback. */}
      <Box flexDirection="column" marginTop={1} flexGrow={1}>
        {selected && selectedBody.trim() ? (
          <>
            <Text bold color="cyan">
              ── {selected.title} ── <Text dimColor>({selectedStatus})</Text>
            </Text>
            {view.lines.map((line, i) => (
              /* biome-ignore lint/suspicious/noArrayIndexKey: scrolled snapshot */
              <Text key={`${selectedId}-${i}`}>{line || " "}</Text>
            ))}
            <Text dimColor>
              {view.atTop ? "顶部" : "↑"} · {view.atBottom ? "底部" : "↓"} ·{" "}
              {scroll + view.lines.length}/{view.total} 行 · PgUp/PgDn 滚动 · ↑↓ 选择章节
            </Text>
          </>
        ) : selectedStatus === "running" ? (
          <>
            <Text color="yellow">{selected?.title ?? ""} 运行中…</Text>
            {state.logs.slice(-8).map((log, i) => (
              /* biome-ignore lint/suspicious/noArrayIndexKey: append-only log */
              <Text key={`${i}`} dimColor>
                • {log}
              </Text>
            ))}
          </>
        ) : selectedStatus === "failed" ? (
          <>
            <Text color="red">{selected?.title ?? ""} 失败</Text>
            <Text color="red">{state.errorMsg.slice(0, 200)}</Text>
            {state.errorDetail && <Text dimColor>按 e 查看错误详情</Text>}
          </>
        ) : (
          <>
            <Text dimColor>整体进度</Text>
            {state.logs.length > 0 ? (
              state.logs.slice(-12).map((log, i) => (
                /* biome-ignore lint/suspicious/noArrayIndexKey: append-only log */
                <Text key={`${i}`} dimColor={log.startsWith("──") || log.startsWith("✓")}>
                  {log.startsWith("──") || log.startsWith("✓") ? `  ${log}` : `• ${log}`}
                </Text>
              ))
            ) : (
              <Text dimColor>{selected ? `${selected.title} 等待中` : "准备开始分析。"}</Text>
            )}
            {state.status === "error" && (
              <Box marginTop={1} flexDirection="column">
                <Text color="red">{state.errorMsg.slice(0, 120)}</Text>
                {state.errorDetail && <Text dimColor>按 e 查看错误详情</Text>}
              </Box>
            )}
          </>
        )}
      </Box>
    </Box>
  );
}

function TabButton({
  label,
  done,
  total,
  active,
}: {
  label: string;
  done: number;
  total: number;
  active: boolean;
}) {
  const allDone = done === total && total > 0;
  return (
    <Box flexDirection="column" borderStyle={active ? "round" : "single"} paddingX={1}>
      <Text bold={active} {...(active ? { color: "cyan" as const } : {})}>
        {label} {active ? "▾" : "▸"}
      </Text>
      <Text color={allDone ? "green" : "yellow"}>
        {done}/{total}
      </Text>
    </Box>
  );
}

function ExecutionSummaryView({ summary }: { summary: ExecutionSummary }) {
  const range =
    summary.targetWeightMinPct !== undefined && summary.targetWeightMaxPct !== undefined
      ? `${summary.targetWeightMinPct.toFixed(1)}%-${summary.targetWeightMaxPct.toFixed(1)}%`
      : summary.targetWeightPct !== undefined
        ? `${summary.targetWeightPct.toFixed(1)}%`
        : "—";
  const weight = summary.targetWeightPct ?? summary.targetWeightMaxPct ?? 0;
  const filled = Math.max(0, Math.min(10, Math.round(weight / 10)));
  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1}>
      <Text bold color="cyan">
        ── 执行摘要 ──
      </Text>
      <Text>
        评级: <Text bold>{summary.rating ?? "—"}</Text> · 目标仓位: {range}{" "}
        <Text color="green">{"█".repeat(filled)}</Text>
        <Text dimColor>{"░".repeat(10 - filled)}</Text>
      </Text>
      <Text dimColor>执行节奏: {summary.executionDelay || "—"}</Text>
      <SummaryLine label="加仓条件" values={summary.addConditions} />
      <SummaryLine label="减仓条件" values={summary.reduceConditions} />
      <SummaryLine label="风险控制" values={summary.riskControls} />
    </Box>
  );
}

function SummaryLine({ label, values }: { label: string; values: string[] }) {
  return (
    <Text dimColor>
      {label}: {values.length > 0 ? values.join("；").slice(0, 100) : "—"}
    </Text>
  );
}

function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

// ===========================================================================
// P2: Report library screen
// ===========================================================================

function ReportLibrary({ state }: { state: AppState }) {
  const { reports, selectedIdx, body, bodyLoading, loading, error, scroll } = state.library;
  const view = reportViewport(body, scroll);
  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      <Text bold>📚 报告库</Text>
      <Box flexDirection="row" flexGrow={1} marginTop={1}>
        {/* Left: report list */}
        <Box flexDirection="column" width={28} borderStyle="single" paddingX={1}>
          <Text bold>历史报告</Text>
          {loading ? (
            <Text dimColor>加载中…</Text>
          ) : error ? (
            <Text color="red">{error.slice(0, 24)}</Text>
          ) : reports.length === 0 ? (
            <Text dimColor>暂无报告</Text>
          ) : (
            reports.slice(0, 18).map((r, i) => (
              <Text
                key={r.path}
                {...(i === selectedIdx ? { color: "cyan" as const, bold: true } : {})}
                dimColor={i !== selectedIdx}
              >
                {i === selectedIdx ? "▶ " : "  "}
                {(r.ticker.split(".")[0] ?? r.ticker).padEnd(8)} {r.date}
              </Text>
            ))
          )}
          <Box marginTop={1}>
            <Text dimColor>↑↓ 选择 · r 刷新 · Esc 返回</Text>
          </Box>
        </Box>
        {/* Right: body viewer (reuses the P0 viewport math) */}
        <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1} marginLeft={1}>
          {reports[selectedIdx] && (
            <Text bold color="cyan">
              {reports[selectedIdx]?.ticker} · {reports[selectedIdx]?.date}
            </Text>
          )}
          {bodyLoading ? (
            <Text dimColor>读取中…</Text>
          ) : body ? (
            <>
              {view.lines.map((line, i) => (
                /* biome-ignore lint/suspicious/noArrayIndexKey: scrolled snapshot */
                <Text key={`lib-${i}`}>{line || " "}</Text>
              ))}
              <Text dimColor>
                {view.atBottom ? "底部" : "↓"} · {scroll + view.lines.length}/{view.total} 行 ·
                PgUp/PgDn 滚动
              </Text>
            </>
          ) : (
            <Text dimColor>选择左侧报告查看内容。</Text>
          )}
        </Box>
      </Box>
    </Box>
  );
}

// ===========================================================================
// P4: Backtest viewer screen
// ===========================================================================

function fmtPct(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? `${(v * 100).toFixed(2)}%` : "—";
}
function fmtNum(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(4) : "—";
}

function BacktestScreen({ state }: { state: AppState }) {
  const { records, selectedIdx, view, loading, error } = state.backtest;
  const selected = records[selectedIdx];
  const metrics = view?.metrics ?? {};
  const health = view?.health ?? null;
  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      <Text bold>📈 回测结果</Text>
      <Box flexDirection="row" flexGrow={1} marginTop={1}>
        <Box flexDirection="column" width={28} borderStyle="single" paddingX={1}>
          <Text bold>回测记录</Text>
          {loading ? (
            <Text dimColor>加载中…</Text>
          ) : error ? (
            <Text color="red">{error.slice(0, 24)}</Text>
          ) : records.length === 0 ? (
            <Text dimColor>暂无回测产物</Text>
          ) : (
            records.slice(0, 16).map((r, i) => (
              <Text
                key={r.path}
                {...(i === selectedIdx ? { color: "cyan" as const, bold: true } : {})}
                dimColor={i !== selectedIdx}
              >
                {i === selectedIdx ? "▶ " : "  "}
                {(r.tickers[0]?.split(".")[0] ?? "?").padEnd(8)} {r.startDate}
              </Text>
            ))
          )}
          <Box marginTop={1}>
            <Text dimColor>↑↓ 选择 · r 刷新 · Esc 返回</Text>
          </Box>
        </Box>
        <Box flexDirection="column" flexGrow={1} borderStyle="single" paddingX={1} marginLeft={1}>
          {selected ? (
            <>
              <Text bold color="cyan">
                {selected.tickers.join(", ") || "?"} · {selected.startDate} → {selected.endDate}
              </Text>
              {view && view.nav.length > 1 && <Text color="cyan">{sparkline(view.nav, 40)}</Text>}
              <Box flexDirection="column" marginTop={1}>
                <Text>最终净值: {fmtNum(metrics.final_value)}</Text>
                <Text>累计收益: {fmtPct(metrics.cumulative_return)}</Text>
                <Text>年化收益: {fmtPct(metrics.annualized_return)}</Text>
                <Text>最大回撤: {fmtPct(metrics.max_drawdown)}</Text>
                <Text>夏普比率: {fmtNum(metrics.sharpe_ratio)}</Text>
                <Text>交易笔数: {String(metrics.total_trades ?? view?.trades ?? "—")}</Text>
              </Box>
              {view && view.benchmarkMetrics.length > 0 && (
                <Box flexDirection="column" marginTop={1}>
                  <Text bold>基准对比</Text>
                  {view.benchmarkMetrics.slice(0, 3).map((b, i) => (
                    <Text key={String(b.benchmark ?? i)} dimColor>
                      {String(b.benchmark ?? "?")}: 累计 {fmtPct(b.cumulative_return)} · 超额{" "}
                      {fmtPct(b.excess_cumulative_return)}
                    </Text>
                  ))}
                </Box>
              )}
              {health && Array.isArray(health.warnings) && health.warnings.length > 0 && (
                <Box flexDirection="column" marginTop={1}>
                  <Text bold color="yellow">
                    ⚠ 健康提示
                  </Text>
                  {(health.warnings as unknown[]).slice(0, 4).map((w, i) => (
                    /* biome-ignore lint/suspicious/noArrayIndexKey: static list */
                    <Text key={`w-${i}`} color="yellow">
                      • {String(w).slice(0, 80)}
                    </Text>
                  ))}
                </Box>
              )}
            </>
          ) : (
            <Text dimColor>选择左侧回测记录查看详情。</Text>
          )}
        </Box>
      </Box>
    </Box>
  );
}

// ===========================================================================
// P5: Paper trading screen
// ===========================================================================

function PaperScreen({ state }: { state: AppState }) {
  const { account, positions, trades, loading, error, user } = state.paper;
  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      <Text bold>💼 模拟交易{user ? ` · ${user}` : ""}</Text>
      {loading ? (
        <Text dimColor>加载中…</Text>
      ) : error ? (
        <Text color="red">{error}</Text>
      ) : (
        <Box flexDirection="column" marginTop={1}>
          {account && (
            <Box flexDirection="column" marginBottom={1}>
              <Text bold>账户</Text>
              <Text>
                总资产: {fmtNum(account.total_assets)} · 现金: {fmtNum(account.cash)} · 市值:{" "}
                {fmtNum(account.market_value)}
              </Text>
              <Text dimColor>
                已实现盈亏: {fmtNum(account.realized_pnl)} · 浮动盈亏:{" "}
                {fmtNum(account.unrealized_pnl)}
              </Text>
            </Box>
          )}
          <Text bold>持仓 ({positions.length})</Text>
          {positions.length === 0 ? (
            <Text dimColor>无持仓</Text>
          ) : (
            positions.slice(0, 10).map((p) => (
              <Text key={String(p.ticker)}>
                {String(p.ticker).padEnd(12)} 数量 {String(p.quantity)} · 现价{" "}
                {fmtNum(p.current_price)} · 盈亏 {fmtPct(p.pnl_pct)}
              </Text>
            ))
          )}
          <Box marginTop={1} flexDirection="column">
            <Text bold>最近成交 ({trades.length})</Text>
            {trades.slice(0, 8).map((t) => (
              <Text key={String(t.id)} dimColor>
                {String(t.created_at).slice(0, 10)} {String(t.side)} {String(t.ticker)} ×{" "}
                {String(t.quantity)} @ {fmtNum(t.price)}
              </Text>
            ))}
          </Box>
        </Box>
      )}
      <Box marginTop={1}>
        <Text dimColor>r 刷新 · Esc 返回</Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// P6: Error detail overlay
// ===========================================================================

function ErrorDetailOverlay({ detail }: { detail: ErrorDetail }) {
  return (
    <Box
      flexDirection="column"
      borderStyle="double"
      borderColor="red"
      paddingX={2}
      paddingY={1}
      marginTop={1}
    >
      <Text bold color="red">
        ✗ 错误详情
      </Text>
      {detail.ticker && <Text>标的: {detail.ticker}</Text>}
      {detail.section && <Text>章节: {detail.section}</Text>}
      <Text dimColor>时间: {detail.timestamp}</Text>
      <Box marginTop={1}>
        <Text>{detail.message.slice(0, 400)}</Text>
      </Box>
      {detail.stack && (
        <Box flexDirection="column" marginTop={1}>
          <Text dimColor>调用栈:</Text>
          {detail.stack
            .split("\n")
            .slice(0, 8)
            .map((line, i) => (
              /* biome-ignore lint/suspicious/noArrayIndexKey: static stack snapshot */
              <Text key={`stk-${i}`} dimColor>
                {line.slice(0, 110)}
              </Text>
            ))}
        </Box>
      )}
      <Box marginTop={1}>
        <Text dimColor>按任意键关闭</Text>
      </Box>
    </Box>
  );
}

// ===========================================================================
// Entry
// ===========================================================================

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  render(<App />);
}
