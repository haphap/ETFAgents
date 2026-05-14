import copy
import unittest
from contextvars import copy_context
from unittest.mock import patch

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.dataflows.config import backtest_context, get_config, set_config
from etfagents.dataflows.exceptions import DataVendorUnavailable
from etfagents.dataflows.interface import VENDOR_LIST, VENDOR_METHODS, route_to_vendor


class DataVendorRoutingTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())

    def tearDown(self):
        set_config(self.original_config)

    def _base_config(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["tool_vendors"] = {}
        return cfg

    def test_fallback_when_primary_vendor_unavailable(self):
        cfg = self._base_config()
        cfg["data_vendors"]["core_stock_apis"] = "tushare,yfinance"
        set_config(cfg)

        def _primary(*_args, **_kwargs):
            raise DataVendorUnavailable("tushare unavailable")

        def _fallback(*_args, **_kwargs):
            return "fallback-ok"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_stock_data": {
                    "tushare": _primary,
                    "yfinance": _fallback,
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_stock_data", "000001.SZ", "2024-01-01", "2024-01-02")

        self.assertEqual(result, "fallback-ok")

    def test_chinese_ticker_falls_back_from_qlib_to_tushare_when_local_calendar_is_stale(self):
        cfg = self._base_config()
        cfg["data_vendors"]["technical_indicators"] = "qlib,tushare"
        set_config(cfg)

        touched = []

        def _qlib(*_args, **_kwargs):
            touched.append("qlib")
            raise DataVendorUnavailable("Qlib local trading calendar is stale")

        def _tushare(*_args, **_kwargs):
            touched.append("tushare")
            return "tushare-indicator"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_indicators": {
                    "qlib": _qlib,
                    "tushare": _tushare,
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_indicators", "300750.SZ", "macd", "2026-04-13", 60)

        self.assertEqual(result, "tushare-indicator")
        self.assertEqual(touched, ["qlib", "tushare"])

    def test_tool_level_vendor_overrides_category_vendor(self):
        cfg = self._base_config()
        cfg["data_vendors"]["news_data"] = "yfinance"
        cfg["tool_vendors"] = {"get_news": "opencli"}
        set_config(cfg)

        def _opencli(*_args, **_kwargs):
            return "opencli-news"

        def _yfinance(*_args, **_kwargs):
            return "yfinance-news"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_news": {
                    "opencli": _opencli,
                    "yfinance": _yfinance,
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-02")

        self.assertEqual(result, "opencli-news")

    def test_global_news_is_pinned_to_opencli(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_global_news": "opencli"}
        set_config(cfg)

        def _opencli(*_args, **_kwargs):
            return "opencli-global"

        def _fallback(*_args, **_kwargs):
            return "fallback-global"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_global_news": {
                    "opencli": _opencli,
                    "yfinance": _fallback,
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_global_news", "2024-01-02", 7, 5)

        self.assertEqual(result, "opencli-global")

    def test_price_and_fundamentals_are_hard_pinned_to_tushare(self):
        cfg = self._base_config()
        cfg["data_vendors"]["core_stock_apis"] = "yfinance"
        cfg["data_vendors"]["technical_indicators"] = "yfinance"
        cfg["data_vendors"]["fundamental_data"] = "yfinance"
        cfg["tool_vendors"] = {
            "get_stock_data": "tushare",
            "get_indicators": "tushare",
            "get_fundamentals": "tushare",
            "get_balance_sheet": "tushare",
            "get_cashflow": "tushare",
            "get_income_statement": "tushare",
        }
        set_config(cfg)

        touched = []

        def _record(name):
            def _inner(*_args, **_kwargs):
                touched.append(name)
                return name
            return _inner

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_stock_data": {"tushare": _record("stock_tushare"), "yfinance": _record("stock_yf")},
                "get_indicators": {"tushare": _record("ind_tushare"), "yfinance": _record("ind_yf")},
                "get_fundamentals": {"tushare": _record("fund_tushare"), "yfinance": _record("fund_yf")},
                "get_balance_sheet": {"tushare": _record("bs_tushare"), "yfinance": _record("bs_yf")},
                "get_cashflow": {"tushare": _record("cf_tushare"), "yfinance": _record("cf_yf")},
                "get_income_statement": {"tushare": _record("is_tushare"), "yfinance": _record("is_yf")},
            },
            clear=False,
        ):
            self.assertEqual(route_to_vendor("get_stock_data", "000001.SZ", "2024-01-01", "2024-01-02"), "stock_tushare")
            self.assertEqual(route_to_vendor("get_indicators", "000001.SZ", "macd", "2024-01-02", 30), "ind_tushare")
            self.assertEqual(route_to_vendor("get_fundamentals", "000001.SZ", "2024-01-02"), "fund_tushare")
            self.assertEqual(route_to_vendor("get_balance_sheet", "000001.SZ", "quarterly", "2024-01-02"), "bs_tushare")
            self.assertEqual(route_to_vendor("get_cashflow", "000001.SZ", "quarterly", "2024-01-02"), "cf_tushare")
            self.assertEqual(route_to_vendor("get_income_statement", "000001.SZ", "quarterly", "2024-01-02"), "is_tushare")

        self.assertEqual(
            touched,
            [
                "stock_tushare",
                "ind_tushare",
                "fund_tushare",
                "bs_tushare",
                "cf_tushare",
                "is_tushare",
            ],
        )

    def test_unsupported_market_returns_explicit_tushare_error(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_stock_data": "tushare"}
        set_config(cfg)

        def _unsupported(*_args, **_kwargs):
            raise DataVendorUnavailable(
                "Tushare currently supports A-share, Hong Kong, and US tickers only, got '7203.T'."
            )

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_stock_data": {"tushare": _unsupported},
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                route_to_vendor("get_stock_data", "7203.T", "2024-01-01", "2024-01-02")

        self.assertIn("A-share, Hong Kong, and US tickers only", str(ctx.exception))

    def test_alpha_vantage_is_not_an_available_vendor(self):
        self.assertNotIn("alpha_vantage", VENDOR_LIST)

        for vendor_map in VENDOR_METHODS.values():
            self.assertNotIn("alpha_vantage", vendor_map)

    def test_get_config_returns_deep_copy_of_nested_vendor_maps(self):
        cfg = self._base_config()
        set_config(cfg)

        snapshot = get_config()
        snapshot["data_vendors"]["news_data"] = "tampered"
        snapshot["tool_vendors"]["get_news"] = "tampered"

        current = get_config()
        self.assertEqual(current["data_vendors"]["news_data"], cfg["data_vendors"]["news_data"])
        self.assertNotIn("get_news", current["tool_vendors"])

    def test_config_is_isolated_per_context(self):
        english_cfg = self._base_config()
        english_cfg["output_language"] = "English"
        chinese_cfg = self._base_config()
        chinese_cfg["output_language"] = "Chinese"

        set_config(english_cfg)
        isolated = copy_context()
        isolated.run(set_config, chinese_cfg)

        self.assertEqual(get_config()["output_language"], "English")
        self.assertEqual(isolated.run(get_config)["output_language"], "Chinese")

    def test_backtest_context_clamps_range_end_date_before_vendor_call(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_stock_data": "tushare"}
        set_config(cfg)
        captured = {}

        def _tushare(*args, **_kwargs):
            captured["args"] = args
            return "stock_tushare"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_stock_data": {"tushare": _tushare},
            },
            clear=False,
        ):
            with backtest_context("2024-01-15"):
                result = route_to_vendor(
                    "get_stock_data",
                    "000001.SZ",
                    "2024-01-01",
                    "2024-01-31",
                )

        self.assertEqual(result, "stock_tushare")
        self.assertEqual(captured["args"], ("000001.SZ", "2024-01-01", "2024-01-15"))

    def test_backtest_context_clamps_curr_date_before_vendor_call(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_etf_info": "tushare"}
        set_config(cfg)
        captured = {}

        def _tushare(*args, **_kwargs):
            captured["args"] = args
            return "etf-info"

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_etf_info": {"tushare": _tushare},
            },
            clear=False,
        ):
            with backtest_context("2024-01-15"):
                result = route_to_vendor("get_etf_info", "510300.SH", "2024-01-31")

        self.assertEqual(result, "etf-info")
        self.assertEqual(captured["args"], ("510300.SH", "2024-01-15"))

    def test_backtest_context_rejects_unbounded_method(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_insider_transactions": "tushare"}
        set_config(cfg)

        with backtest_context("2024-01-15"):
            with self.assertRaises(RuntimeError) as ctx:
                route_to_vendor("get_insider_transactions", "002155.SZ")

        self.assertIn("no date boundary", str(ctx.exception))

    def test_backtest_context_rejects_news_method(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_news": "opencli"}
        set_config(cfg)

        with backtest_context("2024-01-15"):
            with self.assertRaises(RuntimeError) as ctx:
                route_to_vendor("get_news", "AAPL", "2024-01-01", "2024-01-31")

        self.assertIn("no date boundary", str(ctx.exception))

    def test_backtest_context_rejects_global_news_method(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_global_news": "opencli"}
        set_config(cfg)

        with backtest_context("2024-01-15"):
            with self.assertRaises(RuntimeError) as ctx:
                route_to_vendor("get_global_news", "2024-01-31", 7, 5)

        self.assertIn("no date boundary", str(ctx.exception))

    def test_a_share_insider_transactions_prefers_tushare(self):
        cfg = self._base_config()
        cfg["data_vendors"]["news_data"] = "opencli,brave,yfinance"
        cfg["tool_vendors"] = {"get_insider_transactions": "tushare,yfinance"}
        set_config(cfg)

        touched = []

        def _tushare(*_args, **_kwargs):
            touched.append("tushare")
            return [{"insider": "a-share"}]

        def _yfinance(*_args, **_kwargs):
            touched.append("yfinance")
            return [{"insider": "example"}]

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_insider_transactions": {
                    "tushare": _tushare,
                    "yfinance": _yfinance,
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_insider_transactions", "002155.SZ")

        self.assertEqual(touched, ["tushare"])
        self.assertEqual(result, [{"insider": "a-share"}])

    def test_non_a_share_insider_transactions_fall_back_to_yfinance(self):
        cfg = self._base_config()
        cfg["tool_vendors"] = {"get_insider_transactions": "tushare,yfinance"}
        set_config(cfg)

        touched = []

        def _tushare(*_args, **_kwargs):
            touched.append("tushare")
            raise DataVendorUnavailable("A-share only")

        def _yfinance(*_args, **_kwargs):
            touched.append("yfinance")
            return [{"insider": "fallback"}]

        with patch.dict(
            VENDOR_METHODS,
            {
                "get_insider_transactions": {
                    "tushare": _tushare,
                    "yfinance": _yfinance,
                }
            },
            clear=False,
        ):
            result = route_to_vendor("get_insider_transactions", "AAPL")

        self.assertEqual(touched, ["tushare", "yfinance"])
        self.assertEqual(result, [{"insider": "fallback"}])


if __name__ == "__main__":
    unittest.main()
