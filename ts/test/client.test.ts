import { describe, expect, it } from "vitest";
import {
  BridgeApi,
  BridgeClient,
  BridgeTransportError,
  INVALID_PARAMS,
  METHOD_NOT_FOUND,
  RpcError,
} from "../src/bridge/index.js";

/**
 * Black-box client tests. They drive the real `etfagents.bridge` subprocess,
 * proving that the TS client's framing, correlation, error mapping, and
 * shutdown semantics line up with the Python server.
 */

describe("BridgeClient against real sidecar", () => {
  it("correlates concurrent requests by id", async () => {
    const client = new BridgeClient();
    try {
      await client.start();
      // Fire all four in parallel — the client must demux responses back to
      // the correct promise.
      const [list, cfg, stats, user] = await Promise.all([
        client.call<unknown[]>("tools.list", {}),
        client.call<Record<string, unknown>>("config.default", {}),
        client.call<Record<string, unknown>>("cache.stats", {}),
        client.call<{ user: string }>("paper.current_user", {}),
      ]);
      expect(Array.isArray(list)).toBe(true);
      expect(list.length).toBeGreaterThanOrEqual(20);
      expect(cfg.llm_provider).toBeTypeOf("string");
      expect(stats.total_mb).toBeTypeOf("number");
      expect(user.user).toBe("default");
    } finally {
      await client.close();
    }
  });

  it("maps {error} envelope to RpcError with code/method", async () => {
    const client = new BridgeClient();
    try {
      await client.start();
      await expect(client.call("does.not.exist", {})).rejects.toMatchObject({
        name: "RpcError",
        code: METHOD_NOT_FOUND,
        method: "does.not.exist",
      });
    } finally {
      await client.close();
    }
  });

  it("maps invalid-params errors per JSON-RPC spec", async () => {
    const client = new BridgeClient();
    try {
      await client.start();
      const err = await client.call("tools.call", { args: {} }).catch((e) => e);
      expect(err).toBeInstanceOf(RpcError);
      expect((err as RpcError).code).toBe(INVALID_PARAMS);
    } finally {
      await client.close();
    }
  });

  it("times out a call when timeoutMs is short", async () => {
    const client = new BridgeClient();
    try {
      await client.start();
      // Use a 1ms timeout to force a timeout regardless of how fast Python
      // would normally respond.
      await expect(client.call("tools.list", {}, { timeoutMs: 1 })).rejects.toBeInstanceOf(
        BridgeTransportError,
      );
    } finally {
      await client.close();
    }
  });

  it("BridgeApi ergonomic helpers cover the same surface", async () => {
    const client = new BridgeClient();
    const api = new BridgeApi(client);
    try {
      await client.start();
      const tools = await api.toolsList();
      expect(tools.length).toBeGreaterThanOrEqual(20);
      const stats = await api.cacheStats();
      expect(stats.total_mb).toBeTypeOf("number");
      const cfg = await api.configGet();
      expect(cfg.data_vendors).toBeDefined();
    } finally {
      await client.close();
    }
  });
});
