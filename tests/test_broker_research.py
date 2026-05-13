import copy
import unittest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.etf_industry_research_analyst import create_etf_industry_research_analyst
from etfagents.agents.utils.agent_utils import localize_role_name, normalize_chinese_role_terms
from etfagents.agents.utils.agent_states import AgentState
from etfagents.agents.utils.research_report_tools import get_broker_research, get_stock_research
from etfagents.dataflows.config import get_config, set_config
from etfagents.dataflows.interface import VENDOR_METHODS, TOOLS_CATEGORIES, is_a_share_ticker
from etfagents.dataflows.exceptions import DataVendorUnavailable
from etfagents.default_config import DEFAULT_CONFIG
from etfagents.graph.trading_graph import TradingAgentsGraph


class _CapturingLLM:
    """Mock LLM that records prompts and returns a fixed response."""

    def __init__(self, final_content="Default response"):
        self.final_content = final_content
        self.prompts = []

    def bind_tools(self, tools):
        return self

    def invoke(self, prompt, **kwargs):
        self.prompts.append(prompt if isinstance(prompt, str) else str(prompt))
        return AIMessage(content=self.final_content)


class BrokerResearchRoutingTests(unittest.TestCase):
    """Tests for broker research vendor routing registration."""

    def test_broker_research_in_vendor_methods(self):
        self.assertIn("get_broker_research", VENDOR_METHODS)
        self.assertIn("tushare", VENDOR_METHODS["get_broker_research"])

    def test_broker_research_in_tool_categories(self):
        self.assertIn("broker_research", TOOLS_CATEGORIES)
        tools = TOOLS_CATEGORIES["broker_research"]["tools"]
        self.assertIn("get_broker_research", tools)

    def test_default_config_has_broker_research(self):
        self.assertIn("broker_research", DEFAULT_CONFIG["data_vendors"])
        self.assertIn("get_broker_research", DEFAULT_CONFIG["tool_vendors"])

    def test_stock_research_in_vendor_methods(self):
        self.assertIn("get_stock_research", VENDOR_METHODS)
        self.assertIn("tushare", VENDOR_METHODS["get_stock_research"])

    def test_stock_research_in_tool_categories(self):
        self.assertIn("stock_research", TOOLS_CATEGORIES)
        tools = TOOLS_CATEGORIES["stock_research"]["tools"]
        self.assertIn("get_stock_research", tools)

    def test_default_config_has_stock_research(self):
        self.assertIn("stock_research", DEFAULT_CONFIG["data_vendors"])
        self.assertIn("get_stock_research", DEFAULT_CONFIG["tool_vendors"])

    def test_is_a_share_ticker_accepts_suffix_and_raw_digits(self):
        self.assertTrue(is_a_share_ticker("601899.SH"))
        self.assertTrue(is_a_share_ticker("601899"))
        self.assertFalse(is_a_share_ticker("0700.HK"))
        self.assertFalse(is_a_share_ticker("AAPL"))


class AnalystSelectionCompatibilityTests(unittest.TestCase):
    def test_resolve_selected_analysts_returns_all_analysts(self):
        selected, skipped = TradingAgentsGraph.resolve_selected_analysts(
            ["social", "news"],
            "AAPL",
        )

        self.assertEqual(["social", "news"], selected)
        self.assertEqual([], skipped)


class IndustryResearchNamingTests(unittest.TestCase):
    def test_localize_role_name_supports_industry_research_analyst(self):
        original_config = copy.deepcopy(get_config())
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)
        try:
            self.assertEqual("行业研究分析师", localize_role_name("Industry Research Analyst"))
            self.assertEqual("行业研究分析师", localize_role_name("Broker Research Analyst"))
            self.assertEqual("行业研究分析师", localize_role_name("ETF Holdings-Industry Research Analyst"))
            self.assertEqual("个股研究分析师", localize_role_name("Stock Research Analyst"))
            self.assertEqual("个股研究分析师", localize_role_name("ETF Top Holdings Research Analyst"))
            self.assertEqual(
                "行业研究分析师与个股研究分析师",
                normalize_chinese_role_terms("ETF持仓行业研究分析师与ETF头部企业研究分析师"),
            )
        finally:
            set_config(original_config)


