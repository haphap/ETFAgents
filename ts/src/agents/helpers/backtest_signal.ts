/**
 * Backtest signal extraction from trader/portfolio output.
 *
 * Port of ``etfagents.backtest.signals`` — extracts framework-agnostic
 * ``BacktestSignal`` dicts from rendered prose + structured plan.
 *
 * Sub-step 2.6 ports:
 *   - BacktestSignal / BacktestTriggerRule / BacktestRiskRule types
 *   - buildTraderBacktestSignal (main entry for trader path)
 *   - _buildSignal (internal builder)
 *   - All supporting parsers (rating, weight, triggers, conditions, sections)
 */

import type { TraderProposal } from "../schemas/trader_proposal.js";
import { type AgentOutputSignal, parseAgentOutputSchema } from "./output_schema.js";
import { applyPositionSizingPolicy, type PositionSizingContext } from "./position_sizing.js";

// ===========================================================================
// Types
// ===========================================================================

export interface BacktestTriggerRule {
  metric: string;
  op: string;
  threshold: number | [number, number];
  action: string;
  delta_pct?: number | null;
  target_weight_pct?: number | null;
  note: string;
}

export interface BacktestRiskRule {
  metric: string;
  op: string;
  threshold: number | [number, number];
  action: string;
  max_weight_pct?: number | null;
  min_weight_pct?: number | null;
  note: string;
}

export interface BacktestSignal {
  ticker: string;
  decision_date: string;
  source: string;
  source_section: string;
  rating: string;
  target_weight_pct: number | null;
  target_weight_min_pct: number | null;
  target_weight_max_pct: number | null;
  raw_target_weight_pct?: number | null;
  raw_target_weight_min_pct?: number | null;
  raw_target_weight_max_pct?: number | null;
  weight_source: string;
  position_sizing_multiplier?: number;
  position_sizing_reasons?: string[];
  position_sizing_inputs?: Record<string, string | number>;
  max_drawdown_budget?: number;
  estimated_drawdown?: number;
  execution_delay: string;
  starter_size_text: string;
  add_triggers: BacktestTriggerRule[];
  reduce_triggers: BacktestTriggerRule[];
  exit_triggers: BacktestTriggerRule[];
  rebalance_triggers: BacktestTriggerRule[];
  risk_rules: BacktestRiskRule[];
  add_conditions: string[];
  reduce_conditions: string[];
  exit_conditions: string[];
  rebalance_conditions: string[];
  risk_controls: string[];
  monitoring_points: string[];
  signal_text_snapshot: string;
}

// ===========================================================================
// Regex / hint constants (verbatim from Python)
// ===========================================================================

const PERCENT_RANGE_RE =
  /(\d+(?:\.\d+)?)\s*(?:%|％)\s*(?:-|–|—|~|～|至|到)\s*(\d+(?:\.\d+)?)\s*(?:%|％)/;
const PERCENT_SINGLE_RE = /(\d+(?:\.\d+)?)\s*(?:%|％)/;
const RATING_LINE_RE =
  /^[ \t]*(?:研究结论|最终配置建议|最终交易建议|执行倾向|final allocation proposal|final transaction proposal|execution bias|research view)[ \t]*[:：].*$/im;

const TARGET_HINTS = [
  "target allocation",
  "target exposure",
  "allocation band",
  "target weight",
  "目标仓位",
  "目标配置",
  "目标暴露",
  "配置带",
  "基础仓位",
  "基准仓位",
];
const INITIAL_HINTS = [
  "initial",
  "starter",
  "base position",
  "试探仓",
  "初始",
  "底仓",
  "首仓",
  "建仓",
];
const RELATIVE_TARGET_HINTS = [
  "target allocation of",
  "target exposure of",
  "target weight of",
  "目标仓位的",
  "目标配置的",
];

const ADD_HINTS = [
  "add",
  "increase exposure",
  "build",
  "accumulate",
  "加仓",
  "增持",
  "回补",
  "上调",
  "提高仓位",
  "扩大仓位",
];
const REDUCE_HINTS = [
  "reduce",
  "trim",
  "cut position",
  "lower exposure",
  "减仓",
  "减持",
  "降低仓位",
  "降低敞口",
  "降仓",
  "止盈",
];
const EXIT_HINTS = [
  "exit",
  "close position",
  "sell",
  "stop out",
  "清仓",
  "卖出",
  "退出",
  "止损离场",
];
const REBALANCE_HINTS = ["rebalance", "rotate", "调仓", "再平衡", "轮动"];
const RISK_HINTS = [
  "risk",
  "stop loss",
  "cut loss",
  "invalidation",
  "风控",
  "风险",
  "止损",
  "失效",
];
const MONITOR_HINTS = [
  "monitor",
  "watch",
  "track",
  "verify",
  "关注",
  "跟踪",
  "观察",
  "监控",
  "验证",
];

