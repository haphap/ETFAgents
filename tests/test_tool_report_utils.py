import unittest

from etfagents.tool_report_utils import run_tool_report_chain, _is_tool_call_text


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
    def partial(self, **_kwargs):
        return self

    def __or__(self, runnable):
        return runnable


class _FakeTool:
    def __init__(self, name, return_value):
        self.name = name
        self.calls = []
        self.return_value = return_value

    def invoke(self, payload):
        self.calls.append(payload)
        return self.return_value


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

    def test_is_tool_call_text_detects_xml_patterns(self):
        self.assertTrue(_is_tool_call_text('<tool_call><function=foo></tool_call>'))
        self.assertTrue(_is_tool_call_text('<function=get_indicators>'))
        self.assertTrue(_is_tool_call_text('<function_call>something</function_call>'))
        self.assertFalse(_is_tool_call_text('Normal report text'))
        self.assertFalse(_is_tool_call_text(''))

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


if __name__ == "__main__":
    unittest.main()
