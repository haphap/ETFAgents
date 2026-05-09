import unittest
from unittest.mock import patch

from cli.utils import select_llm_provider, select_shallow_thinking_agent


class CliProviderSelectionTests(unittest.TestCase):
    @patch("cli.utils.questionary.select")
    def test_select_llm_provider_returns_internal_provider_key(self, mock_select):
        mock_select.return_value.ask.return_value = (
            "ollama",
            "http://localhost:4000/v1",
            "Ollama / llama.cpp",
        )

        provider, url = select_llm_provider()

        self.assertEqual(provider, "ollama")
        self.assertEqual(url, "http://localhost:4000/v1")

    @patch("cli.utils.questionary.select")
    def test_select_llm_provider_returns_minimax_endpoint(self, mock_select):
        mock_select.return_value.ask.return_value = (
            "minimax",
            "https://api.minimax.chat/v1",
            "MiniMax",
        )

        provider, url = select_llm_provider()

        self.assertEqual(provider, "minimax")
        self.assertEqual(url, "https://api.minimax.chat/v1")

    @patch("cli.utils.questionary.text")
    @patch("cli.utils.questionary.select")
    def test_select_shallow_thinking_agent_supports_custom_minimax_model(
        self,
        mock_select,
        mock_text,
    ):
        mock_select.return_value.ask.return_value = "custom"
        mock_text.return_value.ask.return_value = "MiniMax-Text-01"

        model = select_shallow_thinking_agent("minimax")

        self.assertEqual(model, "MiniMax-Text-01")


if __name__ == "__main__":
    unittest.main()
