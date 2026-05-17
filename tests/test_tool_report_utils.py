import unittest

from langchain_core.messages import HumanMessage

from etfagents.tool_report_utils import (
    TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX,
    date_days_before,
    run_tool_report_chain,
    _is_process_only_report_text,
    _is_tool_call_text,
)


class _FakeResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeBoundLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, _messages):
        return self._responses.pop(0)


class _FakeLLM:
    def __init__(self, tool_responses, fallback_responses=None):
        self._tool_bound = _FakeBoundLLM(tool_responses)
        self._fallback = _FakeBoundLLM(fallback_responses or [])

    def bind_tools(self, _tools):
        return self._tool_bound

    def invoke(self, _messages):
        return self._fallback.invoke(_messages)


class _FakePrompt:
    def __init__(self):
        self.partial_calls = []

    def partial(self, **_kwargs):
        self.partial_calls.append(_kwargs)
        return self

    def __or__(self, runnable):
        return runnable


class _FakeTool:
    def __init__(self, name, return_value=None, *, raises=None):
        self.name = name
        self.calls = []
        self.return_value = return_value
        self.raises = raises

    def invoke(self, payload):
        self.calls.append(payload)
        if self.raises:
            raise self.raises
        return self.return_value


class _RecordingLLM(_FakeLLM):
    def __init__(self, tool_responses, fallback_responses=None):
        super().__init__(tool_responses, fallback_responses)
        self.fallback_invocations = []

    def invoke(self, messages):
        self.fallback_invocations.append(messages)
        return super().invoke(messages)


