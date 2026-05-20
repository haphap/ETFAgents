import copy
from typing import Optional
import datetime
import json
import typer
from pathlib import Path
from functools import wraps
import re
from rich.console import Console
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.columns import Columns
from rich.markdown import Markdown
from rich.layout import Layout
from rich.text import Text
from rich.table import Table
from collections import deque
import time
from rich.tree import Tree
from rich import box
from rich.align import Align
from rich.rule import Rule
from urllib.parse import urlparse

from etfagents.graph.etf_graph import EtfAgentsGraph
from etfagents.agents.utils.analysis_memory import AnalysisMemoryStore
from etfagents.default_config import DEFAULT_CONFIG
from cli.models import AnalystType
from cli.utils import *
from cli.announcements import fetch_announcements, display_announcements
from cli.stats_handler import StatsCallbackHandler
from etfagents.content_utils import contains_cjk
from etfagents.agents.utils.agent_utils import (
    collapse_blank_lines,
    extract_analyst_decision_summary,
    extract_feedback_snapshot,
    get_output_language,
    localize_role_name,
    make_display_snapshot,
    normalize_chinese_manager_terms,
    normalize_chinese_role_terms,
    normalize_visible_debate_body,
    strip_analyst_decision_summary,
    strip_all_feedback_snapshots,
    strip_feedback_snapshot,
    strip_role_prefix,
    strip_second_person_heading_prefix,
)
from etfagents.agents.utils.report_leads import (
    strip_exchange_only_pseudo_titles,
    strip_refine_preamble,
)
from etfagents.agents.utils.state_keys import (
    CANONICAL_TO_LEGACY_STATE_KEYS,
    canonical_state_key,
    get_state_value,
)

console = Console()

app = typer.Typer(
    name="ETFAgents",
    help="ETFAgents CLI: Multi-Agents LLM ETF Investment Framework",
    add_completion=True,  # Enable shell completion
    pretty_exceptions_show_locals=False,
)
memory_app = typer.Typer(help="Structured analysis memory utilities.")
app.add_typer(memory_app, name="memory")

from cli.commands.cache import cache_app
app.add_typer(cache_app, name="cache")


def save_backtest_result(result, output_dir):
    from etfagents.backtest import save_backtest_result as _save_backtest_result

    return _save_backtest_result(result, output_dir)


CHINESE_OUTPUT_VALUES = {"chinese", "中文", "zh", "zh-cn", "zh-hans"}
MEMORY_MODE_VALUES = {"disabled", "continuity-only", "lesson", "full"}

CLI_SECTION_TITLES = {
    "market_flow_report": ("Market & Flow Analysis", "市场与资金流分析"),
    "catalyst_sentiment_report": ("Sentiment & Catalyst Impact Analysis", "舆情与事件影响分析"),
    "macro_regime_report": ("Macro Regime Analysis", "宏观框架分析"),
    "meso_commodity_report": ("Meso Commodity Analysis", "中观大宗商品分析"),
    "holdings_industry_report": ("ETF Holdings-Industry Research", "ETF持仓行业研究"),
    "top_holdings_report": ("ETF Top Holdings Research", "ETF头部持仓研究"),
    "research_allocation_plan": ("Research Team Allocation View", "研究团队配置观点"),
    "trader_allocation_plan": ("ETF Allocation Plan", "ETF配置计划"),
    "final_allocation_decision": ("Portfolio Allocation Decision", "投资组合配置决策"),
}

ANALYST_KEY_ALIASES = {
    "market": "market_flow",
    "etf_flow": "market_flow",
    "social": "catalyst_sentiment",
    "news": "macro_regime",
    "fundamentals": "meso_commodity",
    "etf_structure": "meso_commodity",
    "broker_research": "holdings_industry",
    "etf_macro": "holdings_industry",
    "stock_research": "top_holdings",
}

AGENT_NAME_ALIASES = {
    "Market Analyst": "Market & Flow Analyst",
    "Social Analyst": "Sentiment & Catalyst Analyst",
    "Macro Analyst": "Macro Regime Analyst",
    "Sentiment & Catalyst Analyst": "Sentiment & Catalyst Analyst",
    "Macro Regime Analyst": "Macro Regime Analyst",
    "Fundamentals Analyst": "Meso Commodity Analyst",
    "Commodity Analyst": "Meso Commodity Analyst",
    "Industry Research Analyst": "ETF Holdings-Industry Research Analyst",
    "ETF Industry Research Analyst": "ETF Holdings-Industry Research Analyst",
    "ETF Holdings-Industry Research Analyst": "ETF Holdings-Industry Research Analyst",
    "Broker Research Analyst": "ETF Holdings-Industry Research Analyst",
    "Stock Research Analyst": "ETF Top Holdings Research Analyst",
    "ETF Flow Analyst": "Market & Flow Analyst",
    "ETF Macro Analyst": "ETF Holdings-Industry Research Analyst",
    "ETF Top Holdings Research Analyst": "ETF Top Holdings Research Analyst",
}


def _normalize_analyst_key(key: str) -> str:
    lowered = (key or "").lower()
    return ANALYST_KEY_ALIASES.get(lowered, lowered)

_CHINESE_SECTION_NUMERALS = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def _is_chinese_output() -> bool:
    return get_output_language().strip().lower() in CHINESE_OUTPUT_VALUES


def _localize_cli_label(english: str, chinese: str) -> str:
    return chinese if _is_chinese_output() else english


def _localize_cli_role_title(role: str) -> str:
    return localize_role_name(role) if _is_chinese_output() else role


def _localize_cli_section_title(section_name: str) -> str:
    english, chinese = CLI_SECTION_TITLES.get(section_name, (section_name, section_name))
    return _localize_cli_label(english, chinese)


def _normalize_memory_mode(value: str) -> str:
    normalized = (value or DEFAULT_CONFIG.get("memory_mode", "full")).strip().lower()
    if normalized not in MEMORY_MODE_VALUES:
        raise typer.BadParameter(
            f"memory-mode must be one of: {', '.join(sorted(MEMORY_MODE_VALUES))}"
        )
    return normalized


def _relevel_markdown_headings(content: str, target_min_level: int) -> str:
    """Shift markdown headings so embedded reports preserve nested hierarchy."""
    text = (content or "").strip()
    if not text:
        return ""

    heading_pattern = re.compile(r"(?m)^(#{1,6})(\s+)")
    levels = [len(match.group(1)) for match in heading_pattern.finditer(text)]
    if not levels:
        return text

    offset = max(0, target_min_level - min(levels))
    if offset == 0:
        return text

    def _replace(match: re.Match[str]) -> str:
        level = min(6, len(match.group(1)) + offset)
        return f"{'#' * level}{match.group(2)}"

    return heading_pattern.sub(_replace, text)


def _strip_heading_number_prefix(text: str) -> str:
    stripped = (text or "").strip()
    patterns = (
        r"^#{1,6}\s*",
        r"^[一二三四五六七八九十]+、\s*",
        r"^（[一二三四五六七八九十]+）\s*",
        r"^\d+(?:\.\d+)*\.?\s*",
        r"^[（(]\d+[）)]\s*",
        r"^[①②③④⑤⑥⑦⑧⑨⑩]\s*",
    )
    for pattern in patterns:
        stripped = re.sub(pattern, "", stripped)
    return stripped.strip()


def _clean_report_heading_text(text: str) -> str:
    return strip_second_person_heading_prefix(_strip_heading_number_prefix(text))


_STREAM_STATE_KEYS = {
    *CANONICAL_TO_LEGACY_STATE_KEYS.keys(),
    *(
        legacy
        for legacy_keys in CANONICAL_TO_LEGACY_STATE_KEYS.values()
        for legacy in legacy_keys
    ),
    "investment_debate_state",
    "risk_debate_state",
    "trader_backtest_signal",
    "portfolio_backtest_signal",
    "backtest_signal",
    "analysis_memory_entry",
}


def _looks_like_state_delta(value: object) -> bool:
    return isinstance(value, dict) and any(
        canonical_state_key(str(key)) in _STREAM_STATE_KEYS or str(key) in _STREAM_STATE_KEYS
        for key in value
    )


def _iter_stream_state_updates(update: dict):
    if not isinstance(update, dict):
        return
    yield update
    for value in update.values():
        if _looks_like_state_delta(value):
            yield value


def _chunk_state_value(chunk: dict, key: str, default=None):
    for update in _iter_stream_state_updates(chunk):
        value = get_state_value(update, key, None)
        if value not in (None, ""):
            return value
    return default


def _merge_stream_state(accumulated: dict, update: dict, *, filter_state_keys: bool = True) -> dict:
    """Keep non-empty values from earlier stream chunks for final report output."""
    if not isinstance(update, dict):
        return accumulated

    for state_update in _iter_stream_state_updates(update):
        for raw_key, value in state_update.items():
            key = canonical_state_key(raw_key)
            if value in (None, ""):
                continue
            if filter_state_keys and key not in _STREAM_STATE_KEYS:
                continue
            if isinstance(value, dict) and isinstance(accumulated.get(key), dict):
                _merge_stream_state(
                    accumulated[key],
                    value,
                    filter_state_keys=False,
                )
                continue
            accumulated[key] = copy.deepcopy(value)
    return accumulated


_PLAIN_TOP_LEVEL_HEADING_PATTERN = re.compile(
    r"^([ \t]*)([一二三四五六七八九十]+、)\s*(\S.*)$"
)
_PLAIN_SECOND_LEVEL_HEADING_PATTERN = re.compile(
    r"^([ \t]*)(（[一二三四五六七八九十\d]+）)\s*(\S.*)$"
)
_SENTENCE_STYLE_SECTION_PUNCTUATION_RE = re.compile(r"[。！？!?；;]")
_LOOSE_ARABIC_LIST_ITEM_PATTERN = re.compile(
    r"^([ \t]{0,6})(\d{1,2})(?![\d.)、．])\s+(?!月|日|年|时|分|秒|%|％|亿|万|千|个)(\S.*)$",
    re.MULTILINE,
)
_ARABIC_LIST_ITEM_LINE_PATTERN = re.compile(r"^\s*\d+(?:[.)、．]|\s)\s+\S")
_WRAPPED_ETF_NAME_CODE_PATTERN = re.compile(
    r"(?m)^([^\n。！？!?；;：:]{2,80}(?:ETF|基金)[^\n。！？!?；;：:]{0,40})[ \t]*\n(?:[ \t]*\n)?[ \t]*"
    r"([（(]\d{6}(?:\.(?:SH|SZ|BJ))?[）)]\S*)"
)


