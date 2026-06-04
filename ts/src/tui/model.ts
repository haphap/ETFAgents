// ===========================================================================
// Banner
// ===========================================================================

export const HOME_TITLE = "ETFAgents";
export const HOME_SUBTITLE = "TypeScript terminal workspace";
export const HOME_BANNER_LINES = [
  "███████╗████████╗███████╗",
  "██╔════╝╚══██╔══╝██╔════╝",
  "█████╗     ██║   █████╗",
  "██╔══╝     ██║   ██╔══╝",
  "███████╗   ██║   ██║",
  "╚══════╝   ╚═╝   ╚═╝",
  " █████╗  ██████╗ ███████╗███╗   ██╗████████╗███████╗",
  "██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔════╝",
  "███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ███████╗",
  "██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ╚════██║",
  "██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ███████║",
  "╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝",
] as const;
export const HOME_BANNER_FOOTER = "Multi-agent ETF research terminal";

export const HOME_OPTIONS = [
  { key: "ticker", label: "Research", description: "创建 ETF 研究任务" },
  { key: "library", label: "Reports", description: "浏览历史研报" },
  { key: "backtest", label: "Backtest", description: "查看回测产物" },
  { key: "paper", label: "Paper Trading", description: "查看模拟盘账户" },
] as const;

// ===========================================================================
// Provider / Model catalog
// ===========================================================================

export const PROVIDERS = [
  "openai",
  "deepseek",
  "ollama",
  "xai",
  "openrouter",
  "minimax",
  "vllm",
] as const;

