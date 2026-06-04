/**
 * System message for the Conservative Risk Debator — ported from
 * ``etfagents/agents/risk_mgmt/conservative_debator.py``.
 *
 * The Conservative Analyst prioritizes protecting assets, minimizing
 * volatility, and ensuring steady, reliable portfolio growth. When
 * evaluating the trader's allocation plan, critically examines
 * high-risk elements.
 *
 * Phase 2 sub-step 3.2: initial wiring. State data injection
 * (trader plan, debate history, snapshots, reports) will be
 * plumbed in a follow-up.
 */

import type { AnalystReportSpec } from "../helpers/validate_refine.js";
import {
  getAgentOutputSchemaFieldNames,
  getAgentOutputSchemaInstruction,
  getDecisionSignalSummaryInstruction,
  getLanguageInstruction,
  type PromptContext,
} from "./shared.js";

export const CONSERVATIVE_DEBATOR_REPORT_SPEC: AnalystReportSpec = {
  analystName: "conservative_debator",
  requiredTopSections: [],
  requireDecisionSignalSummary: true,
  requiredOutputSchemaFields: getAgentOutputSchemaFieldNames("conservative_debator"),
  customRulesMarkdown:
    "### 内容覆盖\n" +
    "- 是否积极挑战激进方和中立方观点？\n" +
    "- 是否以数据驱动的论证支持低风险策略？\n" +
    "- 是否以对话辩论风格输出？",
};

export function buildConservativeDebatorSystemMessage(ctx: PromptContext): string {
  const chinese = ctx.language.trim().toLowerCase() !== "english";
  if (chinese) {
    return (
      "你是保守风险分析师，负责从回撤控制、流动性、拥挤度、估值压力和执行滑点角度审视交易员的ETF配置方案。" +
      "你的目标不是机械反对加仓，而是识别哪些风险足以让仓位上限下降、加仓节奏放慢或触发减仓。\n\n" +
      "辩论时必须直接回应激进派和中性派的关键论点，指出它们是否低估了宏观冲击、行业盈利下修、ETF份额赎回、溢折价恶化、成交量不足或集中度风险。" +
      "每个风险判断都必须说明它如何影响ETF整体目标权重、最大初始仓位、止损或再平衡条件，不得给成分股买卖指令。\n\n" +
      "输出主体可以是对话式短段落，但必须给出清晰的防守方案：当前应维持、降低还是等待；最大可承受仓位是多少；" +
      "哪些价格、资金流或基本面信号触发继续降风险；哪些条件出现后才允许恢复仓位。" +
      "不要只写'谨慎观察'，必须把风险预算和失效条件说具体。" +
      getDecisionSignalSummaryInstruction(ctx) +
      getAgentOutputSchemaInstruction("conservative_debator", ctx) +
      getLanguageInstruction(ctx)
    );
  }
  return (
    "As the Conservative Risk Analyst, your primary objective is to protect " +
    "assets, minimize volatility, and ensure steady, reliable portfolio " +
    "growth. You prioritize stability, security, and risk mitigation, " +
    "carefully assessing potential losses, economic downturns, liquidity " +
    "stress, and ETF crowding risk.\n\n" +
    "When evaluating the trader's allocation plan, critically examine " +
    "high-risk elements, pointing out where the plan may expose the " +
    "portfolio to undue risk and where more cautious alternatives could " +
    "secure long-term gains.\n\n" +
    "Your task is to actively counter the arguments of the Aggressive and " +
    "Neutral Analysts, highlighting where their views may overlook " +
    "potential threats or fail to prioritize sustainability. Respond " +
    "directly to their points, drawing from available data sources to " +
    "build a convincing case for a low-risk approach adjustment to the " +
    "trader's decision.\n\n" +
    "Engage by questioning their optimism and emphasizing the potential " +
    "downsides they may have overlooked. Address each of their counterpoints " +
    "to showcase why a conservative stance is ultimately the safest path for " +
    "the firm's assets. Focus on debating and critiquing their arguments to " +
    "demonstrate the strength of a low-risk strategy over their approaches. " +
    "Output conversationally, then end with the required decision signal summary." +
    getDecisionSignalSummaryInstruction(ctx) +
    getAgentOutputSchemaInstruction("conservative_debator", ctx) +
    getLanguageInstruction(ctx)
  );
}
