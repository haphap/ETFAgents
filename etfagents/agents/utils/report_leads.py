import re

from etfagents.agents.utils.agent_utils import collapse_blank_lines

_H1_TITLE_PATTERN = re.compile(r"^#\s+\S")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_TITLE_PREFIX_PATTERN = re.compile(r"^(?:#{1,6}\s+)?(?:[一二三四五六七八九十]+、\s*|（[一二三四五六七八九十\d]+）\s*)?")
_TOP_LEVEL_VISIBLE_HEADING_PATTERN = re.compile(r"^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]+、")
_VISIBLE_SECTION_HEADING_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十\d]+）)"
)
_ENGLISH_HEADING_TRAILER_PATTERN = re.compile(
    r"\s*[\(（][^()（）\n]*[A-Za-z][^()（）\n]*[\)）]\s*$"
)
_INVALID_DISPLAY_TICKERS = {"SH", "SZ", "BJ", "HK", "SS", "SSE", "SZSE", "BSE", "HKG", "SEHK"}
_PSEUDO_TITLE_SUBJECTS = (
    "技术面与资金流综合诊断",
    "舆情与事件影响分析",
    "宏观框架分析",
    "中观商品宏观策略报告",
    "持仓行业研究分析",
    "头部持仓研究分析",
    "Technical & Flow Diagnosis",
    "Sentiment & Catalyst Impact Analysis",
    "Macro Regime Analysis",
    "Meso Commodity Macro Strategy Report",
    "Holdings Industry Research Analysis",
    "Top Holdings Research Analysis",
)
_INVALID_EXCHANGE_ONLY_PREFIX_PATTERN = re.compile(
    r"^(?:BJ|BSE|HKG|HK|SEHK|SH|SS|SSE|SZ|SZSE)[:：\s]+(.+)$"
)
_QUALIFIED_TICKER_PREFIX_PATTERN = re.compile(
    r"^(?=[A-Z0-9.]*\d)[A-Z0-9]+(?:\.[A-Z]+)?\s+(.+)$"
)
_EXCHANGE_ONLY_PSEUDO_TITLE_PATTERN = re.compile(
    r"(?m)^\s*(?:#{1,6}\s*)?"
    r"(?:[一二三四五六七八九十]+、\s*|（[一二三四五六七八九十\d]+）\s*)?"
    r"(?:BJ|BSE|HKG|HK|SEHK|SH|SS|SSE|SZ|SZSE)"
    r"(?=[^\n]{0,160}[:：])[^\n]{0,160}?"
    r"(?:"
    + "|".join(re.escape(subject) for subject in _PSEUDO_TITLE_SUBJECTS)
    + r")\s*$"
)
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
_LEAD_META_PHRASE_PATTERN = re.compile(
    r"(?m)^(?:"
    r"本部分(?:结论)?直接(?:呈现|概括|说明)"
    r"|该部分(?:结论)?直接(?:呈现|概括|说明)"
    r"|这一部分(?:结论)?直接(?:呈现|概括|说明)"
    r"|本节(?:结论)?直接(?:呈现|概括|说明)"
    r"|该节(?:结论)?直接(?:呈现|概括|说明)"
    r"|这一节(?:结论)?直接(?:呈现|概括|说明)"
    r"|本部分通过"
    r"|该部分通过"
    r"|这一部分通过"
    r"|本节通过"
    r"|该节通过"
    r"|这一节通过"
    r"|本节(?:锁定|聚焦(?:于)?|关注|围绕|讨论|转向|观察|拆解|检验)"
    r"|该节(?:锁定|聚焦(?:于)?|关注|围绕|讨论|转向|观察|拆解|检验)"
    r"|这一节(?:锁定|聚焦(?:于)?|关注|围绕|讨论|转向|观察|拆解|检验)"
    r"|This section directly (?:presents|states|summarizes)"
    r"|This section (?:uses|through)"
    r")\s*"
)


def strip_meta_lead_prefixes(report: str) -> str:
    if not report:
        return ""
    stripped = _LEAD_META_PREFIX_PATTERN.sub("", report)
    return _LEAD_META_PHRASE_PATTERN.sub("", stripped)