const DEFAULT_TARGET_WEIGHT: Record<string, number> = {
  BUY: 35,
  OVERWEIGHT: 25,
  HOLD: 15,
  UNDERWEIGHT: 5,
  SELL: 0,
};

const RATING_PATTERNS: ReadonlyArray<readonly [string, RegExp]> = [
  ["BUY", /(?:buy|买入)/i],
  ["OVERWEIGHT", /(?:overweight|增持)/i],
  ["HOLD", /(?:hold|持有)/i],
  ["UNDERWEIGHT", /(?:underweight|减持)/i],
  ["SELL", /(?:sell|卖出)/i],
];

const CHINESE_HEADING_RE = /^[一二三四五六七八九十]+、\S/m;

// ===========================================================================
// Public API
// ===========================================================================

export function buildTraderBacktestSignal(
  ticker: string,
  decisionDate: string,
  renderedText: string,
  structuredPlan: TraderProposal | null = null,
  sizingContext: PositionSizingContext = {},
): BacktestSignal {
  const schemaSignal = parseAgentOutputSchema(renderedText, "trader");
  const rating = normalizeRating(
    (structuredPlan?.rating as string | undefined) ??
      schemaFieldString(schemaSignal, "allocation_action") ??
      parseRating(renderedText),
  );
  const actionText =
    normalizeText(structuredPlan?.execution_plan ?? "") ||
    extractMarkdownSection(renderedText, ["## Allocation Execution Plan", "## 配置执行计划"]);
  const riskText =
    normalizeText(structuredPlan?.risk_management ?? "") ||
    extractMarkdownSection(renderedText, ["## Rebalance and Risk Controls", "## 再平衡与风险控制"]);

  return buildSignal({
    ticker,
    decisionDate,
    source: "trader",
    sourceSection: "execution_plan",
    rating,
    primaryText: actionText,
    secondaryText: riskText,
    structuredPlan,
    schemaSignal,
    sizingContext,
  });
}

// ===========================================================================
// Internal builder
// ===========================================================================

interface BuildSignalOptions {
  ticker: string;
  decisionDate: string;
  source: string;
  sourceSection: string;
  rating: string;
  primaryText: string;
  secondaryText: string;
  structuredPlan: TraderProposal | null;
  schemaSignal: AgentOutputSignal | null;
  sizingContext: PositionSizingContext;
}

