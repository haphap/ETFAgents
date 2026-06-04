/**
 * Path A + sub-step 2.5c-2 renderer for ``TraderProposal``.
 *
 * Mirrors Python's ``render_trader_proposal`` full chain:
 *   1. sanitizeSection(execution_plan, defaultExecutionPlan, rating)
 *   2. inlineContextualMarketLevels(execution_plan, contextText)
 *   3. stripConstituentTradeInstructions(execution_plan)
 *   4. IF missingExecutionThresholds → mergeSparseSectionWithDefault
 *   5. sanitizeTraderThesis(thesis, execution_plan, rating)
 *   6. sanitizeTraderRiskManagement(risk_mgmt, thesis, execution_plan, rating)
 *
 * Then format Chinese-mode with numbered blocks / thesis body.
 */

import { collapseBlankLines } from "../prompts/shared.js";
import { isChinese, localizeRating } from "../schemas/rating.js";
import type { TraderProposal } from "../schemas/trader_proposal.js";
import { inlineContextualMarketLevels } from "./market_levels.js";
import {
  compactText,
  defaultExecutionPlan,
  mergeSparseSectionWithDefault,
  missingExecutionThresholds,
  sanitizeSection,
  sanitizeTraderRiskManagement,
  sanitizeTraderThesis,
} from "./sanitize_section.js";
import {
  formatTraderNumberedBlocks,
  formatTraderThesisBody,
  stripConstituentTradeInstructions,
  stripNumberedHeadingPrefix,
} from "./trader_format.js";

/**
 * Heading aliases that trader output might embed inline.  Mirrors the
 * ``heading_aliases`` tuple in Python ``render_trader_proposal``.
 */
const TRADER_HEADING_ALIASES: ReadonlyArray<string> = [
  "ETF配置逻辑",
  "配置核心逻辑",
  "配置执行计划",
  "交易执行计划",
  "再平衡与风险控制",
  "调仓与风控机制",
  "ETF Allocation Thesis",
  "Allocation Core Logic",
  "Allocation Execution Plan",
  "Trading Execution Plan",
  "Rebalance and Risk Controls",
  "Rebalance and Risk Control",
];

const TRADER_SCHEMA_HEADING_RE =
  /(?:^|\n)\s*(?:\*\*)?(?:输出Schema|Output Schema)(?:\*\*)?\s*(?:\n|$)/;

const RATING_TO_ALLOCATION_ACTION: Record<TraderProposal["rating"], string> = {
  Buy: "BUY",
  Overweight: "OVERWEIGHT",
  Hold: "HOLD",
  Underweight: "UNDERWEIGHT",
  Sell: "SELL",
};

const EXECUTION_TIMING_SCHEMA_VALUE = {
  same_close: "SAME_CLOSE",
  next_open: "NEXT_OPEN",
  next_close: "NEXT_CLOSE",
} as const;

const TRADER_SCHEMA_FIELDS = [
  "agent",
  "allocation_action",
  "target_weight_band",
  "execution_timing",
  "add_trigger_state",
  "risk_control_state",
  "key_drivers",
  "confidence",
] as const;

export interface RenderOptions {
  language: string;
  /** Upstream market-flow report used by ``inlineContextualMarketLevels`` and ``defaultExecutionPlan``. */
  contextText?: string;
}

