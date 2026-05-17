import re
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage

from etfagents.content_utils import contains_cjk, extract_text_content


TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX = "[tool-recovery:data-unavailable]"

_XML_TOOL_CALL_RE = re.compile(
    r"<tool_call>|<function[=\s]|</?function_call>", re.IGNORECASE
)
_DATA_READY_RE = (
    r"(?:(?:已|已经).{0,40}?(?:获取|收集|拿到|完成|掌握).{0,40}?(?:数据|资料|信息)"
    r"|(?:数据|资料|信息).{0,40}?(?:已|已经).{0,40}?(?:获取|收集|拿到|完成|掌握))"
)
_EN_DATA_READY_RE = (
    r"(?:"
    r"(?:all\s+)?(?:required|retrieved|necessary|needed)\s+data"
    r"|(?:retrieved|gathered|collected|obtained)\s+(?:all\s+)?"
    r"(?:(?:required|necessary|needed)\s+)?(?:data|information)"
    r"|(?:all\s+)?data\s+(?:has\s+been\s+)?(?:retrieved|gathered|collected|obtained)"
    r"|(?:data|information)\s+(?:is\s+)?(?:ready|available)"
    r")"
)
_EN_REPORT_ACTION_RE = (
    r"(?:write|draft|compile|generate|produce)"
    r"(?:\s+the)?(?:\s+(?:full|complete|final))?"
    r"(?:\s+cross-analysis)?(?:\s+analysis)?\s+report"
)
_PROCESS_ONLY_REPORT_RE = re.compile(
    r"(?:现在|好的|接下来|下一步|我|所有|数据|资料|信息|已获取|已经获取)[\s\S]{0,80}?"
    + _DATA_READY_RE
    + r"[\s\S]{0,120}?"
    r"(?:开始|将|马上|准备|现在|下面|接下来|随后|继续|直接|正式|可以|能够).{0,40}?"
    r"(?:撰写|生成|输出|写).{0,40}?报告",
    re.IGNORECASE,
)
_EN_PROCESS_ONLY_REPORT_RE = re.compile(
    r"(?:now|okay|alright|next|let me|i(?:'ll| will)?|we(?:'ll| will)?|with all)"
    r"[\s\S]{0,80}?"
    r"(?:"
    + _EN_DATA_READY_RE
    + r"[\s\S]{0,120}?"
    + _EN_REPORT_ACTION_RE
    + r"|"
    + _EN_REPORT_ACTION_RE
    + r"[\s\S]{0,120}?(?:based on|using|from)?[\s\S]{0,40}?"
    + _EN_DATA_READY_RE
    + r")",
    re.IGNORECASE,
)
_PROCESS_ONLY_REPORT_PREFIX_RE = re.compile(
    _PROCESS_ONLY_REPORT_RE.pattern + r"[。.!！]?\s*",
    re.IGNORECASE,
)
_EN_PROCESS_ONLY_REPORT_PREFIX_RE = re.compile(
    _EN_PROCESS_ONLY_REPORT_RE.pattern + r"[。.!！]?\s*",
    re.IGNORECASE,
)
_UNEXECUTED_TOOL_INTENT_TEMPLATE = (
    r"(?:好的[，,]\s*)?(?:接下来|下一步|现在|我将|将会|准备|需要)"
    r"[\s\S]{{0,180}}?"
    r"(?:调用|使用|获取)"
    r"[\s\S]{{0,120}}?"
    r"{tool_name}"
)


def _should_use_chinese_fallback(system_message: str) -> bool:
    return contains_cjk(system_message or "")


def _build_final_report_fallback(system_message: str) -> str:
    if _should_use_chinese_fallback(system_message):
        return (
            " 你的上一条回复没有给出最终报告正文。"
            "下一条回复必须只输出面向用户的最终 Markdown 正文，并立刻以开篇概述段起笔。"
            "不要提及工具、数据已获取/已检索、数据收集、正在撰写、正在整理、下一步或你的过程。"
            "不要以“现在我来”“接下来”“下面”“我将”“我可以开始”等过程性话术开头。"
        )
    return (
        " Your previous reply did not contain the finished report body. "
        "The next reply must be the completed end-user markdown only. "
        "Begin immediately with the opening overview paragraph in the target language. "
        "Do not mention tools, retrieved data, data collection, writing, drafting, compiling, "
        "next steps, or your process. Do not begin with phrases like 'Now let me', 'I will', "
        "'I can now', 'Next', or similar process narration."
    )


def _build_final_report_user_nudge(system_message: str) -> str:
    if _should_use_chinese_fallback(system_message):
        return (
            "只返回最终 Markdown 正文。"
            "不要写前言、状态说明或过程解释。"
            "第一行必须是开篇概述段，不能是过程句。"
        )
    return (
        "Return only the final markdown body. "
        "No preface, no status update, no explanation. "
        "The first line must be the opening overview paragraph, not a process sentence."
    )


def _is_tool_call_text(text: str) -> bool:
    """Return True if *text* looks like an XML-formatted tool call, not a report."""
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_XML_TOOL_CALL_RE.search(stripped))


