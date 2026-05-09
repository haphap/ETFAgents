"""Shared 5-tier rating vocabulary and deterministic bilingual parsers.

The same five-tier scale is used across structured agent rendering, signal
processing, and snapshot generation. Centralizing the parsing logic here keeps
the English and Chinese rating detectors aligned.
"""

from __future__ import annotations

import re
from typing import Final, Tuple


RATINGS_5_TIER: Tuple[str, ...] = (
    "BUY",
    "OVERWEIGHT",
    "HOLD",
    "UNDERWEIGHT",
    "SELL",
)
CHINESE_RATINGS_5_TIER: Tuple[str, ...] = ("买入", "增持", "持有", "减持", "卖出")

ENGLISH_TO_CHINESE: Final[dict[str, str]] = {
    "BUY": "买入",
    "OVERWEIGHT": "增持",
    "HOLD": "持有",
    "UNDERWEIGHT": "减持",
    "SELL": "卖出",
}
CHINESE_TO_ENGLISH: Final[dict[str, str]] = {
    chinese: english for english, chinese in ENGLISH_TO_CHINESE.items()
}

_ENGLISH_LABELS = r"final allocation proposal|final transaction proposal|execution bias|research view|rating|recommendation|stance|current thesis"
_CHINESE_LABELS = r"最终配置建议|最终交易建议|执行倾向|研究结论|配置评级|评级|建议评级|立场|当前观点"

_ENGLISH_NEGATION_PATTERN = re.compile(
    r"(do not|don't|not|avoid|never|no|cannot|can't)(?:\s+\w+){0,3}\s*$",
    re.IGNORECASE,
)
_CHINESE_NEGATION_PATTERN = re.compile(
    r"(不建议|不宜|不是|并非|避免|不要|勿|难言|无法|不能|非|不|别)\s*$"
)

_ENGLISH_EXPLICIT_PATTERNS = [
    (
        "BUY",
        re.compile(
            rf"(?:\*\*)?(?:{_ENGLISH_LABELS})(?:\*\*)?\s*[:：-]\s*\**buy\**\b",
            re.IGNORECASE,
        ),
    ),
    (
        "OVERWEIGHT",
        re.compile(
            rf"(?:\*\*)?(?:{_ENGLISH_LABELS})(?:\*\*)?\s*[:：-]\s*\**overweight\**\b",
            re.IGNORECASE,
        ),
    ),
    (
        "HOLD",
        re.compile(
            rf"(?:\*\*)?(?:{_ENGLISH_LABELS})(?:\*\*)?\s*[:：-]\s*\**hold\**\b",
            re.IGNORECASE,
        ),
    ),
    (
        "UNDERWEIGHT",
        re.compile(
            rf"(?:\*\*)?(?:{_ENGLISH_LABELS})(?:\*\*)?\s*[:：-]\s*\**underweight\**\b",
            re.IGNORECASE,
        ),
    ),
    (
        "SELL",
        re.compile(
            rf"(?:\*\*)?(?:{_ENGLISH_LABELS})(?:\*\*)?\s*[:：-]\s*\**sell\**\b",
            re.IGNORECASE,
        ),
    ),
    ("BUY", re.compile(r"(?:recommend|maintain|shift to|move to)\s+buy\b", re.IGNORECASE)),
    (
        "OVERWEIGHT",
        re.compile(r"(?:recommend|maintain|shift to|move to)\s+overweight\b", re.IGNORECASE),
    ),
    ("HOLD", re.compile(r"(?:recommend|maintain|shift to|move to)\s+hold\b", re.IGNORECASE)),
    (
        "UNDERWEIGHT",
        re.compile(r"(?:recommend|maintain|shift to|move to)\s+underweight\b", re.IGNORECASE),
    ),
    ("SELL", re.compile(r"(?:recommend|maintain|shift to|move to)\s+sell\b", re.IGNORECASE)),
]
_CHINESE_EXPLICIT_PATTERNS = [
    (
        "BUY",
        re.compile(
            rf"(?:\*\*)?(?:{_CHINESE_LABELS})(?:\*\*)?\s*[:：-]\s*\**买入(?:/增持)?\**"
        ),
    ),
    (
        "OVERWEIGHT",
        re.compile(
            rf"(?:\*\*)?(?:{_CHINESE_LABELS})(?:\*\*)?\s*[:：-]\s*\**增持(?:/买入)?\**"
        ),
    ),
    (
        "HOLD",
        re.compile(
            rf"(?:\*\*)?(?:{_CHINESE_LABELS})(?:\*\*)?\s*[:：-]\s*\**持有\**"
        ),
    ),
    (
        "UNDERWEIGHT",
        re.compile(
            rf"(?:\*\*)?(?:{_CHINESE_LABELS})(?:\*\*)?\s*[:：-]\s*\**减持\**"
        ),
    ),
    (
        "SELL",
        re.compile(
            rf"(?:\*\*)?(?:{_CHINESE_LABELS})(?:\*\*)?\s*[:：-]\s*\**卖出\**"
        ),
    ),
    ("BUY", re.compile(r"(?:建议|维持|转为)\s*买入")),
    ("OVERWEIGHT", re.compile(r"(?:建议|维持|转为)\s*增持")),
    ("HOLD", re.compile(r"(?:建议|维持|转为)\s*持有")),
    ("UNDERWEIGHT", re.compile(r"(?:建议|维持|转为)\s*减持")),
    ("SELL", re.compile(r"(?:建议|维持|转为)\s*卖出")),
]

