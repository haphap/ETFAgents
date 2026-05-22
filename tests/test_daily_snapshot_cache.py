import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import etfagents.agents.utils.etf_data_tools as etf_data_tools
from etfagents.agents.utils.daily_snapshot_cache import (
    DailySnapshotCacheError,
    get_or_build_shared_snapshot,
)
from etfagents.dataflows.config import get_config, set_config
from etfagents.default_config import DEFAULT_CONFIG


class SharedSnapshotCacheTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())
        self.tempdir = tempfile.TemporaryDirectory()
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["data_cache_dir"] = self.tempdir.name
        set_config(cfg)
        etf_data_tools._load_cn_schedule_frame.cache_clear()
        etf_data_tools._load_tushare_futures_contract_catalog.cache_clear()
        etf_data_tools._load_tushare_futures_daily_exchange_frame.cache_clear()
        etf_data_tools._load_tushare_futures_main_frame.cache_clear()
        etf_data_tools._load_tushare_warehouse_exchange_frame.cache_clear()
        etf_data_tools._load_tushare_warehouse_series.cache_clear()

    def tearDown(self):
        set_config(self.original_config)
        self.tempdir.cleanup()

    def test_shared_snapshot_persists_after_first_build(self):
        calls = []

        def _builder(curr_date, look_back_days):
            calls.append((curr_date, look_back_days))
            return {"marker": f"{curr_date}:{look_back_days}"}, {"source_summary": "test"}

        first_payload, first_hit = get_or_build_shared_snapshot(
            snapshot_kind="macro",
            curr_date="2026-04-30",
            min_coverage_days=365,
            schema_version=1,
            builder=_builder,
        )
        second_payload, second_hit = get_or_build_shared_snapshot(
            snapshot_kind="macro",
            curr_date="2026-04-30",
            min_coverage_days=365,
            schema_version=1,
            builder=_builder,
        )

        self.assertEqual(first_payload, {"marker": "2026-04-30:365"})
        self.assertEqual(second_payload, first_payload)
        self.assertFalse(first_hit)
        self.assertTrue(second_hit)
        self.assertEqual(calls, [("2026-04-30", 365)])

    def test_schema_change_forces_refresh(self):
        calls = []

        def _builder(curr_date, look_back_days):
            calls.append((curr_date, look_back_days))
            return {"call_count": len(calls)}, {"source_summary": "test"}

        get_or_build_shared_snapshot("macro", "2026-04-30", 365, 1, _builder)
        payload, cache_hit = get_or_build_shared_snapshot(
            "macro",
            "2026-04-30",
            365,
            2,
            _builder,
        )

        self.assertFalse(cache_hit)
        self.assertEqual(payload["call_count"], 2)
        self.assertEqual(calls, [("2026-04-30", 365), ("2026-04-30", 365)])

    def test_insufficient_coverage_forces_refresh(self):
        calls = []

        def _builder(curr_date, look_back_days):
            calls.append(look_back_days)
            return {"coverage_days": look_back_days}, {"source_summary": "test"}

        get_or_build_shared_snapshot("commodity", "2026-04-30", 30, 1, _builder)
        payload, cache_hit = get_or_build_shared_snapshot(
            "commodity",
            "2026-04-30",
            90,
            1,
            _builder,
        )

        self.assertFalse(cache_hit)
        self.assertEqual(payload["coverage_days"], 90)
        self.assertEqual(calls, [30, 90])

    def test_corrupted_cache_raises_explicit_error(self):
        cache_path = (
            Path(self.tempdir.name)
            / "shared_snapshots"
            / "macro"
            / "2026-04-30.json"
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("{not-json", encoding="utf-8")

        with self.assertRaises(DailySnapshotCacheError) as ctx:
            get_or_build_shared_snapshot(
                "macro",
                "2026-04-30",
                365,
                1,
                lambda curr_date, look_back_days: ({}, {"source_summary": "test"}),
            )

        self.assertIn("invalid JSON", str(ctx.exception))


class SharedSnapshotToolIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())
        self.tempdir = tempfile.TemporaryDirectory()
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["data_cache_dir"] = self.tempdir.name
        set_config(cfg)
        etf_data_tools._load_cn_schedule_frame.cache_clear()
        etf_data_tools._load_tushare_futures_contract_catalog.cache_clear()
        etf_data_tools._load_tushare_futures_daily_exchange_frame.cache_clear()
        etf_data_tools._load_tushare_futures_main_frame.cache_clear()
        etf_data_tools._load_tushare_warehouse_exchange_frame.cache_clear()
        etf_data_tools._load_tushare_warehouse_series.cache_clear()

    def tearDown(self):
        set_config(self.original_config)
        self.tempdir.cleanup()

    @staticmethod
    def _series(points):
        index = pd.to_datetime([point[0] for point in points])
        return pd.Series([point[1] for point in points], index=index)

    @staticmethod
    def _futures_frame():
        return pd.DataFrame(
            {
                "trade_date": ["2026-01-30", "2026-03-31", "2026-04-30"],
                "close": [100.0, 108.0, 112.0],
                "oi": [200.0, 215.0, 230.0],
            }
        )

    def test_macro_tool_reuses_disk_cache(self):
        fred_calls = []
        yfinance_calls = []

        def _fake_fred(series_id, curr_date, look_back_days=540):
            fred_calls.append(series_id)
            base = {
                "FEDFUNDS": [( "2026-01-30", 4.2), ("2026-03-31", 4.3), ("2026-04-30", 4.4)],
                "DGS10": [("2026-01-30", 4.0), ("2026-03-31", 4.1), ("2026-04-30", 4.2)],
                "ECBDFR": [("2026-01-30", 2.6), ("2026-03-31", 2.5), ("2026-04-30", 2.4)],
                "IRLTLT01DEM156N": [("2026-01-30", 2.4), ("2026-03-31", 2.45), ("2026-04-30", 2.5)],
                "IR3TIB01JPM156N": [("2026-01-30", 0.2), ("2026-03-31", 0.25), ("2026-04-30", 0.3)],
                "IRLTLT01JPM156N": [("2026-01-30", 1.0), ("2026-03-31", 1.05), ("2026-04-30", 1.1)],
                "DFII10": [("2026-01-30", 1.4), ("2026-03-31", 1.5), ("2026-04-30", 1.6)],
                "BAMLH0A3HYC": [("2026-01-30", 350.0), ("2026-03-31", 360.0), ("2026-04-30", 365.0)],
            }
            return self._series(base[series_id])

        def _fake_yfinance(symbol, curr_date, look_back_days=240):
            yfinance_calls.append(symbol)
            return self._series(
                [("2026-01-30", 100.0), ("2026-03-31", 104.0), ("2026-04-30", 108.0)]
            )

        schedule = pd.DataFrame(
            {
                "publish_date": pd.to_datetime(["2026-04-25", "2026-05-08"]),
                "title": ["PMI", "CPI"],
                "issuing_org": ["NBS", "NBS"],
                "data_api": ["cn_schedule", "cn_schedule"],
            }
        )

        with patch(
            "etfagents.agents.utils.etf_data_tools._load_fred_series",
            side_effect=_fake_fred,
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_china_policy_rate_series",
            return_value=self._series(
                [("2026-01-30", 1.9), ("2026-03-31", 2.0), ("2026-04-30", 2.1)]
            ),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_china_ten_year_yield_series",
            return_value=self._series(
                [("2026-01-30", 2.2), ("2026-03-31", 2.25), ("2026-04-30", 2.3)]
            ),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_yfinance_close",
            side_effect=_fake_yfinance,
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_cn_schedule_frame",
            return_value=schedule,
        ):
            first = etf_data_tools.get_macro_regime_data.invoke(
                {"curr_date": "2026-04-30", "look_back_days": 120}
            )

        self.assertIn("Global Macro Regime Snapshot (2026-04-30)", first)
        self.assertTrue(fred_calls)
        self.assertTrue(yfinance_calls)

        with patch(
            "etfagents.agents.utils.etf_data_tools._load_fred_series",
            side_effect=AssertionError("macro cache miss"),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_china_policy_rate_series",
            side_effect=AssertionError("macro cache miss"),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_china_ten_year_yield_series",
            side_effect=AssertionError("macro cache miss"),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_yfinance_close",
            side_effect=AssertionError("macro cache miss"),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_cn_schedule_frame",
            side_effect=AssertionError("macro cache miss"),
        ):
            second = etf_data_tools.get_macro_regime_data.invoke(
                {"curr_date": "2026-04-30", "look_back_days": 120}
            )

        self.assertEqual(second, first)

    def test_commodity_tool_reuses_disk_cache(self):
        with patch(
            "etfagents.agents.utils.etf_data_tools._load_tushare_futures_main_frame",
            return_value=self._futures_frame(),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_tushare_warehouse_series",
            return_value=self._series(
                [("2026-01-30", 90.0), ("2026-03-31", 85.0), ("2026-04-30", 80.0)]
            ),
        ):
            first = etf_data_tools.get_commodity_cluster_data.invoke(
                {"curr_date": "2026-04-30", "look_back_days": 120}
            )

        self.assertIn("Commodity Cluster Snapshot (2026-04-30)", first)

        with patch(
            "etfagents.agents.utils.etf_data_tools._load_tushare_futures_main_frame",
            side_effect=AssertionError("commodity cache miss"),
        ), patch(
            "etfagents.agents.utils.etf_data_tools._load_tushare_warehouse_series",
            side_effect=AssertionError("commodity cache miss"),
        ):
            second = etf_data_tools.get_commodity_cluster_data.invoke(
                {"curr_date": "2026-04-30", "look_back_days": 120}
            )

        self.assertEqual(second, first)


if __name__ == "__main__":
    unittest.main()
