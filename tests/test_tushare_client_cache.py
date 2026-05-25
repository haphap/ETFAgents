"""Tests for tushare _get_pro_client caching behavior."""

import importlib.util
import unittest
if not importlib.util.find_spec("pandas"):
    raise unittest.SkipTest("pandas not installed")

import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

class TestTushareClientCache(unittest.TestCase):
    def setUp(self):
        from etfagents.dataflows.tushare import clear_pro_client_cache
        clear_pro_client_cache()

    def tearDown(self):
        from etfagents.dataflows.tushare import clear_pro_client_cache
        clear_pro_client_cache()

    @patch.dict("os.environ", {"TUSHARE_TOKEN": "test-token"})
    def test_client_is_cached(self):
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value = MagicMock()
        with patch.dict(sys.modules, {"tushare": mock_ts}):
            from etfagents.dataflows.tushare import _get_pro_client, clear_pro_client_cache
            clear_pro_client_cache()
            client1 = _get_pro_client()
            client2 = _get_pro_client()
            self.assertIs(client1, client2)
            mock_ts.pro_api.assert_called_once()

    @patch.dict("os.environ", {"TUSHARE_TOKEN": "test-token"})
    def test_failed_init_does_not_cache(self):
        mock_ts = MagicMock()
        mock_ts.pro_api.side_effect = RuntimeError("init failed")
        with patch.dict(sys.modules, {"tushare": mock_ts}):
            from etfagents.dataflows.tushare import _get_pro_client, clear_pro_client_cache, DataVendorUnavailable
            clear_pro_client_cache()
            with self.assertRaises(DataVendorUnavailable):
                _get_pro_client()

            # Should not be cached — next call should retry
            mock_ts.pro_api.side_effect = None
            mock_ts.pro_api.return_value = MagicMock()
            client = _get_pro_client()
            self.assertIsNotNone(client)
            self.assertEqual(mock_ts.pro_api.call_count, 2)

    def test_missing_token_raises(self):
        from etfagents.dataflows.tushare import _get_pro_client, DataVendorUnavailable
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(DataVendorUnavailable):
                _get_pro_client()

    def test_clear_cache_works(self):
        import etfagents.dataflows.tushare as mod
        sentinel = MagicMock()
        mod._cached_pro_client = sentinel
        self.assertIs(mod._get_pro_client(), sentinel)
        mod.clear_pro_client_cache()
        self.assertIsNone(mod._cached_pro_client)

    def test_query_pro_retries_transient_connection_reset_once(self):
        from etfagents.dataflows.tushare import _query_pro

        expected = pd.DataFrame({"ts_code": ["560860.SH"]})
        client = MagicMock()
        client.query.side_effect = [
            ConnectionError("Connection aborted.", ConnectionResetError(104, "Connection reset by peer")),
            expected,
        ]

        with (
            patch("etfagents.dataflows.tushare._get_pro_client", return_value=client),
            patch("etfagents.dataflows.tushare.time.sleep") as sleep,
        ):
            result = _query_pro("fund_basic", ts_code="560860.SH")

        self.assertIs(result, expected)
        self.assertEqual(client.query.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_query_pro_stops_after_transient_retry_budget(self):
        from etfagents.dataflows.tushare import DataVendorUnavailable, _query_pro

        client = MagicMock()
        client.query.side_effect = ConnectionError(
            "Connection aborted.", ConnectionResetError(104, "Connection reset by peer")
        )

        with (
            patch("etfagents.dataflows.tushare._get_pro_client", return_value=client),
            patch("etfagents.dataflows.tushare.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(DataVendorUnavailable, "after 3 attempt"):
                _query_pro("fund_basic", ts_code="560860.SH")

        self.assertEqual(client.query.call_count, 3)
        self.assertEqual([sleep_call.args[0] for sleep_call in sleep.call_args_list], [0.5, 1.5])

    def test_query_pro_reports_actual_attempt_count_after_mixed_failures(self):
        from etfagents.dataflows.tushare import DataVendorUnavailable, _query_pro

        client = MagicMock()
        client.query.side_effect = [
            ConnectionError("Connection aborted.", ConnectionResetError(104, "Connection reset by peer")),
            RuntimeError("permission denied"),
        ]

        with (
            patch("etfagents.dataflows.tushare._get_pro_client", return_value=client),
            patch("etfagents.dataflows.tushare.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(DataVendorUnavailable, "after 2 attempt"):
                _query_pro("fund_basic", ts_code="560860.SH")

        self.assertEqual(client.query.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_query_pro_does_not_retry_non_transient_api_error(self):
        from etfagents.dataflows.tushare import DataVendorUnavailable, _query_pro

        client = MagicMock()
        client.query.side_effect = RuntimeError("permission denied")

        with (
            patch("etfagents.dataflows.tushare._get_pro_client", return_value=client),
            patch("etfagents.dataflows.tushare.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(DataVendorUnavailable, "after 1 attempt"):
                _query_pro("fund_basic", ts_code="560860.SH")

        client.query.assert_called_once_with("fund_basic", ts_code="560860.SH")
        sleep.assert_not_called()

if __name__ == "__main__":
    unittest.main()
