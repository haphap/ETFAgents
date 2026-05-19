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


_VALIDATION_PASSED_JSON = '{"score": 9, "pass": true, "critical_issues": [], "minor_issues": [], "missing_elements": [], "general_comment": "OK"}'


class _CapturingLLM:
    """Mock LLM that records prompts and returns a fixed response."""

    def __init__(self, final_content="Default response"):
        self.final_content = final_content
        self.prompts = []

    def bind_tools(self, tools):
        return self

    def invoke(self, prompt, **kwargs):
        self.prompts.append(prompt if isinstance(prompt, str) else str(prompt))
        # Return valid JSON for validation judge step so it passes cleanly
        if "报告质量审核员" in str(prompt):
            return AIMessage(content=_VALIDATION_PASSED_JSON)
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
        self.assertIn("不得使用'本节''本部分''该部分''这一节'等自指式开头", system_msg)
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

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_merges_extra_industry_keywords_for_related_research(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        import pandas as pd

        mock_pro = MagicMock()
        mock_pro.stock_basic.return_value = pd.DataFrame(
            {"ts_code": ["002311.SZ"], "industry": ["农牧饲渔"]}
        )

        def _research_report_side_effect(**kwargs):
            if kwargs.get("report_type") == "个股研报":
                return pd.DataFrame(
                    {
                        "trade_date": ["20260508"],
                        "ind_name": ["养殖业"],
                    }
                )
            if kwargs.get("report_type") != "行业研报":
                return pd.DataFrame()
            ind_name = kwargs.get("ind_name")
            if ind_name == "养殖业":
                return pd.DataFrame(
                    {
                        "trade_date": ["20260507"],
                        "inst_csname": ["华创证券"],
                        "title": ["生猪产能去化加速"],
                        "abstr": ["养殖利润承压，产能去化预期升温。"],
                        "author": ["张三"],
                        "ts_code": ["002311.SZ"],
                        "url": ["http://example.com/hog"],
                        "ind_name": ["养殖业"],
                    }
                )
            if ind_name == "农牧饲渔":
                return pd.DataFrame(
                    {
                        "trade_date": ["20260508"],
                        "inst_csname": ["中邮证券"],
                        "title": ["养殖成本下降，饲料业务盈利高增"],
                        "abstr": ["饲料销量恢复，成本下降带动盈利改善。"],
                        "author": ["李四"],
                        "ts_code": ["002311.SZ"],
                        "url": ["http://example.com/feed"],
                        "ind_name": ["农牧饲渔"],
                    }
                )
            return pd.DataFrame()

        mock_pro.research_report.side_effect = _research_report_side_effect
        mock_client.return_value = mock_pro

        result = get_broker_reports(
            "002311.SZ",
            "2026-01-15",
            "2026-05-15",
            extra_ind_names=["农牧饲渔"],
        )

        self.assertIn("生猪产能去化加速", result)
        self.assertIn("养殖成本下降，饲料业务盈利高增", result)
        industry_calls = [
            call.kwargs["ind_name"]
            for call in mock_pro.research_report.call_args_list
            if call.kwargs.get("report_type") == "行业研报"
        ]
        self.assertEqual(industry_calls[:2], ["养殖业", "农牧饲渔"])

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_skip_industry_resolution_uses_explicit_keywords(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        import pandas as pd

        mock_pro = MagicMock()
        mock_pro.research_report.return_value = pd.DataFrame(
            {
                "trade_date": ["20260515"],
                "inst_csname": ["中信证券"],
                "title": ["互联网行业跟踪"],
                "abstr": ["平台经济基本面改善。"],
                "author": ["张三"],
                "ts_code": ["600050.SH"],
                "url": ["http://example.com/internet"],
                "ind_name": ["互联网"],
            }
        )
        mock_client.return_value = mock_pro

        result = get_broker_reports(
            "00700.HK",
            "2026-01-15",
            "2026-05-15",
            extra_ind_names=["互联网"],
            _skip_market_check=True,
            _skip_industry_resolution=True,
        )

        self.assertIn("Industry Research Reports for 互联网", result)
        mock_pro.stock_basic.assert_not_called()
        self.assertEqual(mock_pro.research_report.call_count, 1)
        call_kwargs = mock_pro.research_report.call_args.kwargs
        self.assertEqual(call_kwargs["ind_name"], "互联网")
        self.assertNotIn("ts_code", call_kwargs)

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_skip_industry_resolution_requires_explicit_keywords(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        mock_client.return_value = MagicMock()

        with self.assertRaisesRegex(DataVendorUnavailable, "Explicit industry keywords"):
            get_broker_reports(
                "00700.HK",
                "2026-01-15",
                "2026-05-15",
                _skip_market_check=True,
                _skip_industry_resolution=True,
            )

    @patch("etfagents.dataflows.tushare._get_pro_client")
    def test_skip_market_check_without_explicit_resolution_rejects_hk(self, mock_client):
        from etfagents.dataflows.tushare import get_broker_reports

        mock_client.return_value = MagicMock()

        with self.assertRaisesRegex(DataVendorUnavailable, "_skip_industry_resolution=True"):
            get_broker_reports(
                "00700.HK",
                "2026-01-15",
                "2026-05-15",
                extra_ind_names=["互联网"],
                _skip_market_check=True,
            )


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