export const MODELS_BY_PROVIDER: Record<string, string[]> = {
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
export const ANALYST_IDS = [
  "market_flow",
  "catalyst_sentiment",
  "macro_regime",
  "meso_commodity",
  "holdings_industry",
  "top_holdings",
] as const;

export const DEPTH_OPTIONS = ["quick", "standard", "deep"] as const;
export type DepthOption = (typeof DEPTH_OPTIONS)[number];
export type Depth = DepthOption | "custom";
export const DEPTH_LABELS: Record<Depth, string> = {
  quick: "快速",
  standard: "标准",
  deep: "深度",
  custom: "自定义",
};

export const DEPTH_ROUND_PRESETS: Record<
  DepthOption,
  { debateRounds: number; riskRounds: number }
> = {
  quick: { debateRounds: 1, riskRounds: 1 },
  standard: { debateRounds: 2, riskRounds: 2 },
  deep: { debateRounds: 3, riskRounds: 3 },
};

export const PROVIDER_BASE_URLS: Record<string, string> = {
  openai: "OpenAI SDK default",
  xai: "https://api.x.ai/v1",
  openrouter: "https://openrouter.ai/api/v1",
  ollama: "http://localhost:11434/v1",
  vllm: "http://127.0.0.1:8020/v1",
  minimax: "https://api.minimax.chat/v1",
  deepseek: "https://api.deepseek.com/v1",
};

/** Report body viewport (lines) and wrap width used by the P0 reader. */
export const REPORT_VIEWPORT = 18;
export const REPORT_WIDTH = 116;
export const ELAPSED_REFRESH_MS = 5000;

// ===========================================================================
// Pipeline section model — mirrors cli/tui/services.py SECTION_DEFINITIONS
// and the node graph built by buildFullGraph (PR #86 full pipeline).
// ===========================================================================

export type Team = "分析师" | "研究" | "交易" | "风险" | "决策";

export interface SectionDef {
  id: string;
  title: string;
  team: Team;
}

export const DEFAULT_SECTIONS: SectionDef[] = [
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
export const TEAM_TABS: ReadonlyArray<{ key: string; team: Team; label: string }> = [
  { key: "analysts", team: "分析师", label: "📊 分析团队" },
  { key: "research", team: "研究", label: "📖 研究" },
  { key: "trader", team: "交易", label: "💹 交易" },
  { key: "risk", team: "风险", label: "⚠️ 风险" },
  { key: "decision", team: "决策", label: "🎯 决策" },
];

export function sectionGroups(selected?: Record<string, boolean>): Record<string, SectionDef[]> {
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
export const NODE_INFO: Record<
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

export type Phase = "home" | "ticker" | "config" | "dashboard" | "library" | "backtest" | "paper";
export type ConfigField =
  | "date"
  | "provider"
  | "model"
  | "depth"
  | "analysts"
  | "debateRounds"
  | "riskRounds";
export type SectionStatus = "pending" | "running" | "done" | "failed";

/** Structured failure detail surfaced in the P6 error overlay. */
export interface ErrorDetail {
  ticker?: string;
  section?: string;
  message: string;
  stack?: string;
  timestamp: string;
}

/** A discovered historical report (P2) or backtest artifact (P4). */
export interface ReportMeta {
  ticker: string;
  date: string;
  path: string;
  rating?: string;
}

export interface BacktestMeta {
  path: string;
  tickers: string[];
  startDate: string;
  endDate: string;
  cumulativeReturn?: number;
}

export interface BacktestView {
  metrics: Record<string, unknown>;
  benchmarkMetrics: Array<Record<string, unknown>>;
  health: Record<string, unknown> | null;
  nav: number[];
  trades: number;
}

export interface QueueItem {
  ticker: string;
  status: "pending" | "running" | "done" | "failed" | "cancelled";
}

export interface ExecutionSummary {
  rating?: string;
  targetWeightPct?: number;
  targetWeightMinPct?: number;
  targetWeightMaxPct?: number;
  targetPrice?: number;
  stopPrice?: number;
  executionDelay?: string;
  addConditions: string[];
  reduceConditions: string[];
  riskControls: string[];
}

export interface PriceRow {
  date?: string;
  name?: string;
  close?: number;
  pctChg?: number;
  high?: number;
  low?: number;
  volume?: number;
}

export interface AppState {
  phase: Phase;
  homeIdx: number;
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
  showHelp: boolean;
  showTeamDetail: boolean;
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

export type Action =
  | { type: "homeMove"; delta: number }
  | { type: "homeOpen" }
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
  | { type: "vllmModelsFetched"; models: string[]; baseUrl?: string }
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
  | { type: "toggleErrorDetail" }
  | { type: "toggleHelp" }
  | { type: "toggleTeamDetail" }
  | { type: "closeTeamDetail" };

export type AppDispatch = (action: Action) => void;

// ===========================================================================
// Helpers
// ===========================================================================

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function initSectionStatus(): Record<string, SectionStatus> {
  return Object.fromEntries(DEFAULT_SECTIONS.map((s) => [s.id, "pending" as const]));
}

export function initSelectedAnalysts(): Record<string, boolean> {
  return Object.fromEntries(ANALYST_IDS.map((id) => [id, true]));
}

/** Section ids belonging to a team tab, in pipeline order. */
export function sectionsForTab(tab: string, selected?: Record<string, boolean>): string[] {
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
export function wrapToWidth(line: string, width: number, continuationIndent = ""): string[] {
  const safeWidth = Math.max(12, width);
  if (line.length <= safeWidth) return [line];
  const out: string[] = [];
  let remaining = line;
  while (remaining.length > safeWidth) {
    const limit = out.length === 0 ? safeWidth : safeWidth - continuationIndent.length;
    let cut = bestWrapIndex(remaining, limit);
    if (out.length > 0 && cut <= continuationIndent.length) {
      cut = Math.max(continuationIndent.length + 1, Math.min(limit, remaining.length));
    }
    out.push(remaining.slice(0, cut).trimEnd());
    remaining = `${continuationIndent}${remaining.slice(cut).trimStart()}`;
  }
  if (remaining) out.push(remaining);
  return out;
}

function bestWrapIndex(text: string, limit: number): number {
  const safeLimit = Math.max(8, Math.min(limit, text.length));
  const windowStart = Math.max(4, safeLimit - 18);
  for (let i = safeLimit; i >= windowStart; i -= 1) {
    const ch = text[i - 1];
    if (ch && /[\s,，;；。.!?！？、]/.test(ch)) return i;
  }
  return safeLimit;
}

export type ReportDisplayLineKind =
  | "blank"
  | "heading"
  | "subheading"
  | "paragraph"
  | "bullet"
  | "ordered"
  | "table"
  | "quote"
  | "code";

export interface ReportDisplayLine {
  text: string;
  kind: ReportDisplayLineKind;
  level?: number;
  continuation?: boolean;
}

function stripInlineMarkdown(text: string): string {
  return text
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .trimEnd();
}

function emphasizedHeadingText(text: string): string | null {
  const emphasized = text.match(/^(?:\*\*|__)(.+?)(?:\*\*|__)$/);
  if (!emphasized) return null;
  const inner = stripInlineMarkdown(emphasized[1] ?? "").trim();
  if (
    /^([一二三四五六七八九十]+[、.)]|[（(][一二三四五六七八九十]+[）)]|\d+[.)、])\s*\S+/.test(inner)
  ) {
    return inner;
  }
  return null;
}

function numberedHeadingText(text: string): string | null {
  const stripped = stripInlineMarkdown(text).trim();
  const numbered = stripped.match(
    /^(([一二三四五六七八九十]+[、.)])|([（(][一二三四五六七八九十]+[）)])|(\d+[.)、]))\s*(\S.+)$/,
  );
  if (!numbered) return null;
  const marker = numbered[1] ?? "";
  const title = numbered[5] ?? "";
  const likelyTitle =
    /[：:]/.test(title) ||
    /^[一二三四五六七八九十]+[、.)]/.test(marker) ||
    /^[（(][一二三四五六七八九十]+[）)]/.test(marker);
  if (!likelyTitle || stripped.length > 96 || /[。.!！?？]$/.test(stripped)) return null;
  return stripped;
}

