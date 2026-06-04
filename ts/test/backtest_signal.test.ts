import { describe, expect, it } from "vitest";
import { buildTraderBacktestSignal } from "../src/agents/helpers/backtest_signal.js";
import type { TraderProposal } from "../src/agents/schemas/trader_proposal.js";

function makePlan(overrides: Partial<TraderProposal> = {}): TraderProposal {
  return {
    thesis: "偏多结构稳固",
    execution_plan: "目标仓位30%，回踩50日均线加仓",
    risk_management: "跌破2.05元减仓",
    rating: "Buy",
    add_triggers: [],
    reduce_triggers: [],
    exit_triggers: [],
    rebalance_triggers: [],
    risk_controls: [],
    ...overrides,
  } as TraderProposal;
}

describe("buildTraderBacktestSignal", () => {
  it("returns a signal with rating from structured plan", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "rendered text",
      makePlan({ rating: "Buy" }),
    );
    expect(signal.rating).toBe("BUY");
    expect(signal.ticker).toBe("510300.SH");
    expect(signal.decision_date).toBe("2024-06-01");
    expect(signal.source).toBe("trader");
  });

  it("falls back to prose rating when structured is null", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "建议买入该ETF，目标仓位20%—30%。",
      null,
    );
    expect(signal.rating).toBe("BUY");
  });

  it("uses parsed trader output schema when structured plan is unavailable", () => {
    const rendered =
      "一、配置逻辑\n结构转弱。\n\n" +
      "四、执行倾向\n**减持**\n\n" +
      "**输出Schema**\n" +
      "agent: trader\n" +
      "allocation_action: UNDERWEIGHT\n" +
      'target_weight_band: "5-10%"\n' +
      "execution_timing: NEXT_CLOSE\n" +
      "execution_trigger_state: READY\n" +
      "risk_control_state: NORMAL\n" +
      'key_drivers: ["资金流转弱", "支撑破位", "风险预算收紧"]\n' +
      "confidence: 0.80";
    const signal = buildTraderBacktestSignal("510300.SH", "2024-06-01", rendered, null);
    expect(signal.rating).toBe("UNDERWEIGHT");
    expect(signal.target_weight_pct).toBe(7.5);
    expect(signal.target_weight_min_pct).toBe(5);
    expect(signal.target_weight_max_pct).toBe(10);
    expect(signal.weight_source).toBe("schema_field");
    expect(signal.execution_delay).toBe("next_close");
  });

  it("extracts target weight from structured target_weight_pct", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "",
      makePlan({ target_weight_pct: 25 }),
    );
    expect(signal.target_weight_pct).toBe(25);
    expect(signal.weight_source).toBe("structured_field");
  });

  it("calibrates structured target weight with risk budget and upstream signals", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "**输出Schema**\nagent: trader\nrisk_control_state: ELEVATED\nconfidence: 0.50",
      makePlan({ target_weight_pct: 30, confidence: 0.5 }),
      {
        maxDrawdownBudget: 0.08,
        agentSignals: {
          market_flow: {
            source: "market_flow",
            agent: "market_flow",
            fields: {
              agent: "market_flow",
              volatility_regime: "EXPANDING",
              flow_regime: "DISTRIBUTION",
            },
            raw: "",
          },
        },
      },
    );
    expect(signal.raw_target_weight_pct).toBe(30);
    expect(signal.target_weight_pct).toBeLessThan(30);
    expect(signal.position_sizing_multiplier).toBeLessThan(1);
    expect(signal.position_sizing_reasons?.join(" ")).toContain("估算回撤");
    expect(signal.position_sizing_inputs?.volatility_regime).toBe("EXPANDING");
    expect(signal.position_sizing_inputs?.flow_regime).toBe("DISTRIBUTION");
  });

  it("extracts target weight from structured target_weight_band", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "",
      makePlan({ target_weight_band: [20, 30] }),
    );
    expect(signal.target_weight_pct).toBe(25);
    expect(signal.target_weight_min_pct).toBe(20);
    expect(signal.target_weight_max_pct).toBe(30);
  });

  it("falls back to prose weight range when structured has no target", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "## 配置执行计划\n目标仓位 20%—30%，回踩支撑加仓。",
      makePlan({ target_weight_pct: null, execution_plan: "" }),
    );
    expect(signal.target_weight_pct).toBe(25);
    expect(signal.target_weight_min_pct).toBe(20);
    expect(signal.target_weight_max_pct).toBe(30);
    expect(signal.weight_source).toBe("parsed_target_range");
  });

  it("falls back to rating defaults when no weight is found anywhere", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "no weight info here",
      makePlan({ rating: "Hold", target_weight_pct: null, execution_plan: "" }),
    );
    expect(signal.target_weight_pct).toBe(15);
    expect(signal.weight_source).toBe("rating_map");
  });

  it("extracts prose conditions by hint", () => {
    const rendered =
      "## 配置执行计划\n" +
      "回踩50日均线加仓至目标配置。成交量达到近20日均量1.2倍时增持。\n" +
      "若跌破支撑则减仓，止损离场。调仓至更优标的。关注资金流向。\n" +
      "## 再平衡与风险控制\n风险控制：跌破2.05元止损。风控要求跟踪验证。";
    const signal = buildTraderBacktestSignal("510300.SH", "2024-06-01", rendered, null);

    expect(signal.add_conditions.length).toBeGreaterThanOrEqual(1);
    expect(signal.add_conditions.some((c) => c.includes("加仓"))).toBe(true);
    expect(signal.reduce_conditions.some((c) => c.includes("减仓"))).toBe(true);
    expect(signal.exit_conditions.some((c) => c.includes("止损离场"))).toBe(true);
    expect(signal.rebalance_conditions.some((c) => c.includes("调仓"))).toBe(true);
    expect(signal.risk_controls.some((c) => c.includes("风险"))).toBe(true);
    expect(signal.monitoring_points.some((c) => c.includes("关注"))).toBe(true);
  });

  it("extracts starter size text from rendered prose section", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "## 配置执行计划\n先建仓30%作为底仓。后续根据走势调整。",
      null,
    );
    expect(signal.starter_size_text).toContain("建仓");
  });

  it("extracts execution timing from structured plan", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "",
      makePlan({ execution_timing: "next_close" }),
    );
    expect(signal.execution_delay).toBe("next_close");
  });

  it("defaults execution timing to next_open", () => {
    const signal = buildTraderBacktestSignal("510300.SH", "2024-06-01", "", null);
    expect(signal.execution_delay).toBe("next_open");
  });

  it("populates signal_text_snapshot from action + risk text", () => {
    const signal = buildTraderBacktestSignal(
      "510300.SH",
      "2024-06-01",
      "## 配置执行计划\n加仓30%。\n## 再平衡与风险控制\n止损2.05元。",
      null,
    );
    expect(signal.signal_text_snapshot).toContain("加仓30%");
    expect(signal.signal_text_snapshot).toContain("止损2.05元");
  });

  it("coerces structured triggers from TraderProposal", () => {
    const plan = makePlan({
      add_triggers: [
        {
          metric: "close",
          op: ">=",
          threshold: 3.58,
          action: "add",
          note: "breakout add",
        } as TraderProposal["add_triggers"][number],
      ],
    });
    const signal = buildTraderBacktestSignal("510300.SH", "2024-06-01", "", plan);
    expect(signal.add_triggers.length).toBe(1);
    expect(signal.add_triggers[0]?.metric).toBe("close");
  });

  it("returns empty signal for empty input", () => {
    const signal = buildTraderBacktestSignal("unknown", "2024-01-01", "", null);
    expect(signal.rating).toBe("HOLD");
    expect(signal.target_weight_pct).toBe(15);
    expect(signal.add_triggers).toEqual([]);
  });

  it("parses English rating from prose", () => {
    const signal = buildTraderBacktestSignal(
      "SPY",
      "2024-06-01",
      "EXECUTION BIAS: **SELL**\nReduce all exposure.",
      null,
    );
    expect(signal.rating).toBe("SELL");
  });
});
