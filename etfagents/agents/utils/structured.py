"""Shared helpers for invoking an agent with structured output and a graceful fallback."""

import copy
import logging
import re
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

from etfagents.content_utils import extract_text_content


SchemaT = TypeVar("SchemaT", bound=BaseModel)
logger = logging.getLogger(__name__)

STRUCTURED_FIELD_POPULATION_INSTRUCTION = (
    "In addition to the prose sections, populate the structured fields "
    "target_weight_pct, target_weight_band, execution_timing, add_triggers, "
    "reduce_triggers, exit_triggers, rebalance_triggers, and risk_controls "
    "whenever the evidence supports them; use null or empty lists only when "
    "the reports truly do not justify reliable values."
)
STRUCTURED_TRIGGER_METRICS_INSTRUCTION = (
    "For structured triggers, prefer supported metrics such as close, open, "
    "high, low, volume, sma_20, close_50_sma, volume_ratio_20d, pnl_pct, "
    "and weight_pct."
)
STRUCTURED_FIELD_VISIBILITY_INSTRUCTION = (
    "Never expose machine-readable field names such as target_weight_pct, "
    "target_weight_band, execution_timing, add_triggers, reduce_triggers, "
    "exit_triggers, rebalance_triggers, or risk_controls in the visible prose."
)
_STRUCTURED_ONLY_PROMPT_SENTENCES = (
    STRUCTURED_FIELD_POPULATION_INSTRUCTION,
    STRUCTURED_TRIGGER_METRICS_INSTRUCTION,
    STRUCTURED_FIELD_VISIBILITY_INSTRUCTION,
)


def _strip_structured_only_text(text: str) -> str:
    """Remove shared structured-only sentences and lightly normalize whitespace.

    This targets the shared prompt sentences reused by Trader and Portfolio
    Manager when structured output is available. After stripping them, it
    collapses runs of 3+ newlines and repeated spaces/tabs so the fallback
    prompt remains readable even when whole sentences were removed mid-block.
    """
    cleaned = text or ""
    for sentence in _STRUCTURED_ONLY_PROMPT_SENTENCES:
        cleaned = cleaned.replace(sentence, "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _transform_prompt_strings(prompt: Any, transform: Callable[[str], str]) -> Any:
    if isinstance(prompt, str):
        return transform(prompt)
    if isinstance(prompt, list):
        return [_transform_prompt_strings(item, transform) for item in prompt]
    if isinstance(prompt, tuple):
        return tuple(_transform_prompt_strings(item, transform) for item in prompt)
    if isinstance(prompt, dict):
        updated = dict(prompt)
        for key, value in prompt.items():
            if isinstance(value, (str, list, tuple, dict)):
                updated[key] = _transform_prompt_strings(value, transform)
        return updated
    return prompt


def build_prose_only_fallback_prompt(prompt: Any, extra_instruction: str = "") -> Any:
    """Remove structured-output-only instructions from a fallback prompt.

    Structured-output mode can ask the model to populate hidden schema fields, but
    that same instruction becomes harmful when we retry as free text because the
    plain model may surface those field names in the visible prose. This helper
    strips the structured-only instructions and optionally appends a prose-format
    reminder tailored to the fallback path.

    For list/tuple chat-style prompts, the extra instruction is appended to the
    first system message only; if no system message exists, one is prepended.
    """
    cleaned_prompt = _transform_prompt_strings(prompt, _strip_structured_only_text)
    extra = (extra_instruction or "").strip()
    if not extra:
        return cleaned_prompt

    if isinstance(cleaned_prompt, str):
        return f"{cleaned_prompt.rstrip()}\n\n{extra}"

    if isinstance(cleaned_prompt, list):
        updated = copy.deepcopy(cleaned_prompt)
        for message in updated:
            if (
                isinstance(message, dict)
                and str(message.get("role", "")).lower() == "system"
                and isinstance(message.get("content"), str)
            ):
                message["content"] = f"{message['content'].rstrip()}\n\n{extra}"
                return updated
        updated.insert(0, {"role": "system", "content": extra})
        return updated

    if isinstance(cleaned_prompt, tuple):
        updated = list(cleaned_prompt)
        for index, message in enumerate(updated):
            if (
                isinstance(message, dict)
                and str(message.get("role", "")).lower() == "system"
                and isinstance(message.get("content"), str)
            ):
                patched = dict(message)
                patched["content"] = f"{patched['content'].rstrip()}\n\n{extra}"
                updated[index] = patched
                return tuple(updated)
        updated.insert(0, {"role": "system", "content": extra})
        return tuple(updated)

    return cleaned_prompt


def bind_structured(llm: Any, schema: type[SchemaT], agent_name: str) -> Optional[Any]:
    """Return a pre-bound structured-output LLM or None if unsupported."""
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name,
            exc,
        )
        return None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[SchemaT], str],
    agent_name: str,
    fallback_prompt: Any | None = None,
) -> str:
    return invoke_structured_or_freetext_with_result(
        structured_llm,
        plain_llm,
        prompt,
        render,
        agent_name,
        fallback_prompt=fallback_prompt,
    )[0]


def invoke_structured_or_freetext_with_result(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[SchemaT], str],
    agent_name: str,
    fallback_prompt: Any | None = None,
) -> tuple[str, Optional[SchemaT]]:
    """Run the structured call and render it; fall back to free text on failure."""
    if structured_llm is not None:
        try:
            structured_result = structured_llm.invoke(prompt)
            return render(structured_result), structured_result
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name,
                exc,
            )

    prose_prompt = (
        fallback_prompt
        if fallback_prompt is not None
        else build_prose_only_fallback_prompt(prompt)
    )
    response = plain_llm.invoke(prose_prompt)
    return extract_text_content(getattr(response, "content", response)), None
