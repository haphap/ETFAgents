import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.etf_industry_research_analyst import (
    create_etf_industry_research_analyst,
)
from etfagents.agents.analysts.etf_stock_research_analyst import (
    create_etf_stock_research_analyst,
)


class _CapturingLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, prompt, **kwargs):
        return AIMessage(content="Report content")


class EtfIndustryResearchAnalystPromptTests(unittest.TestCase):
    def test_prompt_uses_tradingagents_style_cross_analysis_framework(self):
        llm = _CapturingLLM()
        node = create_etf_industry_research_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_industry_research_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("Per-Report Deep Analysis", system_msg)
        self.assertIn("Cross-Report Comparative Analysis", system_msg)
        self.assertIn("ETF Exposure Mapping", system_msg)
        self.assertIn("Supply-Chain Implications", system_msg)
        self.assertIn("Summary Table", system_msg)
        self.assertIn("Do NOT just list numbers", system_msg)
        self.assertIn("industry allocation timing", system_msg)
        self.assertIn("broker tagging noise", system_msg)


class EtfStockResearchAnalystPromptTests(unittest.TestCase):
    def test_prompt_uses_tradingagents_style_stock_framework(self):
        llm = _CapturingLLM()
        node = create_etf_stock_research_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_stock_research_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("Per-Report Deep Analysis", system_msg)
        self.assertIn("Cross-Report Comparative Analysis", system_msg)
        self.assertIn("Earnings Estimate Consensus", system_msg)
        self.assertIn("Valuation Analysis", system_msg)
        self.assertIn("ETF Portfolio Impact", system_msg)
        self.assertIn("Do NOT just list numbers", system_msg)
        self.assertIn("ETF return attribution", system_msg)
        self.assertIn("retrieval artifacts", system_msg)


if __name__ == "__main__":
    unittest.main()
