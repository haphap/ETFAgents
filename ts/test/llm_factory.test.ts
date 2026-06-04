import { describe, expect, it } from "vitest";
import type { EtfAgentsConfig } from "../src/bridge/types.js";
import { createLlmFromConfig } from "../src/llm/factory.js";

describe("LLM factory", () => {
  it("uses the Python-compatible vLLM default endpoint", () => {
    const config = {
      llm_provider: "vllm",
      deep_think_llm: "local-model",
      quick_think_llm: "local-model",
    } as EtfAgentsConfig;

    const handle = createLlmFromConfig(config, { provider: "vllm" });

    expect(handle.baseUrl).toBe("http://127.0.0.1:8020/v1");
  });
});
