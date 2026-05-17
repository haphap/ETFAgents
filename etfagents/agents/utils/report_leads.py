import re

from etfagents.agents.utils.agent_utils import collapse_blank_lines, normalize_chinese_role_terms

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
    "ETF头部持仓分析报告",
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
_CJK_TEXT_EDGE_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9%）】》。，；：、.!?！？]$")
_CJK_TEXT_START_RE = re.compile(r"^[\u3400-\u9fffA-Za-z0-9（【《。！？；，、,.!?;:]")
_LEADING_PUNCT_RE = re.compile(r"^[。！？；，、,.!?;:]")
TOP_SECTION_MARK_RE = re.compile(r"(?m)^\s*([一二三四五六七八九十])、")
OPENING_STRUCTURE_RE = re.compile(
    r"^\s*(?:"
    r"#{1,6}\s+\S|"
    r"[一二三四五六七八九十]+、|"
    r"（[一二三四五六七八九十\d]+）|"
    r"(?:[-*•]|\d+[.．、)])\s+\S|"
    r"\|"
    r")"
)
OPENING_LABEL_RE = re.compile(r"^\s*(?:概述|结论|核心结论|导语)\s*[:：]")
OPENING_DELIVERY_PREAMBLE_RE = re.compile(
    r"^\s*(?:"
    r"(?:报告|分析|内容).{0,12}(?:已|已经)?(?:就绪|完成|生成|整理好|准备好)[。！!；;，,]?\s*"
    r"(?:以下|下面|现在)"
    r"|(?:数据|资料|信息).{0,12}?(?:已经|已)?(?:全部)?(?:获取|收集|拿到|完成)(?:完毕)?[。！!；;，,]?\s*"
    r"(?:以下|下面|现在).{0,80}?(?:撰写|生成|输出|写).{0,60}?报告"
    r"|以下(?:是|为).{0,60}(?:报告|分析)"
    r")"
)


