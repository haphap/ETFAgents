
import importlib.util
import unittest
if not importlib.util.find_spec("langchain_core"):
    raise unittest.SkipTest("langchain_core not installed")

import types
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.llm_clients.openai_client import DeepSeekChatOpenAI

class DeepSeekCreateChatResultTests(unittest.TestCase):
    """Test _create_chat_result with both dict and pydantic responses."""

    def _make_llm(self, model: str = "deepseek-chat") -> DeepSeekChatOpenAI:
        return DeepSeekChatOpenAI(model=model, api_key="test-key")

    def test_dict_response_captures_reasoning_content(self):
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

    def test_pydantic_response_captures_reasoning_content(self):
        """OpenAI SDK returns ChatCompletion pydantic objects, not dicts."""
        from openai.types.chat import ChatCompletion
        from openai.types.chat.chat_completion import Choice
        from openai.types.chat.chat_completion_message import ChatCompletionMessage

        llm = self._make_llm()
        api_msg = ChatCompletionMessage(
            role="assistant", content="Answer", reasoning_content="Chain of thought"
        )
        response = ChatCompletion(
            id="test-1",
            choices=[Choice(index=0, message=api_msg, finish_reason="stop")],
            created=0,
            model="deepseek-chat",
            object="chat.completion",
        )
        result = llm._create_chat_result(response)
        msg = result.generations[0].message
        self.assertEqual(msg.content, "Answer")
        self.assertEqual(
            msg.additional_kwargs["reasoning_content"], "Chain of thought"
        )

    def test_no_reasoning_content(self):
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

    def test_pydantic_response_without_reasoning(self):
        """Non-reasoning model response should not crash."""
        from openai.types.chat import ChatCompletion
        from openai.types.chat.chat_completion import Choice
        from openai.types.chat.chat_completion_message import ChatCompletionMessage

        llm = self._make_llm()
        api_msg = ChatCompletionMessage(role="assistant", content="Plain")
        response = ChatCompletion(
            id="test-2",
            choices=[Choice(index=0, message=api_msg, finish_reason="stop")],
            created=0,
            model="deepseek-chat",
            object="chat.completion",
        )
        result = llm._create_chat_result(response)
        msg = result.generations[0].message
        self.assertEqual(msg.content, "Plain")
        self.assertNotIn("reasoning_content", msg.additional_kwargs)

class DeepSeekRequestPayloadTests(unittest.TestCase):
    """Test that _get_request_payload echoes reasoning_content back."""

    def _make_llm(self, model: str = "deepseek-chat") -> DeepSeekChatOpenAI:
        return DeepSeekChatOpenAI(model=model, api_key="test-key")

    def test_reasoning_content_echoed_in_payload(self):
        """After a response with reasoning_content, subsequent requests must
        include it in the assistant message dict to avoid DeepSeek HTTP 400."""
        llm = self._make_llm()

        # Simulate a conversation: human asks, assistant responds with reasoning
        assistant_msg = AIMessage(content="Answer")
        assistant_msg.additional_kwargs["reasoning_content"] = "Step by step thought"

        messages = [
            HumanMessage(content="Question?"),
            assistant_msg,
            HumanMessage(content="Follow up?"),
        ]

        payload = llm._get_request_payload(messages)

        # Find the assistant message in the payload
        assistant_dicts = [
            m for m in payload["messages"] if m.get("role") == "assistant"
        ]
        self.assertEqual(len(assistant_dicts), 1)
        self.assertEqual(assistant_dicts[0]["reasoning_content"], "Step by step thought")

    def test_no_reasoning_content_when_absent(self):
        """Messages without reasoning_content should not get a None field."""
        llm = self._make_llm()

        messages = [
            HumanMessage(content="Question?"),
            AIMessage(content="Answer"),
            HumanMessage(content="Follow up?"),
        ]

        payload = llm._get_request_payload(messages)

        assistant_dicts = [
            m for m in payload["messages"] if m.get("role") == "assistant"
        ]
        self.assertEqual(len(assistant_dicts), 1)
        self.assertNotIn("reasoning_content", assistant_dicts[0])

    def test_multiple_assistant_messages_preserve_reasoning(self):
        """Each assistant message should carry its own reasoning_content."""
        llm = self._make_llm()

        msg1 = AIMessage(content="First answer")
        msg1.additional_kwargs["reasoning_content"] = "Thought 1"

        msg2 = AIMessage(content="Second answer")
        msg2.additional_kwargs["reasoning_content"] = "Thought 2"

        messages = [
            HumanMessage(content="Q1?"),
            msg1,
            HumanMessage(content="Q2?"),
            msg2,
            HumanMessage(content="Q3?"),
        ]

        payload = llm._get_request_payload(messages)

        assistant_dicts = [
            m for m in payload["messages"] if m.get("role") == "assistant"
        ]
        self.assertEqual(len(assistant_dicts), 2)
        self.assertEqual(assistant_dicts[0]["reasoning_content"], "Thought 1")
        self.assertEqual(assistant_dicts[1]["reasoning_content"], "Thought 2")

class DeepSeekStructuredOutputGuardTests(unittest.TestCase):
    """Test structured output guard for reasoner model."""

    def _make_llm(self, model: str = "deepseek-chat") -> DeepSeekChatOpenAI:
        return DeepSeekChatOpenAI(model=model, api_key="test-key")

    def test_structured_output_blocked_for_reasoner(self):
        llm = self._make_llm(model="deepseek-reasoner")
        with self.assertRaises(NotImplementedError) as ctx:
            llm.with_structured_output({"type": "object"})
        self.assertIn("deepseek-reasoner", str(ctx.exception))

    def test_structured_output_allowed_for_chat(self):
        llm = self._make_llm(model="deepseek-chat")
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