function classifyReportLine(line: string): {
  text: string;
  kind: ReportDisplayLineKind;
  level?: number;
  continuationIndent?: string;
} {
  const trimmed = line.trim();
  if (!trimmed) return { text: "", kind: "blank" };

  const heading = trimmed.match(/^(#{1,6})\s+(.+?)\s*#*$/);
  if (heading) {
    const level = heading[1]?.length ?? 3;
    const text = stripInlineMarkdown(heading[2] ?? "");
    return { text, kind: level <= 2 ? "heading" : "subheading", level };
  }

  const emphasizedHeading = emphasizedHeadingText(trimmed);
  if (emphasizedHeading) {
    return { text: emphasizedHeading, kind: "subheading", level: 4 };
  }

  const numberedHeading = numberedHeadingText(trimmed);
  if (numberedHeading) {
    return { text: numberedHeading, kind: "subheading", level: 4 };
  }

  if (
    /^\|?.+\|.+\|?$/.test(trimmed) ||
    /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(trimmed)
  ) {
    return { text: trimmed, kind: "table", continuationIndent: "  " };
  }

  const bullet = trimmed.match(/^[-*•]\s+(.+)$/);
  if (bullet) {
    return {
      text: `• ${stripInlineMarkdown(bullet[1] ?? "")}`,
      kind: "bullet",
      continuationIndent: "  ",
    };
  }

  const ordered = trimmed.match(/^((?:\d+|[一二三四五六七八九十]+)[.)、])\s+(.+)$/);
  if (ordered) {
    const marker = ordered[1] ?? "1.";
    return {
      text: `${marker} ${stripInlineMarkdown(ordered[2] ?? "")}`,
      kind: "ordered",
      continuationIndent: " ".repeat(Math.min(marker.length + 1, 6)),
    };
  }

  if (trimmed.startsWith(">")) {
    return { text: stripInlineMarkdown(trimmed.replace(/^>\s*/, "")), kind: "quote" };
  }

  return { text: stripInlineMarkdown(line.trimEnd()), kind: "paragraph" };
}

function isMarkdownTableSeparator(line: string): boolean {
  const cells = parseMarkdownTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")));
}

function isMarkdownTableLine(line: string): boolean {
  const trimmed = line.trim();
  return (
    trimmed.includes("|") && (/^\|?.+\|.+\|?$/.test(trimmed) || isMarkdownTableSeparator(trimmed))
  );
}

function parseMarkdownTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => stripInlineMarkdown(cell.trim()));
}

