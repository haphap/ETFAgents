import { describe, expect, it } from "vitest";
import {
  collectTopSectionMarks,
  containsMetaOpeners,
  containsSelfReferentialMetaLeads,
  hasInvalidOpeningCap,
  postJudgeClean,
  preJudgeClean,
  stripDecisionLabelArtifacts,
  stripMetaOpeners,
  stripRefinePreamble,
  stripSelfReferentialMetaLeads,
} from "../src/agents/helpers/report_leads.js";

describe("collectTopSectionMarks", () => {
  it("extracts every Chinese top-level section mark present in the report", () => {
    const text =
      "概览段落\n\n一、市场结构\n内容\n\n二、交易确认\n更多内容\n\n三、价位推演\n\n四、综合结论";
    expect([...collectTopSectionMarks(text)].sort()).toEqual(["一", "三", "二", "四"].sort());
  });

  it("ignores section marks embedded mid-line", () => {
    expect(collectTopSectionMarks("段落中提到一、市场不算章节标题。").size).toBe(0);
  });

  it("returns empty set for empty / undefined input", () => {
    expect(collectTopSectionMarks("").size).toBe(0);
    expect(collectTopSectionMarks(undefined).size).toBe(0);
  });
});

describe("hasInvalidOpeningCap", () => {
  it("flags reports that begin with a section heading", () => {
    expect(hasInvalidOpeningCap("一、市场结构与量价诊断\n趋势同步向上。")).toBe(true);
  });

  it("flags reports that begin with a markdown table", () => {
    expect(hasInvalidOpeningCap("| 指标 | 数值 |\n| --- | --- |\n| RSI | 64 |")).toBe(true);
  });

  it("flags reports that begin with a label-only line", () => {
    expect(hasInvalidOpeningCap("结论：\n后面是论据。")).toBe(true);
    expect(hasInvalidOpeningCap("【核心结论与前置指引】")).toBe(true);
  });

  it("flags reports that begin with process narration", () => {
    expect(hasInvalidOpeningCap("数据已经全部获取完毕，现在我来撰写分析报告。")).toBe(true);
  });

  it("flags reports that begin with a meta opener", () => {
    expect(hasInvalidOpeningCap("本报告将对510300.SH进行多维度分析。")).toBe(true);
  });

  it("flags reports that begin with a self-referential lead", () => {
    expect(hasInvalidOpeningCap("本节锁定中期偏多结构的有效性。")).toBe(true);
  });

  it("accepts reports that begin with a real overview paragraph", () => {
    expect(
      hasInvalidOpeningCap("价格站稳50日均线上方，短中期均线同步向上，MACD柱状图持续扩张。"),
    ).toBe(false);
  });
});

describe("stripDecisionLabelArtifacts", () => {
  it("removes a trailing '最终配置建议: **持有**' line (the bug observed in sub-step 1)", () => {
    const text =
      "一、市场结构与量价诊断\n趋势同步向上。\n\n四、综合结论和指标总览\n偏多配置。\n\n最终配置建议: **持有**";
    const cleaned = stripDecisionLabelArtifacts(text);
    expect(cleaned).not.toContain("最终配置建议");
    expect(cleaned).toContain("一、市场结构与量价诊断");
  });

  it("removes English variants such as 'FINAL ALLOCATION PROPOSAL: **HOLD**'", () => {
    const cleaned = stripDecisionLabelArtifacts(
      "Body of the report.\n\nFINAL ALLOCATION PROPOSAL: **HOLD**",
    );
    expect(cleaned).toBe("Body of the report.");
  });

  it("removes leaked 'EXECUTION BIAS: **BUY**' artifacts", () => {
    expect(stripDecisionLabelArtifacts("Some prose.\nEXECUTION BIAS: **BUY**")).toBe("Some prose.");
  });

  it("leaves real prose containing the rating words intact", () => {
    const text = "若价格跌破200日均线则建议减仓至2成，止损设在3.540元下方。";
    expect(stripDecisionLabelArtifacts(text)).toBe(text);
  });
});

describe("stripRefinePreamble", () => {
  it("removes 以下是根据评审标准修正后的完整报告：style preambles", () => {
    const cleaned = stripRefinePreamble(
      "以下是根据评审标准修正后的完整分析报告：\n\n一、市场结构\n内容。",
    );
    expect(cleaned.startsWith("一、市场结构")).toBe(true);
  });

  it("strips '直接进入正文' / 'Start directly with your body' instruction leaks", () => {
    expect(stripRefinePreamble("直接进入正文\n\n一、章节")).toBe("一、章节");
    expect(stripRefinePreamble("Start directly with your body.\n\nBody.")).toBe("Body.");
  });
});

describe("stripMetaOpeners + containsMetaOpeners", () => {
  it("detects and removes 本报告将... openers", () => {
    const text = "本报告将分析510300.SH。\n\n实际正文。";
    expect(containsMetaOpeners(text)).toBe(true);
    expect(stripMetaOpeners(text)).toBe("实际正文。");
  });

  it("detects and removes 'This report provides...' English variants", () => {
    const text = "This report provides a deep dive into 510300.SH.\n\nActual body.";
    expect(containsMetaOpeners(text)).toBe(true);
    const cleaned = stripMetaOpeners(text);
    expect(cleaned).toBe("Actual body.");
  });

  it("is idempotent — repeated calls yield the same result", () => {
    const text = "本报告将分析。\n\n实际正文。";
    expect(containsMetaOpeners(text)).toBe(true);
    expect(containsMetaOpeners(text)).toBe(true); // global-regex lastIndex must NOT carry over
  });
});

describe("stripSelfReferentialMetaLeads + contains*", () => {
  it("removes 本节锁定 / 本部分讨论 etc.", () => {
    const text = "本节锁定偏多结构。\n\n实际分析。";
    expect(containsSelfReferentialMetaLeads(text)).toBe(true);
    const cleaned = stripSelfReferentialMetaLeads(text);
    expect(cleaned).toBe("实际分析。");
  });
});

describe("preJudgeClean (orchestrator)", () => {
  it("removes refine preamble + decision label + meta opener in one pass", () => {
    const text =
      "以下是根据评审标准修正后的完整报告：\n\n本报告将围绕510300.SH。\n\n一、市场结构\n趋势向上。\n\n最终配置建议: **持有**";
    const cleaned = preJudgeClean(text);
    expect(cleaned.startsWith("一、市场结构")).toBe(true);
    expect(cleaned).not.toContain("以下是根据");
    expect(cleaned).not.toContain("本报告将");
    expect(cleaned).not.toContain("最终配置建议");
  });

  it("is idempotent on already-clean reports", () => {
    const text = "概览段。\n\n一、市场结构\n趋势向上。";
    expect(preJudgeClean(text)).toBe(text);
    expect(preJudgeClean(preJudgeClean(text))).toBe(text);
  });
});

describe("postJudgeClean", () => {
  it("runs preJudgeClean then normalizes Chinese role terms", () => {
    const text = "概览段。\n\n一、市场结构\n熊派分析师认为趋势转弱。\n\n执行倾向: **持有**";
    const cleaned = postJudgeClean(text);
    expect(cleaned).not.toContain("熊派");
    expect(cleaned).toContain("空头");
    expect(cleaned).not.toContain("执行倾向: **持有**");
  });
});
