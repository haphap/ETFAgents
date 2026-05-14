import unittest
from tempfile import TemporaryDirectory

import pandas as pd

from etfagents.backtest.backtrader_engine import (
    EQUAL_WEIGHT_BENCHMARK,
    run_candidate_pool_backtest,
    save_backtest_result,
)
from etfagents.graph.etf_graph import EtfAgentsGraph


class BacktraderEngineTests(unittest.TestCase):
    def _make_graph(self):
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

        graph.analyze_candidate_pool = _fake_ranked
        return graph

    def test_backtrader_backtest_matches_replay_same_close(self):
        graph = self._make_graph()

        def _fake_prices(ticker, _start_date, _end_date):
            frames = {
                "159915.SZ": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 110.0, 111.0],
                        "High": [100.0, 110.0, 111.0],
                        "Low": [100.0, 110.0, 111.0],
                        "Close": [100.0, 110.0, 111.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
                "510300.SH": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 101.0, 106.0],
                        "High": [100.0, 101.0, 106.0],
                        "Low": [100.0, 101.0, 106.0],
                        "Close": [100.0, 101.0, 106.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
            }
            return frames[ticker]

        replay = EtfAgentsGraph.replay_candidate_pool(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            execution_timing="same_close",
            price_loader=_fake_prices,
        )
        result = run_candidate_pool_backtest(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            execution_timing="same_close",
            initial_cash=1_000_000.0,
            price_loader=_fake_prices,
        )

        self.assertAlmostEqual(result.metrics.cumulative_return, replay.metrics.cumulative_return, places=6)
        self.assertEqual(result.execution_timing, "same_close")
        self.assertEqual(len(result.rebalances), 2)
        self.assertEqual(result.rebalances[0].selected_tickers, ["159915.SZ"])
        self.assertEqual(result.rebalances[1].selected_tickers, ["510300.SH"])

    def test_backtrader_backtest_supports_next_open(self):
        graph = self._make_graph()

        def _fake_prices(ticker, _start_date, _end_date):
            frames = {
                "159915.SZ": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08", "2026-01-10"]),
                        "Open": [100.0, 101.0, 111.0, 112.0],
                        "High": [100.0, 110.0, 111.0, 112.0],
                        "Low": [100.0, 101.0, 111.0, 112.0],
                        "Close": [100.0, 110.0, 111.0, 112.0],
                        "Volume": [1_000, 1_000, 1_000, 1_000],
                    }
                ),
                "510300.SH": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08", "2026-01-10"]),
                        "Open": [100.0, 101.0, 102.0, 107.0],
                        "High": [100.0, 101.0, 106.0, 107.0],
                        "Low": [100.0, 101.0, 102.0, 107.0],
                        "Close": [100.0, 101.0, 106.0, 107.0],
                        "Volume": [1_000, 1_000, 1_000, 1_000],
                    }
                ),
            }
            return frames[ticker]

        replay = EtfAgentsGraph.replay_candidate_pool(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            execution_timing="next_open",
            price_loader=_fake_prices,
        )
        result = EtfAgentsGraph.backtest_candidate_pool(
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
        self.assertAlmostEqual(result.metrics.cumulative_return, replay.metrics.cumulative_return, places=6)
        self.assertGreaterEqual(len(result.orders), 2)
        self.assertEqual(result.rebalances[0].execution_date, "2026-01-06")

    def test_backtrader_backtest_defaults_to_equal_weight_benchmark_for_pool(self):
        graph = self._make_graph()

        def _fake_prices(ticker, _start_date, _end_date):
            frames = {
                "159915.SZ": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 110.0, 111.0],
                        "High": [100.0, 110.0, 111.0],
                        "Low": [100.0, 110.0, 111.0],
                        "Close": [100.0, 110.0, 111.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
                "510300.SH": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 101.0, 106.0],
                        "High": [100.0, 101.0, 106.0],
                        "Low": [100.0, 101.0, 106.0],
                        "Close": [100.0, 101.0, 106.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
            }
            return frames[ticker]

        result = run_candidate_pool_backtest(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            execution_timing="same_close",
            initial_cash=1_000_000.0,
            price_loader=_fake_prices,
        )

        self.assertEqual(result.benchmarks, [EQUAL_WEIGHT_BENCHMARK])
        self.assertEqual(len(result.benchmark_metrics), 1)
        self.assertEqual(result.benchmark_metrics[0].benchmark, EQUAL_WEIGHT_BENCHMARK)
        self.assertAlmostEqual(result.benchmark_metrics[0].cumulative_return, 0.085, places=6)
        self.assertAlmostEqual(result.benchmark_metrics[0].excess_cumulative_return, 0.0694554455, places=6)

    def test_backtrader_backtest_supports_explicit_benchmark_ticker(self):
        graph = self._make_graph()

        def _fake_prices(ticker, _start_date, _end_date):
            frames = {
                "159915.SZ": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 110.0, 111.0],
                        "High": [100.0, 110.0, 111.0],
                        "Low": [100.0, 110.0, 111.0],
                        "Close": [100.0, 110.0, 111.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
                "510300.SH": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 101.0, 106.0],
                        "High": [100.0, 101.0, 106.0],
                        "Low": [100.0, 101.0, 106.0],
                        "Close": [100.0, 101.0, 106.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
                "SPY": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 102.0, 103.0],
                        "High": [100.0, 102.0, 103.0],
                        "Low": [100.0, 102.0, 103.0],
                        "Close": [100.0, 102.0, 103.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
            }
            return frames[ticker]

        result = run_candidate_pool_backtest(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            execution_timing="same_close",
            initial_cash=1_000_000.0,
            benchmark_tickers=["SPY"],
            price_loader=_fake_prices,
        )

        self.assertEqual(result.benchmarks, ["SPY"])
        self.assertEqual(len(result.benchmark_nav), len(result.nav))
        self.assertAlmostEqual(result.benchmark_metrics[0].cumulative_return, 0.03, places=6)

    def test_save_backtest_result_writes_artifacts(self):
        graph = self._make_graph()

        def _fake_prices(ticker, _start_date, _end_date):
            frames = {
                "159915.SZ": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 110.0, 111.0],
                        "High": [100.0, 110.0, 111.0],
                        "Low": [100.0, 110.0, 111.0],
                        "Close": [100.0, 110.0, 111.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
                "510300.SH": pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2026-01-02", "2026-01-06", "2026-01-08"]),
                        "Open": [100.0, 101.0, 106.0],
                        "High": [100.0, 101.0, 106.0],
                        "Low": [100.0, 101.0, 106.0],
                        "Close": [100.0, 101.0, 106.0],
                        "Volume": [1_000, 1_000, 1_000],
                    }
                ),
            }
            return frames[ticker]

        result = run_candidate_pool_backtest(
            graph,
            ["159915.SZ", "510300.SH"],
            "2026-01-02",
            "2026-01-08",
            rebalance_interval_days=1,
            top_k=1,
            execution_timing="same_close",
            price_loader=_fake_prices,
        )

        with TemporaryDirectory() as tmpdir:
            output_dir = save_backtest_result(result, tmpdir)
            self.assertTrue((output_dir / "manifest.json").exists())
            self.assertTrue((output_dir / "metrics.json").exists())
            self.assertTrue((output_dir / "nav.csv").exists())
            self.assertTrue((output_dir / "benchmarks.csv").exists())
            self.assertTrue((output_dir / "positions.csv").exists())
            self.assertTrue((output_dir / "orders.csv").exists())
            self.assertTrue((output_dir / "summary.md").exists())
            self.assertTrue((output_dir / "nav_chart.svg").exists())
            self.assertTrue((output_dir / "report.html").exists())
            self.assertTrue((output_dir / "signals" / "2026-01-02.json").exists())


if __name__ == "__main__":
    unittest.main()
