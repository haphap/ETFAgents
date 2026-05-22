"""Placeholder tests for AnalysisRunner contracts (M2).

These tests pin the acceptance criteria for the runner that will be
implemented in M2.  They are skipped until the runner lands.
"""

import unittest


@unittest.skip("M2: AnalysisRunner not yet implemented")
class AnalysisRunnerContractTests(unittest.TestCase):
    def test_stream_emits_ticker_started_then_section_done_then_ticker_done(self):
        """Runner must yield TickerStarted → SectionDone × N → TickerDone
        for each ticker in the queue."""

    def test_cancel_emits_cancelled_and_stops_processing(self):
        """request_cancel() must cause remaining tickers to yield
        TickerCancelled without calling finalize_run() or saving reports."""

    def test_cancel_leaves_no_temp_files(self):
        """If cancelled mid-stream, no .tmp section files should remain
        in the report directory.  Atomic write or cleanup on cancel."""

    def test_error_yields_ticker_failed_and_continues_queue(self):
        """A graph exception for one ticker must yield TickerFailed(error=...)
        and continue processing the remaining tickers."""

    def test_graph_close_run_always_called(self):
        """graph.close_run() must be called in a finally block regardless
        of success, failure, or cancellation."""

    def test_report_persisted_after_ticker_done(self):
        """After TickerDone, the complete_report.md and section files
        must exist on disk at the expected paths."""


if __name__ == "__main__":
    unittest.main()
