
import importlib.util
import unittest
if not importlib.util.find_spec("pandas"):
    raise unittest.SkipTest("pandas not installed")

import unittest
from unittest.mock import patch

import pandas as pd

import etfagents.dataflows.tushare as _tushare_mod
from etfagents.dataflows.tushare import get_etf_holdings

class TushareHoldingsNameTests(unittest.TestCase):
    def setUp(self):
        _tushare_mod._stock_basic_name_cache = None
    @patch("etfagents.dataflows.tushare._query_pro")
    def test_get_etf_holdings_enriches_missing_stock_names_from_stock_basic(self, mock_query):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "510300.SH",
                            "ann_date": "20260521",
                            "end_date": "20260520",
                            "symbol": "600519",
                            "stk_mkv_ratio": 5.23,
                        }
                    ]
                )
            if api_name == "stock_basic":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "600519.SH",
                            "symbol": "600519",
                            "name": "贵州茅台",
                        }
                    ]
                )
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        csv_text = get_etf_holdings("510300.SH", "2026-05-22")

        self.assertIn("stk_name", csv_text)
        self.assertIn("贵州茅台", csv_text)

    @patch("etfagents.dataflows.tushare._query_pro")
    def test_get_etf_holdings_preserves_existing_stock_names(self, mock_query):
        def _fake_query(api_name, **params):
            if api_name == "fund_portfolio":
                return pd.DataFrame(
                    [
                        {
                            "ts_code": "510300.SH",
                            "ann_date": "20260521",
                            "end_date": "20260520",
                            "symbol": "600519",
                            "stk_name": "贵州茅台",
                            "stk_mkv_ratio": 5.23,
                        }
                    ]
                )
            raise AssertionError(f"Unexpected api_name: {api_name}")

        mock_query.side_effect = _fake_query

        csv_text = get_etf_holdings("510300.SH", "2026-05-22")

        self.assertIn("贵州茅台", csv_text)
        self.assertEqual(1, mock_query.call_count)

if __name__ == "__main__":
    unittest.main()
