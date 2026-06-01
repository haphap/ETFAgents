"""Regression tests for the ``memory.append_analysis`` bridge handler.

Proves that a non-default runtime config (forwarded by the TS Memory Writer
node) reaches ``AnalysisMemoryStore`` instead of being silently replaced by
``DEFAULT_CONFIG``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from etfagents.bridge.handlers.memory import memory_append_analysis


_STATE = {"asset_of_interest": "510300.SH", "trade_date": "2026-05-29"}


class MemoryAppendAnalysisConfigTests(unittest.TestCase):
    def test_runtime_results_dir_is_honoured(self) -> None:
        """A custom results_dir in the passed config must drive where memory is stored."""
        with tempfile.TemporaryDirectory() as tmp:
            result = memory_append_analysis(
                {
                    "state": _STATE,
                    "config": {"results_dir": tmp, "memory_mode": "full"},
                }
            )
            self.assertTrue(result["written"])
            memory_dir = Path(tmp) / "memory"
            # The entry must land under the runtime results_dir, not DEFAULT_CONFIG's.
            self.assertTrue(memory_dir.exists())
            self.assertTrue(any(memory_dir.rglob("*")))

    def test_runtime_memory_mode_disabled_is_honoured(self) -> None:
        """memory_mode=disabled in the passed config must short-circuit the write."""
        with tempfile.TemporaryDirectory() as tmp:
            result = memory_append_analysis(
                {
                    "state": _STATE,
                    "config": {"results_dir": tmp, "memory_mode": "disabled"},
                }
            )
            self.assertFalse(result["written"])
            self.assertEqual(result["entry"], {})
            self.assertFalse((Path(tmp) / "memory").exists())


if __name__ == "__main__":
    unittest.main()
