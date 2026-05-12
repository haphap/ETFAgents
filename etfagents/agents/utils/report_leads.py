import re

from etfagents.agents.utils.agent_utils import collapse_blank_lines

_H1_TITLE_PATTERN = re.compile(r"^#\s+\S")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_LEAD_META_PREFIX_PATTERN = re.compile(
    r"(?m)^(?:"
    r"本部分(?:的)?(?:结论|判断|核心结论|核心判断)?(?:表明|显示|意味着|在于|是)?"
    r"|该部分(?:的)?(?:结论|判断|核心结论|核心判断)?(?:表明|显示|意味着|在于|是)?"
    r"|这一部分(?:的)?(?:结论|判断|核心结论|核心判断)?(?:表明|显示|意味着|在于|是)?"
    r"|本节(?:的)?(?:结论|判断|核心结论|核心判断)?(?:表明|显示|意味着|在于|是)?"
    r"|该节(?:的)?(?:结论|判断|核心结论|核心判断)?(?:表明|显示|意味着|在于|是)?"
    r"|这一节(?:的)?(?:结论|判断|核心结论|核心判断)?(?:表明|显示|意味着|在于|是)?"
    r"|This section(?:'s)?\s+(?:conclusion|conclusions|key takeaway|key point)(?:\s+(?:shows|indicates|means|is))?"
    r"|The key takeaway of this section(?:\s+(?:shows|indicates|means|is))?"
    r")[：:，,\s]+"
)


def strip_meta_lead_prefixes(report: str) -> str:
    if not report:
        return ""
    return _LEAD_META_PREFIX_PATTERN.sub("", report)


def _looks_like_section_heading(line: str) -> bool:
    stripped = (line or "").strip()
    return stripped.startswith("#") or bool(
        re.match(r"^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十\d]+）)", stripped)
    )


def ensure_title_lead_paragraph(
    report: str,
    chinese_default_lead: str,
    english_default_lead: str,
) -> str:
    if not report:
        return ""
    text = collapse_blank_lines(report).strip()
    lines = text.splitlines()
    if not lines or not _H1_TITLE_PATTERN.match(lines[0].strip()):
        return text

    first_body_line = 1
    while first_body_line < len(lines) and not lines[first_body_line].strip():
        first_body_line += 1
    if first_body_line >= len(lines) or not _looks_like_section_heading(lines[first_body_line]):
        return text

    default_lead = chinese_default_lead if _CJK_PATTERN.search(text) else english_default_lead
    return collapse_blank_lines(
        "\n".join([lines[0], "", default_lead, ""] + lines[first_body_line:])
    )


def strip_title_lead_paragraph(report: str) -> str:
    if not report:
        return ""
    text = collapse_blank_lines(report).strip()
    lines = text.splitlines()
    if not lines or not _H1_TITLE_PATTERN.match(lines[0].strip()):
        return text

    first_body_line = 1
    while first_body_line < len(lines) and not lines[first_body_line].strip():
        first_body_line += 1
    if first_body_line >= len(lines):
        return text
    if _looks_like_section_heading(lines[first_body_line]):
        return text

    first_heading_line = first_body_line
    while first_heading_line < len(lines) and not _looks_like_section_heading(lines[first_heading_line]):
        first_heading_line += 1
    if first_heading_line >= len(lines):
        return text

    return collapse_blank_lines("\n".join([lines[0], ""] + lines[first_heading_line:]))


def strip_first_section_lead_paragraph(report: str) -> str:
    if not report:
        return ""
    text = collapse_blank_lines(report).strip()
    lines = text.splitlines()
    if not lines:
        return text

    top_level_visible_pattern = re.compile(r"^(?:#{1,6}\s*)?[一二三四五六七八九十]+、")
    subheading_visible_pattern = re.compile(r"^(?:#{1,6}\s*)?（[一二三四五六七八九十\d]+）")
    markdown_only_heading_pattern = re.compile(r"^#{1,6}\s*$")

    first_top_level_visible = None
    for index, line in enumerate(lines):
        if top_level_visible_pattern.match((line or "").strip()):
            first_top_level_visible = index
            break
    if first_top_level_visible is None:
        return text

    first_subheading_visible = None
    for index in range(first_top_level_visible + 1, len(lines)):
        if subheading_visible_pattern.match((lines[index] or "").strip()):
            first_subheading_visible = index
            break
    if first_subheading_visible is None:
        return text

    heading_start = first_top_level_visible
    probe = first_top_level_visible - 1
    while probe >= 0 and not lines[probe].strip():
        probe -= 1
    if probe >= 0 and markdown_only_heading_pattern.match((lines[probe] or "").strip()):
        heading_start = probe

    preserved = lines[:first_top_level_visible + 1]
    remainder = lines[first_subheading_visible:]
    return collapse_blank_lines("\n".join(preserved + [""] + remainder))
