import io
import sys
import unittest
from contextlib import redirect_stdout

from cli.commands.tui import tui


class LegacyTuiCommandTests(unittest.TestCase):
    def test_tui_command_prints_migration_notice_without_loading_textual_app(self):
        had_textual_app = "cli.tui.app" in sys.modules
        out = io.StringIO()

        with redirect_stdout(out):
            tui()

        text = out.getvalue()
        self.assertIn("Python Textual TUI is deprecated", text)
        self.assertIn("pnpm dev tui", text)
        self.assertEqual("cli.tui.app" in sys.modules, had_textual_app)


if __name__ == "__main__":
    unittest.main()