def first_nonempty_line(text: str) -> str:
    """Return the first non-empty line from generated report text."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return next(
        (line.strip() for line in lines if line.strip()),
        "",
    )


def collect_top_section_marks(text: str) -> set[str]:
    """Return Chinese top-level section marks such as 一/二/三."""
    return set(TOP_SECTION_MARK_RE.findall(text or ""))


def starts_without_overview_paragraph(text: str) -> bool:
    """Detect reports that start with a heading, section, list, or table."""
    first_line = first_nonempty_line(text)
    return bool(first_line and OPENING_STRUCTURE_RE.match(first_line))


def has_invalid_opening_cap(
    text: str,
    *,
    reject_labels: bool = True,
    reject_meta: bool = True,
) -> bool:
    """Detect opening lines that are structural, label-style, or task-description prose."""
    first_line = first_nonempty_line(text)
    if not first_line or OPENING_STRUCTURE_RE.match(first_line):
        return True
    if reject_labels and OPENING_LABEL_RE.match(first_line):
        return True
    if OPENING_DELIVERY_PREAMBLE_RE.match(first_line):
        return True
    if reject_meta and contains_meta_openers(first_line):
        return True
    return False


def contains_markdown_table(text: str) -> bool:
    """Return True when report text includes at least one markdown table row."""
    return any(_looks_like_markdown_table_line(line) for line in (text or "").splitlines())


def get_no_title_instruction() -> str:
    return (
        " Do NOT write a report title or H1 heading. Begin with a 2-4 sentence overview paragraph before section one. "
        "For Chinese reports, write that overview before the first '一、' section; never start directly with '一、', '（一）', a bullet list, or a table. "
        "Do NOT repeat the report subject as a standalone title-like line anywhere in the body, and never construct pseudo-titles from only SH / SZ / HK / BJ or similar exchange suffixes."
    )


def get_topic_and_term_style_instruction() -> str:
    return (
        " Make the opening sentence concise and thesis-led, with the same sharpness a strong title would have, rather than using generic scene-setting. "
        "Do NOT start the opening paragraph with a standalone conclusion label such as '结论：偏多' or '结论：偏空' — weave the directional stance into the body of the paragraph naturally. "
        "Do NOT use '（导语）' as a label before introductory paragraphs. "
        "When explaining technical terms, weave the explanation into the sentence where the term first appears — "
        "do NOT collect multiple term definitions into a single parenthetical block such as '（附首次出现关键术语的白话解释：...）' or '（关键术语交易含义速览：...）'. "
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


def _looks_like_markdown_table_line(line: str) -> bool:
    stripped = (line or "").strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _looks_like_structural_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return True
    if _looks_like_section_heading(stripped) or _looks_like_markdown_table_line(stripped):
        return True
    if _LEADING_LABEL_PREFIX_RE.search(stripped) or _QA_LABEL_RE.search(stripped):
        return True
    if _SELF_REFERENTIAL_META_LEAD_RE.search(stripped) or _META_OPENER_RE.search(stripped):
        return True
    return bool(re.match(r"^(?:[-*+]\s+|\d+[.)、]\s+|>{1,}\s*)", stripped))


def _strip_box_edge_line(line: str) -> str:
    stripped = (line or "").strip()
    if _looks_like_markdown_table_line(stripped):
        return line.rstrip()
    return stripped.strip("│").strip()


def normalize_boxed_text_wrapping(report: str) -> str:
    """Remove leaked TUI box edges and merge accidental hard-wraps in prose."""
    if not report:
        return ""

    raw_lines = report.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    lines = [_strip_box_edge_line(line) for line in raw_lines]
    merged: list[str] = []
    for line in lines:
        if not merged:
            merged.append(line)
            continue

        prev = merged[-1]
        if (
            prev
            and line
            and not _looks_like_structural_line(prev)
            and not _looks_like_structural_line(line)
            and _CJK_TEXT_EDGE_RE.search(prev)
            and _CJK_TEXT_START_RE.match(line)
        ):
            separator = (
                ""
                if _LEADING_PUNCT_RE.match(line.lstrip()) or re.search(r"[。！？；，、]$", prev.rstrip())
                else " "
            )
            merged[-1] = f"{prev.rstrip()}{separator}{line.lstrip()}"
        else:
            merged.append(line)

    return collapse_blank_lines("\n".join(merged))


_SELF_REFERENTIAL_META_LEAD_RE = re.compile(
    r"(?m)^\s*(?:（[^）]*）)?\s*"
    r"(?:本节|本部分|该部分|这一节|本段|本文|本章节)"
    r"(?:核心结论|章节导语|导语|锁定|聚焦|讨论|围绕|分析|探讨|旨在|将|主要|重点|结论|说明|指出|表明|认为|阐述|梳理|审视|检视)"
    r"[^\n]*\n?"
)


def strip_self_referential_meta_leads(report: str) -> str:
    """Remove self-referential meta-leads like '本节核心结论指出…' from report text."""
    if not report:
        return ""
    cleaned = _SELF_REFERENTIAL_META_LEAD_RE.sub("", report)
    return collapse_blank_lines(cleaned)


_LABEL_CUES = (
    "对交易应该怎么做",
    "这意味着什么",
    "这意味著什么",
    "对交易应怎么做",
    "交易该怎么做",
    "交易应该怎么做",
    "交易应怎么做",
    "交易建议",
    "交易指引",
    "交易含义",
    "市场含义",
    "配置含义",
    "判断",
    "概述",
    "证据",
    "合约信号",
    "关键价位",
    "条件情景",
    "结论",
    "核心结论",
    "导语",
    "章节导语",
    "本章节导语",
    "信号总结",
    "章节总结",
    "信号小结",
)

_LEADING_LABEL_PREFIX_RE = re.compile(
    r"(?m)^(\s*(?:#{1,6}\s*)?[▌►▶▸👉]?\s*\*{0,2})"
    r"(?:(?:（|【)?(?:导语|章节导语|本章节导语|信号总结|章节总结|信号小结)(?:）|】)?"
    r"|(?:"
    + "|".join(re.escape(label) for label in _LABEL_CUES)
    + r"))"
    r"(?:\*{0,2}[ \t]*[：:？?][ \t]*|\*{0,2}[ \t]+)"
)

_QA_LABEL_RE = re.compile(
    r"(?m)^\s*(?:#{1,6}\s*)?[▌►▶▸👉]?\s*\*{0,2}"
    r"(?:(?:（|【)?(?:导语|章节导语|本章节导语|信号总结|章节总结|信号小结)(?:）|】)?"
    r"|(?:"
    + "|".join(re.escape(label) for label in _LABEL_CUES)
    + r"))"
    r"(?:\*{0,2}\s*[：:？?]\s*)?\*{0,2}\s*$\n?"
)

_TERM_BLOCK_RE = re.compile(
    r"（(?:附首次出现关键术语|关键术语交易含义速览|关键术语解释|术语速览|术语说明|关键技术[^）]*|技术术语[^）]*|技术指标[^）]*|指标速览[^）]*|指标说明[^）]*)）",
    re.DOTALL,
)
_TERM_DEFINITION_PREAMBLE_RE = re.compile(
    r"为降低.{0,120}(?:技术术语|高频技术术语|术语).{0,80}(?:解释|说明|含义)",
)
_TERM_DEFINITION_LINE_RE = re.compile(
    r"(?:[•·]\s*)?[^：:\n]{1,30}[：:].{0,180}(?:是指|指的是|交易含义|市场含义|配置含义)"
    r"|(?:是指|指的是|交易含义|市场含义|配置含义)"
)
_OPENING_SECTION_MARKER_RE = re.compile(r"(?m)^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]+、")
_OPENING_TERM_EXPLANATION_RE = re.compile(
    r"（[^）]{0,140}(?:"
    r"是指|指的是|即|也就是|意思是|通俗|简单说|简单来说|用于|用来|衡量|反映|代表|表示|"
    r"英文|简称|又称|全称|定义|解释|白话|术语|交易含义"
    r")[^）]{0,140}）"
)
_DECISION_LABEL_LINE_RE = re.compile(
    r"(?im)^\s*"
    r"(?:final allocation proposal|final transaction proposal|execution bias|recommendation|rating|research view"
    r"|最终配置建议|最终交易建议|执行倾向|建议评级|配置评级|研究结论|评级)"
    r"\s*[:：]?\s*\**"
    r"(?:buy|overweight|hold|underweight|sell|买入|增持|持有|减持|卖出)"
    r"\**[。！!？?\s]*$"
)
_DECISION_LABEL_PREFIX_RE = re.compile(
    r"(?im)^\s*"
    r"(?:final allocation proposal|final transaction proposal|execution bias|recommendation|rating|research view"
    r"|最终配置建议|最终交易建议|执行倾向|建议评级|配置评级|研究结论|评级)"
    r"\s*[:：]?\s*\**"
    r"(?:buy|overweight|hold|underweight|sell|买入|增持|持有|减持|卖出)"
    r"\**[。！!？?\s]+"
)

_ARTIFACT_ONLY_LINE_RE = re.compile(r"^[\s│|╭╮╰╯┌┐└┘├┤┬┴┼─━—-]+$")
_INTERROGATIVE_CUE_RE = re.compile(
    r"(?:吗|么|呢|为何|为什么|如何|是否|是不是|能否|可否|会否|多少|几时|几月|几日|哪个|哪些|哪类|哪种|哪一|谁|什么|怎么|怎麽|咋|what|why|how|whether|when|where|which|who)",
    re.IGNORECASE,
)


def strip_qa_labels(report: str) -> str:
    """Remove Q&A-style label lines like '对交易应该怎么做：...' from report text."""
    if not report:
        return ""

    def _strip_label_prefix(match: re.Match) -> str:
        prefix = match.group(1)
        return re.sub(r"^\s*#{1,6}\s*", "", prefix)

    cleaned = _LEADING_LABEL_PREFIX_RE.sub(_strip_label_prefix, report)
    cleaned = _QA_LABEL_RE.sub("", cleaned)
    cleaned = _TERM_BLOCK_RE.sub("", cleaned)
    cleaned = strip_standalone_term_definition_blocks(cleaned)
    return collapse_blank_lines(cleaned)


def _strip_table_artifact_edges(line: str) -> str:
    return (line or "").strip().strip("│|").strip()


def _is_artifact_only_line(line: str) -> bool:
    stripped = (line or "").strip()
    return bool(
        stripped and _ARTIFACT_ONLY_LINE_RE.fullmatch(stripped) and "|" not in stripped
    )


def _starts_with_term_definition_bullet(text: str) -> bool:
    return bool(re.match(r"^\s*[•·]", text or ""))


def strip_standalone_term_definition_blocks(report: str) -> str:
    """Remove standalone glossary-style blocks while preserving inline explanations."""
    if not report:
        return ""

    lines = report.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    kept: list[str] = []
    skipping = False
    saw_blank_after_block = False

    for line in lines:
        content = _strip_table_artifact_edges(line)

        if not skipping and _TERM_DEFINITION_PREAMBLE_RE.search(content):
            skipping = True
            saw_blank_after_block = False
            continue

        if skipping:
            if _looks_like_section_heading(content):
                skipping = False
                kept.append(line)
                continue
            if not content or _is_artifact_only_line(line):
                saw_blank_after_block = True
                continue
            if saw_blank_after_block:
                if _starts_with_term_definition_bullet(content) and _TERM_DEFINITION_LINE_RE.search(content):
                    continue
                skipping = False
                kept.append(line)
                continue
            if _TERM_DEFINITION_LINE_RE.search(content):
                continue
            skipping = False
            kept.append(line)
            continue

        kept.append(line)

    return collapse_blank_lines("\n".join(kept))


def strip_opening_term_explanations(report: str) -> str:
    """Remove parenthetical term explanations from the opening cap paragraph."""
    if not report:
        return ""

    match = _OPENING_SECTION_MARKER_RE.search(report)
    if not match:
        return collapse_blank_lines(_OPENING_TERM_EXPLANATION_RE.sub("", report))

    opening = report[: match.start()]
    rest = report[match.start() :]
    opening = _OPENING_TERM_EXPLANATION_RE.sub("", opening)
    return collapse_blank_lines(opening + rest)


def strip_decision_label_artifacts(report: str) -> str:
    """Remove leaked recommendation labels such as FINAL TRANSACTION PROPOSAL / 最终配置建议."""
    if not report:
        return ""
    cleaned = _DECISION_LABEL_LINE_RE.sub("", report)
    cleaned = _DECISION_LABEL_PREFIX_RE.sub("", cleaned)
    return collapse_blank_lines(cleaned)


_REFINE_PREAMBLE_RE = re.compile(
    r"(?m)^\s*"
    r"(?:以下是|根据|按照|依据|参照|基于)"
    r"[^\n]{0,160}"
    r"(?:修正|修订|修改|改进|完善|优化|调整|评审|审核)"
    r"[^\n]*\n?"
)
_REPORT_PROCESS_PREAMBLE_RE = re.compile(
    r"(?m)^\s*"
    r"(?:数据|资料|信息).{0,12}?(?:已经|已)?(?:全部)?(?:获取|收集|拿到|完成)(?:完毕)?[。！!；;，,]?\s*"
    r"(?:以下|下面|现在).{0,80}?(?:撰写|生成|输出|写).{0,60}?报告[。！!；;，,]?\s*"
)
_PROMPT_INSTRUCTION_LEAK_RE = re.compile(
    r"(?m)^\s*(?:直接进入正文|Start directly with (?:your )?(?:argument|body|report))"
    r"[。.!！]?\s*$\n?"
)

_META_OPENER_RE = re.compile(
    r"(?m)^\s*"
    r"(?:本报告(?:将|围绕|聚焦|基于|对[^\n]{0,80}(?:进行|展开))|本分析(?:将|围绕|聚焦|基于|对[^\n]{0,80}(?:进行|展开))|本文(?:将|围绕|聚焦|基于)|下文(?:将|围绕|聚焦)"
    r"|This report(?: provides| aims| reviews| analyzes| focuses on)|This analysis(?: provides| aims| reviews| presents| focuses on)?)"
    r"[^\n]*\n?"
)


def _strip_leading_artifact_lines(report: str) -> str:
    lines = (report or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    first_content = 0
    while first_content < len(lines):
        stripped = lines[first_content].strip()
        if not stripped or _is_artifact_only_line(stripped):
            first_content += 1
            continue
        break
    return collapse_blank_lines("\n".join(lines[first_content:]))


def strip_artifact_only_lines(report: str) -> str:
    """Remove standalone separator / box-art lines anywhere in generated reports."""
    if not report:
        return ""
    kept = [
        line
        for line in report.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        if not _is_artifact_only_line(line)
    ]
    return collapse_blank_lines("\n".join(kept))


def strip_refine_preamble(report: str) -> str:
    """Remove meta-commentary from the refine step, e.g. '以下是根据评审标准修正后的完整报告...'."""
    if not report:
        return ""
    cleaned = _REFINE_PREAMBLE_RE.sub("", report)
    cleaned = _REPORT_PROCESS_PREAMBLE_RE.sub("", cleaned)
    cleaned = _PROMPT_INSTRUCTION_LEAK_RE.sub("", cleaned)
    cleaned = strip_artifact_only_lines(cleaned)
    return _strip_leading_artifact_lines(cleaned)


def strip_meta_openers(report: str) -> str:
    """Remove meta-description openers like '本报告将…', '本分析基于…', 'This report provides...'."""
    if not report:
        return ""
    cleaned = _META_OPENER_RE.sub("", report)
    return _strip_leading_artifact_lines(cleaned)


def strip_declarative_question_marks(report: str) -> str:
    """Turn stray declarative sentence-ending question marks into periods."""
    if not report:
        return ""

    def _replace(match: re.Match) -> str:
        sentence = match.group(1)
        if _INTERROGATIVE_CUE_RE.search(sentence) or _looks_like_section_heading(sentence.strip()):
            return match.group(0)
        return f"{sentence}。"

    cleaned = re.sub(r"([^\n。！？!?]{2,})[？?]", _replace, report)
    return collapse_blank_lines(cleaned)


def contains_qa_label_artifacts(report: str) -> bool:
    """Public detector: True when QA-label structures (judgement / evidence / etc.) appear."""
    if not report:
        return False
    if _LEADING_LABEL_PREFIX_RE.search(report):
        return True
    if _QA_LABEL_RE.search(report):
        return True
    if _TERM_BLOCK_RE.search(report):
        return True
    return any(
        _TERM_DEFINITION_PREAMBLE_RE.search(_strip_table_artifact_edges(line))
        for line in report.splitlines()
    )


def contains_self_referential_meta_leads(report: str) -> bool:
    """Public detector: True when self-referential leads (本节锁定…) appear."""
    if not report:
        return False
    return bool(_SELF_REFERENTIAL_META_LEAD_RE.search(report))


def contains_meta_openers(report: str) -> bool:
    """Public detector: True when 本报告将… / This report provides… style openers appear."""
    if not report:
        return False
    return bool(_META_OPENER_RE.search(report))


def pre_judge_clean(report: str) -> str:
    """Idempotent regex cleanups that should run BEFORE the LLM judge / refine.

    Stripping these artifacts up front avoids triggering the judge on issues we
    can already fix locally (refine preambles, H1 titles, QA labels, self-referential
    meta-leads, generic ``本报告将…`` openers). Running this pass before validation
    keeps the judge focused on substantive content quality.
    """
    if not report:
        return ""
    cleaned = normalize_boxed_text_wrapping(report)
    cleaned = strip_refine_preamble(cleaned)
    cleaned = strip_report_title(cleaned)
    cleaned = strip_qa_labels(cleaned)
    cleaned = strip_opening_term_explanations(cleaned)
    cleaned = strip_decision_label_artifacts(cleaned)
    cleaned = strip_meta_openers(cleaned)
    cleaned = strip_self_referential_meta_leads(cleaned)
    return collapse_blank_lines(cleaned)


def post_judge_clean(report: str) -> str:
    """Cleanups that should run AFTER the LLM refine step.

    Re-runs ``pre_judge_clean`` (idempotent) so any artifact reintroduced by the
    refine call is normalised, then performs the punctuation pass that should
    only happen on the final output to avoid corrupting question-style headings
    inside the original report.
    """
    if not report:
        return ""
    cleaned = pre_judge_clean(report)
    cleaned = normalize_chinese_role_terms(cleaned)
    cleaned = strip_declarative_question_marks(cleaned)
    return collapse_blank_lines(cleaned)


def clean_generated_report(report: str) -> str:
    """Backward-compatible alias covering ``pre_judge_clean`` + ``post_judge_clean``.

    Existing call sites that wrap the entire pipeline in a single post-pass keep
    working unchanged. New analyst pipelines should call ``pre_judge_clean``
    before ``validate_and_refine`` and ``post_judge_clean`` after, to avoid the
    LLM judge being triggered on artifacts the regex layer can fix locally.
    """
    if not report:
        return ""
    return post_judge_clean(report)