def _looks_like_plain_numbered_heading(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _VISIBLE_ORDINAL_CONTINUATION_PATTERN.match(stripped):
        return False
    for pattern in (_PLAIN_TOP_LEVEL_HEADING_PATTERN, _PLAIN_SECOND_LEVEL_HEADING_PATTERN):
        match = pattern.match(stripped)
        if not match:
            continue
        body = match.group(3).strip()
        return bool(body) and not _SENTENCE_STYLE_SECTION_PUNCTUATION_RE.search(body)
    return False


def _normalize_loose_arabic_list_markers(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text or not _is_chinese_output():
        return text
    return _LOOSE_ARABIC_LIST_ITEM_PATTERN.sub(r"\1\2. \3", text)


def _join_wrapped_etf_name_code(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text or not _is_chinese_output():
        return text
    return _WRAPPED_ETF_NAME_CODE_PATTERN.sub(r"\1\2", text)


def _strip_sentence_like_section_prefixes_in_lists(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text or not _is_chinese_output():
        return text

    lines = text.split("\n")
    nonempty_indices = [index for index, line in enumerate(lines) if line.strip()]
    for position, index in enumerate(nonempty_indices):
        line = lines[index]
        stripped = line.strip()
        if not stripped or _looks_like_plain_numbered_heading(stripped):
            continue

        match = None
        for pattern in (_PLAIN_TOP_LEVEL_HEADING_PATTERN, _PLAIN_SECOND_LEVEL_HEADING_PATTERN):
            match = pattern.match(stripped)
            if match:
                break
        if not match:
            continue

        previous_line = lines[nonempty_indices[position - 1]].strip() if position > 0 else ""
        next_line = (
            lines[nonempty_indices[position + 1]].strip()
            if position + 1 < len(nonempty_indices)
            else ""
        )
        if not (
            _ARABIC_LIST_ITEM_LINE_PATTERN.match(previous_line)
            or _ARABIC_LIST_ITEM_LINE_PATTERN.match(next_line)
        ):
            continue

        leading_whitespace = re.match(r"^\s*", line).group(0)
        lines[index] = f"{leading_whitespace}{match.group(3).strip()}"
    return "\n".join(lines)


def _format_heading_prefix(depth: int, index: int) -> str:
    if depth == 0 and 1 <= index <= len(_CHINESE_SECTION_NUMERALS):
        return f"{_CHINESE_SECTION_NUMERALS[index - 1]}、"
    if depth == 1 and 1 <= index <= len(_CHINESE_SECTION_NUMERALS):
        return f"（{_CHINESE_SECTION_NUMERALS[index - 1]}）"
    if depth == 2:
        return f"{index}. "
    if depth == 3:
        return f"({index}) "
    if depth == 4 and 1 <= index <= 10:
        circled = "①②③④⑤⑥⑦⑧⑨⑩"
        return f"{circled[index - 1]} "
    return ""


def _normalize_report_heading_numbering(content: str) -> str:
    text = (content or "").strip()
    if not text or not _is_chinese_output():
        return text

    heading_pattern = re.compile(r"(?m)^(#{1,6})(\s+)(.+)$")
    matches = list(heading_pattern.finditer(text))
    if not matches:
        return text

    levels = [len(match.group(1)) for match in matches]
    unique_levels = sorted(set(levels))
    min_level = min(unique_levels)
    min_level_count = sum(level == min_level for level in levels)
    has_deeper_levels = any(level > min_level for level in levels)
    first_min_heading = next(
        (match.group(3).strip() for match in matches if len(match.group(1)) == min_level),
        "",
    )
    first_min_is_numbered_section = bool(
        re.match(r"^(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十\d]+）)", first_min_heading)
    )
    title_level = (
        min_level
        if min_level_count == 1 and has_deeper_levels and not first_min_is_numbered_section
        else None
    )
    numbered_levels = [level for level in unique_levels if level != title_level]
    if not numbered_levels:
        return text

    level_to_depth = {level: idx for idx, level in enumerate(numbered_levels)}
    counters = [0] * max(5, len(numbered_levels))

    def _replace(match: re.Match[str]) -> str:
        level = len(match.group(1))
        spacing = match.group(2)
        heading_text = match.group(3).strip()
        if level == title_level or level not in level_to_depth:
            return match.group(0)

        depth = level_to_depth[level]
        if depth > 4:
            return match.group(0)

        counters[depth] += 1
        for idx in range(depth + 1, len(counters)):
            counters[idx] = 0

        prefix = _format_heading_prefix(depth, counters[depth])
        clean_heading = _clean_report_heading_text(heading_text)
        return f"{match.group(1)}{spacing}{prefix}{clean_heading}"

    return heading_pattern.sub(_replace, text)


_REPORT_HEADING_LINE_PATTERN = re.compile(r"^\s*#{1,6}\s+\S")
_VISIBLE_SECTION_LINE_PATTERN = re.compile(
    r"^\s*(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十\d]+）)\s*\S"
)
_VISIBLE_ORDINAL_CONTINUATION_PATTERN = re.compile(
    r"^\s*[一二三四五六七八九十]+、[一二三四五六七八九十\d]+轮"
)
_WRAPPED_ORDINAL_ROUND_PHRASE_RE = re.compile(
    r"(在第)\s*\n+\s*([一二三四五六七八九十]+、[一二三四五六七八九十\d]+轮)"
)
_VISIBLE_SECTION_MARKER = r"(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十\d]+）)"
_ORPHAN_VISIBLE_SECTION_MARKER_LINE_PATTERN = re.compile(
    rf"^([ \t]*)({_VISIBLE_SECTION_MARKER})\s*$"
)
_INLINE_VISIBLE_SECTION_PATTERN = re.compile(
    rf"([。！？；：:])\s*({_VISIBLE_SECTION_MARKER}\s*\S)"
)
_INLINE_MARKDOWN_VISIBLE_SECTION_PATTERN = re.compile(
    rf"(?<=[^#\n])[ \t]*#{{1,6}}[ \t]*(?={_VISIBLE_SECTION_MARKER}\s*\S)"
)
_INLINE_SPACED_SUBSECTION_PATTERN = re.compile(
    r"(?<=[^#\s\n])[\t ]+(?=（[一二三四五六七八九十\d]+）\s*\S)"
)
_INLINE_TOP_TO_SUBSECTION_PATTERN = re.compile(
    r"(?m)^(\s*(?:#{1,6}\s*)?[一二三四五六七八九十]+、[^\n]*?)[\t ]+(?=（[一二三四五六七八九十\d]+）\s*\S)"
)
_INLINE_MANAGER_SECTION_BODY_PATTERN = re.compile(
    r"(?m)^(\s*(?:#{1,6}\s*)?(?:[一二三四五六七八九十]+、\s*)?"
    r"(?:辩论结论|行为逻辑|持仓建议|研究结论))\s+(?=\S)(.+)$"
)
_MARKDOWN_HEADING_PATTERN = re.compile(r"^\s*(#{1,6})\s+\S")
_EMPTY_MARKDOWN_DECORATION_LINE_PATTERN = re.compile(r"^\s*[*_]{1,4}\s*$")
_MARKDOWN_LIST_OR_TABLE_LINE_PATTERN = re.compile(
    r"^\s*(?:[-*+]\s+\S|\d+[.．、)]\s+\S|[|>]|```)"
)
_CHINESE_ORDERED_CUE_RE = re.compile(r"(第一|第二|第三|第四|第五|首先|其次|再次|最后)[，,]")
_CHINESE_SENTENCE_RE = re.compile(r"[^。！？!?]+[。！？!?]?")
_ORPHAN_SNAPSHOT_ITEM_RE = re.compile(
    r"^\s*-\s*(?:立场|本轮新增|本轮新增与反驳|待验证|Stance|New this round|To verify)\s*[:：]",
    re.IGNORECASE,
)
_ETF_SCOPE_NOTE_RE = re.compile(
    r"成分股层面的估值、盈利和权重信息仅作为ETF仓位调整依据，"
    r"实际执行对象仍是ETF整体仓位，不对成分股给出直接交易指令。?"
)


def _is_report_heading_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _VISIBLE_ORDINAL_CONTINUATION_PATTERN.match(stripped):
        return False
    return bool(
        _REPORT_HEADING_LINE_PATTERN.match(stripped)
        or _VISIBLE_SECTION_LINE_PATTERN.match(stripped)
    )


def _normalize_orphan_section_marker_lines(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text or not _is_chinese_output():
        return text

    lines = text.split("\n")
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _ORPHAN_VISIBLE_SECTION_MARKER_LINE_PATTERN.match(line)
        if not match:
            normalized.append(line)
            index += 1
            continue

        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1

        if next_index < len(lines):
            next_line = lines[next_index].strip()
            if not (
                _ORPHAN_VISIBLE_SECTION_MARKER_LINE_PATTERN.match(next_line)
                or _is_report_heading_line(next_line)
                or _ARABIC_LIST_ITEM_LINE_PATTERN.match(next_line)
            ):
                normalized.append(f"{match.group(1)}{match.group(2)}{next_line}")
                index = next_index + 1
                continue

        index += 1

    return "\n".join(normalized)


def _split_inline_section_headings(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    text = _INLINE_MANAGER_SECTION_BODY_PATTERN.sub(r"\1\n\2", text)
    text = _INLINE_MARKDOWN_VISIBLE_SECTION_PATTERN.sub("\n\n", text)
    text = _INLINE_VISIBLE_SECTION_PATTERN.sub(r"\1\n\n\2", text)
    text = _INLINE_TOP_TO_SUBSECTION_PATTERN.sub(r"\1\n\n", text)
    text = _INLINE_SPACED_SUBSECTION_PATTERN.sub("\n\n", text)
    return text


def _ensure_report_heading_spacing(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    lines = text.split("\n")
    spaced: list[str] = []
    for index, line in enumerate(lines):
        if _is_report_heading_line(line) and spaced and spaced[-1].strip():
            spaced.append("")
        spaced.append(line)
        if index == len(lines) - 1:
            continue
        if not _is_report_heading_line(line):
            continue
        if lines[index + 1].strip():
            spaced.append("")
    return "\n".join(spaced)


def _strip_empty_markdown_decoration_lines(content: str) -> str:
    lines = (content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(
        line for line in lines if not _EMPTY_MARKDOWN_DECORATION_LINE_PATTERN.match(line)
    )


def _markdown_heading_level(line: str) -> int | None:
    match = _MARKDOWN_HEADING_PATTERN.match(line or "")
    return len(match.group(1)) if match else None


def _is_empty_subsection_candidate(line: str) -> bool:
    match = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line or "")
    if not match:
        return False
    # Only drop empty subsection shells. Top-level headings are structural anchors
    # and should remain even when their first child subsection carries the body.
    return bool(re.match(r"^（[一二三四五六七八九十\d]+）", match.group(1).strip()))


def _extract_markdown_heading_title(line: str) -> str:
    match = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line or "")
    return match.group(1).strip() if match else ""


def _strip_empty_report_headings(content: str) -> tuple[str, set[tuple[int, str]]]:
    lines = (content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    if not lines:
        return "", set()

    remove_indices: set[int] = set()
    for index, line in enumerate(lines):
        level = _markdown_heading_level(line)
        if level is None or not _is_empty_subsection_candidate(line):
            continue

        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1

        next_level = (
            _markdown_heading_level(lines[next_index])
            if next_index < len(lines)
            else None
        )
        previous_same_level = any(
            _markdown_heading_level(previous_line) == level
            and _is_empty_subsection_candidate(previous_line)
            for previous_line in lines[:index]
        )
        # Remove empty sibling subsection headings created by the model, while
        # keeping a lone trailing subsection as a visible structural cue.
        if (next_level is not None and next_level <= level) or (
            next_index >= len(lines) and previous_same_level
        ):
            remove_indices.add(index)
            remove_indices.update(range(index + 1, next_index))

    unnumber_singletons: set[tuple[int, str]] = set()
    for index, line in enumerate(lines):
        level = _markdown_heading_level(line)
        if (
            index in remove_indices
            or level is None
            or not _is_empty_subsection_candidate(line)
        ):
            continue

        parent_start = -1
        parent_level = 0
        for previous_index in range(index - 1, -1, -1):
            previous_level = _markdown_heading_level(lines[previous_index])
            if previous_level is not None and previous_level < level:
                parent_start = previous_index
                parent_level = previous_level
                break
        if parent_start == -1:
            continue

        parent_end = len(lines)
        for next_index in range(parent_start + 1, len(lines)):
            next_level = _markdown_heading_level(lines[next_index])
            if next_level is not None and next_level <= parent_level:
                parent_end = next_index
                break

        sibling_indices = [
            sibling_index
            for sibling_index in range(parent_start + 1, parent_end)
            if _markdown_heading_level(lines[sibling_index]) == level
            and _is_empty_subsection_candidate(lines[sibling_index])
        ]
        kept_siblings = [
            sibling_index for sibling_index in sibling_indices if sibling_index not in remove_indices
        ]
        removed_siblings = [
            sibling_index for sibling_index in sibling_indices if sibling_index in remove_indices
        ]
        if len(kept_siblings) == 1 and removed_siblings:
            clean_title = _clean_report_heading_text(_extract_markdown_heading_title(line))
            unnumber_singletons.add((level, clean_title))

    return "\n".join(
        line for index, line in enumerate(lines) if index not in remove_indices
    ), unnumber_singletons


def _strip_single_child_subsection_numbering(
    content: str, singleton_keys: set[tuple[int, str]]
) -> str:
    if not singleton_keys:
        return content

    lines = (content or "").splitlines()
    normalized: list[str] = []
    for line in lines:
        match = re.match(r"^(\s*#{1,6})(\s+)(.+?)\s*$", line)
        if not match:
            normalized.append(line)
            continue

        level = len(match.group(1).lstrip())
        title = match.group(3).strip()
        clean_title = _clean_report_heading_text(title)
        if (level, clean_title) in singleton_keys and re.match(
            r"^（[一二三四五六七八九十\d]+）", title
        ):
            normalized.append(f"{match.group(1)}{match.group(2)}{clean_title}")
            continue
        normalized.append(line)
    return "\n".join(normalized)


def _is_soft_join_candidate(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _markdown_heading_level(stripped) is not None or _is_report_heading_line(stripped):
        return False
    return not _MARKDOWN_LIST_OR_TABLE_LINE_PATTERN.match(stripped)


def _join_chinese_soft_line_breaks(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text or not _is_chinese_output():
        return text

    lines = text.split("\n")
    joined: list[str] = []
    for line in lines:
        stripped = line.strip()
        if (
            joined
            and _is_soft_join_candidate(joined[-1])
            and _is_soft_join_candidate(stripped)
            and (contains_cjk(joined[-1]) or contains_cjk(stripped))
        ):
            joined[-1] = f"{joined[-1].rstrip()}{stripped}"
            continue
        joined.append(line)
    return "\n".join(joined)


def _format_dense_chinese_manager_paragraph(paragraph: str) -> str:
    text = (paragraph or "").strip()
    if not text or not contains_cjk(text):
        return paragraph
    if _MARKDOWN_LIST_OR_TABLE_LINE_PATTERN.match(text) or _is_report_heading_line(text):
        return paragraph

    ordered_matches = list(_CHINESE_ORDERED_CUE_RE.finditer(text))
    if len(ordered_matches) >= 2:
        prefix = text[: ordered_matches[0].start()].rstrip("：:；;，, ")
        items = []
        for index, match in enumerate(ordered_matches):
            end = ordered_matches[index + 1].start() if index + 1 < len(ordered_matches) else len(text)
            item = text[match.start():end].strip("；;。 ")
            if item:
                items.append(item)
        if prefix and len(items) >= 2:
            return "\n\n".join([f"{prefix}：", *[f"{idx}. {item}" for idx, item in enumerate(items, 1)]])

    include_match = re.search(r"(包括|如下|具体阈值包括)[:：]", text)
    if include_match:
        prefix = text[: include_match.end()].strip()
        rest = text[include_match.end():].strip()
        chunks = [chunk.strip("；;。 ") for chunk in re.split(r"[；;]", rest) if chunk.strip("；;。 ")]
        if len(chunks) >= 3:
            return "\n\n".join([prefix, *[f"{idx}. {chunk}" for idx, chunk in enumerate(chunks, 1)]])

    sentences = [match.group(0).strip() for match in _CHINESE_SENTENCE_RE.finditer(text) if match.group(0).strip()]
    if len(text) >= 80 and len(sentences) >= 3:
        return "\n\n".join(sentences)
    return paragraph


def _format_research_manager_readability(content: str) -> str:
    if not content or not _is_chinese_output():
        return content

    blocks = re.split(r"\n\s*\n", content)
    formatted = [_format_dense_chinese_manager_paragraph(block) for block in blocks]
    return "\n\n".join(formatted)


def _join_wrapped_ordinal_round_phrases(content: str) -> str:
    return _WRAPPED_ORDINAL_ROUND_PHRASE_RE.sub(r"\1\2", content or "")


def _strip_orphan_manager_snapshot_items(content: str) -> str:
    lines = (content or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    if not lines:
        return ""

    cut_index = len(lines)
    for index, line in enumerate(lines):
        if _ORPHAN_SNAPSHOT_ITEM_RE.match(line):
            cut_index = index
            break
    if cut_index < len(lines) and cut_index > 0:
        previous = lines[cut_index - 1].strip()
        if _ETF_SCOPE_NOTE_RE.search(previous):
            cut_index -= 1

    cleaned = "\n".join(lines[:cut_index])
    cleaned = _ETF_SCOPE_NOTE_RE.sub("", cleaned)
    return collapse_blank_lines(cleaned)


def _convert_plain_headings_to_markdown(content: str) -> str:
    """Convert plain-text Chinese numbered headings (一、/（一）) to markdown headings."""
    text = (content or "").strip()
    if not text:
        return ""

    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        # Skip lines that already have markdown heading tags
        if stripped.startswith("#"):
            result.append(line)
            continue
        # Convert top-level headings: 一、xxx → # 一、xxx
        if _looks_like_plain_numbered_heading(stripped) and stripped.startswith(tuple("一二三四五六七八九十")):
            result.append(f"# {stripped}")
            continue
        # Convert second-level headings: （一）xxx → ## （一）xxx
        if _looks_like_plain_numbered_heading(stripped) and stripped.startswith("（"):
            result.append(f"## {stripped}")
            continue
        result.append(line)
    return "\n".join(result)


def _prepare_report_markdown(content: str, target_min_level: Optional[int] = None) -> str:
    text = strip_refine_preamble(content)
    text = strip_exchange_only_pseudo_titles(text)
    text = _strip_empty_markdown_decoration_lines(text)
    text = _normalize_loose_arabic_list_markers(text)
    text = _join_wrapped_etf_name_code(text)
    text = _strip_sentence_like_section_prefixes_in_lists(text)
    text = _normalize_orphan_section_marker_lines(text)
    text = _split_inline_section_headings(text)
    text = _convert_plain_headings_to_markdown(text)
    text, singleton_keys = _strip_empty_report_headings(text)
    text = _normalize_report_heading_numbering(text)
    text = _strip_single_child_subsection_numbering(text, singleton_keys)
    text = _join_chinese_soft_line_breaks(text)
    text = _ensure_report_heading_spacing(text)
    if target_min_level is not None:
        text = _relevel_markdown_headings(text, target_min_level)
    return collapse_blank_lines(text)


# Create a deque to store recent messages with a maximum length
class MessageBuffer:
    # Fixed teams that always run (not user-selectable)
    FIXED_AGENTS = {
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    # Analyst name mapping
    ANALYST_MAPPING = {
        "market_flow": "Market & Flow Analyst",
        "catalyst_sentiment": "Sentiment & Catalyst Analyst",
        "macro_regime": "Macro Regime Analyst",
        "meso_commodity": "Meso Commodity Analyst",
        "holdings_industry": "ETF Holdings-Industry Research Analyst",
        "top_holdings": "ETF Top Holdings Research Analyst",
    }

    # Report section mapping: section -> (analyst_key for filtering, finalizing_agent)
    # analyst_key: which analyst selection controls this section (None = always included)
    # finalizing_agent: which agent must be "completed" for this report to count as done
    REPORT_SECTIONS = {
        "market_flow_report": ("market_flow", "Market & Flow Analyst"),
        "catalyst_sentiment_report": ("catalyst_sentiment", "Sentiment & Catalyst Analyst"),
        "macro_regime_report": ("macro_regime", "Macro Regime Analyst"),
        "meso_commodity_report": ("meso_commodity", "Meso Commodity Analyst"),
        "holdings_industry_report": ("holdings_industry", "ETF Holdings-Industry Research Analyst"),
        "top_holdings_report": ("top_holdings", "ETF Top Holdings Research Analyst"),
        "research_allocation_plan": (None, "Research Manager"),
        "trader_allocation_plan": (None, "Trader"),
        "final_allocation_decision": (None, "Portfolio Manager"),
    }

    REPORT_SECTION_ALIASES = {
        "market_report": "market_flow_report",
        "research_report": "market_flow_report",
        "etf_flow_report": "market_flow_report",
        "sentiment_report": "catalyst_sentiment_report",
        "news_report": "macro_regime_report",
        "fundamentals_report": "meso_commodity_report",
        "etf_structure_report": "meso_commodity_report",
        "stock_report": "holdings_industry_report",
        "etf_macro_report": "holdings_industry_report",
        "etf_stock_research_report": "top_holdings_report",
        "investment_plan": "research_allocation_plan",
        "trader_investment_plan": "trader_allocation_plan",
        "final_trade_decision": "final_allocation_decision",
    }

    def __init__(self, max_length=100):
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None  # Store the complete final report
        self.agent_status = {}
        self.current_agent = None
        self.report_sections = {}
        self.selected_analysts = []
        self._processed_message_ids = set()

    def init_for_analysis(self, selected_analysts):
        """Initialize agent status and report sections based on selected analysts.

        Args:
            selected_analysts: List of analyst type strings (e.g., ["market", "news"])
        """
        self.selected_analysts = [_normalize_analyst_key(a) for a in selected_analysts]

        # Build agent_status dynamically
        self.agent_status = {}

        # Add selected analysts
        for analyst_key in self.selected_analysts:
            if analyst_key in self.ANALYST_MAPPING:
                self.agent_status[self.ANALYST_MAPPING[analyst_key]] = "pending"

        # Add fixed teams
        for team_agents in self.FIXED_AGENTS.values():
            for agent in team_agents:
                self.agent_status[agent] = "pending"

        # Build report_sections dynamically
        self.report_sections = {}
        for section, (analyst_key, _) in self.REPORT_SECTIONS.items():
            if analyst_key is None or analyst_key in self.selected_analysts:
                self.report_sections[section] = None

        # Reset other state
        self.current_report = None
        self.final_report = None
        self.current_agent = None
        self.messages.clear()
        self.tool_calls.clear()
        self._processed_message_ids.clear()

    def get_completed_reports_count(self):
        """Count reports that are finalized (their finalizing agent is completed).

        A report is considered complete when:
        1. The report section has content (not None), AND
        2. The agent responsible for finalizing that report has status "completed"

        This prevents interim updates (like debate rounds) from counting as completed.
        """
        count = 0
        for section in self.report_sections:
            if section not in self.REPORT_SECTIONS:
                continue
            _, finalizing_agent = self.REPORT_SECTIONS[section]
            # Report is complete if it has content AND its finalizing agent is done
            has_content = self.report_sections.get(section) is not None
            agent_done = self.agent_status.get(finalizing_agent) == "completed"
            if has_content and agent_done:
                count += 1
        return count

    def add_message(self, message_type, content):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))

    def add_tool_call(self, tool_name, args):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))

    def update_agent_status(self, agent, status):
        agent = AGENT_NAME_ALIASES.get(agent, agent)
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name, content):
        section_name = self.REPORT_SECTION_ALIASES.get(section_name, section_name)
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()

    def _update_current_report(self):
        # For the panel display, only show the most recently updated section
        latest_section = None
        latest_content = None

        # Find the most recently updated section
        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content
               
        if latest_section and latest_content:
            self.current_report = (
                f"### {_localize_cli_section_title(latest_section)}\n"
                f"{_prepare_report_markdown(latest_content, 4)}"
            )

        # Update the final complete report
        self._update_final_report()

    def _update_final_report(self):
        report_parts = []

        # Analyst Team Reports - use .get() to handle missing sections
        analyst_sections = [
            "market_flow_report",
            "catalyst_sentiment_report",
            "macro_regime_report",
            "meso_commodity_report",
            "holdings_industry_report",
            "top_holdings_report",
        ]
        if any(self.report_sections.get(section) for section in analyst_sections):
            report_parts.append(
                f"## {_localize_cli_label('Analyst Team Reports', '分析团队报告')}"
            )
            if self.report_sections.get("market_flow_report"):
                report_parts.append(
                    f"### {_localize_cli_section_title('market_flow_report')}\n"
                    f"{_prepare_report_markdown(self.report_sections['market_flow_report'], 4)}"
                )
            if self.report_sections.get("catalyst_sentiment_report"):
                report_parts.append(
                    f"### {_localize_cli_section_title('catalyst_sentiment_report')}\n"
                    f"{_prepare_report_markdown(self.report_sections['catalyst_sentiment_report'], 4)}"
                )
            if self.report_sections.get("macro_regime_report"):
                report_parts.append(
                    f"### {_localize_cli_section_title('macro_regime_report')}\n"
                    f"{_prepare_report_markdown(self.report_sections['macro_regime_report'], 4)}"
                )
            if self.report_sections.get("meso_commodity_report"):
                report_parts.append(
                    f"### {_localize_cli_section_title('meso_commodity_report')}\n"
                    f"{_prepare_report_markdown(self.report_sections['meso_commodity_report'], 4)}"
                )
            if self.report_sections.get("holdings_industry_report"):
                report_parts.append(
                    f"### {_localize_cli_section_title('holdings_industry_report')}\n"
                    f"{_prepare_report_markdown(self.report_sections['holdings_industry_report'], 4)}"
                )
            if self.report_sections.get("top_holdings_report"):
                report_parts.append(
                    f"### {_localize_cli_section_title('top_holdings_report')}\n"
                    f"{_prepare_report_markdown(self.report_sections['top_holdings_report'], 4)}"
                )

        # Research Team Reports
        if self.report_sections.get("research_allocation_plan"):
            report_parts.append(
                f"## {_localize_cli_section_title('research_allocation_plan')}"
            )
            report_parts.append(
                _prepare_report_markdown(self.report_sections["research_allocation_plan"], 3)
            )

        # Trading Team Reports
        if self.report_sections.get("trader_allocation_plan"):
            report_parts.append(
                f"## {_localize_cli_section_title('trader_allocation_plan')}"
            )
            report_parts.append(
                _prepare_report_markdown(
                    self.report_sections["trader_allocation_plan"], 3
                )
            )

        # Portfolio Management Decision
        if self.report_sections.get("final_allocation_decision"):
            report_parts.append(
                f"## {_localize_cli_section_title('final_allocation_decision')}"
            )
            report_parts.append(
                _prepare_report_markdown(
                    self.report_sections["final_allocation_decision"], 3
                )
            )

        self.final_report = collapse_blank_lines("\n\n".join(report_parts)) if report_parts else None


message_buffer = MessageBuffer()


RESEARCH_SPEAKER_ALIASES = {
    "Bull Researcher": ("Bull Researcher", "Bull Analyst", "多头分析师"),
    "Bear Researcher": ("Bear Researcher", "Bear Analyst", "空头分析师"),
}

RISK_SPEAKER_ALIASES = {
    "Aggressive Analyst": ("Aggressive Analyst", "激进风险分析师", "激进分析师"),
    "Conservative Analyst": ("Conservative Analyst", "保守风险分析师", "保守分析师"),
    "Neutral Analyst": ("Neutral Analyst", "中性风险分析师", "中性分析师"),
}


def _build_speaker_pattern(speaker_aliases: dict[str, tuple[str, ...]]) -> re.Pattern[str]:
    aliases = []
    for names in speaker_aliases.values():
        aliases.extend(names)
    escaped = sorted((re.escape(name) for name in aliases), key=len, reverse=True)
    return re.compile(rf"(?m)^\s*({'|'.join(escaped)})\s*[:：]\s*")


def _split_history_into_turns(history: str, speaker_aliases: dict[str, tuple[str, ...]]) -> list[str]:
    if not history or not history.strip():
        return []

    pattern = _build_speaker_pattern(speaker_aliases)
    matches = list(pattern.finditer(history))
    if not matches:
        return [history.strip()]

    turns = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(history)
        turn = history[start:end].strip()
        if turn:
            turns.append(turn)
    return turns


def _format_grouped_rounds(
    histories: dict[str, str],
    speaker_aliases: dict[str, tuple[str, ...]],
    manager_title: Optional[str] = None,
    manager_content: str = "",
    manager_snapshot_path: str = "",
    manager_show_snapshot: bool = True,
    show_round_snapshots: bool = True,
    manager_readability: bool = False,
) -> str:
    is_chinese = _is_chinese_output()
    turns_by_speaker = {
        speaker: _split_history_into_turns(histories.get(speaker, ""), speaker_aliases)
        for speaker in speaker_aliases
    }
    max_rounds = max((len(turns) for turns in turns_by_speaker.values()), default=0)

    parts = []
    for round_index in range(max_rounds):
        round_parts = []
        for speaker, turns in turns_by_speaker.items():
            if round_index < len(turns):
                turn = turns[round_index]
                turn_without_snapshot = strip_feedback_snapshot(turn)
                argument_body = normalize_chinese_role_terms(
                    strip_role_prefix(
                        strip_analyst_decision_summary(turn_without_snapshot),
                        speaker,
                    )
                )
                argument_body = normalize_visible_debate_body(argument_body)
                decision_summary = normalize_chinese_role_terms(
                    extract_analyst_decision_summary(turn)
                )
                snapshot = normalize_chinese_role_terms(
                    extract_feedback_snapshot(turn)
                )
                speaker_title = _localize_cli_role_title(speaker) if is_chinese else speaker
                speaker_parts = [f"#### {speaker_title}"]
                if argument_body:
                    speaker_parts.append(argument_body)
                if decision_summary:
                    speaker_parts.append(decision_summary)
                if snapshot and show_round_snapshots:
                    speaker_parts.append(snapshot)
                round_parts.append(collapse_blank_lines("\n\n".join(speaker_parts)))
        if round_parts:
            round_title = f"第 {round_index + 1} 轮" if is_chinese else f"Round {round_index + 1}"
            parts.append(collapse_blank_lines(f"### {round_title}\n\n" + "\n\n".join(round_parts)))

    if manager_title and manager_content and manager_content.strip():
        parts.append(
            f"### {manager_title}\n"
            f"{_format_manager_decision(manager_content, manager_snapshot_path, show_snapshot_summary=manager_show_snapshot, nested_min_heading_level=4, improve_readability=manager_readability)}"
        )

    return collapse_blank_lines("\n\n".join(parts))


def _format_manager_decision(
    manager_content: str,
    snapshot_path: str = "",
    show_snapshot_summary: bool = True,
    nested_min_heading_level: Optional[int] = None,
    improve_readability: bool = False,
) -> str:
    """Show the manager's conclusion first, then a short snapshot summary."""
    content = (manager_content or "").strip()
    if not content:
        return ""

    body = normalize_chinese_manager_terms(strip_all_feedback_snapshots(content))
    body = _strip_orphan_manager_snapshot_items(body)
    if nested_min_heading_level is not None:
        body = _prepare_report_markdown(body, nested_min_heading_level)
    else:
        body = _prepare_report_markdown(body)
    body = _join_wrapped_ordinal_round_phrases(body)
    if improve_readability:
        body = _format_research_manager_readability(body)
    snapshot_summary = ""
    if show_snapshot_summary:
        snapshot = normalize_chinese_role_terms(extract_feedback_snapshot(content))
        snapshot_summary = make_display_snapshot(snapshot, snapshot_path)

    parts = []
    if body:
        parts.append(body)
    if snapshot_summary:
        snapshot_title = (
            "反馈快照摘要"
            if _is_chinese_output()
            else "Snapshot Summary"
        )
        parts.append(f"#### {snapshot_title}\n{snapshot_summary}")

    return collapse_blank_lines("\n\n".join(parts))


def format_research_team_history(debate_state: dict) -> str:
    output_language = get_output_language().strip().lower()
    manager_title = (
        "研究经理结论"
        if output_language in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}
        else "Research Manager Decision"
    )
    return _format_grouped_rounds(
        {
            "Bull Researcher": debate_state.get("bull_history", ""),
            "Bear Researcher": debate_state.get("bear_history", ""),
        },
        RESEARCH_SPEAKER_ALIASES,
        manager_title=manager_title,
        manager_content=debate_state.get("judge_decision", ""),
        manager_snapshot_path=debate_state.get("judge_snapshot_path", ""),
        manager_show_snapshot=False,
        show_round_snapshots=False,
        manager_readability=True,
    )


def format_risk_management_history(risk_state: dict, include_manager: bool = True) -> str:
    output_language = get_output_language().strip().lower()
    manager_title = (
        "投资组合经理结论"
        if output_language in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}
        else "Portfolio Manager Decision"
    )
    return _format_grouped_rounds(
        {
            "Aggressive Analyst": risk_state.get("aggressive_history", ""),
            "Conservative Analyst": risk_state.get("conservative_history", ""),
            "Neutral Analyst": risk_state.get("neutral_history", ""),
        },
        RISK_SPEAKER_ALIASES,
        manager_title=manager_title if include_manager else None,
        manager_content=risk_state.get("judge_decision", "") if include_manager else "",
        manager_snapshot_path=risk_state.get("judge_snapshot_path", "") if include_manager else "",
        manager_show_snapshot=False,
        show_round_snapshots=False,
        manager_readability=True,
    )


def create_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )
    layout["main"].split_column(
        Layout(name="upper", ratio=3), Layout(name="analysis", ratio=5)
    )
    layout["upper"].split_row(
        Layout(name="progress", ratio=2), Layout(name="messages", ratio=3)
    )
    return layout


def format_tokens(n):
    """Format token count for display."""
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def update_display(layout, spinner_text=None, stats_handler=None, start_time=None):
    # Header with welcome message
    layout["header"].update(
        Panel(
            "[bold green]Welcome to ETFAgents CLI[/bold green]\n"
            "[dim]Multi-Agents LLM ETF Investment Framework[/dim]",
            title="Welcome to ETFAgents",
            border_style="green",
            padding=(1, 2),
            expand=True,
        )
    )

    # Progress panel showing agent status
    progress_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        box=box.SIMPLE_HEAD,  # Use simple header with horizontal lines
        title=None,  # Remove the redundant Progress title
        padding=(0, 2),  # Add horizontal padding
        expand=True,  # Make table expand to fill available space
    )
    progress_table.add_column("Team", style="cyan", justify="center", width=20)
    progress_table.add_column("Agent", style="green", justify="center", width=20)
    progress_table.add_column("Status", style="yellow", justify="center", width=20)

    # Group agents by team - filter to only include agents in agent_status
    all_teams = {
        "Analyst Team": [
            "Market & Flow Analyst",
            "Sentiment & Catalyst Analyst",
            "Macro Regime Analyst",
            "Meso Commodity Analyst",
            "ETF Holdings-Industry Research Analyst",
            "ETF Top Holdings Research Analyst",
        ],
        "Research Team": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "Trading Team": ["Trader"],
        "Risk Management": ["Aggressive Analyst", "Neutral Analyst", "Conservative Analyst"],
        "Portfolio Management": ["Portfolio Manager"],
    }

    # Filter teams to only include agents that are in agent_status
    teams = {}
    for team, agents in all_teams.items():
        active_agents = [a for a in agents if a in message_buffer.agent_status]
        if active_agents:
            teams[team] = active_agents

    for team, agents in teams.items():
        # Add first agent with team name
        first_agent = agents[0]
        status = message_buffer.agent_status.get(first_agent, "pending")
        if status == "in_progress":
            spinner = Spinner(
                "dots", text="[blue]in_progress[/blue]", style="bold cyan"
            )
            status_cell = spinner
        else:
            status_color = {
                "pending": "yellow",
                "completed": "green",
                "error": "red",
            }.get(status, "white")
            status_cell = f"[{status_color}]{status}[/{status_color}]"
        progress_table.add_row(team, first_agent, status_cell)

        # Add remaining agents in team
        for agent in agents[1:]:
            status = message_buffer.agent_status.get(agent, "pending")
            if status == "in_progress":
                spinner = Spinner(
                    "dots", text="[blue]in_progress[/blue]", style="bold cyan"
                )
                status_cell = spinner
            else:
                status_color = {
                    "pending": "yellow",
                    "completed": "green",
                    "error": "red",
                }.get(status, "white")
                status_cell = f"[{status_color}]{status}[/{status_color}]"
            progress_table.add_row("", agent, status_cell)

        # Add horizontal line after each team
        progress_table.add_row("─" * 20, "─" * 20, "─" * 20, style="dim")

    layout["progress"].update(
        Panel(progress_table, title="Progress", border_style="cyan", padding=(1, 2))
    )

    # Messages panel showing recent messages and tool calls
    messages_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        expand=True,  # Make table expand to fill available space
        box=box.MINIMAL,  # Use minimal box style for a lighter look
        show_lines=True,  # Keep horizontal lines
        padding=(0, 1),  # Add some padding between columns
    )
    messages_table.add_column("Time", style="cyan", width=8, justify="center")
    messages_table.add_column("Type", style="green", width=10, justify="center")
    messages_table.add_column(
        "Content", style="white", no_wrap=False, ratio=1
    )  # Make content column expand

    # Combine tool calls and messages
    all_messages = []

    # Add tool calls
    for timestamp, tool_name, args in message_buffer.tool_calls:
        formatted_args = format_tool_args(args)
        all_messages.append((timestamp, "Tool", f"{tool_name}: {formatted_args}"))

    # Add regular messages
    for timestamp, msg_type, content in message_buffer.messages:
        content_str = str(content) if content else ""
        if len(content_str) > 200:
            content_str = content_str[:197] + "..."
        all_messages.append((timestamp, msg_type, content_str))

    # Sort by timestamp descending (newest first)
    all_messages.sort(key=lambda x: x[0], reverse=True)

    # Calculate how many messages we can show based on available space
    max_messages = 12

    # Get the first N messages (newest ones)
    recent_messages = all_messages[:max_messages]

    # Add messages to table (already in newest-first order)
    for timestamp, msg_type, content in recent_messages:
        # Format content with word wrapping
        wrapped_content = Text(content, overflow="fold")
        messages_table.add_row(timestamp, msg_type, wrapped_content)

    layout["messages"].update(
        Panel(
            messages_table,
            title="Messages & Tools",
            border_style="blue",
            padding=(1, 2),
        )
    )

    # Analysis panel showing current report
    if message_buffer.current_report:
        layout["analysis"].update(
            Panel(
                Markdown(message_buffer.current_report),
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )
    else:
        layout["analysis"].update(
            Panel(
                "[italic]Waiting for analysis report...[/italic]",
                title="Current Report",
                border_style="green",
                padding=(1, 2),
            )
        )

    # Footer with statistics
    # Agent progress - derived from agent_status dict
    agents_completed = sum(
        1 for status in message_buffer.agent_status.values() if status == "completed"
    )
    agents_total = len(message_buffer.agent_status)

    # Report progress - based on agent completion (not just content existence)
    reports_completed = message_buffer.get_completed_reports_count()
    reports_total = len(message_buffer.report_sections)

    # Build stats parts
    stats_parts = [f"Agents: {agents_completed}/{agents_total}"]

    # LLM and tool stats from callback handler
    if stats_handler:
        stats = stats_handler.get_stats()
        stats_parts.append(f"LLM: {stats['llm_calls']}")
        stats_parts.append(f"Tools: {stats['tool_calls']}")

        # Token display with graceful fallback
        if stats["tokens_in"] > 0 or stats["tokens_out"] > 0:
            tokens_str = f"Tokens: {format_tokens(stats['tokens_in'])}\u2191 {format_tokens(stats['tokens_out'])}\u2193"
        else:
            tokens_str = "Tokens: --"
        stats_parts.append(tokens_str)

    stats_parts.append(f"Reports: {reports_completed}/{reports_total}")

    # Elapsed time
    if start_time:
        elapsed = time.time() - start_time
        elapsed_str = f"\u23f1 {int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
        stats_parts.append(elapsed_str)

    stats_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    stats_table.add_column("Stats", justify="center")
    stats_table.add_row(" | ".join(stats_parts))

    layout["footer"].update(Panel(stats_table, border_style="grey50"))


def get_user_selections():
    """Get all user selections before starting the analysis display."""
    # Display ASCII art welcome message
    with open(Path(__file__).parent / "static" / "welcome.txt", "r", encoding="utf-8") as f:
        welcome_ascii = f.read()

    # Create welcome box content
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]ETFAgents: Multi-Agents LLM ETF Investment Framework - CLI[/bold green]\n\n"
    welcome_content += "[bold]Workflow Steps:[/bold]\n"
    welcome_content += "I. Analyst Team → II. Research Team → III. Trader → IV. Risk Management → V. Portfolio Management\n\n"
    welcome_content += (
        "[dim]Multi-Agents LLM ETF Investment Framework[/dim]"
    )

    # Create and center the welcome box
    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="Welcome to ETFAgents",
        subtitle="Multi-Agents LLM ETF Investment Framework",
    )
    console.print(Align.center(welcome_box))
    console.print()
    console.print()  # Add vertical space before announcements

    # Fetch and display announcements (silent on failure)
    announcements = fetch_announcements()
    display_announcements(console, announcements)

    # Create a boxed questionnaire for each step
    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]Default: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # Step 1: ETF ticker or candidate pool
    console.print(
        create_question_box(
            "Step 1: ETF Ticker / Candidate Pool",
            "Enter one ETF ticker, or a comma-separated candidate pool with exchange suffixes when needed (examples: 510300.SH or 510300.SH,159915.SZ,513100.SH)",
            "510300.SH",
        )
    )
    selected_tickers = get_tickers()
    analysis_mode = "candidate_pool" if len(selected_tickers) > 1 else "single"
    selected_ticker = selected_tickers[0]

    # Step 2: Analysis date
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(
        create_question_box(
            "Step 2: Analysis Date",
            "Enter the analysis date (YYYY-MM-DD)",
            default_date,
        )
    )
    analysis_date = get_analysis_date()

    # Step 3: Output language
    console.print(
        create_question_box(
            "Step 3: Output Language",
            "Select the language for analyst reports and final decision"
        )
    )
    output_language = ask_output_language()

    # Step 4: Select analysts
    console.print(
        create_question_box(
            "Step 4: Analysts Team", "Select your LLM analyst agents for the analysis"
        )
    )
    selected_analysts = select_analysts()
    console.print(
        f"[green]Selected analysts:[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # Step 5: Research depth
    console.print(
        create_question_box(
            "Step 5: Research Depth", "Select your research depth level"
        )
    )
    selected_research_depth = select_research_depth()

    # Step 6: LLM Provider
    console.print(
        create_question_box(
            "Step 6: LLM Provider", "Select your LLM provider"
        )
    )
    selected_llm_provider, backend_url = select_llm_provider()

    # Step 7: Thinking agents
    console.print(
        create_question_box(
            "Step 7: Thinking Agents", "Select your thinking agents for analysis"
        )
    )
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider, backend_url)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider, backend_url)

    # Step 8: Provider-specific thinking configuration
    thinking_level = None
    reasoning_effort = None
    anthropic_effort = None

    provider_lower = selected_llm_provider.lower()
    if provider_lower == "google":
        console.print(
            create_question_box(
                "Step 8: Thinking Mode",
                "Configure Gemini thinking mode"
            )
        )
        thinking_level = ask_gemini_thinking_config()
    elif provider_lower == "openai":
        console.print(
            create_question_box(
                "Step 8: Reasoning Effort",
                "Configure OpenAI reasoning effort level"
            )
        )
        reasoning_effort = ask_openai_reasoning_effort()
    elif provider_lower == "anthropic":
        console.print(
            create_question_box(
                "Step 8: Effort Level",
                "Configure Claude effort level"
            )
        )
        anthropic_effort = ask_anthropic_effort()

    return {
        "analysis_mode": analysis_mode,
        "ticker": selected_ticker,
        "tickers": selected_tickers,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "google_thinking_level": thinking_level,
        "openai_reasoning_effort": reasoning_effort,
        "anthropic_effort": anthropic_effort,
        "output_language": output_language,
    }


