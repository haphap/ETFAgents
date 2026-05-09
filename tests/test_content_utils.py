import unittest

from etfagents.content_utils import extract_text_content


class _TextBlock:
    def __init__(self, text, block_type="text"):
        self.type = block_type
        self.text = text


class ContentUtilsTests(unittest.TestCase):
    def test_extract_text_content_ignores_reasoning_blocks(self):
        content = [
            {"type": "reasoning", "text": "internal"},
            {"type": "text", "text": "Market report"},
            {"type": "output_text", "text": "Fundamentals report"},
        ]

        self.assertEqual(
            extract_text_content(content),
            "Market report\nFundamentals report",
        )

    def test_extract_text_content_supports_object_blocks(self):
        content = [_TextBlock("Market report"), _TextBlock("ignored", "reasoning")]

        self.assertEqual(extract_text_content(content), "Market report")

    def test_extract_text_content_supports_nested_content(self):
        content = {
            "type": "message",
            "content": [{"type": "text", "text": "Nested report"}],
        }

        self.assertEqual(extract_text_content(content), "Nested report")


if __name__ == "__main__":
    unittest.main()