class BrokerResearchToolTests(unittest.TestCase):
    """Tests for the get_broker_research LangChain tool."""

    @patch("etfagents.agents.utils.research_report_tools.route_to_vendor")
    def test_tool_calls_route_to_vendor(self, mock_route):
        mock_route.return_value = "# Broker Research Reports\n\nSome reports"
        result = get_broker_research.invoke({
            "ticker": "601899.SH",
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
        })
        mock_route.assert_called_once_with(
            "get_broker_research", "601899.SH", "2026-03-01", "2026-04-01"
        )
        self.assertIn("Broker Research Reports", result)


class StockResearchToolTests(unittest.TestCase):
    """Tests for the get_stock_research LangChain tool."""

    @patch("etfagents.agents.utils.research_report_tools.route_to_vendor")
    def test_tool_calls_route_to_vendor(self, mock_route):
        mock_route.return_value = "# Individual Stock Research Reports\n\nSome reports"
        result = get_stock_research.invoke({
            "ticker": "601899.SH",
            "start_date": "2026-03-01",
            "end_date": "2026-04-01",
        })
        mock_route.assert_called_once_with(
            "get_stock_research", "601899.SH", "2026-03-01", "2026-04-01"
        )
        self.assertIn("Stock Research Reports", result)


class ETFIndustryResearchAnalystTests(unittest.TestCase):
    def test_title_lead_before_first_section_is_backfilled(self):
        llm = _CapturingLLM("Report content")
        node = create_etf_industry_research_analyst(llm)

        raw_report = (
            "# ETF持仓行业研究分析报告\n\n"
            "## 一、行业主线与分歧焦点\n\n"
            "行业景气回升，重仓暴露集中。"
        )

        with patch(
            "etfagents.agents.analysts.etf_industry_research_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "asset_symbol": "510300.SH",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        rendered = result["holdings_industry_report"]
        self.assertIn("该ETF的行业暴露强弱取决于重仓股指向的主导产业，是否同时具备景气延续、政策支撑与盈利兑现三重确认。", rendered)
        self.assertFalse(rendered.startswith("#"))
        self.assertIn("一、行业主线与分歧焦点", rendered)
        self.assertLess(
            rendered.index("该ETF的行业暴露强弱取决于重仓股指向的主导产业，是否同时具备景气延续、政策支撑与盈利兑现三重确认。"),
            rendered.index("一、行业主线与分歧焦点"),
        )

    def test_section_lead_meta_prefix_is_stripped(self):
        llm = _CapturingLLM("Report content")
        node = create_etf_industry_research_analyst(llm)

        raw_report = (
            "# ETF持仓行业研究分析报告\n\n"
            "重仓行业景气仍在扩散，高权重板块对估值弹性贡献更大。\n\n"
            "## 一、行业主线与分歧焦点\n\n"
            "本部分结论表明，该ETF重仓新能源与金融科技，对无风险利率下行更敏感。\n\n"
            "### （一）共识主线\n\n"
            "多数机构看多景气延续。\n\n"
            "## 二、景气、政策与产业链验证\n\n"
            "本部分结论表明，政策催化仍在延续，行业景气尚未逆转。\n\n"
            "### （一）景气与价格对比\n\n"
            "盈利预期仍在修复。"
        )

        with patch(
            "etfagents.agents.analysts.etf_industry_research_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "asset_symbol": "159949.SZ",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        rendered = result["holdings_industry_report"]
        self.assertNotIn("本部分结论表明", rendered)
        self.assertIn("该ETF重仓新能源与金融科技，对无风险利率下行更敏感。", rendered)
        self.assertIn("政策催化仍在延续，行业景气尚未逆转。", rendered)
        self.assertIn("一、行业主线与分歧焦点", rendered)
        self.assertIn("（一）共识主线", rendered)
        self.assertIn("二、景气、政策与产业链验证", rendered)
        self.assertIn("（一）景气与价格对比", rendered)

    def test_industry_noise_paragraph_is_stripped(self):
        llm = _CapturingLLM("Report content")
        node = create_etf_industry_research_analyst(llm)

        raw_report = (
            "主导行业景气仍在修复，配置逻辑没有被破坏。\n\n"
            "## 一、总体研判\n\n"
            "行业分类噪声干扰：兴业银锡（000426.SZ）在数据源中被归类为贵金属，但其核心主业为铅锌锡冶炼。贵金属研报大量聚焦金银宏观定价，缺乏对锡主产国具体验证。\n\n"
            "真正需要跟踪的是有色链供需和价格传导是否继续改善。"
        )

        with patch(
            "etfagents.agents.analysts.etf_industry_research_analyst.run_tool_report_chain",
            return_value=(AIMessage(content=raw_report), raw_report),
        ):
            result = node(
                {
                    "asset_symbol": "159949.SZ",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 159949.SZ")],
                }
            )

        rendered = result["holdings_industry_report"]
        self.assertNotIn("行业分类噪声干扰", rendered)
        self.assertNotIn("数据源中被归类", rendered)
        self.assertIn("真正需要跟踪的是有色链供需和价格传导是否继续改善。", rendered)

    def test_prompt_requires_title_lead_and_forbids_meta_section_leads(self):
        llm = _CapturingLLM("Report content")
        node = create_etf_industry_research_analyst(llm)

        captured_args = {}

        def mock_run(*args, **kwargs):
            captured_args["system_message"] = kwargs.get("system_message", "")
            return (AIMessage(content="Report content"), "Report content")

        with patch(
            "etfagents.agents.analysts.etf_industry_research_analyst.run_tool_report_chain",
            side_effect=mock_run,
        ):
            node(
                {
                    "asset_symbol": "510300.SH",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 510300.SH")],
                }
            )

        system_msg = captured_args.get("system_message", "")
        self.assertIn("Do NOT write a report title or H1 heading", system_msg)
        self.assertIn("不得使用'本部分结论表明'", system_msg)
        self.assertIn("1-2句导语开头", system_msg)
        self.assertIn("数据源分类噪声", system_msg)
        self.assertIn("Make the opening sentence concise and thesis-led", system_msg)
        self.assertIn("do NOT lean on a single repeated word such as '反噬'", system_msg)

class BrokerResearchTushareTests(unittest.TestCase):
    """Tests for the tushare broker reports data function."""

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_raises_for_non_ashare(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        mock_pro = MagicMock()
        mock_client.return_value = mock_pro

        with self.assertRaises(DataVendorUnavailable):
            get_broker_reports("AAPL", "2026-01-01", "2026-04-01")

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_raises_when_no_data(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        import pandas as pd

        mock_pro = MagicMock()
        mock_pro.stock_basic.return_value = pd.DataFrame({"ts_code": ["601899.SH"], "industry": ["有色金属"]})
        mock_pro.research_report.return_value = pd.DataFrame()
        mock_client.return_value = mock_pro

        with self.assertRaises(DataVendorUnavailable):
            get_broker_reports("601899.SH", "2026-01-01", "2026-04-01")

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_formats_reports_as_markdown(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        import pandas as pd

        mock_pro = MagicMock()
        mock_pro.stock_basic.return_value = pd.DataFrame({"ts_code": ["601899.SH"], "industry": ["有色金属"]})
        mock_pro.research_report.return_value = pd.DataFrame({
            "trade_date": ["20260401", "20260328"],
            "inst_csname": ["中信证券", "国泰君安"],
            "title": ["买入评级", "增持评级"],
            "abstr": ["业绩超预期", "估值合理"],
            "author": ["张三", "李四"],
            "report_type": ["行业研报", "行业研报"],
            "name": ["紫金矿业", "紫金矿业"],
            "ts_code": ["601899.SH", "601899.SH"],
            "url": ["http://example.com/1", "http://example.com/2"],
            "ind_name": ["有色金属", "有色金属"],
        })
        mock_client.return_value = mock_pro

        result = get_broker_reports("601899.SH", "2026-01-01", "2026-04-01")

        self.assertIn("Industry Research Reports", result)
        self.assertIn("有色金属", result)
        self.assertIn("中信证券", result)
        self.assertIn("国泰君安", result)
        self.assertIn("买入评级", result)
        self.assertIn("业绩超预期", result)
        # Most recent first
        self.assertTrue(result.index("2026-04-01") < result.index("2026-03-28"))

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_prefers_stock_report_industry_keyword_when_searching_industry_reports(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        import pandas as pd

        mock_pro = MagicMock()
        mock_pro.stock_basic.return_value = pd.DataFrame(
            {"ts_code": ["601899.SH"], "industry": ["有色金属"]}
        )

        def _research_report_side_effect(**kwargs):
            if kwargs.get("report_type") == "个股研报":
                return pd.DataFrame(
                    {
                        "trade_date": ["20260401", "20260320"],
                        "ind_name": ["工业金属", "工业金属"],
                    }
                )
            if kwargs.get("report_type") == "行业研报" and kwargs.get("ind_name") == "工业金属":
                return pd.DataFrame(
                    {
                        "trade_date": ["20260401"],
                        "inst_csname": ["中信证券"],
                        "title": ["工业金属景气上行"],
                        "abstr": ["铜金景气度回升。"],
                        "author": ["张三"],
                        "ts_code": ["601899.SH"],
                        "url": ["http://example.com/1"],
                        "ind_name": ["工业金属"],
                    }
                )
            return pd.DataFrame()

        mock_pro.research_report.side_effect = _research_report_side_effect
        mock_client.return_value = mock_pro

        result = get_broker_reports("601899.SH", "2026-01-01", "2026-04-01")

        self.assertIn("工业金属", result)
        industry_calls = [
            call.kwargs
            for call in mock_pro.research_report.call_args_list
            if call.kwargs.get("report_type") == "行业研报"
        ]
        self.assertEqual(industry_calls[0]["ind_name"], "工业金属")


class StockReportsTushareTests(unittest.TestCase):
    """Tests for the tushare stock reports data function."""

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_raises_for_non_ashare(self, mock_client):
        from etfagents.dataflows.tushare import get_stock_reports

        mock_pro = MagicMock()
        mock_client.return_value = mock_pro

        with self.assertRaises(DataVendorUnavailable):
            get_stock_reports("AAPL", "2026-01-01", "2026-04-01")

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_raises_when_no_data(self, mock_client):
        from etfagents.dataflows.tushare import get_stock_reports

        import pandas as pd

        mock_pro = MagicMock()
        mock_pro.research_report.return_value = pd.DataFrame()
        mock_client.return_value = mock_pro

        with self.assertRaises(DataVendorUnavailable):
            get_stock_reports("601899.SH", "2026-01-01", "2026-04-01")

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_formats_reports_as_markdown(self, mock_client):
        from etfagents.dataflows.tushare import get_stock_reports

        import pandas as pd

        mock_pro = MagicMock()
        mock_pro.research_report.return_value = pd.DataFrame({
            "trade_date": ["20260401", "20260328"],
            "inst_csname": ["中信证券", "国泰君安"],
            "title": ["买入评级", "增持评级"],
            "abstr": ["业绩超预期", "估值合理"],
            "author": ["张三", "李四"],
            "report_type": ["个股研报", "个股研报"],
            "name": ["紫金矿业", "紫金矿业"],
            "ts_code": ["601899.SH", "601899.SH"],
            "url": ["http://example.com/1", "http://example.com/2"],
            "ind_name": ["有色金属", "有色金属"],
        })
        mock_client.return_value = mock_pro

        result = get_stock_reports("601899.SH", "2026-01-01", "2026-04-01")

        self.assertIn("Individual Stock Research Reports", result)
        self.assertIn("601899.SH", result)
        self.assertIn("中信证券", result)
        self.assertIn("国泰君安", result)
        self.assertIn("买入评级", result)
        self.assertIn("业绩超预期", result)
        # Most recent first
        self.assertTrue(result.index("2026-04-01") < result.index("2026-03-28"))


if __name__ == "__main__":
    unittest.main()
