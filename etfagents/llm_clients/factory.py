from importlib import import_module
from typing import Optional

from .base_client import BaseLLMClient

_OPENAI_COMPATIBLE_PROVIDERS = ("openai", "xai", "openrouter", "ollama", "minimax", "vllm")


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: LLM provider (openai, anthropic, google, xai, minimax, ollama, openrouter, vllm)
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments
            - http_client: Custom httpx.Client for SSL proxy or certificate customization
            - http_async_client: Custom httpx.AsyncClient for async operations
            - timeout: Request timeout in seconds
            - max_retries: Maximum retry attempts
            - api_key: API key for the provider
            - callbacks: LangChain callbacks

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    if provider_lower in _OPENAI_COMPATIBLE_PROVIDERS:
        openai_module = import_module("etfagents.llm_clients.openai_client")
        OpenAIClient = openai_module.OpenAIClient
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)
    if provider_lower == "anthropic":
        anthropic_module = import_module("etfagents.llm_clients.anthropic_client")
        AnthropicClient = anthropic_module.AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        google_module = import_module("etfagents.llm_clients.google_client")
        GoogleClient = google_module.GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
