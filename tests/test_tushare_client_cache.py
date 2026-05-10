"""Tests for tushare _get_pro_client caching behavior."""

import sys
import unittest
from unittest.mock import MagicMock, patch


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


if __name__ == "__main__":
    unittest.main()