def get_title_body_guard_instruction() -> str:
    return (
        " After the H1 title and its title lead, do NOT repeat the title anywhere in the body. "
        "Never insert title-like lines such as '一、SH 科创50ETF华夏：技术面与资金流综合诊断', "
        "'HK：科创50ETF华夏：技术面与资金流综合诊断', or similar exchange-only variants. "
        "If the full exchange-qualified ticker is unavailable, omit the ticker rather than constructing a pseudo-title from only SH / SZ / HK / BJ or similar exchange suffixes."
    )


def get_no_title_instruction() -> str:
    return (
        " Do NOT write a report title or H1 heading. Start directly with a 2-4 sentence overview paragraph before section one. "
        "Do NOT repeat the report subject as a standalone title-like line anywhere in the body, and never construct pseudo-titles from only SH / SZ / HK / BJ or similar exchange suffixes."
    )


def get_topic_and_term_style_instruction() -> str:
    return (
        " Make the opening sentence concise and thesis-led, with the same sharpness a strong title would have, rather than using generic scene-setting. "
        "In Chinese output, do NOT lean on a single repeated word such as '反噬'; vary the wording with precise alternatives like '利润挤压', '成本倒逼', '负反馈', '传导受阻', or '盈利受压' when the context fits."
    )


def get_concise_heading_instruction() -> str:
    return (
        " Top-level and second-level headings must be concise, specific, and point directly to the content of that section. "
        "You MUST use the exact section headings specified in the report structure above. "
        "Do NOT substitute generic labels such as '总体研判', '深度分析', '风险与催化', or '总结' "
        "when the structure already provides a precise heading for that section. "
        "If the structure does not provide a heading, write one that is brief, forceful, and immediately usable. "
        "In Chinese output, top-level and second-level headings must stay in plain Chinese and must NOT append English translations or notes in parentheses. "
        "Do NOT output code blocks, JSON, dictionary mappings, variable assignments, or any programming-language structure. "
        "Each heading should appear directly in the report as readable text, not as configuration. "
        "Use '一、' for top-level headings and '（一）' for second-level headings."
    )


def strip_exchange_only_pseudo_titles(report: str) -> str:
    if not report:
        return ""
    return collapse_blank_lines(_EXCHANGE_ONLY_PSEUDO_TITLE_PATTERN.sub("", report))


def _normalize_heading_key(line: str) -> str:
    stripped = _ENGLISH_HEADING_TRAILER_PATTERN.sub("", (line or "").strip()).strip()
    return re.sub(r"\s+", " ", stripped)


def normalize_chinese_section_headings(
    report: str,
    *,
    strip_english_for_subheadings: bool = True,
) -> str:
    if not report:
        return ""

    heading_pattern = (
        _VISIBLE_SECTION_HEADING_PATTERN
        if strip_english_for_subheadings
        else _TOP_LEVEL_VISIBLE_HEADING_PATTERN
    )
    cleaned_lines: list[str] = []
    pending_top_level_heading: str | None = None

    for raw_line in report.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw_line
        stripped = (line or "").strip()
        if heading_pattern.match(stripped):
            line = _ENGLISH_HEADING_TRAILER_PATTERN.sub("", line).rstrip()
            stripped = line.strip()

        if _TOP_LEVEL_VISIBLE_HEADING_PATTERN.match(stripped):
            heading_key = _normalize_heading_key(stripped)
            if pending_top_level_heading == heading_key:
                continue
            pending_top_level_heading = heading_key
        elif stripped:
            pending_top_level_heading = None

        cleaned_lines.append(line)

    return collapse_blank_lines("\n".join(cleaned_lines))


def _looks_like_report_title_line(line: str) -> bool:
    normalized = _normalize_title_candidate(line)
    if not normalized or _looks_like_section_heading(normalized):
        return False
    lowered = normalized.lower()
    return any(subject.lower() in lowered for subject in _PSEUDO_TITLE_SUBJECTS)


def strip_report_title(report: str) -> str:
    text = strip_exchange_only_pseudo_titles(report)
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    first_nonempty = 0
    while first_nonempty < len(lines) and not lines[first_nonempty].strip():
        first_nonempty += 1
    if first_nonempty >= len(lines):
        return ""

    first_line = lines[first_nonempty].strip()
    if _H1_TITLE_PATTERN.match(first_line) or _looks_like_report_title_line(first_line):
        del lines[first_nonempty]
    return collapse_blank_lines("\n".join(lines[first_nonempty:]))


