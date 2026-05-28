import { describe, expect, it } from "vitest";
import { containsCjk, extractTextContent } from "../src/agents/helpers/content.js";
import {
  isProcessOnlyReportText,
  isToolCallText,
  looksLikeProcessNarration,
  looksLikeUnexecutedToolIntent,
  stripProcessOnlyReportPrefix,
} from "../src/agents/helpers/process_narration.js";

describe("extractTextContent", () => {
  it("returns plain string content unchanged (trimmed)", () => {
    expect(extractTextContent("  hello  ")).toBe("hello");
  });

  it("joins string array entries with newlines", () => {
    expect(extractTextContent(["a", "b"])).toBe("a\nb");
  });

  it("extracts text from anthropic-style content blocks", () => {
    const blocks = [
      { type: "text", text: "first part" },
      { type: "text", text: "second part" },
    ];
    expect(extractTextContent(blocks)).toBe("first part\nsecond part");
  });

  it("recurses into nested .content fields", () => {
    const nested = { type: "anything", content: [{ type: "text", text: "deep" }] };
    expect(extractTextContent(nested)).toBe("deep");
  });

  it("ignores non-text blocks like tool_use", () => {
    const blocks = [
      { type: "tool_use", text: "should be ignored", input: {} },
      { type: "text", text: "kept" },
    ];
    expect(extractTextContent(blocks)).toBe("kept");
  });

  it("returns empty string for null / undefined", () => {
    expect(extractTextContent(null)).toBe("");
    expect(extractTextContent(undefined)).toBe("");
  });
});

describe("containsCjk", () => {
  it("detects Chinese characters", () => {
    expect(containsCjk("配置逻辑")).toBe(true);
    expect(containsCjk("plain ascii")).toBe(false);
    expect(containsCjk("")).toBe(false);
  });
});

describe("looksLikeProcessNarration", () => {
  it("matches Chinese 'data ready, now I will write' opening lines", () => {
    expect(looksLikeProcessNarration("数据已经全部获取完毕，现在我来撰写分析报告。")).toBe(true);
    expect(looksLikeProcessNarration("以下是510300.SH的分析报告：")).toBe(true);
    expect(looksLikeProcessNarration("报告已就绪，下面给出完整结论。")).toBe(true);
  });

  it("does not match real opening sentences", () => {
    expect(
      looksLikeProcessNarration("价格站稳50日均线上方，短中期均线同步向上，MACD柱状图持续扩张。"),
    ).toBe(false);
    expect(looksLikeProcessNarration("")).toBe(false);
  });
});

describe("isToolCallText", () => {
  it("flags XML-formatted tool calls in any case", () => {
    expect(isToolCallText("<tool_call>get_etf_info</tool_call>")).toBe(true);
    expect(isToolCallText("<function=foo>x</function>")).toBe(true);
    expect(isToolCallText("<FUNCTION_CALL>...</FUNCTION_CALL>")).toBe(true);
  });

  it("does not flag normal report text", () => {
    expect(isToolCallText("一、市场结构与量价诊断")).toBe(false);
  });
});

describe("isProcessOnlyReportText", () => {
  it("flags short Chinese 'now I will write' notes", () => {
    expect(isProcessOnlyReportText("现在所有数据已经获取完毕，下面开始撰写完整的分析报告。")).toBe(
      true,
    );
  });

  it("flags short English 'now let me write the report' notes", () => {
    // EN_DATA_READY_RE requires explicit phrasing like "retrieved data" /
    // "gathered information" / "data is ready" — generic "based on the data"
    // does not qualify, mirroring the Python contract.
    expect(
      isProcessOnlyReportText(
        "Now let me write the complete analysis report based on retrieved data.",
      ),
    ).toBe(true);
  });

  it("does not flag a real report once a 一、 heading is present", () => {
    const real = "现在我来撰写报告：\n\n一、市场结构与量价诊断\n趋势同步向上，资金净流入。";
    expect(isProcessOnlyReportText(real)).toBe(false);
  });

  it("ignores text longer than 700 chars", () => {
    const long = "数据已经获取，现在开始撰写报告。".repeat(100);
    expect(isProcessOnlyReportText(long)).toBe(false);
  });
});

describe("stripProcessOnlyReportPrefix", () => {
  it("removes a process line that occupies its own paragraph", () => {
    const text =
      "现在所有数据已经获取完毕，下面开始撰写完整的分析报告。\n\n一、市场结构与量价诊断\n趋势同步向上。";
    const out = stripProcessOnlyReportPrefix(text);
    expect(out.startsWith("一、市场结构与量价诊断")).toBe(true);
  });

  it("leaves clean text untouched", () => {
    expect(stripProcessOnlyReportPrefix("价格站稳50日均线上方，短中期均线同步向上。")).toBe(
      "价格站稳50日均线上方，短中期均线同步向上。",
    );
  });
});

describe("looksLikeUnexecutedToolIntent", () => {
  it("flags 'I will call get_etf_price_data' intent without execution", () => {
    expect(
      looksLikeUnexecutedToolIntent(
        "好的，接下来我将调用 get_etf_price_data 获取价格数据。",
        "get_etf_price_data",
      ),
    ).toBe(true);
    expect(
      looksLikeUnexecutedToolIntent(
        "我准备使用 get_etf_indicators 拉取技术指标。",
        "get_etf_indicators",
      ),
    ).toBe(true);
  });

  it("does not flag text inside a finished report (heading present)", () => {
    const finished =
      "一、市场结构与量价诊断\n10日EMA 3.617，由 get_etf_price_data 返回的最近价格为 3.582。";
    expect(looksLikeUnexecutedToolIntent(finished, "get_etf_price_data")).toBe(false);
  });

  it("returns false for missing tool name or empty text", () => {
    expect(looksLikeUnexecutedToolIntent("", "anything")).toBe(false);
    expect(looksLikeUnexecutedToolIntent("text", "")).toBe(false);
  });
});
