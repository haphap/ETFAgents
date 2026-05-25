
import importlib.util
import unittest
if not importlib.util.find_spec("langchain_core"):
    raise unittest.SkipTest("langchain_core not installed")

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from etfagents.agents.analysts.social_media_analyst import create_social_media_analyst

_VALIDATION_PASSED_JSON = '{"score": 9, "pass": true, "critical_issues": [], "minor_issues": [], "missing_elements": [], "general_comment": "OK"}'
_VALID_CATALYST_REPORT = (
    "重仓股新闻和宏观事件对ETF形成中性偏积极影响，真实支撑仍需等待行业催化扩散。\n\n"
    "一、情绪主线与权重影响\n"
    "（一）产品情绪与讨论强弱\n"
    "Report content。\n\n"
    "二、事件传导与定价辨别\n"
    "（一）宏观事件传导\n"
    "Report content。\n"
    "（二）真实支撑与短期噪声\n"
    "Report content。\n\n"
    "三、后续触发与验证要点\n"
    "（一）后续监控要点\n"
    "Report content。\n\n"
    "四、结论与跟踪表\n"
    "| 事件 | ETF影响 | 跟踪表 |\n"
    "| --- | --- | --- |\n"
    "| 宏观新闻 | 中性 | 继续观察 |"
)

class _CapturingLLM(RunnableLambda):
    """Mock LLM compatible with prompt | llm chain composition."""

    def __init__(self):
        super().__init__(func=self._invoke)

    def _invoke(self, prompt, **kwargs):
        if "报告质量审核员" in str(prompt):
            return AIMessage(content=_VALIDATION_PASSED_JSON)
        return AIMessage(content=_VALID_CATALYST_REPORT)

