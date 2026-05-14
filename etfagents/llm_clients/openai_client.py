import os
from typing import Any, List, Optional

from langchain_core.messages import BaseMessage
from langchain_core.prompt_values import ChatPromptValue
from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "minimax": ("https://api.minimax.chat/v1", "MINIMAX_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "vllm": ("http://127.0.0.1:8020/v1", None),
}


def _input_to_messages(input: Any) -> List[BaseMessage]:
    """Convert input to a list of messages for DeepSeekChatOpenAI."""
    if isinstance(input, ChatPromptValue):
        return input.to_messages()
    return ChatOpenAI._input_to(input)


class DeepSeekChatOpenAI(NormalizedChatOpenAI):
    """ChatOpenAI subclass for DeepSeek models.

    DeepSeek's thinking-mode models (deepseek-reasoner) return reasoning
    in a separate ``reasoning_content`` field.  This class:
    * Captures ``reasoning_content`` from the response into
      ``AIMessage.additional_kwargs`` so callers can inspect it.
    * Echoes ``reasoning_content`` back in subsequent request messages so
      the API does not reject multi-turn conversations (HTTP 400).
    * Blocks ``with_structured_output`` for ``deepseek-reasoner`` because
      that model does not support ``tool_choice``.
    """

    def _input_to(self, input: Any) -> List[BaseMessage]:
        return _input_to_messages(input)

    # --- response handling ---

    def _create_chat_result(self, response: dict, generation_info: dict | None = None):
        result = super()._create_chat_result(response, generation_info)
        # Promote reasoning_content into additional_kwargs for each
        # generation so downstream code can access the chain-of-thought.
        for gen in result.generations:
            msg = gen.message
            if not msg or not hasattr(msg, "additional_kwargs"):
                continue
            for choice in response.get("choices", []):
                rc = (choice.get("message") or {}).get("reasoning_content")
                if rc:
                    msg.additional_kwargs["reasoning_content"] = rc
                    break
        return result

    # --- request payload ---

    def _get_request_payload(
        self, input, *, stop=None, **kwargs
    ) -> dict:
        payload = super()._get_request_payload(input, stop=stop, **kwargs)
        # Echo reasoning_content back for multi-turn conversations.
        # DeepSeek returns HTTP 400 if a previous assistant message
        # contained reasoning_content but the follow-up omits it.
        for msg in payload.get("messages", []):
            if not isinstance(msg, dict):
                continue
            rc = (
                (msg.get("additional_kwargs") or {}).get("reasoning_content")
                or (msg.get("message_kwargs") or {}).get("reasoning_content")
            )
            if rc:
                msg["reasoning_content"] = rc
        return payload

    # --- structured output guard ---

    def with_structured_output(self, schema, **kwargs):
        if self.model == "deepseek-reasoner":
            raise NotImplementedError(
                "deepseek-reasoner does not support tool_choice / structured output. "
                "Use deepseek-chat or another model for structured extraction."
            )
        return super().with_structured_output(schema, **kwargs)


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI-compatible providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, MiniMax,
    OpenRouter, Ollama, vLLM) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # Provider-specific base URL and auth
        if self.provider in _PROVIDER_CONFIG:
            default_base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = self.base_url or default_base_url
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        # DeepSeek: use custom subclass for reasoning_content round-trip
        if self.provider == "deepseek":
            return DeepSeekChatOpenAI(**llm_kwargs)

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
