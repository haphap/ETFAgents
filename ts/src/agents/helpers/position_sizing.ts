import type { AgentOutputSignal, AgentSignalMap, AgentSignalValue } from "./output_schema.js";

export interface PositionSizingOptions {
  /** Max acceptable drawdown budget as decimal (0.12) or percent (12). */
  maxDrawdownBudget?: number;
}

export interface PositionSizingContext extends PositionSizingOptions {
  agentSignals?: AgentSignalMap;
  traderSchemaSignal?: AgentOutputSignal | null;
  traderConfidence?: number | null;
}

export interface PositionSizingInput extends PositionSizingContext {
  rating: string;
  targetWeightPct: number;
  targetWeightMinPct: number;
  targetWeightMaxPct: number;
}

export interface PositionSizingResult {
  targetWeightPct: number;
  targetWeightMinPct: number;
  targetWeightMaxPct: number;
  rawTargetWeightPct: number;
  rawTargetWeightMinPct: number;
  rawTargetWeightMaxPct: number;
  multiplier: number;
  maxDrawdownBudget: number;
  estimatedDrawdown: number;
  reasons: string[];
  inputs: Record<string, string | number>;
}

const DEFAULT_MAX_DRAWDOWN_BUDGET = 0.12;

const RATING_CAPS: Record<string, number> = {
  BUY: 40,
  OVERWEIGHT: 30,
  HOLD: 18,
  UNDERWEIGHT: 10,
  SELL: 5,
};

function normalizeBudget(value: number | undefined): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_DRAWDOWN_BUDGET;
  const numeric = Number(value);
  if (numeric <= 0) return DEFAULT_MAX_DRAWDOWN_BUDGET;
  return numeric > 1 ? numeric / 100 : numeric;
}

function fieldValue(
  signals: AgentSignalMap | undefined,
  source: string,
  field: string,
): AgentSignalValue | undefined {
  return signals?.[source]?.fields[field];
}

function stringField(value: AgentSignalValue | undefined): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim().toUpperCase() : undefined;
}

function numericField(value: AgentSignalValue | undefined): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function clampPct(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value * 10000) / 10000));
}

function confidenceMultiplier(confidence: number | undefined, reasons: string[]): number {
  if (confidence === undefined) return 1;
  if (confidence < 0.45) {
    reasons.push(`低置信度 ${confidence.toFixed(2)}，仓位降至55%`);
    return 0.55;
  }
  if (confidence < 0.6) {
    reasons.push(`置信度 ${confidence.toFixed(2)} 偏低，仓位降至75%`);
    return 0.75;
  }
  if (confidence < 0.75) {
    reasons.push(`置信度 ${confidence.toFixed(2)} 中等，仓位降至90%`);
    return 0.9;
  }
  return 1;
}

function riskMultiplier(riskControlState: string | undefined, reasons: string[]): number {
  if (riskControlState === "ELEVATED") {
    reasons.push("风控状态 ELEVATED，仓位降至75%");
    return 0.75;
  }
  return 1;
}

function volatilityMultiplier(volatilityRegime: string | undefined, reasons: string[]): number {
  if (volatilityRegime === "EXPANDING") {
    reasons.push("波动状态 EXPANDING，仓位降至80%");
    return 0.8;
  }
  return 1;
}

function flowMultiplier(flowRegime: string | undefined, reasons: string[]): number {
  if (flowRegime === "DISTRIBUTION") {
    reasons.push("资金流 DISTRIBUTION，仓位降至75%");
    return 0.75;
  }
  if (flowRegime === "CROWDED") {
    reasons.push("资金流 CROWDED，仓位降至85%");
    return 0.85;
  }
  return 1;
}

// This is an asset/regime drawdown proxy, not a portfolio-contribution estimate.
// Target weight is applied later via the multiplier; supportive regimes may
// reduce the proxy, but they never raise the trader's stated target size.
function estimateDrawdown(args: {
  volatilityRegime?: string;
  flowRegime?: string;
  riskControlState?: string;
  confidence?: number;
}): number {
  let estimate = 0.12;
  if (args.volatilityRegime === "EXPANDING") estimate += 0.06;
  else if (args.volatilityRegime === "NORMAL") estimate += 0.02;
  else if (args.volatilityRegime === "CONTRACTING") estimate -= 0.02;

  if (args.riskControlState === "ELEVATED") estimate += 0.04;
  if (args.flowRegime === "DISTRIBUTION") estimate += 0.03;
  else if (args.flowRegime === "CROWDED") estimate += 0.02;
  else if (args.flowRegime === "ACCUMULATION") estimate -= 0.01;
  if (args.confidence !== undefined && args.confidence < 0.55) estimate += 0.02;
  return Math.min(0.25, Math.max(0.06, estimate));
}

