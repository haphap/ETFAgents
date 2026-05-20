"""Shared model catalog for CLI selections and validation."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Dict, List, Literal, Tuple

logger = logging.getLogger(__name__)

ModelOption = Tuple[str, str]
ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]

OLLAMA_MODEL_ALIASES = {
    "Qwen3.5-35B-3A": "samuelcardillo/Qwopus-MoE-35B-A3B-GGUF:Q4_K_M",
    "Qwen3.5-35B-A3B": "samuelcardillo/Qwopus-MoE-35B-A3B-GGUF:Q4_K_M",
}


class CapabilityLevel(IntEnum):
    BASIC = 1
    STANDARD = 2
    ADVANCED = 3
    PROFESSIONAL = 4
    FLAGSHIP = 5


ModelFeature = Literal[
    "tool_calling", "long_context", "reasoning",
    "fast_response", "cost_effective",
]

_SKIP_RECOMMENDATION_PROVIDERS = {"openrouter", "vllm", "ollama"}

MODEL_CAPABILITIES: dict[str, dict] = {
    # openai
    "gpt-5.4-mini": {
        "level": 2, "roles": ["quick", "deep"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 2,
    },
    "gpt-5.4-nano": {
        "level": 1, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 1,
    },
    "gpt-5.4": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 3, "cost": 3, "quality": 4,
    },
    "gpt-4.1": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling"],
        "speed": 4, "cost": 3, "quality": 3,
    },
    "gpt-5.2": {
        "level": 4, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 2, "cost": 2, "quality": 4,
    },
    "gpt-5.4-pro": {
        "level": 5, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 1, "cost": 1, "quality": 5,
    },
    # anthropic
    "claude-haiku-4-5": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 4, "quality": 2,
    },
    "claude-sonnet-4-5": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 3, "cost": 3, "quality": 4,
    },
    "claude-sonnet-4-6": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 4, "cost": 3, "quality": 4,
    },
    "claude-opus-4-5": {
        "level": 5, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 1, "cost": 1, "quality": 5,
    },
    "claude-opus-4-6": {
        "level": 5, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 2, "cost": 1, "quality": 5,
    },
    # google
    "gemini-2.5-flash": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 2,
    },
    "gemini-2.5-flash-lite": {
        "level": 1, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 1,
    },
    "gemini-2.5-pro": {
        "level": 4, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 2, "cost": 2, "quality": 4,
    },
    "gemini-3-flash-preview": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "long_context"],
        "speed": 4, "cost": 4, "quality": 3,
    },
    "gemini-3.1-flash-lite-preview": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 2,
    },
    "gemini-3.1-pro-preview": {
        "level": 4, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 2, "cost": 2, "quality": 4,
    },
    # xai
    "grok-4-fast-non-reasoning": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 4, "cost": 3, "quality": 2,
    },
    "grok-4-1-fast-non-reasoning": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 4, "cost": 3, "quality": 2,
    },
    "grok-4-1-fast-reasoning": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "reasoning"],
        "speed": 3, "cost": 2, "quality": 3,
    },
    "grok-4-fast-reasoning": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling", "reasoning"],
        "speed": 3, "cost": 2, "quality": 3,
    },
    "grok-4-0709": {
        "level": 5, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 1, "cost": 1, "quality": 5,
    },
    # minimax
    "MiniMax-M2.7-highspeed": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 1,
    },
    "MiniMax-M2.5-highspeed": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 5, "cost": 5, "quality": 1,
    },
    "MiniMax-M2.1": {
        "level": 1, "roles": ["quick"],
        "features": ["tool_calling"],
        "speed": 3, "cost": 4, "quality": 1,
    },
    "MiniMax-M2.7": {
        "level": 3, "roles": ["deep"],
        "features": ["tool_calling"],
        "speed": 3, "cost": 4, "quality": 3,
    },
    "MiniMax-M2.5": {
        "level": 2, "roles": ["deep"],
        "features": ["tool_calling"],
        "speed": 3, "cost": 4, "quality": 2,
    },
    "MiniMax-M2": {
        "level": 2, "roles": ["deep"],
        "features": ["tool_calling"],
        "speed": 3, "cost": 4, "quality": 2,
    },
    # deepseek
    "deepseek-v4-flash": {
        "level": 2, "roles": ["quick"],
        "features": ["tool_calling", "fast_response", "cost_effective"],
        "speed": 4, "cost": 5, "quality": 2,
    },
    "deepseek-chat": {
        "level": 3, "roles": ["quick", "deep"],
        "features": ["tool_calling"],
        "speed": 3, "cost": 4, "quality": 3,
    },
    "deepseek-v4-pro": {
        "level": 4, "roles": ["deep"],
        "features": ["tool_calling", "long_context", "reasoning"],
        "speed": 1, "cost": 3, "quality": 4,
    },
    "deepseek-reasoner": {
        "level": 4, "roles": ["deep"],
        "features": ["reasoning", "long_context"],
        "speed": 1, "cost": 3, "quality": 4,
    },
}

RESEARCH_DEPTH_REQUIREMENTS: dict[str, dict] = {
    "快速": {"min_level": 1, "quick_min": 1, "deep_min": 1,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 0, "risk_rounds": 0},
    "基础": {"min_level": 1, "quick_min": 1, "deep_min": 2,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 1, "risk_rounds": 0},
    "标准": {"min_level": 2, "quick_min": 2, "deep_min": 3,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 1, "risk_rounds": 1},
    "深度": {"min_level": 3, "quick_min": 2, "deep_min": 4,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling"],
             "debate_rounds": 2, "risk_rounds": 2},
    "全面": {"min_level": 3, "quick_min": 3, "deep_min": 5,
             "quick_required_features": ["tool_calling"],
             "deep_required_features": ["tool_calling", "reasoning"],
             "debate_rounds": 3, "risk_rounds": 3},
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
    "deepseek": {
        "quick": [
            ("DeepSeek V4 Flash - Fast, cost-efficient", "deepseek-v4-flash"),
            ("DeepSeek Chat - General purpose", "deepseek-chat"),
        ],
        "deep": [
            ("DeepSeek V4 Pro - Most capable reasoning model", "deepseek-v4-pro"),
            ("DeepSeek V4 Flash - Fast, cost-efficient", "deepseek-v4-flash"),
            ("DeepSeek Reasoner - Extended thinking (no tool_choice, no structured output)", "deepseek-reasoner"),
            ("DeepSeek Chat - General purpose", "deepseek-chat"),
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


def get_depth_config(depth: str) -> dict | None:
    """Return debate/risk round configuration for a research depth name."""
    return RESEARCH_DEPTH_REQUIREMENTS.get(depth)


def _provider_model_ids(provider: str) -> set[str]:
    """Return non-custom static model IDs for a cloud provider."""
    return {
        mid
        for mode_options in MODEL_OPTIONS.get(provider, {}).values()
        for _, mid in mode_options
        if mid != "custom"
    }


def recommend_models(
    depth: str,
    provider: str | None = None,
) -> dict:
    """Recommend optimal quick+deep model pair based on research depth.

    Algorithm:
    1. Filter MODEL_CAPABILITIES by depth requirements (level, features, roles).
    2. If provider specified, restrict to models in MODEL_OPTIONS[provider];
       if provider is None, search across all cloud providers.
    3. Sort quick candidates by (level DESC, cost DESC, speed DESC).
    4. Sort deep candidates by (level DESC, quality DESC, cost DESC).
    5. Return top candidate for each role.
    """
    if provider and provider.lower() in _SKIP_RECOMMENDATION_PROVIDERS:
        return {
            "quick_model": None,
            "deep_model": None,
            "quick_reason": f"Provider '{provider}' uses dynamic/custom models, skip recommendation",
            "deep_reason": f"Provider '{provider}' uses dynamic/custom models, skip recommendation",
            "depth": depth,
        }

    req = RESEARCH_DEPTH_REQUIREMENTS.get(depth)
    if req is None:
        return {
            "quick_model": None,
            "deep_model": None,
            "quick_reason": f"Unknown depth '{depth}'",
            "deep_reason": f"Unknown depth '{depth}'",
            "depth": depth,
        }

    if provider:
        allowed_ids = _provider_model_ids(provider.lower())
        if not allowed_ids:
            return {
                "quick_model": None,
                "deep_model": None,
                "quick_reason": f"Provider '{provider}' has no static models",
                "deep_reason": f"Provider '{provider}' has no static models",
                "depth": depth,
            }
    else:
        all_ids: set[str] = set()
        for p in MODEL_OPTIONS:
            if p not in _SKIP_RECOMMENDATION_PROVIDERS:
                all_ids.update(_provider_model_ids(p))
        allowed_ids = all_ids

    candidates = {
        mid: cap for mid, cap in MODEL_CAPABILITIES.items()
        if mid in allowed_ids
    }

    def _meets(cap: dict, min_level: int, role: str, required_features: list[str]) -> bool:
        if role not in cap["roles"]:
            return False
        if cap["level"] < min_level:
            return False
        return all(f in cap["features"] for f in required_features)

    quick_cands = [
        (mid, cap) for mid, cap in candidates.items()
        if _meets(cap, req["quick_min"], "quick", req["quick_required_features"])
    ]
    deep_cands = [
        (mid, cap) for mid, cap in candidates.items()
        if _meets(cap, req["deep_min"], "deep", req["deep_required_features"])
    ]

    quick_cands.sort(key=lambda x: (-x[1]["level"], -x[1]["cost"], -x[1]["speed"]))
    deep_cands.sort(key=lambda x: (-x[1]["level"], -x[1]["quality"], -x[1]["cost"]))

    quick_model = quick_cands[0][0] if quick_cands else None
    deep_model = deep_cands[0][0] if deep_cands else None

    quick_reason = (
        f"Level {quick_cands[0][1]['level']}, cost {quick_cands[0][1]['cost']}, speed {quick_cands[0][1]['speed']}"
        if quick_model else "No qualifying quick model found"
    )
    deep_reason = (
        f"Level {deep_cands[0][1]['level']}, quality {deep_cands[0][1]['quality']}, cost {deep_cands[0][1]['cost']}"
        if deep_model else "No qualifying deep model found"
    )

    return {
        "quick_model": quick_model,
        "deep_model": deep_model,
        "quick_reason": quick_reason,
        "deep_reason": deep_reason,
        "depth": depth,
    }