def _normalize_ticker_list(raw_text: str) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[\n,]+", raw_text or ""):
        ticker = part.strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers


def _normalize_benchmark_list(raw_text: str | None) -> list[str]:
    benchmarks: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[\n,]+", raw_text or ""):
        value = part.strip()
        if not value:
            continue
        benchmark = "equal_weight_pool" if value.lower() == "equal_weight_pool" else value.upper()
        if benchmark in seen:
            continue
        seen.add(benchmark)
        benchmarks.append(benchmark)
    return benchmarks


def get_tickers():
    """Get one ETF ticker or a comma-separated candidate pool from user input."""
    while True:
        raw_value = typer.prompt("", default="510300.SH")
        tickers = _normalize_ticker_list(raw_value)
        if tickers:
            return tickers
        console.print("[red]Error: Please enter at least one ETF ticker[/red]")


def get_analysis_date():
    """Get the analysis date from user input."""
    while True:
        date_str = typer.prompt(
            "", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        try:
            # Validate date format and ensure it's not in the future
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]Error: Analysis date cannot be in the future[/red]")
                continue
            return date_str
        except ValueError:
            console.print(
                "[red]Error: Invalid date format. Please use YYYY-MM-DD[/red]"
            )


def _candidate_pool_slug(tickers: list[str]) -> str:
    visible = tickers[:3]
    base = "__".join(visible)
    if len(tickers) > 3:
        base += f"__plus_{len(tickers) - 3}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)


