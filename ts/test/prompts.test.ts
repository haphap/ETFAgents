import { describe, expect, it } from "vitest";
import { buildAggressiveDebatorSystemMessage } from "../src/agents/prompts/aggressive_debator.js";
import { buildBearResearcherSystemMessage } from "../src/agents/prompts/bear_researcher.js";
import { buildBullResearcherSystemMessage } from "../src/agents/prompts/bull_researcher.js";
import { buildCatalystSentimentSystemMessage } from "../src/agents/prompts/catalyst_sentiment.js";
import { buildConservativeDebatorSystemMessage } from "../src/agents/prompts/conservative_debator.js";
import { buildHoldingsIndustrySystemMessage } from "../src/agents/prompts/holdings_industry.js";
import { buildMacroRegimeSystemMessage } from "../src/agents/prompts/macro_regime.js";
import { buildMarketFlowSystemMessage } from "../src/agents/prompts/market_flow.js";
import { buildMesoCommoditySystemMessage } from "../src/agents/prompts/meso_commodity.js";
import { buildNeutralDebatorSystemMessage } from "../src/agents/prompts/neutral_debator.js";
import { buildPortfolioManagerSystemMessage } from "../src/agents/prompts/portfolio_manager.js";
import { buildResearchManagerSystemMessage } from "../src/agents/prompts/research_manager.js";
import {
  buildInstrumentContext,
  collapseBlankLines,
  dateDaysBefore,
  extractDecisionSignalSummary,
  getCollaborationStopInstruction,
  getDecisionSignalSummaryInstruction,
  getLanguageInstruction,
  reportForDecisionContext,
  truncateForPrompt,
} from "../src/agents/prompts/shared.js";
import { buildTopHoldingsSystemMessage } from "../src/agents/prompts/top_holdings.js";
import {
  buildTraderSystemMessage,
  STRUCTURED_FIELD_POPULATION_INSTRUCTION,
  stripStructuredOnlyText,
} from "../src/agents/prompts/trader.js";

describe("prompt helpers", () => {
  it("getLanguageInstruction returns empty for English", () => {
    expect(getLanguageInstruction({ language: "English" })).toBe("");
    expect(getLanguageInstruction({ language: "english" })).toBe("");
  });

  it("getLanguageInstruction surfaces Chinese rules verbatim", () => {
    const out = getLanguageInstruction({ language: "Chinese" });
    expect(out).toContain("Write your entire response in Chinese");
    // Chinese numbering hierarchy must be preserved verbatim — these tokens
    // are the contract many downstream regex post-processors rely on.
    expect(out).toContain("一、二、三、");
    expect(out).toContain("（一）（二）（三）");
    expect(out).toContain("① ② ③");
  });

  it("getCollaborationStopInstruction picks the localized variant", () => {
    expect(getCollaborationStopInstruction({ language: "Chinese" })).toContain("最终配置建议");
    expect(getCollaborationStopInstruction({ language: "English" })).toContain(
      "FINAL ALLOCATION PROPOSAL",
    );
  });

  it("buildInstrumentContext keeps the exchange suffix instruction (avoids 点 substitution)", () => {
    const context = buildInstrumentContext("510300.SH");
    expect(context).toContain("510300.SH");
    expect(context).toContain("never replace `.` with `点`");
  });

  it("collapseBlankLines collapses 3+ newlines into 2", () => {
    expect(collapseBlankLines("a\n\n\n\nb")).toBe("a\n\nb");
    expect(collapseBlankLines("\r\nx\r\n\r\ny\r\n")).toBe("x\n\ny");
    expect(collapseBlankLines("")).toBe("");
  });

  it("truncateForPrompt preserves opening and closing excerpts with a clear marker", () => {
    const long = `OPENING-${"x".repeat(20_000)}-CLOSING`;
    const out = truncateForPrompt(long, { language: "Chinese", reportContextCharLimit: 1000 });
    expect(out.length).toBeLessThanOrEqual(1000);
    expect(out).toContain("[Content trimmed for prompt");
    expect(out).toContain("[Opening excerpt]");
    expect(out).toContain("[Closing excerpt]");
    expect(out).toContain("OPENING-");
    expect(out).toContain("-CLOSING");
  });

  it("truncateForPrompt stays within small user-configured limits", () => {
    const report =
      "OPEN\n" +
      "x".repeat(8_000) +
      "\n**决策信号摘要**\n方向: 偏多\n置信度: 中\n时间窗口: 1周\nETF传导路径: 资金流 -> ETF\n核心证据: 份额增加\n最大反证条件: 放量跌破支撑\n配置含义: 增持ETF\n下一步观察: 成交量\n" +
      "CLOSE";
    const out = truncateForPrompt(report, { language: "Chinese", reportContextCharLimit: 250 });
    expect(out.length).toBeLessThanOrEqual(250);
    expect(out).toContain("[Decision signal summary]");
  });

  it("extractDecisionSignalSummary finds the final summary block", () => {
    const report =
      "正文很长。\n\n**决策信号摘要**\n" +
      "方向: 偏多\n置信度: 中\n时间窗口: 1周\nETF传导路径: 资金流 -> ETF\n" +
      "核心证据: 成交量放大\n最大反证条件: 跌破支撑\n配置含义: 增持ETF\n下一步观察: 份额变化";
    expect(extractDecisionSignalSummary(report)).toContain("方向: 偏多");
  });

  it("reportForDecisionContext prioritizes the decision signal summary when trimming", () => {
    const report =
      "OPEN\n" +
      "x".repeat(8_000) +
      "\n**决策信号摘要**\n方向: 偏空\n置信度: 高\n时间窗口: 1周\nETF传导路径: 利率 -> ETF\n核心证据: 量能恶化\n最大反证条件: 放量收复均线\n配置含义: 减持ETF\n下一步观察: 成交量";
    const out = reportForDecisionContext(report, { language: "Chinese" }, 1_200);
    expect(out.length).toBeLessThanOrEqual(1_200);
    expect(out).toContain("[Decision signal summary]");
    expect(out).toContain("方向: 偏空");
    expect(out).toContain("OPEN");
  });

  it("getDecisionSignalSummaryInstruction defines the stable Chinese contract", () => {
    const out = getDecisionSignalSummaryInstruction({ language: "Chinese" });
    expect(out).toContain("**决策信号摘要**");
    expect(out).toContain("方向、置信度、时间窗口、ETF传导路径");
  });

  it("dateDaysBefore is timezone-stable for ISO yyyy-mm-dd", () => {
    expect(dateDaysBefore("2024-06-15", 30)).toBe("2024-05-16");
    expect(dateDaysBefore("2024-01-01", 1)).toBe("2023-12-31");
    // Bad input is passed through (matches Python's defensive try/except)
    expect(dateDaysBefore("not-a-date", 30)).toBe("not-a-date");
  });
});

