"""Tests for synthesize_side_report error handling."""

import importlib.util
import unittest
if not importlib.util.find_spec("langchain_core"):
    raise unittest.SkipTest("langchain_core not installed")

import unittest
from unittest.mock import MagicMock, patch

from etfagents.agents.utils.agent_utils import synthesize_side_report

class _FakeResponse:
    def __init__(self, content):
        self.content = content

class TestSynthesizeSideReport(unittest.TestCase):
    @patch("etfagents.agents.utils.agent_utils._is_chinese_output", return_value=False)
    def test_returns_synthesized_text(self, _mock_cn):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("Synthesized report content.")
        result = synthesize_side_report(llm, "Bull Researcher", "arg1\narg2\narg3", "snap")
        self.assertEqual(result, "Synthesized report content.")
        llm.invoke.assert_called_once()

    @patch("etfagents.agents.utils.agent_utils._is_chinese_output", return_value=False)
    def test_falls_back_to_truncated_history_on_failure(self, _mock_cn):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("LLM down")
        history = "round 1 text\nround 2 text\nround 3 text"
        result = synthesize_side_report(llm, "Bear Researcher", history, "snap")
        self.assertIn("round 1 text", result)

    @patch("etfagents.agents.utils.agent_utils._is_chinese_output", return_value=True)
    def test_chinese_prompt_when_chinese_output(self, _mock_cn):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("综合报告")
        result = synthesize_side_report(llm, "Bull Researcher", "历史", "快照")
        self.assertEqual(result, "综合报告")
        call_args = llm.invoke.call_args[0][0]
        self.assertIn("综合立场报告", call_args)

    @patch("etfagents.agents.utils.agent_utils._is_chinese_output", return_value=False)
    def test_empty_history_returns_snapshot(self, _mock_cn):
        llm = MagicMock()
        result = synthesize_side_report(llm, "Bull Researcher", "", "fallback snapshot")
        self.assertEqual(result, "fallback snapshot")
        llm.invoke.assert_not_called()

if __name__ == "__main__":
    unittest.main()
