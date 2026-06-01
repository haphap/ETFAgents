import { describe, expect, it } from "vitest";
import { extractHoldingNames } from "../src/agents/nodes/catalyst_sentiment.js";

describe("catalyst prefetch — extractHoldingNames", () => {
  it("pulls the top-N constituent names from a holdings CSV (skips comments)", () => {
    const csv = `# ETF holdings
code,name,weight
600519.SH,贵州茅台,5.1
000858.SZ,五粮液,3.2
601318.SH,中国平安,2.8
600036.SH,招商银行,2.1
`;
    expect(extractHoldingNames(csv)).toEqual(["贵州茅台", "五粮液", "中国平安"]);
    expect(extractHoldingNames(csv, 2)).toEqual(["贵州茅台", "五粮液"]);
  });

  it("supports the stk_name / sec_name column aliases", () => {
    expect(extractHoldingNames("ts_code,stk_name\n1,Alpha\n2,Beta\n")).toEqual(["Alpha", "Beta"]);
    expect(extractHoldingNames("code,sec_name\n1,Gamma\n")).toEqual(["Gamma"]);
  });

  it("returns an empty list when there is no name column or no holdings", () => {
    expect(extractHoldingNames("")).toEqual([]);
    expect(extractHoldingNames("No ETF holdings found.")).toEqual([]);
    expect(extractHoldingNames("code,weight\n600519.SH,5.1\n")).toEqual([]);
  });
});
