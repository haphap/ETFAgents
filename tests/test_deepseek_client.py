import types
import unittest
from unittest.mock import patch

from etfagents.llm_clients.openai_client import DeepSeekChatOpenAI


class DeepSeekReasoningContentTests(unittest.TestCase):
    """Test that reasoning_content is captured and echoed for DeepSeek."""

    def _make_llm(self, model: str = "deepseek-chat") -> DeepSeekChatOpenAI:
        return DeepSeekChatOpenAI(model=model, api_key="test-key")

    def test_create_chat_result_captures_reasoning_content(self):
        llm = self._make_llm()
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello",
                        "reasoning_content": "Let me think step by step.",
                    },
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
            "model": "deepseek-chat",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        result = llm._create_chat_result(response)
        msg = result.generations[0].message
        self.assertEqual(msg.content, "Hello")
        self.assertEqual(
            msg.additional_kwargs["reasoning_content"],
            "Let me think step by step.",
        )

    def test_create_chat_result_no_reasoning_content(self):
        llm = self._make_llm()
        response = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hi"},
                    "index": 0,
                    "finish_reason": "stop",
                }
            ],
            "model": "deepseek-chat",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        result = llm._create_chat_result(response)
        msg = result.generations[0].message
        self.assertEqual(msg.content, "Hi")
        self.assertNotIn("reasoning_content", msg.additional_kwargs)

    def test_structured_output_blocked_for_reasoner(self):
        llm = self._make_llm(model="deepseek-reasoner")
        with self.assertRaises(NotImplementedError) as ctx:
            llm.with_structured_output({"type": "object"})
        self.assertIn("deepseek-reasoner", str(ctx.exception))

    def test_structured_output_allowed_for_chat(self):
        llm = self._make_llm(model="deepseek-chat")
        # Should not raise; returns a wrapper (we don't need to test the
        # wrapper itself, just that the guard does NOT trigger).
        try:
            llm.with_structured_output(
                {"type": "object", "title": "TestSchema", "properties": {"x": {"type": "string"}}}
            )
        except NotImplementedError:
            self.fail("with_structured_output should work for deepseek-chat")


class DeepSeekFactoryRoutingTests(unittest.TestCase):
    """Test that create_llm_client routes deepseek to OpenAIClient."""

    def test_deepseek_uses_openai_compatible_module(self):
        from etfagents.llm_clients.factory import create_llm_client

        fake_module = types.SimpleNamespace(
            OpenAIClient=lambda *args, **kwargs: ("openai", args, kwargs)
        )
        with patch(
            "etfagents.llm_clients.factory.import_module",
            side_effect=lambda name: self.assertEqual(
                name, "etfagents.llm_clients.openai_client"
            ) or fake_module,
        ):
            client = create_llm_client("deepseek", "deepseek-chat")

        self.assertEqual(client[0], "openai")

    def test_deepseek_in_compatible_providers(self):
        from etfagents.llm_clients.factory import _OPENAI_COMPATIBLE_PROVIDERS

        self.assertIn("deepseek", _OPENAI_COMPATIBLE_PROVIDERS)


if __name__ == "__main__":
    unittest.main()
