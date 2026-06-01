"""Regression tests for the ``memory.append_analysis`` bridge handler.

Proves that a non-default runtime config (forwarded by the TS Memory Writer
node) reaches ``AnalysisMemoryStore`` instead of being silently replaced by
``DEFAULT_CONFIG``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from etfagents.bridge.handlers.memory import _DEFAULT_ANALYSTS, memory_append_analysis


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

    def test_empty_selected_analysts_is_preserved_not_defaulted(self) -> None:
        """An explicit empty selected_analysts must NOT be coerced to the full default.

        The config hash is derived from selected_analysts, so coercing [] to the
        full set would make the stored entry disagree with what the graph ran.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"results_dir": tmp, "memory_mode": "full"}
            empty = memory_append_analysis(
                {"state": _STATE, "selected_analysts": [], "config": cfg}
            )
            full = memory_append_analysis(
                {
                    "state": _STATE,
                    "selected_analysts": list(_DEFAULT_ANALYSTS),
                    "config": cfg,
                }
            )
            self.assertTrue(empty["written"])
            self.assertTrue(full["written"])
            # Distinct selections must yield distinct config hashes.
            self.assertNotEqual(empty["entry"]["config_hash"], full["entry"]["config_hash"])


if __name__ == "__main__":
    unittest.main()
