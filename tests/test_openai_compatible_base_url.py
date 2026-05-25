
import importlib.util
import unittest
if not importlib.util.find_spec("langchain_google_genai"):
    raise unittest.SkipTest("langchain_google_genai not installed")

import os
import unittest
from unittest.mock import patch

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.llm_clients.factory import create_llm_client
from etfagents.llm_clients.google_client import GoogleClient
from etfagents.llm_clients.openai_client import OpenAIClient

class OpenAICompatibleBaseUrlTests(unittest.TestCase):
    @patch("etfagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_ollama_provider_respects_explicit_base_url(self, mock_chat):
        client = OpenAIClient(
            "qwen3:latest",
            base_url="http://localhost:4000/v1",
            provider="ollama",
        )
        client.get_llm()

        kwargs = mock_chat.call_args[1]
        self.assertEqual(kwargs["base_url"], "http://localhost:4000/v1")
        self.assertEqual(kwargs["api_key"], "ollama")

    @patch("etfagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_factory_preserves_ollama_alias_model_name(self, mock_chat):
        client = create_llm_client(
            provider="ollama",
            model="Qwen3.5-35B-A3B",
            base_url="http://localhost:4000/v1",
        )
        client.get_llm()

        kwargs = mock_chat.call_args[1]
        self.assertEqual(kwargs["model"], "Qwen3.5-35B-A3B")

    @patch("etfagents.llm_clients.google_client.NormalizedChatGoogleGenerativeAI")
    def test_google_client_does_not_receive_default_openai_base_url(self, mock_chat):
        self.assertIsNone(DEFAULT_CONFIG["backend_url"])

        client = GoogleClient("gemini-2.5-flash")
        client.get_llm()

        self.assertNotIn("base_url", mock_chat.call_args[1])

    @patch.dict(os.environ, {"MINIMAX_API_KEY": "minimax-key"}, clear=False)
    @patch("etfagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_minimax_provider_uses_default_base_url_and_api_key(self, mock_chat):
        client = create_llm_client(
            provider="minimax",
            model="MiniMax-M2.7",
        )
        client.get_llm()

        kwargs = mock_chat.call_args[1]
        self.assertEqual(kwargs["base_url"], "https://api.minimax.chat/v1")
        self.assertEqual(kwargs["api_key"], "minimax-key")
        self.assertEqual(kwargs["model"], "MiniMax-M2.7")

if __name__ == "__main__":
    unittest.main()
