import re

from langchain_core.messages import HumanMessage

from etfagents.content_utils import extract_text_content


_FINAL_REPORT_FALLBACK = (
    " You have already gathered all required data. "
    "Do not call any tools again. Write the final report now based only on the "
    "information already present in the conversation."
)
_FINAL_REPORT_USER_NUDGE = (
    "Write the complete final markdown report now. "
    "Do not call tools. Do not explain your process. "
    "Use only the information already present in this conversation."
)

_XML_TOOL_CALL_RE = re.compile(
    r"<tool_call>|<function[=\s]|</?function_call>", re.IGNORECASE
)
_UNEXECUTED_TOOL_INTENT_TEMPLATE = (
    r"(?:好的[，,]\s*)?(?:接下来|下一步|现在|我将|将会|准备|需要)"
    r"[\s\S]{{0,180}}?"
    r"(?:调用|使用|获取)"
    r"[\s\S]{{0,120}}?"
    r"{tool_name}"
)


def _is_tool_call_text(text: str) -> bool:
    """Return True if *text* looks like an XML-formatted tool call, not a report."""
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_XML_TOOL_CALL_RE.search(stripped))


def _extract_report_text(result) -> str:
    report = extract_text_content(getattr(result, "content", None))
    if not report or _is_tool_call_text(report):
        return ""
    return report


def _looks_like_unexecuted_tool_intent(text: str, tool_name: str) -> bool:
    """Detect process-only text where a model says it will call a tool but did not."""
    if not text or not tool_name:
        return False
    stripped = text.strip()
    if len(stripped) > 700:
        return False
    if tool_name not in stripped:
        return False
    if re.search(r"(?m)^\s*[一二三四五六七八九十]+、", stripped):
        return False
    pattern = _UNEXECUTED_TOOL_INTENT_TEMPLATE.format(tool_name=re.escape(tool_name))
    return bool(re.search(pattern, stripped))


def _invoke_tool_safely(tool, payload: dict) -> str:
    try:
        return str(tool.invoke(payload))
    except Exception as exc:  # pragma: no cover - defensive runtime recovery
        return f"{tool.name} failed: {exc}"


def _recover_unexecuted_tool_intent(
    *,
    prompt_template,
    llm,
    messages,
    prompt_kwargs: dict,
    recovery_config: dict | None,
    report: str,
):
    if not recovery_config:
        return None, ""

    trigger_tool_name = recovery_config.get("trigger_tool_name")
    if not _looks_like_unexecuted_tool_intent(report, trigger_tool_name):
        return None, ""

    tool_payloads = recovery_config.get("tool_payloads") or []
    tool_sections = []
    tool_failures = 0
    for item in tool_payloads:
        tool = item["tool"]
        payload = item.get("payload", {})
        output = _invoke_tool_safely(tool, payload)
        if output.startswith(f"{tool.name} failed:"):
            tool_failures += 1
        tool_sections.append(f"### {tool.name} result\n{output}")

    if tool_sections and tool_failures == len(tool_sections):
        failure_text = "\n\n".join(tool_sections)
        return None, (
            "Required data tools were unavailable, so the final report cannot be completed "
            f"without risking unsupported analysis.\n\n{failure_text}"
        )

    recovery_context = (
        "The previous assistant response described a future tool call but did not execute it. "
        "The required tools have now been executed below. Write the complete final markdown report now. "
        "Do not mention that a recovery happened, do not explain your process, and do not call tools.\n\n"
        + "\n\n".join(tool_sections)
    )
    recovery_kwargs = dict(prompt_kwargs)
    recovery_kwargs["system_message"] = (
        f"{prompt_kwargs['system_message']} You have already gathered the required tool data. "
        "Do not call tools. Produce the final report from the provided tool results."
    )
    final_prompt = prompt_template.partial(**recovery_kwargs)
    result = (final_prompt | llm).invoke(
        [
            *messages,
            HumanMessage(content=recovery_context),
        ]
    )
    recovered_report = _extract_report_text(result)
    return result, recovered_report


def run_tool_report_chain(
    prompt_template,
    llm,
    tools,
    messages,
    *,
    unexecuted_tool_recovery: dict | None = None,
    **prompt_kwargs,
):
    """Run a tool-enabled analyst chain and recover from empty final responses."""
    base_prompt = prompt_template.partial(**prompt_kwargs)
    result = (base_prompt | llm.bind_tools(tools)).invoke(messages)

    if getattr(result, "tool_calls", None):
        return result, ""

    report = _extract_report_text(result)
    if report:
        recovered_result, recovered_report = _recover_unexecuted_tool_intent(
            prompt_template=prompt_template,
            llm=llm,
            messages=messages,
            prompt_kwargs=prompt_kwargs,
            recovery_config=unexecuted_tool_recovery,
            report=report,
        )
        if recovered_report:
            return recovered_result or result, recovered_report
        return result, report

    fallback_kwargs = dict(prompt_kwargs)
    fallback_kwargs["system_message"] = (
        f"{prompt_kwargs['system_message']}{_FINAL_REPORT_FALLBACK}"
    )
    fallback_prompt = prompt_template.partial(**fallback_kwargs)
    fallback_result = (fallback_prompt | llm).invoke(messages)
    fallback_report = _extract_report_text(fallback_result)

    if fallback_report:
        return fallback_result, fallback_report

    second_fallback_result = (fallback_prompt | llm).invoke(
        [
            *messages,
            HumanMessage(content=_FINAL_REPORT_USER_NUDGE),
        ]
    )
    second_fallback_report = _extract_report_text(second_fallback_result)

    if second_fallback_report:
        return second_fallback_result, second_fallback_report

    return result, ""