def _is_process_only_report_text(text: str) -> bool:
    """Return True for short process notes like 'I have the data and will write now'."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > 700:
        return False
    if re.search(r"(?m)^\s*[一二三四五六七八九十]+、", stripped):
        return False
    short = stripped[:240]
    return bool(
        _PROCESS_ONLY_REPORT_RE.match(short)
        or _EN_PROCESS_ONLY_REPORT_RE.match(short)
    )


def _strip_process_only_report_prefix(text: str) -> str:
    """Remove leading process-only status lines from otherwise valid reports."""
    lines = (text or "").strip().splitlines()
    changed = False
    while lines:
        first_line = lines[0].strip()
        if not first_line:
            lines.pop(0)
            changed = True
            continue
        if not (
            _PROCESS_ONLY_REPORT_RE.match(first_line[:240])
            or _EN_PROCESS_ONLY_REPORT_RE.match(first_line[:240])
        ):
            break
        prefix_match = _PROCESS_ONLY_REPORT_PREFIX_RE.match(
            first_line
        ) or _EN_PROCESS_ONLY_REPORT_PREFIX_RE.match(first_line)
        if not prefix_match:
            break
        remainder = first_line[prefix_match.end():].strip()
        if remainder:
            lines[0] = remainder
            changed = True
            break
        lines.pop(0)
        changed = True
    return "\n".join(lines).strip() if changed else (text or "").strip()


def _extract_report_text(result, report_acceptance_check=None) -> str:
    report = _strip_process_only_report_prefix(
        extract_text_content(getattr(result, "content", None))
    )
    if not report or _is_tool_call_text(report) or _is_process_only_report_text(report):
        return ""
    if report_acceptance_check is not None and not report_acceptance_check(report):
        return ""
    return report


def _report_is_accepted(report: str, report_acceptance_check=None) -> bool:
    if not report:
        return False
    return report_acceptance_check is None or report_acceptance_check(report)


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


def _recovery_trigger_tool_names(recovery_config: dict) -> tuple[str, ...]:
    # Accept the legacy `trigger_tool_name: str` key so older callers keep working.
    names = recovery_config.get("trigger_tool_names")
    if names is None:
        names = recovery_config.get("trigger_tool_name")
    if isinstance(names, str):
        return (names,)
    return tuple(name for name in (names or ()) if name)


def date_days_before(curr_date: str, days: int) -> str:
    try:
        return (
            datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=days)
        ).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return curr_date


def _invoke_tool_safely(tool, payload: dict) -> tuple[bool, str]:
    try:
        return True, str(tool.invoke(payload))
    except Exception as exc:  # pragma: no cover - defensive runtime recovery
        return False, f"{tool.name} failed: {exc}"


def _recover_unexecuted_tool_intent(
    *,
    prompt_template,
    llm,
    messages,
    prompt_kwargs: dict,
    recovery_config: dict | None,
    report: str,
    report_acceptance_check=None,
):
    if not recovery_config:
        return None, ""

    trigger_tool_names = _recovery_trigger_tool_names(recovery_config)
    matched_tool_names = {
        tool_name
        for tool_name in trigger_tool_names
        if _looks_like_unexecuted_tool_intent(report, tool_name)
    }
    if not matched_tool_names:
        return None, ""

    tool_payloads = recovery_config.get("tool_payloads") or []
    matched_payloads = [
        item
        for item in tool_payloads
        if item.get("tool") is not None
        and getattr(item["tool"], "name", None) in matched_tool_names
    ]
    payloads_to_run = matched_payloads or tool_payloads
    tool_sections = []
    tool_failures = 0
    for item in payloads_to_run:
        tool = item["tool"]
        payload = item.get("payload", {})
        success, output = _invoke_tool_safely(tool, payload)
        if not success:
            tool_failures += 1
        tool_sections.append(f"### {tool.name} result\n{output}")

    if tool_sections and tool_failures == len(tool_sections):
        failure_text = "\n\n".join(tool_sections)
        return None, (
            f"{TOOL_RECOVERY_DATA_UNAVAILABLE_PREFIX}\n"
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
    recovered_report = _extract_report_text(result, report_acceptance_check)
    return result, recovered_report


def run_tool_report_chain(
    prompt_template,
    llm,
    tools,
    messages,
    *,
    unexecuted_tool_recovery: dict | None = None,
    report_acceptance_check=None,
    **prompt_kwargs,
):
    """Run a tool-enabled analyst chain and recover from empty final responses.

    If every non-tool attempt fails the optional acceptance check, returns the
    first result and an empty report so callers do not persist rejected content.
    """
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
            report_acceptance_check=report_acceptance_check,
        )
        if recovered_report:
            return recovered_result or result, recovered_report
        if _report_is_accepted(report, report_acceptance_check):
            return result, report

    fallback_kwargs = dict(prompt_kwargs)
    system_message = prompt_kwargs.get("system_message", "")
    fallback_kwargs["system_message"] = (
        f"{system_message}{_build_final_report_fallback(system_message)}"
    )
    fallback_prompt = prompt_template.partial(**fallback_kwargs)
    fallback_result = (fallback_prompt | llm).invoke(messages)
    fallback_report = _extract_report_text(fallback_result, report_acceptance_check)

    if fallback_report:
        return fallback_result, fallback_report

    second_fallback_result = (fallback_prompt | llm).invoke(
        [
            *messages,
            HumanMessage(content=_build_final_report_user_nudge(system_message)),
        ]
    )
    second_fallback_report = _extract_report_text(
        second_fallback_result,
        report_acceptance_check,
    )

    if second_fallback_report:
        return second_fallback_result, second_fallback_report

    return result, ""
