
import importlib.util
import unittest
if not importlib.util.find_spec("pandas"):
    raise unittest.SkipTest("pandas not installed")

import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from etfagents.agents.utils import etf_data_tools
from etfagents.agents.utils.etf_data_tools import (
    _build_commodity_snapshot,
    _build_macro_snapshot,
    _load_tushare_futures_main_frame,
    _load_tushare_warehouse_series,
    _load_fred_series,
)

def _series(points):
    index = pd.to_datetime([date for date, _ in points])
    values = [value for _, value in points]
    return pd.Series(values, index=index, dtype=float)

class MacroDataToolsTests(unittest.TestCase):
    def setUp(self):
        etf_data_tools._load_tushare_futures_contract_catalog.cache_clear()
        etf_data_tools._load_tushare_futures_daily_exchange_frame.cache_clear()
        etf_data_tools._load_tushare_futures_main_frame.cache_clear()
        etf_data_tools._load_tushare_warehouse_exchange_frame.cache_clear()
        etf_data_tools._load_tushare_warehouse_series.cache_clear()

    @patch.dict(os.environ, {"FRED_API_KEY": "test-key"}, clear=False)
    @patch("etfagents.agents.utils.etf_data_tools.requests.get")
    def test_load_fred_series_parses_official_api_observations(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "observations": [
                {"date": "2026-01-01", "value": "4.50"},
                {"date": "2026-01-31", "value": "4.60"},
                {"date": "2026-02-01", "value": "."},
            ]
        }
        mock_get.return_value = response

        series = _load_fred_series("FEDFUNDS", "2026-02-01", 60)

        self.assertEqual([round(value, 2) for value in series.tolist()], [4.50, 4.60])
        self.assertEqual(mock_get.call_args.kwargs["params"]["series_id"], "FEDFUNDS")
        self.assertEqual(mock_get.call_args.kwargs["params"]["file_type"], "json")

    @patch("etfagents.agents.utils.etf_data_tools._load_yfinance_close")
    @patch("etfagents.agents.utils.etf_data_tools._load_china_ten_year_yield_series")
    @patch("etfagents.agents.utils.etf_data_tools._load_china_policy_rate_series")
    @patch("etfagents.agents.utils.etf_data_tools._load_fred_series")
    def test_macro_snapshot_uses_tushare_for_china_and_fred_for_overseas_rates(
        self,
        mock_load_fred_series,
        mock_load_china_policy_rate_series,
        mock_load_china_ten_year_yield_series,
        mock_load_yfinance_close,
    ):
        fred_series_map = {
            "FEDFUNDS": _series([("2026-01-01", 4.40), ("2026-01-31", 4.50)]),
            "DGS10": _series([("2026-01-01", 4.20), ("2026-01-31", 4.30)]),
            "ECBDFR": _series([("2026-01-01", 3.00), ("2026-01-31", 3.10)]),
            "IRLTLT01DEM156N": _series([("2026-01-01", 2.40), ("2026-01-31", 2.50)]),
            "IR3TIB01JPM156N": _series([("2026-01-01", 0.20), ("2026-01-31", 0.30)]),
            "IRLTLT01JPM156N": _series([("2026-01-01", 1.20), ("2026-01-31", 1.30)]),
            "DFII10": _series([("2026-01-01", 1.00), ("2026-01-31", 1.10)]),
            "BAMLH0A3HYC": _series([("2026-01-01", 320.0), ("2026-01-31", 340.0)]),
        }

        def _fred_side_effect(series_id, curr_date, look_back_days=540):
            return fred_series_map[series_id]

        mock_load_fred_series.side_effect = _fred_side_effect
        mock_load_china_policy_rate_series.return_value = _series([("2026-01-01", 3.00), ("2026-01-31", 3.10)])
        mock_load_china_ten_year_yield_series.return_value = _series([("2026-01-01", 2.20), ("2026-01-31", 2.30)])
        mock_load_yfinance_close.return_value = _series([("2025-11-01", 100.0), ("2026-01-01", 105.0), ("2026-01-31", 110.0)])

        snapshot = _build_macro_snapshot("2026-01-31", 120)

        self.assertIn("China | 3.10% | 0.10ppt | 2.30% | 0.10ppt |", snapshot)
        self.assertIn("US - China short-rate spread | 1.40ppt", snapshot)
        self.assertIn("Data sources: overseas policy/benchmark rates and sovereign yields are pulled from FRED; China short-rate and 10Y government-bond data are pulled from Tushare", snapshot)
        requested_series = [call.args[0] for call in mock_load_fred_series.call_args_list]
        self.assertNotIn("IR3TIB01CNM156N", requested_series)
        self.assertNotIn("IRLTLT01CNM156N", requested_series)

    @patch("etfagents.agents.utils.etf_data_tools._load_cn_schedule_frame")
    @patch("etfagents.agents.utils.etf_data_tools._load_yfinance_close")
    @patch("etfagents.agents.utils.etf_data_tools._load_china_ten_year_yield_series")
    @patch("etfagents.agents.utils.etf_data_tools._load_china_policy_rate_series")
    @patch("etfagents.agents.utils.etf_data_tools._load_fred_series")
    def test_macro_snapshot_includes_cn_schedule_calendar(
        self,
        mock_load_fred_series,
        mock_load_china_policy_rate_series,
        mock_load_china_ten_year_yield_series,
        mock_load_yfinance_close,
        mock_load_cn_schedule_frame,
    ):
        fred_series_map = {
            "FEDFUNDS": _series([("2026-03-01", 4.40), ("2026-04-30", 4.50)]),
            "DGS10": _series([("2026-03-01", 4.20), ("2026-04-30", 4.30)]),
            "ECBDFR": _series([("2026-03-01", 3.00), ("2026-04-30", 3.10)]),
            "IRLTLT01DEM156N": _series([("2026-03-01", 2.40), ("2026-04-30", 2.50)]),
            "IR3TIB01JPM156N": _series([("2026-03-01", 0.20), ("2026-04-30", 0.30)]),
            "IRLTLT01JPM156N": _series([("2026-03-01", 1.20), ("2026-04-30", 1.30)]),
            "DFII10": _series([("2026-03-01", 1.00), ("2026-04-30", 1.10)]),
            "BAMLH0A3HYC": _series([("2026-03-01", 320.0), ("2026-04-30", 340.0)]),
        }

        mock_load_fred_series.side_effect = lambda series_id, *_args, **_kwargs: fred_series_map[series_id]
        mock_load_china_policy_rate_series.return_value = _series([("2026-03-01", 3.00), ("2026-04-30", 3.10)])
        mock_load_china_ten_year_yield_series.return_value = _series([("2026-03-01", 2.20), ("2026-04-30", 2.30)])
        mock_load_yfinance_close.return_value = _series([("2026-02-01", 100.0), ("2026-03-31", 105.0), ("2026-04-30", 110.0)])
        mock_load_cn_schedule_frame.return_value = pd.DataFrame(
            {
                "publish_date": pd.to_datetime(["2026-05-10", "2026-05-16"]),
                "title": ["居民消费价格指数月度报告", "固定资产投资月度报告"],
                "issuing_org": ["国家统计局", "国家统计局"],
                "data_api": ["cn_cpi", "待上线"],
            }
        )

        snapshot = _build_macro_snapshot("2026-04-30", 120)

        self.assertIn("China macro release calendar (eco-calendar) around the next rebalance window", snapshot)
        self.assertIn("居民消费价格指数月度报告", snapshot)
        self.assertIn("cn_schedule", snapshot)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_tushare_futures_main_frame_returns_empty_when_trade_date_missing(self, mock_query_pro):
        def _query(api_name, **kwargs):
            if api_name == "fut_basic":
                return pd.DataFrame(
                    {"ts_code": ["AU2406.SHF"], "list_date": ["20240101"], "delist_date": ["20240630"]}
                )
            if api_name == "fut_daily":
                return pd.DataFrame({"close": [1.0], "oi": [2.0], "vol": [3.0]})
            raise AssertionError(f"Unexpected API call: {api_name}")

        mock_query_pro.side_effect = _query

        frame = _load_tushare_futures_main_frame.__wrapped__("AU", "SHFE", "2026-04-30", 120)

        self.assertTrue(frame.empty)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_tushare_futures_main_frame_keeps_trade_date_after_main_contract_selection(self, mock_query_pro):
        mock_query_pro.side_effect = [
            pd.DataFrame(
                {
                    "ts_code": ["AU2406.SHF", "AU2408.SHF"],
                    "fut_code": ["AU", "AU"],
                    "list_date": ["20240101", "20240101"],
                    "delist_date": ["20240630", "20240830"],
                }
            ),
            pd.DataFrame(
                {
                    "ts_code": ["AU2406.SHF", "AU2406.SHF", "AU2408.SHF", "AU2408.SHF"],
                    "trade_date": ["20240429", "20240430", "20240429", "20240430"],
                    "close": [100.0, 101.0, 102.0, 103.0],
                    "oi": [1000.0, 900.0, 1200.0, 1300.0],
                    "vol": [200.0, 150.0, 250.0, 260.0],
                }
            ),
        ]

        frame = _load_tushare_futures_main_frame.__wrapped__("AU", "SHFE", "2024-04-30", 120)

        self.assertEqual(list(frame["trade_date"].dt.strftime("%Y%m%d")), ["20240429", "20240430"])
        self.assertEqual(list(frame["ts_code"]), ["AU2408.SHF", "AU2408.SHF"])

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_tushare_futures_main_frame_reuses_exchange_level_batches(self, mock_query_pro):
        mock_query_pro.side_effect = [
            pd.DataFrame(
                {
                    "ts_code": ["AU2406.SHF", "CU2406.SHF"],
                    "fut_code": ["AU", "CU"],
                    "list_date": ["20240101", "20240101"],
                    "delist_date": ["20240630", "20240630"],
                }
            ),
            pd.DataFrame(
                {
                    "ts_code": ["AU2406.SHF", "CU2406.SHF"],
                    "trade_date": ["20240430", "20240430"],
                    "close": [101.0, 70100.0],
                    "oi": [900.0, 1200.0],
                    "vol": [150.0, 260.0],
                }
            ),
        ]

        au_frame = _load_tushare_futures_main_frame.__wrapped__("AU", "SHFE", "2024-04-30", 120)
        cu_frame = _load_tushare_futures_main_frame.__wrapped__("CU", "SHFE", "2024-04-30", 120)

        self.assertEqual(list(au_frame["ts_code"]), ["AU2406.SHF"])
        self.assertEqual(list(cu_frame["ts_code"]), ["CU2406.SHF"])
        self.assertEqual(mock_query_pro.call_count, 2)
        self.assertEqual(mock_query_pro.call_args_list[0].kwargs["exchange"], "SHFE")
        self.assertNotIn("fut_code", mock_query_pro.call_args_list[0].kwargs)
        self.assertEqual(mock_query_pro.call_args_list[1].args[0], "fut_daily")
        self.assertEqual(mock_query_pro.call_args_list[1].kwargs["exchange"], "SHFE")

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_tushare_futures_main_frame_fills_missing_contracts_from_partial_batch(self, mock_query_pro):
        def _query(api_name, **kwargs):
            if api_name == "fut_basic":
                return pd.DataFrame(
                    {
                        "ts_code": ["AU2406.SHF", "AU2408.SHF"],
                        "fut_code": ["AU", "AU"],
                        "list_date": ["20240101", "20240101"],
                        "delist_date": ["20240630", "20240830"],
                    }
                )
            if api_name == "fut_daily" and "exchange" in kwargs:
                return pd.DataFrame(
                    {
                        "ts_code": ["AU2406.SHF"],
                        "trade_date": ["20240430"],
                        "close": [101.0],
                        "oi": [900.0],
                        "vol": [150.0],
                    }
                )
            if api_name == "fut_daily" and kwargs.get("ts_code") == "AU2408.SHF":
                return pd.DataFrame(
                    {
                        "ts_code": ["AU2408.SHF"],
                        "trade_date": ["20240430"],
                        "close": [103.0],
                        "oi": [1300.0],
                        "vol": [260.0],
                    }
                )
            raise AssertionError(f"Unexpected API call: {api_name} {kwargs}")

        mock_query_pro.side_effect = _query

        frame = _load_tushare_futures_main_frame.__wrapped__("AU", "SHFE", "2024-04-30", 120)

        self.assertEqual(list(frame["ts_code"]), ["AU2408.SHF"])
        self.assertEqual(mock_query_pro.call_count, 3)
        self.assertEqual(mock_query_pro.call_args_list[-1].kwargs["ts_code"], "AU2408.SHF")

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_tushare_warehouse_series_returns_empty_when_trade_date_missing(self, mock_query_pro):
        mock_query_pro.return_value = pd.DataFrame({"symbol": ["AU"], "vol": [10.0]})

        series = _load_tushare_warehouse_series.__wrapped__("AU", "SHFE", "2026-04-30", 120)

        self.assertTrue(series.empty)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_tushare_warehouse_series_reuses_exchange_level_batches(self, mock_query_pro):
        mock_query_pro.return_value = pd.DataFrame(
            {
                "symbol": ["AU", "CU"],
                "trade_date": ["20240430", "20240430"],
                "vol": [10.0, 30.0],
            }
        )

        au_series = _load_tushare_warehouse_series.__wrapped__("AU", "SHFE", "2024-04-30", 120)
        cu_series = _load_tushare_warehouse_series.__wrapped__("CU", "SHFE", "2024-04-30", 120)

        self.assertEqual(list(au_series), [10.0])
        self.assertEqual(list(cu_series), [30.0])
        self.assertEqual(mock_query_pro.call_count, 1)
        self.assertEqual(mock_query_pro.call_args.kwargs["exchange"], "SHFE")
        self.assertNotIn("symbol", mock_query_pro.call_args.kwargs)

    @patch("etfagents.agents.utils.etf_data_tools._query_pro")
    def test_tushare_warehouse_series_fills_partial_batch_date_coverage(self, mock_query_pro):
        def _query(api_name, **kwargs):
            if api_name == "fut_wsr" and "symbol" not in kwargs:
                return pd.DataFrame(
                    {
                        "symbol": ["AU", "CU"],
                        "trade_date": ["20240429", "20240430"],
                        "vol": [10.0, 30.0],
                    }
                )
            if api_name == "fut_wsr" and kwargs.get("symbol") == "AU":
                return pd.DataFrame(
                    {
                        "symbol": ["AU", "AU"],
                        "trade_date": ["20240429", "20240430"],
                        "vol": [10.0, 12.0],
                    }
                )
            raise AssertionError(f"Unexpected API call: {api_name} {kwargs}")

        mock_query_pro.side_effect = _query

        series = _load_tushare_warehouse_series.__wrapped__("AU", "SHFE", "2024-04-30", 120)

        self.assertEqual(list(series), [10.0, 12.0])
        self.assertEqual(mock_query_pro.call_count, 2)
        self.assertEqual(mock_query_pro.call_args_list[-1].kwargs["symbol"], "AU")

    @patch("etfagents.agents.utils.etf_data_tools._load_tushare_warehouse_series")
    @patch("etfagents.agents.utils.etf_data_tools._load_tushare_futures_main_frame")
    def test_commodity_snapshot_uses_tushare_contracts_and_anomaly_language(
        self,
        mock_load_tushare_futures_main_frame,
        mock_load_tushare_warehouse_series,
    ):
        def _futures_frame(symbol, _exchange, _curr_date, _look_back_days=240):
            price_map = {
                "AU": [100.0, 112.0, 118.0], "AG": [100.0, 105.0, 110.0],
                "CU": [100.0, 95.0, 92.0], "AL": [100.0, 98.0, 96.0],
                "PB": [100.0, 103.0, 106.0],
                "NI": [100.0, 110.0, 115.0], "ZN": [100.0, 97.0, 94.0],
                "SC": [100.0, 108.0, 106.0],
                "LC": [100.0, 125.0, 135.0],
                "RB": [100.0, 90.0, 82.0], "HC": [100.0, 92.0, 85.0],
                "I": [100.0, 95.0, 88.0], "JM": [100.0, 105.0, 102.0],
                "TA": [100.0, 104.0, 108.0], "MA": [100.0, 96.0, 93.0],
                "L": [100.0, 98.0, 95.0],
                "M": [100.0, 110.0, 118.0], "C": [100.0, 102.0, 105.0],
                "P": [100.0, 108.0, 115.0],
                "SP": [100.0, 104.0, 103.0], "RU": [100.0, 102.0, 105.0],
                "SI": [100.0, 90.0, 85.0], "UR": [100.0, 100.0, 98.0],
                "V": [100.0, 95.0, 93.0], "SA": [100.0, 110.0, 108.0],
            }
            oi_map = {
                "AU": [1000.0, 1250.0, 1350.0], "AG": [1000.0, 1100.0, 1200.0],
                "CU": [1000.0, 1200.0, 1400.0], "AL": [1000.0, 1050.0, 1100.0],
                "PB": [1000.0, 1080.0, 1150.0],
                "NI": [1000.0, 1150.0, 1250.0], "ZN": [1000.0, 1080.0, 1120.0],
                "SC": [1000.0, 980.0, 960.0],
                "LC": [1000.0, 1300.0, 1500.0],
                "RB": [1000.0, 1120.0, 1280.0], "HC": [1000.0, 1100.0, 1250.0],
                "I": [1000.0, 1100.0, 1200.0], "JM": [1000.0, 1050.0, 1080.0],
                "TA": [1000.0, 1080.0, 1150.0], "MA": [1000.0, 1020.0, 1050.0],
                "L": [1000.0, 1010.0, 1030.0],
                "M": [1000.0, 1200.0, 1350.0], "C": [1000.0, 1050.0, 1100.0],
                "P": [1000.0, 1100.0, 1200.0],
                "SP": [1000.0, 1005.0, 1010.0], "RU": [1000.0, 1020.0, 1050.0],
                "SI": [1000.0, 950.0, 900.0], "UR": [1000.0, 1000.0, 1020.0],
                "V": [1000.0, 980.0, 960.0], "SA": [1000.0, 1100.0, 1150.0],
            }
            if symbol not in price_map:
                raise KeyError(f"No mock data for {symbol}")
            return pd.DataFrame(
                {
                    "trade_date": pd.to_datetime(["2025-11-01", "2026-01-01", "2026-01-31"]),
                    "close": price_map[symbol],
                    "oi": oi_map[symbol],
                }
            )

        def _warehouse_series(symbol, _exchange, _curr_date, _look_back_days=240):
            warehouse_map = {
                "AU": [100.0, 85.0, 80.0], "AG": [100.0, 95.0, 90.0],
                "CU": [100.0, 130.0, 145.0], "AL": [100.0, 105.0, 110.0],
                "PB": [100.0, 102.0, 108.0],
                "NI": [100.0, 100.0, 105.0], "ZN": [100.0, 98.0, 102.0],
                "SC": [100.0, 100.0, 101.0],
                "LC": [100.0, 60.0, 55.0],
                "RB": [100.0, 140.0, 165.0], "HC": [100.0, 130.0, 150.0],
                "I": [100.0, 120.0, 130.0], "JM": [100.0, 105.0, 110.0],
                "TA": [100.0, 105.0, 110.0], "MA": [100.0, 108.0, 115.0],
                "L": [100.0, 100.0, 105.0],
                "M": [100.0, 95.0, 88.0], "C": [100.0, 110.0, 120.0],
                "P": [100.0, 90.0, 85.0],
                "SP": [100.0, 110.0, 115.0], "RU": [100.0, 100.0, 105.0],
                "SI": [100.0, 95.0, 90.0], "UR": [100.0, 100.0, 98.0],
                "V": [100.0, 100.0, 105.0], "SA": [100.0, 108.0, 112.0],
            }
            return _series(
                [
                    ("2025-11-01", warehouse_map[symbol][0]),
                    ("2026-01-01", warehouse_map[symbol][1]),
                    ("2026-01-31", warehouse_map[symbol][2]),
                ]
            )

        mock_load_tushare_futures_main_frame.side_effect = _futures_frame
        mock_load_tushare_warehouse_series.side_effect = _warehouse_series

        snapshot = _build_commodity_snapshot("2026-01-31", 120)

        self.assertIn("Data sources: Tushare futures daily data stitched across the most active contracts", snapshot)
        self.assertIn("沪金主力", snapshot)
        self.assertIn("碳酸锂主力", snapshot)
        self.assertIn("沪铝主力", snapshot)
        self.assertIn("PVC主力", snapshot)
        self.assertNotIn("Global lithium supply-chain ETF proxy", snapshot)
        self.assertNotIn("Steel producers ETF proxy", snapshot)
        self.assertIn("## Key anomalies", snapshot)
        self.assertIn("fresh long participation", snapshot)
        self.assertIn("warehouse receipts", snapshot)

if __name__ == "__main__":
    unittest.main()
