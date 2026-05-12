import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.etf_industry_research_analyst import (
    create_etf_industry_research_analyst,
)
from etfagents.agents.analysts.etf_market_analyst import (
    create_etf_market_analyst,
)
from etfagents.agents.analysts.news_analyst import (
    create_news_analyst,
)
from etfagents.agents.analysts.social_media_analyst import (
    create_social_media_analyst,
)
from etfagents.agents.analysts.etf_structure_analyst import (
    create_etf_structure_analyst,
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
        self.assertIn("title lead", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)


class EtfStructureAnalystPromptTests(unittest.TestCase):
    def test_prompt_forces_judgment_before_data_dump(self):
        llm = _CapturingLLM()
        node = create_etf_structure_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_structure_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "159980.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159980.SZ")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn(
            "judgment first -> evidence second -> ETF/industry implication last",
            system_msg,
        )
        self.assertIn(
            "Never output three or more naked data fragments in a row",
            system_msg,
        )
        self.assertIn(
            "Do NOT enumerate contracts one by one with parallel sentence templates",
            system_msg,
        )
        self.assertIn(
            "对ETF行业链配置有什么含义",
            system_msg,
        )
        self.assertIn("title lead", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)


class EtfMarketAnalystPromptTests(unittest.TestCase):
    def test_prompt_requires_title_lead_and_plain_language_trading_explanation(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("title lead", system_msg)
        self.assertIn("Do NOT write unexplained phrases such as '标准多头发散形态'", system_msg)
        self.assertIn("这意味着什么", system_msg)
        self.assertIn("对交易应该怎么做", system_msg)
        self.assertIn("Use EXACTLY two top-level sections (一、二)", system_msg)
        self.assertIn("Do NOT introduce headings like '核心交易信号', '结论依据'", system_msg)
        self.assertIn("without any sub-heading", system_msg)
        self.assertIn("must NOT have a separate lead paragraph or hat paragraph", system_msg)


class EtfNewsAndSentimentAnalystPromptTests(unittest.TestCase):
    def test_news_prompt_starts_directly_at_first_section(self):
        llm = _CapturingLLM()
        node = create_news_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.news_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("Start the visible report body directly at '一、总体研判'", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)

    def test_social_prompt_starts_directly_at_first_section(self):
        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        captured = {}

        def _mock_run(*args, **kwargs):
            captured["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.social_media_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        system_msg = captured["system_message"]
        self.assertIn("Start the visible report body directly at '一、总体研判'", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)


class EtfAnalystTitleLeadBackfillTests(unittest.TestCase):
    def test_stock_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_etf_stock_research_analyst(llm)

        raw_report = (
            "# ETF头部持仓研究分析报告\n\n"
            "## 一、总体研判\n\n"
            "高权重个股盈利分化继续扩大。"
        )

        with patch(
            "etfagents.agents.analysts.etf_stock_research_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        rendered = result["top_holdings_report"]
        self.assertIn("该ETF头部持仓的盈利修复、估值分化与权重集中度共同决定组合的收益来源与回撤来源。", rendered)
        self.assertLess(
            rendered.index("该ETF头部持仓的盈利修复、估值分化与权重集中度共同决定组合的收益来源与回撤来源。"),
            rendered.index("一、总体研判"),
        )

    def test_structure_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_etf_structure_analyst(llm)

        raw_report = (
            "# ETF中观大宗商品分析报告\n\n"
            "## 一、核心矛盾与主线判断\n\n"
            "上游成本压力与下游利润承压并存。"
        )

        with patch(
            "etfagents.agents.analysts.etf_structure_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "159980.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159980.SZ")],
                }
            )

        rendered = result["meso_commodity_report"]
        self.assertIn("商品链异常更像是对宏观与产业链矛盾的提前定价", rendered)
        self.assertLess(
            rendered.index("商品链异常更像是对宏观与产业链矛盾的提前定价"),
            rendered.index("一、核心矛盾与主线判断"),
        )

    def test_market_report_missing_title_lead_is_backfilled(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        raw_report = (
            "# ETF市场与资金流分析报告\n\n"
            "## 一、趋势与动量\n\n"
            "价格仍运行在关键均线之上。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst._etf_market_report_needs_rewrite",
            return_value=False,
        ):
            result = node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        rendered = result["market_flow_report"]
        self.assertIn("该ETF当前量价结构更接近趋势延续还是震荡回撤", rendered)
        self.assertLess(
            rendered.index("该ETF当前量价结构更接近趋势延续还是震荡回撤"),
            rendered.index("一、趋势与动量"),
        )

    def test_news_report_title_lead_before_first_section_is_removed(self):
        llm = _CapturingLLM()
        node = create_news_analyst(llm)

        raw_report = (
            "# ETF宏观框架分析报告\n\n"
            "该ETF的宏观敏感性主要由利率路径、信用环境、政策节奏与核心暴露方向共同决定。\n\n"
            "## 一、总体研判\n\n"
            "利率与政策预期继续主导配置方向。"
        )

        with patch(
            "etfagents.agents.analysts.news_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        rendered = result["macro_regime_report"]
        self.assertNotIn("该ETF的宏观敏感性主要由利率路径、信用环境、政策节奏与核心暴露方向共同决定", rendered)
        self.assertIn("# ETF宏观框架分析报告", rendered)
        self.assertIn("一、总体研判", rendered)

    def test_sentiment_report_title_lead_before_first_section_is_removed(self):
        llm = _CapturingLLM()
        node = create_social_media_analyst(llm)

        raw_report = (
            "# ETF舆情与事件影响分析报告\n\n"
            "当前影响该ETF定价的舆情与事件不在于 headline 数量。\n\n"
            "## 一、总体研判\n\n"
            "主导板块事件催化仍强于产品层面噪声。"
        )

        with patch(
            "etfagents.agents.analysts.social_media_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "company_of_interest": "510300.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        rendered = result["catalyst_sentiment_report"]
        self.assertNotIn("当前影响该ETF定价的舆情与事件不在于 headline 数量", rendered)
        self.assertIn("# ETF舆情与事件影响分析报告", rendered)
        self.assertIn("一、总体研判", rendered)

    def test_market_report_strips_conclusion_basis_label(self):
        llm = _CapturingLLM()
        node = create_etf_market_analyst(llm)

        raw_report = (
            "# ETF市场与资金流分析报告\n\n"
            "偏多格局延续，但确认信号仍需要量能配合。\n\n"
            "## 一、市场结构与量价诊断\n\n"
            "### （一）趋势与动量\n\n"
            "**结论依据**：10日均线继续上穿20日均线。\n\n"
            "## 二、交易确认与执行计划\n\n"
            "### （一）信号确认与决策\n\n"
            "若回踩不破支撑，可继续持有。"
        )

        with patch(
            "etfagents.agents.analysts.etf_market_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ), patch(
            "etfagents.agents.analysts.etf_market_analyst._etf_market_report_needs_rewrite",
            return_value=False,
        ):
            result = node(
                {
                    "company_of_interest": "159949.SZ",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        rendered = result["market_flow_report"]
        self.assertNotIn("结论依据", rendered)
        self.assertNotIn("### （一）信号确认与决策", rendered)
        self.assertIn("10日均线继续上穿20日均线。", rendered)


if __name__ == "__main__":
    unittest.main()