export function applyPositionSizingPolicy(input: PositionSizingInput): PositionSizingResult {
  const reasons: string[] = [];
  const confidence =
    input.traderConfidence ??
    numericField(input.traderSchemaSignal?.fields.confidence) ??
    numericField(fieldValue(input.agentSignals, "trader", "confidence"));
  const riskControlState =
    stringField(input.traderSchemaSignal?.fields.risk_control_state) ??
    stringField(fieldValue(input.agentSignals, "trader", "risk_control_state"));
  const volatilityRegime = stringField(
    fieldValue(input.agentSignals, "market_flow", "volatility_regime"),
  );
  const flowRegime = stringField(fieldValue(input.agentSignals, "market_flow", "flow_regime"));

  let multiplier = 1;
  multiplier *= confidenceMultiplier(confidence, reasons);
  multiplier *= riskMultiplier(riskControlState, reasons);
  multiplier *= volatilityMultiplier(volatilityRegime, reasons);
  multiplier *= flowMultiplier(flowRegime, reasons);

  const maxDrawdownBudget = normalizeBudget(input.maxDrawdownBudget);
  const estimatedDrawdown = estimateDrawdown({
    ...(volatilityRegime ? { volatilityRegime } : {}),
    ...(flowRegime ? { flowRegime } : {}),
    ...(riskControlState ? { riskControlState } : {}),
    ...(confidence !== undefined ? { confidence } : {}),
  });
  if (estimatedDrawdown > maxDrawdownBudget) {
    const drawdownMultiplier = Math.max(0.35, maxDrawdownBudget / estimatedDrawdown);
    multiplier *= drawdownMultiplier;
    reasons.push(
      `估算回撤 ${(estimatedDrawdown * 100).toFixed(1)}% 超过预算 ${(maxDrawdownBudget * 100).toFixed(1)}%，仓位乘数 ${drawdownMultiplier.toFixed(2)}`,
    );
  }

  const cap = RATING_CAPS[input.rating] ?? RATING_CAPS.HOLD ?? 18;
  const cappedHigh = Math.min(input.targetWeightMaxPct * multiplier, cap);
  const cappedLow = Math.min(input.targetWeightMinPct * multiplier, cappedHigh);
  const scaledPct = Math.min(input.targetWeightPct * multiplier, cap);
  const targetWeightMinPct = clampPct(cappedLow);
  const targetWeightMaxPct = clampPct(cappedHigh);
  const targetWeightPct = clampPct(
    targetWeightMinPct === targetWeightMaxPct
      ? targetWeightMaxPct
      : Math.min(Math.max(scaledPct, targetWeightMinPct), targetWeightMaxPct),
  );
  if (input.targetWeightMaxPct > cap) {
    reasons.push(`评级 ${input.rating} 的仓位上限为 ${cap}%`);
  }

  return {
    targetWeightPct,
    targetWeightMinPct,
    targetWeightMaxPct,
    rawTargetWeightPct: input.targetWeightPct,
    rawTargetWeightMinPct: input.targetWeightMinPct,
    rawTargetWeightMaxPct: input.targetWeightMaxPct,
    multiplier: Math.round(multiplier * 10000) / 10000,
    maxDrawdownBudget,
    estimatedDrawdown,
    reasons,
    inputs: {
      ...(confidence !== undefined ? { confidence } : {}),
      ...(riskControlState ? { risk_control_state: riskControlState } : {}),
      ...(volatilityRegime ? { volatility_regime: volatilityRegime } : {}),
      ...(flowRegime ? { flow_regime: flowRegime } : {}),
      max_drawdown_budget: maxDrawdownBudget,
      estimated_drawdown: estimatedDrawdown,
    },
  };
}