function buildSignal(opts: BuildSignalOptions): BacktestSignal {
  const {
    ticker,
    decisionDate,
    source,
    sourceSection,
    rating,
    primaryText,
    secondaryText,
    structuredPlan,
    schemaSignal,
    sizingContext,
  } = opts;

  // Target weight: structured plan → parsed Output Schema → prose → rating defaults
  let targetRange = extractStructuredTargetWeight(structuredPlan);
  let weightSource: string;
  if (targetRange === null) {
    targetRange = extractSchemaTargetWeight(schemaSignal);
    if (targetRange === null) {
      targetRange = extractTargetWeight(primaryText, secondaryText);
      weightSource = targetRange ? targetRange[1] : "unknown";
    } else {
      weightSource = targetRange[1];
    }
  } else {
    weightSource = targetRange[1];
  }

  let targetWeightPct: number;
  let targetWeightMinPct: number;
  let targetWeightMaxPct: number;
  if (targetRange && targetRange[0] !== null) {
    const [low, high] = targetRange[0];
    targetWeightPct = round4((low + high) / 2);
    targetWeightMinPct = round4(low);
    targetWeightMaxPct = round4(high);
  } else {
    const def = DEFAULT_TARGET_WEIGHT[rating] ?? DEFAULT_TARGET_WEIGHT.HOLD ?? 15;
    targetWeightPct = def;
    targetWeightMinPct = def;
    targetWeightMaxPct = def;
    weightSource = "rating_map";
  }

  const structuredTriggers = extractStructuredTriggerRules(structuredPlan);
  const snapshot = [normalizeText(primaryText), normalizeText(secondaryText)]
    .filter(Boolean)
    .join("\n");

  const sizing = applyPositionSizingPolicy({
    rating,
    targetWeightPct,
    targetWeightMinPct,
    targetWeightMaxPct,
    ...sizingContext,
    traderSchemaSignal: schemaSignal,
    ...(structuredPlan?.confidence !== undefined && structuredPlan.confidence !== null
      ? { traderConfidence: structuredPlan.confidence }
      : {}),
  });

  return {
    ticker,
    decision_date: decisionDate,
    source,
    source_section: sourceSection,
    rating,
    target_weight_pct: sizing.targetWeightPct,
    target_weight_min_pct: sizing.targetWeightMinPct,
    target_weight_max_pct: sizing.targetWeightMaxPct,
    raw_target_weight_pct: sizing.rawTargetWeightPct,
    raw_target_weight_min_pct: sizing.rawTargetWeightMinPct,
    raw_target_weight_max_pct: sizing.rawTargetWeightMaxPct,
    weight_source: weightSource,
    position_sizing_multiplier: sizing.multiplier,
    position_sizing_reasons: sizing.reasons,
    position_sizing_inputs: sizing.inputs,
    max_drawdown_budget: sizing.maxDrawdownBudget,
    estimated_drawdown: sizing.estimatedDrawdown,
    execution_delay: extractExecutionTiming(structuredPlan, schemaSignal),
    starter_size_text: extractSentenceWithHints(primaryText, INITIAL_HINTS),
    add_triggers: structuredTriggers.add_triggers,
    reduce_triggers: structuredTriggers.reduce_triggers,
    exit_triggers: structuredTriggers.exit_triggers,
    rebalance_triggers: structuredTriggers.rebalance_triggers,
    risk_rules: structuredTriggers.risk_rules,
    add_conditions: collectConditions([primaryText, secondaryText], ADD_HINTS),
    reduce_conditions: collectConditions([primaryText, secondaryText], REDUCE_HINTS),
    exit_conditions: collectConditions([primaryText, secondaryText], EXIT_HINTS),
    rebalance_conditions: collectConditions([primaryText, secondaryText], REBALANCE_HINTS),
    risk_controls: collectConditions([primaryText, secondaryText], RISK_HINTS),
    monitoring_points: collectConditions([primaryText, secondaryText], MONITOR_HINTS),
    signal_text_snapshot: snapshot,
  };
}

// ===========================================================================
// Weight extraction
// ===========================================================================

function extractStructuredTargetWeight(
  plan: TraderProposal | null,
): [[number, number], string] | null {
  if (!plan) return null;

  const pct = coercePct(plan.target_weight_pct ?? null);
  if (pct !== null) return [[pct, pct], "structured_field"];

  const band = plan.target_weight_band ?? null;
  if (band && Array.isArray(band) && band.length === 2) {
    const low = coercePct(band[0]);
    const high = coercePct(band[1]);
    if (low !== null && high !== null) {
      return [[Math.min(low, high), Math.max(low, high)], "structured_field"];
    }
  }
  return null;
}

function extractSchemaTargetWeight(
  signal: AgentOutputSignal | null,
): [[number, number], string] | null {
  const raw = signal?.fields.target_weight_band;
  if (raw === undefined || Array.isArray(raw)) return null;
  if (typeof raw === "number") return [[raw, raw], "schema_field"];
  const text = raw.trim();
  if (!text || /^unknown$/i.test(text)) return null;
  const rangeMatch =
    /(\d+(?:\.\d+)?)\s*(?:%|％)?\s*(?:-|–|—|~|～|至|到)\s*(\d+(?:\.\d+)?)\s*(?:%|％)?/.exec(text);
  if (rangeMatch) {
    const low = Number.parseFloat(rangeMatch[1] ?? "0");
    const high = Number.parseFloat(rangeMatch[2] ?? "0");
    return [[Math.min(low, high), Math.max(low, high)], "schema_field"];
  }
  const singleMatch = /(\d+(?:\.\d+)?)\s*(?:%|％)?/.exec(text);
  if (singleMatch) {
    const value = Number.parseFloat(singleMatch[1] ?? "0");
    return [[value, value], "schema_field"];
  }
  return null;
}

