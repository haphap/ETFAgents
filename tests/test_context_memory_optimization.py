import copy
import unittest

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.dataflows.config import get_config, set_config
from etfagents.agents.utils.agent_utils import (
    build_debate_brief,
    extract_analyst_decision_summary,
    extract_feedback_snapshot,
    get_snapshot_template,
    make_display_snapshot,
    normalize_chinese_numeric_expressions,
    normalize_chinese_role_terms,
    normalize_display_numbering,
    strip_analyst_decision_summary,
    strip_feedback_snapshot,
    truncate_for_prompt,
)


class ContextMemoryOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.original_config = copy.deepcopy(get_config())

    def tearDown(self):
        set_config(self.original_config)

    def test_truncate_for_prompt_uses_config_limit(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["report_context_char_limit"] = 10
        set_config(cfg)

        text = "abcdefghijklmnopqrstuvwxyz"
        truncated = truncate_for_prompt(text)

        self.assertIn("Content trimmed", truncated)
        self.assertTrue(truncated.endswith("qrstuvwxyz"))

    def test_normalize_display_numbering_keeps_chinese_headings(self):
        text = "一、核心观点\n② 跟踪订单\n③ 跟踪利润率"
        normalized = normalize_display_numbering(text)

        self.assertIn("一、核心观点", normalized)
        self.assertIn("2. 跟踪订单", normalized)
        self.assertIn("3. 跟踪利润率", normalized)

    def test_normalize_chinese_role_terms_translates_mixed_finance_terms(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        text = "Capex、Forward PE、quarterly earnings、scalability，以及全轮次交锋都需要统一。"
        normalized = normalize_chinese_role_terms(text)

        self.assertIn("资本开支", normalized)
        self.assertIn("前瞻市盈率", normalized)
        self.assertIn("单季度业绩", normalized)
        self.assertIn("规模扩张能力", normalized)
        self.assertIn("全轮次辩论", normalized)

    def test_normalize_chinese_role_terms_localizes_raw_indicator_keys(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        text = "close_10_ema、close_50_sma、boll_ub、boll_lb、macds、macdh、vwma 都需要转成可读标签。"
        normalized = normalize_chinese_role_terms(text)

        self.assertIn("10日EMA", normalized)
        self.assertIn("50日SMA", normalized)
        self.assertIn("布林带上轨", normalized)
        self.assertIn("布林带下轨", normalized)
        self.assertIn("MACD信号线", normalized)
        self.assertIn("MACD柱状图", normalized)
        self.assertIn("成交量加权移动平均线", normalized)
        self.assertNotIn("close_10_ema", normalized)

    def test_normalize_chinese_numeric_expressions_handles_approximate_values(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        text = "四百余万元合同负债、十余天账期、近三个月营收改善、约四百万元销售额。"
        normalized = normalize_chinese_numeric_expressions(text)

        self.assertEqual(normalized, text)

    def test_normalize_chinese_role_terms_does_not_corrupt_approximate_large_units(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        normalized = normalize_chinese_role_terms("公司仍有四百余万元合同负债。")

        self.assertIn("四百余万元合同负债", normalized)
        self.assertNotIn("余0元", normalized)
        self.assertNotIn("400余万元", normalized)

    def test_normalize_chinese_numeric_expressions_handles_composite_large_units(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        normalized = normalize_chinese_numeric_expressions("合同金额一亿零三万元，签约额约一亿零三万元。")

        self.assertEqual(normalized, "合同金额10003万元，签约额约一亿零三万元。")

    def test_normalize_chinese_numeric_expressions_rescales_large_arabic_currency_amounts(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        normalized = normalize_chinese_numeric_expressions(
            "公司拥有超300000000000元现金储备与充沛的经营现金流。"
        )

        self.assertEqual(normalized, "公司拥有超3000亿元现金储备与充沛的经营现金流。")

    def test_normalize_chinese_role_terms_normalizes_ticker_codes_and_dates(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        normalized = normalize_chinese_role_terms(
            "对三零零七五零点SZ（宁德时代）的判断转弱，观察区间为二〇二六年五月一日至二〇二六年六月三十日。"
        )

        self.assertIn("300750.SZ（宁德时代）", normalized)
        self.assertIn("2026年5月1日至2026年6月30日", normalized)

    def test_feedback_snapshot_helpers(self):
        response = (
            "Argument body here.\n\n"
            "FEEDBACK SNAPSHOT:\n"
            "- Current thesis: Bull case improved.\n"
            "- What changed: Margin outlook improved.\n"
            "- Why it changed: Earnings beat.\n"
            "- Key rebuttal: Bear margin fears are weaker.\n"
            "- Lesson for next round: Track valuation risk."
        )

        snapshot = extract_feedback_snapshot(response)
        body = strip_feedback_snapshot(response)
        brief = build_debate_brief(
            {
                "Bull Analyst": snapshot,
                "Bear Analyst": "FEEDBACK SNAPSHOT:\n- Current thesis: Bear case unchanged.",
            },
            latest_speaker="Bull Analyst",
        )

        self.assertIn("- Stance: Bull case improved.", snapshot)
        self.assertIn("- New this round & rebuttal:", snapshot)
        self.assertIn("Margin outlook improved.", snapshot)
        self.assertIn("Earnings beat.", snapshot)
        self.assertIn("Bear margin fears are weaker.", snapshot)
        self.assertEqual(body, "Argument body here.")
        self.assertIn("Latest update came from: Bull Analyst", brief)
        self.assertIn("Bull Analyst latest snapshot", brief)

    def test_build_debate_brief_localizes_summary_phrases_for_chinese(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        brief = build_debate_brief(
            {
                "Bull Analyst": "反馈快照:\n- 当前观点: 多头增强。",
                "Bear Analyst": "反馈快照:\n- 当前观点: 空头不变。",
            },
            latest_speaker="Bull Analyst",
        )

        self.assertIn("最新更新来自: 多头分析师", brief)
        self.assertIn("多头分析师 最新快照", brief)

    def test_feedback_snapshot_helpers_support_chinese_template(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        self.assertIn("反馈快照", get_snapshot_template())

        response = (
            "论证正文。\n\n"
            "反馈快照:\n"
            "- 当前观点: 多头逻辑增强。\n"
            "- 发生了什么变化: 利润率预期改善。\n"
            "- 为什么变化: 财报超预期。\n"
            "- 关键反驳: 空头对利润率的担忧减弱。\n"
            "- 下一轮教训: 继续跟踪估值风险。"
        )

        snapshot = extract_feedback_snapshot(response)
        body = strip_feedback_snapshot(response)

        self.assertIn("- 立场: 多头逻辑增强。", snapshot)
        self.assertIn("- 本轮新增与反驳:", snapshot)
        self.assertIn("利润率预期改善", snapshot)
        self.assertIn("财报超预期", snapshot)
        self.assertIn("空头对利润率的担忧减弱", snapshot)
        self.assertEqual(body, "论证正文。")

    def test_analyst_decision_summary_helpers_strip_markdown_block(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。\n\n"
            "决策摘要:\n"
            "- 评级: 增持\n"
            "- 置信度: 80%\n"
            "- 时间区间: 6-12个月\n"
            "- 关键假设:\n"
            "  1. AI需求持续。\n"
            "  2. 公司维持份额。\n"
            "  3. 供应链无重大扰动。\n\n"
            "反馈快照:\n"
            "- 当前观点: 增持。\n"
            "- 发生了什么变化: 新增需求验证。\n"
            "- 为什么变化: 景气度上升。\n"
            "- 关键反驳: 空头低估需求。\n"
            "- 下一轮教训: 跟踪订单。"
        )

        summary = extract_analyst_decision_summary(response)
        body = strip_analyst_decision_summary(strip_feedback_snapshot(response))

        self.assertIn("决策摘要:", summary)
        self.assertIn("- 评级: 增持", summary)
        self.assertIn("- 置信度: 80%", summary)
        self.assertEqual(body, "论证正文。")

    def test_analyst_decision_summary_normalizes_legacy_xml(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。\n\n"
            "**Reflections from similar situations and lessons learned:**\n"
            "Do not show this.\n\n"
            "```xml\n"
            "<final_answer>\n"
            "<conclusion>增持</conclusion>\n"
            "<confidence_level>80%</confidence_level>\n"
            "<time_horizon>6-12 months</time_horizon>\n"
            "<key_assumptions>\n"
            "1. AI需求持续\n"
            "2. 份额稳定\n"
            "3. 无重大扰动\n"
            "</key_assumptions>\n"
            "</final_answer>\n"
            "```\n"
        )

        summary = extract_analyst_decision_summary(response)
        body = strip_analyst_decision_summary(response)

        self.assertIn("决策摘要:", summary)
        self.assertIn("- 评级: 增持", summary)
        self.assertIn("- 置信度: 80%", summary)
        self.assertNotIn("Reflections from similar situations", body)
        self.assertNotIn("<final_answer>", body)

    def test_analyst_decision_summary_aligns_risk_rating_and_numeric_format(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。\n\n"
            "风险建议: **设止损后持有**\n\n"
            "决策摘要:\n"
            "- 评级: 强烈看多并坚定持有\n"
            "- 置信度: 百分之七十五\n"
            "- 时间区间: 未来一至三个月\n"
            "- 关键假设:\n"
            "  1. 股价重新站上五十日均线上方。\n"
            "  2. 港股融资规模控制在三十亿美元以内。\n"
        )

        summary = extract_analyst_decision_summary(response)

        self.assertIn("- 评级: 持有", summary)
        self.assertNotIn("强烈看多并坚定持有", summary)
        self.assertIn("- 置信度: 75%", summary)
        self.assertIn("- 时间区间: 未来1—3个月", summary)
        self.assertIn("50日均线上方", summary)
        self.assertIn("30亿美元以内", summary)

    def test_normalize_chinese_role_terms_converts_precise_numeric_expressions(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        normalized = normalize_chinese_role_terms(
            "平均真实波幅升至三十三点一五元，股价高于五十日均线，"
            "估值偏离幅度在百分之四十以上，观察周期为未来一至三个月。"
        )

        self.assertIn("33.15元", normalized)
        self.assertIn("50日均线", normalized)
        self.assertIn("40%以上", normalized)
        self.assertIn("1—3个月", normalized)

    def test_risk_recommendation_with_hedge_language_normalizes_to_underweight(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。\n\n"
            "风险建议: **分批调整，保留底仓动态对冲**\n\n"
            "决策摘要:\n"
            "- 评级: 持有\n"
            "- 置信度: 70%\n"
            "- 时间区间: 未来一至三个月\n"
            "- 关键假设:\n"
            "  1. 波动率仍偏高。\n"
            "  2. 价格结构尚未完全修复。\n"
        )

        normalized = normalize_chinese_role_terms(response)
        summary = extract_analyst_decision_summary(normalized)

        self.assertIn("风险建议: **分批减仓，控制回撤**", normalized)
        self.assertIn("- 评级: 减持", summary)
        self.assertNotIn("- 评级: 持有", summary)

    def test_feedback_snapshot_infers_substantive_chinese_content_when_placeholder_block_is_used(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。本轮新增了对库存风险的反驳，并强调需要继续跟踪金价与并购进度。\n\n"
            "反馈快照:\n"
            "- 当前观点: 暂无。\n"
            "- 发生了什么变化: 未明确说明。\n"
            "- 为什么变化: 未明确说明。\n"
            "- 关键反驳: 未明确说明。\n"
            "- 下一轮教训: 未明确说明。"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertNotIn("未明确说明", snapshot)
        self.assertNotIn("暂无", snapshot)
        self.assertIn("- 立场: 持有", snapshot)
        self.assertIn("库存与备货压力", snapshot)
        self.assertIn("金价走势", snapshot)
        self.assertIn("并购进度", snapshot)
        self.assertNotIn("本轮新增了对库存风险的反驳", snapshot)

    def test_feedback_snapshot_fills_empty_fields_with_inferred_content(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "论证正文。本轮转向更谨慎，核心原因是估值偏高且需要继续跟踪成交量是否萎缩。\n\n"
            "反馈快照:\n"
            "- 当前观点:\n"
            "- 发生了什么变化:\n"
            "- 为什么变化: 估值偏高。\n"
            "- 关键反驳:\n"
            "- 下一轮教训:"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("- 立场: 持有", snapshot)
        self.assertIn("- 本轮新增与反驳:", snapshot)
        self.assertIn("高估值消化能力", snapshot)
        self.assertIn("- 待验证:", snapshot)
        self.assertNotIn("- 立场: \n", snapshot)
        self.assertNotIn("- 本轮新增与反驳: \n", snapshot)

    def test_feedback_snapshot_detects_explicit_chinese_rating_terms(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "我们维持减持观点，建议分批止盈，等待更好的风险收益比。\n\n"
            "反馈快照:\n"
            "- 当前观点:\n"
            "- 发生了什么变化:\n"
            "- 为什么变化:\n"
            "- 关键反驳:\n"
            "- 下一轮教训:"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("- 立场: 减持", snapshot)

    def test_feedback_snapshot_ignores_negated_buy_language(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "当前不建议买入，应该继续观察，等待更明确的基本面确认。\n\n"
            "反馈快照:\n"
            "- 当前观点:\n"
            "- 发生了什么变化:\n"
            "- 为什么变化:\n"
            "- 关键反驳:\n"
            "- 下一轮教训:"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("- 立场: 持有", snapshot)
        self.assertNotIn("- 立场: 买入", snapshot)

    def test_feedback_snapshot_ignores_negated_english_buy_language(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "English"
        set_config(cfg)

        response = (
            "We do not recommend buy here and prefer to wait for clearer confirmation.\n\n"
            "FEEDBACK SNAPSHOT:\n"
            "- Current thesis:\n"
            "- What changed:\n"
            "- Why it changed:\n"
            "- Key rebuttal:\n"
            "- Lesson for next round:"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("- Stance: HOLD", snapshot)
        self.assertNotIn("- Stance: BUY", snapshot)

    def test_feedback_snapshot_rewrites_copied_body_fields(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "激进分析师: 各位，我们必须直面这个市场的狂热与理性之间的巨大裂痕。"
            "保守派和中性分析师建议我们持有观望，理由是高估值、库存压力和技术面未反转。"
            "但这些存货更像是为AI需求爆发准备的战略备货，而不是简单的减值风险。"
            "153-160元区间已经形成底部结构，下一轮还要继续跟踪1.6T良率、订单兑现和量能变化。\n\n"
            "反馈快照:\n"
            "- 立场: 激进加仓。\n"
            "- 本轮新增: 激进分析师: 各位，我们必须直面这个市场的狂热与理性之间的巨大裂痕。保守派和中性分析师建议我们持有观望，理由是高估值、库存压力和技术面未反转。\n"
            "- 关键反驳: 但这些存货更像是为AI需求爆发准备的战略备货，而不是简单的减值风险。\n"
            "- 待验证: 153-160元区间已经形成底部结构，下一轮还要继续跟踪1.6T良率、订单兑现和量能变化。"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertNotIn("各位，我们必须直面", snapshot)
        self.assertIn("库存与备货压力", snapshot)
        self.assertIn("需求与订单兑现", snapshot)
        self.assertIn("1.6T良率爬坡", snapshot)

    def test_feedback_snapshot_rewrites_duplicate_fields_and_generic_to_verify(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "多头分析师: 空头分析师将估值与地缘政治风险直接推导为脆弱性，但宁德时代在价格战最激烈阶段仍实现净利润增长42.29%，"
            "说明盈利韧性和定价权没有被破坏。下一轮需要继续跟踪一季报增速、400元阻力位突破情况以及储能订单兑现节奏。\n\n"
            "反馈快照:\n"
            "- 立场: 买入——盈利韧性仍强。\n"
            "- 本轮新增: 空头分析师，我理解你对宁德时代当前估值和地缘政治风险的担忧，但你的分析框架忽略了这家企业最核心的护城河——在行业价格战最惨烈的2025年，宁德时代净利润逆势增长42.29%，这恰恰证明了其定价权而非脆弱性。让我用数据重新审视这笔投资的价值。\n"
            "- 关键反驳: 空头分析师，我理解你对宁德时代当前估值和地缘政治风险的担忧，但你的分析框架忽略了这家企业最核心的护城河——在行业价格战最惨烈的2025年，宁德时代净利润逆势增长42.29%，这恰恰证明了其定价权而非脆弱性。让我用数据重新审视这笔投资的价值。\n"
            "- 待验证: **投资决策的理性框架** 当前时点，宁德时代处于趋势向上但动能收敛的临界状态。"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertNotIn("投资决策的理性框架", snapshot)
        self.assertNotIn("我理解你对宁德时代当前估值和地缘政治风险的担忧", snapshot)
        self.assertIn("- 本轮新增与反驳:", snapshot)
        self.assertIn("并据此反驳对手", snapshot)
        self.assertIn("- 待验证: 下一轮继续跟踪", snapshot)

    def test_make_display_snapshot_uses_clean_clause_instead_of_raw_truncation(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        snapshot = (
            "反馈快照:\n"
            "- 立场: 激进加仓——AI需求与订单兑现仍在强化。\n"
            "- 本轮新增: 各位，我们必须直面这个市场的狂热与理性之间的巨大裂痕。库存与备货压力其实对应订单前置准备。\n"
            "- 关键反驳: 首先，对手把高估值直接等同于泡沫，但忽略了订单兑现节奏。\n"
            "- 待验证: 再看技术面，继续跟踪1.6T良率、订单兑现和量能变化。"
        )

        display = make_display_snapshot(snapshot, "/tmp/snapshot.md")

        self.assertNotIn("各位，我们必须直面", display)
        self.assertNotIn("首先，对手", display)
        self.assertNotIn("再看技术面", display)
        self.assertNotIn("...", display)
        self.assertIn("库存与备货压力其实对应订单前置准备", display)
        self.assertIn("对手把高估值直接等同于泡沫，但忽略了订单兑现节奏", display)
        self.assertIn("继续跟踪1.6T良率、订单兑现和量能变化", display)
        self.assertNotIn("(完整内容见:", display)

    def test_feedback_snapshot_rewrites_quantitatively_overlapping_rebuttal(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "多头分析师: 我本轮首次引入订单锁定率概念，指出2041亿合同负债对945亿存货形成216%的覆盖，"
            "说明库存并非被动堆积，而是已有订单锁定的交付准备。空头分析师则认为合同负债与存货性质不同，"
            "预收款高并不等于库存安全，但这种线性推断忽略了交付节奏和产能兑现之间的匹配关系。"
            "下一轮继续跟踪存货周转天数是否守住97天，以及储能订单的兑现速度。\n\n"
            "反馈快照:\n"
            "- 立场: 买入/增持——库存质量优于市场担忧。\n"
            "- 本轮新增: 首次引入“订单锁定率”概念（合同负债/存货=216%），指出该比率超100%意味着库存已有在手订单覆盖，库存更像交付准备而非滞销积压。\n"
            "- 关键反驳: [空头分析师]本轮提出2041亿合同负债与945亿存货性质不同、预收款多不等于库存安全，但同一组216%覆盖数据恰恰说明库存与订单绑定程度高，因此其风险外推过度。\n"
            "- 待验证: ①存货周转天数能否守住97天——若连续两季度突破100天则确认去库存压力；②储能订单兑现节奏。"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("订单锁定率", snapshot)
        self.assertIn("- 本轮新增与反驳:", snapshot)
        self.assertIn("风险外推过度", snapshot)

    def test_feedback_snapshot_prefers_risk_recommendation_for_risk_debate_body(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["output_language"] = "Chinese"
        set_config(cfg)

        response = (
            "保守分析师: 各位，作为保守风险分析师，我必须再次强调高估值和库存风险。\n"
            "激进分析师主张增持，但我认为当前风险收益比不支持继续冒进。\n"
            "再看技术面，股价仍在50日均线下方，需继续观察支撑位。\n\n"
            "风险建议: **设止损后持有**"
        )

        snapshot = extract_feedback_snapshot(response)

        self.assertIn("- 立场: 维持现仓，等待确认信号", snapshot)
        self.assertNotIn("- 立场: 增持", snapshot)


if __name__ == "__main__":
    unittest.main()
