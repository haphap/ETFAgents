import { AIMessage } from "@langchain/core/messages";
import { describe, expect, it } from "vitest";
import { buildMemoryPayload, createMemoryWriterNode } from "../src/agents/nodes/memory_writer.js";
import type { SpineStateType } from "../src/agents/state.js";
import { emptyDebateState } from "../src/agents/state.js";

function fakeState(overrides: Partial<SpineStateType> = {}): SpineStateType {
  return {
    messages: [new AIMessage("x")],
    asset_of_interest: "510300.SH",
    trade_date: "2026-05-29",
    market_flow_report: "mf",
    catalyst_sentiment_report: "cs",
    macro_regime_report: "mr",
    meso_commodity_report: "mc",
    holdings_industry_report: "hi",
    top_holdings_report: "th",
    research_allocation_plan: "rap",
    trader_allocation_plan: "tap",
    trader_backtest_signal: { rating: "Overweight" },
    final_allocation_decision: "fad",
    investment_debate_state: {
      ...emptyDebateState(),
      currentBullResponse: "Bull: up",
      currentBearResponse: "Bear: down",
    },
    risk_debate_state: {
      ...emptyDebateState(),
      currentAggressiveResponse: "Aggressive: more",
      currentConservativeResponse: "Conservative: less",
      currentNeutralResponse: "Neutral: hold",
    },
    analysis_memory_entry: {},
    continuity_context: {},
    lesson_context: {},
    method_context: {},
    sender: "",
    bull_researcher_report: "",
    bear_researcher_report: "",
    aggressive_debator_response: "",
    conservative_debator_response: "",
    neutral_debator_response: "",
    ...overrides,
  } as SpineStateType;
}

describe("memory writer", () => {
  it("builds a Python-shaped snake_case payload from state", () => {
    const payload = buildMemoryPayload(fakeState());
    expect(payload.asset_of_interest).toBe("510300.SH");
    expect(payload.final_allocation_decision).toBe("fad");
    // trader_backtest_signal is intentionally omitted so build_state_backtest_signal
    // falls through to the PM's final_allocation_decision instead of the trader view.
    expect(payload).not.toHaveProperty("trader_backtest_signal");
    expect(payload.investment_debate_state).toEqual({
      current_bull_response: "Bull: up",
      current_bear_response: "Bear: down",
    });
    expect(payload.risk_debate_state).toEqual({
      current_aggressive_response: "Aggressive: more",
      current_conservative_response: "Conservative: less",
      current_neutral_response: "Neutral: hold",
    });
  });

  it("is a no-op when no persist callback is wired", async () => {
    const node = createMemoryWriterNode({});
    expect(await node(fakeState())).toEqual({});
  });

  it("records the persisted entry and swallows persistence failures", async () => {
    const ok = createMemoryWriterNode({
      persist: async () => ({ id: "run-1", ticker: "510300.SH" }),
    });
    expect(await ok(fakeState())).toEqual({
      analysis_memory_entry: { id: "run-1", ticker: "510300.SH" },
    });

    const boom = createMemoryWriterNode({
      persist: async () => {
        throw new Error("bridge down");
      },
    });
    expect(await boom(fakeState())).toEqual({});
  });

  it("forwards the runtime config to the persist callback", async () => {
    let captured: Record<string, unknown> | undefined;
    const node = createMemoryWriterNode({
      persist: async (payload) => {
        captured = payload;
        return {};
      },
      config: { memory_mode: "disabled", results_dir: "/tmp/custom" },
    });
    await node(fakeState());
    expect(captured?.config).toEqual({ memory_mode: "disabled", results_dir: "/tmp/custom" });
  });
});
