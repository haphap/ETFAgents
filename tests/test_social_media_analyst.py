import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.social_media_analyst import create_social_media_analyst


class _CapturingLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, prompt, **kwargs):
        return AIMessage(content="Report content")


class SocialMediaAnalystTests(unittest.TestCase):
    def test_social_analyst_returns_sentiment_report(self):
        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        with patch(
            "etfagents.agents.analysts.social_media_analyst.run_tool_report_chain",
            return_value=(
                AIMessage(content="# Sentiment report\n\nSupportive flow."),
                "# Sentiment report\n\nSupportive flow.",
            ),
        ):
            result = node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        self.assertIn("sentiment_report", result)
        self.assertIn("Supportive flow", result["sentiment_report"])
        self.assertEqual(result["messages"][0].content, result["sentiment_report"])

    def test_social_analyst_prompt_expands_to_holdings_industries_and_macro_events(self):
        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["tools"] = [tool.name for tool in args[2]]
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.social_media_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        self.assertEqual(
            captured["tools"],
            ["get_etf_info", "get_etf_holdings", "get_news", "get_global_news"],
        )
        system_msg = captured["system_message"]
        self.assertIn("not limited to the ETF product itself", system_msg)
        self.assertIn("dominant industries", system_msg)
        self.assertIn("top-weight holdings", system_msg)
        self.assertIn("macro events", system_msg)
        self.assertIn("support, cap, or drag ETF price action", system_msg)
        self.assertIn("真实支撑、真实拖累与噪声区分", system_msg)
        self.assertIn("do not use English labels like 'Genuine Support'", system_msg)
