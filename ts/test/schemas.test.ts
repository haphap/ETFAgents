import { describe, expect, it } from "vitest";
import { appendTraderOutputSchema, renderTraderProposal } from "../src/agents/helpers/render.js";
import { isChinese, localizeRating } from "../src/agents/schemas/rating.js";
import { TraderProposalSchema } from "../src/agents/schemas/trader_proposal.js";

describe("rating helpers", () => {
  it("localizes to Chinese terms when language is Chinese", () => {
    expect(localizeRating("Buy", "Chinese")).toBe("买入");
    expect(localizeRating("Hold", "中文")).toBe("持有");
    expect(localizeRating("Sell", "zh-cn")).toBe("卖出");
  });

  it("uppercases the English rating otherwise", () => {
    expect(localizeRating("Buy", "English")).toBe("BUY");
    expect(localizeRating("Hold", "")).toBe("HOLD");
  });

  it("isChinese is permissive about the canonical aliases", () => {
    expect(isChinese("Chinese")).toBe(true);
    expect(isChinese("中文")).toBe(true);
    expect(isChinese("zh")).toBe(true);
    expect(isChinese("English")).toBe(false);
    expect(isChinese(undefined)).toBe(false);
  });
});

describe("TraderProposalSchema", () => {
  it("parses a minimal Pydantic-equivalent payload with default arrays", () => {
    const parsed = TraderProposalSchema.parse({
      thesis: "thesis text",
      execution_plan: "execution text",
      risk_management: "risk text",
      rating: "Buy",
    });
    expect(parsed.add_triggers).toEqual([]);
    expect(parsed.reduce_triggers).toEqual([]);
    expect(parsed.rating).toBe("Buy");
    expect(parsed.target_weight_pct).toBeUndefined();
  });

  it("accepts populated structured fields and validates trigger shapes", () => {
    const parsed = TraderProposalSchema.parse({
      thesis: "t",
      execution_plan: "e",
      risk_management: "r",
      rating: "Overweight",
      target_weight_pct: 30,
      execution_timing: "next_open",
      add_triggers: [
        { metric: "close_50_sma", op: ">=", threshold: 2.05, action: "add", note: "n" },
      ],
      risk_controls: [
        { metric: "pnl_pct", op: "<=", threshold: -5, action: "exit", note: "stop loss" },
      ],
    });
    expect(parsed.target_weight_pct).toBe(30);
    expect(parsed.add_triggers[0]?.metric).toBe("close_50_sma");
    expect(parsed.risk_controls[0]?.action).toBe("exit");
  });

  it("rejects an unknown rating", () => {
    expect(() =>
      TraderProposalSchema.parse({
        thesis: "t",
        execution_plan: "e",
        risk_management: "r",
        rating: "BuyABit",
      }),
    ).toThrow();
  });
});

describe("renderTraderProposal", () => {
  const proposal = TraderProposalSchema.parse({
    thesis: "偏多结构稳固，确认信号同时出现。",
    execution_plan: "目标仓位 30%，回踩 50 日均线加仓。",
    risk_management: "跌破支撑 2.05 元先减仓 50%，跌破 2.00 元清仓。",
    rating: "Buy",
  });

  it("emits the four canonical Chinese sections in order with localized rating", () => {
    const rendered = renderTraderProposal(proposal, { language: "Chinese" });
    expect(rendered).toContain("一、配置逻辑");
    expect(rendered).toContain("二、配置执行计划");
    expect(rendered).toContain("三、再平衡与风险控制");
    expect(rendered).toContain("四、执行倾向");
    expect(rendered).toContain("**买入**");
    // Section ordering must match the contract Python's render_trader_proposal enforces
    const a = rendered.indexOf("一、配置逻辑");
    const b = rendered.indexOf("二、配置执行计划");
    const c = rendered.indexOf("三、再平衡与风险控制");
    const d = rendered.indexOf("四、执行倾向");
    expect(a).toBeLessThan(b);
    expect(b).toBeLessThan(c);
    expect(c).toBeLessThan(d);
  });

  it("emits the English EXECUTION BIAS line when language is English", () => {
    const rendered = renderTraderProposal(proposal, { language: "English" });
    expect(rendered).toContain("## ETF Allocation Thesis");
    expect(rendered).toContain("EXECUTION BIAS: **BUY**");
  });

  it("appends a concrete trader output schema after the execution bias", () => {
    const withSchema = appendTraderOutputSchema(
      renderTraderProposal(proposal, { language: "Chinese" }),
      proposal,
      "Chinese",
    );
    expect(withSchema).toContain("**输出Schema**");
    expect(withSchema).toContain("agent: trader");
    expect(withSchema).toContain("allocation_action: BUY");
    expect(withSchema).toContain('target_weight_band: "UNKNOWN"');
    expect(withSchema).toContain("confidence:");
    expect(withSchema.indexOf("四、执行倾向")).toBeLessThan(withSchema.indexOf("**输出Schema**"));
    expect(appendTraderOutputSchema(withSchema, proposal, "Chinese")).toBe(withSchema);
  });

  it("replaces an incomplete trader output schema", () => {
    const partial = `${renderTraderProposal(proposal, { language: "Chinese" })}\n\n**输出Schema**\nagent: trader`;
    const withSchema = appendTraderOutputSchema(partial, proposal, "Chinese");
    expect(withSchema.match(/\*\*输出Schema\*\*/g)?.length).toBe(1);
    expect(withSchema).toContain("allocation_action: BUY");
    expect(withSchema).toContain("key_drivers:");
  });
});
