
import importlib.util
import unittest
if not importlib.util.find_spec("pandas"):
    raise unittest.SkipTest("pandas not installed")

import copy
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
from langgraph.prebuilt import ToolNode

from etfagents.agents.utils.etf_data_tools import (
    _AH_SHARE_MAP,
    _HK_BENCHMARK_PROXY_BASKETS,
    _build_constituent_frame,
    _match_commodity_proxy_basket,
    _hk_industry_to_broker_keywords,
    _related_broker_industry_keywords,
    get_etf_holdings,
    get_etf_indicators,
    get_etf_industry_research,
    get_etf_top_holdings_research,
)
from etfagents.backtest.cache import BacktestSignalStore
from etfagents.dataflows.exceptions import DataVendorUnavailable, MissingEtfHoldings
from etfagents.dataflows.config import get_config, set_config
from etfagents.dataflows.config import backtest_context
from etfagents.dataflows.interface import TOOLS_CATEGORIES, VENDOR_METHODS, get_category_for_method
from etfagents.dataflows.tushare import get_etf_universe
from etfagents.dataflows.akshare import get_hk_security_industry
from etfagents.graph.conditional_logic import ConditionalLogic
from etfagents.graph.etf_graph import (
    ETF_DEFAULT_CONFIG,
    EtfAgentsGraph,
    _sanitize_candidate_payload_text,
    _selected_analyst_report_keys,
)
from etfagents.graph.etf_setup import ETFGraphSetup

class ETFExtensionTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())

    def tearDown(self):
        set_config(self.original_config)

    @patch("etfagents.dataflows.akshare.get_hk_security_profile")
    def test_akshare_hk_security_industry_extracts_profile_field(self, mock_profile):
        mock_profile.return_value = pd.DataFrame([{"所属行业": "互联网服务"}])

        self.assertEqual(get_hk_security_industry("00700.HK"), "互联网服务")
        mock_profile.assert_called_once_with("00700.HK")

    @patch("etfagents.dataflows.akshare.get_hk_security_profile")
    def test_akshare_hk_security_industry_rejects_non_industry_row_fallback(self, mock_profile):
        mock_profile.return_value = pd.DataFrame([["所属行业", "腾讯控股有限公司", "互联网服务"]])

        self.assertEqual(get_hk_security_industry("00700.HK"), "互联网服务")

    def test_ah_share_map_keys_match_basket_members(self):
        basket_members = {
            member["ts_code"]
            for basket in _HK_BENCHMARK_PROXY_BASKETS
            for member in basket["members"]
        }

        self.assertEqual(basket_members, set(_AH_SHARE_MAP))
        self.assertFalse(
            any(
                "a_share_code" in member
                for basket in _HK_BENCHMARK_PROXY_BASKETS
                for member in basket["members"]
            )
        )

    def test_hk_industry_to_broker_keywords_mapping_covers_basket_industries(self):
        basket_industries = {
            member["industry"]
            for basket in _HK_BENCHMARK_PROXY_BASKETS
            for member in basket["members"]
        }

        for industry in basket_industries:
            self.assertTrue(_hk_industry_to_broker_keywords(industry), industry)

    def test_etf_methods_are_registered_in_vendor_routing(self):
        self.assertEqual(get_category_for_method("get_etf_price_data"), "etf_market_data")
        self.assertEqual(get_category_for_method("get_etf_info"), "etf_reference_data")
        self.assertIn("get_etf_holdings", TOOLS_CATEGORIES["etf_reference_data"]["tools"])
        self.assertIn("get_etf_share", VENDOR_METHODS)
        self.assertIn("get_etf_universe", TOOLS_CATEGORIES["etf_reference_data"]["tools"])

    def test_etf_default_config_pins_etf_tools_to_tushare(self):
        cfg = copy.deepcopy(ETF_DEFAULT_CONFIG)
        self.assertEqual(cfg["tool_vendors"]["get_etf_price_data"], "tushare")
        self.assertEqual(cfg["tool_vendors"]["get_etf_nav"], "tushare")
        self.assertEqual(cfg["tool_vendors"]["get_etf_holdings"], "tushare")
        self.assertEqual(cfg["tool_vendors"]["get_etf_universe"], "tushare")

    @patch("etfagents.agents.utils.etf_data_tools.route_to_vendor")
    def test_etf_indicator_aliases_normalize_generic_ma_requests(self, mock_route):
        mock_route.return_value = "ok"

        payload = get_etf_indicators.invoke(
            {
                "symbol": "510300.SH",
                "indicator": "MA, MACD_signal, Bollinger_upper",
                "curr_date": "2026-01-15",
                "look_back_days": 60,
            }
        )

        self.assertEqual(payload, "ok\n\nok\n\nok")
        self.assertEqual(
            [call.args[2] for call in mock_route.call_args_list],
            ["close_20_sma", "macds", "boll_ub"],
        )

    def test_etf_graph_keeps_selected_analysts_for_cn_etf(self):
        analysts, skipped = EtfAgentsGraph.resolve_selected_analysts(
            ["market", "news", "etf_structure", "broker_research", "stock_research"],
            "510300.SH",
        )
        self.assertEqual(
            analysts,
            ["market_flow", "macro_regime", "meso_commodity", "holdings_industry", "top_holdings"],
        )
        self.assertEqual(skipped, [])
        self.assertEqual(
            _selected_analyst_report_keys(analysts),
            (
                "market_flow_report",
                "macro_regime_report",
                "meso_commodity_report",
                "holdings_industry_report",
                "top_holdings_report",
            ),
        )
        self.assertEqual(
            _selected_analyst_report_keys(["market", "news", "etf_structure", "broker_research", "stock_research"]),
            _selected_analyst_report_keys(analysts),
        )

    def test_conditional_logic_supports_new_etf_analysts(self):
        logic = ConditionalLogic()

        class _Message:
            def __init__(self, tool_calls):
                self.tool_calls = tool_calls

        state = {"messages": [_Message([{"name": "get_etf_info"}])]}
        self.assertEqual(logic.should_continue_etf_structure(state), "tools_meso_commodity")
        self.assertEqual(logic.should_continue_etf_flow(state), "tools_market_flow")
        self.assertEqual(logic.should_continue_etf_macro(state), "tools_holdings_industry")

    def test_etf_graph_setup_maps_legacy_clear_routes_to_renamed_nodes(self):
        setup = ETFGraphSetup(
            quick_thinking_llm=object(),
            deep_thinking_llm=object(),
            tool_nodes={
                "market_flow": ToolNode([]),
                "catalyst_sentiment": ToolNode([]),
                "macro_regime": ToolNode([]),
                "meso_commodity": ToolNode([]),
                "holdings_industry": ToolNode([]),
                "top_holdings": ToolNode([]),
            },
            conditional_logic=ConditionalLogic(),
        )

        self.assertEqual(
            setup._analyst_route_map("market_flow")["Msg Clear Market"],
            "Msg Clear Market & Flow",
        )
        self.assertEqual(
            setup._analyst_route_map("macro_regime")["Msg Clear News"],
            "Msg Clear Macro Regime",
        )
        self.assertEqual(
            setup._analyst_route_map("meso_commodity")["Msg Clear ETF Structure"],
            "Msg Clear Meso Commodity",
        )
        self.assertEqual(
            setup._analyst_route_map("holdings_industry")["Msg Clear Industry Research"],
            "Msg Clear ETF Holdings-Industry Research",
        )
        self.assertEqual(
            setup._analyst_route_map("top_holdings")["Msg Clear Stock Research"],
            "Msg Clear ETF Top Holdings Research",
        )

    def test_candidate_pool_is_ranked_by_final_rating(self):
        graph = object.__new__(EtfAgentsGraph)

        def _fake_propagate(ticker, _trade_date):
            ratings = {
                "510300.SH": "OVERWEIGHT",
                "159915.SZ": "BUY",
                "513100.SH": "HOLD",
            }
            rating = ratings[ticker]
            return (
                {
                    "market_flow_report": f"market-flow-{ticker}",
                    "research_allocation_plan": f"research-{ticker}",
                    "trader_allocation_plan": f"trader-{ticker}",
                    "final_allocation_decision": f"decision-{ticker}",
                },
                rating,
            )

        graph.propagate = _fake_propagate
        graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE

        ranked = EtfAgentsGraph.analyze_candidate_pool(
            graph,
            ["510300.SH", "159915.SZ", "513100.SH"],
            "2026-01-15",
        )

        self.assertEqual(
            [item["ticker"] for item in ranked],
            ["159915.SZ", "510300.SH", "513100.SH"],
        )
        self.assertEqual(ranked[0]["market_flow_report"], "market-flow-159915.SZ")
        self.assertEqual(ranked[0]["final_allocation_decision"], "decision-159915.SZ")
        self.assertEqual(
            [item["suggested_weight_pct"] for item in ranked],
            [50.0, 33.3, 16.7],
        )
        self.assertEqual(ranked[0]["backtest_signal"]["source"], "candidate_pool")
        self.assertEqual(ranked[0]["backtest_signal"]["target_weight_pct"], 50.0)

    @patch("etfagents.agents.utils.etf_data_tools.get_broker_reports")
    @patch("etfagents.agents.utils.etf_data_tools._resolve_broker_industry_keyword")
    @patch("etfagents.agents.utils.etf_data_tools._get_pro_client")
    @patch("etfagents.agents.utils.etf_data_tools._lookup_a_share_metadata")
    @patch("etfagents.agents.utils.etf_data_tools._load_latest_etf_holdings_frame")
    def test_etf_industry_research_uses_broker_industry_keyword_from_top_holding(
        self,
        mock_holdings_frame,
        mock_lookup_metadata,
        mock_get_pro_client,
        mock_resolve_broker_industry_keyword,
        mock_get_broker_reports,
    ):
        mock_holdings_frame.return_value = (
            "516650.SH",
            pd.DataFrame(
                [
                    {
                        "symbol": "601899.SH",
                        "stk_code": "601899",
                        "holding_weight": 12.3,
                        "stk_mkv_ratio": 12.3,
                        "end_date": "20260331",
                    },
                    {
                        "symbol": "603993.SH",
                        "stk_code": "603993",
                        "holding_weight": 8.1,
                        "stk_mkv_ratio": 8.1,
                        "end_date": "20260331",
                    },
                ]
            ),
        )
        mock_lookup_metadata.side_effect = [
            {"ts_code": "601899.SH", "name": "紫金矿业", "industry": "有色金属"},
            {"ts_code": "603993.SH", "name": "洛阳钼业", "industry": "有色金属"},
        ]
        mock_get_pro_client.return_value = object()
        mock_resolve_broker_industry_keyword.side_effect = [
            ("工业金属", "stock-report ind_name", "有色金属"),
            ("工业金属", "stock-report ind_name", "有色金属"),
        ]
        mock_get_broker_reports.return_value = "# Industry Research Reports for 工业金属"

        result = get_etf_industry_research.invoke(
            {"ticker": "516650.SH", "curr_date": "2026-04-30"}
        )

        self.assertIn("工业金属", result)
        self.assertIn("Keyword source: stock-report ind_name", result)
        self.assertIn("Stock basic industry fallback / comparison: 有色金属", result)
        mock_get_broker_reports.assert_called_once()
        call_args = mock_get_broker_reports.call_args
        self.assertEqual(call_args.args[0], "601899.SH")
        self.assertEqual(call_args.args[2], "2026-04-30")
        self.assertEqual(call_args.kwargs["max_reports"], 5)
        self.assertNotIn("extra_ind_names", call_args.kwargs)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    @patch("etfagents.agents.utils.etf_data_tools.route_to_vendor")
    def test_get_etf_holdings_uses_commodity_producer_proxy_when_disclosure_missing(
        self,
        mock_route_to_vendor,
        mock_query_pro,
    ):
        mock_route_to_vendor.side_effect = MissingEtfHoldings(
            "No ETF holdings data found for '518880.SH' up to 2026-05-15."
        )
        mock_query_pro.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "518880.SH",
                    "name": "黄金ETF",
                    "benchmark": "上海金基准价",
                    "fund_type": "ETF",
                    "invest_type": "商品型",
                    "market": "SH",
                }
            ]
        )

        result = get_etf_holdings.invoke(
            {"ticker": "518880.SH", "curr_date": "2026-05-15"}
        )

        self.assertIn("A-share 黄金 producers", result)
        self.assertIn("山东黄金", result)
        self.assertIn("中金黄金", result)
        self.assertIn("紫金矿业", result)
        self.assertIn("Proxy basket", result)
        self.assertIn("proxy_weight_illustrative_pct", result)
        self.assertIn("Proxy weights are illustrative", result)
        self.assertNotIn("No ETF holdings data found", result)

    @patch("etfagents.agents.utils.etf_data_tools._load_latest_etf_holdings_frame")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_etf_industry_research_propagates_missing_holdings_for_non_commodity_etf(
        self,
        mock_query_pro,
        mock_holdings_frame,
    ):
        message = "No ETF holdings data found for '562500.SH' up to 2026-05-15."
        mock_holdings_frame.side_effect = MissingEtfHoldings(message)
        mock_query_pro.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "562500.SH",
                    "name": "新能源电池ETF",
                    "benchmark": "中证新能源电池主题指数",
                    "fund_type": "ETF",
                    "invest_type": "被动指数型",
                    "market": "SH",
                }
            ]
        )

        with self.assertRaisesRegex(MissingEtfHoldings, re.escape(message)):
            get_etf_industry_research.invoke(
                {"ticker": "562500.SH", "curr_date": "2026-05-15"}
            )

    @patch("etfagents.agents.utils.etf_data_tools._load_latest_etf_holdings_frame")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_etf_industry_research_propagates_missing_holdings_when_profile_is_empty(
        self,
        mock_query_pro,
        mock_holdings_frame,
    ):
        message = "No ETF holdings data found for '518880.SH' up to 2026-05-15."
        mock_holdings_frame.side_effect = MissingEtfHoldings(message)
        mock_query_pro.return_value = pd.DataFrame()

        with self.assertRaisesRegex(MissingEtfHoldings, re.escape(message)):
            get_etf_industry_research.invoke(
                {"ticker": "518880.SH", "curr_date": "2026-05-15"}
            )

    @patch("etfagents.agents.utils.etf_data_tools.get_broker_reports")
    @patch("etfagents.agents.utils.etf_data_tools._resolve_broker_industry_keyword")
    @patch("etfagents.agents.utils.etf_data_tools._get_pro_client")
    @patch("etfagents.agents.utils.etf_data_tools._load_latest_etf_holdings_frame")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_etf_industry_research_falls_back_to_commodity_producer_proxy_when_holdings_missing(
        self,
        mock_query_pro,
        mock_holdings_frame,
        mock_get_pro_client,
        mock_resolve_broker_industry_keyword,
        mock_get_broker_reports,
    ):
        mock_holdings_frame.side_effect = MissingEtfHoldings(
            "No ETF holdings data found for '518880.SH' up to 2026-05-15."
        )
        mock_query_pro.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "518880.SH",
                    "name": "黄金ETF",
                    "benchmark": "上海金基准价",
                    "fund_type": "ETF",
                    "invest_type": "商品型",
                    "market": "SH",
                }
            ]
        )
        mock_get_pro_client.return_value = object()
        mock_resolve_broker_industry_keyword.side_effect = [
            ("贵金属", "stock-report ind_name", "有色金属"),
            ("贵金属", "stock-report ind_name", "有色金属"),
            ("贵金属", "stock-report ind_name", "有色金属"),
        ]
        mock_get_broker_reports.return_value = "# Industry Research Reports for 贵金属"

        result = get_etf_industry_research.invoke(
            {"ticker": "518880.SH", "curr_date": "2026-05-15"}
        )

        self.assertIn("representative A-share 黄金 producers", result)
        self.assertIn("Proxy weight (illustrative)", result)
        self.assertIn("supplementary rather than ETF top-holding analysis", result)
        self.assertIn("山东黄金", result)
        self.assertIn("贵金属", result)
        self.assertEqual(mock_get_broker_reports.call_count, 1)

    @patch("etfagents.agents.utils.etf_data_tools.get_stock_reports")
    @patch("etfagents.agents.utils.etf_data_tools._lookup_a_share_metadata")
    @patch("etfagents.agents.utils.etf_data_tools._load_latest_etf_holdings_frame")
    def test_etf_top_holdings_research_keeps_a_share_heading_for_disclosed_holdings(
        self,
        mock_holdings_frame,
        mock_lookup_metadata,
        mock_get_stock_reports,
    ):
        mock_holdings_frame.return_value = (
            "510300.SH",
            pd.DataFrame(
                [
                    {
                        "symbol": "600519.SH",
                        "stk_code": "600519",
                        "holding_weight": 8.5,
                        "stk_mkv_ratio": 8.5,
                        "end_date": "20260331",
                    },
                    {
                        "symbol": "300750.SZ",
                        "stk_code": "300750",
                        "holding_weight": 7.2,
                        "stk_mkv_ratio": 7.2,
                        "end_date": "20260331",
                    },
                ]
            ),
        )
        mock_lookup_metadata.side_effect = [
            {"ts_code": "600519.SH", "name": "贵州茅台", "industry": "食品饮料"},
            {"ts_code": "300750.SZ", "name": "宁德时代", "industry": "电力设备"},
        ]
        mock_get_stock_reports.return_value = "# Stock Research Reports"

        result = get_etf_top_holdings_research.invoke(
            {"ticker": "510300.SH", "curr_date": "2026-04-30", "top_n": 2}
        )

        self.assertIn("## Top disclosed A-share holdings", result)
        self.assertNotIn("## Top disclosed holdings", result)
        self.assertEqual(mock_get_stock_reports.call_count, 2)

    @patch("etfagents.agents.utils.etf_data_tools.get_stock_reports")
    @patch("etfagents.agents.utils.etf_data_tools._load_latest_etf_holdings_frame")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_etf_top_holdings_research_falls_back_to_commodity_producer_proxy_when_holdings_missing(
        self,
        mock_query_pro,
        mock_holdings_frame,
        mock_get_stock_reports,
    ):
        mock_holdings_frame.side_effect = MissingEtfHoldings(
            "No ETF holdings data found for '518880.SH' up to 2026-05-15."
        )
        mock_query_pro.return_value = pd.DataFrame(
            [
                {
                    "ts_code": "518880.SH",
                    "name": "黄金ETF",
                    "benchmark": "上海金基准价",
                    "fund_type": "ETF",
                    "invest_type": "商品型",
                    "market": "SH",
                }
            ]
        )
        mock_get_stock_reports.return_value = "# Stock Research Reports for 黄金 producer"

        result = get_etf_top_holdings_research.invoke(
            {"ticker": "518880.SH", "curr_date": "2026-05-15"}
        )

        self.assertIn("representative A-share 黄金 producers", result)
        self.assertIn("## Proxy A-share producer basket", result)
        self.assertIn("Proxy weight (illustrative)", result)
        self.assertIn("proxy weight (illustrative)", result)
        self.assertIn("山东黄金", result)
        self.assertIn("# Stock Research Reports for 黄金 producer", result)
        self.assertEqual(mock_get_stock_reports.call_count, 3)

    @patch("etfagents.agents.utils.etf_data_tools.get_broker_reports")
    @patch("etfagents.agents.utils.etf_data_tools._resolve_broker_industry_keyword")
    @patch("etfagents.agents.utils.etf_data_tools._get_pro_client")
    @patch("etfagents.agents.utils.etf_data_tools._lookup_a_share_metadata")
    @patch("etfagents.agents.utils.etf_data_tools._load_latest_etf_holdings_frame")
    def test_etf_industry_research_searches_related_agriculture_keywords(
        self,
        mock_holdings_frame,
        mock_lookup_metadata,
        mock_get_pro_client,
        mock_resolve_broker_industry_keyword,
        mock_get_broker_reports,
    ):
        mock_holdings_frame.return_value = (
            "516810.SH",
            pd.DataFrame(
                [
                    {
                        "symbol": "002311.SZ",
                        "stk_code": "002311",
                        "holding_weight": 10.2,
                        "stk_mkv_ratio": 10.2,
                        "end_date": "20260331",
                    },
                ]
            ),
        )
        mock_lookup_metadata.return_value = {
            "ts_code": "002311.SZ",
            "name": "海大集团",
            "industry": "农牧饲渔",
        }
        mock_get_pro_client.return_value = object()
        mock_resolve_broker_industry_keyword.return_value = (
            "养殖业",
            "stock-report ind_name",
            "农牧饲渔",
        )
        mock_get_broker_reports.return_value = (
            "# Industry Research Reports for 养殖业, 农牧饲渔\n\n"
            "中邮证券_养殖成本下降，饲料业务盈利高增_20260508.pdf"
        )

        result = get_etf_industry_research.invoke(
            {"ticker": "516810.SH", "curr_date": "2026-05-15"}
        )

        self.assertIn("Related industry keywords searched: 农牧饲渔, 养殖业", result)
        self.assertIn("养殖成本下降，饲料业务盈利高增", result)
        call_args = mock_get_broker_reports.call_args
        self.assertEqual(call_args.args[0], "002311.SZ")
        self.assertEqual(call_args.kwargs["extra_ind_names"], ["农牧饲渔", "养殖业"])

    def test_related_agriculture_keywords_ignore_constituent_name_substrings(self):
        row = {
            "industry": "白酒",
            "research_industry": "饮料制造",
            "base_industry": "食品饮料",
            "name": "饲料新材料股份",
        }

        self.assertEqual([], _related_broker_industry_keywords(row))

    def test_match_commodity_proxy_basket_prefers_lithium_for_new_energy_lithium_text(self):
        profile = pd.Series(
            {
                "ts_code": "562500.SH",
                "name": "有色金属新能源锂矿ETF",
                "benchmark": "中证新能源锂矿主题指数",
                "asset_scope": "commodity",
                "exposure_bucket": "commodity_real_asset",
            }
        )

        basket = _match_commodity_proxy_basket(profile)

        self.assertIsNotNone(basket)
        self.assertEqual(basket["label"], "锂")

    def test_match_commodity_proxy_basket_discloses_copper_heavy_industrial_metals_proxy(self):
        profile = pd.Series(
            {
                "ts_code": "159980.SZ",
                "name": "工业金属ETF",
                "benchmark": "中证工业金属主题指数",
                "asset_scope": "commodity",
                "exposure_bucket": "commodity_real_asset",
            }
        )

        basket = _match_commodity_proxy_basket(profile)

        self.assertIsNotNone(basket)
        self.assertEqual(basket["label"], "工业金属")
        self.assertEqual(basket["display_label"], "工业金属（铜偏重代理）")

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_cross_border_etf_uses_hk_proxy_when_holdings_missing(self, mock_query):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": params["ts_code"],
                            "name": {"00700.HK": "腾讯控股", "09988.HK": "阿里巴巴-W"}.get(
                                params["ts_code"],
                                params["ts_code"],
                            ),
                            "market": "主板",
                        }
                    ]
                )
            if api_name == "hk_daily":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": params["ts_code"],
                            "trade_date": "20260514" if params["ts_code"] == "00700.HK" else "20260515",
                            "close": 400.0,
                            "pct_chg": 1.2,
                        }
                    ]
                )
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        ts_code, latest_date, frame = _build_constituent_frame("513130.SH", "2026-05-15", 3)

        self.assertEqual(ts_code, "513130.SH")
        self.assertEqual(latest_date, "20260515")
        self.assertEqual(frame.attrs["source"], "hk_benchmark_proxy")
        self.assertIn("normalized to 100% of the representative proxy basket", frame.attrs["source_note"])
        self.assertAlmostEqual(frame["weight"].sum(), 46.03, places=2)
        self.assertIn("00700.HK", set(frame["ts_code"]))
        self.assertIn("latest_close", frame.columns)

    @patch("etfagents.agents.utils.etf_data_tools._lookup_akshare_hk_industry")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_frame_derives_a_share_code_and_akshare_industry(
        self,
        mock_query,
        mock_lookup_akshare_hk_industry,
    ):
        mock_lookup_akshare_hk_industry.side_effect = lambda code: {
            "00700.HK": "互联网服务",
            "00981.HK": "半导体",
        }.get(code, "")

        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        _, _, frame = _build_constituent_frame("513130.SH", "2026-05-15", 8)

        tencent = frame[frame["ts_code"] == "00700.HK"].iloc[0]
        smic = frame[frame["ts_code"] == "00981.HK"].iloc[0]
        self.assertEqual(tencent["industry"], "互联网服务")
        self.assertEqual(tencent["industry_source"], "akshare profile industry")
        self.assertEqual(smic["a_share_code"], "688981.SH")

    @patch("etfagents.agents.utils.etf_data_tools._lookup_akshare_hk_industry", return_value="")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_frame_falls_back_to_basket_industry_when_akshare_missing(
        self,
        mock_query,
        _mock_lookup_akshare_hk_industry,
    ):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        _, _, frame = _build_constituent_frame("513130.SH", "2026-05-15", 1)

        self.assertEqual(frame.iloc[0]["industry"], "互联网平台")
        self.assertEqual(frame.iloc[0]["industry_source"], "basket fallback industry")

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    @patch("etfagents.agents.utils.etf_data_tools.route_to_vendor")
    def test_get_etf_holdings_returns_hk_proxy_after_tushare_holdings_miss(
        self,
        mock_route,
        mock_query,
    ):
        mock_route.side_effect = MissingEtfHoldings(
            "No ETF holdings data found for '513130.SH' up to 2026-05-15."
        )

        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        result = get_etf_holdings.invoke(
            {"ticker": "513130.SH", "curr_date": "2026-05-15"}
        )

        self.assertIn("Hong Kong 恒生科技 constituents", result)
        self.assertIn("00700.HK", result)
        self.assertIn("latest_hk_close", result)
        self.assertIn("proxy_basket_weight_pct", result)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_etf_research_tools_use_proxy_without_a_share_reports(self, mock_query):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        industry = get_etf_industry_research.invoke(
            {"ticker": "513130.SH", "curr_date": "2026-05-15", "top_n": 2}
        )
        top_holdings = get_etf_top_holdings_research.invoke(
            {"ticker": "513130.SH", "curr_date": "2026-05-15", "top_n": 2}
        )

        self.assertIn("Dominant Hong Kong proxy industries", industry)
        self.assertIn("AkShare HK security profile industries", industry)
        self.assertIn("Proxy Hong Kong benchmark basket", top_holdings)
        self.assertIn("Proxy basket weight", industry)
        self.assertIn("Proxy basket weight", top_holdings)
        self.assertIn("Tushare HK daily snapshot", top_holdings)
        self.assertNotIn("No eligible A-share", industry + top_holdings)

    @patch("etfagents.agents.utils.etf_data_tools.get_broker_reports")
    @patch("etfagents.agents.utils.etf_data_tools.get_stock_reports")
    @patch("etfagents.agents.utils.etf_data_tools._lookup_akshare_hk_industry", return_value="")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_top_holdings_uses_a_share_for_dual_listed(
        self,
        mock_query,
        _mock_lookup_akshare_hk_industry,
        mock_get_stock_reports,
        mock_get_broker_reports,
    ):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query
        mock_get_stock_reports.return_value = "# Individual Stock Research Reports for 688981.SH"
        mock_get_broker_reports.return_value = "# Industry Research Reports for 互联网"

        result = get_etf_top_holdings_research.invoke(
            {"ticker": "513130.SH", "curr_date": "2026-05-15", "top_n": 8}
        )

        self.assertIn("00981.HK -> 688981.SH", result)
        self.assertIn("A+H dual-listed", result)
        mock_get_stock_reports.assert_any_call(
            "688981.SH",
            "2026-01-15",
            "2026-05-15",
            max_reports=5,
        )

    @patch("etfagents.agents.utils.etf_data_tools.get_broker_reports")
    @patch("etfagents.agents.utils.etf_data_tools.get_stock_reports")
    @patch("etfagents.agents.utils.etf_data_tools._lookup_akshare_hk_industry", return_value="")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_top_holdings_explains_dual_listed_stock_report_failover(
        self,
        mock_query,
        _mock_lookup_akshare_hk_industry,
        mock_get_stock_reports,
        mock_get_broker_reports,
    ):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query
        mock_get_stock_reports.side_effect = DataVendorUnavailable("No stock research reports found")
        mock_get_broker_reports.return_value = "# Industry Research Reports for 半导体"

        result = get_etf_top_holdings_research.invoke(
            {"ticker": "513130.SH", "curr_date": "2026-05-15", "top_n": 8}
        )

        self.assertIn(
            "[A+H dual-listed, but A-share stock research was unavailable; "
            "falling back to theme-related industry reports, not constituent-level coverage. "
            "Reason: No stock research reports found]",
            result,
        )
        mock_get_broker_reports.assert_any_call(
            "688981.SH",
            "2026-01-15",
            "2026-05-15",
            max_reports=5,
            extra_ind_names=["半导体", "电子"],
            _skip_industry_resolution=True,
        )

    @patch("etfagents.agents.utils.etf_data_tools.get_broker_reports")
    @patch("etfagents.agents.utils.etf_data_tools._lookup_akshare_hk_industry", return_value="")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_top_holdings_uses_industry_fallback_once_per_industry(
        self,
        mock_query,
        _mock_lookup_akshare_hk_industry,
        mock_get_broker_reports,
    ):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query
        mock_get_broker_reports.return_value = "# Industry Research Reports for 互联网"

        # The 恒生科技 proxy basket intentionally starts with Tencent and Alibaba,
        # both in 互联网平台, so top_n=2 exercises per-industry fallback de-duplication.
        result = get_etf_top_holdings_research.invoke(
            {"ticker": "513130.SH", "curr_date": "2026-05-15", "top_n": 2}
        )

        self.assertIn("Theme-related industry reports reused from Holding 1", result)
        self.assertEqual(mock_get_broker_reports.call_count, 1)
        call_kwargs = mock_get_broker_reports.call_args.kwargs
        self.assertTrue(call_kwargs["_skip_market_check"])
        self.assertTrue(call_kwargs["_skip_industry_resolution"])
        self.assertEqual(call_kwargs["extra_ind_names"], ["互联网", "传媒"])

    @patch("etfagents.agents.utils.etf_data_tools.get_broker_reports")
    @patch("etfagents.agents.utils.etf_data_tools._lookup_akshare_hk_industry", return_value="")
    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_industry_research_prefers_a_share_representative(
        self,
        mock_query,
        _mock_lookup_akshare_hk_industry,
        mock_get_broker_reports,
    ):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513900.SH",
                            "name": "恒生中国企业ETF",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生中国企业指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query
        mock_get_broker_reports.return_value = "# Industry Research Reports"

        result = get_etf_industry_research.invoke(
            {"ticker": "513900.SH", "curr_date": "2026-05-15", "top_n": 6}
        )

        self.assertIn("00939.HK -> 601939.SH", result)
        called_tickers = [call.args[0] for call in mock_get_broker_reports.call_args_list]
        self.assertIn("601939.SH", called_tickers)
        ccb_call = next(call for call in mock_get_broker_reports.call_args_list if call.args[0] == "601939.SH")
        self.assertTrue(ccb_call.kwargs["_skip_industry_resolution"])
        self.assertNotIn("_skip_market_check", ccb_call.kwargs)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_uses_fallback_metadata_when_hk_basic_is_empty(self, mock_query):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame()
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        _, latest_date, frame = _build_constituent_frame("513130.SH", "2026-05-15", 2)

        self.assertEqual(latest_date, "20260515")
        self.assertEqual(frame.iloc[0]["name"], "腾讯控股")
        self.assertEqual(frame.iloc[0]["industry"], "互联网平台")
        self.assertAlmostEqual(frame.iloc[0]["weight"], 15.87, places=2)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    @patch("etfagents.agents.utils.etf_data_tools.route_to_vendor")
    def test_get_etf_holdings_keeps_hk_proxy_when_hk_daily_fails(
        self,
        mock_route,
        mock_query,
    ):
        mock_route.side_effect = MissingEtfHoldings(
            "No ETF holdings data found for '513130.SH' up to 2026-05-15."
        )

        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513130.SH",
                            "name": "恒生科技ETF华泰柏瑞",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生科技指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                raise DataVendorUnavailable("502")
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        _, latest_date, frame = _build_constituent_frame("513130.SH", "2026-05-15", 2)
        result = get_etf_holdings.invoke(
            {"ticker": "513130.SH", "curr_date": "2026-05-15"}
        )

        self.assertEqual(latest_date, "20260515")
        self.assertFalse(frame.empty)
        self.assertIn("00700.HK", result)
        self.assertNotIn("latest_hk_close", result)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_hk_proxy_prefers_broad_hong_kong_basket_without_tech_keyword(self, mock_query):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame()
            if api_name == "fund_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "513900.SH",
                            "name": "恒生中国企业ETF",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "QDII",
                            "benchmark": "恒生中国企业指数",
                        }
                    ]
                )
            if api_name == "hk_basic":
                return pd.DataFrame([{"ts_code": params["ts_code"], "name": params["ts_code"]}])
            if api_name == "hk_daily":
                return pd.DataFrame([{"trade_date": "20260515", "close": 100.0, "pct_chg": 0.5}])
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        _, _, frame = _build_constituent_frame("513900.SH", "2026-05-15", 3)

        self.assertEqual(frame.attrs["proxy_label"], "港股宽基")
        self.assertIn("00005.HK", set(frame["ts_code"]))

    @patch("etfagents.dataflows.tushare._query_pro")
    def test_etf_universe_includes_enriched_factor_columns(self, mock_query):
        def _fake_query(api_name, **params):
            ts_code = params.get("ts_code")
            if api_name == "fund_basic":
                if ts_code:
                    return pd.DataFrame(
                        [
                            {
                                "ts_code": ts_code,
                                "name": "沪深300ETF",
                                "market": "SH",
                                "fund_type": "ETF",
                                "invest_type": "被动指数型",
                                "benchmark": "沪深300指数",
                                "list_date": "20200101",
                                "management": "Test AM",
                            }
                        ]
                    )
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "510300.SH",
                            "name": "沪深300ETF",
                            "market": "SH",
                            "fund_type": "ETF",
                            "invest_type": "被动指数型",
                            "benchmark": "沪深300指数",
                            "list_date": "20200101",
                            "management": "Test AM",
                        }
                    ]
                )
            if api_name == "fund_daily":
                return pd.DataFrame(
                    [
                        {"trade_date": "20260115", "close": 4.20, "amount": 1500000, "vol": 320000},
                        {"trade_date": "20260114", "close": 4.15, "amount": 1300000, "vol": 300000},
                        {"trade_date": "20260113", "close": 4.10, "amount": 1100000, "vol": 280000},
                    ]
                )
            if api_name == "fund_nav":
                return pd.DataFrame(
                    [
                        {"end_date": "20260115", "nav_date": "20260115", "unit_nav": 4.18, "total_netasset": 12000000000},
                        {"end_date": "20260114", "nav_date": "20260114", "unit_nav": 4.14, "total_netasset": 11800000000},
                    ]
                )
            if api_name == "fund_share":
                return pd.DataFrame(
                    [
                        {"end_date": "20260115", "fd_share": 1050000000},
                        {"end_date": "20251231", "fd_share": 1000000000},
                    ]
                )
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        payload = get_etf_universe(curr_date="2026-01-15", market="SH", limit=1)

        self.assertIn("liquidity_score", payload)
        self.assertIn("premium_discount_bps", payload)
        self.assertIn("share_change_pct", payload)
        self.assertIn("aum_bucket", payload)
        self.assertIn("exposure_bucket", payload)
        self.assertIn("latest_trade_date", payload)
        self.assertIn("latest available daily close, not an intraday real-time quote", payload)
        self.assertIn("ok", payload)

    def test_candidate_pool_replay_builds_metrics_and_windows(self):
        graph = object.__new__(EtfAgentsGraph)

        def _fake_ranked(_tickers, trade_date):
            ranked_by_date = {
                "2026-01-02": [
                    {"ticker": "159915.SZ", "rating": "BUY", "suggested_weight_pct": 70.0},
                    {"ticker": "510300.SH", "rating": "HOLD", "suggested_weight_pct": 30.0},
                ],
                "2026-01-06": [
                    {"ticker": "510300.SH", "rating": "BUY", "suggested_weight_pct": 60.0},
                    {"ticker": "159915.SZ", "rating": "OVERWEIGHT", "suggested_weight_pct": 40.0},
                ],
            }
            return ranked_by_date[trade_date]

        def _fake_prices(ticker, _start_date, _end_date):
            frames = {
                "159915.SZ": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Close": [100.0, 110.0, 111.0],
                    }
                ),
                "510300.SH": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Close": [100.0, 101.0, 106.0],
                    }
                ),
            }
            return frames[ticker]

        graph.analyze_candidate_pool = _fake_ranked

        result = EtfAgentsGraph.replay_candidate_pool(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            price_loader=_fake_prices,
        )

        self.assertEqual(result.metrics.periods, 2)
        self.assertEqual(
            [window.selected_tickers for window in result.windows],
            [["159915.SZ"], ["510300.SH"]],
        )
        self.assertAlmostEqual(result.windows[0].period_return, 0.1, places=6)
        self.assertAlmostEqual(result.windows[1].period_return, 0.049505, places=6)
        self.assertAlmostEqual(result.metrics.cumulative_return, 0.154455, places=6)
        self.assertAlmostEqual(result.metrics.average_turnover, 1.0, places=6)
        self.assertEqual(result.execution_timing, "same_close")
        self.assertEqual(result.to_dict()["top_k"], 1)

    def test_candidate_pool_replay_supports_next_open_execution(self):
        graph = object.__new__(EtfAgentsGraph)

        def _fake_ranked(_tickers, trade_date):
            ranked_by_date = {
                "2026-01-02": [
                    {"ticker": "159915.SZ", "rating": "BUY", "suggested_weight_pct": 70.0},
                    {"ticker": "510300.SH", "rating": "HOLD", "suggested_weight_pct": 30.0},
                ],
                "2026-01-06": [
                    {"ticker": "510300.SH", "rating": "BUY", "suggested_weight_pct": 60.0},
                    {"ticker": "159915.SZ", "rating": "OVERWEIGHT", "suggested_weight_pct": 40.0},
                ],
            }
            return ranked_by_date[trade_date]

        def _fake_prices(ticker, _start_date, _end_date):
            frames = {
                "159915.SZ": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08", "2026-01-10"]),
                        "Open": [100.0, 101.0, 111.0, 112.0],
                        "Close": [100.0, 110.0, 111.0, 112.0],
                    }
                ),
                "510300.SH": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08", "2026-01-10"]),
                        "Open": [100.0, 101.0, 102.0, 107.0],
                        "Close": [100.0, 101.0, 106.0, 107.0],
                    }
                ),
            }
            return frames[ticker]

        graph.analyze_candidate_pool = _fake_ranked

        result = EtfAgentsGraph.replay_candidate_pool(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            execution_timing="next_open",
            price_loader=_fake_prices,
        )

        self.assertEqual(result.execution_timing, "next_open")
        self.assertAlmostEqual(result.windows[0].period_return, 0.09901, places=6)
        self.assertAlmostEqual(result.windows[1].period_return, 0.04902, places=6)
        self.assertAlmostEqual(result.metrics.cumulative_return, 0.152883, places=6)

    def test_candidate_pool_uses_cached_backtest_result_within_backtest_context(self):
        graph = object.__new__(EtfAgentsGraph)
        graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        graph.selected_analysts = ["market_flow", "macro_regime"]
        with TemporaryDirectory() as tmpdir:
            graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            graph.config["results_dir"] = tmpdir
            call_count = {"propagate": 0}

            def _fake_propagate(ticker, _trade_date):
                call_count["propagate"] += 1
                return (
                    {
                        "market_flow_report": f"market-flow-{ticker}",
                        "macro_regime_report": f"macro-{ticker}",
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                        "backtest_signal": {
                            "ticker": ticker,
                            "decision_date": "2026-01-15",
                            "rating": "BUY",
                            "source": "portfolio_manager",
                            "source_section": "positioning_recommendation",
                            "target_weight_pct": 25.0,
                            "target_weight_min_pct": 25.0,
                            "target_weight_max_pct": 25.0,
                            "weight_source": "rating_map",
                            "execution_delay": "next_open",
                            "starter_size_text": "",
                            "add_conditions": [],
                            "reduce_conditions": [],
                            "exit_conditions": [],
                            "rebalance_conditions": [],
                            "risk_controls": [],
                            "monitoring_points": [],
                            "signal_text_snapshot": f"decision-{ticker}",
                        },
                    },
                    "BUY",
                )

            graph.propagate = _fake_propagate

            with backtest_context("2026-01-15"):
                first = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")
                second = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")

        self.assertEqual(call_count["propagate"], 1)
        self.assertEqual(first[0]["ticker"], second[0]["ticker"])
        self.assertEqual(first[0]["rating"], second[0]["rating"])

    def test_candidate_pool_force_refresh_bypasses_cache(self):
        graph = object.__new__(EtfAgentsGraph)
        graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        graph.selected_analysts = ["market_flow", "macro_regime"]
        with TemporaryDirectory() as tmpdir:
            graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            graph.config["results_dir"] = tmpdir
            call_count = {"propagate": 0}

            def _fake_propagate(ticker, _trade_date):
                call_count["propagate"] += 1
                return (
                    {
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                        "backtest_signal": {
                            "ticker": ticker,
                            "decision_date": "2026-01-15",
                            "rating": "BUY",
                            "source": "portfolio_manager",
                            "source_section": "positioning_recommendation",
                            "target_weight_pct": 25.0,
                            "target_weight_min_pct": 25.0,
                            "target_weight_max_pct": 25.0,
                            "weight_source": "structured_field",
                            "execution_delay": "next_open",
                            "starter_size_text": "",
                            "add_conditions": [],
                            "reduce_conditions": [],
                            "exit_conditions": [],
                            "rebalance_conditions": [],
                            "risk_controls": [],
                            "monitoring_points": [],
                            "signal_text_snapshot": f"decision-{ticker}",
                        },
                    },
                    "BUY",
                )

            graph.propagate = _fake_propagate

            with backtest_context("2026-01-15"):
                EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")
                EtfAgentsGraph.analyze_candidate_pool(
                    graph,
                    ["510300.SH"],
                    "2026-01-15",
                    force_refresh=True,
                )

        self.assertEqual(call_count["propagate"], 2)

    def test_candidate_pool_cache_sanitizes_report_preambles_before_persisting(self):
        graph = object.__new__(EtfAgentsGraph)
        graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        graph.selected_analysts = ["market_flow"]
        with TemporaryDirectory() as tmpdir:
            graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            graph.config["results_dir"] = tmpdir

            def _fake_propagate(ticker, _trade_date):
                return (
                    {
                        "market_flow_report": "市场分析正文",
                        "research_allocation_plan": "数据已获取完毕，以下为研究团队配置观点。\n\n研究观点正文",
                        "trader_allocation_plan": "报告已就绪。以下为交易员配置计划。\n\n交易计划正文",
                        "final_allocation_decision": "数据已获取完毕，以下为投资组合配置决策。\n\n最终配置建议：买入",
                        "backtest_signal": {
                            "ticker": ticker,
                            "decision_date": "2026-01-15",
                            "rating": "BUY",
                            "source": "portfolio_manager",
                            "source_section": "positioning_recommendation",
                            "target_weight_pct": 25.0,
                            "target_weight_min_pct": 25.0,
                            "target_weight_max_pct": 25.0,
                            "weight_source": "structured_field",
                            "execution_delay": "next_open",
                            "starter_size_text": "",
                            "add_conditions": [],
                            "reduce_conditions": [],
                            "exit_conditions": [],
                            "rebalance_conditions": [],
                            "risk_controls": [],
                            "monitoring_points": [],
                            "signal_text_snapshot": "数据已获取完毕，以下为投资组合配置决策。\n\n最终配置建议：买入",
                        },
                    },
                    "BUY",
                )

            graph.propagate = _fake_propagate

            with backtest_context("2026-01-15"):
                ranked = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")

            cache_files = list(Path(tmpdir).rglob("2026-01-15.json"))
            self.assertEqual(1, len(cache_files))
            cached = json.loads(cache_files[0].read_text())
            self.assertEqual("研究观点正文", cached["research_allocation_plan"])
            self.assertEqual("交易计划正文", cached["trader_allocation_plan"])
            self.assertEqual("最终配置建议：买入", cached["final_allocation_decision"])
            self.assertEqual("最终配置建议：买入", cached["backtest_signal"]["signal_text_snapshot"])
            self.assertEqual("研究观点正文", ranked[0]["research_allocation_plan"])

    def test_candidate_payload_text_keeps_legitimate_short_overview(self):
        text = "本ETF分析显示趋势同步向上，资金确认偏多，建议保持配置。\n\n一、市场结构与量价诊断\n趋势延续。"
        self.assertEqual(text, _sanitize_candidate_payload_text(text))

    def test_candidate_payload_text_strips_process_opening_before_partial_preamble_match(self):
        text = "数据已获取完毕，以下为研究团队配置观点。\n\n研究观点正文"

        self.assertEqual("研究观点正文", _sanitize_candidate_payload_text(text))

    def test_candidate_payload_text_uses_shared_process_narration_detection(self):
        text = "资料已经齐备，下面给出宏观框架判断。\n\n宏观观点正文"

        self.assertEqual("宏观观点正文", _sanitize_candidate_payload_text(text))

    def test_candidate_pool_cache_hits_are_sanitized_before_returning(self):
        graph = object.__new__(EtfAgentsGraph)
        graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        graph.selected_analysts = ["market_flow"]
        with TemporaryDirectory() as tmpdir:
            graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            graph.config["results_dir"] = tmpdir
            cache = BacktestSignalStore(
                graph.config,
                graph.selected_analysts,
                force_refresh=False,
            )
            raw_payload = {
                "ticker": "510300.SH",
                "rating": "BUY",
                "score": "5",
                "market_flow_report": "市场分析正文",
                "research_allocation_plan": "数据已获取完毕，以下为研究团队配置观点。\n\n研究观点正文",
                "trader_allocation_plan": "报告已就绪。以下为交易员配置计划。\n\n交易计划正文",
                "final_allocation_decision": "数据已获取完毕，以下为投资组合配置决策。\n\n最终配置建议：买入",
                "backtest_signal": {
                    "ticker": "510300.SH",
                    "decision_date": "2026-01-15",
                    "rating": "BUY",
                    "source": "portfolio_manager",
                    "source_section": "positioning_recommendation",
                    "target_weight_pct": 25.0,
                    "target_weight_min_pct": 25.0,
                    "target_weight_max_pct": 25.0,
                    "weight_source": "structured_field",
                    "execution_delay": "next_open",
                    "starter_size_text": "",
                    "add_conditions": [],
                    "reduce_conditions": [],
                    "exit_conditions": [],
                    "rebalance_conditions": [],
                    "risk_controls": [],
                    "monitoring_points": [],
                    "signal_text_snapshot": "数据已获取完毕，以下为投资组合配置决策。\n\n最终配置建议：买入",
                },
            }
            graph.propagate = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("cache should be used")
            )

            with backtest_context("2026-01-15"):
                cache.put("510300.SH", "2026-01-15", raw_payload)
                ranked = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")

        self.assertEqual("研究观点正文", ranked[0]["research_allocation_plan"])
        self.assertEqual("交易计划正文", ranked[0]["trader_allocation_plan"])
        self.assertEqual("最终配置建议：买入", ranked[0]["final_allocation_decision"])
        self.assertEqual("最终配置建议：买入", ranked[0]["backtest_signal"]["signal_text_snapshot"])

    def test_candidate_pool_recomputes_when_selected_analyst_report_was_cached_empty(self):
        graph = object.__new__(EtfAgentsGraph)
        graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        graph.selected_analysts = ["market_flow"]
        with TemporaryDirectory() as tmpdir:
            graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            graph.config["results_dir"] = tmpdir
            call_count = {"propagate": 0}

            def _fake_propagate(ticker, _trade_date):
                call_count["propagate"] += 1
                report = "" if call_count["propagate"] == 1 else f"market-flow-{ticker}"
                return (
                    {
                        "market_flow_report": report,
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                    },
                    "BUY",
                )

            graph.propagate = _fake_propagate

            with backtest_context("2026-01-15"):
                first = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")
                cache_files = list(Path(tmpdir).rglob("2026-01-15.json"))
                self.assertEqual(1, len(cache_files))
                first_cached = json.loads(cache_files[0].read_text())
                second = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")
                second_cached = json.loads(cache_files[0].read_text())

        self.assertEqual(call_count["propagate"], 2)
        self.assertEqual("", first[0]["market_flow_report"])
        self.assertEqual("market-flow-510300.SH", second[0]["market_flow_report"])
        self.assertNotIn("market_flow_report", first_cached)
        self.assertEqual("market-flow-510300.SH", second_cached["market_flow_report"])

    def test_candidate_pool_uses_cache_when_unselected_analyst_report_is_missing(self):
        graph = object.__new__(EtfAgentsGraph)
        graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        graph.selected_analysts = ["macro_regime"]
        with TemporaryDirectory() as tmpdir:
            graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            graph.config["results_dir"] = tmpdir
            call_count = {"propagate": 0}

            def _fake_propagate(ticker, _trade_date):
                call_count["propagate"] += 1
                return (
                    {
                        "macro_regime_report": f"macro-{ticker}",
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                    },
                    "BUY",
                )

            graph.propagate = _fake_propagate

            with backtest_context("2026-01-15"):
                first = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")
                second = EtfAgentsGraph.analyze_candidate_pool(graph, ["510300.SH"], "2026-01-15")

        self.assertEqual(call_count["propagate"], 1)
        self.assertEqual("macro-510300.SH", first[0]["macro_regime_report"])
        self.assertEqual("macro-510300.SH", second[0]["macro_regime_report"])

    def test_candidate_pool_cache_misses_when_config_changes(self):
        first_graph = object.__new__(EtfAgentsGraph)
        second_graph = object.__new__(EtfAgentsGraph)
        first_graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        second_graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        first_graph.selected_analysts = ["market_flow"]
        second_graph.selected_analysts = ["market_flow", "macro_regime"]
        with TemporaryDirectory() as tmpdir:
            first_graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            first_graph.config["results_dir"] = tmpdir
            second_graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            second_graph.config["results_dir"] = tmpdir
            first_calls = {"propagate": 0}
            second_calls = {"propagate": 0}

            def _first_propagate(ticker, _trade_date):
                first_calls["propagate"] += 1
                return (
                    {
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                    },
                    "BUY",
                )

            def _second_propagate(ticker, _trade_date):
                second_calls["propagate"] += 1
                return (
                    {
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                    },
                    "BUY",
                )

            first_graph.propagate = _first_propagate
            second_graph.propagate = _second_propagate

            with backtest_context("2026-01-15"):
                EtfAgentsGraph.analyze_candidate_pool(first_graph, ["510300.SH"], "2026-01-15")
                EtfAgentsGraph.analyze_candidate_pool(second_graph, ["510300.SH"], "2026-01-15")

        self.assertEqual(first_calls["propagate"], 1)
        self.assertEqual(second_calls["propagate"], 1)

    def test_candidate_pool_cache_misses_when_memory_signature_changes(self):
        first_graph = object.__new__(EtfAgentsGraph)
        second_graph = object.__new__(EtfAgentsGraph)
        first_graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        second_graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
        first_graph.selected_analysts = ["market_flow"]
        second_graph.selected_analysts = ["market_flow"]
        first_graph.analysis_memory_store = type("Store", (), {"memory_signature": lambda *_args: "mem-a"})()
        second_graph.analysis_memory_store = type("Store", (), {"memory_signature": lambda *_args: "mem-b"})()
        with TemporaryDirectory() as tmpdir:
            first_graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            first_graph.config["results_dir"] = tmpdir
            first_graph.config["memory_in_backtest"] = True
            second_graph.config = copy.deepcopy(ETF_DEFAULT_CONFIG)
            second_graph.config["results_dir"] = tmpdir
            second_graph.config["memory_in_backtest"] = True
            first_calls = {"propagate": 0}
            second_calls = {"propagate": 0}

            def _first_propagate(ticker, _trade_date):
                first_calls["propagate"] += 1
                return (
                    {
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                    },
                    "BUY",
                )

            def _second_propagate(ticker, _trade_date):
                second_calls["propagate"] += 1
                return (
                    {
                        "research_allocation_plan": f"research-{ticker}",
                        "trader_allocation_plan": f"trader-{ticker}",
                        "final_allocation_decision": f"decision-{ticker}",
                    },
                    "BUY",
                )

            first_graph.propagate = _first_propagate
            second_graph.propagate = _second_propagate

            with backtest_context("2026-01-15"):
                EtfAgentsGraph.analyze_candidate_pool(first_graph, ["510300.SH"], "2026-01-15")
                EtfAgentsGraph.analyze_candidate_pool(second_graph, ["510300.SH"], "2026-01-15")

        self.assertEqual(first_calls["propagate"], 1)
        self.assertEqual(second_calls["propagate"], 1)

if __name__ == "__main__":
    unittest.main()