function compactSchemaDriver(text: string | undefined): string {
  const cleaned = (text ?? "")
    .replace(/\*\*(?:输出Schema|Output Schema)\*\*[\s\S]*$/m, "")
    .replace(/^(?:一、|二、|三、|四、|##\s*)[^\n]*\n?/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return "";
  const sentence = cleaned.split(/[。！？!?]\s*|[.!?]\s+/)[0]?.trim() || cleaned;
  return sentence.length > 140 ? `${sentence.slice(0, 137)}...` : sentence;
}

function schemaDrivers(
  plan: TraderProposal | null | undefined,
  text: string,
  language: string,
): string[] {
  const candidates = plan
    ? [plan.thesis, plan.execution_plan, plan.risk_management]
    : text.split(/\n{2,}/).slice(0, 5);
  const drivers: string[] = [];
  const seen = new Set<string>();
  for (const candidate of candidates) {
    const driver = compactSchemaDriver(candidate);
    if (!driver) continue;
    const key = compactText(driver);
    if (seen.has(key)) continue;
    drivers.push(driver);
    seen.add(key);
    if (drivers.length >= 5) break;
  }
  const fallbackDrivers = isChinese(language)
    ? [
        "上游研究结论需要和交易执行条件同步验证",
        "目标仓位必须以ETF整体风险预算为约束",
        "风险控制触发条件决定是否维持或下调暴露",
      ]
    : [
        "Upstream research must be checked against execution conditions",
        "Target weight must stay within the ETF-level risk budget",
        "Risk-control triggers decide whether exposure is maintained or reduced",
      ];
  for (const fallback of fallbackDrivers) {
    if (drivers.length >= 3) break;
    const key = compactText(fallback);
    if (seen.has(key)) continue;
    drivers.push(fallback);
    seen.add(key);
  }
  return drivers.slice(0, 5);
}

function targetWeightBand(plan: TraderProposal | null | undefined): string {
  if (plan?.target_weight_band) {
    const [low, high] = plan.target_weight_band;
    return `${low}-${high}%`;
  }
  if (typeof plan?.target_weight_pct === "number") return `${plan.target_weight_pct}%`;
  return "UNKNOWN";
}

function schemaConfidence(plan: TraderProposal | null | undefined): string {
  if (!plan) return "0.50";
  let score = 0.6;
  if (typeof plan.target_weight_pct === "number" || plan.target_weight_band) score += 0.08;
  if (plan.execution_timing) score += 0.06;
  if (plan.add_triggers.length + plan.reduce_triggers.length + plan.exit_triggers.length > 0) {
    score += 0.06;
  }
  if (plan.risk_controls.length > 0) score += 0.06;
  return Math.min(score, 0.84).toFixed(2);
}

function schemaRiskControlState(plan: TraderProposal | null | undefined): string {
  if (!plan) return "NORMAL";
  if (plan.rating === "Sell" || plan.rating === "Underweight") return "ELEVATED";
  if (plan.risk_controls.some((rule) => rule.action === "exit" || rule.action === "cap")) {
    return "ELEVATED";
  }
  return "NORMAL";
}

function hasSchemaField(text: string, field: string): boolean {
  return new RegExp(`(?:^|\\n)\\s*${field}\\s*[:：]`).test(text);
}

/**
 * Append the trader's MOSAIC-style visible schema after post-processing.
 * The structured render path otherwise has no prose-level schema block, while
 * the free-text fallback may lose its schema when the execution-bias section is restored.
 */
export function appendTraderOutputSchema(
  text: string,
  plan: TraderProposal | null | undefined,
  language: string,
): string {
  const existingSchema = TRADER_SCHEMA_HEADING_RE.exec(text);
  if (existingSchema) {
    const schemaText = text.slice(existingSchema.index);
    if (TRADER_SCHEMA_FIELDS.every((field) => hasSchemaField(schemaText, field))) {
      return collapseBlankLines(text);
    }
    text = text.slice(0, existingSchema.index).trimEnd();
  }

  const heading = isChinese(language) ? "**输出Schema**" : "**Output Schema**";
  const allocationAction = plan ? RATING_TO_ALLOCATION_ACTION[plan.rating] : "HOLD";
  const timing = plan?.execution_timing
    ? EXECUTION_TIMING_SCHEMA_VALUE[plan.execution_timing]
    : "WAIT_FOR_TRIGGER";
  const addTriggerState = plan?.add_triggers.length ? "READY" : "WAIT";
  const block =
    `${heading}\n` +
    "agent: trader\n" +
    `allocation_action: ${allocationAction}\n` +
    `target_weight_band: "${targetWeightBand(plan)}"\n` +
    `execution_timing: ${timing}\n` +
    `add_trigger_state: ${addTriggerState}\n` +
    `risk_control_state: ${schemaRiskControlState(plan)}\n` +
    `key_drivers: ${JSON.stringify(schemaDrivers(plan, text, language))}\n` +
    `confidence: ${schemaConfidence(plan)}`;
  return collapseBlankLines(`${text}\n\n${block}`);
}

export function renderTraderProposal(plan: TraderProposal, opts: RenderOptions): string {
  const { language, contextText } = opts;
  const rating = plan.rating;

  // ---- 1. Sanitize execution_plan -------------------------------------------
  const execDefault = defaultExecutionPlan(rating, language, contextText);
  let executionPlan = sanitizeSection(plan.execution_plan, execDefault, rating, language, {
    checkActionConflict: true,
    requireDetail: true,
    stripHeadings: TRADER_HEADING_ALIASES,
  });

  // ---- 2. Inline contextual market levels -----------------------------------
  executionPlan = inlineContextualMarketLevels(executionPlan, contextText, language);

  // ---- 3. Strip constituent trade instructions ------------------------------
  executionPlan = stripConstituentTradeInstructions(executionPlan, language);

  // ---- 4. If still missing thresholds, merge with default -------------------
  if (
    missingExecutionThresholds(executionPlan) &&
    !compactText(executionPlan).includes(compactText(execDefault))
  ) {
    executionPlan = mergeSparseSectionWithDefault(executionPlan, execDefault, language);
    executionPlan = inlineContextualMarketLevels(executionPlan, contextText, language);
    executionPlan = stripConstituentTradeInstructions(executionPlan, language);
  }

  // ---- 5. Sanitize thesis ---------------------------------------------------
  const thesis = sanitizeTraderThesis(plan.thesis, executionPlan, rating, language);

  // ---- 6. Sanitize risk management ------------------------------------------
  let riskManagement = sanitizeTraderRiskManagement(
    plan.risk_management,
    thesis,
    executionPlan,
    rating,
    language,
  );
  riskManagement = stripConstituentTradeInstructions(riskManagement, language);

  // ---- 7. Format ------------------------------------------------------------
  const recommendation = localizeRating(rating, language);

  if (isChinese(language)) {
    const thesisBody = formatTraderThesisBody(stripNumberedHeadingPrefix(thesis), language);
    const execBlocks = formatTraderNumberedBlocks(executionPlan, "execution", language);
    const riskBlocks = formatTraderNumberedBlocks(riskManagement, "risk", language);
    return collapseBlankLines(
      "一、配置逻辑\n" +
        `${thesisBody.trim()}\n\n` +
        "二、配置执行计划\n" +
        `${execBlocks.trim()}\n\n` +
        "三、再平衡与风险控制\n" +
        `${riskBlocks.trim()}\n\n` +
        "四、执行倾向\n" +
        `**${recommendation}**`,
    );
  }

  return collapseBlankLines(
    "## ETF Allocation Thesis\n" +
      `${thesis.trim()}\n\n` +
      "## Allocation Execution Plan\n" +
      `${executionPlan.trim()}\n\n` +
      "## Rebalance and Risk Controls\n" +
      `${riskManagement.trim()}\n\n` +
      `EXECUTION BIAS: **${recommendation}**`,
  );
}
