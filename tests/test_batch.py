import time
import unittest
from unittest.mock import MagicMock, patch

from etfagents.graph.etf_graph import EtfAgentsGraph


def _make_graph():
    graph = object.__new__(EtfAgentsGraph)
    graph.config = {"data_cache_dir": "/tmp"}
    graph.selected_analysts = EtfAgentsGraph.DEFAULT_SELECTED_ANALYSTS
    graph._RATING_SCORE = EtfAgentsGraph._RATING_SCORE
    return graph


class AnalyzeCandidatePoolCallbackTests(unittest.TestCase):
    @patch("etfagents.graph.etf_graph.BacktestSignalStore")
    @patch.object(EtfAgentsGraph, "propagate")
    def test_callback_called_per_ticker(self, mock_propagate, _mock_cache_cls):
        mock_propagate.return_value = ({"final_allocation_decision": "Rating: BUY"}, "BUY")
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        _mock_cache_cls.return_value = mock_cache

        graph = _make_graph()
        callbacks = []
        results = graph.analyze_candidate_pool(
            ["510300.SH", "159915.SZ"],
            "2026-05-20",
            per_ticker_callback=lambda t, i, n, r: callbacks.append((t, i, n, r)),
        )
        self.assertEqual(len(callbacks), 2)
        self.assertEqual(callbacks[0][0], "510300.SH")
        self.assertEqual(callbacks[0][1], 0)
        self.assertEqual(callbacks[0][2], 2)
        self.assertEqual(callbacks[1][0], "159915.SZ")
        self.assertEqual(callbacks[1][1], 1)

    @patch("etfagents.graph.etf_graph.BacktestSignalStore")
    @patch.object(EtfAgentsGraph, "propagate")
    def test_callback_receives_error_on_failure(self, mock_propagate, _mock_cache_cls):
        mock_propagate.side_effect = [
            RuntimeError("API down"),
            ({"final_allocation_decision": "Rating: HOLD"}, "HOLD"),
        ]
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        _mock_cache_cls.return_value = mock_cache

        graph = _make_graph()
        callbacks = []
        results = graph.analyze_candidate_pool(
            ["510300.SH", "159915.SZ"],
            "2026-05-20",
            per_ticker_callback=lambda t, i, n, r: callbacks.append((t, i, n, r)),
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticker"], "159915.SZ")
        self.assertEqual(len(callbacks), 2)
        self.assertIsInstance(callbacks[0][3], RuntimeError)
        self.assertEqual(callbacks[0][0], "510300.SH")
        self.assertNotIsInstance(callbacks[1][3], Exception)

    @patch("etfagents.graph.etf_graph.BacktestSignalStore")
    @patch.object(EtfAgentsGraph, "propagate")
    def test_no_callback_when_none(self, mock_propagate, _mock_cache_cls):
        mock_propagate.return_value = ({"final_allocation_decision": "Rating: HOLD"}, "HOLD")
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        _mock_cache_cls.return_value = mock_cache

        graph = _make_graph()
        results = graph.analyze_candidate_pool(
            ["510300.SH"],
            "2026-05-20",
        )
        self.assertEqual(len(results), 1)

    @patch("etfagents.graph.etf_graph.BacktestSignalStore")
    @patch.object(EtfAgentsGraph, "propagate")
    def test_all_tickers_fail_still_returns_empty(self, mock_propagate, _mock_cache_cls):
        mock_propagate.side_effect = RuntimeError("API down")
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        _mock_cache_cls.return_value = mock_cache

        graph = _make_graph()
        results = graph.analyze_candidate_pool(
            ["510300.SH", "159915.SZ"],
            "2026-05-20",
        )
        self.assertEqual(results, [])

    @patch("etfagents.graph.etf_graph.BacktestSignalStore")
    @patch.object(EtfAgentsGraph, "propagate")
    def test_callback_on_cached_result(self, mock_propagate, _mock_cache_cls):
        mock_cache = MagicMock()
        mock_cache.get.return_value = {
            "ticker": "510300.SH",
            "rating": "BUY",
            "score": "4",
            "final_allocation_decision": "Rating: BUY",
            "market_flow_report": "report",
            "catalyst_sentiment_report": "report",
            "macro_regime_report": "report",
            "meso_commodity_report": "report",
            "holdings_industry_report": "report",
            "top_holdings_report": "report",
        }
        _mock_cache_cls.return_value = mock_cache

        graph = _make_graph()
        callbacks = []
        results = graph.analyze_candidate_pool(
            ["510300.SH"],
            "2026-05-20",
            per_ticker_callback=lambda t, i, n, r: callbacks.append((t, i, n, r)),
        )
        mock_propagate.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(callbacks[0][0], "510300.SH")
        self.assertNotIsInstance(callbacks[0][3], Exception)

    @patch("etfagents.graph.etf_graph.BacktestSignalStore")
    @patch.object(EtfAgentsGraph, "propagate")
    def test_callback_timing_per_ticker_delta_not_cumulative(self, mock_propagate, _mock_cache_cls):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        _mock_cache_cls.return_value = mock_cache
        mock_propagate.return_value = ({"final_allocation_decision": "Rating: HOLD"}, "HOLD")

        fake_t = [100.0]
        step = [30.0, 150.0]

        def _fake_time():
            if step:
                fake_t[0] += step.pop(0)
            return fake_t[0]

        with patch("time.time", side_effect=_fake_time):
            graph = _make_graph()
            completed_times: list[float] = []
            results = graph.analyze_candidate_pool(
                ["510300.SH", "159915.SZ"],
                "2026-05-20",
                per_ticker_callback=lambda t, i, n, r: completed_times.append(time.time()),
            )

        self.assertEqual(len(completed_times), 2)
        delta_1 = completed_times[0] - 100.0
        delta_2 = completed_times[1] - completed_times[0]
        self.assertAlmostEqual(delta_1, 30.0)
        self.assertAlmostEqual(delta_2, 150.0)


if __name__ == "__main__":
    unittest.main()