function fitCell(text: string, width: number): string {
  if (text.length <= width) return text.padEnd(width);
  if (width <= 1) return text.slice(0, width);
  return `${text.slice(0, width - 1)}…`;
}

function renderMarkdownTableBlock(lines: string[], width: number): ReportDisplayLine[] {
  const parsed = lines
    .map((line) => ({
      cells: parseMarkdownTableRow(line),
      separator: isMarkdownTableSeparator(line),
    }))
    .filter((row) => row.cells.length > 0);
  const rows = parsed.filter((row) => !row.separator).map((row) => row.cells);
  const columnCount = Math.max(...rows.map((row) => row.length), 0);
  if (columnCount === 0) return [];

  const normalized = rows.map((row) =>
    Array.from({ length: columnCount }, (_, index) => row[index] ?? ""),
  );
  const columnWidths = Array.from({ length: columnCount }, (_, index) =>
    Math.max(3, ...normalized.map((row) => row[index]?.length ?? 0)),
  );
  const gapWidth = 2;
  const available = Math.max(24, width);
  let totalWidth = columnWidths.reduce((sum, item) => sum + item, 0) + gapWidth * (columnCount - 1);
  const minWidth = columnCount > 3 ? 6 : 8;
  while (totalWidth > available) {
    const shrinkIndex = columnWidths.reduce(
      (best, item, index) => (item > (columnWidths[best] ?? 0) ? index : best),
      0,
    );
    const current = columnWidths[shrinkIndex] ?? minWidth;
    if (current <= minWidth) break;
    columnWidths[shrinkIndex] = current - 1;
    totalWidth -= 1;
  }

  const renderRow = (cells: string[]) =>
    cells
      .map((cell, index) => fitCell(cell, columnWidths[index] ?? 8))
      .join("  ")
      .trimEnd();
  const separator = columnWidths.map((item) => "-".repeat(item)).join("  ");
  const out: ReportDisplayLine[] = [];
  normalized.forEach((row, index) => {
    out.push({ text: renderRow(row), kind: "table" });
    if (index === 0 && parsed.some((item) => item.separator)) {
      out.push({ text: separator, kind: "table" });
    }
  });
  return out;
}

function renderCodeBlock(lines: string[], width: number): ReportDisplayLine[] {
  const out: ReportDisplayLine[] = [];
  for (const line of lines) {
    for (const wrapped of wrapToWidth(line.replace(/\t/g, "  "), width, "  ")) {
      out.push({ text: wrapped, kind: "code" });
    }
  }
  return out;
}

function reportDisplayLines(body: string, width: number): ReportDisplayLine[] {
  const out: ReportDisplayLine[] = [];
  let previousBlank = true;
  const rawLines = body.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  for (let i = 0; i < rawLines.length; i += 1) {
    const raw = rawLines[i] ?? "";
    if (/^\s*```/.test(raw)) {
      const codeLines: string[] = [];
      while (i + 1 < rawLines.length) {
        i += 1;
        const codeLine = rawLines[i] ?? "";
        if (/^\s*```/.test(codeLine)) break;
        codeLines.push(codeLine);
      }
      if (!previousBlank) out.push({ text: "", kind: "blank" });
      out.push(...renderCodeBlock(codeLines, width));
      previousBlank = false;
      continue;
    }

    if (isMarkdownTableLine(raw)) {
      const tableLines = [raw];
      while (i + 1 < rawLines.length && isMarkdownTableLine(rawLines[i + 1] ?? "")) {
        i += 1;
        tableLines.push(rawLines[i] ?? "");
      }
      if (tableLines.length >= 2 && tableLines.some(isMarkdownTableSeparator)) {
        if (!previousBlank) out.push({ text: "", kind: "blank" });
        out.push(...renderMarkdownTableBlock(tableLines, width));
        previousBlank = false;
        continue;
      }
    }

    const classified = classifyReportLine(raw);
    if (classified.kind === "blank") {
      if (!previousBlank) out.push({ text: "", kind: "blank" });
      previousBlank = true;
      continue;
    }

    if ((classified.kind === "heading" || classified.kind === "subheading") && !previousBlank) {
      out.push({ text: "", kind: "blank" });
    }

    const wrapped = wrapToWidth(classified.text, width, classified.continuationIndent ?? "");
    wrapped.forEach((text, index) => {
      out.push({
        text,
        kind: classified.kind,
        ...(classified.level !== undefined ? { level: classified.level } : {}),
        ...(index > 0 ? { continuation: true } : {}),
      });
    });
    previousBlank = false;
  }
  while (out.at(-1)?.kind === "blank") out.pop();
  return out;
}

