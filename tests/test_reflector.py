"""Tests for the Reflector class."""

import unittest
from unittest.mock import MagicMock

from etfagents.graph.reflection import Reflector


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class TestReflector(unittest.TestCase):
    def test_reflect_returns_text(self):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("The decision was well-timed.")
        reflector = Reflector(llm)

        result = reflector.reflect_on_final_decision("Buy QQQ", 0.05, 0.02)
        self.assertEqual(result, "The decision was well-timed.")
        llm.invoke.assert_called_once()

    def test_reflect_returns_empty_on_exception(self):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("LLM unavailable")
        reflector = Reflector(llm)

        result = reflector.reflect_on_final_decision("Sell SPY", -0.03, -0.01)
        self.assertEqual(result, "")

    def test_reflect_strips_whitespace(self):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("  lesson learned  \n")
        reflector = Reflector(llm)

        result = reflector.reflect_on_final_decision("Hold", 0.0, 0.0)
        self.assertEqual(result, "lesson learned")


if __name__ == "__main__":
    unittest.main()