def ensure_h1_title(report: str, title: str) -> str:
    if not report:
        return f"# {title}"

    text = report.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return f"# {title}"

    lines = text.splitlines()
    first_nonempty = 0
    while first_nonempty < len(lines) and not lines[first_nonempty].strip():
        first_nonempty += 1

    if first_nonempty < len(lines):
        first_line = lines[first_nonempty].strip()
        if _H1_TITLE_PATTERN.match(first_line):
            lines[first_nonempty] = f"# {title}"
            return strip_exchange_only_pseudo_titles(_remove_duplicate_title_lines(
                collapse_blank_lines("\n".join(lines[first_nonempty:])),
                title,
            ))
        if _looks_like_duplicated_title_heading(first_line, title):
            lines[first_nonempty] = f"# {title}"
            return strip_exchange_only_pseudo_titles(_remove_duplicate_title_lines(
                collapse_blank_lines("\n".join(lines[first_nonempty:])),
                title,
            ))

    return strip_exchange_only_pseudo_titles(_remove_duplicate_title_lines(
        collapse_blank_lines(f"# {title}\n\n{text}"),
        title,
    ))


def _normalize_title_candidate(text: str) -> str:
    candidate = _TITLE_PREFIX_PATTERN.sub("", (text or "").strip())
    return re.sub(r"\s+", " ", candidate).strip()


def _strip_invalid_ticker_prefix(text: str) -> str:
    normalized = _normalize_title_candidate(text)
    parts = re.split(r"[:：]", normalized, maxsplit=1)
    if len(parts) != 2:
        return normalized
    prefix, remainder = parts[0].strip().upper(), parts[1].strip()
    if prefix in _INVALID_DISPLAY_TICKERS:
        return remainder
    return normalized


def _strip_exchange_only_prefix(text: str) -> str:
    normalized = _normalize_title_candidate(text)
    match = _INVALID_EXCHANGE_ONLY_PREFIX_PATTERN.match(normalized)
    if match:
        return match.group(1).strip()
    return normalized


def _strip_qualified_ticker_prefix(text: str) -> str:
    normalized = _normalize_title_candidate(text)
    match = _QUALIFIED_TICKER_PREFIX_PATTERN.match(normalized)
    if match:
        return match.group(1).strip()
    return normalized


def _strip_title_subject_prefix(text: str) -> str:
    normalized = _normalize_title_candidate(text)
    parts = re.split(r"[:：]", normalized, maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()
    return normalized


def _looks_like_duplicated_title_heading(line: str, title: str) -> bool:
    normalized_line = _normalize_title_candidate(line)
    normalized_title = _normalize_title_candidate(title)
    if not normalized_line or not normalized_title:
        return False
    line_variants = {
        normalized_line,
        _strip_invalid_ticker_prefix(normalized_line),
        _strip_exchange_only_prefix(normalized_line),
        _strip_title_subject_prefix(normalized_line),
    }
    title_variants = {
        normalized_title,
        _strip_qualified_ticker_prefix(normalized_title),
        _strip_title_subject_prefix(normalized_title),
    }
    return any(
        line_variant and title_variant and line_variant == title_variant
        for line_variant in line_variants
        for title_variant in title_variants
    )


def _remove_duplicate_title_lines(report: str, title: str) -> str:
    lines = (report or "").splitlines()
    if not lines:
        return ""

    cleaned = [lines[0]]
    for line in lines[1:]:
        if _looks_like_duplicated_title_heading(line.strip(), title):
            continue
        cleaned.append(line)
    return collapse_blank_lines("\n".join(cleaned))


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
    if not lines:
        return text

    first_body_line = 0
    if _H1_TITLE_PATTERN.match(lines[0].strip()):
        first_body_line = 1
        while first_body_line < len(lines) and not lines[first_body_line].strip():
            first_body_line += 1
    if first_body_line >= len(lines) or not _looks_like_section_heading(lines[first_body_line]):
        return text

    default_lead = chinese_default_lead if _CJK_PATTERN.search(text) else english_default_lead
    return collapse_blank_lines(
        "\n".join(lines[:first_body_line] + [default_lead, ""] + lines[first_body_line:])
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
