"""Unit tests for the refactored analyst report validate / refine pipeline."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from etfagents.agents.utils.report_leads import (
    clean_generated_report,
    contains_meta_openers,
    contains_qa_label_artifacts,
    contains_self_referential_meta_leads,
    post_judge_clean,
    pre_judge_clean,
    strip_standalone_term_definition_blocks,
)
from etfagents.agents.utils.validate_refine import (
    AnalystReportSpec,
    JudgeVerdict,
    StaticVerdict,
    _merge_verdicts,
    _parse_judge_json,
    static_validate,
    validate_and_refine,
)


_MARKET_SPEC = AnalystReportSpec(
    analyst_name="market_flow",
    required_top_sections=("一", "二", "三"),
    required_indicator_tokens=("MACD", "RSI"),
    custom_rules_markdown="### 内容覆盖\n- 必须覆盖资金流。\n",
)


_GOOD_MARKET_REPORT = (
    "整体偏多，资金流支撑回升。\n\n"
    "一、市场结构与量价诊断\n"
    "二级章节略：MACD 维持金叉，RSI 处于 60 附近。\n\n"
    "二、交易确认与执行计划\n"
    "回踩 50 日均线确认后加仓。\n\n"
    "三、关键价位与条件情景推演\n"
    "失守 2.05 元则下调评级。\n"
)


class StaticValidateTests(unittest.TestCase):
    def test_clean_market_report_passes_static(self):
        verdict = static_validate(_GOOD_MARKET_REPORT, _MARKET_SPEC)
        self.assertFalse(verdict.has_issues, msg=verdict)

    def test_missing_top_section_recorded(self):
        report = (
            "整体偏多。\n\n"
            "一、市场结构与量价诊断\n"
            "MACD 金叉，RSI 60。\n\n"
            "二、交易确认与执行计划\n"
            "正常加仓。\n"
        )
        verdict = static_validate(report, _MARKET_SPEC)
        self.assertTrue(verdict.has_issues)
        self.assertTrue(any("三" in item for item in verdict.missing_elements))

    def test_missing_indicator_recorded(self):
        report = (
            "整体偏多。\n\n"
            "一、市场结构与量价诊断\n"
            "均线维持向上。\n\n"
            "二、交易确认与执行计划\n"
            "正常加仓。\n\n"
            "三、关键价位与条件情景推演\n"
            "失守 2.05 元则下调评级。\n"
        )
        verdict = static_validate(report, _MARKET_SPEC)
        self.assertTrue(any("MACD" in item for item in verdict.missing_elements))
        self.assertTrue(any("RSI" in item for item in verdict.missing_elements))

    def test_qa_label_and_meta_lead_detected(self):
        report = (
            "整体偏多。\n\n"
            "一、市场结构与量价诊断\n"
            "MACD 金叉，RSI 60。\n\n"
            "本节核心结论指出趋势仍未走坏。\n\n"
            "判断：偏多。\n\n"
            "二、交易确认与执行计划\n"
            "正常加仓。\n\n"
            "三、关键价位与条件情景推演\n"
            "失守 2.05 元则下调评级。\n"
        )
        verdict = static_validate(report, _MARKET_SPEC)
        self.assertTrue(any("自指式" in item for item in verdict.critical_issues))
        self.assertTrue(any("标签式结构" in item for item in verdict.critical_issues))

    def test_markdown_h1_h2_recorded(self):
        report = (
            "# 技术面诊断\n\n"
            "## 子标题\n\n"
            "一、市场结构与量价诊断\n"
            "MACD 金叉，RSI 60。\n\n"
            "二、交易确认与执行计划\n"
            "三、关键价位与条件情景推演\n"
        )
        verdict = static_validate(report, _MARKET_SPEC)
        self.assertTrue(any("H1" in item for item in verdict.critical_issues))
        self.assertTrue(any("##" in item for item in verdict.critical_issues))

    def test_required_tail_token_search_uses_window(self):
        spec = AnalystReportSpec(
            analyst_name="t",
            required_tail_tokens=("研报总览",),
        )
        early_only = "研报总览\n" + "正文段落。" * 400  # > 1500 chars total
        verdict = static_validate(early_only, spec)
        self.assertTrue(any("研报总览" in item for item in verdict.missing_elements))

        ending_present = ("正文段落。" * 400) + "\n研报总览\n"
        verdict_ok = static_validate(ending_present, spec)
        self.assertFalse(
            any("研报总览" in item for item in verdict_ok.missing_elements),
            msg=verdict_ok.missing_elements,
        )


class ParseJudgeJsonTests(unittest.TestCase):
    def test_strict_passed_payload_parsed(self):
        text = '{"score": 9, "passed": true, "critical_issues": [], "missing_elements": []}'
        verdict = _parse_judge_json(text)
        self.assertIsNotNone(verdict)
        self.assertEqual(9, verdict.score)
        self.assertTrue(verdict.passed)

    def test_legacy_pass_alias_accepted(self):
        text = '{"score": 9, "pass": true, "critical_issues": [], "missing_elements": []}'
        verdict = _parse_judge_json(text)
        self.assertIsNotNone(verdict)
        self.assertTrue(verdict.passed)

    def test_skips_leading_garbage_and_trailing_text(self):
        text = "Here is the verdict:\n```json\n" + (
            '{"score": 8, "passed": true, "critical_issues": [], "missing_elements": []}'
        ) + "\n```\nAdditional commentary."
        verdict = _parse_judge_json(text)
        self.assertIsNotNone(verdict)
        self.assertEqual(8, verdict.score)

    def test_non_string_input_returns_none(self):
        self.assertIsNone(_parse_judge_json(None))
        self.assertIsNone(_parse_judge_json(MagicMock()))


class ValidationModeTests(unittest.TestCase):
    def test_disabled_mode_skips_llm_entirely(self):
        llm = MagicMock()
        out = validate_and_refine(
            "整体偏多。",
            llm,
            _MARKET_SPEC,
            validation_mode="disabled",
        )
        self.assertEqual("整体偏多。", out)
        llm.with_structured_output.assert_not_called()
        llm.invoke.assert_not_called()

    def test_static_only_returns_input_when_no_issues(self):
        llm = MagicMock()
        out = validate_and_refine(
            _GOOD_MARKET_REPORT,
            llm,
            _MARKET_SPEC,
            validation_mode="static_only",
        )
        self.assertEqual(_GOOD_MARKET_REPORT, out)
        llm.invoke.assert_not_called()

    def test_static_only_triggers_refine_when_static_issues_exist(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = AttributeError("not supported")

        def _invoke(prompt, **_kwargs):
            # The refine prompt always includes the verdict JSON.
            self.assertIn("评审结果", prompt)
            return AIMessage(content="重写后的清洁报告。")

        llm.invoke.side_effect = _invoke

        bad_report = (
            "整体偏多。\n\n一、市场结构与量价诊断\n均线维持向上。\n"
        )  # missing 二、三 + missing MACD/RSI
        out = validate_and_refine(
            bad_report,
            llm,
            _MARKET_SPEC,
            validation_mode="static_only",
        )
        self.assertEqual("重写后的清洁报告。", out)
        # Only one LLM call (refine) — static_only never invokes the judge.
        self.assertEqual(1, llm.invoke.call_count)

    def test_static_plus_llm_uses_legacy_pass_alias(self):
        passing_payload = (
            '{"score": 9, "pass": true, "critical_issues": [], '
            '"minor_issues": [], "missing_elements": [], "general_comment": "ok"}'
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = AttributeError("not supported")
        llm.invoke.return_value = AIMessage(content=passing_payload)

        out = validate_and_refine(
            _GOOD_MARKET_REPORT,
            llm,
            _MARKET_SPEC,
            validation_mode="static_plus_llm",
        )
        # Judge says pass=true and static is clean → original report retained.
        self.assertEqual(_GOOD_MARKET_REPORT, out)
        self.assertEqual(1, llm.invoke.call_count)


class MergeVerdictsTests(unittest.TestCase):
    def test_static_only_pass(self):
        merged = _merge_verdicts(
            mode="static_only",
            static=StaticVerdict(),
            llm=None,
            score_threshold=7,
        )
        self.assertIsNotNone(merged)
        self.assertTrue(merged.passed)
        self.assertEqual(10, merged.score)

    def test_static_only_fail(self):
        merged = _merge_verdicts(
            mode="static_only",
            static=StaticVerdict(critical_issues=["bad"]),
            llm=None,
            score_threshold=7,
        )
        self.assertFalse(merged.passed)
        self.assertEqual(["bad"], merged.critical_issues)

    def test_static_plus_llm_static_issues_force_fail(self):
        llm_verdict = JudgeVerdict(
            score=9,
            passed=True,
            critical_issues=[],
            minor_issues=[],
            missing_elements=[],
        )
        merged = _merge_verdicts(
            mode="static_plus_llm",
            static=StaticVerdict(critical_issues=["还有自指式开头"]),
            llm=llm_verdict,
            score_threshold=7,
        )
        self.assertFalse(merged.passed)
        self.assertIn("还有自指式开头", merged.critical_issues)

    def test_llm_only_returns_llm_verdict(self):
        llm_verdict = JudgeVerdict(score=8, passed=True)
        merged = _merge_verdicts(
            mode="llm_only",
            static=StaticVerdict(),
            llm=llm_verdict,
            score_threshold=7,
        )
        self.assertIs(merged, llm_verdict)


class CleaningOrderingTests(unittest.TestCase):
    def test_pre_judge_clean_strips_artifacts_judge_would_flag(self):
        raw = (
            "以下是根据评审标准修正后的完整报告。\n"
            "# 技术面诊断\n\n"
            "本节核心结论指出趋势仍未走坏。\n\n"
            "判断：偏多。\n\n"
            "本报告将围绕当前ETF的量价结构。\n\n"
            "MACD 金叉，RSI 60。"
        )
        cleaned = pre_judge_clean(raw)
        self.assertFalse(contains_qa_label_artifacts(cleaned))
        self.assertFalse(contains_self_referential_meta_leads(cleaned))
        self.assertFalse(contains_meta_openers(cleaned))
        self.assertNotIn("以下是根据评审标准", cleaned)
        self.assertNotIn("# 技术面诊断", cleaned)
        self.assertIn("MACD 金叉", cleaned)

    def test_post_judge_clean_runs_punctuation_pass(self):
        raw = "走势已确认上行?\n\n"
        cleaned = post_judge_clean(raw)
        self.assertIn("走势已确认上行。", cleaned)

    def test_clean_generated_report_alias_matches_full_pipeline(self):
        raw = (
            "以下是根据评审标准修正后的完整报告。\n"
            "本报告将围绕当前ETF。\n\n"
            "判断：偏多。\n\n"
            "结论已确认?"
        )
        baseline = post_judge_clean(pre_judge_clean(raw))
        legacy = clean_generated_report(raw)
        self.assertEqual(baseline, legacy)

    def test_standalone_term_definition_block_is_removed(self):
        raw = (
            "开篇结论仍然保留。\n\n"
            "│  为降低跨市场阅读门槛并强化交易执行指引，本文对文中高频技术术语作如下通俗解释与含义说明： •\n"
            "│  仓单去化：指交易所标准仓单数量持续减少。交易含义：代表下游企业正在实质性提货。 •\n"
            "│  右侧多头：指在价格已突破关键压力位后顺势建仓的策略。交易含义：需严格设定止损线。\n"
            "│\n"
            "一、市场结构与量价诊断\n"
            "MACD 金叉首次出现时仍可在句内解释。"
        )

        cleaned = strip_standalone_term_definition_blocks(raw)

        self.assertIn("开篇结论仍然保留", cleaned)
        self.assertIn("一、市场结构与量价诊断", cleaned)
        self.assertIn("MACD 金叉", cleaned)
        self.assertNotIn("为降低跨市场阅读门槛", cleaned)
        self.assertNotIn("仓单去化：", cleaned)
        self.assertFalse(contains_qa_label_artifacts(cleaned))

    def test_term_definition_block_does_not_swallow_following_plain_paragraphs(self):
        raw = (
            "开篇结论保留。\n\n"
            "为降低跨市场阅读门槛，本文对文中高频技术术语作如下解释：\n"
            "• 仓单去化：指交易所标准仓单数量持续减少，交易含义为下游提货。\n"
            "• 右侧多头：指价格突破后顺势建仓，交易含义为需严格止损。\n\n"
            "板块景气度：电池正极材料指引开始转弱，需关注库存指引和定价指标。\n"
            "下一段：成交额放大至昨日两倍，主力资金净流入指数靠前。\n"
        )

        cleaned = strip_standalone_term_definition_blocks(raw)

        self.assertIn("开篇结论保留", cleaned)
        self.assertIn("板块景气度：电池正极材料指引开始转弱", cleaned)
        self.assertIn("下一段：成交额放大至昨日两倍", cleaned)
        self.assertNotIn("仓单去化：", cleaned)


if __name__ == "__main__":
    unittest.main()