function extractTargetWeight(...texts: string[]): [[number, number], string] | null {
  const combined = texts.join(" ");
  const targetSentence = extractSentenceWithHints(combined, TARGET_HINTS);
  if (targetSentence) {
    const weight = extractWeightRangeFromSentence(targetSentence);
    if (weight) return [weight, "parsed_target_range"];
  }

  for (const text of texts) {
    const starter = extractSentenceWithHints(text, INITIAL_HINTS);
    if (starter && !containsRelativeTargetReference(starter)) {
      const weight = extractWeightRangeFromSentence(starter);
      if (weight) return [weight, "parsed_initial_range"];
    }
  }
  return null;
}

function extractWeightRangeFromSentence(sentence: string): [number, number] | null {
  if (containsRelativeTargetReference(sentence)) return null;
  const rangeMatch = PERCENT_RANGE_RE.exec(sentence);
  if (rangeMatch) {
    const low = Number.parseFloat(rangeMatch[1] ?? "0");
    const high = Number.parseFloat(rangeMatch[2] ?? "0");
    return [Math.min(low, high), Math.max(low, high)];
  }
  const singleMatch = PERCENT_SINGLE_RE.exec(sentence);
  if (singleMatch) {
    const value = Number.parseFloat(singleMatch[1] ?? "0");
    return [value, value];
  }
  return null;
}

function containsRelativeTargetReference(text: string): boolean {
  const lowered = text.toLowerCase();
  return RELATIVE_TARGET_HINTS.some((h) => lowered.includes(h) || text.includes(h));
}

// ===========================================================================
// Trigger / risk rule extraction
// ===========================================================================

function extractStructuredTriggerRules(plan: TraderProposal | null): {
  add_triggers: BacktestTriggerRule[];
  reduce_triggers: BacktestTriggerRule[];
  exit_triggers: BacktestTriggerRule[];
  rebalance_triggers: BacktestTriggerRule[];
  risk_rules: BacktestRiskRule[];
} {
  if (!plan) {
    return {
      add_triggers: [],
      reduce_triggers: [],
      exit_triggers: [],
      rebalance_triggers: [],
      risk_rules: [],
    };
  }
  return {
    add_triggers: coerceTriggerRules(plan.add_triggers ?? []),
    reduce_triggers: coerceTriggerRules(plan.reduce_triggers ?? []),
    exit_triggers: coerceTriggerRules(plan.exit_triggers ?? []),
    rebalance_triggers: coerceTriggerRules(plan.rebalance_triggers ?? []),
    risk_rules: coerceRiskRules(plan.risk_controls ?? []),
  };
}

function coerceTriggerRules(raw: readonly Record<string, unknown>[]): BacktestTriggerRule[] {
  const out: BacktestTriggerRule[] = [];
  for (const rule of raw) {
    const metric = String(rule.metric ?? "")
      .trim()
      .toLowerCase();
    const op = String(rule.op ?? "").trim();
    const action = String(rule.action ?? "")
      .trim()
      .toLowerCase();
    const threshold = coerceThreshold(rule.threshold ?? null);
    if (!metric || !op || !action || threshold === null) continue;
    out.push({
      metric,
      op,
      threshold,
      action,
      delta_pct: coercePct(rule.delta_pct ?? null),
      target_weight_pct: coercePct(rule.target_weight_pct ?? null),
      note: String(rule.note ?? "").trim(),
    });
  }
  return out;
}

function coerceRiskRules(raw: readonly Record<string, unknown>[]): BacktestRiskRule[] {
  const out: BacktestRiskRule[] = [];
  for (const rule of raw) {
    const metric = String(rule.metric ?? "")
      .trim()
      .toLowerCase();
    const op = String(rule.op ?? "").trim();
    const action = String(rule.action ?? "")
      .trim()
      .toLowerCase();
    const threshold = coerceThreshold(rule.threshold ?? null);
    if (!metric || !op || !action || threshold === null) continue;
    out.push({
      metric,
      op,
      threshold,
      action,
      max_weight_pct: coercePct(rule.max_weight_pct ?? null),
      min_weight_pct: coercePct(rule.min_weight_pct ?? null),
      note: String(rule.note ?? "").trim(),
    });
  }
  return out;
}

function coerceThreshold(value: unknown): number | [number, number] | null {
  if (Array.isArray(value) && value.length === 2) {
    const low = coercePct(value[0]);
    const high = coercePct(value[1]);
    if (low === null || high === null) return null;
    return [Math.min(low, high), Math.max(low, high)];
  }
  return coercePct(value);
}

