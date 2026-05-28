import { describe, expect, it } from "vitest";
import {
  compactText,
  containsExplicitRatingMarker,
  defaultActionLogic,
  defaultDebateConclusion,
  defaultExecutionPlan,
  defaultPositioningGuidance,
  defaultResearchPositioningGuidance,
  defaultRiskManagement,
  defaultTradingThesis,
  hasConflictingPrimaryAction,
  isPlaceholderLike,
  isRecommendationOnlySegment,
  isRecommendationRestatingSentence,
  mergeSparseSectionWithDefault,
  missingExecutionThresholds,
  removeOverlappingSentences,
  sanitizeSection,
  sanitizeTraderRiskManagement,
  sanitizeTraderThesis,
  sectionNeedsDetail,
  sentenceSimilarity,
  splitSentences,
  stripLeadingSectionHeadings,
  stripManagerInstructionLeakage,
  stripRecommendationRestatingSentences,
} from "../src/agents/helpers/sanitize_section.js";

// ---------------------------------------------------------------------------
// compactText
// ---------------------------------------------------------------------------
describe("compactText", () => {
  it("strips whitespace, punctuation, and lowercases", () => {
    expect(compactText("Hello, World!")).toBe("helloworld");
    expect(compactText("  多 空 因 素  ")).toBe("多空因素");
  });

  it("handles CJK punctuation", () => {
    expect(compactText("买入；卖出。")).toBe("买入卖出");
    expect(compactText("测试（括号）")).toBe("测试括号");
  });

  it("returns empty for empty/undefined", () => {
    expect(compactText("")).toBe("");
    expect(compactText(undefined)).toBe("");
  });
});

