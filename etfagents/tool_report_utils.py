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


def run_tool_report_chain(prompt_template, llm, tools, messages, **prompt_kwargs):
    """Run a tool-enabled analyst chain and recover from empty final responses."""
    base_prompt = prompt_template.partial(**prompt_kwargs)
    result = (base_prompt | llm.bind_tools(tools)).invoke(messages)

    if getattr(result, "tool_calls", None):
        return result, ""

    report = _extract_report_text(result)
    if report:
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
