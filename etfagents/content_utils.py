from typing import Any


_TEXT_BLOCK_TYPES = {"text", "output_text"}


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _collect_text_parts(content: Any) -> list[str]:
    if content is None:
        return []

    if isinstance(content, str):
        text = _clean_text(content)
        return [text] if text else []

    if isinstance(content, (list, tuple)):
        parts = []
        for item in content:
            parts.extend(_collect_text_parts(item))
        return parts

    if isinstance(content, dict):
        block_type = content.get("type")
        text = _clean_text(content.get("text"))
        if text and (block_type in _TEXT_BLOCK_TYPES or block_type is None):
            return [text]

        nested = content.get("content")
        if nested is not None and nested is not content:
            return _collect_text_parts(nested)
        return []

    block_type = getattr(content, "type", None)
    text = _clean_text(getattr(content, "text", None))
    if text and (block_type in _TEXT_BLOCK_TYPES or block_type is None):
        return [text]

    nested = getattr(content, "content", None)
    if nested is not None and nested is not content:
        return _collect_text_parts(nested)

    return []


def extract_text_content(content: Any) -> str:
    """Extract plain text from provider-specific LLM content structures."""
    return "\n".join(_collect_text_parts(content))
