import { describe, expect, it } from "vitest";
import {
  demoteTraderH1Headings,
  formatTraderNumberedBlocks,
  formatTraderThesisBody,
  normalizeTraderConfigLogicHeading,
  restoreTraderExecutionBiasSection,
  stripConstituentTradeInstructions,
  stripNumberedHeadingPrefix,
} from "../src/agents/helpers/trader_format.js";

describe("demoteTraderH1Headings", () => {
  it("turns # H1 into ## while leaving ## and below alone", () => {
    expect(demoteTraderH1Headings("# Title\n## Sub")).toBe("## Title\n## Sub");
    expect(demoteTraderH1Headings("# 中文标题")).toBe("## 中文标题");
    expect(demoteTraderH1Headings("Body without heading")).toBe("Body without heading");
  });

  it("returns empty for empty / undefined", () => {
    expect(demoteTraderH1Headings(undefined)).toBe("");
    expect(demoteTraderH1Headings("")).toBe("");
  });
});

describe("normalizeTraderConfigLogicHeading", () => {
  it("renames 'ETF配置逻辑' to '配置逻辑' (alias — no body re-insert)", () => {
    const text = "一、ETF配置逻辑\n这是配置逻辑的正文。";
    const out = normalizeTraderConfigLogicHeading(text, "Chinese");
    expect(out).toContain("一、配置逻辑");
    expect(out).not.toContain("ETF配置逻辑");
  });

  it("preserves a non-alias heading text by re-inserting it as a paragraph", () => {
    const text = "一、配置主线索\n核心论据：偏多结构成立。";
    const out = normalizeTraderConfigLogicHeading(text, "Chinese");
    expect(out.startsWith("一、配置逻辑")).toBe(true);
    // Original heading text (now demoted to paragraph) is retained
    expect(out).toContain("配置主线索");
    // Body text follows
    expect(out).toContain("核心论据：偏多结构成立。");
  });

  it("is a no-op for English output", () => {
    const text = "## ETF Allocation Thesis\nbody";
    expect(normalizeTraderConfigLogicHeading(text, "English")).toBe(text);
  });

  it("leaves canonical '一、配置逻辑' unchanged", () => {
    const text = "一、配置逻辑\n配置逻辑正文。";
    expect(normalizeTraderConfigLogicHeading(text, "Chinese")).toBe(text);
  });
});

describe("restoreTraderExecutionBiasSection", () => {
  it("promotes a tail-of-doc '执行倾向: **持有**' line into section 四", () => {
    const text =
      "一、配置逻辑\n偏多。\n\n二、配置执行计划\n回踩加仓。\n\n三、再平衡与风险控制\n跌破止损。\n\n执行倾向: **持有**";
    const out = restoreTraderExecutionBiasSection(text, "Chinese");
    expect(out).toContain("\n\n四、执行倾向\n**持有**");
    // Must not duplicate the rating elsewhere
    expect(out).not.toContain("执行倾向: **持有**");
  });

  it("rewrites '最终配置建议: **买入**' tail into section 四 with the same rating", () => {
    const text = "一、配置逻辑\n偏多。\n\n最终配置建议: **买入**";
    const out = restoreTraderExecutionBiasSection(text, "Chinese");
    expect(out.endsWith("四、执行倾向\n**买入**")).toBe(true);
  });

  it("when section 四 already exists, normalizes its body to **rating** only", () => {
    const text = "一、配置逻辑\n偏多。\n\n四、执行倾向\n执行倾向: **减持**\n配置评级: **减持**";
    const out = restoreTraderExecutionBiasSection(text, "Chinese");
    // Expect a single canonical rating line, no duplicate label echoes.
    expect(out).toContain("四、执行倾向\n**减持**");
    expect(out.match(/减持/g)?.length).toBeLessThanOrEqual(2);
  });

  it("leaves text unchanged if no rating can be located", () => {
    const text = "一、配置逻辑\n偏多。\n\n二、配置执行计划\n回踩加仓。";
    expect(restoreTraderExecutionBiasSection(text, "Chinese")).toBe(text);
  });

  it("is a no-op for English output", () => {
    const text = "## ETF Allocation Thesis\nbody\n\nEXECUTION BIAS: **HOLD**";
    expect(restoreTraderExecutionBiasSection(text, "English")).toBe(text);
  });
});

