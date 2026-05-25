import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.macro_analyst import (
    create_macro_analyst,
    _looks_like_complete_macro_report,
)


_VALIDATION_PASSED_JSON = '{"score": 9, "pass": true, "critical_issues": [], "minor_issues": [], "missing_elements": [], "general_comment": "OK"}'


class _CapturingLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, prompt, **kwargs):
        # Return valid JSON for validation judge step so it passes cleanly
        if "报告质量审核员" in str(prompt):
            return AIMessage(content=_VALIDATION_PASSED_JSON)
        return AIMessage(content="Macro report content")


class MacroAnalystTests(unittest.TestCase):
    def test_macro_analyst_returns_macro_regime_report(self):
        llm = _CapturingLLM()
        node = create_macro_analyst(llm)

        with patch(
            "etfagents.agents.analysts.macro_analyst.run_tool_report_chain",
            return_value=(
                AIMessage(content="# Macro report\n\nUnified macro logic."),
                "# Macro report\n\nUnified macro logic.",
            ),
        ):
            result = node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        self.assertIn("macro_regime_report", result)
        self.assertIn("Unified macro logic", result["macro_regime_report"])

    def test_macro_analyst_prompt_includes_etf_exposure_calendar_and_macro_framework(self):
        llm = _CapturingLLM()
        node = create_macro_analyst(llm)
        captured = {}

        def _mock_run(*args, **kwargs):
            captured["tools"] = [tool.name for tool in args[2]]
            captured["system_message"] = kwargs.get("system_message", "")
            captured["recovery"] = kwargs.get("unexecuted_tool_recovery", {})
            captured["acceptance_check"] = kwargs.get("report_acceptance_check")
            return (AIMessage(content="Macro report"), "Macro report")

        with patch(
            "etfagents.agents.analysts.macro_analyst.run_tool_report_chain",
            side_effect=_mock_run,
        ):
            node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        self.assertEqual(
            captured["tools"],
            ["get_etf_info", "get_etf_holdings", "get_macro_regime_data", "get_global_news", "get_news"],
        )
        system_msg = captured["system_message"]
        self.assertIn("ETF暴露与敏感因子", system_msg)
        self.assertIn("cn_schedule", system_msg)
        self.assertIn("异常信号与传导链", system_msg)
        self.assertIn("下个窗口关键催化", system_msg)
        self.assertIn("开篇帽段必须直接给出宏观主判断", system_msg)
        self.assertIn("每个一级章节（一、二、三、四）标题后直接写2-3句投资判断", system_msg)
        self.assertIn("内容目标：ETF暴露与敏感因子覆盖主导仓位", system_msg)
        self.assertIn("不得以'概述：'", system_msg)
        self.assertIn("不得写'本报告对…进行分析'", system_msg)
        self.assertIn("一级和二级标题只写中文标题", system_msg)
        self.assertNotIn("识别ETF主导仓位", system_msg)
        self.assertNotIn("整合全球利率、信用定价", system_msg)
        self.assertNotIn("解释哪些利差、实际利率", system_msg)
        self.assertNotIn("列出下一个再平衡窗口", system_msg)
        self.assertNotIn("本部分的核心结论是", system_msg)
        self.assertNotIn("Exposure & Macro Thesis", system_msg)
        self.assertNotIn("Signals & Scenario Analysis", system_msg)
        self.assertIs(captured["acceptance_check"], _looks_like_complete_macro_report)
        self.assertEqual(captured["tools"], captured["recovery"]["trigger_tool_names"])
        self.assertEqual(
            captured["tools"],
            [item["tool"].name for item in captured["recovery"]["tool_payloads"]],
        )

    def test_macro_report_acceptance_rejects_labeled_or_meta_opening_cap(self):
        valid_report = (
            "煤价下行和全球利率分化正在压缩煤炭ETF的风险溢价，当前配置应以防守等待为主，"
            "只有政策稳增长和需求修复同时兑现才适合提高仓位。\n\n"
            "一、暴露与宏观主线\n"
            "ETF暴露集中在煤炭链条。\n\n"
            "二、异常信号与情景推演\n"
            "实际利率和煤价构成主要压力。\n\n"
            "三、催化窗口与失效条件\n"
            "跟踪政策与库存数据。\n\n"
            "四、配置结论与跟踪表\n"
            "| 指标 | 配置含义 |\n"
            "| --- | --- |\n"
            "| 煤价 | 下行压制盈利 |"
        )

        self.assertTrue(_looks_like_complete_macro_report(valid_report))
        self.assertTrue(
            _looks_like_complete_macro_report(
                "煤价下行和全球利率分化正在压缩煤炭ETF的风险溢价，当前配置应以防守等待为主。\n\n"
                "一、暴露与宏观主线\nETF暴露集中在煤炭链条。\n\n"
                "二、异常信号与情景推演\n实际利率和煤价构成主要压力。\n\n"
                "三、催化窗口与失效条件\n跟踪政策与库存数据。"
            )
        )
        self.assertFalse(
            _looks_like_complete_macro_report(
                "概述：煤炭ETF宏观压力仍在。\n\n"
                "一、暴露与宏观主线\nETF暴露集中。\n\n"
                "二、异常信号与情景推演\n压力仍在。\n\n"
                "三、催化窗口与失效条件\n跟踪政策。\n\n"
                "四、配置结论与跟踪表\n| 指标 | 配置含义 |\n| --- | --- |"
            )
        )
        self.assertFalse(
            _looks_like_complete_macro_report(
                "本报告对515220.SH煤炭ETF国泰进行截至2026年4月30日的宏观与配置分析，聚焦其高集中度煤炭持仓在煤价下行、全球利率分化及AI科技虹吸效应下的风险暴露与再平衡机遇。\n\n"
                "一、暴露与宏观主线\nETF暴露集中。\n\n"
                "二、异常信号与情景推演\n压力仍在。\n\n"
                "三、催化窗口与失效条件\n跟踪政策。\n\n"
                "四、配置结论与跟踪表\n| 指标 | 配置含义 |\n| --- | --- |"
            )
        )



if __name__ == "__main__":
    unittest.main()
