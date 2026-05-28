import { describe, expect, it } from "vitest";
import {
  CHINESE_ROLE_TERM_REPLACEMENTS,
  normalizeChineseManagerTerms,
  normalizeChineseRoleTerms,
} from "../src/agents/helpers/role_terms.js";

describe("normalizeChineseRoleTerms", () => {
  it("replaces deprecated role terms with the project's canonical wording", () => {
    expect(normalizeChineseRoleTerms("熊派分析师认为趋势转弱")).toBe("空头分析师认为趋势转弱");
    expect(normalizeChineseRoleTerms("牛派投资者偏多")).toBe("多头投资者偏多");
    expect(normalizeChineseRoleTerms("根本面分析建议")).toBe("基本面分析建议");
  });

  it("prefers the longest matching term when multiple variants overlap", () => {
    // 'ETF持仓行业研究分析师' (longer) should win over 'ETF持仓' or '行业研究分析师'.
    expect(normalizeChineseRoleTerms("ETF持仓行业研究分析师给出加仓建议")).toBe(
      "行业研究分析师给出加仓建议",
    );
  });

  it("rewrites every term in the replacement map at least once", () => {
    for (const [from, to] of CHINESE_ROLE_TERM_REPLACEMENTS) {
      expect(normalizeChineseRoleTerms(from)).toBe(to);
    }
  });

  it("returns empty string for empty / undefined", () => {
    expect(normalizeChineseRoleTerms("")).toBe("");
    expect(normalizeChineseRoleTerms(undefined)).toBe("");
  });
});

describe("normalizeChineseManagerTerms", () => {
  it("rewrites English manager-section H2 headings to Chinese", () => {
    const text =
      "## Debate Conclusion\n论据如下。\n\n## Action Logic\n推理。\n\n## Positioning Recommendation\n仓位建议。";
    const out = normalizeChineseManagerTerms(text);
    expect(out).toContain("## 辩论结论");
    expect(out).toContain("## 行为逻辑");
    expect(out).toContain("## 持仓建议");
    expect(out).not.toContain("Debate Conclusion");
  });

  it("rewrites EXECUTION BIAS / FINAL ALLOCATION PROPOSAL labels", () => {
    expect(normalizeChineseManagerTerms("EXECUTION BIAS: **BUY**")).toContain("执行倾向");
    expect(normalizeChineseManagerTerms("FINAL ALLOCATION PROPOSAL: **HOLD**")).toContain(
      "研究结论:",
    );
    expect(normalizeChineseManagerTerms("FINAL TRANSACTION PROPOSAL: **HOLD**")).toContain(
      "研究结论:",
    );
  });

  it("composes role-term and manager-term passes (熊派 → 空头 + Action Logic → 行为逻辑)", () => {
    const text = "## Action Logic\n熊派分析师认为下行风险加大。";
    const out = normalizeChineseManagerTerms(text);
    expect(out).toContain("## 行为逻辑");
    expect(out).toContain("空头分析师");
    expect(out).not.toContain("熊派");
  });

  it("rewrites '最终配置建议:' line label to '研究结论:'", () => {
    const out = normalizeChineseManagerTerms("最终配置建议: 偏多。");
    expect(out.startsWith("研究结论: 偏多")).toBe(true);
  });
});
