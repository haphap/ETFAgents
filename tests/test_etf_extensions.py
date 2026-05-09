import copy
import unittest
from unittest.mock import patch

import pandas as pd
from langgraph.prebuilt import ToolNode

from etfagents.agents.utils.etf_data_tools import get_etf_indicators, get_etf_industry_research
from etfagents.dataflows.config import get_config, set_config
from etfagents.dataflows.interface import TOOLS_CATEGORIES, VENDOR_METHODS, get_category_for_method
from etfagents.dataflows.tushare import get_etf_universe
from etfagents.graph.conditional_logic import ConditionalLogic
from etfagents.graph.etf_graph import ETF_DEFAULT_CONFIG, EtfAgentsGraph
from etfagents.graph.etf_setup import ETFGraphSetup


class ETFExtensionTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())

    def tearDown(self):
        set_config(self.original_config)

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
        self.assertEqual(ranked[0]["final_allocation_decision"], "decision-159915.SZ")
        self.assertEqual(
            [item["suggested_weight_pct"] for item in ranked],
            [50.0, 33.3, 16.7],
        )

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
        self.assertEqual(result.to_dict()["top_k"], 1)


if __name__ == "__main__":
    unittest.main()
