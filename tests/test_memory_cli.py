import copy
from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from cli.main import app
from etfagents.agents.utils.analysis_memory import AnalysisMemoryStore, MethodPlaybookEntry
from etfagents.default_config import DEFAULT_CONFIG


class _FakeMetrics:
    cumulative_return = 0.0
    annualized_return = 0.0
    max_drawdown = 0.0
    sharpe_ratio = 0.0
    average_turnover = 0.0
    total_trades = 0


class _FakeHealth:
    weight_source_counts = {}
    structured_trigger_count = 0
    risk_rule_count = 0
    trigger_bucket_counts = {}
    execution_timing_mismatch_count = 0
    clamp_hit_count = 0
    missing_price_rows = 0
    unsupported_trigger_count = 0


class _FakeBacktestResult:
    execution_timing = "same_close"
    metrics = _FakeMetrics()
    benchmarks = []
    benchmark_metrics = []
    health = _FakeHealth()

    def rebalance_summary_rows(self):
        return []


class _FakeGraph:
    last_config = None

    def __init__(self, *args, **kwargs):
        _FakeGraph.last_config = kwargs.get("config")

    def backtest_candidate_pool(self, *args, **kwargs):
        return _FakeBacktestResult()


class MemoryCliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        _FakeGraph.last_config = None

    @patch("cli.main.run_analysis")
    def test_analyze_passes_memory_mode(self, mock_run_analysis):
        result = self.runner.invoke(app, ["analyze", "--memory-mode", "disabled"])

        self.assertEqual(0, result.exit_code, result.stdout)
        mock_run_analysis.assert_called_once_with(checkpoint=False, memory_mode="disabled")

    @patch("cli.main.save_backtest_result")
    @patch("cli.main._preflight_local_backend")
    @patch("cli.main.EtfAgentsGraph", _FakeGraph)
    def test_backtest_passes_memory_options_into_config(self, _mock_preflight, _mock_save):
        result = self.runner.invoke(
            app,
            [
                "backtest",
                "--tickers",
                "510300.SH,159915.SZ",
                "--start-date",
                "2026-01-02",
                "--end-date",
                "2026-01-31",
                "--memory-mode",
                "disabled",
                "--memory-in-backtest",
            ],
        )

        self.assertEqual(0, result.exit_code, result.stdout)
        self.assertIsNotNone(_FakeGraph.last_config)
        self.assertEqual("disabled", _FakeGraph.last_config["memory_mode"])
        self.assertTrue(_FakeGraph.last_config["memory_in_backtest"])

    def test_promote_playbook_cli_activates_draft_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            cfg["results_dir"] = tmpdir
            store = AnalysisMemoryStore(cfg, [])
            store.append_playbook(
                MethodPlaybookEntry(
                    id="draft-rule",
                    role="all",
                    ticker="510300.SH",
                    created_at="2026-01-01T00:00:00Z",
                    source_lesson_id="lesson-1",
                    rule="Keep invalidation explicit.",
                    status="draft",
                )
            )

            result = self.runner.invoke(
                app,
                [
                    "memory",
                    "promote-playbook",
                    "--id",
                    "draft-rule",
                    "--results-dir",
                    str(Path(tmpdir)),
                ],
            )

            self.assertEqual(0, result.exit_code, result.stdout)
            active_cutoff = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
            active = store.get_active_playbook_entries("trader", "510300.SH", active_cutoff)
            self.assertEqual(1, len(active))
            self.assertEqual("active", active[0].status)
            self.assertIsNotNone(active[0].expires_at)


if __name__ == "__main__":
    unittest.main()
