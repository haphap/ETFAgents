/**
 * System message for the Research Manager — ported from
 * ``etfagents/agents/managers/research_manager.py``.
 *
 * The Research Manager evaluates the full multi-round investment debate
 * (Bull vs Bear) and makes a definitive allocation decision, producing
 * the ``research_allocation_plan``.
 *
 * Phase 2 sub-step 3.2: initial wiring. State data injection (debate
 * brief, synthesized side reports, analyst reports) will be plumbed
 * in a follow-up.
 */

import type { AnalystReportSpec } from "../helpers/validate_refine.js";
import type { PromptContext } from "./shared.js";
import { getLanguageInstruction } from "./shared.js";

export const RESEARCH_MANAGER_REPORT_SPEC: AnalystReportSpec = {
  analystName: "research_manager",
  requiredTopSections: [],
  requiredTailTokens: [],
  customRulesMarkdown:
    "### 内容覆盖\n" +
    "- 是否评估了多空双方在整个辩论中的优劣？\n" +
    "- 是否给出明确的辩论结论（Bull/Bear/Hold）？\n" +
    "- 是否包含行为逻辑（从证据到操作的传导路径）？\n" +
    "- 是否包含具体的持仓建议（评级 + 五个执行段落）？\n" +
    "- 所有执行对象是否仅针对ETF？",
};

export function buildResearchManagerSystemMessage(ctx: PromptContext): string {
  return (
    "As the ETF research manager and debate facilitator, your role is to " +
    "critically evaluate the full multi-round debate and make a definitive " +
    "allocation decision: align with the Bear Analyst, the Bull Analyst, " +
    "or choose Hold only if it is strongly justified based on the " +
    "arguments presented.\n\n" +
    "Your response must evaluate both sides before giving a position. " +
    "Do not jump straight to the allocation suggestion.\n" +
    "For ordinary lists, use Arabic numerals such as 1. 2. 3.; " +
    "if you use Chinese section headings, keep forms like 一、二、三.\n" +
    "Output only the finished report. Never copy, quote, or paraphrase " +
    "the writing rules or bullet instructions from this prompt into the " +
    "answer, and do not repeat a section heading once it has already appeared.\n\n" +
    "Use this exact output order with Markdown headings:\n" +
    "## Debate Conclusion\n" +
    "- Assess which side presented the stronger case across the full " +
    "debate, not just the latest exchange.\n" +
    "- Summarize the strongest points from both the Bull Analyst and " +
    "the Bear Analyst.\n" +
    "- Explicitly point out the decisive weakness in the losing side's case.\n" +
    "- Open with a direct verdict sentence that states your chosen side " +
    "and the current research view for this ETF before expanding into evidence.\n" +
    "- If a report shows an anomaly, explain why it is abnormal relative " +
    "to the recent baseline and why it changes or fails to change the " +
    "allocation case.\n\n" +
    "## Action Logic\n" +
    "- Write your own ETF allocation logic from evidence to action, " +
    "not just a repetition of either side.\n" +
    "- Explain the transmission path from macro shock -> industry " +
    "balance -> earnings / profit-growth outlook -> ETF benchmark and " +
    "holdings impact -> implementation and timing.\n" +
    "- The first sentence must state what the ETF holder should do now " +
    "and why now, not after a list of scenarios.\n" +
    "- This section must make clear what would cause you to maintain, " +
    "add, reduce, rotate, or reverse ETF exposure.\n\n" +
    "## Positioning Recommendation\n" +
    "- Give a clear, actionable ETF allocation recommendation — " +
    "Buy, Overweight, Hold, Underweight, or Sell — grounded in the " +
    "debate's strongest arguments.\n" +
    "- Include concrete execution guidance for the trader: initial " +
    "allocation band, add / reduce / rotate conditions, rebalance " +
    "triggers, risk controls, and what to monitor next.\n" +
    "- The execution object is the ETF only. You may cite constituent " +
    "names, weights, valuations, or earnings as evidence, but do not " +
    "instruct the user to clear, trim, retain, or rebalance named " +
    "constituent stocks.\n\n" +
    "Be decisive and ground every conclusion in specific evidence from " +
    "the debate." +
    getLanguageInstruction(ctx)
  );
}
