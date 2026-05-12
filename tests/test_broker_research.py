import copy
import unittest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.broker_research_analyst import create_broker_research_analyst
from etfagents.agents.analysts.etf_industry_research_analyst import create_etf_industry_research_analyst
from etfagents.agents.analysts.stock_research_analyst import create_stock_research_analyst
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
    def test_resolve_selected_analysts_skips_a_share_only_research_for_non_a_share(self):
        selected, skipped = TradingAgentsGraph.resolve_selected_analysts(
            ["market", "broker_research", "stock_research"],
            "AAPL",
        )

        self.assertEqual(["market"], selected)
        self.assertEqual(["broker_research", "stock_research"], skipped)

    def test_resolve_selected_analysts_keeps_research_for_a_share_raw_digits(self):
        selected, skipped = TradingAgentsGraph.resolve_selected_analysts(
            ["market", "broker_research", "stock_research"],
            "601899",
        )

        self.assertEqual(["market", "broker_research", "stock_research"], selected)
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
                normalize_chinese_role_terms("ETF持仓映射行业研究分析师与ETF头部企业研究分析师"),
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


class BrokerResearchAnalystTests(unittest.TestCase):
    """Tests for the broker research analyst node."""

    def test_analyst_returns_research_report_field(self):
        llm = _CapturingLLM(
            "# Broker Research Cross-Analysis\n\n"
            "Consensus: Most brokers are bullish on growth prospects."
        )
        node = create_broker_research_analyst(llm)

        with patch(
            "etfagents.agents.analysts.broker_research_analyst.run_tool_report_chain",
            return_value=(
                AIMessage(content="# Broker Research Cross-Analysis\n\nConsensus view."),
                "# Broker Research Cross-Analysis\n\nConsensus view.",
            ),
        ):
            result = node(
                {
                    "company_of_interest": "601899.SH",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 601899.SH")],
                }
            )

        self.assertIn("research_report", result)
        self.assertIn("Broker Research Cross-Analysis", result["research_report"])
        self.assertEqual(result["messages"][0].content, result["research_report"])

    def test_analyst_prompt_includes_cross_analysis_instruction(self):
        llm = _CapturingLLM("Report content")
        node = create_broker_research_analyst(llm)

        captured_args = {}
        original_run = "etfagents.agents.analysts.broker_research_analyst.run_tool_report_chain"

        def mock_run(*args, **kwargs):
            captured_args["system_message"] = kwargs.get("system_message", "")
            captured_args["prompt_template"] = args[0]
            return (AIMessage(content="Report content"), "Report content")

        with patch(original_run, side_effect=mock_run):
            node(
                {
                    "company_of_interest": "300750.SZ",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 300750.SZ")],
                }
            )

        system_msg = captured_args.get("system_message", "")
        self.assertIn("cross-analys", system_msg.lower())
        self.assertIn("consensus", system_msg.lower())
        self.assertIn("divergence", system_msg.lower())


class StockResearchAnalystTests(unittest.TestCase):
    """Tests for the stock research analyst node."""

    def test_analyst_returns_stock_report_field(self):
        llm = _CapturingLLM(
            "# Stock Research Cross-Analysis\n\n"
            "Consensus: Most brokers rate the stock as Buy."
        )
        node = create_stock_research_analyst(llm)

        with patch(
            "etfagents.agents.analysts.stock_research_analyst.run_tool_report_chain",
            return_value=(
                AIMessage(content="# Stock Research Cross-Analysis\n\nConsensus view."),
                "# Stock Research Cross-Analysis\n\nConsensus view.",
            ),
        ):
            result = node(
                {
                    "company_of_interest": "601899.SH",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 601899.SH")],
                }
            )

        self.assertIn("stock_report", result)
        self.assertIn("Stock Research Cross-Analysis", result["stock_report"])
        self.assertEqual(result["messages"][0].content, result["stock_report"])

    def test_analyst_prompt_includes_cross_analysis_instruction(self):
        llm = _CapturingLLM("Report content")
        node = create_stock_research_analyst(llm)

        captured_args = {}
        original_run = "etfagents.agents.analysts.stock_research_analyst.run_tool_report_chain"

        def mock_run(*args, **kwargs):
            captured_args["system_message"] = kwargs.get("system_message", "")
            captured_args["prompt_template"] = args[0]
            return (AIMessage(content="Report content"), "Report content")

        with patch(original_run, side_effect=mock_run):
            node(
                {
                    "company_of_interest": "300750.SZ",
                    "trade_date": "2026-04-01",
                    "messages": [HumanMessage(content="Analyze 300750.SZ")],
                }
            )

        system_msg = captured_args.get("system_message", "")
        self.assertIn("cross-analys", system_msg.lower())
        self.assertIn("consensus", system_msg.lower())
        self.assertIn("divergence", system_msg.lower())
        self.assertIn("earnings", system_msg.lower())
        self.assertIn("valuation", system_msg.lower())


class ETFIndustryResearchAnalystTests(unittest.TestCase):
    def test_title_lead_before_first_section_is_removed(self):
        llm = _CapturingLLM("Report content")
        node = create_etf_industry_research_analyst(llm)

        raw_report = (
            "# ETF持仓映射行业研究分析报告\n\n"
            "该ETF的行业暴露主要由核心重仓股映射出的主导产业驱动。\n\n"
            "## 一、总体研判\n\n"
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
        self.assertNotIn("该ETF的行业暴露主要由核心重仓股映射出的主导产业驱动", rendered)
        self.assertIn("# ETF持仓映射行业研究分析报告", rendered)
        self.assertIn("一、总体研判", rendered)

    def test_section_lead_meta_prefix_is_stripped(self):
        llm = _CapturingLLM("Report content")
        node = create_etf_industry_research_analyst(llm)

        raw_report = (
            "# ETF持仓映射行业研究分析报告\n\n"
            "重仓行业景气仍在扩散，高权重板块对估值弹性贡献更大。\n\n"
            "## 一、总体研判\n\n"
            "本部分结论表明，该ETF重仓新能源与金融科技，对无风险利率下行更敏感。\n\n"
            "### （一）共识观点\n\n"
            "多数机构看多景气延续。\n\n"
            "## 二、深度分析\n\n"
            "本部分结论表明，政策催化仍在延续，行业景气尚未逆转。\n\n"
            "### （一）量化对比\n\n"
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

    def test_prompt_starts_directly_at_first_section_and_forbids_meta_section_leads(self):
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
        self.assertIn("do NOT insert a separate title lead", system_msg)
        self.assertIn("Do NOT use lead-ins such as '本部分结论表明'", system_msg)

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