function extractExecutionTiming(
  plan: TraderProposal | null,
  signal: AgentOutputSignal | null = null,
): string {
  const raw = plan?.execution_timing ?? schemaFieldString(signal, "execution_timing") ?? null;
  if (raw === null || raw === undefined) return "next_open";
  const normalized = String(raw).trim().toLowerCase();
  if (normalized === "same_close") return "same_close";
  if (normalized === "next_open") return "next_open";
  if (normalized === "next_close") return "next_close";
  return ["same_close", "next_open", "next_close"].includes(normalized) ? normalized : "next_open";
}

// ===========================================================================
// Prose extraction
// ===========================================================================

function collectConditions(texts: string[], hints: readonly string[]): string[] {
  const collected: string[] = [];
  for (const text of texts) {
    for (const sentence of iterSentences(text)) {
      const lowered = sentence.toLowerCase();
      if (hints.some((h) => lowered.includes(h) || sentence.includes(h))) {
        collected.push(sentence);
      }
    }
  }
  return dedupe(collected);
}

function extractSentenceWithHints(text: string, hints: readonly string[]): string {
  for (const sentence of iterSentences(text)) {
    const lowered = sentence.toLowerCase();
    if (hints.some((h) => lowered.includes(h) || sentence.includes(h))) {
      return sentence;
    }
  }
  return "";
}

function iterSentences(text: string): string[] {
  const normalized = normalizeText(text);
  if (!normalized) return [];
  return normalized
    .split(/(?<=[。！？!?；;])\s+|\n+/)
    .map((s) => s.replace(/^[ \t-]+|[ \t-]+$/g, ""))
    .filter(Boolean);
}

function extractMarkdownSection(text: string, headings: readonly string[]): string {
  const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  for (const heading of headings) {
    const label = heading.replace(/^#+\s*/, "").trim();
    const escaped = escapeRegExp(label);

    // Markdown heading: `## label`
    const mdRe = new RegExp(`^(#+)\\s+${escaped}\\s*$`, "m");
    const mdMatch = mdRe.exec(normalized);
    if (mdMatch?.[1]) {
      const level = mdMatch[1].length;
      const start = mdMatch.index ?? 0;
      const remainder = normalized.slice(start + mdMatch[0].length);
      const boundary = new RegExp(`^#{1,${level}}\\s+\\S`, "m");
      return sliceUntilNextHeading(remainder, boundary);
    }

    // Chinese numbered heading: `一、label`
    const cnRe = new RegExp(`^[一二三四五六七八九十]+、${escaped}\\s*$`, "m");
    const cnMatch = cnRe.exec(normalized);
    if (cnMatch) {
      const cnStart = cnMatch.index ?? 0;
      const remainder = normalized.slice(cnStart + cnMatch[0].length);
      return sliceUntilNextHeading(remainder, CHINESE_HEADING_RE);
    }
  }
  return "";
}

function sliceUntilNextHeading(remainder: string, boundary: RegExp): string {
  const match = boundary.exec(remainder);
  const end = match ? match.index : remainder.length;
  return normalizeText(remainder.slice(0, end));
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function _stripRatingLines(text: string): string {
  return normalizeText(text.replace(RATING_LINE_RE, ""));
}

// ===========================================================================
// Rating parsing
// ===========================================================================

function parseRating(text: string): string {
  const content = (text ?? "").trim();
  if (!content) return "HOLD";
  const upper = content.toUpperCase();
  if (upper in DEFAULT_TARGET_WEIGHT) return upper;
  for (const [rating, pattern] of RATING_PATTERNS) {
    if (pattern.test(content)) return rating;
  }
  return "HOLD";
}

function normalizeRating(rating: unknown): string {
  if (rating && typeof rating === "object" && "value" in (rating as Record<string, unknown>)) {
    return parseRating(String((rating as Record<string, unknown>).value ?? "HOLD"));
  }
  return parseRating(String(rating ?? "HOLD"));
}

function schemaFieldString(signal: AgentOutputSignal | null, field: string): string | null {
  const value = signal?.fields[field];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

// ===========================================================================
// Utilities
// ===========================================================================

function normalizeText(text: string): string {
  const content = (text ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  if (!content) return "";
  const lines = content
    .split("\n")
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  return lines.join("\n");
}

function coercePct(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? round4(n) : null;
}

function round4(n: number): number {
  return Math.round(n * 10000) / 10000;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function dedupe(items: readonly string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const s = item.trim();
    if (!s || seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out;
}