// ---------------------------------------------------------------------------
// splitSentences
// ---------------------------------------------------------------------------
describe("splitSentences", () => {
  it("splits on Chinese sentence-ending punctuation", () => {
    expect(splitSentences("第一句。第二句！第三句？")).toEqual([
      "第一句。",
      "第二句！",
      "第三句？",
    ]);
  });

  it("splits on newlines", () => {
    expect(splitSentences("line one\nline two\nline three")).toEqual([
      "line one",
      "line two",
      "line three",
    ]);
  });

  it("splits on English sentence-ending punctuation", () => {
    const result = splitSentences("First sentence. Second sentence! Third?");
    expect(result).toEqual(["First sentence.", "Second sentence!", "Third?"]);
  });

  it("returns empty for empty/undefined", () => {
    expect(splitSentences("")).toEqual([]);
    expect(splitSentences(undefined)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// isPlaceholderLike
// ---------------------------------------------------------------------------
describe("isPlaceholderLike", () => {
  it("detects exact-match placeholders (Chinese)", () => {
    expect(isPlaceholderLike("评估双方论证强度总结核心论点与致命弱点")).toBe(true);
    expect(isPlaceholderLike("明确评级与执行指引")).toBe(true);
    expect(isPlaceholderLike("待验证")).toBe(true);
  });

  it("detects exact-match placeholders (English)", () => {
    expect(isPlaceholderLike("balanced conclusion after evaluating both bull and bear cases")).toBe(
      true,
    );
    expect(isPlaceholderLike("concise trading thesis explaining the proposed action")).toBe(true);
  });

  it("detects regex-pattern placeholders", () => {
    expect(isPlaceholderLike("评估双方论证的强度，总结核心论点与致命弱点")).toBe(true);
    expect(isPlaceholderLike("evidence to action logic explaining valuation catalysts")).toBe(true);
  });

  it("returns false for real content", () => {
    expect(
      isPlaceholderLike("当前上行逻辑更完整，适合在确认信号仍然有效的前提下逐步建立仓位。"),
    ).toBe(false);
    expect(isPlaceholderLike("The upside thesis is more complete right now.")).toBe(false);
  });

  it("returns false for empty", () => {
    expect(isPlaceholderLike("")).toBe(false);
    expect(isPlaceholderLike(undefined)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// sectionNeedsDetail
// ---------------------------------------------------------------------------
describe("sectionNeedsDetail", () => {
  it("returns true for short Chinese text (< 55 compact chars)", () => {
    expect(sectionNeedsDetail("短线看涨。", "Chinese")).toBe(true);
  });

  it("returns true for Chinese text with < 2 sentences", () => {
    expect(sectionNeedsDetail("这是一个很长的段落但是只有一句话没有句号结尾", "Chinese")).toBe(
      true,
    );
  });

  it("returns false for adequate Chinese text", () => {
    const text =
      "当前上行逻辑更完整，适合在确认信号仍然有效的前提下逐步建立仓位。驱动这一判断的核心不是单一价格反弹，而是宏观压制边际缓和。";
    expect(sectionNeedsDetail(text, "Chinese")).toBe(false);
  });

  it("returns true for short English text (< 18 words)", () => {
    expect(sectionNeedsDetail("Buy now.", "English")).toBe(true);
  });

  it("returns false for adequate English text", () => {
    const text =
      "The upside thesis is more complete right now. The setup favors staged accumulation while confirmation remains intact. The core case should explain why macro pressure is easing.";
    expect(sectionNeedsDetail(text, "English")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// containsExplicitRatingMarker
// ---------------------------------------------------------------------------
describe("containsExplicitRatingMarker", () => {
  it("detects Chinese markers", () => {
    expect(containsExplicitRatingMarker("建议评级：买入", "Chinese")).toBe(true);
    expect(containsExplicitRatingMarker("最终配置建议: 持有", "Chinese")).toBe(true);
    expect(containsExplicitRatingMarker("维持增持", "Chinese")).toBe(true);
  });

  it("detects English markers", () => {
    expect(containsExplicitRatingMarker("RECOMMENDATION: BUY", "English")).toBe(true);
    expect(containsExplicitRatingMarker("RATING: HOLD", "English")).toBe(true);
    expect(containsExplicitRatingMarker("Recommend Overweight", "English")).toBe(true);
  });

  it("returns false for normal text", () => {
    expect(containsExplicitRatingMarker("当前价格站稳支撑位", "Chinese")).toBe(false);
    expect(containsExplicitRatingMarker("Price holds above support", "English")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isRecommendationOnlySegment
// ---------------------------------------------------------------------------
describe("isRecommendationOnlySegment", () => {
  it("detects Chinese recommendation-only lines", () => {
    expect(isRecommendationOnlySegment("建议评级：买入", "Chinese")).toBe(true);
    expect(isRecommendationOnlySegment("建议持有策略", "Chinese")).toBe(true);
    expect(isRecommendationOnlySegment("针对该ETF，建议采取买入策略", "Chinese")).toBe(true);
  });

  it("detects English recommendation-only lines", () => {
    expect(isRecommendationOnlySegment("RECOMMENDATION: BUY", "English")).toBe(true);
    expect(isRecommendationOnlySegment("MAINTAIN HOLD", "English")).toBe(true);
  });

  it("returns false for lines with substance", () => {
    expect(isRecommendationOnlySegment("当前价格站稳支撑位，建议评级：买入", "Chinese")).toBe(
      false,
    );
    expect(
      isRecommendationOnlySegment("Price holds support, recommend buying on dips.", "English"),
    ).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// isRecommendationRestatingSentence
// ---------------------------------------------------------------------------
describe("isRecommendationRestatingSentence", () => {
  it("detects Chinese restating sentences", () => {
    expect(isRecommendationRestatingSentence("综合以上证据，建议买入。", "Chinese")).toBe(true);
    expect(isRecommendationRestatingSentence("本组合明确评级为持有。", "Chinese")).toBe(true);
    expect(isRecommendationRestatingSentence("对510300.SH建议增持。", "Chinese")).toBe(true);
  });

  it("detects English restating sentences", () => {
    expect(
      isRecommendationRestatingSentence(
        "Based on the evidence above, the recommendation is BUY.",
        "English",
      ),
    ).toBe(true);
    expect(isRecommendationRestatingSentence("The clear view is hold.", "English")).toBe(true);
  });

  it("returns false for substantive sentences", () => {
    expect(
      isRecommendationRestatingSentence("当前价格站稳50日均线上方，成交量放大。", "Chinese"),
    ).toBe(false);
    expect(
      isRecommendationRestatingSentence(
        "Price reclaimed the 50-day moving average with volume.",
        "English",
      ),
    ).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// stripRecommendationRestatingSentences
// ---------------------------------------------------------------------------
describe("stripRecommendationRestatingSentences", () => {
  it("removes restating sentences, keeps substantive ones", () => {
    const text = "价格站稳支撑位。综合以上证据，建议买入。成交量持续放大。";
    const result = stripRecommendationRestatingSentences(text, "Chinese");
    expect(result).toContain("价格站稳支撑位");
    expect(result).toContain("成交量持续放大");
    expect(result).not.toContain("建议买入");
  });

  it("returns empty for all-restating text", () => {
    expect(stripRecommendationRestatingSentences("综合以上证据，建议买入。", "Chinese")).toBe("");
  });
});

// ---------------------------------------------------------------------------
// hasConflictingPrimaryAction
// ---------------------------------------------------------------------------
describe("hasConflictingPrimaryAction", () => {
  it("detects bullish verbs conflicting with SELL rating", () => {
    expect(hasConflictingPrimaryAction("应该买入该ETF", "Sell", "Chinese")).toBe(true);
    expect(hasConflictingPrimaryAction("建议加仓", "Underweight", "Chinese")).toBe(true);
  });

  it("detects bearish verbs conflicting with BUY rating", () => {
    // "考虑" matches ALLOW_SUFFIX_RE → exempted (Python behavior)
    expect(hasConflictingPrimaryAction("考虑减持", "Buy", "Chinese")).toBe(false);
    // "建议卖出" — "建议" is not a conditional prefix, no allow suffix → conflict
    expect(hasConflictingPrimaryAction("建议卖出该ETF", "Overweight", "Chinese")).toBe(true);
  });

  it("detects English conflicts", () => {
    // "should" not a conditional prefix → conflict
    expect(hasConflictingPrimaryAction("We should reduce exposure now", "Buy", "English")).toBe(
      true,
    );
    // "Consider" matches ALLOW_SUFFIX_RE → exempted
    expect(hasConflictingPrimaryAction("Consider adding to the position", "Sell", "English")).toBe(
      false,
    );
  });

  it("exempts conditional prefixes", () => {
    expect(hasConflictingPrimaryAction("若价格跌破支撑则减仓", "Buy", "Chinese")).toBe(false);
    // "If" is in a different comma-separated clause than "reduce" —
    // the clause-level exemption cannot see it. Python behaves the same.
    expect(
      hasConflictingPrimaryAction("If price breaks support, reduce exposure", "Buy", "English"),
    ).toBe(true);
  });

  it("returns true for HOLD with non-conditional bullish text", () => {
    // "可" matches ALLOW_SUFFIX_RE → exempted
    expect(hasConflictingPrimaryAction("若条件满足可加仓", "Hold", "Chinese")).toBe(false);
    // No conditional prefix → conflict
    expect(hasConflictingPrimaryAction("应该买入该ETF", "Hold", "Chinese")).toBe(true);
  });

  it("returns false for no action verbs", () => {
    expect(hasConflictingPrimaryAction("当前价格在支撑位附近震荡", "Buy", "Chinese")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// sentenceSimilarity
// ---------------------------------------------------------------------------
describe("sentenceSimilarity", () => {
  it("returns 1 for identical strings", () => {
    expect(sentenceSimilarity("价格站稳支撑位", "价格站稳支撑位")).toBe(1);
  });

  it("returns 0 for empty strings", () => {
    expect(sentenceSimilarity("", "test")).toBe(0);
    expect(sentenceSimilarity("test", "")).toBe(0);
  });

  it("returns ~0.9 for substring containment (minLen >= 12)", () => {
    const short = "价格站稳支撑位后继续上行";
    const long = "在确认价格站稳支撑位后继续上行的过程中，成交量持续放大";
    expect(sentenceSimilarity(short, long)).toBe(0.9);
  });

  it("returns 0 for very different lengths (ratio < 0.4)", () => {
    expect(
      sentenceSimilarity("买", "当前上行逻辑更完整，适合在确认信号仍然有效的前提下逐步建立仓位"),
    ).toBe(0);
  });

  it("returns > 0 for similar strings", () => {
    const sim = sentenceSimilarity("价格站稳支撑位后继续上行", "价格站稳阻力位后继续上行");
    expect(sim).toBeGreaterThan(0.5);
    expect(sim).toBeLessThan(1);
  });
});

// ---------------------------------------------------------------------------
// removeOverlappingSentences
// ---------------------------------------------------------------------------
describe("removeOverlappingSentences", () => {
  it("removes sentences that overlap with reference", () => {
    const text = "价格站稳支撑位。成交量持续放大。宏观环境改善。";
    const reference = "价格站稳支撑位。行业景气回升。";
    const result = removeOverlappingSentences(text, reference);
    expect(result).toContain("成交量持续放大");
    expect(result).toContain("宏观环境改善");
    expect(result).not.toContain("价格站稳支撑位");
  });

  it("keeps all sentences when no overlap", () => {
    const text = "行业景气回升。资金流入增加。";
    const reference = "价格站稳支撑位。成交量放大。";
    const result = removeOverlappingSentences(text, reference);
    expect(result).toContain("行业景气回升");
    expect(result).toContain("资金流入增加");
  });

  it("returns original text when reference is empty", () => {
    expect(removeOverlappingSentences("测试文本。", "")).toBe("测试文本。");
    expect(removeOverlappingSentences("测试文本。", undefined)).toBe("测试文本。");
  });
});

// ---------------------------------------------------------------------------
// defaultTradingThesis
// ---------------------------------------------------------------------------
describe("defaultTradingThesis", () => {
  it("returns Chinese text for Chinese language", () => {
    const thesis = defaultTradingThesis("Buy", "Chinese");
    expect(thesis).toContain("上行逻辑");
    expect(thesis.length).toBeGreaterThan(50);
  });

  it("returns English text for English language", () => {
    const thesis = defaultTradingThesis("Buy", "English");
    expect(thesis).toContain("upside thesis");
    expect(thesis.length).toBeGreaterThan(50);
  });

  it("covers all five ratings", () => {
    for (const rating of ["Buy", "Overweight", "Hold", "Underweight", "Sell"] as const) {
      expect(defaultTradingThesis(rating, "Chinese")).toBeTruthy();
      expect(defaultTradingThesis(rating, "English")).toBeTruthy();
    }
  });
});

// ---------------------------------------------------------------------------
// defaultExecutionPlan
// ---------------------------------------------------------------------------
describe("defaultExecutionPlan", () => {
  it("returns Chinese text with anchor injection", () => {
    const plan = defaultExecutionPlan("Buy", "Chinese", "50日均线 3.579 元");
    expect(plan).toContain("3.579");
    expect(plan.length).toBeGreaterThan(50);
  });

  it("returns English text", () => {
    const plan = defaultExecutionPlan("Buy", "English");
    expect(plan).toContain("20%-30%");
    expect(plan.length).toBeGreaterThan(50);
  });

  it("covers all five ratings", () => {
    for (const rating of ["Buy", "Overweight", "Hold", "Underweight", "Sell"] as const) {
      expect(defaultExecutionPlan(rating, "Chinese")).toBeTruthy();
      expect(defaultExecutionPlan(rating, "English")).toBeTruthy();
    }
  });
});

// ---------------------------------------------------------------------------
// defaultRiskManagement
// ---------------------------------------------------------------------------
describe("defaultRiskManagement", () => {
  it("returns Chinese text", () => {
    expect(defaultRiskManagement("Buy", "Chinese")).toContain("失效条件");
  });

  it("returns English text", () => {
    expect(defaultRiskManagement("Buy", "English")).toContain("invalidation");
  });

  it("covers all five ratings", () => {
    for (const rating of ["Buy", "Overweight", "Hold", "Underweight", "Sell"] as const) {
      expect(defaultRiskManagement(rating, "Chinese")).toBeTruthy();
      expect(defaultRiskManagement(rating, "English")).toBeTruthy();
    }
  });
});

// ---------------------------------------------------------------------------
// defaultDebateConclusion / defaultActionLogic / defaultResearchPositioningGuidance / defaultPositioningGuidance
// ---------------------------------------------------------------------------
describe("other defaults", () => {
  it("defaultDebateConclusion covers all ratings", () => {
    for (const rating of ["Buy", "Overweight", "Hold", "Underweight", "Sell"] as const) {
      expect(defaultDebateConclusion(rating, "Chinese")).toBeTruthy();
      expect(defaultDebateConclusion(rating, "English")).toBeTruthy();
    }
  });

  it("defaultActionLogic covers all ratings", () => {
    for (const rating of ["Buy", "Overweight", "Hold", "Underweight", "Sell"] as const) {
      expect(defaultActionLogic(rating, "Chinese")).toBeTruthy();
      expect(defaultActionLogic(rating, "English")).toBeTruthy();
    }
  });

  it("defaultResearchPositioningGuidance covers all ratings", () => {
    for (const rating of ["Buy", "Overweight", "Hold", "Underweight", "Sell"] as const) {
      expect(defaultResearchPositioningGuidance(rating, "Chinese")).toBeTruthy();
      expect(defaultResearchPositioningGuidance(rating, "English")).toBeTruthy();
    }
  });

  it("defaultPositioningGuidance returns first sentence", () => {
    const guidance = defaultPositioningGuidance("Buy", "Chinese");
    const full = defaultResearchPositioningGuidance("Buy", "Chinese");
    expect(guidance.length).toBeLessThanOrEqual(full.length);
    expect(guidance.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// stripLeadingSectionHeadings
// ---------------------------------------------------------------------------
describe("stripLeadingSectionHeadings", () => {
  it("strips heading lines from the start", () => {
    const text = "配置逻辑\n配置执行计划\n实际内容在这里。";
    const result = stripLeadingSectionHeadings(text, ["配置逻辑", "配置执行计划"]);
    expect(result).toBe("实际内容在这里。");
  });

  it("strips numbered headings", () => {
    const text = "一、配置逻辑\n二、配置执行计划\n实际内容。";
    const result = stripLeadingSectionHeadings(text, ["配置逻辑", "配置执行计划"]);
    expect(result).toBe("实际内容。");
  });

  it("does not strip non-heading content", () => {
    const text = "当前价格站稳支撑位。";
    expect(stripLeadingSectionHeadings(text, ["配置逻辑"])).toBe(text);
  });

  it("returns empty for empty input", () => {
    expect(stripLeadingSectionHeadings("", ["配置逻辑"])).toBe("");
    expect(stripLeadingSectionHeadings(undefined, ["配置逻辑"])).toBe("");
  });
});

// ---------------------------------------------------------------------------
// stripManagerInstructionLeakage
// ---------------------------------------------------------------------------
describe("stripManagerInstructionLeakage", () => {
  it("strips instruction-like lines", () => {
    const text = "请在输出字段中提供详细的分析。\n实际分析内容在这里。";
    const result = stripManagerInstructionLeakage(text);
    expect(result).toContain("实际分析内容在这里");
    expect(result).not.toContain("请在输出字段中");
  });

  it("passes through clean text unchanged", () => {
    const text = "当前价格站稳支撑位，成交量放大。";
    expect(stripManagerInstructionLeakage(text)).toBe(text);
  });

  it("returns empty for empty/undefined", () => {
    expect(stripManagerInstructionLeakage("")).toBe("");
    expect(stripManagerInstructionLeakage(undefined)).toBe("");
  });
});

// ---------------------------------------------------------------------------
// sanitizeSection
// ---------------------------------------------------------------------------
describe("sanitizeSection", () => {
  it("returns default for empty text", () => {
    expect(sanitizeSection("", "默认文本", "Buy", "Chinese")).toBe("默认文本");
    expect(sanitizeSection(undefined, "默认文本", "Buy", "Chinese")).toBe("默认文本");
  });

  it("returns default for placeholder text", () => {
    expect(sanitizeSection("明确评级与执行指引", "默认文本", "Buy", "Chinese")).toBe("默认文本");
  });

  it("returns default for conflicting action", () => {
    const result = sanitizeSection("建议卖出该ETF", "默认文本", "Buy", "Chinese", {
      checkActionConflict: true,
    });
    expect(result).toBe("默认文本");
  });

  it("merges sparse content with default when requireDetail is true", () => {
    const sparse = "短线看涨。";
    const defaultText = "详细分析文本包含多个句子和具体数据。价格站稳支撑位。成交量放大。";
    const result = sanitizeSection(sparse, defaultText, "Buy", "Chinese", { requireDetail: true });
    expect(result).toContain("短线看涨");
    expect(result).toContain("详细分析文本");
  });

  it("passes through clean, substantive text", () => {
    const text =
      "当前上行逻辑更完整，适合在确认信号仍然有效的前提下逐步建立仓位。驱动这一判断的核心不是单一价格反弹，而是宏观压制边际缓和、行业盈利与供需线索同步改善。";
    const result = sanitizeSection(text, "默认文本", "Buy", "Chinese");
    // Content is preserved (may be re-joined with newlines after sentence splitting)
    expect(result).toContain("当前上行逻辑更完整");
    expect(result).toContain("宏观压制边际缓和");
    expect(result).not.toBe("默认文本");
  });

  it("strips recommendation-restating sentences", () => {
    const text = "价格站稳支撑位。综合以上证据，建议买入。成交量放大。";
    const result = sanitizeSection(text, "默认文本", "Buy", "Chinese");
    expect(result).toContain("价格站稳支撑位");
    expect(result).toContain("成交量放大");
  });
});

// ---------------------------------------------------------------------------
// mergeSparseSectionWithDefault
// ---------------------------------------------------------------------------
describe("mergeSparseSectionWithDefault", () => {
  it("returns default when content is empty", () => {
    expect(mergeSparseSectionWithDefault("", "默认文本")).toBe("默认文本");
    expect(mergeSparseSectionWithDefault(undefined, "默认文本")).toBe("默认文本");
  });

  it("returns default when content equals default (compact)", () => {
    expect(mergeSparseSectionWithDefault("默认文本。", "默认文本")).toBe("默认文本");
  });

  it("merges content with default using punctuation-aware joiner", () => {
    const result = mergeSparseSectionWithDefault("短线看涨", "详细分析文本", "Chinese");
    expect(result).toContain("短线看涨");
    expect(result).toContain("详细分析文本");
  });

  it("uses newline joiner when content ends with punctuation", () => {
    const result = mergeSparseSectionWithDefault("短线看涨。", "详细分析文本", "Chinese");
    expect(result).toBe("短线看涨。\n详细分析文本");
  });
});

// ---------------------------------------------------------------------------
// sanitizeTraderThesis
// ---------------------------------------------------------------------------
describe("sanitizeTraderThesis", () => {
  it("returns default for empty thesis", () => {
    const result = sanitizeTraderThesis("", "执行计划内容", "Buy", "Chinese");
    expect(result).toContain("上行逻辑");
  });

  it("deduplicates against execution plan", () => {
    const executionPlan = "价格站稳50日均线3.579元后加仓，成交量达到1.2倍。";
    const thesis = "价格站稳50日均线3.579元后加仓，成交量达到1.2倍。宏观环境改善。";
    const result = sanitizeTraderThesis(thesis, executionPlan, "Buy", "Chinese");
    expect(result).toContain("宏观环境改善");
  });

  it("returns default for conflicting action", () => {
    const result = sanitizeTraderThesis("建议卖出该ETF", "执行计划", "Buy", "Chinese");
    expect(result).toContain("上行逻辑");
  });
});

// ---------------------------------------------------------------------------
// sanitizeTraderRiskManagement
// ---------------------------------------------------------------------------
describe("sanitizeTraderRiskManagement", () => {
  it("returns default for empty risk management", () => {
    const result = sanitizeTraderRiskManagement("", "配置逻辑", "执行计划", "Buy", "Chinese");
    expect(result).toContain("失效条件");
  });

  it("deduplicates against thesis and execution plan", () => {
    const thesis = "价格站稳支撑位后逐步加仓。";
    const executionPlan = "成交量达到1.2倍20日均量。";
    const riskMgmt = "价格站稳支撑位后逐步加仓。成交量达到1.2倍20日均量。若跌破支撑则止损。";
    const result = sanitizeTraderRiskManagement(riskMgmt, thesis, executionPlan, "Buy", "Chinese");
    expect(result).toContain("若跌破支撑则止损");
  });
});

// ---------------------------------------------------------------------------
// missingExecutionThresholds
// ---------------------------------------------------------------------------
describe("missingExecutionThresholds", () => {
  it("returns true for empty text", () => {
    expect(missingExecutionThresholds("")).toBe(true);
    expect(missingExecutionThresholds(undefined)).toBe(true);
  });

  it("returns false when all three threshold types are present", () => {
    const text = "当价格站稳50日均线3.579元，且成交量达到近20日均量的1.2倍时加仓。";
    expect(missingExecutionThresholds(text)).toBe(false);
  });

  it("returns true when market-level anchor is missing", () => {
    const text = "当成交量达到1.2倍时加仓，目标价位3.58元。";
    expect(missingExecutionThresholds(text)).toBe(true);
  });

  it("returns true when volume/flow threshold is missing", () => {
    const text = "当价格站稳50日均线3.579元时加仓。";
    expect(missingExecutionThresholds(text)).toBe(true);
  });

  it("returns false when market-level anchor is present alongside numeric", () => {
    // "50日均线" → NUMERIC_THRESHOLD_RE matches "50日" (digit + unit "日").
    // Python's regex has the same overmatch — both treat "50日均线" as a numeric threshold.
    const text = "当价格站稳50日均线且成交量放大时加仓。";
    expect(missingExecutionThresholds(text)).toBe(false);
  });

  it("returns true when all thresholds are missing", () => {
    expect(missingExecutionThresholds("当价格企稳后加仓。")).toBe(true);
  });
});

// ===========================================================================
// English-path coverage (functions with isChinese(language) branches)
// ===========================================================================

// --- sanitizeSection (English) ---
describe("sanitizeSection (English)", () => {
  it("returns default for empty text", () => {
    expect(sanitizeSection("", "default text", "Buy", "English")).toBe("default text");
  });

  it("strips English recommendation-restating sentences", () => {
    const text = "Price holds above support. The recommendation is BUY. Volume is expanding.";
    const result = sanitizeSection(text, "default text", "Buy", "English");
    expect(result).toContain("Price holds above support");
    expect(result).toContain("Volume is expanding");
    expect(result).not.toContain("recommendation is BUY");
  });

  it("returns default for conflicting action", () => {
    expect(
      sanitizeSection("We should sell immediately.", "default text", "Buy", "English", {
        checkActionConflict: true,
      }),
    ).toBe("default text");
  });

  it("merges sparse English content with default when requireDetail is true", () => {
    const result = sanitizeSection(
      "Short take.",
      "A detailed default with multiple sentences. Second sentence.",
      "Buy",
      "English",
      { requireDetail: true },
    );
    expect(result).toContain("Short take");
    expect(result).toContain("detailed default");
  });
});

// --- sanitizeTraderThesis (English) ---
describe("sanitizeTraderThesis (English)", () => {
  it("returns default for empty thesis", () => {
    const result = sanitizeTraderThesis("", "exec plan content", "Buy", "English");
    expect(result).toContain("upside thesis");
  });

  it("deduplicates against execution plan", () => {
    const execPlan = "Add only after price reclaims 50-day SMA 3.58 and volume expands.";
    const thesis =
      "Add only after price reclaims 50-day SMA 3.58 and volume expands. Macro conditions are improving.";
    const result = sanitizeTraderThesis(thesis, execPlan, "Buy", "English");
    expect(result).toContain("Macro conditions");
  });
});

// --- sanitizeTraderRiskManagement (English) ---
describe("sanitizeTraderRiskManagement (English)", () => {
  it("returns default for empty risk management", () => {
    const result = sanitizeTraderRiskManagement("", "thesis", "exec plan", "Buy", "English");
    expect(result).toContain("invalidation");
  });
});

// --- mergeSparseSectionWithDefault (English) ---
describe("mergeSparseSectionWithDefault (English)", () => {
  it("merges English content with default using period joiner", () => {
    const result = mergeSparseSectionWithDefault(
      "Short thesis",
      "Detailed default analysis.",
      "English",
    );
    expect(result).toContain("Short thesis");
    expect(result).toContain("Detailed default");
  });

  it("uses newline joiner when content ends with period", () => {
    const result = mergeSparseSectionWithDefault("Short thesis.", "Detailed default.", "English");
    expect(result).toBe("Short thesis.\nDetailed default.");
  });
});

// --- stripRecommendationRestatingSentences (English) ---
describe("stripRecommendationRestatingSentences (English)", () => {
  it("removes English restating sentences", () => {
    const text = "Volume is expanding. The view is HOLD. Price reclaimed support.";
    const result = stripRecommendationRestatingSentences(text, "English");
    expect(result).toContain("Volume is expanding");
    expect(result).toContain("Price reclaimed support");
    expect(result).not.toContain("view is HOLD");
  });
});

// --- stripLeadingSectionHeadings (English) ---
describe("stripLeadingSectionHeadings (English)", () => {
  it("strips English section heading lines", () => {
    const text = "ETF Allocation Thesis\nAllocation Execution Plan\nActual content here.";
    const result = stripLeadingSectionHeadings(text, [
      "ETF Allocation Thesis",
      "Allocation Execution Plan",
    ]);
    expect(result).toBe("Actual content here.");
  });
});

// --- stripManagerInstructionLeakage (English) ---
describe("stripManagerInstructionLeakage (English)", () => {
  it("strips English instruction lines", () => {
    const text = "Please ensure the field contains detailed analysis.\nActual content here.";
    const result = stripManagerInstructionLeakage(text);
    expect(result).toContain("Actual content here");
    expect(result).not.toContain("Please ensure the field");
  });
});

// ===========================================================================
// Additional option / boundary coverage
// ===========================================================================

// --- sanitizeSection with stripHeadings ---
describe("sanitizeSection with stripHeadings", () => {
  it("strips leading headings before sanitizing", () => {
    const text = "一、执行计划\n实际分析内容包含多个句子。价格站稳支撑位后逐步加仓。";
    const result = sanitizeSection(text, "default", "Buy", "Chinese", {
      stripHeadings: ["执行计划"],
    });
    expect(result).not.toContain("一、执行计划");
    expect(result).toContain("价格站稳支撑位后逐步加仓");
  });
});

// --- removeOverlappingSentences with custom threshold ---
describe("removeOverlappingSentences custom threshold", () => {
  it("uses custom threshold to control overlap sensitivity", () => {
    const text = "Price holds above the support level. Volume is expanding.";
    // Slightly different sentence — high similarity
    const reference = "Price holds above the resistance level.";
    // Default threshold 0.72: these two sentences have high LCS ratio
    // (only "support"/"resistance" differ) → likely removed at 0.72
    const resultDefault = removeOverlappingSentences(text, reference);
    // With threshold 0.95: only near-identical matches removed → keeps it
    const resultRelaxed = removeOverlappingSentences(text, reference, 0.95);
    expect(resultDefault.length).toBeLessThanOrEqual(resultRelaxed.length);
  });
});

// --- sectionNeedsDetail boundary ---
describe("sectionNeedsDetail boundary", () => {
  // Chinese: compact < 55 chars or < 2 sentences → needs detail
  it("returns false for Chinese text crossing the compact-char boundary", () => {
    // Two sentences, compact >= 55 chars after stripping
    const text =
      "当前上行逻辑更完整适合在确认信号仍然有效的前提下逐步建立仓位做好准备。驱动这一判断的核心不是单一价格反弹而是宏观压制趋缓。";
    expect(sectionNeedsDetail(text, "Chinese")).toBe(false);
  });

  it("returns true for English text below word-count boundary", () => {
    // 17 words → below 18-word threshold
    const text = "The setup favors staged accumulation while confirmation remains intact. Short.";
    expect(sectionNeedsDetail(text, "English")).toBe(true);
  });
});

// --- hasConflictingPrimaryAction with comma-separated clauses ---
describe("hasConflictingPrimaryAction clause-level exemptions", () => {
  it("exempts when allow-word is in the clause immediately before the match", () => {
    // "考虑" in clausePrefix "可以考虑减持" but the conflict check looks at
    // the clause prefix of the bearish match "减持".
    // clausePrefix = "可以考虑" → ALLOW_SUFFIX_RE matches "考虑" → exempted
    expect(hasConflictingPrimaryAction("基本面改善，可以考虑减持", "Buy", "Chinese")).toBe(false);
  });
});
