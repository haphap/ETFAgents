"""Contract tests for AnalysisRunner (M2).

These tests verify that the runner correctly handles streaming,
cancellation, error recovery, and resource cleanup.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _build_stubs():
    """Build lightweight stubs for heavy modules that AnalysisRunner
    lazy-imports (cli.report_utils, cli.stats_handler) so tests run
    without langchain_core / langgraph installed."""
    stubs: dict[str, types.ModuleType] = {}

    report_mod = types.ModuleType("cli.report_utils")
    report_mod.merge_stream_state = lambda acc, upd, **kw: acc.update(
        {k: v for k, v in (upd if isinstance(upd, dict) else {}).items() if v}
    )
    stubs["cli.report_utils"] = report_mod

    stats_mod = types.ModuleType("cli.stats_handler")
    stats_mod.StatsCallbackHandler = type(
        "StatsCallbackHandler", (), {"get_stats": lambda self: {}}
    )
    stubs["cli.stats_handler"] = stats_mod

    return stubs


# Import under stub context, then exit immediately so sys.modules is clean.
_stubs = _build_stubs()
with patch.dict(sys.modules, _stubs):
    from cli.tui.services import (
        AnalysisRunner,
        SectionDone,
        TickerCancelled,
        TickerDone,
        TickerFailed,
        TickerStarted,
    )


class _FakeGraph:
    """Minimal fake graph for testing runner contracts."""

    def __init__(self):
        self.closed = False
        self.finalized = False

    def prepare_run(self, ticker, date, callbacks=None):
        return {}, {}, False

    def finalize_run(self, date, state):
        self.finalized = True

    def close_run(self):
        self.closed = True

    @property
    def graph(self):
        return self

    def stream(self, init_state, **kwargs):
        """Minimal stream that yields one dummy chunk."""
        yield {"dummy": "chunk"}


class AnalysisRunnerContractTests(unittest.TestCase):
    def setUp(self):
        self._stub_patcher = patch.dict(sys.modules, _build_stubs())
        self._stub_patcher.start()
        self._markdown_patcher = patch.object(
            AnalysisRunner,
            "_prepare_markdown",
            staticmethod(lambda content: content),
        )
        self._markdown_patcher.start()

    def tearDown(self):
        self._markdown_patcher.stop()
        self._stub_patcher.stop()

    def test_stream_emits_ticker_started_then_section_done_then_ticker_done(self):
        """Runner must yield TickerStarted → SectionDone × N → TickerDone."""
        runner = AnalysisRunner()

        # Mock the graph and report saving
        with patch.object(runner, "_make_graph") as mock_make_graph:
            with patch.object(runner, "_save_report") as mock_save_report:
                with patch.object(runner, "_extract_rating_from_report") as mock_rating:
                    fake_graph = _FakeGraph()
                    mock_make_graph.return_value = fake_graph
                    mock_save_report.return_value = Path("/fake/report.md")
                    mock_rating.return_value = "BUY"

                    # Override stream to emit a real market_flow_report chunk
                    def fake_stream(init_state, **kwargs):
                        yield {"market_flow_report": "Market analysis"}

                    fake_graph.stream = fake_stream

                    events = list(runner.run_queue(["510300.SH"]))

                    # Verify sequence
                    self.assertIsInstance(events[0], TickerStarted)
                    self.assertEqual(events[0].ticker, "510300.SH")
                    self.assertTrue(any(isinstance(e, SectionDone) for e in events))
                    self.assertIsInstance(events[-1], TickerDone)
                    self.assertEqual(events[-1].ticker, "510300.SH")
                    self.assertEqual(events[-1].rating, "BUY")

    def test_selected_analysts_limit_visible_runner_sections(self):
        """Configured analyst selection should drive progress totals and emitted sections."""
        runner = AnalysisRunner()

        with patch.object(runner, "_make_graph") as mock_make_graph:
            with patch.object(runner, "_save_report") as mock_save_report:
                with patch.object(runner, "_extract_rating_from_report") as mock_rating:
                    fake_graph = _FakeGraph()
                    mock_make_graph.return_value = fake_graph
                    mock_save_report.return_value = Path("/fake/report.md")
                    mock_rating.return_value = None

                    def fake_stream(init_state, **kwargs):
                        yield {"market_flow_report": "Market"}
                        yield {"macro_regime_report": "Macro should be hidden"}
                        yield {"trader_allocation_plan": "Trader"}

                    fake_graph.stream = fake_stream

                    events = list(runner.run_queue(["510300.SH"], selected_analysts=["market_flow"]))

                    self.assertEqual(events[0].total_sections, 6)
                    section_done = [e for e in events if isinstance(e, SectionDone)]
                    self.assertEqual([e.section_id for e in section_done], ["market_flow", "trader"])
                    self.assertEqual([e.total for e in section_done], [6, 6])

    def test_cancel_emits_cancelled_and_stops_processing(self):
        """request_cancel() must cause remaining tickers to yield TickerCancelled
        and must NOT call _make_graph/finalize_run/_save_report for them."""
        runner = AnalysisRunner()

        with patch.object(runner, "_make_graph") as mock_make_graph:
            with patch.object(runner, "_save_report") as mock_save_report:
                with patch.object(runner, "_extract_rating_from_report") as mock_rating:
                    fake_graph = _FakeGraph()
                    mock_make_graph.return_value = fake_graph
                    mock_save_report.return_value = Path("/fake/report.md")
                    mock_rating.return_value = "BUY"

                    def fake_stream(init_state, **kwargs):
                        yield {"market_flow_report": "Analysis"}

                    fake_graph.stream = fake_stream

                    def cancel_on_second():
                        """Cancel after first ticker."""
                        events = []
                        for event in runner.run_queue(["510300.SH", "159915.SZ"]):
                            events.append(event)
                            if isinstance(event, TickerDone):
                                runner.request_cancel()
                        return events

                    events = cancel_on_second()
                    self.assertTrue(any(isinstance(e, TickerCancelled) for e in events))

                    # _make_graph should only be called once (for the first ticker)
                    self.assertEqual(mock_make_graph.call_count, 1)
                    # _save_report should only be called once (for the first ticker)
                    self.assertEqual(mock_save_report.call_count, 1)

    def test_graph_close_run_always_called(self):
        """graph.close_run() must be called in a finally block."""
        runner = AnalysisRunner()

        with patch.object(runner, "_make_graph") as mock_make_graph:
            fake_graph = _FakeGraph()
            mock_make_graph.return_value = fake_graph

            # Simulate an error during stream
            def fake_stream_error(init_state, **kwargs):
                raise RuntimeError("Stream error")

            fake_graph.stream = fake_stream_error

            list(runner.run_queue(["510300.SH"]))

            # close_run() should have been called despite error
            self.assertTrue(fake_graph.closed)

    def test_error_yields_ticker_failed_and_continues_queue(self):
        """A graph exception for one ticker must yield TickerFailed and continue."""
        runner = AnalysisRunner()

        with patch.object(runner, "_make_graph") as mock_make_graph:
            fake_graph = _FakeGraph()
            mock_make_graph.return_value = fake_graph

            # First ticker fails, second succeeds
            call_count = [0]

            def fake_stream(init_state, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("First ticker error")
                yield {"market_flow_report": "Second ticker OK"}

            fake_graph.stream = fake_stream

            with patch.object(runner, "_save_report") as mock_save_report:
                with patch.object(runner, "_extract_rating_from_report") as mock_rating:
                    mock_save_report.return_value = Path("/fake/report.md")
                    mock_rating.return_value = None

                    events = list(runner.run_queue(["510300.SH", "159915.SZ"]))

                    # Both tickers should appear, one as failed, one as done
                    ticker_failed = [e for e in events if isinstance(e, TickerFailed)]
                    ticker_done = [e for e in events if isinstance(e, TickerDone)]
                    self.assertEqual(len(ticker_failed), 1)
                    self.assertEqual(len(ticker_done), 1)

    def test_section_detection_marks_completion(self):
        """Section updates in chunks must be detected and emitted."""
        runner = AnalysisRunner()

        with patch.object(runner, "_make_graph") as mock_make_graph:
            with patch.object(runner, "_save_report") as mock_save_report:
                with patch.object(runner, "_extract_rating_from_report") as mock_rating:
                    fake_graph = _FakeGraph()
                    mock_make_graph.return_value = fake_graph
                    mock_save_report.return_value = Path("/fake/report.md")
                    mock_rating.return_value = None

                    # Emit multiple section updates
                    def fake_stream(init_state, **kwargs):
                        yield {"market_flow_report": "Market"}
                        yield {"catalyst_sentiment_report": "Sentiment"}
                        yield {"macro_regime_report": "Macro"}

                    fake_graph.stream = fake_stream

                    events = list(runner.run_queue(["510300.SH"]))
                    section_done = [e for e in events if isinstance(e, SectionDone)]
                    self.assertEqual(len(section_done), 3)
                    self.assertEqual(
                        [e.section_id for e in section_done],
                        ["market_flow", "catalyst_sentiment", "macro_regime"],
                    )

    def test_research_debate_updates_before_manager_decision(self):
        """Research debate history should be visible before judge_decision lands."""
        runner = AnalysisRunner()
        emitted: dict[str, str] = {}
        runner._format_research = lambda debate: debate.get("bull_history", "")

        events = list(runner._detect_section_updates(
            {
                "investment_debate_state": {
                    "bull_history": "Bull view in progress",
                    "bear_history": "",
                    "judge_decision": "",
                }
            },
            {},
            emitted,
            "510300.SH",
        ))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].section_id, "research_debate")
        self.assertIn("Bull view", events[0].content)

    def test_research_section_can_update_after_first_debate_event(self):
        """Final manager content should replace earlier in-progress debate content."""
        runner = AnalysisRunner()
        emitted: dict[str, str] = {}
        runner._format_research = lambda debate: debate.get("bull_history", "")
        list(runner._detect_section_updates(
            {"investment_debate_state": {"bull_history": "Draft", "judge_decision": ""}},
            {},
            emitted,
            "510300.SH",
        ))

        events = list(runner._detect_section_updates(
            {"research_allocation_plan": "Final manager decision"},
            {},
            emitted,
            "510300.SH",
        ))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].section_id, "research")
        self.assertEqual(events[0].content, "Final manager decision")

    def test_section_done_carries_backtest_signal_when_available(self):
        """Structured investment signals should reach the TUI with section events."""
        runner = AnalysisRunner()
        emitted: dict[str, str] = {}
        signal = {
            "rating": "OVERWEIGHT",
            "target_weight_pct": 2.0,
        }

        events = list(runner._detect_section_updates(
            {"final_allocation_decision": "Final manager decision"},
            {"backtest_signal": signal},
            emitted,
            "510300.SH",
        ))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].section_id, "portfolio_manager")
        self.assertEqual(events[0].backtest_signal, signal)

    def test_section_done_backtest_signal_defaults_to_none(self):
        event = SectionDone(
            ticker="510300.SH",
            section_id="market_flow",
            content="report",
            completed=1,
            total=9,
        )

        self.assertIsNone(event.backtest_signal)


if __name__ == "__main__":
    unittest.main()