class SocialMediaAnalystTests(unittest.TestCase):
    @patch("etfagents.agents.analysts.social_media_analyst.get_news_for_queries")
    @patch("etfagents.agents.analysts.social_media_analyst.get_global_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_holdings")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_info")
    def test_social_analyst_returns_sentiment_report(
        self, mock_info, mock_holdings, mock_news, mock_global, mock_queries
    ):
        mock_info.func.return_value = "ETF profile data"
        mock_holdings.func.return_value = "name,weight\n紫金矿业,8.5%\n贵州茅台,6.2%\n"
        mock_news.return_value = "## ticker news\n- Some news"
        mock_global.return_value = "## global news\n- Global event"
        mock_queries.return_value = "## holdings news\n- Holding news"

        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        result = node(
            {
                "company_of_interest": "510300.SH",
                "trade_date": "2026-04-01",
                "messages": [HumanMessage(content="Analyze 510300.SH")],
            }
        )

        self.assertIn("catalyst_sentiment_report", result)
        self.assertIn("Report content", result["catalyst_sentiment_report"])
        self.assertEqual(result["messages"][0].content, result["catalyst_sentiment_report"])

    @patch("etfagents.agents.analysts.social_media_analyst.get_news_for_queries")
    @patch("etfagents.agents.analysts.social_media_analyst.get_global_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_holdings")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_info")
    def test_social_analyst_strips_leaked_transaction_proposal_prefix(
        self, mock_info, mock_holdings, mock_news, mock_global, mock_queries
    ):
        mock_info.func.return_value = "ETF profile data"
        mock_holdings.func.return_value = "name,weight\n紫金矿业,8.5%\n贵州茅台,6.2%\n"
        mock_news.return_value = "## ticker news\n- Some news"
        mock_global.return_value = "## global news\n- Global event"
        mock_queries.return_value = "## holdings news\n- Holding news"

        llm = RunnableLambda(
            lambda prompt, config=None: AIMessage(content=_VALIDATION_PASSED_JSON)
            if "报告质量审核员" in str(prompt)
            else AIMessage(
                content=(
                    "FINAL TRANSACTION PROPOSAL: **OVERWEIGHT**\n\n"
                    "情绪主线仍偏正面，真实支撑仍需等待行业催化扩散。\n\n"
                    "一、情绪主线与权重影响\n"
                    "（一）产品情绪与讨论强弱\n"
                    "报告内容。\n\n"
                    "二、事件传导与定价辨别\n"
                    "（一）宏观事件传导\n"
                    "报告内容。\n"
                    "（二）真实支撑与短期噪声\n"
                    "报告内容。\n\n"
                    "三、后续触发与验证要点\n"
                    "（一）后续监控要点\n"
                    "报告内容。\n\n"
                    "四、结论与跟踪表\n"
                    "| 事件 | ETF影响 | 跟踪表 |\n"
                    "| --- | --- | --- |\n"
                    "| 宏观新闻 | 中性 | 继续观察 |"
                )
            )
        )
        node = create_social_media_analyst(llm)

        result = node(
            {
                "company_of_interest": "510300.SH",
                "trade_date": "2026-04-01",
                "messages": [HumanMessage(content="Analyze 510300.SH")],
            }
        )

        self.assertNotIn("FINAL TRANSACTION PROPOSAL", result["catalyst_sentiment_report"])
        self.assertNotIn("OVERWEIGHT", result["catalyst_sentiment_report"])
        self.assertIn("情绪主线仍偏正面", result["catalyst_sentiment_report"])

    @patch("etfagents.agents.analysts.social_media_analyst.get_news_for_queries")
    @patch("etfagents.agents.analysts.social_media_analyst.get_global_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_holdings")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_info")
    def test_social_analyst_prompt_contains_data_blocks_and_instructions(
        self, mock_info, mock_holdings, mock_news, mock_global, mock_queries
    ):
        mock_info.func.return_value = "ETF profile data"
        mock_holdings.func.return_value = "name,weight\n紫金矿业,8.5%\n"
        mock_news.return_value = "## ticker news\n- Some news"
        mock_global.return_value = "## global news\n- Global event"
        mock_queries.return_value = "## holdings news\n- Holding news"

        captured = {}

        def capturing_func(input, config=None):
            text = str(input)
            # Capture the main system prompt (not the validation judge prompt)
            if "报告质量审核员" not in text and "prompt" not in captured:
                captured["prompt"] = text
            if "报告质量审核员" in text:
                return AIMessage(content=_VALIDATION_PASSED_JSON)
            return AIMessage(content="Report content")

        llm = RunnableLambda(capturing_func)
        node = create_social_media_analyst(llm)

        node(
            {
                "company_of_interest": "510300.SH",
                "trade_date": "2026-04-01",
                "messages": [HumanMessage(content="Analyze 510300.SH")],
            }
        )

        system_msg = captured.get("prompt", "")
        self.assertIn("<etf_info>", system_msg)
        self.assertIn("<etf_holdings>", system_msg)
        self.assertIn("<ticker_news>", system_msg)
        self.assertIn("<holdings_news>", system_msg)
        self.assertIn("<global_news>", system_msg)
        self.assertIn("ETF profile data", system_msg)
        self.assertIn("紫金矿业", system_msg)
        self.assertIn("不限于ETF产品本身", system_msg)
        self.assertIn("主导行业", system_msg)
        self.assertIn("真实支撑与短期噪声", system_msg)
        self.assertIn("不得使用英文标签", system_msg)
        self.assertIn("跨数据源比对", system_msg)
        self.assertIn("区分事实与观点", system_msg)
        self.assertNotIn("FINAL TRANSACTION PROPOSAL", system_msg)

    @patch("etfagents.agents.analysts.social_media_analyst.get_news_for_queries")
    @patch("etfagents.agents.analysts.social_media_analyst.get_global_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_news")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_holdings")
    @patch("etfagents.agents.analysts.social_media_analyst.get_etf_info")
    def test_social_analyst_parses_holding_names(
        self, mock_info, mock_holdings, mock_news, mock_global, mock_queries
    ):
        mock_info.func.return_value = "ETF profile data"
        mock_holdings.func.return_value = (
            "# ETF holdings for 510300.SH\n"
            "# Total records: 10\n\n"
            "name,weight,stk_code\n"
            "紫金矿业,8.5%,601899.SH\n"
            "贵州茅台,6.2%,600519.SH\n"
            "宁德时代,5.1%,300750.SZ\n"
            "招商银行,4.8%,600036.SH\n"
        )
        mock_news.return_value = "## ticker news"
        mock_global.return_value = "## global news"
        mock_queries.return_value = "## holdings news"

        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        node(
            {
                "company_of_interest": "510300.SH",
                "trade_date": "2026-04-01",
                "messages": [HumanMessage(content="Analyze 510300.SH")],
            }
        )

        # Should have called get_news_for_queries with top 3 holding names
        mock_queries.assert_called_once()
        call_args = mock_queries.call_args[0]
        queries = call_args[0]
        self.assertEqual(queries, ["紫金矿业", "贵州茅台", "宁德时代"])

if __name__ == "__main__":
    unittest.main()
