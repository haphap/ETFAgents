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

export interface RenderOptions {
  language: string;
  /** Upstream market-flow report used by ``inlineContextualMarketLevels`` and ``defaultExecutionPlan``. */
  contextText?: string;
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