describe("market_flow prompt", () => {
  it("contains the four-section contract verbatim", () => {
    const sys = buildMarketFlowSystemMessage({ language: "Chinese" });
    expect(sys).toContain("一、市场结构与量价诊断");
    expect(sys).toContain("二、交易确认与执行计划");
    expect(sys).toContain("三、关键价位与条件情景推演");
    expect(sys).toContain("四、综合结论和指标总览");
    // Indicator IDs must be embedded — drift here means tools won't match
    expect(sys).toContain("close_10_ema");
    expect(sys).toContain("close_200_sma");
    expect(sys).toContain("rsi");
  });
});

describe("front-line analyst prompt rewrites", () => {
  it("uses compact decision frameworks instead of long sample reports", () => {
    const ctx = { language: "Chinese" };
    const catalystData = {
      etfInfo: "",
      etfHoldings: "",
      tickerNews: "",
      holdingsNews: "",
      globalNews: "",
    };
    const prompts = [
      buildMarketFlowSystemMessage(ctx),
      buildMacroRegimeSystemMessage(ctx),
      buildMesoCommoditySystemMessage(ctx),
      buildCatalystSentimentSystemMessage(ctx, catalystData),
      buildHoldingsIndustrySystemMessage(ctx),
      buildTopHoldingsSystemMessage(ctx),
    ];

    for (const prompt of prompts) {
      expect(prompt).toContain("决策框架");
      expect(prompt).toContain("ETF整体仓位");
      expect(prompt).not.toContain("完整报告示例");
      expect(prompt).not.toContain("示例合约");
      expect(prompt).not.toContain("正面示例");
      expect(prompt).not.toContain("反面示例");
    }
  });
});

describe("trader prompt", () => {
  it("includes the three structured-only sentences exactly once each", () => {
    const sys = buildTraderSystemMessage({ language: "Chinese" });
    expect(sys.split(STRUCTURED_FIELD_POPULATION_INSTRUCTION).length - 1).toBe(1);
  });

  it("stripStructuredOnlyText removes all three structured-only sentences", () => {
    const sys = buildTraderSystemMessage({ language: "Chinese" });
    const stripped = stripStructuredOnlyText(sys);
    expect(stripped).not.toContain(STRUCTURED_FIELD_POPULATION_INSTRUCTION);
    expect(stripped).not.toContain(
      "execution_timing, add_triggers, reduce_triggers, exit_triggers, rebalance_triggers",
    );
    // The non-structured guidance must survive
    expect(stripped).toContain("配置执行计划");
  });
});

