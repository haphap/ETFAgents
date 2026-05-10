"""Tests for ETF market report quality validation functions."""

import unittest

from etfagents.agents.analysts.etf_market_analyst import (
    _etf_report_has_full_coverage,
    _etf_report_has_actionable_intro,
    _etf_report_has_actionable_depth,
    _etf_market_report_needs_rewrite,
)


class TestFullCoverage(unittest.TestCase):
    def test_full_report_passes(self):
        report = (
            "Trend: 50 SMA at 450, 200 SMA at 430, 10 EMA crossing above 20 SMA. "
            "MACD signal bullish with histogram expanding. RSI at 58, not overbought. "
            "Bollinger bands widening, price near upper band. VWMA confirms volume "
            "expansion on breakout days."
        )
        self.assertTrue(_etf_report_has_full_coverage(report))

    def test_missing_macd_fails(self):
        report = (
            "50 SMA at 450, 200 SMA at 430, 10 EMA trending up. "
            "RSI at 58. Bollinger bands widening. VWMA elevated."
        )
        self.assertFalse(_etf_report_has_full_coverage(report))

    def test_missing_rsi_fails(self):
        report = (
            "SMA and EMA trending up. MACD bullish. "
            "Bollinger bands widening. VWMA confirms."
        )
        self.assertFalse(_etf_report_has_full_coverage(report))

    def test_missing_boll_fails(self):
        report = (
            "SMA and EMA trending up. MACD bullish. RSI at 55. VWMA confirms."
        )
        self.assertFalse(_etf_report_has_full_coverage(report))


class TestActionableIntro(unittest.TestCase):
    def test_bullish_intro_passes(self):
        report = "偏多格局，50日均线支撑有效，MACD金叉确认。\n后续内容..."
        self.assertTrue(_etf_report_has_actionable_intro(report))

    def test_english_bullish_intro_passes(self):
        report = "Bullish setup with strong support at the 50 SMA.\nMore details..."
        self.assertTrue(_etf_report_has_actionable_intro(report))

    def test_boilerplate_intro_fails(self):
        report = "本报告将分析ETF技术面指标。\n具体内容如下..."
        self.assertFalse(_etf_report_has_actionable_intro(report))

    def test_english_boilerplate_fails(self):
        report = "Structured breakdown of the ETF technical indicators.\nDetails..."
        self.assertFalse(_etf_report_has_actionable_intro(report))

    def test_empty_report_fails(self):
        self.assertFalse(_etf_report_has_actionable_intro(""))


class TestActionableDepth(unittest.TestCase):
    def test_deep_report_passes(self):
        report = "A" * 500  # meets length
        report += "价格高于50日均线支撑位，若跌破则减仓。RSI超买区域死叉风险。"
        self.assertTrue(_etf_report_has_actionable_depth(report))

    def test_short_report_fails(self):
        report = "偏多，MACD金叉。" * 10  # under 400 chars
        self.assertFalse(_etf_report_has_actionable_depth(report))

    def test_length_ok_but_no_depth_keywords_fails(self):
        report = "x" * 500
        self.assertFalse(_etf_report_has_actionable_depth(report))


class TestNeedsRewrite(unittest.TestCase):
    def test_empty_needs_rewrite(self):
        self.assertTrue(_etf_market_report_needs_rewrite(""))

    def test_good_report_no_rewrite(self):
        # Build a report that passes all three checks:
        # 1. Full coverage (sma/ema, macd, rsi, boll, vwma)
        # 2. Actionable intro (starts with a directional term)
        # 3. Actionable depth (>=400 chars, >=3 keyword groups)
        report = (
            "偏多格局确认，价格站稳50日均线上方，短期均线呈多头排列，50日SMA位于445元提供中期支撑。"  # intro + sma
            + "10 EMA金叉20日均线，当前位于452元，MACD信号线看涨，柱状图持续扩张，DIF与DEA差值扩大至1.2，快慢线均位于零轴上方。"  # ema + macd
            + "RSI位于58，尚未超买，距离超买区域70仍有较大空间，中期动能偏强，未出现顶背离信号，动量维持正面。"  # rsi
            + "布林带开口扩大，价格运行于中轨448与上轨462之间，中轨提供动态支撑，带宽扩张表明波动率上升，价格贴近上轨运行。"  # boll
            + "成交量加权移动平均线（VWMA）确认放量突破有效，近5日成交量达到20日均量的1.4倍，资金持续流入，换手率维持在合理水平。"  # vwma
            + "若价格回踩448-450支撑区间不破则可加仓，若跌破440则止损减仓，上方第一阻力位462元，第二阻力位470元。"  # depth: if/then + support
            + "当前超买信号尚未触发，但需关注RSI死叉风险，若RSI下穿50则考虑减仓，MACD死叉为次要风控信号。建议维持偏多配置。"  # depth: overbought + crossover
        )
        self.assertFalse(_etf_market_report_needs_rewrite(report))

    def test_missing_coverage_needs_rewrite(self):
        report = "偏多格局。" + "MACD bullish. RSI ok. " * 30
        self.assertTrue(_etf_market_report_needs_rewrite(report))


if __name__ == "__main__":
    unittest.main()
