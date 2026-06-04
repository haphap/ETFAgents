/**
 * Explicit context blocks injected into the debator / manager prompts.
 *
 * Mirrors the Python researcher / risk-debator / manager nodes, which build a
 * single prompt string that embeds the six analyst report state keys plus the
 * opposing side's debate history and latest response. The TS analysts append
 * their reports to the message history, but the debaters/managers additionally
 * receive them explicitly here so the prompt construction matches Python.
 *
 * Scope: this is *history* parity, not *snapshot* parity. Each speaker gets the
 * full own + opponent histories and latest responses (the substantive content),
 * but Python's per-round feedback snapshots, snapshot file paths, rolling debate
 * brief, and manager-side side-report synthesis are intentionally NOT ported —
 * that compression layer is a separate follow-up. At maxDebateRounds /
 * maxRiskRounds > 1 the model sees the same content Python compresses, just
 * uncompressed.
 */

import { type PromptContext, reportForDecisionContext } from "../prompts/shared.js";
import type { DebateState, SpineStateType } from "../state.js";
import { formatAgentSignalsForPrompt } from "./output_schema.js";

const DEBATE_REPORT_CONTEXT_LIMIT = 5_000;

/** The six analyst reports, labelled, skipping any that are still empty. */
export function buildReportsBlock(state: SpineStateType, ctx?: PromptContext): string {
  const reportContextCharLimit = Math.min(
    ctx?.reportContextCharLimit ?? DEBATE_REPORT_CONTEXT_LIMIT,
    DEBATE_REPORT_CONTEXT_LIMIT,
  );
  const promptContext: PromptContext = {
    language: ctx?.language ?? "Chinese",
    reportContextCharLimit,
    ...(ctx?.validationMode ? { validationMode: ctx.validationMode } : {}),
  };
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
    .map(
      ([label, body]) =>
        `### ${label}\n${reportForDecisionContext(body, promptContext, reportContextCharLimit)}`,
    );
  const structuredSignals = formatAgentSignalsForPrompt(state.agent_signals, {
    language: promptContext.language,
    include: [
      "market_flow",
      "catalyst_sentiment",
      "macro_regime",
      "meso_commodity",
      "holdings_industry",
      "top_holdings",
    ],
  });
  const reportBlock = blocks.length
    ? `## 分析师报告\n\n优先使用每份报告中的「决策信号摘要」；报告摘录只作为证据核对，不要把长篇正文重新复述。\n\n${blocks.join("\n\n")}`
    : "";
  return join([structuredSignals, reportBlock]);
}

function section(title: string, body: string): string {
  return body?.trim() ? `## ${title}\n${body.trim()}` : "";
}

function join(parts: string[]): string {
  return parts.filter(Boolean).join("\n\n");
}

/** Bull researcher sees reports + own history + the bear's full history and latest argument. */
export function buildBullContext(state: SpineStateType, ctx?: PromptContext): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state, ctx),
    section("我方（看多）完整历史", d.bullHistory),
    section("对手（看空）完整历史", d.bearHistory),
    section("对手最新论点", d.currentBearResponse),
  ]);
}

/** Bear researcher sees reports + own history + the bull's full history and latest argument. */
export function buildBearContext(state: SpineStateType, ctx?: PromptContext): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state, ctx),
    section("我方（看空）完整历史", d.bearHistory),
    section("对手（看多）完整历史", d.bullHistory),
    section("对手最新论点", d.currentBullResponse),
  ]);
}

/** Research manager sees reports + both sides' complete debate histories. */
export function buildResearchManagerContext(state: SpineStateType, ctx?: PromptContext): string {
  const d = state.investment_debate_state;
  return join([
    buildReportsBlock(state, ctx),
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

export function buildRiskContext(
  state: SpineStateType,
  speaker: RiskRole,
  ctx?: PromptContext,
): string {
  const d = state.risk_debate_state;
  const own = RISK_META[speaker];
  const others = (Object.keys(RISK_META) as RiskRole[]).filter((r) => r !== speaker);
  return join([
    buildReportsBlock(state, ctx),
    formatAgentSignalsForPrompt(state.agent_signals, {
      language: ctx?.language ?? "Chinese",
      include: ["research_manager", "trader"],
      title:
        ctx?.language?.trim().toLowerCase() === "english"
          ? "## Manager and Trader Structured Signals"
          : "## 研究经理与交易员结构化信号",
    }),
    section("交易员配置方案", state.trader_allocation_plan),
    section(`我方（${own.label}）完整历史`, String(d[own.history] ?? "")),
    ...others.flatMap((r) => [
      section(`${RISK_META[r].label}完整历史`, String(d[RISK_META[r].history] ?? "")),
      section(`${RISK_META[r].label}最新论点`, String(d[RISK_META[r].response] ?? "")),
    ]),
  ]);
}

export const buildAggressiveContext = (state: SpineStateType, ctx?: PromptContext): string =>
  buildRiskContext(state, "Aggressive", ctx);

export const buildConservativeContext = (state: SpineStateType, ctx?: PromptContext): string =>
  buildRiskContext(state, "Conservative", ctx);

export const buildNeutralContext = (state: SpineStateType, ctx?: PromptContext): string =>
  buildRiskContext(state, "Neutral", ctx);

/** Portfolio manager sees reports + the research plan + all three risk histories. */
export function buildPortfolioManagerContext(state: SpineStateType, ctx?: PromptContext): string {
  const d = state.risk_debate_state;
  return join([
    buildReportsBlock(state, ctx),
    formatAgentSignalsForPrompt(state.agent_signals, {
      language: ctx?.language ?? "Chinese",
      include: [
        "research_manager",
        "trader",
        "aggressive_debator",
        "conservative_debator",
        "neutral_debator",
      ],
      title:
        ctx?.language?.trim().toLowerCase() === "english"
          ? "## Downstream Structured Signals"
          : "## 下游结构化信号",
    }),
    section("研究经理配置方案", state.research_allocation_plan),
    section("激进派历史", d.aggressiveHistory),
    section("保守派历史", d.conservativeHistory),
    section("中性派历史", d.neutralHistory),
  ]);
}