def save_candidate_pool_report(candidates: list[dict[str, str]], analysis_date: str, save_path: Path):
    """Save a ranked candidate-pool summary and per-ticker ETF allocation notes."""
    save_path.mkdir(parents=True, exist_ok=True)
    candidates_dir = save_path / "ranked_candidates"
    candidates_dir.mkdir(exist_ok=True)

    summary_lines = [
        f"## {_localize_cli_label('Candidate Ranking', '候选池排序')}",
        "",
        "| "
        + " | ".join(
            [
                _localize_cli_label("Rank", "排名"),
                _localize_cli_label("Ticker", "代码"),
                _localize_cli_label("Rating", "评级"),
                _localize_cli_label("Score", "分数"),
                _localize_cli_label("Suggested Weight", "建议权重"),
            ]
        )
        + " |",
        "| --- | --- | --- | --- | --- |",
    ]
    sections: list[str] = []
    analyst_sections = [
        ("market_flow_report", _localize_cli_section_title("market_flow_report")),
        ("catalyst_sentiment_report", _localize_cli_section_title("catalyst_sentiment_report")),
        ("macro_regime_report", _localize_cli_section_title("macro_regime_report")),
        ("meso_commodity_report", _localize_cli_section_title("meso_commodity_report")),
        ("holdings_industry_report", _localize_cli_section_title("holdings_industry_report")),
        ("top_holdings_report", _localize_cli_section_title("top_holdings_report")),
    ]

    for index, candidate in enumerate(candidates, start=1):
        weight_text = f"{candidate.get('suggested_weight_pct', 0.0):.1f}%"
        summary_lines.append(
            f"| {index} | {candidate['ticker']} | {candidate['rating']} | {candidate['score']} | {weight_text} |"
        )
        analyst_report_parts = [
            f"## {title}\n{_prepare_report_markdown(candidate.get(key, ''), 3)}"
            for key, title in analyst_sections
            if candidate.get(key)
        ]

        candidate_body = collapse_blank_lines(
            "\n\n".join(
            [
                f"# {candidate['ticker']}",
                f"**{_localize_cli_label('Rating', '评级')}**: {candidate['rating']}",
                f"**{_localize_cli_label('Suggested Weight', '建议权重')}**: {weight_text}",
                *analyst_report_parts,
                f"## {_localize_cli_label('Final Allocation Decision', '最终配置决策')}\n{_prepare_report_markdown(candidate.get('final_allocation_decision', ''), 3)}",
                f"## {_localize_cli_label('Trader Allocation Plan', '交易员配置计划')}\n{_prepare_report_markdown(candidate.get('trader_allocation_plan', ''), 3)}",
                f"## {_localize_cli_label('Research Allocation View', '研究团队配置观点')}\n{_prepare_report_markdown(candidate.get('research_allocation_plan', ''), 3)}",
            ]
        )
        )
        candidate_file = candidates_dir / f"{index:02d}_{candidate['ticker'].replace('.', '_')}.md"
        candidate_file.write_text(candidate_body, encoding="utf-8")

        sections.append(
            collapse_blank_lines(
                "\n\n".join(
                [
                    f"## {index}. {candidate['ticker']}",
                    f"**{_localize_cli_label('Rating', '评级')}**: {candidate['rating']}",
                    f"**{_localize_cli_label('Suggested Weight', '建议权重')}**: {weight_text}",
                    *[
                        f"### {title}\n{_prepare_report_markdown(candidate.get(key, ''), 4)}"
                        for key, title in analyst_sections
                        if candidate.get(key)
                    ],
                    f"### {_localize_cli_label('Final Allocation Decision', '最终配置决策')}",
                    _prepare_report_markdown(candidate.get("final_allocation_decision", ""), 4),
                ]
            )
            )
        )

    header = collapse_blank_lines(
        f"# {_localize_cli_label('ETF Candidate Pool Report', 'ETF候选池分析报告')}\n\n"
        f"{_localize_cli_label('Analysis Date', '分析日期')}: {analysis_date}\n\n"
        f"{_localize_cli_label('Generated', '生成时间')}: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    report_text = collapse_blank_lines(header + "\n" + "\n".join(summary_lines) + "\n\n" + "\n\n".join(sections))
    report_path = save_path / "complete_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    return report_path


def _default_backtest_output_dir(config: dict, tickers: list[str], start_date: str, end_date: str) -> Path:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        Path(config["results_dir"])
        / "backtest"
        / _candidate_pool_slug(tickers)
        / f"{start_date}_to_{end_date}"
        / timestamp
    )


