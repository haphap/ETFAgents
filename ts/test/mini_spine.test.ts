/**
 * Verifies the market_flow → trader graph wiring with a mocked LLM so we can
 * assert routing without network or credentials.
 *
 * The mock simulates two phases:
 *   1. market_flow: first invocation returns an AIMessage with one tool_call
 *      → the graph must route to ToolNode → market_flow re-entered with the
 *      tool result appended → second invocation returns the report text.
 *   2. trader: ``withStructuredOutput`` returns a hand-crafted TraderProposal.
 *
 * The test does not exercise real LLMs; it only proves the spine wiring is
 * correct.
 */

import { AIMessage, HumanMessage, ToolMessage } from "@langchain/core/messages";
import { tool } from "@langchain/core/tools";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import type { TraderProposal } from "../src/agents/schemas/trader_proposal.js";
import { buildMiniSpineGraph } from "../src/graph/mini_spine.js";

class FakeChatModel {
  invokeCalls = 0;
  structuredCalls = 0;

  bindTools(_tools: unknown): FakeChatModel {
    return this;
  }

  async invoke(messages: ReadonlyArray<unknown>): Promise<AIMessage> {
    this.invokeCalls++;
    // First market_flow call: emit a tool call.
    if (this.invokeCalls === 1) {
      return new AIMessage({
        content: "",
        tool_calls: [
          {
            id: "call_1",
            name: "get_etf_price_data",
            args: { ticker: "510300.SH", start_date: "2024-01-01", end_date: "2024-06-01" },
          },
        ],
      });
    }
    // Subsequent calls: detect we have a ToolMessage in history → emit final report.
    const sawToolMessage = messages.some((m) => m instanceof ToolMessage);
    if (sawToolMessage) {
      return new AIMessage(
        "概览段：偏多结构成立，趋势与量能同步确认。\n\n" +
          "一、市场结构与量价诊断\n" +
          "趋势同步向上，MACD 与 RSI 同步偏多。\n\n" +
          "二、交易确认与执行计划\n" +
          "回踩支撑加仓为主。\n\n" +
          "三、关键价位与条件情景推演\n" +
          "支撑 3.58 一带，跌破即转弱。\n\n" +
          "四、综合结论和指标总览\n" +
          "偏多配置。\n\n" +
          "| 指标 | 数值 |\n" +
          "| --- | --- |\n" +
          "| MACD | 0.05 |\n\n" +
          "**决策信号摘要**\n" +
          "方向: 偏多\n置信度: 中\n时间窗口: 1周\nETF传导路径: 量价 -> ETF\n核心证据: MACD改善\n最大反证条件: 放量跌破支撑\n配置含义: 增持ETF\n下一步观察: 成交量\n\n" +
          "**输出Schema**\n" +
          "agent: market_flow\n" +
          "price_regime: TREND_UP\n" +
          "flow_regime: ACCUMULATION\n" +
          "volatility_regime: NORMAL\n" +
          "execution_bias: ADD\n" +
          'key_levels: ["3.58"]\n' +
          'key_drivers: ["MACD改善", "量能确认", "支撑有效"]\n' +
          "confidence: 0.75",
      );
    }
    return new AIMessage("(unexpected) no tool result available");
  }

  withStructuredOutput<T>(_schema: unknown): { invoke: (msgs: unknown) => Promise<T> } {
    this.structuredCalls++;
    const proposal: TraderProposal = {
      thesis: "偏多结构稳固",
      execution_plan: "目标仓位 30%，回踩 50 日均线加仓",
      risk_management: "跌破 2.05 元减仓",
      rating: "Buy",
      key_drivers: ["趋势改善", "量能确认", "风险可控"],
      add_triggers: [],
      reduce_triggers: [],
      exit_triggers: [],
      rebalance_triggers: [],
      risk_controls: [],
    } as TraderProposal;
    return { invoke: async () => proposal as T };
  }
}

const PRICE_TOOL = tool(
  async (input) => {
    const { ticker } = input as { ticker: string };
    return `Date,Close\n2024-06-01,2.10\n# tool ran for ${ticker}`;
  },
  {
    name: "get_etf_price_data",
    description: "fake price data",
    schema: z.object({
      ticker: z.string(),
      start_date: z.string(),
      end_date: z.string(),
    }),
  },
);

describe("buildMiniSpineGraph", () => {
  it("routes market_flow → tools → market_flow → trader and finishes with structured output", async () => {
    const llm = new FakeChatModel();
    const graph = buildMiniSpineGraph({
      // Cast: FakeChatModel implements just the surface the graph needs.
      llm: llm as unknown as Parameters<typeof buildMiniSpineGraph>[0]["llm"],
      marketFlowTools: [PRICE_TOOL],
      // The graph routing test does not exercise the LLM-judge / refine
      // step (covered by validate_refine.test.ts); disabling avoids the
      // FakeChatModel being asked to simulate judge responses.
      promptContext: { language: "Chinese", validationMode: "disabled" },
    });

    const result = await graph.invoke({
      messages: [new HumanMessage("510300.SH")],
      asset_of_interest: "510300.SH",
      trade_date: "2024-06-01",
    });

    // The market_flow node was called twice (once with tool_call, once with tool result)
    expect(llm.invokeCalls).toBeGreaterThanOrEqual(2);
    expect(llm.structuredCalls).toBe(1);

    expect(result.market_flow_report).toContain("一、市场结构与量价诊断");
    expect(result.market_flow_report).not.toContain("输出Schema");
    expect(result.market_flow_report).not.toContain("决策信号摘要");
    expect(result.agent_signals.market_flow?.fields.price_regime).toBe("TREND_UP");
    expect(result.trader_allocation_plan).toContain("一、配置逻辑");
    expect(result.trader_allocation_plan).toContain("**买入**");
    expect(result.trader_allocation_plan).not.toContain("输出Schema");
    expect(result.agent_signals.trader?.fields.allocation_action).toBe("BUY");
    expect(result.sender).toBe("Trader");
  });
});
