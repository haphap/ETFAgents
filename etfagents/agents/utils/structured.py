"""Shared helpers for invoking an agent with structured output and a graceful fallback."""

import logging
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

from etfagents.content_utils import extract_text_content


SchemaT = TypeVar("SchemaT", bound=BaseModel)
logger = logging.getLogger(__name__)


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
) -> str:
    return invoke_structured_or_freetext_with_result(
        structured_llm,
        plain_llm,
        prompt,
        render,
        agent_name,
    )[0]


def invoke_structured_or_freetext_with_result(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[SchemaT], str],
    agent_name: str,
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

    response = plain_llm.invoke(prompt)
    return extract_text_content(getattr(response, "content", response)), None