def save_report_to_disk(final_state, ticker: str, save_path: Path):
    """Save complete analysis report to disk with organized subfolders."""
    save_path.mkdir(parents=True, exist_ok=True)
    sections = []

    # 1. Analysts
    analysts_dir = save_path / "1_analysts"
    analyst_parts = []
    if get_state_value(final_state, "market_flow_report", ""):
        analysts_dir.mkdir(exist_ok=True)
        market_report = _prepare_report_markdown(get_state_value(final_state, "market_flow_report", ""))
        (analysts_dir / "market_flow.md").write_text(market_report, encoding="utf-8")
        analyst_parts.append((_localize_cli_role_title("Market & Flow Analyst"), market_report))
    if get_state_value(final_state, "catalyst_sentiment_report", ""):
        analysts_dir.mkdir(exist_ok=True)
        sentiment_report = _prepare_report_markdown(get_state_value(final_state, "catalyst_sentiment_report", ""))
        (analysts_dir / "catalyst_sentiment.md").write_text(sentiment_report, encoding="utf-8")
        analyst_parts.append((_localize_cli_role_title("Sentiment & Catalyst Analyst"), sentiment_report))
    if get_state_value(final_state, "macro_regime_report", ""):
        analysts_dir.mkdir(exist_ok=True)
        news_report = _prepare_report_markdown(get_state_value(final_state, "macro_regime_report", ""))
        (analysts_dir / "macro_regime.md").write_text(news_report, encoding="utf-8")
        analyst_parts.append((_localize_cli_role_title("Macro Regime Analyst"), news_report))
    if get_state_value(final_state, "meso_commodity_report", ""):
        analysts_dir.mkdir(exist_ok=True)
        fundamentals_report = _prepare_report_markdown(get_state_value(final_state, "meso_commodity_report", ""))
        (analysts_dir / "meso_commodity.md").write_text(fundamentals_report, encoding="utf-8")
        analyst_parts.append((_localize_cli_role_title("Meso Commodity Analyst"), fundamentals_report))
    if get_state_value(final_state, "holdings_industry_report", ""):
        analysts_dir.mkdir(exist_ok=True)
        stock_report = _prepare_report_markdown(get_state_value(final_state, "holdings_industry_report", ""))
        (analysts_dir / "holdings_industry.md").write_text(stock_report, encoding="utf-8")
        analyst_parts.append((_localize_cli_role_title("ETF Holdings-Industry Research Analyst"), stock_report))
    if get_state_value(final_state, "top_holdings_report", ""):
        analysts_dir.mkdir(exist_ok=True)
        holdings_report = _prepare_report_markdown(get_state_value(final_state, "top_holdings_report", ""))
        (analysts_dir / "top_holdings.md").write_text(holdings_report, encoding="utf-8")
        analyst_parts.append((_localize_cli_role_title("ETF Top Holdings Research Analyst"), holdings_report))
    if analyst_parts:
        content = collapse_blank_lines(
            "\n\n".join(
            f"### {name}\n{_prepare_report_markdown(text, 4)}"
            for name, text in analyst_parts
        )
        )
        sections.append(
            collapse_blank_lines(
                f"## {_localize_cli_label('I. Analyst Team Reports', 'I. 分析团队报告')}\n{content}"
            )
        )

    # 2. Research
    if final_state.get("investment_debate_state"):
        research_dir = save_path / "2_research"
        debate = final_state["investment_debate_state"]
        research_parts = []
        if debate.get("bull_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bull.md").write_text(debate["bull_history"], encoding="utf-8")
            research_parts.append((_localize_cli_role_title("Bull Researcher"), debate["bull_history"]))
        if debate.get("bear_history"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "bear.md").write_text(debate["bear_history"], encoding="utf-8")
            research_parts.append((_localize_cli_role_title("Bear Researcher"), debate["bear_history"]))
        if debate.get("judge_decision"):
            research_dir.mkdir(exist_ok=True)
            (research_dir / "manager.md").write_text(
                _format_manager_decision(
                    debate["judge_decision"],
                    debate.get("judge_snapshot_path", ""),
                    show_snapshot_summary=False,
                    nested_min_heading_level=None,
                    improve_readability=True,
                ),
                encoding="utf-8",
            )
        formatted_research = format_research_team_history(debate)
        if formatted_research:
            research_dir.mkdir(exist_ok=True)
            (research_dir / "rounds.md").write_text(formatted_research, encoding="utf-8")
        if research_parts:
            content = formatted_research or collapse_blank_lines(
                "\n\n".join(
                f"### {name}\n{text}" for name, text in research_parts
            )
            )
            sections.append(
                collapse_blank_lines(
                    f"## {_localize_cli_label('II. Research Team Decision', 'II. 研究团队结论')}\n{content}"
                )
            )

    # 3. Trading
    if get_state_value(final_state, "trader_allocation_plan", ""):
        trading_dir = save_path / "3_trading"
        trading_dir.mkdir(exist_ok=True)
        trader_plan = _prepare_report_markdown(
            get_state_value(final_state, "trader_allocation_plan", ""), 2
        )
        (trading_dir / "trader.md").write_text(trader_plan, encoding="utf-8")
        sections.append(
            collapse_blank_lines(
                f"## {_localize_cli_label('III. Allocation Team Plan', 'III. 配置团队计划')}\n"
                f"### {_localize_cli_role_title('Trader')}\n"
                f"{_prepare_report_markdown(trader_plan, 4)}"
            )
        )

    # 4. Risk Management
    if final_state.get("risk_debate_state"):
        risk_dir = save_path / "4_risk"
        risk = final_state["risk_debate_state"]
        risk_parts = []
        if risk.get("aggressive_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "aggressive.md").write_text(risk["aggressive_history"], encoding="utf-8")
            risk_parts.append((_localize_cli_role_title("Aggressive Analyst"), risk["aggressive_history"]))
        if risk.get("conservative_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "conservative.md").write_text(risk["conservative_history"], encoding="utf-8")
            risk_parts.append((_localize_cli_role_title("Conservative Analyst"), risk["conservative_history"]))
        if risk.get("neutral_history"):
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "neutral.md").write_text(risk["neutral_history"], encoding="utf-8")
            risk_parts.append((_localize_cli_role_title("Neutral Analyst"), risk["neutral_history"]))
        formatted_risk = format_risk_management_history(risk, include_manager=False)
        if formatted_risk:
            risk_dir.mkdir(exist_ok=True)
            (risk_dir / "rounds.md").write_text(formatted_risk, encoding="utf-8")
        if risk_parts:
            content = formatted_risk or collapse_blank_lines(
                "\n\n".join(
                f"### {name}\n{text}" for name, text in risk_parts
            )
            )
            sections.append(
                collapse_blank_lines(
                    f"## {_localize_cli_label('IV. Risk Management Team Decision', 'IV. 风险管理团队结论')}\n{content}"
                )
            )

        # 5. Portfolio Manager
        if risk.get("judge_decision"):
            portfolio_dir = save_path / "5_portfolio"
            portfolio_dir.mkdir(exist_ok=True)
            formatted_portfolio = _format_manager_decision(
                risk["judge_decision"],
                risk.get("judge_snapshot_path", ""),
                show_snapshot_summary=False,
                nested_min_heading_level=None,
                improve_readability=True,
            )
            (portfolio_dir / "decision.md").write_text(formatted_portfolio, encoding="utf-8")
            sections.append(
                collapse_blank_lines(
                    f"## {_localize_cli_label('V. Portfolio Manager Decision', 'V. 投资组合经理决策')}\n"
                    f"### {_localize_cli_role_title('Portfolio Manager')}\n"
                    f"{_format_manager_decision(risk['judge_decision'], risk.get('judge_snapshot_path', ''), show_snapshot_summary=False, nested_min_heading_level=4, improve_readability=True)}"
                )
            )

    # Write consolidated report
    header = collapse_blank_lines(
        f"# {_localize_cli_label('ETF Allocation Analysis Report', 'ETF配置分析报告')}: {ticker}\n\n"
        f"{_localize_cli_label('Generated', '生成时间')}: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    (save_path / "complete_report.md").write_text(
        collapse_blank_lines(header + "\n\n" + "\n\n".join(sections)),
        encoding="utf-8",
    )
    return save_path / "complete_report.md"


def display_complete_report(final_state):
    """Display the complete analysis report sequentially (avoids truncation)."""
    console.print()
    console.print(
        Rule(_localize_cli_label("Complete Analysis Report", "完整分析报告"), style="bold green")
    )

    # I. Analyst Team Reports
    analysts = []
    if get_state_value(final_state, "market_flow_report", ""):
        analysts.append((_localize_cli_role_title("Market & Flow Analyst"), get_state_value(final_state, "market_flow_report", "")))
    if get_state_value(final_state, "catalyst_sentiment_report", ""):
        analysts.append((_localize_cli_role_title("Sentiment & Catalyst Analyst"), get_state_value(final_state, "catalyst_sentiment_report", "")))
    if get_state_value(final_state, "macro_regime_report", ""):
        analysts.append((_localize_cli_role_title("Macro Regime Analyst"), get_state_value(final_state, "macro_regime_report", "")))
    if get_state_value(final_state, "meso_commodity_report", ""):
        analysts.append((_localize_cli_role_title("Meso Commodity Analyst"), get_state_value(final_state, "meso_commodity_report", "")))
    if get_state_value(final_state, "holdings_industry_report", ""):
        analysts.append((_localize_cli_role_title("ETF Holdings-Industry Research Analyst"), get_state_value(final_state, "holdings_industry_report", "")))
    if get_state_value(final_state, "top_holdings_report", ""):
        analysts.append((_localize_cli_role_title("ETF Top Holdings Research Analyst"), get_state_value(final_state, "top_holdings_report", "")))
    if analysts:
        console.print(
            Panel(
                f"[bold]{_localize_cli_label('I. Analyst Team Reports', 'I. 分析团队报告')}[/bold]",
                border_style="cyan",
            )
        )
        for title, content in analysts:
            console.print(
                Panel(
                    Markdown(_prepare_report_markdown(content)),
                    title=title,
                    border_style="blue",
                    padding=(1, 2),
                )
            )

    # II. Research Team Reports
    if final_state.get("investment_debate_state"):
        debate = final_state["investment_debate_state"]
        formatted_research = format_research_team_history(debate)
        if formatted_research:
            console.print(
                Panel(
                    f"[bold]{_localize_cli_label('II. Research Team Decision', 'II. 研究团队结论')}[/bold]",
                    border_style="magenta",
                )
            )
            console.print(
                Panel(
                    Markdown(formatted_research),
                    title=_localize_cli_label("Research Team", "研究团队"),
                    border_style="blue",
                    padding=(1, 2),
                )
            )

    # III. Trading Team
    if get_state_value(final_state, "trader_allocation_plan", ""):
        console.print(
            Panel(
                f"[bold]{_localize_cli_label('III. Allocation Team Plan', 'III. 配置团队计划')}[/bold]",
                border_style="yellow",
            )
        )
        console.print(
            Panel(
                Markdown(
                    _prepare_report_markdown(
                        get_state_value(final_state, "trader_allocation_plan", ""), 2
                    )
                ),
                title=_localize_cli_role_title("Trader"),
                border_style="blue",
                padding=(1, 2),
            )
        )

    # IV. Risk Management Team
    if final_state.get("risk_debate_state"):
        risk = final_state["risk_debate_state"]
        formatted_risk = format_risk_management_history(risk, include_manager=False)
        if formatted_risk:
            console.print(
                Panel(
                    f"[bold]{_localize_cli_label('IV. Risk Management Team Decision', 'IV. 风险管理团队结论')}[/bold]",
                    border_style="red",
                )
            )
            console.print(
                Panel(
                    Markdown(formatted_risk),
                    title=_localize_cli_label("Risk Management Team", "风险管理团队"),
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # V. Portfolio Manager Decision
        if risk.get("judge_decision"):
            console.print(
                Panel(
                    f"[bold]{_localize_cli_label('V. Portfolio Manager Decision', 'V. 投资组合经理决策')}[/bold]",
                    border_style="green",
                )
            )
            console.print(
                Panel(
                    Markdown(
                        _format_manager_decision(
                            risk["judge_decision"],
                            risk.get("judge_snapshot_path", ""),
                            show_snapshot_summary=False,
                        )
                    ),
                    title=_localize_cli_role_title("Portfolio Manager"),
                    border_style="blue",
                    padding=(1, 2),
                )
            )


def display_candidate_pool_report(candidates: list[dict[str, str]]):
    """Display a ranked ETF candidate-pool summary on screen."""
    console.print()
    console.print(
        Rule(_localize_cli_label("ETF Candidate Pool Report", "ETF候选池分析报告"), style="bold green")
    )

    ranking = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE_HEAVY)
    ranking.add_column(_localize_cli_label("Rank", "排名"), justify="right")
    ranking.add_column(_localize_cli_label("Ticker", "代码"))
    ranking.add_column(_localize_cli_label("Rating", "评级"))
    ranking.add_column(_localize_cli_label("Score", "分数"), justify="right")
    ranking.add_column(_localize_cli_label("Suggested Weight", "建议权重"), justify="right")

    for index, candidate in enumerate(candidates, start=1):
        ranking.add_row(
            str(index),
            candidate["ticker"],
            candidate["rating"],
            str(candidate["score"]),
            f"{candidate.get('suggested_weight_pct', 0.0):.1f}%",
        )
    console.print(ranking)

    for candidate in candidates:
        body_parts = [
            f"## {_localize_cli_section_title(section)}\n{_prepare_report_markdown(candidate.get(section, ''), 3)}"
            for section in (
                "market_flow_report",
                "catalyst_sentiment_report",
                "macro_regime_report",
                "meso_commodity_report",
                "holdings_industry_report",
                "top_holdings_report",
            )
            if candidate.get(section)
        ]
        if candidate.get("final_allocation_decision"):
            body_parts.append(
                f"## {_localize_cli_section_title('final_allocation_decision')}\n"
                f"{_prepare_report_markdown(candidate.get('final_allocation_decision', ''), 3)}"
            )
        console.print(
            Panel(
                Markdown(collapse_blank_lines("\n\n".join(body_parts))),
                title=f"{candidate['ticker']} · {candidate['rating']} · {candidate.get('suggested_weight_pct', 0.0):.1f}%",
                border_style="blue",
                padding=(1, 2),
            )
        )


def update_research_team_status(status):
    """Update status for research team members (not Trader)."""
    research_team = ["Bull Researcher", "Bear Researcher", "Research Manager"]
    for agent in research_team:
        message_buffer.update_agent_status(agent, status)


# Ordered list of analysts for status transitions
ANALYST_ORDER = [
    "market_flow",
    "catalyst_sentiment",
    "macro_regime",
    "meso_commodity",
    "holdings_industry",
    "top_holdings",
]
ANALYST_AGENT_NAMES = {
    "market_flow": "Market & Flow Analyst",
    "catalyst_sentiment": "Sentiment & Catalyst Analyst",
    "macro_regime": "Macro Regime Analyst",
    "meso_commodity": "Meso Commodity Analyst",
    "holdings_industry": "ETF Holdings-Industry Research Analyst",
    "top_holdings": "ETF Top Holdings Research Analyst",
}
ANALYST_REPORT_MAP = {
    "market_flow": "market_flow_report",
    "catalyst_sentiment": "catalyst_sentiment_report",
    "macro_regime": "macro_regime_report",
    "meso_commodity": "meso_commodity_report",
    "holdings_industry": "holdings_industry_report",
    "top_holdings": "top_holdings_report",
}


def update_analyst_statuses(message_buffer, chunk):
    """Update analyst statuses based on accumulated report state.

    Logic:
    - Store new report content from the current chunk if present
    - Check accumulated report_sections (not just current chunk) for status
    - Analysts with reports = completed
    - First analyst without report = in_progress
    - Remaining analysts without reports = pending
    - When all analysts done, set Bull Researcher to in_progress
    """
    selected = message_buffer.selected_analysts
    found_active = False

    for analyst_key in ANALYST_ORDER:
        if analyst_key not in selected:
            continue

        agent_name = ANALYST_AGENT_NAMES[analyst_key]
        report_key = ANALYST_REPORT_MAP[analyst_key]

        # Capture new report content from current chunk
        report_content = _chunk_state_value(chunk, report_key, "")
        if report_content:
            message_buffer.update_report_section(report_key, report_content)

        # Determine status from accumulated sections, not just current chunk
        has_report = bool(message_buffer.report_sections.get(report_key))

        if has_report:
            message_buffer.update_agent_status(agent_name, "completed")
        elif not found_active:
            message_buffer.update_agent_status(agent_name, "in_progress")
            found_active = True
        else:
            message_buffer.update_agent_status(agent_name, "pending")

    # When all analysts complete, transition research team to in_progress
    if not found_active and selected:
        if message_buffer.agent_status.get("Bull Researcher") == "pending":
            message_buffer.update_agent_status("Bull Researcher", "in_progress")

def extract_content_string(content):
    """Extract string content from various message formats.
    Returns None if no meaningful text content is found.
    """
    import ast

    def is_empty(val):
        """Check if value is empty using Python's truthiness."""
        if val is None or val == '':
            return True
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return True
            try:
                return not bool(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                return False  # Can't parse = real text
        return not bool(val)

    if is_empty(content):
        return None

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, dict):
        text = content.get('text', '')
        return text.strip() if not is_empty(text) else None

    if isinstance(content, list):
        text_parts = [
            item.get('text', '').strip() if isinstance(item, dict) and item.get('type') == 'text'
            else (item.strip() if isinstance(item, str) else '')
            for item in content
        ]
        result = ' '.join(t for t in text_parts if t and not is_empty(t))
        return result if result else None

    return str(content).strip() if not is_empty(content) else None


def classify_message_type(message) -> tuple[str, str | None]:
    """Classify LangChain message into display type and extract content.

    Returns:
        (type, content) - type is one of: User, Agent, Data, Control
                        - content is extracted string or None
    """
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    content = extract_content_string(getattr(message, 'content', None))

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return ("Control", content)
        return ("User", content)

    if isinstance(message, ToolMessage):
        return ("Data", content)

    if isinstance(message, AIMessage):
        return ("Agent", content)

    # Fallback for unknown types
    return ("System", content)


def format_tool_args(args, max_length=80) -> str:
    """Format tool arguments for terminal display."""
    result = str(args)
    if len(result) > max_length:
        return result[:max_length - 3] + "..."
    return result


def _iter_chunk_messages(chunk: dict):
    if not isinstance(chunk, dict):
        return
    for message in chunk.get("messages", []) or []:
        yield message
    for value in chunk.values():
        if isinstance(value, dict):
            for message in value.get("messages", []) or []:
                yield message


def _sanitize_stream_log_content(content: str) -> str:
    return strip_refine_preamble(content or "").strip()


def process_chunk_messages(chunk, buffer: MessageBuffer) -> None:
    """Record unique streamed messages and tool calls from a graph chunk."""
    for message in _iter_chunk_messages(chunk):
        msg_id = getattr(message, "id", None)
        if msg_id is not None:
            if msg_id in buffer._processed_message_ids:
                continue
            buffer._processed_message_ids.add(msg_id)

        msg_type, content = classify_message_type(message)
        content = _sanitize_stream_log_content(content)
        if content and content.strip():
            buffer.add_message(msg_type, content)

        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                if isinstance(tool_call, dict):
                    buffer.add_tool_call(tool_call["name"], tool_call["args"])
                else:
                    buffer.add_tool_call(tool_call.name, tool_call.args)


def _format_provider_label(provider: str) -> str:
    mapping = {
        "vllm": "vLLM",
        "ollama": "Ollama / llama.cpp",
        "openai": "OpenAI",
        "google": "Google",
        "anthropic": "Anthropic",
        "xai": "xAI",
        "openrouter": "OpenRouter",
        "minimax": "MiniMax",
    }
    return mapping.get((provider or "").lower(), provider or "LLM backend")


def _iter_exception_chain(exc: Exception):
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        yield current
        seen.add(id(current))
        current = current.__cause__ or current.__context__


def _is_local_backend_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost"}


def _preflight_local_backend(provider: str, backend_url: str) -> None:
    if not _is_local_backend_url(backend_url):
        return

    import requests

    endpoint = f"{backend_url.rstrip('/')}/models"
    try:
        response = requests.get(endpoint, timeout=3)
        response.raise_for_status()
    except Exception as exc:
        label = _format_provider_label(provider)
        raise RuntimeError(
            f"Cannot reach {label} backend at {backend_url}. Start the local server first, or choose a different provider."
        ) from exc


def _format_runtime_failure(exc: Exception, selections: dict) -> str:
    provider_label = _format_provider_label(selections.get("llm_provider", ""))
    backend_url = selections.get("backend_url", "")

    if any("connection refused" in str(err).lower() for err in _iter_exception_chain(exc)):
        if backend_url:
            return f"Cannot reach {provider_label} backend at {backend_url}. Start the server first, or choose a different provider."
        return f"Cannot reach the selected {provider_label} backend. Start the server first, or choose a different provider."

    message = str(exc).strip() or exc.__class__.__name__
    return f"Analysis failed: {message}"


def run_analysis(checkpoint: bool = False, memory_mode: str | None = None):
    # First get all user selections
    selections = get_user_selections()

    # Create config with selected research depth
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    # Provider-specific thinking configuration
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")
    config["anthropic_effort"] = selections.get("anthropic_effort")
    config["output_language"] = selections.get("output_language", "English")
    config["checkpoint_enabled"] = checkpoint
    config["memory_mode"] = _normalize_memory_mode(memory_mode or config.get("memory_mode", "full"))

    # Create stats callback handler for tracking LLM/tool calls
    stats_handler = StatsCallbackHandler()

    # Normalize analyst selection to predefined order (selection is a 'set', order is fixed)
    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]
    selected_analyst_keys = [_normalize_analyst_key(a) for a in selected_analyst_keys]
    if selections["analysis_mode"] == "candidate_pool":
        if not selected_analyst_keys:
            console.print("\n[red]Please select at least one analyst.[/red]")
            raise typer.Exit(code=1)

        graph = EtfAgentsGraph(
            selected_analyst_keys,
            config=config,
            debug=False,
            callbacks=[stats_handler],
        )

        try:
            _preflight_local_backend(selections["llm_provider"], selections["backend_url"])
        except Exception as exc:
            console.print(f"\n[red]{_format_runtime_failure(exc, selections)}[/red]")
            raise typer.Exit(code=1)

        pool_slug = _candidate_pool_slug(selections["tickers"])
        results_dir = (
            Path(config["results_dir"])
            / "_candidate_pools"
            / pool_slug
            / selections["analysis_date"]
        )
        results_dir.mkdir(parents=True, exist_ok=True)

        console.print(
            f"\n[bold cyan]{_localize_cli_label('Candidate pool analysis started', '候选池分析已开始')}[/bold cyan]"
        )
        console.print(
            f"[green]{_localize_cli_label('Tickers', '标的')}:[/green] {', '.join(selections['tickers'])}"
        )
        console.print(
            f"[green]{_localize_cli_label('Analysts', '分析师')}:[/green] "
            + ", ".join(ANALYST_AGENT_NAMES.get(a, a) for a in selected_analyst_keys)
        )

        try:
            with console.status(
                _localize_cli_label("Ranking ETF candidates...", "正在对 ETF 候选池进行排序...")
            ):
                ranked_candidates = graph.analyze_candidate_pool(
                    selections["tickers"],
                    selections["analysis_date"],
                )
        except Exception as exc:
            console.print(f"\n[red]{_format_runtime_failure(exc, selections)}[/red]")
            raise typer.Exit(code=1)

        console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")
        local_report_file = save_candidate_pool_report(
            ranked_candidates,
            selections["analysis_date"],
            results_dir,
        )
        console.print(
            f"[green]✓ Local report saved:[/green] {local_report_file.resolve()}"
        )

        save_choice = typer.prompt("Save another copy?", default="N").strip().upper()
        if save_choice in ("Y", "YES", ""):
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_path = Path.cwd() / "reports" / f"candidate_pool_{pool_slug}_{timestamp}"
            save_path_str = typer.prompt(
                "Save path (press Enter for default)",
                default=str(default_path)
            ).strip()
            save_path = Path(save_path_str)
            try:
                report_file = save_candidate_pool_report(
                    ranked_candidates,
                    selections["analysis_date"],
                    save_path,
                )
                console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
                console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
            except Exception as e:
                console.print(f"[red]Error saving report: {e}[/red]")

        display_choice = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
        if display_choice in ("Y", "YES", ""):
            display_candidate_pool_report(ranked_candidates)
        return

    selected_analyst_keys, skipped_analyst_keys = EtfAgentsGraph.resolve_selected_analysts(
        selected_analyst_keys,
        selections["ticker"],
    )
    selected_analyst_labels = [ANALYST_AGENT_NAMES.get(a, a) for a in selected_analyst_keys]
    skipped_analyst_labels = [ANALYST_AGENT_NAMES.get(a, a) for a in skipped_analyst_keys]
    if not selected_analyst_keys:
        console.print(
            "\n[red]All selected analysts are incompatible with this ETF ticker.[/red]"
        )
        raise typer.Exit(code=1)
    if skipped_analyst_labels:
        console.print(
            "\n[yellow]Skipping A-share-only analysts for this ticker:[/yellow] "
            + ", ".join(skipped_analyst_labels)
        )

    # Initialize the graph with callbacks bound to LLMs
    graph = EtfAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )

    # Initialize message buffer with selected analysts
    message_buffer.init_for_analysis(selected_analyst_keys)

    # Track start time for elapsed display
    start_time = time.time()

    try:
        _preflight_local_backend(selections["llm_provider"], selections["backend_url"])
    except Exception as exc:
        console.print(f"\n[red]{_format_runtime_failure(exc, selections)}[/red]")
        raise typer.Exit(code=1)

    # Create result directory
    results_dir = Path(config["results_dir"]) / selections["ticker"] / selections["analysis_date"]
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    def save_message_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            content = content.replace("\n", " ")  # Replace newlines with spaces
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [{message_type}] {content}\n")
        return wrapper
    
    def save_tool_call_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, tool_name, args = obj.tool_calls[-1]
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\n")
        return wrapper

    def save_report_section_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(section_name, content):
            func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                content = obj.report_sections[section_name]
                if content:
                    file_name = f"{section_name}.md"
                    text = "\n".join(str(item) for item in content) if isinstance(content, list) else content
                    with open(report_dir / file_name, "w", encoding="utf-8") as f:
                        f.write(text)
        return wrapper

    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
    message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

    # Now start the display layout
    layout = create_layout()

    final_state = None
    runtime_error = None
    with Live(layout, refresh_per_second=4) as live:
        # Initial display
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Add initial messages
        message_buffer.add_message("System", f"Selected ticker: {selections['ticker']}")
        message_buffer.add_message(
            "System", f"Analysis date: {selections['analysis_date']}"
        )
        message_buffer.add_message(
            "System",
            f"Selected analysts: {', '.join(selected_analyst_labels)}",
        )
        if skipped_analyst_labels:
            message_buffer.add_message(
                "System",
                f"Skipped A-share-only analysts for this ticker: {', '.join(skipped_analyst_labels)}",
            )
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Update agent status to in_progress for the first analyst
        first_analyst = selected_analyst_labels[0]
        message_buffer.update_agent_status(first_analyst, "in_progress")
        update_display(layout, stats_handler=stats_handler, start_time=start_time)

        # Create spinner text
        spinner_text = (
            f"Analyzing {selections['ticker']} on {selections['analysis_date']}..."
        )
        update_display(layout, spinner_text, stats_handler=stats_handler, start_time=start_time)

        try:
            trace = []
            init_agent_state, args, resumed = graph.prepare_run(
                selections["ticker"],
                selections["analysis_date"],
                callbacks=[stats_handler],
            )
            if resumed:
                message_buffer.add_message(
                    "System",
                    f"Resuming checkpoint for {selections['ticker']} on {selections['analysis_date']}",
                )
                update_display(layout, stats_handler=stats_handler, start_time=start_time)

            completed_successfully = False
            try:
                accumulated_state = copy.deepcopy(init_agent_state)
                for chunk in graph.graph.stream(init_agent_state, **args):
                    _merge_stream_state(accumulated_state, chunk)
                    # Process all messages in each chunk so intermediate tool calls are not dropped.
                    process_chunk_messages(chunk, message_buffer)

                    # Update analyst statuses based on report state (runs on every chunk)
                    update_analyst_statuses(message_buffer, chunk)

                    # Research Team - Handle Investment Debate State
                    if chunk.get("investment_debate_state"):
                        debate_state = chunk["investment_debate_state"]
                        bull_hist = debate_state.get("bull_history", "").strip()
                        bear_hist = debate_state.get("bear_history", "").strip()
                        judge = debate_state.get("judge_decision", "").strip()
                        formatted_research = format_research_team_history(debate_state)

                        # Only update status when there's actual content
                        if bull_hist or bear_hist:
                            update_research_team_status("in_progress")
                        if formatted_research:
                            message_buffer.update_report_section(
                                "research_allocation_plan", formatted_research
                            )
                        if judge:
                            update_research_team_status("completed")
                            message_buffer.update_agent_status("Trader", "in_progress")

                    # Trading Team
                    if get_state_value(chunk, "trader_allocation_plan", ""):
                        message_buffer.update_report_section(
                            "trader_allocation_plan", get_state_value(chunk, "trader_allocation_plan", "")
                        )
                        if message_buffer.agent_status.get("Trader") != "completed":
                            message_buffer.update_agent_status("Trader", "completed")
                            message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

                    # Risk Management Team - Handle Risk Debate State
                    if chunk.get("risk_debate_state"):
                        risk_state = chunk["risk_debate_state"]
                        agg_hist = risk_state.get("aggressive_history", "").strip()
                        con_hist = risk_state.get("conservative_history", "").strip()
                        neu_hist = risk_state.get("neutral_history", "").strip()
                        judge = risk_state.get("judge_decision", "").strip()
                        formatted_risk = format_risk_management_history(
                            risk_state, include_manager=False
                        )
                        formatted_portfolio = (
                            _format_manager_decision(
                                judge,
                                risk_state.get("judge_snapshot_path", ""),
                                show_snapshot_summary=False,
                            )
                            if judge
                            else ""
                        )

                        if agg_hist:
                            if message_buffer.agent_status.get("Aggressive Analyst") != "completed":
                                message_buffer.update_agent_status("Aggressive Analyst", "in_progress")
                        if con_hist:
                            if message_buffer.agent_status.get("Conservative Analyst") != "completed":
                                message_buffer.update_agent_status("Conservative Analyst", "in_progress")
                        if neu_hist:
                            if message_buffer.agent_status.get("Neutral Analyst") != "completed":
                                message_buffer.update_agent_status("Neutral Analyst", "in_progress")
                        if formatted_portfolio:
                            message_buffer.update_report_section(
                                "final_allocation_decision", formatted_portfolio
                            )
                        if judge:
                            if message_buffer.agent_status.get("Portfolio Manager") != "completed":
                                message_buffer.update_agent_status("Portfolio Manager", "in_progress")
                                message_buffer.update_agent_status("Aggressive Analyst", "completed")
                                message_buffer.update_agent_status("Conservative Analyst", "completed")
                                message_buffer.update_agent_status("Neutral Analyst", "completed")
                                message_buffer.update_agent_status("Portfolio Manager", "completed")

                    # Update the display
                    update_display(layout, stats_handler=stats_handler, start_time=start_time)

                    trace.append(chunk)
                completed_successfully = True
            finally:
                if completed_successfully and trace:
                    graph.finalize_run(selections["analysis_date"], accumulated_state)
                graph.close_run()

            # Get final state and decision
            final_state = accumulated_state
            decision = graph.process_signal(get_state_value(final_state, "final_allocation_decision", ""))

            # Update all agent statuses to completed
            for agent in message_buffer.agent_status:
                message_buffer.update_agent_status(agent, "completed")

            message_buffer.add_message(
                "System", f"Completed analysis for {selections['analysis_date']}"
            )

            # Update final report sections
            for section in message_buffer.report_sections.keys():
                if section == "research_allocation_plan" and final_state.get("investment_debate_state"):
                    message_buffer.update_report_section(
                        section,
                        format_research_team_history(final_state["investment_debate_state"]),
                    )
                elif section == "final_allocation_decision" and final_state.get("risk_debate_state"):
                    message_buffer.update_report_section(
                        section,
                        _format_manager_decision(
                            get_state_value(final_state, "final_allocation_decision", ""),
                            final_state["risk_debate_state"].get("judge_snapshot_path", ""),
                            show_snapshot_summary=False,
                        ),
                    )
                elif get_state_value(final_state, section, None) is not None:
                    message_buffer.update_report_section(section, get_state_value(final_state, section, ""))

            update_display(layout, stats_handler=stats_handler, start_time=start_time)
        except Exception as exc:
            runtime_error = exc
            message_buffer.add_message("System", _format_runtime_failure(exc, selections))
            update_display(layout, stats_handler=stats_handler, start_time=start_time)

    if runtime_error is not None:
        console.print(f"\n[red]{_format_runtime_failure(runtime_error, selections)}[/red]")
        raise typer.Exit(code=1)

    # Post-analysis prompts (outside Live context for clean interaction)
    console.print("\n[bold cyan]Analysis Complete![/bold cyan]\n")

    try:
        local_report_file = save_report_to_disk(
            final_state,
            selections["ticker"],
            results_dir,
        )
        console.print(
            f"[green]✓ Local report saved:[/green] {local_report_file.resolve()}"
        )
    except Exception as e:
        console.print(f"[red]Error saving local report: {e}[/red]")

    # Prompt to export an additional copy
    save_choice = typer.prompt("Save another copy?", default="N").strip().upper()
    if save_choice in ("Y", "YES", ""):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.cwd() / "reports" / f"{selections['ticker']}_{timestamp}"
        save_path_str = typer.prompt(
            "Save path (press Enter for default)",
            default=str(default_path)
        ).strip()
        save_path = Path(save_path_str)
        try:
            report_file = save_report_to_disk(final_state, selections["ticker"], save_path)
            console.print(f"\n[green]✓ Report saved to:[/green] {save_path.resolve()}")
            console.print(f"  [dim]Complete report:[/dim] {report_file.name}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

    # Prompt to display full report
    display_choice = typer.prompt("\nDisplay full report on screen?", default="Y").strip().upper()
    if display_choice in ("Y", "YES", ""):
        display_complete_report(final_state)


@app.command()
def backtest(
    tickers: str = typer.Option(..., "--tickers", help="Comma-separated ETF tickers."),
    benchmark_tickers: Optional[str] = typer.Option(
        None,
        "--benchmark-tickers",
        help="Comma-separated benchmark tickers, or include equal_weight_pool for a synthetic equal-weight pool benchmark.",
    ),
    start_date: str = typer.Option(..., "--start-date", help="Backtest start date (YYYY-MM-DD)."),
    end_date: str = typer.Option(..., "--end-date", help="Backtest end date (YYYY-MM-DD)."),
    rebalance_interval_days: int = typer.Option(21, "--rebalance-interval-days", min=1),
    top_k: int = typer.Option(3, "--top-k", min=1),
    execution_timing: str = typer.Option("same_close", "--execution-timing"),
    initial_cash: float = typer.Option(1_000_000.0, "--initial-cash"),
    commission: float = typer.Option(0.0, "--commission"),
    slippage_perc: float = typer.Option(0.0, "--slippage-perc"),
    cash_buffer_pct: float = typer.Option(0.0, "--cash-buffer-pct"),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Bypass backtest signal cache and recompute graph outputs."),
    research_depth: int = typer.Option(1, "--research-depth", min=1),
    llm_provider: str = typer.Option(DEFAULT_CONFIG["llm_provider"], "--llm-provider"),
    deep_think_llm: str = typer.Option(DEFAULT_CONFIG["deep_think_llm"], "--deep-think-llm"),
    quick_think_llm: str = typer.Option(DEFAULT_CONFIG["quick_think_llm"], "--quick-think-llm"),
    output_language: str = typer.Option(DEFAULT_CONFIG["output_language"], "--output-language"),
    memory_mode: str = typer.Option(DEFAULT_CONFIG["memory_mode"], "--memory-mode", help="disabled, continuity-only, lesson, or full."),
    memory_in_backtest: bool = typer.Option(False, "--memory-in-backtest/--no-memory-in-backtest", help="Allow memory retrieval during backtests. Off by default for reproducibility."),
    backend_url: Optional[str] = typer.Option(None, "--backend-url"),
    save_path: Optional[Path] = typer.Option(None, "--save-path"),
):
    normalized_tickers = _normalize_ticker_list(tickers)
    normalized_benchmarks = _normalize_benchmark_list(benchmark_tickers)
    if not normalized_tickers:
        console.print("[red]Error: Please provide at least one ETF ticker.[/red]")
        raise typer.Exit(code=1)
    try:
        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        console.print("[red]Error: Dates must use YYYY-MM-DD format.[/red]")
        raise typer.Exit(code=1)
    if start_dt > end_dt:
        console.print("[red]Error: start-date must be on or before end-date.[/red]")
        raise typer.Exit(code=1)

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["llm_provider"] = llm_provider.lower()
    config["deep_think_llm"] = deep_think_llm
    config["quick_think_llm"] = quick_think_llm
    config["max_debate_rounds"] = research_depth
    config["max_risk_discuss_rounds"] = research_depth
    config["output_language"] = output_language
    config["backend_url"] = backend_url
    config["memory_mode"] = _normalize_memory_mode(memory_mode)
    config["memory_in_backtest"] = memory_in_backtest

    try:
        _preflight_local_backend(llm_provider, backend_url)
    except Exception as exc:
        console.print(f"\n[red]{_format_runtime_failure(exc, {'llm_provider': llm_provider, 'backend_url': backend_url})}[/red]")
        raise typer.Exit(code=1)

    graph = EtfAgentsGraph(config=config, debug=False)
    output_dir = save_path or _default_backtest_output_dir(config, normalized_tickers, start_date, end_date)

    with console.status(_localize_cli_label("Running backtest...", "正在运行回测...")):
        result = graph.backtest_candidate_pool(
            normalized_tickers,
            start_date,
            end_date,
            rebalance_interval_days=rebalance_interval_days,
            top_k=top_k,
            execution_timing=execution_timing,
            initial_cash=initial_cash,
            commission=commission,
            slippage_perc=slippage_perc,
            cash_buffer_pct=cash_buffer_pct,
            benchmark_tickers=normalized_benchmarks or None,
            force_refresh=force_refresh,
        )
        save_backtest_result(result, output_dir)

    summary = Table(title=_localize_cli_label("Backtest Summary", "回测摘要"), box=box.SIMPLE_HEAVY)
    summary.add_column(_localize_cli_label("Metric", "指标"))
    summary.add_column(_localize_cli_label("Value", "数值"))
    summary.add_row(_localize_cli_label("Execution", "执行时点"), result.execution_timing)
    summary.add_row(_localize_cli_label("Cumulative Return", "累计收益"), f"{result.metrics.cumulative_return:.4%}")
    summary.add_row(_localize_cli_label("Annualized Return", "年化收益"), f"{result.metrics.annualized_return:.4%}")
    summary.add_row(_localize_cli_label("Max Drawdown", "最大回撤"), f"{result.metrics.max_drawdown:.4%}")
    summary.add_row(_localize_cli_label("Sharpe", "夏普"), f"{result.metrics.sharpe_ratio:.4f}")
    summary.add_row(_localize_cli_label("Average Turnover", "平均换手"), f"{result.metrics.average_turnover:.4f}")
    summary.add_row(_localize_cli_label("Trades", "成交笔数"), str(result.metrics.total_trades))
    if result.benchmarks:
        summary.add_row(_localize_cli_label("Benchmarks", "基准"), ", ".join(result.benchmarks))
    for benchmark_metric in result.benchmark_metrics:
        summary.add_row(
            _localize_cli_label(f"{benchmark_metric.benchmark} Return", f"{benchmark_metric.benchmark} 收益"),
            f"{benchmark_metric.cumulative_return:.4%}",
        )
        summary.add_row(
            _localize_cli_label(f"{benchmark_metric.benchmark} Excess", f"{benchmark_metric.benchmark} 超额"),
            f"{benchmark_metric.excess_cumulative_return:.4%}",
        )
    console.print(summary)
    health = Table(title=_localize_cli_label("Backtest Health", "回测健康检查"), box=box.SIMPLE_HEAVY)
    health.add_column(_localize_cli_label("Check", "检查项"))
    health.add_column(_localize_cli_label("Value", "数值"))
    health.add_row(
        _localize_cli_label("Weight Sources", "权重来源分布"),
        ", ".join(
            f"{key}:{value}"
            for key, value in sorted(result.health.weight_source_counts.items())
        ) or "none",
    )
    health.add_row(
        _localize_cli_label("Structured Triggers", "结构化触发器"),
        str(result.health.structured_trigger_count),
    )
    health.add_row(
        _localize_cli_label("Risk Rules", "风控规则"),
        str(result.health.risk_rule_count),
    )
    health.add_row(
        _localize_cli_label("Trigger Buckets", "触发器分布"),
        ", ".join(
            f"{key}:{value}"
            for key, value in sorted(result.health.trigger_bucket_counts.items())
        ),
    )
    health.add_row(
        _localize_cli_label("Timing Mismatches", "执行时点不一致"),
        str(result.health.execution_timing_mismatch_count),
    )
    health.add_row(
        _localize_cli_label("Clamp Hits", "日期夹紧次数"),
        str(result.health.clamp_hit_count),
    )
    health.add_row(
        _localize_cli_label("Missing Price Rows", "缺失价格行"),
        str(result.health.missing_price_rows),
    )
    health.add_row(
        _localize_cli_label("Unsupported Trigger Rules", "不支持的触发器规则"),
        str(result.health.unsupported_trigger_count),
    )
    console.print(health)

    rebalance_summary = Table(title=_localize_cli_label("Rebalance Summary", "调仓摘要"), box=box.SIMPLE_HEAVY)
    rebalance_summary.add_column(_localize_cli_label("Decision", "决策日"))
    rebalance_summary.add_column(_localize_cli_label("Reason", "原因"))
    rebalance_summary.add_column(_localize_cli_label("Tickers", "标的"))
    rebalance_summary.add_column(_localize_cli_label("Weights", "权重"))
    rebalance_summary.add_column(_localize_cli_label("Ratings", "评级"))
    rebalance_summary.add_column(_localize_cli_label("Weight Source", "权重来源"))
    rebalance_summary.add_column(_localize_cli_label("Period Return", "阶段收益"))
    rebalance_summary.add_column(_localize_cli_label("Cum Return", "累计收益"))
    for row in result.rebalance_summary_rows():
        rebalance_summary.add_row(
            row["decision_date"],
            row["reason"],
            ", ".join(row["selected_tickers"]) or "-",
            ", ".join(
                f"{ticker}:{weight:.1%}"
                for ticker, weight in row["weights"].items()
                if weight > 1e-9
            ) or "-",
            ", ".join(
                f"{ticker}:{rating}"
                for ticker, rating in row["ratings"].items()
            ) or "-",
            ", ".join(row["weight_sources"]) or "unknown",
            f"{row['period_return']:.4%}",
            f"{row['cumulative_return']:.4%}",
        )
    console.print(rebalance_summary)
    console.print(
        f"[green]{_localize_cli_label('Artifacts saved', '结果已保存')}:[/green] {Path(output_dir).resolve()}"
    )


@app.command()
def analyze(
    checkpoint: bool = typer.Option(
        False,
        "--checkpoint",
        help="Enable checkpoint/resume so interrupted runs can continue from the last completed node.",
    ),
    clear_checkpoints: bool = typer.Option(
        False,
        "--clear-checkpoints",
        help="Delete all saved checkpoints before running.",
    ),
    memory_mode: str = typer.Option(
        DEFAULT_CONFIG["memory_mode"],
        "--memory-mode",
        help="disabled, continuity-only, lesson, or full.",
    ),
):
    if clear_checkpoints:
        from etfagents.graph.checkpointer import clear_all_checkpoints

        deleted = clear_all_checkpoints(DEFAULT_CONFIG["data_cache_dir"])
        console.print(f"[yellow]Cleared {deleted} checkpoint(s).[/yellow]")
    run_analysis(checkpoint=checkpoint, memory_mode=memory_mode)


@memory_app.command("promote-playbook")
def promote_playbook(
    playbook_id: str = typer.Option(..., "--id", help="Playbook entry id to promote."),
    expires_days: int = typer.Option(90, "--expires-days", min=1, help="Days before the promoted rule expires."),
    max_active: int = typer.Option(20, "--max-active", min=1, help="Maximum active rules to keep within the same playbook scope."),
    results_dir: Optional[Path] = typer.Option(None, "--results-dir", help="Override results_dir when locating memory artifacts."),
):
    config = copy.deepcopy(DEFAULT_CONFIG)
    if results_dir is not None:
        config["results_dir"] = str(results_dir)
    store = AnalysisMemoryStore(config, [])
    try:
        promoted = store.promote_playbook(
            playbook_id,
            expires_days=expires_days,
            max_active=max_active,
        )
    except KeyError:
        console.print(f"[red]Playbook entry not found:[/red] {playbook_id}")
        raise typer.Exit(code=1)

    console.print(f"[green]Promoted playbook:[/green] {promoted.id}")
    console.print(f"[green]Status:[/green] {promoted.status}")
    if promoted.expires_at:
        console.print(f"[green]Expires:[/green] {promoted.expires_at}")


if __name__ == "__main__":
    app()
