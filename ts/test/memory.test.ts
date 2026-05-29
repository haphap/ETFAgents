/**
 * Unit tests for memory prompt injection (sub-step 2.7).
 */

import { describe, expect, it } from "vitest";
import {
  buildMemoryPromptSection,
  injectMemoryPromptSection,
  type MemoryRoleConfig,
} from "../src/agents/helpers/memory.js";
import type { SpineStateType } from "../src/agents/state.js";

function makeState(overrides: Partial<SpineStateType> = {}): SpineStateType {
  return {
    messages: [],
    asset_of_interest: "510300.SH",
    trade_date: "2024-06-01",
    market_flow_report: "",
    catalyst_sentiment_report: "",
    macro_regime_report: "",
    meso_commodity_report: "",
    holdings_industry_report: "",
    top_holdings_report: "",
    research_allocation_plan: "",
    trader_allocation_plan: "",
    trader_backtest_signal: {},
    sender: "",
    continuity_context: {},
    lesson_context: {},
    method_context: {},
    ...overrides,
  } as unknown as SpineStateType;
}

describe("buildMemoryPromptSection", () => {
  const role: MemoryRoleConfig = { role: "trader" };

  it("returns empty when no memory context exists", () => {
    const state = makeState();
    expect(buildMemoryPromptSection(state, role, "Chinese")).toBe("");
  });

  it("returns empty for English with no context", () => {
    const state = makeState();
    expect(buildMemoryPromptSection(state, role, "English")).toBe("");
  });

  it("builds section with continuity context", () => {
    const state = makeState({
      continuity_context: { trader: "上次分析：偏多结构成立" },
    });
    const section = buildMemoryPromptSection(state, role, "Chinese");
    expect(section).toContain("偏多结构成立");
    expect(section).toContain("仅供内部吸收");
  });

  it("builds section with lesson context", () => {
    const state = makeState({
      lesson_context: { trader: "历史复盘：支撑位判断准确" },
    });
    const section = buildMemoryPromptSection(state, role, "Chinese");
    expect(section).toContain("支撑位判断准确");
  });

  it("builds combined section with all contexts", () => {
    const state = makeState({
      continuity_context: { trader: "continuity text" },
      lesson_context: { trader: "lesson text" },
      method_context: { trader: "method text" },
    });
    const section = buildMemoryPromptSection(state, role, "English");
    expect(section).toContain("continuity text");
    expect(section).toContain("lesson text");
    expect(section).toContain("method text");
    expect(section).toContain("do not quote verbatim");
  });

  it("falls back to aliases when primary role not found", () => {
    const state = makeState({
      continuity_context: { etf_market_analyst: "market flow memory" },
    });
    const section = buildMemoryPromptSection(
      state,
      { role: "nonexistent", aliases: ["etf_market_analyst"] },
      "Chinese",
    );
    expect(section).toContain("market flow memory");
  });
});

describe("injectMemoryPromptSection", () => {
  it("returns system message unchanged when memory is empty", () => {
    expect(injectMemoryPromptSection("system msg", "")).toBe("system msg");
  });

  it("prepends memory section before system message", () => {
    const result = injectMemoryPromptSection("system msg", "memory content");
    expect(result.startsWith("memory content")).toBe(true);
    expect(result.includes("system msg")).toBe(true);
  });
});