_ENGLISH_HEURISTIC_PATTERNS = [
    ("SELL", re.compile(r"(exit position|sell the stock|close the position|fully exit)", re.IGNORECASE)),
    (
        "UNDERWEIGHT",
        re.compile(r"(reduce exposure|trim the position|take partial profits)", re.IGNORECASE),
    ),
    (
        "OVERWEIGHT",
        re.compile(r"(add to position|increase exposure|build the position)", re.IGNORECASE),
    ),
    ("BUY", re.compile(r"(buy the stock|enter the position|strong upside)", re.IGNORECASE)),
    ("HOLD", re.compile(r"(maintain the position|wait for confirmation|stay on hold)", re.IGNORECASE)),
]
_CHINESE_HEURISTIC_PATTERNS = [
    ("SELL", re.compile(r"(清仓|退出(?:仓位|头寸)?|止损离场|果断卖出|卖出为主)")),
    (
        "UNDERWEIGHT",
        re.compile(r"(降低仓位|分批止盈|降低敞口|部分卖出|先减仓|逢高减仓|止盈减仓)"),
    ),
    ("OVERWEIGHT", re.compile(r"(加仓|提高仓位|逢低布局|继续增持|扩大仓位)")),
    ("BUY", re.compile(r"(买入机会|积极布局|值得买入|坚定看多|继续买入)")),
    ("HOLD", re.compile(r"(继续观察|暂不动作|维持仓位|等待确认|持仓观望)")),
]

_ENGLISH_WORD_PATTERNS = [
    ("OVERWEIGHT", re.compile(r"\boverweight\b", re.IGNORECASE)),
    ("UNDERWEIGHT", re.compile(r"\bunderweight\b", re.IGNORECASE)),
    ("BUY", re.compile(r"\bbuy\b", re.IGNORECASE)),
    ("HOLD", re.compile(r"\bhold\b", re.IGNORECASE)),
    ("SELL", re.compile(r"\bsell\b", re.IGNORECASE)),
]
_CHINESE_WORD_PATTERNS = [
    ("BUY", re.compile(r"买入")),
    ("OVERWEIGHT", re.compile(r"增持")),
    ("HOLD", re.compile(r"持有")),
    ("UNDERWEIGHT", re.compile(r"减持")),
    ("SELL", re.compile(r"卖出")),
]


def parse_rating(text: str, default: str = "HOLD") -> str:
    """Return the canonical English rating from mixed English/Chinese prose."""
    return detect_english_rating(text, default=default)


def detect_english_rating(text: str, default: str = "HOLD") -> str:
    """Return the canonical English 5-tier rating from prose text."""
    return _detect_rating(text, default=_normalize_english_rating(default))


def detect_chinese_rating(text: str, default: str = "持有") -> str:
    """Return the canonical Chinese 5-tier rating from prose text."""
    english_default = CHINESE_TO_ENGLISH.get(default, "HOLD")
    return ENGLISH_TO_CHINESE[_detect_rating(text, default=english_default)]


def _detect_rating(text: str, default: str) -> str:
    content = _normalize_text(text)
    if not content:
        return default

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        lines = [content]

    for line in lines:
        explicit = _match_patterns(line, _ENGLISH_EXPLICIT_PATTERNS, _ENGLISH_NEGATION_PATTERN)
        if explicit:
            return explicit
        explicit = _match_patterns(line, _CHINESE_EXPLICIT_PATTERNS, _CHINESE_NEGATION_PATTERN)
        if explicit:
            return explicit

    for line in lines:
        heuristic = _match_patterns(line, _ENGLISH_HEURISTIC_PATTERNS, _ENGLISH_NEGATION_PATTERN)
        if heuristic:
            return heuristic
        heuristic = _match_patterns(line, _CHINESE_HEURISTIC_PATTERNS, _CHINESE_NEGATION_PATTERN)
        if heuristic:
            return heuristic

    for line in lines:
        word_match = _match_patterns(line, _ENGLISH_WORD_PATTERNS, _ENGLISH_NEGATION_PATTERN)
        if word_match:
            return word_match
        word_match = _match_patterns(line, _CHINESE_WORD_PATTERNS, _CHINESE_NEGATION_PATTERN)
        if word_match:
            return word_match

    return default


def _match_patterns(
    text: str,
    patterns: list[tuple[str, re.Pattern[str]]],
    negation_pattern: re.Pattern[str],
) -> str | None:
    for rating, pattern in patterns:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 32): match.start()]
            if negation_pattern.search(prefix):
                continue
            return rating
    return None


def _normalize_english_rating(rating: str) -> str:
    if not rating:
        return "HOLD"
    upper = rating.strip().upper()
    if upper in RATINGS_5_TIER:
        return upper
    title = rating.strip().title()
    for canonical in RATINGS_5_TIER:
        if canonical.title() == title:
            return canonical
    return CHINESE_TO_ENGLISH.get(rating.strip(), "HOLD")


def _normalize_text(text: str) -> str:
    return (text or "").replace("：", ":").strip()
