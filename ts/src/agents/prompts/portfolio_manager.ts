/**
 * System message for the Portfolio Manager — ported from
 * ``etfagents/agents/managers/portfolio_manager.py``.
 *
 * The Portfolio Manager synthesizes the full risk debate (Aggressive,
 * Conservative, Neutral) and delivers the final ETF portfolio
 * allocation decision (``final_allocation_decision``).
 *
 * Phase 2 sub-step 3.3: initial wiring. State data injection
 * (risk debate brief, synthesized risk analyst reports, analyst
 * reports) will be plumbed in a follow-up.
 */

import type { AnalystReportSpec } from "../helpers/validate_refine.js";
import type { PromptContext } from "./shared.js";
import {
  getAgentOutputSchemaFieldNames,
  getAgentOutputSchemaInstruction,
  getDecisionSignalSummaryInstruction,
  getLanguageInstruction,
} from "./shared.js";

export const PORTFOLIO_MANAGER_REPORT_SPEC: AnalystReportSpec = {
  analystName: "portfolio_manager",
  requiredTopSections: [],
  requiredTailTokens: [],
  requireDecisionSignalSummary: true,
  requiredOutputSchemaFields: getAgentOutputSchemaFieldNames("portfolio_manager"),
  customRulesMarkdown:
    "### 内容覆盖\n" +
    "- 是否评估了三个风险视角（激进/保守/中性）在整个辩论中的优劣？\n" +
    "- 是否给出明确的辩论结论和最终配置建议？\n" +
    "- 是否包含行为逻辑（从证据到执行的传导路径）？\n" +
    "- 是否包含具体的持仓建议（评级 + 五个执行段落）？\n" +
    "- 所有执行对象是否仅针对ETF？",
};

export function buildPortfolioManagerSystemMessage(ctx: PromptContext): string {
  const chinese = ctx.language.trim().toLowerCase() !== "english";
  if (chinese) {
    return (
      "你是投资组合经理，负责综合研究经理方案、交易员执行计划和激进/保守/中性三方风险辩论，输出最终ETF组合配置决定。" +
      "你必须先评估三种风险视角，再给出最终建议；不要直接跳到结论。\n\n" +
      "输出只写最终报告，不要复制提示词规则。所有执行动作的对象必须是这只ETF的整体仓位或目标权重；" +
      "成分股、行业和宏观只能作为归因证据，不得给成分股交易指令。必须优先使用上游决策信号摘要，并把完整报告正文当作补充证据。\n\n" +
      "按以下顺序输出Markdown标题：\n" +
      "## 辩论结论\n" +
      "- 第一句直接给出最终动作、主导原因和最强风险视角。\n" +
      "- 总结激进、保守、中性三方最强证据，并说明没有采纳的观点为何被压倒。\n\n" +
      "## 行为逻辑\n" +
      "- 写出从宏观/行业/持仓证据到ETF执行的组合决策链，不要复述任一分析师原文。\n" +
      "- 第一句必须说明当前动作、当前仓位态度和核心原因。\n" +
      "- 先建立一个清晰基准情景，再写失效条件、反转条件和再平衡触发。\n\n" +
      "## 持仓建议\n" +
      "- 给出买入、增持、持有、减持或卖出之一。\n" +
      "- 包含目标仓位区间、最大初始仓位、加/减/轮动条件、止损或退出触发、再平衡规则和下一步监控。\n\n" +
      "最终结论必须可执行：有仓位、有时间窗口、有触发条件、有反证条件。" +
      getDecisionSignalSummaryInstruction(ctx) +
      getAgentOutputSchemaInstruction("portfolio_manager", ctx) +
      getLanguageInstruction(ctx)
    );
  }
  return (
    "As the Portfolio Manager, synthesize the full risk debate and deliver " +
    "the final ETF portfolio allocation decision.\n\n" +
    "Your response must evaluate all three risk perspectives before giving " +
    "a position. Do not jump straight to the final recommendation.\n" +
    "For ordinary lists, use Arabic numerals such as 1. 2. 3.; " +
    "if you use Chinese section headings, keep forms like 一、二、三.\n" +
    "Output only the finished report. Never copy, quote, or paraphrase " +
    "the writing rules or bullet instructions from this prompt into the " +
    "answer, and do not repeat a section heading once it has already " +
    "appeared.\n\n" +
    "Use this exact output order with Markdown headings:\n" +
    "## Debate Conclusion\n" +
    "- Assess which risk perspective presented the strongest case across " +
    "the full debate.\n" +
    "- Summarize the strongest points from the Aggressive Analyst, " +
    "Conservative Analyst, and Neutral Analyst.\n" +
    "- Explain the decisive weakness in the view you did not ultimately " +
    "follow, or clarify why multiple views were overruled.\n" +
    "- Start with a direct verdict sentence stating the final action for " +
    "this ETF and the dominant reason it wins.\n\n" +
    "## Action Logic\n" +
    "- Write your own ETF portfolio decision logic from evidence to " +
    "execution, not just a paraphrase of one analyst.\n" +
    "- The first sentence must state the current action now, the sizing " +
    "stance now, and the core reason now. Do not open with generic " +
    "prerequisites or abstract caveats.\n" +
    "- Build one clear base-case chain from macro / industry / holdings " +
    "evidence to ETF implementation; only after that should you mention " +
    "invalidation triggers.\n" +
    "- Make clear what would cause you to maintain, add, reduce, rotate, " +
    "hedge, or reverse ETF exposure.\n\n" +
    "## Positioning Recommendation\n" +
    "- Give a clear, actionable ETF portfolio recommendation — " +
    "Buy, Overweight, Hold, Underweight, or Sell — grounded in the " +
    "debate's strongest evidence.\n" +
    "- Include concrete execution guidance: target allocation band, " +
    "add / reduce / rotate conditions, maximum initial sizing, rebalance " +
    "triggers, risk controls, and what to monitor next.\n" +
    "- The execution object is the ETF only. You may cite constituent " +
    "names, weights, valuations, or earnings as evidence, but do not " +
    "instruct the user to clear, trim, retain, or rebalance named " +
    "constituent stocks.\n\n" +
    "Be decisive and ground every conclusion in specific evidence from " +
    "the analysts." +
    getDecisionSignalSummaryInstruction(ctx) +
    getAgentOutputSchemaInstruction("portfolio_manager", ctx) +
    getLanguageInstruction(ctx)
  );
}
