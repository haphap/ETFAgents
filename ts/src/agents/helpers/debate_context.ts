/**
 * Explicit context blocks injected into the debator / manager prompts.
 *
 * Mirrors the Python researcher / risk-debator / manager nodes, which build a
 * single prompt string that embeds the six analyst report state keys plus the
 * opposing side's debate history and latest response. The TS analysts append
 * their reports to the message history, but the debaters/managers additionally
 * receive them explicitly here so the prompt construction matches Python.
 */

import type { SpineStateType } from "../state.js";

/** The six analyst reports, labelled, skipping any that are still empty. */
export function buildReportsBlock(state: SpineStateType): string {
  const rows: Array<[string, string]> = [
    ["市场与资金流分析", state.market_flow_report],
    ["舆情与事件影响分析", state.catalyst_sentiment_report],
    ["宏观框架分析", state.macro_regime_report],
    ["中观大宗商品分析", state.meso_commodity_report],
    ["ETF持仓行业研究", state.holdings_industry_report],
    ["ETF头部持仓研究", state.top_holdings_report],
  ];
  const blocks = rows
    .filter(([, body]) => body?.trim())
    .map(([label, body]) => `### ${label}\n${body.trim()}`);
  return blocks.length ? `## 分析师报告\n\n${blocks.join("\n\n")}` : "";
}

function section(title: string, body: string): string {
  return body?.trim() ? `## ${title}\n${body.trim()}` : "";
}

function join(parts: string[]): string {
  return parts.filter(Boolean).join("\n\n");
}

/** Bull researcher sees reports + the bear's full history and latest argument. */
export function buildBullContext(state: SpineStateType): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state),
    section("对手（看空）历史", d.bearHistory),
    section("对手最新论点", d.currentBearResponse),
  ]);
}

/** Bear researcher sees reports + the bull's full history and latest argument. */
export function buildBearContext(state: SpineStateType): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state),
    section("对手（看多）历史", d.bullHistory),
    section("对手最新论点", d.currentBullResponse),
  ]);
}

/** Research manager sees reports + both sides' complete debate histories. */
export function buildResearchManagerContext(state: SpineStateType): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state),
    section("看多完整辩论历史", d.bullHistory),
    section("看空完整辩论历史", d.bearHistory),
  ]);
}

/** Risk debators see reports, the trader plan, and the other two analysts. */
export function buildRiskContext(
  state: SpineStateType,
  others: Array<[string, keyof typeof state.risk_debate_state]>,
): string {
  const d = state.risk_debate_state;
  return join([
    buildReportsBlock(state),
    section("交易员配置方案", state.trader_allocation_plan),
    ...others.map(([label, key]) => section(label, String(d[key] ?? ""))),
  ]);
}

export const buildAggressiveContext = (state: SpineStateType): string =>
  buildRiskContext(state, [
    ["保守派最新论点", "currentConservativeResponse"],
    ["中性派最新论点", "currentNeutralResponse"],
  ]);

export const buildConservativeContext = (state: SpineStateType): string =>
  buildRiskContext(state, [
    ["激进派最新论点", "currentAggressiveResponse"],
    ["中性派最新论点", "currentNeutralResponse"],
  ]);

export const buildNeutralContext = (state: SpineStateType): string =>
  buildRiskContext(state, [
    ["激进派最新论点", "currentAggressiveResponse"],
    ["保守派最新论点", "currentConservativeResponse"],
  ]);

/** Portfolio manager sees reports + the research plan + all three risk histories. */
export function buildPortfolioManagerContext(state: SpineStateType): string {
  const d = state.risk_debate_state;
  return join([
    buildReportsBlock(state),
    section("研究经理配置方案", state.research_allocation_plan),
    section("激进派历史", d.aggressiveHistory),
    section("保守派历史", d.conservativeHistory),
    section("中性派历史", d.neutralHistory),
  ]);
}
