import unittest
from unittest.mock import MagicMock

from etfagents.agents.utils.rating import parse_rating
from etfagents.graph.signal_processing import SignalProcessor


class ParseRatingTests(unittest.TestCase):
    def test_parses_explicit_english_labels(self):
        self.assertEqual(parse_rating("Rating: Buy\nReasoning here."), "BUY")
        self.assertEqual(parse_rating("**Rating**: Underweight\nTrim exposure."), "UNDERWEIGHT")

    def test_parses_explicit_chinese_labels(self):
        self.assertEqual(parse_rating("最终配置建议: **买入**"), "BUY")
        self.assertEqual(parse_rating("建议评级：减持"), "UNDERWEIGHT")

    def test_parses_structured_markdown_shape(self):
        text = (
            "## 辩论结论\n综合来看更适合控制仓位。\n\n"
            "## 持仓建议\n建议评级: 持有\n继续等待更强确认信号。"
        )
        self.assertEqual(parse_rating(text), "HOLD")

    def test_returns_default_when_no_rating_found(self):
        self.assertEqual(parse_rating("Plain prose without a recommendation."), "HOLD")
        self.assertEqual(parse_rating("后续继续跟踪盈利兑现与订单变化。", default="SELL"), "SELL")


class SignalProcessorTests(unittest.TestCase):
    def test_returns_rating_without_using_llm(self):
        llm = MagicMock()
        processor = SignalProcessor(llm)

        self.assertEqual(
            processor.process_signal("FINAL ALLOCATION PROPOSAL: **OVERWEIGHT**"),
            "OVERWEIGHT",
        )

        llm.invoke.assert_not_called()
        llm.with_structured_output.assert_not_called()


if __name__ == "__main__":
    unittest.main()
