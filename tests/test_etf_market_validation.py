"""Tests for ETF market report quality validation functions."""

import unittest

from etfagents.agents.analysts.etf_market_analyst import (
    _etf_report_has_full_coverage,
    _etf_report_has_actionable_intro,
    _etf_report_has_actionable_depth,
    _etf_report_has_explanatory_clarity,
    _etf_report_has_compact_structure,
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

    def test_title_then_actionable_lead_passes(self):
        report = "# ETF市场与资金流分析报告\n\n偏多格局，50日均线支撑有效，MACD金叉确认。\n后续内容..."
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


class TestExplanatoryClarity(unittest.TestCase):
    def test_explained_jargon_passes(self):
        report = (
            "多头排列意味着短中期均线同时向上，说明买盘在不同持有周期都占优。"
            "对交易而言，这更适合持有或等回踩加仓，而不是在急拉后盲目追高。"
            "MACD金叉说明短期动能重新强于中期趋势，这意味着上行动能恢复。"
            "操作上若量能继续放大可顺势加仓，若放量失败则等待下一次确认。"
        )
        self.assertTrue(_etf_report_has_explanatory_clarity(report))

    def test_unexplained_jargon_fails(self):
        report = "标准多头发散形态，趋势完好，放量突破，MACD金叉，建议关注。"
        self.assertFalse(_etf_report_has_explanatory_clarity(report))


class TestCompactStructure(unittest.TestCase):
    def test_exact_three_section_structure_passes(self):
        report = (
            "# ETF市场与资金流分析报告\n\n"
            "偏多格局，量价配合尚未破坏。\n\n"
            "## 一、市场结构与量价诊断\n\n"
            "### （一）趋势与动量\n\n"
            "内容\n\n"
            "### （二）波动与流动性\n\n"
            "内容\n\n"
            "## 二、交易确认与执行计划\n\n"
            "内容\n\n"
            "## 三、关键价位与条件情景推演\n\n"
            "内容"
        )
        self.assertTrue(_etf_report_has_compact_structure(report))

    def test_old_three_section_structure_fails(self):
        report = (
            "# ETF市场与资金流分析报告\n\n"
            "## 一、趋势与动量\n\n"
            "内容\n\n"
            "## 二、波动与流动性\n\n"
            "内容\n\n"
            "## 三、信号确认与决策\n\n"
            "内容"
        )
        self.assertFalse(_etf_report_has_compact_structure(report))


class TestNeedsRewrite(unittest.TestCase):
    def test_empty_needs_rewrite(self):
        self.assertTrue(_etf_market_report_needs_rewrite(""))

    def test_good_report_no_rewrite(self):
        # Build a report that passes all three checks:
        # 1. Full coverage (sma/ema, macd, rsi, boll, vwma)
        # 2. Actionable intro (starts with a directional term)
        # 3. Actionable depth (>=400 chars, >=3 keyword groups)
        # 4. Explanatory clarity (explains jargon and links to trading meaning)
        report = (
            "# ETF市场与资金流分析报告\n\n"
            "偏多格局确认，价格站稳50日均线上方，短期均线呈多头排列，这意味着不同持有周期的买盘都在同步占优；"
            "对交易而言，更适合顺势持有并等待回踩确认，而不是在急拉后盲目追高。"
            + "\n\n## 一、市场结构与量价诊断\n\n"
            + "趋势与动量、波动与流动性都指向量价仍在同向确认。"
            + "\n\n### （一）趋势与动量\n\n"
            + "10 EMA金叉20日均线，当前位于452元，MACD信号线看涨，柱状图持续扩张，DIF与DEA差值扩大至1.2，快慢线均位于零轴上方，这说明短线动能正在重新强化。"  # ema + macd
            + "对交易而言，若后续量能不掉队，可继续按趋势思路持有；若动能先行钝化，则应收缩仓位等待下一次入场点。"  # clarity + trading meaning
            + "RSI位于58，尚未超买，距离超买区域70仍有较大空间，中期动能偏强，未出现顶背离信号，动量维持正面。"  # rsi
            + "\n\n### （二）波动与流动性\n\n"
            + "布林带开口扩大，价格运行于中轨448与上轨462之间，中轨提供动态支撑，带宽扩张表明波动率上升，价格贴近上轨运行。"  # boll
            + "成交量加权移动平均线（VWMA）确认放量突破有效，近5日成交量达到20日均量的1.4倍，资金持续流入，换手率维持在合理水平。"  # vwma
            + "\n\n## 二、交易确认与执行计划\n\n"
            + "当前确认信号仍强于风险信号，执行上以回踩确认和条件化风控为主。"
            + "若价格回踩448-450支撑区间不破则可加仓，若跌破440则止损减仓，上方第一阻力位462元，第二阻力位470元。"  # depth: if/then + support
            + "当前超买信号尚未触发，但需关注RSI死叉风险，若RSI下穿50则考虑减仓，MACD死叉为次要风控信号。建议维持偏多配置。"  # depth: overbought + crossover
            + "\n\n## 三、关键价位与条件情景推演\n\n"
            + "448-450元是本轮结构的第一支撑带，因为这里同时对应20日均线与近阶段成交密集区，若回踩后成交量没有明显失速、VWMA继续抬升，基准情景仍是震荡消化后上攻462-470元阻力带，这意味着趋势资金仍在承接，操作上可以继续持有并等待回踩加仓。"
            + "反之，若价格放量跌破448元并进一步失守440元，同时MACD柱状图收缩、RSI回落至50下方，则应把情景切换为结构转弱，优先减仓而非继续追随原有偏多判断。"
        )
        self.assertFalse(_etf_market_report_needs_rewrite(report))

    def test_missing_coverage_needs_rewrite(self):
        report = "偏多格局。" + "MACD bullish. RSI ok. " * 30
        self.assertTrue(_etf_market_report_needs_rewrite(report))


if __name__ == "__main__":
    unittest.main()
