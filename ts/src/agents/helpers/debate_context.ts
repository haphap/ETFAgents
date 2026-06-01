/**
 * Explicit context blocks injected into the debator / manager prompts.
 *
 * Mirrors the Python researcher / risk-debator / manager nodes, which build a
 * single prompt string that embeds the six analyst report state keys plus the
 * opposing side's debate history and latest response. The TS analysts append
 * their reports to the message history, but the debaters/managers additionally
 * receive them explicitly here so the prompt construction matches Python.
 */

import type { DebateState, SpineStateType } from "../state.js";

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

/** Bull researcher sees reports + own history + the bear's full history and latest argument. */
export function buildBullContext(state: SpineStateType): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state),
    section("我方（看多）完整历史", d.bullHistory),
    section("对手（看空）完整历史", d.bearHistory),
    section("对手最新论点", d.currentBearResponse),
  ]);
}

/** Bear researcher sees reports + own history + the bull's full history and latest argument. */
export function buildBearContext(state: SpineStateType): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state),
    section("我方（看空）完整历史", d.bearHistory),
    section("对手（看多）完整历史", d.bullHistory),
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

/**
 * Risk debators see reports, the trader plan, their own complete history, and
 * the other two analysts' complete histories + latest responses — mirroring
 * the Python aggressive/conservative/neutral prompts so multi-round runs keep
 * each speaker's prior-round position in context.
 */
type RiskRole = "Aggressive" | "Conservative" | "Neutral";

const RISK_META: Record<
  RiskRole,
  { label: string; history: keyof DebateState; response: keyof DebateState }
> = {
  Aggressive: {
    label: "激进派",
    history: "aggressiveHistory",
    response: "currentAggressiveResponse",
  },
  Conservative: {
    label: "保守派",
    history: "conservativeHistory",
    response: "currentConservativeResponse",
  },
  Neutral: { label: "中性派", history: "neutralHistory", response: "currentNeutralResponse" },
};

export function buildRiskContext(state: SpineStateType, speaker: RiskRole): string {
  const d = state.risk_debate_state;
  const own = RISK_META[speaker];
  const others = (Object.keys(RISK_META) as RiskRole[]).filter((r) => r !== speaker);
  return join([
    buildReportsBlock(state),
    section("交易员配置方案", state.trader_allocation_plan),
    section(`我方（${own.label}）完整历史`, String(d[own.history] ?? "")),
    ...others.flatMap((r) => [
      section(`${RISK_META[r].label}完整历史`, String(d[RISK_META[r].history] ?? "")),
      section(`${RISK_META[r].label}最新论点`, String(d[RISK_META[r].response] ?? "")),
    ]),
  ]);
}

export const buildAggressiveContext = (state: SpineStateType): string =>
  buildRiskContext(state, "Aggressive");

export const buildConservativeContext = (state: SpineStateType): string =>
  buildRiskContext(state, "Conservative");

export const buildNeutralContext = (state: SpineStateType): string =>
  buildRiskContext(state, "Neutral");

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
