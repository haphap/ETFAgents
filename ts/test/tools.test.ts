import { describe, expect, it } from "vitest";
import {
  BridgeApi,
  BridgeClient,
  bridgeToolFromMetadata,
  type JsonSchemaObject,
  jsonSchemaToZod,
  listBridgeTools,
  pickBridgeTools,
  type ToolMetadata,
} from "../src/bridge/index.js";

describe("jsonSchemaToZod", () => {
  it("parses Pydantic-style flat object schemas with required + optional fields", () => {
    const schema: JsonSchemaObject = {
      type: "object",
      properties: {
        ticker: { type: "string", description: "Ticker symbol" },
        start_date: { type: "string", description: "Start" },
        look_back_days: { type: "integer", description: "Days", default: 7 },
      },
      required: ["ticker", "start_date"],
    };
    const zod = jsonSchemaToZod(schema);
    expect(() => zod.parse({ ticker: "X", start_date: "2024-01-01" })).not.toThrow();
    // Default applied
    const parsed = zod.parse({ ticker: "X", start_date: "2024-01-01" });
    expect(parsed).toMatchObject({ look_back_days: 7 });
    // Required missing → throws
    expect(() => zod.parse({ ticker: "X" })).toThrow();
    // Wrong type rejected
    expect(() => zod.parse({ ticker: 1, start_date: "2024-01-01" })).toThrow();
  });

  it("rejects unsupported features with an actionable error", () => {
    expect(() =>
      jsonSchemaToZod({
        type: "object",
        properties: { whatever: { type: "string", anyOf: [{ type: "string" }] } },
      }),
    ).toThrow(/anyOf/);
    expect(() =>
      jsonSchemaToZod({
        type: "object",
        // biome-ignore lint/suspicious/noExplicitAny: deliberately invalid input
        properties: { weird: { type: "array" as any } },
      }),
    ).toThrow(/unsupported type/);
  });
});

describe("bridgeToolFromMetadata (unit)", () => {
  it("creates a structured tool whose name/description match metadata", () => {
    const fakeApi = {
      toolsCall: async () => ({ text: "irrelevant" }),
    } as unknown as BridgeApi;
    const meta: ToolMetadata = {
      name: "demo_tool",
      description: "A demo tool",
      args_schema: {
        type: "object",
        properties: { ticker: { type: "string" } },
        required: ["ticker"],
      },
    };
    const tool = bridgeToolFromMetadata(fakeApi, meta);
    expect(tool.name).toBe("demo_tool");
    expect(tool.description).toBe("A demo tool");
  });

  it("invoking the tool routes through BridgeApi.toolsCall and returns the text", async () => {
    const calls: Array<{ name: string; args: unknown; ctx: unknown }> = [];
    const fakeApi = {
      toolsCall: async (name: string, args: unknown, ctx: unknown) => {
        calls.push({ name, args, ctx });
        return { text: `ok:${name}` };
      },
    } as unknown as BridgeApi;
    const meta: ToolMetadata = {
      name: "echo",
      description: "echo",
      args_schema: {
        type: "object",
        properties: { ticker: { type: "string" } },
        required: ["ticker"],
      },
    };
    const tool = bridgeToolFromMetadata(fakeApi, meta, {
      context: { mode: "backtest", as_of_date: "2024-06-01" },
    });
    const result = await tool.invoke({ ticker: "510300.SH" });
    expect(result).toBe("ok:echo");
    expect(calls).toHaveLength(1);
    expect(calls[0]?.name).toBe("echo");
    expect(calls[0]?.args).toEqual({ ticker: "510300.SH" });
    expect(calls[0]?.ctx).toEqual({ mode: "backtest", as_of_date: "2024-06-01" });
  });
});

describe("listBridgeTools / pickBridgeTools against real sidecar", () => {
  it("converts every Pydantic schema returned by tools.list into a usable tool", async () => {
    const client = new BridgeClient();
    const api = new BridgeApi(client);
    try {
      await client.start();
      const tools = await listBridgeTools(api);
      expect(tools.length).toBeGreaterThanOrEqual(20);
      const names = tools.map((t) => t.name).sort();
      expect(names).toContain("get_etf_info");
      expect(names).toContain("get_news");
      // Every tool must have a non-empty schema (input validation works)
      for (const tool of tools) {
        expect(tool.name).toBeTypeOf("string");
        expect(tool.description).toBeTypeOf("string");
      }
    } finally {
      await client.close();
    }
  });

  it("pickBridgeTools surfaces missing names with the available list", async () => {
    const client = new BridgeClient();
    const api = new BridgeApi(client);
    try {
      await client.start();
      await expect(pickBridgeTools(api, ["get_etf_info", "fake_tool"])).rejects.toThrow(
        /fake_tool/,
      );
    } finally {
      await client.close();
    }
  });
});
