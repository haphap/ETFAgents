import re

from etfagents.agents.utils.agent_utils import collapse_blank_lines

_H1_TITLE_PATTERN = re.compile(r"^#\s+\S")
_TITLE_PREFIX_PATTERN = re.compile(r"^(?:#{1,6}\s+)?(?:[一二三四五六七八九十]+、\s*|（[一二三四五六七八九十\d]+）\s*)?")
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


_SELF_REFERENTIAL_META_LEAD_RE = re.compile(
    r"(?m)^\s*(?:（[^）]*）)?\s*"
    r"(?:本节|本部分|该部分|这一节|本段)"
    r"(?:核心结论|锁定|聚焦|讨论|围绕|分析|探讨|旨在|将|主要|重点|结论|说明|指出|表明|认为|阐述|梳理|审视|检视)"
    r"[^\n]*\n?"
)


def strip_self_referential_meta_leads(report: str) -> str:
    """Remove self-referential meta-leads like '本节核心结论指出…' from report text."""
    if not report:
        return ""
    cleaned = _SELF_REFERENTIAL_META_LEAD_RE.sub("", report)
    return collapse_blank_lines(cleaned)


_REFINE_PREAMBLE_RE = re.compile(
    r"(?m)^\s*"
    r"(?:以下是|根据|按照|依据|参照|基于)"
    r"[^。\n]{0,40}"
    r"(?:修正|修订|修改|改进|完善|优化|调整|评审|审核)"
    r"[^。\n]*[。\n]?"
)


def strip_refine_preamble(report: str) -> str:
    """Remove meta-commentary from the refine step, e.g. '以下是根据评审标准修正后的完整报告...'."""
    if not report:
        return ""
    cleaned = _REFINE_PREAMBLE_RE.sub("", report)
    return collapse_blank_lines(cleaned)


