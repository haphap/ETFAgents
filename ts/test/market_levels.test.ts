import { describe, expect, it } from "vitest";
import {
  extractMarketLevelAnchors,
  inlineContextualMarketLevels,
} from "../src/agents/helpers/market_levels.js";

const MARKET_REPORT_SAMPLE =
  "概览段：偏多结构成立。\n\n" +
  "一、市场结构与量价诊断\n" +
  "10日均线 3.617 元、20日均线 3.639 元、50日均线 3.579 元、200日均线 3.537 元。\n" +
  "布林中轨 3.639 元，布林上轨 3.698 元，布林下轨 3.581 元。\n" +
  "VWMA 3.638 元在价格上方，前低 3.510 元尚未触及。\n";

describe("extractMarketLevelAnchors", () => {
  it("captures Chinese label-then-value anchors with proper joining", () => {
    // Limit big enough to also include 布林中轨 after the four 均线 anchors.
    const anchors = extractMarketLevelAnchors(MARKET_REPORT_SAMPLE, 8);
    expect(anchors.length).toBeGreaterThanOrEqual(2);
    expect(anchors.some((a) => a.includes("50日均线") && a.includes("3.579"))).toBe(true);
    expect(anchors.some((a) => a.includes("布林中轨") && a.includes("3.639"))).toBe(true);
  });

  it("respects the limit parameter", () => {
    expect(extractMarketLevelAnchors(MARKET_REPORT_SAMPLE, 1)).toHaveLength(1);
    expect(extractMarketLevelAnchors(MARKET_REPORT_SAMPLE, 2)).toHaveLength(2);
  });

  it("returns empty for missing / non-anchored text", () => {
    expect(extractMarketLevelAnchors("", 3)).toEqual([]);
    expect(extractMarketLevelAnchors("纯文字段，没有数值", 3)).toEqual([]);
    expect(extractMarketLevelAnchors(undefined, 3)).toEqual([]);
  });
});

describe("inlineContextualMarketLevels", () => {
  it("replaces generic placeholder phrases with the prioritized anchor", () => {
    const trader = "若回踩市场分析中给出的首个关键阻力/支撑转换位不破，则可加仓。";
    const out = inlineContextualMarketLevels(trader, MARKET_REPORT_SAMPLE, "Chinese");
    // Generic placeholder should be replaced by the highest-priority anchor (50日均线 3.579 元)
    expect(out).not.toContain("市场分析中给出的首个关键阻力/支撑转换位");
    expect(out).toContain("50日均线");
    expect(out).toContain("3.579");
  });

  it("replaces bare labels with label+value when followed by non-digit content", () => {
    const trader = "跌破50日均线后先减仓 50%。";
    const out = inlineContextualMarketLevels(trader, MARKET_REPORT_SAMPLE, "Chinese");
    // Bare "50日均线" gets replaced with the anchor "50日均线3.579 元".
    // (No space between label and value because label contains CJK — mirrors Python behavior.)
    expect(out).toContain("50日均线3.579");
    expect(out).toContain("先减仓 50%");
  });

  it("does not double-replace a label that is already followed by a number", () => {
    const trader = "支撑参考 50日均线 3.50 元，止损 3.40 元下方。";
    const out = inlineContextualMarketLevels(trader, MARKET_REPORT_SAMPLE, "Chinese");
    // "50日均线 3.50 元" already has a number after the label → not replaced
    expect(out).toContain("50日均线 3.50 元");
    expect(out).not.toContain("50日均线 3.579 元 3.50");
  });

  it("falls back to '主支撑位或50日均线' substitution when configured", () => {
    const trader = "回踩主支撑位或50日均线不破则可加仓。";
    const out = inlineContextualMarketLevels(trader, MARKET_REPORT_SAMPLE, "Chinese");
    expect(out).not.toContain("主支撑位或50日均线");
    // Should now include at least one concrete anchor with a number
    expect(out).toMatch(/3\.\d+/);
  });

  it("is a no-op when context_text is empty or language is English", () => {
    const trader = "市场分析中给出的首个关键阻力/支撑转换位";
    expect(inlineContextualMarketLevels(trader, "", "Chinese")).toBe(trader);
    expect(inlineContextualMarketLevels(trader, MARKET_REPORT_SAMPLE, "English")).toBe(trader);
    expect(inlineContextualMarketLevels(trader, undefined, "Chinese")).toBe(trader);
  });

  it("returns empty / undefined for empty input", () => {
    expect(inlineContextualMarketLevels("", MARKET_REPORT_SAMPLE, "Chinese")).toBe("");
    expect(inlineContextualMarketLevels(undefined, MARKET_REPORT_SAMPLE, "Chinese")).toBe("");
  });
});