describe("stripConstituentTradeInstructions", () => {
  it("removes a sentence that issues a constituent buy/sell instruction", () => {
    const text = "建议清仓中国核电（7.91%权重，归母同比-34.19%），转向更稳健配置。";
    const out = stripConstituentTradeInstructions(text, "Chinese");
    // Constituent name + percentage detail removed; scope note inserted
    expect(out).not.toContain("中国核电");
    expect(out).toContain("成分股层面的估值");
  });

  it("preserves the ETF-level prefix when the segment also issues a fund-level action", () => {
    const text = "目标权重压至 4%，优先减持中国核电（7.91%权重，归母同比-34.19%）。";
    const out = stripConstituentTradeInstructions(text, "Chinese");
    expect(out).toContain("目标权重");
    expect(out).not.toContain("中国核电");
  });

  it("leaves clauses with no constituent detail untouched", () => {
    const text = "目标仓位维持在 4% 以下，跌破支撑则减至 2 成。";
    expect(stripConstituentTradeInstructions(text, "Chinese")).toBe(text);
  });

  it("does not insert a duplicate scope note when invoked with insertScopeNote=false", () => {
    const text = "建议清仓中国核电（7.91%权重）。";
    const out = stripConstituentTradeInstructions(text, "Chinese", { insertScopeNote: false });
    expect(out).not.toContain("成分股层面的估值");
  });

  it("is a no-op for English output (English prose handled by prompt rules)", () => {
    const text = "Trim the China General Nuclear (7.91% weight) holding.";
    expect(stripConstituentTradeInstructions(text, "English")).toBe(text);
  });

  it("returns empty for empty / undefined", () => {
    expect(stripConstituentTradeInstructions("", "Chinese")).toBe("");
    expect(stripConstituentTradeInstructions(undefined, "Chinese")).toBe("");
  });
});

describe("stripNumberedHeadingPrefix", () => {
  it("removes leading 一、/ 二、numbering", () => {
    expect(stripNumberedHeadingPrefix("一、配置逻辑")).toBe("配置逻辑");
    expect(stripNumberedHeadingPrefix("二、 趋势同步向上")).toBe("趋势同步向上");
  });

  it("removes leading 1. / 2) numbering", () => {
    expect(stripNumberedHeadingPrefix("1. 偏多")).toBe("偏多");
    expect(stripNumberedHeadingPrefix("2) plan")).toBe("plan");
  });

  it("strips a markdown heading prefix combined with numbering", () => {
    expect(stripNumberedHeadingPrefix("## 一、 配置逻辑")).toBe("配置逻辑");
  });

  it("leaves a plain sentence unchanged", () => {
    expect(stripNumberedHeadingPrefix("当前偏多结构成立。")).toBe("当前偏多结构成立。");
  });
});

describe("formatTraderThesisBody", () => {
  it("promotes each sentence to a numbered argument when there are 2+ sentences", () => {
    const text = "偏多结构成立。资金流持续净流入。中期趋势未破。";
    const out = formatTraderThesisBody(text, "Chinese");
    expect(out).toContain("1. 偏多结构成立。");
    expect(out).toContain("2. 资金流持续净流入。");
    expect(out).toContain("3. 中期趋势未破。");
  });

  it("leaves a single-sentence thesis unchanged", () => {
    const text = "当前宏观与行业同步偏多。";
    expect(formatTraderThesisBody(text, "Chinese")).toBe(text);
  });

  it("is a no-op for English output", () => {
    const text = "Macro improves. Industry confirms. Flows positive.";
    expect(formatTraderThesisBody(text, "English")).toBe(text);
  });
});

describe("formatTraderNumberedBlocks", () => {
  it("buckets sentences into execution blocks (initial / add / reduce / monitor)", () => {
    const text =
      "先以目标仓位的 30% 建立试探仓，按节奏分批入场。" +
      "若价格站稳 50 日均线，可上调到 5 成。" +
      "若价格放量跌破 3.58 元则先减至 2 成。" +
      "持续跟踪份额变化与 NAV 溢价率。";
    const out = formatTraderNumberedBlocks(text, "execution", "Chinese");
    // Buckets present: initial (first sentence, no action verb), add (上调),
    // reduce (跌破/减至), monitor (跟踪).
    expect(out).toContain("1. 初始仓位与执行节奏");
    expect(out).toContain("2. 加仓触发条件");
    expect(out).toContain("3. 减仓触发的核心条件");
    expect(out).toContain("4. 跟踪验证与再平衡");
    // The original sentences must all survive
    expect(out).toContain("先以目标仓位的 30%");
    expect(out).toContain("放量跌破 3.58 元");
    expect(out).toContain("份额变化与 NAV");
  });

  it("uses risk-section labels when sectionKind=risk", () => {
    const text =
      "风险预算控制在 6% 以内，单只 ETF 仓位上限 50%。" +
      "若价格放量跌破 3.54 元则减至 2 成。" +
      "回补需要价格站回 50 日均线且份额连续 2 日净申购。" +
      "每日监控波动率与流动性。";
    const out = formatTraderNumberedBlocks(text, "risk", "Chinese");
    expect(out).toContain("1. 风险预算与仓位边界");
    expect(out).toMatch(/回补与恢复条件|监控优先级|减仓触发的核心条件/);
  });

  it("returns the input unchanged when it already has numbered blocks", () => {
    const text = "1. 初始仓位\n建立 30% 试探仓。\n\n2. 加仓条件\n站稳 50 日均线。";
    expect(formatTraderNumberedBlocks(text, "execution", "Chinese")).toBe(text);
  });

  it("returns the input unchanged for short single-bucket prose", () => {
    const text = "建议以 30% 仓位试探。";
    expect(formatTraderNumberedBlocks(text, "execution", "Chinese")).toBe(text);
  });

  it("is a no-op for English output (English numbering handled by prompts)", () => {
    const text = "Open at 30% sizing. Add above 50-day SMA. Trim below support.";
    expect(formatTraderNumberedBlocks(text, "execution", "English")).toBe(text);
  });
});
