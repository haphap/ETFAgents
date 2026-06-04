import type { BaseMessage } from "@langchain/core/messages";
import { AIMessage } from "@langchain/core/messages";
import { describe, expect, it } from "vitest";
import {
  type AnalystReportSpec,
  parseJudgeJson,
  staticValidate,
  staticVerdictHasIssues,
  validateAndRefine,
} from "../src/agents/helpers/validate_refine.js";

const MARKET_FLOW_SPEC: AnalystReportSpec = {
  analystName: "market_flow",
  requiredTopSections: ["一", "二", "三", "四"],
  requiredIndicatorTokens: ["MACD", "RSI"],
  requiredTailTokens: ["综合结论和指标总览"],
  requireTailTable: true,
};

const SUMMARY_REQUIRED_SPEC: AnalystReportSpec = {
  analystName: "summary_required",
  requireDecisionSignalSummary: true,
};

const DECISION_SUMMARY =
  "\n\n**决策信号摘要**\n" +
  "方向: 偏多\n" +
  "置信度: 中\n" +
  "时间窗口: 1周\n" +
  "ETF传导路径: 资金流改善 -> ETF价格支撑\n" +
  "核心证据: MACD改善；份额净申购\n" +
  "最大反证条件: 放量跌破支撑\n" +
  "配置含义: 增持ETF整体仓位\n" +
  "下一步观察: 成交量和份额变化";

const COMPLETE_REPORT =
  "概览段：偏多结构成立，MACD与RSI同步确认。\n\n" +
  "一、市场结构与量价诊断\n" +
  "趋势同步向上，MACD柱状图扩张。\n\n" +
  "二、交易确认与执行计划\n" +
  "回踩支撑加仓为主。\n\n" +
  "三、关键价位与条件情景推演\n" +
  "支撑3.58元一带，跌破即转弱。\n\n" +
  "四、综合结论和指标总览\n" +
  "偏多配置。\n\n" +
  "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n" +
  "| --- | --- | --- | --- | --- |\n" +
  "| MACD | 0.05 | 零轴上方 | 动能增强 | 死叉则衰减 |\n" +
  "| RSI | 64 | 中性偏强 | 接近超买 | 上穿70警惕 |";

describe("staticValidate", () => {
  it("passes a complete report against the market_flow spec", () => {
    const verdict = staticValidate(COMPLETE_REPORT, MARKET_FLOW_SPEC);
    expect(staticVerdictHasIssues(verdict)).toBe(false);
  });

  it("flags missing top-level sections", () => {
    const broken = COMPLETE_REPORT.replace("二、交易确认与执行计划", "二2、交易确认与执行计划");
    const verdict = staticValidate(broken, MARKET_FLOW_SPEC);
    expect(verdict.missingElements.some((m) => m.includes("二"))).toBe(true);
  });

  it("flags missing indicator tokens", () => {
    const noMacd = COMPLETE_REPORT.replace(/MACD/g, "动量");
    const verdict = staticValidate(noMacd, MARKET_FLOW_SPEC);
    expect(verdict.missingElements.some((m) => m.includes("MACD"))).toBe(true);
  });

  it("flags missing tail markdown table", () => {
    const noTable = COMPLETE_REPORT.replace(/\| --- \| --- \| --- \| --- \| --- \|\n/, "");
    const verdict = staticValidate(noTable, MARKET_FLOW_SPEC);
    expect(verdict.missingElements.some((m) => m.includes("Markdown 表格"))).toBe(true);
  });

  it("flags an opening that jumps straight into a heading", () => {
    const headingFirst = `一、市场结构\n趋势向上。${COMPLETE_REPORT.slice(COMPLETE_REPORT.indexOf("\n二、"))}`;
    const verdict = staticValidate(headingFirst, MARKET_FLOW_SPEC);
    expect(verdict.criticalIssues.some((i) => i.includes("开篇概述帽段"))).toBe(true);
  });

  it("flags markdown ## headings (should be Chinese numbering)", () => {
    const withH2 = `## Section One\n\n${COMPLETE_REPORT}`;
    const verdict = staticValidate(withH2, MARKET_FLOW_SPEC);
    expect(verdict.criticalIssues.some((i) => i.includes("##"))).toBe(true);
  });

  it("flags self-referential meta leads", () => {
    const withMeta = `本节锁定偏多结构。\n\n${COMPLETE_REPORT}`;
    const verdict = staticValidate(withMeta, MARKET_FLOW_SPEC);
    expect(verdict.criticalIssues.some((i) => i.includes("自指式元叙述"))).toBe(true);
  });

  it("enforces the decision signal summary when the spec requires it", () => {
    const verdict = staticValidate("概览段。\n\n一、正文\n内容。", SUMMARY_REQUIRED_SPEC);
    expect(verdict.missingElements).toContain("缺少末尾『决策信号摘要』");

    const complete = staticValidate(
      `概览段。\n\n一、正文\n内容。${DECISION_SUMMARY}`,
      SUMMARY_REQUIRED_SPEC,
    );
    expect(staticVerdictHasIssues(complete)).toBe(false);
  });

  it("flags missing fields inside the decision signal summary", () => {
    const verdict = staticValidate(
      "概览段。\n\n**决策信号摘要**\n方向: 中性",
      SUMMARY_REQUIRED_SPEC,
    );
    expect(verdict.missingElements.some((m) => m.includes("置信度"))).toBe(true);
    expect(verdict.missingElements.some((m) => m.includes("最大反证条件"))).toBe(true);
  });
});

