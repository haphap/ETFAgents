
import importlib.util
import unittest
if not importlib.util.find_spec("questionary"):
    raise unittest.SkipTest("questionary not installed")

import unittest

from cli.utils import normalize_ticker_symbol
from etfagents.agents.utils.agent_utils import build_instrument_context

class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)
        self.assertIn("Never spell ticker digits in Chinese", context)

if __name__ == "__main__":
    unittest.main()
