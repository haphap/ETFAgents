import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from etfagents.dataflows.exceptions import DataVendorUnavailable
from etfagents.dataflows import qlib_local


class QlibLocalTests(unittest.TestCase):
    def test_load_ohlcv_restores_original_prices_and_drops_incomplete_rows(self):
        idx = pd.to_datetime(["2026-03-07", "2026-03-10", "2026-03-11"])
        feature_map = {
            "open": pd.Series([10.0, 20.0, 30.0], index=idx, name="open"),
            "high": pd.Series([11.0, 21.0], index=idx[:2], name="high"),
            "low": pd.Series([9.0, 19.0, 29.0], index=idx, name="low"),
            "close": pd.Series([10.5, 20.5], index=idx[:2], name="close"),
            "volume": pd.Series([2000.0, 4000.0], index=idx[:2], name="volume"),
            "amount": pd.Series([500.0, 600.0], index=idx[:2], name="amount"),
            "factor": pd.Series([0.5, 0.25], index=idx[:2], name="factor"),
        }

        def fake_read_feature(_instrument, field, _start, _end):
            return feature_map.get(field, pd.Series(dtype="float64", name=field))

        with patch("etfagents.dataflows.qlib_local._read_feature", side_effect=fake_read_feature):
            df = qlib_local._load_ohlcv("sz300750", "2026-03-07", "2026-03-11")

        self.assertEqual(list(df.index.strftime("%Y-%m-%d")), ["2026-03-07", "2026-03-10"])
        self.assertAlmostEqual(df.loc[pd.Timestamp("2026-03-07"), "close"], 21.0)
        self.assertAlmostEqual(df.loc[pd.Timestamp("2026-03-10"), "open"], 80.0)
        self.assertAlmostEqual(df.loc[pd.Timestamp("2026-03-10"), "volume"], 1000.0)
        self.assertAlmostEqual(df.loc[pd.Timestamp("2026-03-07"), "amount"], 500.0)
        self.assertNotIn("factor", df.columns)
        self.assertNotIn("adjclose", df.columns)

    def test_load_ohlcv_drops_rows_with_missing_or_zero_factor(self):
        idx = pd.to_datetime(["2026-03-07", "2026-03-10", "2026-03-11"])
        feature_map = {
            "open": pd.Series([10.0, 20.0, 30.0], index=idx, name="open"),
            "high": pd.Series([11.0, 21.0, 31.0], index=idx, name="high"),
            "low": pd.Series([9.0, 19.0, 29.0], index=idx, name="low"),
            "close": pd.Series([10.5, 20.5, 30.5], index=idx, name="close"),
            "volume": pd.Series([2000.0, 4000.0, 6000.0], index=idx, name="volume"),
            "factor": pd.Series([0.5, 0.0, float("nan")], index=idx, name="factor"),
        }

        def fake_read_feature(_instrument, field, _start, _end):
            return feature_map.get(field, pd.Series(dtype="float64", name=field))

        with patch("etfagents.dataflows.qlib_local._read_feature", side_effect=fake_read_feature):
            df = qlib_local._load_ohlcv("sz300750", "2026-03-07", "2026-03-11")

        self.assertEqual(list(df.index.strftime("%Y-%m-%d")), ["2026-03-07"])
        self.assertAlmostEqual(df.loc[pd.Timestamp("2026-03-07"), "open"], 20.0)
        self.assertAlmostEqual(df.loc[pd.Timestamp("2026-03-07"), "volume"], 1000.0)

    def test_get_stock_raises_when_local_data_is_stale(self):
        idx = pd.to_datetime(["2026-02-24"])
        df = pd.DataFrame(
            {
                "open": [360.0],
                "high": [365.0],
                "low": [355.0],
                "close": [362.0],
                "volume": [1_000_000.0],
                "amount": [362_000_000.0],
            },
            index=idx,
        )
        df.index.name = "Date"

        with (
            patch("etfagents.dataflows.qlib_local._load_ohlcv", return_value=df),
            patch(
                "etfagents.dataflows.qlib_local._expected_last_trading_day",
                return_value=pd.Timestamp("2026-03-10"),
            ),
        ):
            with self.assertRaises(DataVendorUnavailable):
                qlib_local.get_stock("300750.SZ", "2026-01-01", "2026-03-10")

    def test_load_price_frame_raises_when_local_data_is_stale(self):
        idx = pd.to_datetime(["2026-02-24"])
        df = pd.DataFrame(
            {
                "open": [360.0],
                "high": [365.0],
                "low": [355.0],
                "close": [362.0],
                "volume": [1_000_000.0],
            },
            index=idx,
        )
        df.index.name = "Date"

        with (
            patch("etfagents.dataflows.qlib_local._load_ohlcv", return_value=df),
            patch(
                "etfagents.dataflows.qlib_local._expected_last_trading_day",
                return_value=pd.Timestamp("2026-03-10"),
            ),
        ):
            with self.assertRaises(DataVendorUnavailable):
                qlib_local._load_price_frame("300750.SZ", "2026-03-10")

    def test_get_stock_raises_when_local_calendar_does_not_cover_requested_trading_day(self):
        idx = pd.to_datetime(["2026-04-08"])
        df = pd.DataFrame(
            {
                "open": [390.0],
                "high": [395.0],
                "low": [385.0],
                "close": [391.3],
                "volume": [1_000_000.0],
                "amount": [391_300_000.0],
            },
            index=idx,
        )
        df.index.name = "Date"

        with (
            patch("etfagents.dataflows.qlib_local._load_ohlcv", return_value=df),
            patch(
                "etfagents.dataflows.qlib_local._load_calendar",
                return_value=[datetime(2026, 4, 7), datetime(2026, 4, 8)],
            ),
        ):
            with self.assertRaises(DataVendorUnavailable) as ctx:
                qlib_local.get_stock("300750.SZ", "2026-03-01", "2026-04-13")

        self.assertIn("trading calendar is stale", str(ctx.exception))
        self.assertIn("2026-04-08", str(ctx.exception))

    def test_get_stock_allows_weekend_request_when_calendar_reaches_prior_friday(self):
        idx = pd.to_datetime(["2026-04-10"])
        df = pd.DataFrame(
            {
                "open": [400.0],
                "high": [405.0],
                "low": [398.0],
                "close": [402.0],
                "volume": [1_100_000.0],
                "amount": [442_200_000.0],
            },
            index=idx,
        )
        df.index.name = "Date"

        with (
            patch("etfagents.dataflows.qlib_local._load_ohlcv", return_value=df),
            patch(
                "etfagents.dataflows.qlib_local._load_calendar",
                return_value=[datetime(2026, 4, 10)],
            ),
        ):
            result = qlib_local.get_stock("300750.SZ", "2026-04-01", "2026-04-12")

        self.assertIn("2026-04-10,400.0,405.0,398.0,402.0", result)


if __name__ == "__main__":
    unittest.main()
