/**
 * Build a LangChain ChatOpenAI client from the bridge's active config.
 *
 * Phase 1 only supports OpenAI-compatible providers (openai, xai, openrouter,
 * ollama, vllm, minimax, deepseek). Native Anthropic/Google clients are
 * deferred to Phase 2 alongside the rest of the agent porting work.
 */

import { ChatOpenAI } from "@langchain/openai";
import type { EtfAgentsConfig } from "../bridge/types.js";

/** Providers wired through the OpenAI-compatible Chat Completions API. */
const OPENAI_COMPATIBLE = new Set([
  "openai",
  "xai",
  "openrouter",
  "ollama",
  "vllm",
  "minimax",
  "deepseek",
]);

/** Default base URLs per provider when the bridge config doesn't specify one. */
const DEFAULT_BASE_URL: Record<string, string | undefined> = {
  openai: undefined, // SDK default
  xai: "https://api.x.ai/v1",
  openrouter: "https://openrouter.ai/api/v1",
  ollama: "http://localhost:11434/v1",
  vllm: "http://localhost:8000/v1",
  minimax: "https://api.minimax.chat/v1",
  deepseek: "https://api.deepseek.com/v1",
};

/** Env var precedence: provider-specific first, then the generic `OPENAI_API_KEY`. */
const API_KEY_ENV: Record<string, string[]> = {
  openai: ["OPENAI_API_KEY"],
  xai: ["XAI_API_KEY", "OPENAI_API_KEY"],
  openrouter: ["OPENROUTER_API_KEY", "OPENAI_API_KEY"],
  ollama: [], // local, no key
  vllm: [], // local, no key
  minimax: ["MINIMAX_API_KEY", "OPENAI_API_KEY"],
  deepseek: ["DEEPSEEK_API_KEY", "OPENAI_API_KEY"],
};

export interface LlmOptions {
  /** "deep" (default) → uses ``deep_think_llm``; "quick" → ``quick_think_llm``. */
  tier?: "deep" | "quick";
  /** Override the model from config. */
  model?: string;
  /** Override the temperature from config (Phase 1 default 0.2). */
  temperature?: number;
  /** Override the provider from config (e.g. "ollama" for a local Lemonade server). */
  provider?: string;
  /** Override the base URL from config. */
  baseUrl?: string;
  /** Override the per-request max_tokens budget (useful for reasoning models). */
  maxTokens?: number;
}

export interface LlmHandle {
  llm: ChatOpenAI;
  provider: string;
  model: string;
  baseUrl: string | undefined;
}

function pickModel(config: EtfAgentsConfig, tier: "deep" | "quick"): string {
  const key = tier === "deep" ? "deep_think_llm" : "quick_think_llm";
  const value = config[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(
      `Bridge config is missing '${key}'. Run the bridge with a complete config or pass --model.`,
    );
  }
  return value;
}

function pickApiKey(provider: string): string | undefined {
  const candidates = API_KEY_ENV[provider] ?? [];
  for (const name of candidates) {
    const value = process.env[name];
    if (value && value.trim() !== "") {
      return value;
    }
  }
  return undefined;
}

export function createLlmFromConfig(config: EtfAgentsConfig, options: LlmOptions = {}): LlmHandle {
  const provider = (options.provider ?? String(config.llm_provider ?? "openai")).toLowerCase();
  if (!OPENAI_COMPATIBLE.has(provider)) {
    throw new Error(
      `Provider '${provider}' is not OpenAI-compatible. ` +
        `Phase 1 supports: ${[...OPENAI_COMPATIBLE].sort().join(", ")}. ` +
        `Anthropic/Google native clients arrive in Phase 2.`,
    );
  }

  const model = options.model ?? pickModel(config, options.tier ?? "deep");
  const baseUrl =
    options.baseUrl ??
    (config.backend_url as string | null | undefined) ??
    DEFAULT_BASE_URL[provider];

  const apiKey = pickApiKey(provider);
  const requiresKey = (API_KEY_ENV[provider] ?? []).length > 0;
  if (requiresKey && !apiKey) {
    const names = API_KEY_ENV[provider]?.join(" or ");
    throw new Error(`Missing API key for provider '${provider}'. Set ${names} in the environment.`);
  }

  const llm = new ChatOpenAI({
    model,
    temperature: options.temperature ?? 0.2,
    ...(options.maxTokens ? { maxTokens: options.maxTokens } : {}),
    // Some OpenAI-compatible servers (Lemonade, Ollama, vLLM) reject empty
    // Authorization headers, so pass a placeholder when no key is configured.
    ...(apiKey ? { apiKey } : { apiKey: "not-needed" }),
    ...(baseUrl ? { configuration: { baseURL: baseUrl } } : {}),
  });

  return { llm, provider, model, baseUrl };
}
