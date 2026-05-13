import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from etfagents.agents.analysts.macro_analyst import create_macro_analyst


class _CapturingLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, prompt, **kwargs):
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
        self.assertIn("一级和二级标题只写中文标题", system_msg)
        self.assertNotIn("Exposure & Macro Thesis", system_msg)
        self.assertNotIn("Signals & Scenario Analysis", system_msg)

    def test_macro_analyst_strips_english_parentheticals_from_section_headings(self):
        llm = _CapturingLLM()
        node = create_macro_analyst(llm)

        with patch(
            "etfagents.agents.analysts.macro_analyst.run_tool_report_chain",
            return_value=(
                AIMessage(
                    content=(
                        "一、暴露与宏观主线 (Exposure & Macro Thesis)\n\n"
                        "（一）ETF暴露与敏感因子（Exposure Sensitivities）\n"
                        "PMI (Purchasing Managers' Index) 仍是正文里的正常解释。\n\n"
                        "二、异常信号与情景推演（Signals & Scenario Analysis）\n"
                        "风险偏好回落正在压缩高弹性暴露。"
                    )
                ),
                (
                    "一、暴露与宏观主线 (Exposure & Macro Thesis)\n\n"
                    "（一）ETF暴露与敏感因子（Exposure Sensitivities）\n"
                    "PMI (Purchasing Managers' Index) 仍是正文里的正常解释。\n\n"
                    "二、异常信号与情景推演（Signals & Scenario Analysis）\n"
                    "风险偏好回落正在压缩高弹性暴露。"
                ),
            ),
        ):
            result = node(
                {
                    "company_of_interest": "516650.SH",
                    "trade_date": "2026-04-30",
                    "messages": [HumanMessage(content="Analyze 516650.SH")],
                }
            )

        report = result["macro_regime_report"]
        self.assertIn("一、暴露与宏观主线", report)
        self.assertIn("（一）ETF暴露与敏感因子", report)
        self.assertIn("二、异常信号与情景推演", report)
        self.assertNotIn("Exposure & Macro Thesis", report)
        self.assertNotIn("Exposure Sensitivities", report)
        self.assertNotIn("Signals & Scenario Analysis", report)
        self.assertIn("PMI (Purchasing Managers' Index)", report)


if __name__ == "__main__":
    unittest.main()
