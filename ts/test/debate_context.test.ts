import { describe, expect, it } from "vitest";
import {
  buildAggressiveContext,
  buildBearContext,
  buildBullContext,
  buildReportsBlock,
} from "../src/agents/helpers/debate_context.js";
import type { SpineStateType } from "../src/agents/state.js";
import { emptyDebateState } from "../src/agents/state.js";

function stateWith(
  investment: Partial<ReturnType<typeof emptyDebateState>>,
  risk: Partial<ReturnType<typeof emptyDebateState>> = {},
): SpineStateType {
  return {
    market_flow_report: "mf-report",
    catalyst_sentiment_report: "",
    macro_regime_report: "",
    meso_commodity_report: "",
    holdings_industry_report: "",
    top_holdings_report: "",
    trader_allocation_plan: "trader-plan",
    investment_debate_state: { ...emptyDebateState(), ...investment },
    risk_debate_state: { ...emptyDebateState(), ...risk },
  } as unknown as SpineStateType;
}

describe("debate context builders", () => {
  it("gives the bull its own complete history plus the bear's (round > 1 parity)", () => {
    const ctx = buildBullContext(
      stateWith({
        bullHistory: "BULL_R1",
        bearHistory: "BEAR_R1",
        currentBearResponse: "BEAR_NOW",
      }),
    );
    expect(ctx).toContain("我方（看多）完整历史");
    expect(ctx).toContain("BULL_R1");
    expect(ctx).toContain("BEAR_R1");
    expect(ctx).toContain("BEAR_NOW");
    expect(ctx).toContain("mf-report"); // reports still injected
  });

  it("gives the bear its own complete history plus the bull's", () => {
    const ctx = buildBearContext(stateWith({ bullHistory: "BULL_R1", bearHistory: "BEAR_R1" }));
    expect(ctx).toContain("我方（看空）完整历史");
    expect(ctx).toContain("BEAR_R1");
    expect(ctx).toContain("BULL_R1");
  });

  it("gives a risk debator its own history plus the other two histories", () => {
    const ctx = buildAggressiveContext(
      stateWith(
        {},
        {
          aggressiveHistory: "AGG_R1",
          conservativeHistory: "CON_R1",
          neutralHistory: "NEU_R1",
          currentConservativeResponse: "CON_NOW",
        },
      ),
    );
    expect(ctx).toContain("我方（激进派）完整历史");
    expect(ctx).toContain("AGG_R1");
    expect(ctx).toContain("CON_R1");
    expect(ctx).toContain("NEU_R1");
    expect(ctx).toContain("CON_NOW");
    expect(ctx).toContain("trader-plan");
  });

  it("compresses long analyst reports around the decision signal summary", () => {
    const longState = stateWith({});
    longState.market_flow_report =
      "OPENING_SIGNAL\n" +
      "MIDDLE_NOISE".repeat(1_000) +
      "\n**决策信号摘要**\n方向: 偏多\n置信度: 中\n时间窗口: 1周\nETF传导路径: 资金流 -> ETF\n核心证据: 份额增加\n最大反证条件: 放量跌破支撑\n配置含义: 增持ETF\n下一步观察: 成交量\n" +
      "CLOSING_SIGNAL";

    const ctx = buildReportsBlock(longState, { language: "Chinese", reportContextCharLimit: 800 });
    expect(ctx).toContain("优先使用每份报告中的「决策信号摘要」");
    expect(ctx).toContain("[Decision signal summary]");
    expect(ctx).toContain("方向: 偏多");
    expect(ctx).toContain("OPENING_SIGNAL");
    expect(ctx).toContain("CLOSING_SIGNAL");
  });
});