class ToolReportUtilsTests(unittest.TestCase):
    def test_returns_tool_response_when_more_tools_needed(self):
        prompt = _FakePrompt()
        llm = _FakeLLM([_FakeResponse(tool_calls=[{"name": "get_stock_data"}])])

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual(report, "")
        self.assertEqual(len(result.tool_calls), 1)

    def test_retries_empty_final_response_without_tools(self):
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [_FakeResponse(content="")],
            [_FakeResponse(content=[{"type": "text", "text": "Final report"}])],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual(report, "Final report")
        self.assertEqual(result.content[0]["text"], "Final report")

    def test_xml_tool_call_in_content_triggers_fallback(self):
        xml_tool_call = (
            '<tool_call>\n<function=get_indicators>\n'
            '<parameter=symbol>\n300308.SZ\n</parameter>\n'
            '<parameter=indicator>\nmacd\n</parameter>\n'
            '</function>\n</tool_call>'
        )
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [_FakeResponse(content=xml_tool_call)],
            [_FakeResponse(content="Real market analysis report")],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual(report, "Real market analysis report")

    def test_second_fallback_runs_when_first_fallback_is_empty(self):
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [_FakeResponse(content="")],
            [
                _FakeResponse(content=""),
                _FakeResponse(content="Recovered report on second fallback"),
            ],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual(report, "Recovered report on second fallback")
        self.assertEqual(result.content, "Recovered report on second fallback")

    def test_fallback_prompts_use_chinese_output_contract(self):
        prompt = _FakePrompt()
        llm = _RecordingLLM(
            [_FakeResponse(content="")],
            [
                _FakeResponse(content=""),
                _FakeResponse(content="Recovered report on second fallback"),
            ],
        )

        run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="中文系统提示",
        )

        fallback_system_message = prompt.partial_calls[1]["system_message"]
        self.assertIn("下一条回复必须只输出面向用户的最终 Markdown 正文", fallback_system_message)
        self.assertIn("不要以“现在我来”", fallback_system_message)
        self.assertNotIn("You have already gathered all required data", fallback_system_message)

        second_fallback_messages = llm.fallback_invocations[1]
        self.assertIsInstance(second_fallback_messages[-1], HumanMessage)
        self.assertIn("只返回最终 Markdown 正文", second_fallback_messages[-1].content)
        self.assertIn("第一行必须是开篇概述段", second_fallback_messages[-1].content)

    def test_fallback_prompts_use_english_output_contract(self):
        prompt = _FakePrompt()
        llm = _RecordingLLM(
            [_FakeResponse(content="")],
            [
                _FakeResponse(content=""),
                _FakeResponse(content="Recovered report on second fallback"),
            ],
        )

        run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="English system prompt",
        )

        fallback_system_message = prompt.partial_calls[1]["system_message"]
        self.assertIn("The next reply must be the completed end-user markdown only", fallback_system_message)
        self.assertIn("Do not begin with phrases like 'Now let me'", fallback_system_message)
        self.assertNotIn("You have already gathered all required data", fallback_system_message)

        second_fallback_messages = llm.fallback_invocations[1]
        self.assertIsInstance(second_fallback_messages[-1], HumanMessage)
        self.assertIn("Return only the final markdown body", second_fallback_messages[-1].content)
        self.assertIn("The first line must be the opening overview paragraph", second_fallback_messages[-1].content)

    def test_is_tool_call_text_detects_xml_patterns(self):
        self.assertTrue(_is_tool_call_text('<tool_call><function=foo></tool_call>'))
        self.assertTrue(_is_tool_call_text('<function=get_indicators>'))
        self.assertTrue(_is_tool_call_text('<function_call>something</function_call>'))
        self.assertFalse(_is_tool_call_text('Normal report text'))
        self.assertFalse(_is_tool_call_text(''))

    def test_process_only_report_text_triggers_fallback(self):
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [_FakeResponse(content="所有数据已获取。现在撰写完整的诊断报告。")],
            [_FakeResponse(content="Real final report")],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual("Real final report", report)
        self.assertEqual("Real final report", result.content)

    def test_process_only_prefix_is_removed_from_real_report(self):
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [
                _FakeResponse(
                    content=(
                        "所有数据已获取。现在撰写完整的诊断报告。\n\n"
                        "一、市场结构与量价诊断\n趋势偏多。"
                    )
                )
            ]
        )

        _, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual("一、市场结构与量价诊断\n趋势偏多。", report)

    def test_process_only_inline_prefix_keeps_report_body(self):
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [
                _FakeResponse(
                    content=(
                        "所有数据已获取。现在撰写完整的诊断报告。"
                        "一、市场结构与量价诊断\n趋势偏多。"
                    )
                )
            ]
        )

        _, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual("一、市场结构与量价诊断\n趋势偏多。", report)

    def test_acceptance_check_rejects_non_report_and_triggers_fallback(self):
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [_FakeResponse(content="数据已获取完毕，现在整合所有信息撰写报告。")],
            [_FakeResponse(content="真实报告正文")],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
            report_acceptance_check=lambda text: "真实报告" in text,
        )

        self.assertEqual("真实报告正文", report)
        self.assertEqual("真实报告正文", result.content)

    def test_acceptance_check_returns_empty_when_all_attempts_rejected(self):
        prompt = _FakePrompt()
        llm = _FakeLLM(
            [_FakeResponse(content="first draft")],
            [
                _FakeResponse(content="fallback draft"),
                _FakeResponse(content="second fallback draft"),
            ],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
            report_acceptance_check=lambda _text: False,
        )

        self.assertEqual("", report)
        self.assertEqual("first draft", result.content)

    def test_long_process_only_inline_prefix_keeps_report_body(self):
        prompt = _FakePrompt()
        overview = "行业景气修复但利润传导仍不均衡，" * 12
        llm = _FakeLLM(
            [
                _FakeResponse(
                    content=(
                        "现在我已获取全部所需数据，下面撰写最终交叉分析报告。"
                        f"{overview}\n\n"
                        "一、行业主线与分歧焦点\n盈利修复仍需验证。"
                    )
                )
            ]
        )

        _, report = run_tool_report_chain(
            prompt,
            llm,
            tools=["tool"],
            messages=["state"],
            system_message="sys",
        )

        self.assertEqual(
            f"{overview}\n\n一、行业主线与分歧焦点\n盈利修复仍需验证。",
            report,
        )

    def test_process_only_detector_ignores_real_sectioned_reports(self):
        self.assertTrue(
            _is_process_only_report_text(
                "现在我已获取全部所需数据，开始撰写综合诊断报告。"
            )
        )
        self.assertTrue(
            _is_process_only_report_text(
                "所有数据已获取。现在撰写完整的诊断报告。"
            )
        )
        self.assertTrue(
            _is_process_only_report_text(
                "现在我已获取全部所需数据，下面撰写最终交叉分析报告。"
            )
        )
        self.assertTrue(
            _is_process_only_report_text(
                "现在我已掌握所有必要数据，可以撰写完整的配置报告。"
            )
        )
        self.assertTrue(
            _is_process_only_report_text(
                "Now let me compile the full cross-analysis report based on all retrieved data."
            )
        )
        self.assertFalse(
            _is_process_only_report_text(
                "一、市场结构与量价诊断\n已获取的数据说明趋势偏强，报告正文继续展开。"
            )
        )
        self.assertFalse(
            _is_process_only_report_text(
                "尽管该ETF的数据已掌握，但市场不可控，需要继续撰写报告来验证风险敞口。"
            )
        )
        self.assertFalse(
            _is_process_only_report_text(
                "Now the market structure shows broad participation, and the report below details the evidence."
            )
        )

    def test_process_only_detector_does_not_match_mid_sentence_report_plan(self):
        self.assertFalse(
            _is_process_only_report_text(
                "本ETF已获取充足成交数据；预计将在下次再平衡前撰写补充报告以验证假设。"
            )
        )

    def test_recovers_unexecuted_intent_for_any_configured_trigger_tool(self):
        prompt = _FakePrompt()
        news_tool = _FakeTool("get_news", "news data")
        llm = _FakeLLM(
            [_FakeResponse(content="好的，接下来我将调用 get_news 工具获取催化剂。")],
            [_FakeResponse(content="Recovered macro report")],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=[news_tool],
            messages=["state"],
            system_message="sys",
            unexecuted_tool_recovery={
                "trigger_tool_names": ["get_etf_info", "get_news"],
                "tool_payloads": [
                    {
                        "tool": news_tool,
                        "payload": {
                            "ticker": "516650.SH",
                            "start_date": "2026-03-30",
                            "end_date": "2026-04-30",
                        },
                    },
                ],
            },
        )

        self.assertEqual(report, "Recovered macro report")
        self.assertEqual(result.content, "Recovered macro report")
        self.assertEqual(
            [
                {
                    "ticker": "516650.SH",
                    "start_date": "2026-03-30",
                    "end_date": "2026-04-30",
                }
            ],
            news_tool.calls,
        )

    def test_acceptance_check_preserves_unexecuted_tool_recovery(self):
        prompt = _FakePrompt()
        news_tool = _FakeTool("get_news", "news data")
        llm = _FakeLLM(
            [_FakeResponse(content="好的，接下来我将调用 get_news 工具获取催化剂。")],
            [_FakeResponse(content="Recovered complete report")],
        )

        result, report = run_tool_report_chain(
            prompt,
            llm,
            tools=[news_tool],
            messages=["state"],
            system_message="sys",
            report_acceptance_check=lambda text: text.startswith("Recovered"),
            unexecuted_tool_recovery={
                "trigger_tool_names": ["get_news"],
                "tool_payloads": [
                    {"tool": news_tool, "payload": {"ticker": "516650.SH"}},
                ],
            },
        )

        self.assertEqual("Recovered complete report", report)
        self.assertEqual("Recovered complete report", result.content)
        self.assertEqual([{"ticker": "516650.SH"}], news_tool.calls)

    def test_recovery_only_runs_payloads_for_matched_tool_names(self):
        prompt = _FakePrompt()
        info_tool = _FakeTool("get_etf_info", "info data")
        news_tool = _FakeTool("get_news", "news data")
        llm = _FakeLLM(
            [_FakeResponse(content="好的，接下来我将调用 get_news 工具获取催化剂。")],
            [_FakeResponse(content="Recovered report")],
        )

        _, report = run_tool_report_chain(
            prompt,
            llm,
            tools=[info_tool, news_tool],
            messages=["state"],
            system_message="sys",
            unexecuted_tool_recovery={
                "trigger_tool_names": ["get_etf_info", "get_news"],
                "tool_payloads": [
                    {"tool": info_tool, "payload": {"ticker": "516650.SH"}},
                    {"tool": news_tool, "payload": {"ticker": "516650.SH"}},
                ],
            },
        )

        self.assertEqual("Recovered report", report)
        self.assertEqual([], info_tool.calls)
        self.assertEqual([{"ticker": "516650.SH"}], news_tool.calls)

    def test_recovery_runs_multiple_matched_payloads(self):
        prompt = _FakePrompt()
        info_tool = _FakeTool("get_etf_info", "info data")
        news_tool = _FakeTool("get_news", "news data")
        llm = _FakeLLM(
            [
                _FakeResponse(
                    content=(
                        "好的，接下来我将调用 get_etf_info 工具，并继续调用 get_news 工具。"
                    )
                )
            ],
            [_FakeResponse(content="Recovered report")],
        )

        _, report = run_tool_report_chain(
            prompt,
            llm,
            tools=[info_tool, news_tool],
            messages=["state"],
            system_message="sys",
            unexecuted_tool_recovery={
                "trigger_tool_names": ["get_etf_info", "get_news"],
                "tool_payloads": [
                    {"tool": info_tool, "payload": {"ticker": "516650.SH"}},
                    {"tool": news_tool, "payload": {"ticker": "516650.SH"}},
                ],
            },
        )

        self.assertEqual("Recovered report", report)
        self.assertEqual([{"ticker": "516650.SH"}], info_tool.calls)
        self.assertEqual([{"ticker": "516650.SH"}], news_tool.calls)

    def test_recovery_failure_count_uses_boolean_not_output_prefix(self):
        prompt = _FakePrompt()
        news_tool = _FakeTool("get_news", "get_news failed: vendor returned a literal status")
        llm = _FakeLLM(
            [_FakeResponse(content="好的，接下来我将调用 get_news 工具。")],
            [_FakeResponse(content="Recovered report despite literal prefix")],
        )

        _, report = run_tool_report_chain(
            prompt,
            llm,
            tools=[news_tool],
            messages=["state"],
            system_message="sys",
            unexecuted_tool_recovery={
                "trigger_tool_names": ["get_news"],
                "tool_payloads": [{"tool": news_tool, "payload": {"ticker": "516650.SH"}}],
            },
        )

        self.assertEqual("Recovered report despite literal prefix", report)

    def test_recovery_returns_data_unavailable_report_when_all_tools_raise(self):
        prompt = _FakePrompt()
        news_tool = _FakeTool("get_news", raises=RuntimeError("vendor down"))
        llm = _FakeLLM([_FakeResponse(content="好的，接下来我将调用 get_news 工具。")])

        _, report = run_tool_report_chain(
            prompt,
            llm,
            tools=[news_tool],
            messages=["state"],
            system_message="sys",
            unexecuted_tool_recovery={
                "trigger_tool_names": ["get_news"],
                "tool_payloads": [{"tool": news_tool, "payload": {"ticker": "516650.SH"}}],
            },
        )

        self.assertTrue(report.startswith(TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX))
        self.assertIn("get_news failed: vendor down", report)

    def test_date_days_before_handles_valid_and_invalid_dates(self):
        self.assertEqual("2026-03-31", date_days_before("2026-04-30", 30))
        self.assertEqual("not-a-date", date_days_before("not-a-date", 30))


if __name__ == "__main__":
    unittest.main()
