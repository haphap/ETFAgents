import { describe, expect, it } from "vitest";
import {
  buildAggressiveContext,
  buildBearContext,
  buildBullContext,
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
});