describe("visible agent prompts", () => {
  it("inherit the configured Chinese output language", () => {
    const ctx = { language: "Chinese" };
    const catalystData = {
      etfInfo: "",
      etfHoldings: "",
      tickerNews: "",
      holdingsNews: "",
      globalNews: "",
    };
    const prompts = [
      ["market_flow", buildMarketFlowSystemMessage(ctx)],
      ["macro_regime", buildMacroRegimeSystemMessage(ctx)],
      ["meso_commodity", buildMesoCommoditySystemMessage(ctx)],
      ["catalyst_sentiment", buildCatalystSentimentSystemMessage(ctx, catalystData)],
      ["holdings_industry", buildHoldingsIndustrySystemMessage(ctx)],
      ["top_holdings", buildTopHoldingsSystemMessage(ctx)],
      ["bull_researcher", buildBullResearcherSystemMessage(ctx)],
      ["bear_researcher", buildBearResearcherSystemMessage(ctx)],
      ["research_manager", buildResearchManagerSystemMessage(ctx)],
      ["trader", buildTraderSystemMessage(ctx)],
      ["aggressive_debator", buildAggressiveDebatorSystemMessage(ctx)],
      ["conservative_debator", buildConservativeDebatorSystemMessage(ctx)],
      ["neutral_debator", buildNeutralDebatorSystemMessage(ctx)],
      ["portfolio_manager", buildPortfolioManagerSystemMessage(ctx)],
    ] as const;

    for (const [name, prompt] of prompts) {
      expect({
        name,
        hasChineseLanguageInstruction: prompt.includes("Write your entire response in Chinese"),
      }).toEqual({ name, hasChineseLanguageInstruction: true });
    }
  });

  it("requires decision signal summaries from report-producing agents", () => {
    const ctx = { language: "Chinese" };
    const catalystData = {
      etfInfo: "",
      etfHoldings: "",
      tickerNews: "",
      holdingsNews: "",
      globalNews: "",
    };
    const prompts = [
      buildMarketFlowSystemMessage(ctx),
      buildMacroRegimeSystemMessage(ctx),
      buildMesoCommoditySystemMessage(ctx),
      buildCatalystSentimentSystemMessage(ctx, catalystData),
      buildHoldingsIndustrySystemMessage(ctx),
      buildTopHoldingsSystemMessage(ctx),
      buildBullResearcherSystemMessage(ctx),
      buildBearResearcherSystemMessage(ctx),
      buildResearchManagerSystemMessage(ctx),
      buildAggressiveDebatorSystemMessage(ctx),
      buildConservativeDebatorSystemMessage(ctx),
      buildNeutralDebatorSystemMessage(ctx),
      buildPortfolioManagerSystemMessage(ctx),
    ];

    for (const prompt of prompts) {
      expect(prompt).toContain("**决策信号摘要**");
      expect(prompt).toContain("最大反证条件");
      expect(prompt).toContain("ETF整体仓位");
    }
  });

  it("requires MOSAIC-style output schemas from every visible agent prompt", () => {
    const ctx = { language: "Chinese" };
    const catalystData = {
      etfInfo: "",
      etfHoldings: "",
      tickerNews: "",
      holdingsNews: "",
      globalNews: "",
    };
    const prompts = [
      ["market_flow", buildMarketFlowSystemMessage(ctx)],
      ["macro_regime", buildMacroRegimeSystemMessage(ctx)],
      ["meso_commodity", buildMesoCommoditySystemMessage(ctx)],
      ["catalyst_sentiment", buildCatalystSentimentSystemMessage(ctx, catalystData)],
      ["holdings_industry", buildHoldingsIndustrySystemMessage(ctx)],
      ["top_holdings", buildTopHoldingsSystemMessage(ctx)],
      ["bull_researcher", buildBullResearcherSystemMessage(ctx)],
      ["bear_researcher", buildBearResearcherSystemMessage(ctx)],
      ["research_manager", buildResearchManagerSystemMessage(ctx)],
      ["trader", buildTraderSystemMessage(ctx)],
      ["aggressive_debator", buildAggressiveDebatorSystemMessage(ctx)],
      ["conservative_debator", buildConservativeDebatorSystemMessage(ctx)],
      ["neutral_debator", buildNeutralDebatorSystemMessage(ctx)],
      ["portfolio_manager", buildPortfolioManagerSystemMessage(ctx)],
    ] as const;

    for (const [name, prompt] of prompts) {
      expect({
        name,
        hasOutputSchema: prompt.includes("输出Schema"),
        hasAgentField: prompt.includes("agent:"),
        hasConfidenceField: prompt.includes("confidence: <0-1>"),
      }).toEqual({
        name,
        hasOutputSchema: true,
        hasAgentField: true,
        hasConfidenceField: true,
      });
    }
    expect(buildMesoCommoditySystemMessage(ctx)).toContain(
      "oil_regime: BACKWARDATION | CONTANGO | NEUTRAL",
    );
    expect(buildMesoCommoditySystemMessage(ctx)).toContain(
      "china_demand_signal: ACCELERATING | STEADY | DECELERATING",
    );
  });

  it("uses Chinese source prompts for the risk team in Chinese mode", () => {
    const ctx = { language: "Chinese" };
    expect(buildAggressiveDebatorSystemMessage(ctx)).toContain("你是激进风险分析师");
    expect(buildConservativeDebatorSystemMessage(ctx)).toContain("你是保守风险分析师");
    expect(buildNeutralDebatorSystemMessage(ctx)).toContain("你是中性风险分析师");
  });
});