/**
 * P0: produce the visible report viewport. Returns the wrapped lines, the
 * clamped scroll offset, the total wrapped-line count, and edge flags so the
 * caller can render a scroll indicator without recomputing.
 */
export function reportDisplayViewport(
  body: string,
  scroll: number,
  viewport = REPORT_VIEWPORT,
  width = REPORT_WIDTH,
): {
  lines: ReportDisplayLine[];
  scroll: number;
  total: number;
  atTop: boolean;
  atBottom: boolean;
} {
  const lines = reportDisplayLines(body, width);
  const total = lines.length;
  const maxScroll = Math.max(0, total - viewport);
  const clamped = Math.max(0, Math.min(scroll, maxScroll));
  return {
    lines: lines.slice(clamped, clamped + viewport),
    scroll: clamped,
    total,
    atTop: clamped === 0,
    atBottom: clamped >= maxScroll,
  };
}

export function reportViewport(
  body: string,
  scroll: number,
  viewport = REPORT_VIEWPORT,
  width = REPORT_WIDTH,
): { lines: string[]; scroll: number; total: number; atTop: boolean; atBottom: boolean } {
  const view = reportDisplayViewport(body, scroll, viewport, width);
  return { ...view, lines: view.lines.map((line) => line.text) };
}

/** P1: clamp debate/risk rounds to the supported range (1–3); the graph loops
 * the debates for the chosen count via routeDebate / routeRiskDebate. */
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

export function dateDaysBefore(isoDate: string, days: number): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return isoDate;
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

export function asNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

