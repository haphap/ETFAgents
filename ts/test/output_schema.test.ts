import { describe, expect, it } from "vitest";
import {
  formatAgentSignalsForPrompt,
  parseAgentOutputSchema,
  signalUpdate,
  stripAgentMachineBlocks,
} from "../src/agents/helpers/output_schema.js";

describe("agent output schema parser", () => {
  it("parses a MOSAIC-style Chinese schema block into typed fields", () => {
    const report =
      "正文。\n\n" +
      "**决策信号摘要**\n方向: 中性\n置信度: 中\n时间窗口: 1周\nETF传导路径: 商品 -> ETF\n核心证据: 铜价上涨\n最大反证条件: 需求转弱\n配置含义: 持有ETF\n下一步观察: 库存\n\n" +
      "**输出Schema**\n" +
      "agent: commodities\n" +
      "oil_regime: BACKWARDATION\n" +
      "metals_regime: RISK_ON\n" +
      "ag_regime: BALANCED\n" +
      "china_demand_signal: STEADY\n" +
      'key_drivers: ["铜库存下降", "中国需求稳定", "油价曲线偏紧"]\n' +
      "confidence: 0.68";

    const parsed = parseAgentOutputSchema(report, "meso_commodity");
    expect(parsed?.source).toBe("meso_commodity");
    expect(parsed?.agent).toBe("commodities");
    expect(parsed?.fields.oil_regime).toBe("BACKWARDATION");
    expect(parsed?.fields.confidence).toBe(0.68);
    expect(parsed?.key_drivers).toEqual(["铜库存下降", "中国需求稳定", "油价曲线偏紧"]);
    expect(parsed?.decision_summary?.方向).toBe("中性");
    expect(parsed?.decision_summary_raw).not.toContain("输出Schema");
  });

  it("strips decision summary and output schema from visible report text", () => {
    const report =
      "正文第一段。\n\n四、综合结论和指标总览\n\n结论段。\n\n" +
      "**决策信号摘要**\n方向: 偏多\n置信度: 高\n\n" +
      "**输出Schema**\nagent: market_flow\nconfidence: 0.8";
    const visible = stripAgentMachineBlocks(report);
    expect(visible).toContain("四、综合结论和指标总览");
    expect(visible).toContain("结论段。");
    expect(visible).not.toContain("决策信号摘要");
    expect(visible).not.toContain("输出Schema");
  });

  it("formats parsed signals as a compact machine-readable context block", () => {
    const signals = signalUpdate(
      "market_flow",
      "**决策信号摘要**\n方向: 偏多\n置信度: 高\n配置含义: 增持ETF\n\n" +
        "**输出Schema**\nagent: market_flow\nprice_regime: TREND_UP\nconfidence: 0.75",
    );
    const block = formatAgentSignalsForPrompt(signals, { language: "Chinese" });
    expect(block).toContain("## 结构化信号");
    expect(block).toContain("### market_flow");
    expect(block).toContain("决策信号摘要");
    expect(block).toContain("方向: 偏多");
    expect(block).toContain("输出Schema字段");
    expect(block).toContain("price_regime: TREND_UP");
    expect(block).toContain("confidence: 0.75");
  });
});