describe("parseJudgeJson", () => {
  it("parses a clean JSON object response", () => {
    const text = JSON.stringify({
      score: 8,
      passed: true,
      critical_issues: [],
      minor_issues: ["minor"],
      missing_elements: [],
      general_comment: "ok",
    });
    const verdict = parseJudgeJson(text);
    expect(verdict?.score).toBe(8);
    expect(verdict?.passed).toBe(true);
    expect(verdict?.minor_issues).toEqual(["minor"]);
  });

  it("recovers a JSON object embedded in surrounding text", () => {
    const text =
      "Here is my analysis:\n```\n" +
      JSON.stringify({ score: 5, passed: false, critical_issues: ["x"] }) +
      "\n```\nThanks.";
    const verdict = parseJudgeJson(text);
    expect(verdict?.score).toBe(5);
    expect(verdict?.passed).toBe(false);
    expect(verdict?.critical_issues).toEqual(["x"]);
  });

  it("normalises legacy 'pass' key to 'passed'", () => {
    const text = '{"score": 9, "pass": true}';
    const verdict = parseJudgeJson(text);
    expect(verdict?.passed).toBe(true);
  });

  it("returns null when no JSON object with score is present", () => {
    expect(parseJudgeJson("just prose, no json")).toBeNull();
    expect(parseJudgeJson("{}")).toBeNull();
    expect(parseJudgeJson(undefined)).toBeNull();
  });
});

class StubLlm {
  invokeCount = 0;
  responses: string[];
  constructor(responses: string[]) {
    this.responses = [...responses];
  }
  async invoke(_input: unknown): Promise<AIMessage> {
    this.invokeCount += 1;
    const next = this.responses.shift() ?? "";
    return new AIMessage(next);
  }
  // unused — surface only so the cast in validate_refine compiles
  bindTools(_tools: unknown): StubLlm {
    return this;
  }
}

describe("validateAndRefine", () => {
  it("passes the report through unchanged when the LLM judge says passed=true", async () => {
    const llm = new StubLlm([
      JSON.stringify({ score: 9, passed: true, critical_issues: [], missing_elements: [] }),
    ]);
    const result = await validateAndRefine(
      COMPLETE_REPORT,
      llm as unknown as Parameters<typeof validateAndRefine>[1],
      MARKET_FLOW_SPEC,
    );
    expect(result).toBe(COMPLETE_REPORT);
    expect(llm.invokeCount).toBe(1);
  });

  it("invokes refine when the verdict reports critical_issues", async () => {
    const llm = new StubLlm([
      JSON.stringify({
        score: 4,
        passed: false,
        critical_issues: ["缺少四级章节"],
        missing_elements: [],
        general_comment: "needs work",
      }),
      "REFINED REPORT TEXT",
    ]);
    const result = await validateAndRefine(
      "概览段。\n\n一、市场结构\n内容。",
      llm as unknown as Parameters<typeof validateAndRefine>[1],
      MARKET_FLOW_SPEC,
    );
    expect(result).toBe("REFINED REPORT TEXT");
    expect(llm.invokeCount).toBe(2);
  });

  it("static_only mode skips the LLM judge entirely", async () => {
    const llm = new StubLlm([]);
    const result = await validateAndRefine(
      COMPLETE_REPORT,
      llm as unknown as Parameters<typeof validateAndRefine>[1],
      MARKET_FLOW_SPEC,
      { validationMode: "static_only" },
    );
    expect(result).toBe(COMPLETE_REPORT);
    expect(llm.invokeCount).toBe(0);
  });

  it("disabled mode short-circuits without invoking the LLM", async () => {
    const llm = new StubLlm([]);
    const result = await validateAndRefine(
      "broken report",
      llm as unknown as Parameters<typeof validateAndRefine>[1],
      MARKET_FLOW_SPEC,
      { validationMode: "disabled" },
    );
    expect(result).toBe("broken report");
    expect(llm.invokeCount).toBe(0);
  });

  it("preserves the data-unavailable marker without judging", async () => {
    const llm = new StubLlm([]);
    const marker = "[tool-recovery:data-unavailable]\nVendor down.";
    const result = await validateAndRefine(
      marker,
      llm as unknown as Parameters<typeof validateAndRefine>[1],
      MARKET_FLOW_SPEC,
    );
    expect(result).toBe(marker);
    expect(llm.invokeCount).toBe(0);
  });
});

// Suppress unused-import lint warnings — BaseMessage is referenced by the
// signature exposed via the `as unknown as` cast above.
void ({} as BaseMessage);