export function parseCsvLine(line: string): string[] {
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

export function valueByKeys(row: Record<string, unknown>, keys: readonly string[]): unknown {
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

export function normalizePriceRows(rows: Array<Record<string, unknown>>): PriceRow[] {
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
export const PRICE_COLUMN_KEYS = new Set([
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

export function sparkline(values: readonly number[], width = 16): string {
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

export function listFromUnknown(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item))
    .filter(Boolean)
    .slice(0, 3);
}

const PRICE_RULE_METRICS = new Set(["close", "price", "nav"]);
const PRICE_TEXT_RE = /(\d+(?:\.\d+)?)(?:\s*元)/g;
const CONDITION_STRIP_RE = /^\s*\d+[.、)）]\s*|^[-*•]\s*|`[^`]*`/g;

function signalNumber(value: unknown, suffix = ""): string {
  const n = asNumber(value);
  if (n === undefined) return "--";
  return `${Number.isInteger(n) ? n.toFixed(0) : n.toFixed(3)}${suffix}`;
}

function cleanConditionText(text: string): string {
  return text
    .replace(CONDITION_STRIP_RE, "")
    .replace(/^[\w_]+\s*[:：]\s*/, "")
    .replace(/^[`「『].*?[`」』]\s*[-–—]\s*/, "")
    .trim();
}

function signalThreshold(rule: Record<string, unknown>): string {
  const threshold = rule.threshold;
  if (Array.isArray(threshold) && threshold.length === 2) {
    return `${signalNumber(threshold[0])}-${signalNumber(threshold[1])}`;
  }
  return signalNumber(threshold);
}

function ruleLine(rule: Record<string, unknown>): string {
  const note = String(rule.note ?? rule.action ?? "").trim();
  const metric = String(rule.metric ?? "").trim();
  const op = String(rule.op ?? "").trim();
  const threshold = signalThreshold(rule);
  const prefix = [metric, op, threshold].filter((part) => part && part !== "--").join(" ");
  return note ? `${prefix} ${note}`.trim() : prefix;
}

function signalLines(signal: Record<string, unknown>, keys: readonly string[]): string[] {
  const out: string[] = [];
  for (const key of keys) {
    const value = signal[key];
    if (!Array.isArray(value)) continue;
    for (const item of value) {
      if (typeof item === "string") {
        const cleaned = cleanConditionText(item);
        if (cleaned) out.push(cleaned);
      } else if (item && typeof item === "object") {
        const line = ruleLine(item as Record<string, unknown>);
        if (line) out.push(line);
      }
      if (out.length >= 3) return out;
    }
  }
  return out;
}

function extractPriceRule(
  signal: Record<string, unknown>,
  ruleKeys: readonly string[],
  actionHints: readonly string[],
): number | undefined {
  for (const key of ruleKeys) {
    const rules = signal[key];
    if (!Array.isArray(rules)) continue;
    for (const rule of rules) {
      if (!rule || typeof rule !== "object") continue;
      const record = rule as Record<string, unknown>;
      const metric = String(record.metric ?? "").toLowerCase();
      const action = String(record.action ?? "").toLowerCase();
      if (!PRICE_RULE_METRICS.has(metric)) continue;
      if (actionHints.length > 0 && !actionHints.some((hint) => action.includes(hint))) continue;
      const threshold = record.threshold;
      if (typeof threshold === "number") return threshold;
    }
  }
  return undefined;
}

function extractPriceFromText(
  signal: Record<string, unknown>,
  textKeys: readonly string[],
  hints: readonly string[],
): number | undefined {
  for (const key of textKeys) {
    const items = signal[key];
    if (!Array.isArray(items)) continue;
    for (const item of items) {
      if (typeof item !== "string") continue;
      PRICE_TEXT_RE.lastIndex = 0;
      for (const match of item.matchAll(PRICE_TEXT_RE)) {
        const raw = match[1];
        if (!raw || match.index === undefined) continue;
        const price = Number.parseFloat(raw);
        const start = Math.max(0, match.index - 40);
        const end = Math.min(item.length, match.index + 40);
        const context = item.slice(start, end).toLowerCase();
        if (hints.some((hint) => context.includes(hint.toLowerCase()))) return price;
      }
    }
  }
  return undefined;
}

export function priceRuler(stop: number, current: number, target: number, width = 30): string {
  const ordered: Array<[string, number]> = [
    ["止损价", stop],
    ["现价", current],
    ["目标价", target],
  ];
  ordered.sort((a, b) => a[1] - b[1]);
  const grouped: Array<{ value: number; labels: string[] }> = [];
  for (const [label, value] of ordered) {
    const last = grouped[grouped.length - 1];
    if (last && last.value === value) last.labels.push(label);
    else grouped.push({ value, labels: [label] });
  }
  const first = grouped[0];
  const last = grouped[grouped.length - 1];
  if (!first || !last) return "";
  const span = last.value - first.value;
  if (!span || span <= 0) return "";
  const parts: string[] = [];
  for (let i = 0; i < grouped.length; i += 1) {
    const item = grouped[i];
    if (!item) continue;
    if (i > 0) {
      const prev = grouped[i - 1];
      const distance = prev ? item.value - prev.value : 0;
      parts.push("─".repeat(Math.max(3, Math.round((distance / span) * width))));
    }
    const marker = item.labels.includes("现价") ? "╋ " : "";
    parts.push(`${marker}${item.labels.join("/")} ${signalNumber(item.value)}`);
  }
  return parts.join(" ");
}

export function queueStatusLabel(status: QueueItem["status"]): string {
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

export function buildExecutionSummary(
  finalState: Record<string, unknown>,
): ExecutionSummary | null {
  const signal = finalState.trader_backtest_signal as Record<string, unknown> | undefined;
  if (!signal) return null;
  const summary: ExecutionSummary = {
    addConditions: signalLines(signal, ["add_triggers", "add_conditions"]),
    reduceConditions: signalLines(signal, [
      "reduce_triggers",
      "reduce_conditions",
      "exit_triggers",
      "exit_conditions",
    ]),
    riskControls: signalLines(signal, ["risk_rules", "risk_controls"]),
  };
  const rating = signal.rating;
  if (typeof rating === "string" && rating) summary.rating = rating;
  const target = asNumber(signal.target_weight_pct);
  if (target !== undefined) summary.targetWeightPct = target;
  const targetMin = asNumber(signal.target_weight_min_pct);
  if (targetMin !== undefined) summary.targetWeightMinPct = targetMin;
  const targetMax = asNumber(signal.target_weight_max_pct);
  if (targetMax !== undefined) summary.targetWeightMaxPct = targetMax;
  const targetPrice =
    extractPriceRule(signal, ["add_triggers", "rebalance_triggers"], ["add", "buy", "rebalance"]) ??
    extractPriceFromText(signal, ["add_conditions"], ["突破", "加仓", "目标", "上方", "上行"]);
  if (targetPrice !== undefined) summary.targetPrice = targetPrice;
  const stopPrice =
    extractPriceRule(
      signal,
      ["risk_rules", "reduce_triggers", "exit_triggers"],
      ["reduce", "exit", "sell", "stop", "cap"],
    ) ??
    extractPriceFromText(
      signal,
      ["risk_controls", "reduce_conditions"],
      ["止损", "跌破", "防守", "下方", "stop"],
    );
  if (stopPrice !== undefined) summary.stopPrice = stopPrice;
  const delay = signal.execution_delay;
  if (typeof delay === "string" && delay) summary.executionDelay = delay;
  return summary;
}

export function initState(): AppState {
  return {
    phase: "home",
    homeIdx: 0,
    ticker: "",
    tickers: [],
    queue: [],
    currentTickerIdx: 0,
    date: today(),
    provider: "",
    model: "",
    selectedAnalysts: initSelectedAnalysts(),
    depth: "standard",
    debateRounds: DEPTH_ROUND_PRESETS.standard.debateRounds,
    riskRounds: DEPTH_ROUND_PRESETS.standard.riskRounds,
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
    showHelp: false,
    showTeamDetail: false,
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

export function focusValue(state: AppState): string {
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

export function selectOptions(state: AppState): string[] {
  if (state.selectOpen === "provider") return [...PROVIDERS];
  if (state.selectOpen === "model") {
    const p = state.provider.toLowerCase();
    if (p === "vllm") return state.vllmModels ?? [];
    return MODELS_BY_PROVIDER[p] ?? [];
  }
  if (state.selectOpen === "depth") return [...DEPTH_OPTIONS];
  return [];
}

export function modelHasOptions(state: AppState): boolean {
  if (!state.provider) return false;
  const p = state.provider.toLowerCase();
  if (p === "vllm") return (state.vllmModels?.length ?? 0) > 0;
  return (MODELS_BY_PROVIDER[p]?.length ?? 0) > 0;
}

export function isSelectField(state: AppState, field: ConfigField): boolean {
  if (field === "provider") return true;
  if (field === "depth") return true;
  if (field === "model") return modelHasOptions(state);
  return false;
}

export const FOCUS_ORDER: ConfigField[] = [
  "date",
  "provider",
  "model",
  "depth",
  "analysts",
  "debateRounds",
  "riskRounds",
];
export function nextFocus(current: ConfigField): ConfigField {
  const i = FOCUS_ORDER.indexOf(current);
  return FOCUS_ORDER[i + 1] ?? FOCUS_ORDER[0] ?? "date";
}

export function depthFromRounds(debateRounds: number, riskRounds: number): Depth {
  for (const [depth, preset] of Object.entries(DEPTH_ROUND_PRESETS) as Array<
    [DepthOption, { debateRounds: number; riskRounds: number }]
  >) {
    if (preset.debateRounds === debateRounds && preset.riskRounds === riskRounds) {
      return depth;
    }
  }
  return "custom";
}

export function backendDisplay(provider: string, backendUrl: string): string {
  if (backendUrl) return backendUrl;
  const key = provider.toLowerCase();
  if (key && PROVIDER_BASE_URLS[key]) return PROVIDER_BASE_URLS[key];
  return "(Bridge config)";
}

// ===========================================================================
// Reducer
// ===========================================================================

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "homeMove": {
      const n = HOME_OPTIONS.length;
      return { ...state, homeIdx: (state.homeIdx + action.delta + n) % n };
    }
    case "homeOpen": {
      const target = HOME_OPTIONS[state.homeIdx]?.key ?? "ticker";
      return { ...state, phase: target, errorMsg: "", selectOpen: null, selectIdx: 0 };
    }
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
        backendUrl: "",
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
        showHelp: false,
        showTeamDetail: false,
      };
    case "setFocus":
      return {
        ...state,
        focus: action.focus,
        selectOpen: null,
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
      if (state.selectOpen === "depth") {
        const depth = value as DepthOption;
        const preset = DEPTH_ROUND_PRESETS[depth];
        return {
          ...state,
          depth,
          debateRounds: preset.debateRounds,
          riskRounds: preset.riskRounds,
          selectOpen: null,
          selectIdx: 0,
        };
      }
      const newProvider = state.selectOpen === "provider" ? value : state.provider;
      const newModel = state.selectOpen === "provider" ? "" : state.model;
      const vllmModels =
        state.selectOpen === "provider" && newProvider.toLowerCase() !== "vllm"
          ? null
          : state.vllmModels;
      const backendUrl = state.selectOpen === "provider" ? "" : state.backendUrl;
      return {
        ...state,
        provider: newProvider,
        model: newModel,
        backendUrl,
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
        showHelp: false,
        showTeamDetail: false,
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
      const currentScroll = state.reportScrollBySection[action.sectionId] ?? 0;
      const previousView = reportViewport(previous ?? "", currentScroll);
      const shouldFollowBottom = !previous || previousView.atBottom;
      const nextView = shouldFollowBottom
        ? reportViewport(nextBody, Number.MAX_SAFE_INTEGER)
        : reportViewport(nextBody, currentScroll);
      return {
        ...state,
        reports: { ...state.reports, [action.sectionId]: nextBody },
        reportNodes: {
          ...state.reportNodes,
          [action.sectionId]: [...(state.reportNodes[action.sectionId] ?? []), action.nodeLabel],
        },
        reportScrollBySection: {
          ...state.reportScrollBySection,
          [action.sectionId]: nextView.scroll,
        },
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
      return {
        ...state,
        phase: "ticker",
        errorMsg: "",
        selectOpen: null,
        selectIdx: 0,
        showTeamDetail: false,
      };
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
      return {
        ...state,
        vllmModels: action.models,
        ...(action.baseUrl ? { backendUrl: action.baseUrl } : {}),
      };
    case "vllmModelsFailed":
      return { ...state, vllmModels: [] };

    // --- P1 config ---
    case "toggleAnalyst": {
      const currentlyOn = state.selectedAnalysts[action.id] !== false;
      // Refuse to turn off the last enabled analyst — the graph (and Python)
      // require at least one analyst; a 0-analyst run yields a decision with no
      // analyst reports. Keeping >=1 selected avoids that pseudo-result.
      if (currentlyOn && selectedAnalystIds(state.selectedAnalysts).length <= 1) {
        return state;
      }
      return {
        ...state,
        selectedAnalysts: {
          ...state.selectedAnalysts,
          [action.id]: !currentlyOn,
        },
      };
    }
    case "moveAnalystCursor": {
      const n = ANALYST_IDS.length;
      return { ...state, analystCursor: (state.analystCursor + action.delta + n) % n };
    }
    case "stepRounds": {
      const nextValue = clampRound(state[action.field] + action.delta);
      const nextDebate = action.field === "debateRounds" ? nextValue : state.debateRounds;
      const nextRisk = action.field === "riskRounds" ? nextValue : state.riskRounds;
      return {
        ...state,
        [action.field]: nextValue,
        depth: depthFromRounds(nextDebate, nextRisk),
      };
    }
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
      return {
        ...state,
        phase: action.phase,
        errorMsg: "",
        selectOpen: null,
        selectIdx: 0,
        showHelp: false,
        showTeamDetail: false,
      };

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
    case "toggleHelp":
      return { ...state, showHelp: !state.showHelp };
    case "toggleTeamDetail":
      return { ...state, showTeamDetail: !state.showTeamDetail };
    case "closeTeamDetail":
      return { ...state, showTeamDetail: false };
  }
}
