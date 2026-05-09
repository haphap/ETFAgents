import types
import unittest
from unittest.mock import patch

from etfagents.llm_clients.factory import create_llm_client


class LazyFactoryImportTests(unittest.TestCase):
    def test_ollama_uses_only_openai_compatible_module(self):
        fake_module = types.SimpleNamespace(
            OpenAIClient=lambda *args, **kwargs: ("openai", args, kwargs)
        )

        with patch(
            "etfagents.llm_clients.factory.import_module",
            side_effect=lambda name: self.assertEqual(
                name, "etfagents.llm_clients.openai_client"
            ) or fake_module,
        ):
            client = create_llm_client("ollama", "Qwen3.5-35B-A3B")

        self.assertEqual(client[0], "openai")

    def test_google_uses_only_google_module(self):
        fake_module = types.SimpleNamespace(
            GoogleClient=lambda *args, **kwargs: ("google", args, kwargs)
        )

        with patch(
            "etfagents.llm_clients.factory.import_module",
            side_effect=lambda name: self.assertEqual(
                name, "etfagents.llm_clients.google_client"
            ) or fake_module,
        ):
            client = create_llm_client("google", "gemini-2.5-flash")

        self.assertEqual(client[0], "google")


if __name__ == "__main__":
    unittest.main()
