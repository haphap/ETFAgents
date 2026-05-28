import { describe, expect, it } from "vitest";
import {
  looksLikeCompleteMarketFlowReport,
  normalizeMarketFlowTailSections,
} from "../src/agents/helpers/market_flow_normalize.js";

const COMPLETE_TAIL_TABLE =
  "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n" +
  "| --- | --- | --- | --- | --- |\n" +
  "| MACD | 0.05 | 零轴上方 | 动能增强 | 死叉则衰减 |";

const COMPLETE_REPORT =
  "概览段：偏多结构成立，量价同步确认。\n\n" +
  "一、市场结构与量价诊断\n趋势同步向上。\n\n" +
  "二、交易确认与执行计划\n回踩加仓为主。\n\n" +
  "三、关键价位与条件情景推演\n支撑 3.58 一带。\n\n" +
  "四、综合结论和指标总览\n\n偏多配置，目标 3.65。\n\n" +
  COMPLETE_TAIL_TABLE;

describe("looksLikeCompleteMarketFlowReport", () => {
  it("accepts a complete report with three numbered sections + table", () => {
    expect(looksLikeCompleteMarketFlowReport(COMPLETE_REPORT)).toBe(true);
  });

  it("rejects empty / undefined", () => {
    expect(looksLikeCompleteMarketFlowReport("")).toBe(false);
    expect(looksLikeCompleteMarketFlowReport(undefined)).toBe(false);
  });

  it("rejects reports starting with a heading (invalid opening cap)", () => {
    const headingFirst = COMPLETE_REPORT.split("\n").slice(2).join("\n");
    expect(looksLikeCompleteMarketFlowReport(headingFirst)).toBe(false);
  });

  it("rejects reports starting with process narration", () => {
    const processFirst = `数据已经全部获取完毕，下面开始撰写完整的分析报告。\n\n${COMPLETE_REPORT}`;
    expect(looksLikeCompleteMarketFlowReport(processFirst)).toBe(false);
  });

  it("rejects when section 二 is missing", () => {
    const noTwo = COMPLETE_REPORT.replace("二、交易确认与执行计划", "二2、交易确认与执行计划");
    expect(looksLikeCompleteMarketFlowReport(noTwo)).toBe(false);
  });

  it("rejects when no markdown table separator is present anywhere", () => {
    const noTable = COMPLETE_REPORT.replace("| --- | --- | --- | --- | --- |", "");
    expect(looksLikeCompleteMarketFlowReport(noTable)).toBe(false);
  });
});

describe("normalizeMarketFlowTailSections", () => {
  it("is idempotent when the report already uses the canonical layout", () => {
    const out = normalizeMarketFlowTailSections(COMPLETE_REPORT);
    expect(out).toContain("四、综合结论和指标总览\n\n偏多配置，目标 3.65。");
    expect(out).toContain(COMPLETE_TAIL_TABLE);
    // Run twice — output must not change.
    expect(normalizeMarketFlowTailSections(out)).toBe(out);
  });

  it("layout (a): 综合结论段落 + 指标总览 heading + table → merged canonical", () => {
    const legacy =
      "概览段：偏多。\n\n一、…\n二、…\n三、…\n\n" +
      "四、综合结论和指标总览\n\n偏多配置，目标 3.65。\n\n" +
      "指标总览\n\n" +
      COMPLETE_TAIL_TABLE;
    const out = normalizeMarketFlowTailSections(legacy);
    expect(out).not.toContain("\n指标总览\n");
    expect(out).toMatch(/四、综合结论和指标总览\s+偏多配置，目标 3\.65/);
    expect(out).toContain(COMPLETE_TAIL_TABLE);
  });

  it("layout (b): table + standalone 综合结论 heading + paragraph → merged", () => {
    const legacy =
      "概览段：偏多。\n\n一、…\n二、…\n三、…\n\n" +
      "四、指标总览\n\n" +
      COMPLETE_TAIL_TABLE +
      "\n\n综合结论\n\n偏多配置，目标 3.65。";
    const out = normalizeMarketFlowTailSections(legacy);
    expect(out).toContain("四、综合结论和指标总览");
    expect(out).toContain("偏多配置，目标 3.65。");
    expect(out).not.toContain("\n综合结论\n\n偏多配置");
    // Table must still be present
    expect(out).toContain(COMPLETE_TAIL_TABLE);
  });

  it("layout (c): table + inline 综合结论：… label → promoted to canonical heading", () => {
    const legacy =
      "概览段：偏多。\n\n一、…\n二、…\n三、…\n\n" +
      COMPLETE_TAIL_TABLE +
      "\n\n综合结论：偏多配置，目标 3.65。";
    const out = normalizeMarketFlowTailSections(legacy);
    expect(out).toContain("四、综合结论和指标总览");
    expect(out).toContain("偏多配置，目标 3.65。");
    expect(out).not.toMatch(/^\s*综合结论：/m);
  });

  it("no-table case: inline 综合结论：… label is still promoted", () => {
    const noTable = "概览段。\n\n一、…\n\n综合结论：偏多配置。";
    const out = normalizeMarketFlowTailSections(noTable);
    expect(out).toContain("四、综合结论和指标总览");
    expect(out).toContain("偏多配置。");
    expect(out).not.toMatch(/综合结论：/);
  });

  it("strips a duplicate combined-tail heading appearing later in the document", () => {
    const dup =
      COMPLETE_REPORT +
      "\n\n四、综合结论和指标总览\n这是后续重复的章节，应被剥离。\n\n" +
      COMPLETE_TAIL_TABLE;
    const out = normalizeMarketFlowTailSections(dup);
    // First combined-tail heading kept
    const firstIdx = out.indexOf("四、综合结论和指标总览");
    expect(firstIdx).toBeGreaterThanOrEqual(0);
    // No second occurrence after that
    expect(out.indexOf("四、综合结论和指标总览", firstIdx + 1)).toBe(-1);
    expect(out).not.toContain("这是后续重复的章节");
  });

  it("returns empty string for empty / undefined", () => {
    expect(normalizeMarketFlowTailSections("")).toBe("");
    expect(normalizeMarketFlowTailSections(undefined)).toBe("");
  });
});
