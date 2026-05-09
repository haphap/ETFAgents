"""Shared model catalog for CLI selections and validation."""

from __future__ import annotations

from typing import Dict, List, Tuple

ModelOption = Tuple[str, str]
ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]

OLLAMA_MODEL_ALIASES = {
    "Qwen3.5-35B-3A": "samuelcardillo/Qwopus-MoE-35B-A3B-GGUF:Q4_K_M",
    "Qwen3.5-35B-A3B": "samuelcardillo/Qwopus-MoE-35B-A3B-GGUF:Q4_K_M",
}


MODEL_OPTIONS: ProviderModeOptions = {
    "openai": {
        "quick": [
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            ("GPT-5.4 Nano - Cheapest, high-volume tasks", "gpt-5.4-nano"),
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-4.1 - Smartest non-reasoning model", "gpt-4.1"),
        ],
        "deep": [
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-5.2 - Strong reasoning, cost-effective", "gpt-5.2"),
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            ("GPT-5.4 Pro - Most capable, expensive ($30/$180 per 1M tokens)", "gpt-5.4-pro"),
        ],
    },
    "anthropic": {
        "quick": [
            ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
            ("Claude Haiku 4.5 - Fast, near-instant responses", "claude-haiku-4-5"),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
        "deep": [
            ("Claude Opus 4.6 - Most intelligent, agents and coding", "claude-opus-4-6"),
            ("Claude Opus 4.5 - Premium, max intelligence", "claude-opus-4-5"),
            ("Claude Sonnet 4.6 - Best speed and intelligence balance", "claude-sonnet-4-6"),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
    },
    "google": {
        "quick": [
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
            ("Gemini 3.1 Flash Lite - Most cost-efficient", "gemini-3.1-flash-lite-preview"),
            ("Gemini 2.5 Flash Lite - Fast, low-cost", "gemini-2.5-flash-lite"),
        ],
        "deep": [
            ("Gemini 3.1 Pro - Reasoning-first, complex workflows", "gemini-3.1-pro-preview"),
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Pro - Stable pro model", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
        ],
    },
    "xai": {
        "quick": [
            ("Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx", "grok-4-1-fast-non-reasoning"),
            ("Grok 4 Fast (Non-Reasoning) - Speed optimized", "grok-4-fast-non-reasoning"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
        ],
        "deep": [
            ("Grok 4 - Flagship model", "grok-4-0709"),
            ("Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx", "grok-4-1-fast-reasoning"),
            ("Grok 4 Fast (Reasoning) - High-performance", "grok-4-fast-reasoning"),
            ("Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx", "grok-4-1-fast-non-reasoning"),
        ],
    },
    "minimax": {
        "quick": [
            ("MiniMax M2.7 Highspeed - Fastest general model", "MiniMax-M2.7-highspeed"),
            ("MiniMax M2.5 Highspeed - Lower-cost fast model", "MiniMax-M2.5-highspeed"),
            ("MiniMax M2.1 - Legacy balanced model", "MiniMax-M2.1"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("MiniMax M2.7 - Strongest reasoning model", "MiniMax-M2.7"),
            ("MiniMax M2.5 - Balanced reasoning/cost", "MiniMax-M2.5"),
            ("MiniMax M2 - Legacy flagship model", "MiniMax-M2"),
            ("Custom model ID", "custom"),
        ],
    },
    # OpenRouter models are fetched dynamically at CLI runtime.
    # No static entries needed; any model ID is accepted by the validator.
    "openrouter": {
        "quick": [],
        "deep": [],
    },
    # vLLM models are served locally; any model ID is accepted by the validator.
    "vllm": {
        "quick": [
            ("Carnice-V2-27b-NVFP4 (vLLM local)", "sakamakismile/Carnice-V2-27b-NVFP4-TEXT-MTP"),
        ],
        "deep": [
            ("Carnice-V2-27b-NVFP4 (vLLM local)", "sakamakismile/Carnice-V2-27b-NVFP4-TEXT-MTP"),
        ],
    },
    "ollama": {
        "quick": [
            ("Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M (llama.cpp local)", "Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M"),
            ("Jackrong/Qwopus3.5-27B-v3-GGUF:Q4_K_M (llama.cpp local)", "Jackrong/Qwopus3.5-27B-v3-GGUF:Q4_K_M"),
            ("Qwen3.5-27B (llama.cpp local)", "Qwen3.5-27B"),
            ("Qwen3.5-35B-3A (llama.cpp local alias)", "Qwen3.5-35B-3A"),
            ("Qwen3.5-122B (llama.cpp local)", "Qwen3.5-122B"),
        ],
        "deep": [
            ("Qwen3.5-122B (llama.cpp local)", "Qwen3.5-122B"),
            ("Jackrong/Qwopus3.5-27B-v3-GGUF:Q4_K_M (llama.cpp local)", "Jackrong/Qwopus3.5-27B-v3-GGUF:Q4_K_M"),
            ("Qwen3.5-35B-A3B (llama.cpp local alias)", "Qwen3.5-35B-A3B"),
            ("Qwen3.5-27B (llama.cpp local)", "Qwen3.5-27B"),
            ("Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M (llama.cpp local)", "Jackrong/Qwopus3.5-9B-v3-GGUF:Q4_K_M"),
        ],
    },
}


def get_model_options(provider: str, mode: str) -> List[ModelOption]:
    """Return shared model options for a provider and selection mode."""
    return MODEL_OPTIONS[provider.lower()][mode]


def get_known_models() -> Dict[str, List[str]]:
    """Build known model names from the shared CLI catalog."""
    return {
        provider: sorted(
            {
                value
                for options in mode_options.values()
                for _, value in options
            }
        )
        for provider, mode_options in MODEL_OPTIONS.items()
    }
