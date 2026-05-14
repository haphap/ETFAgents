from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import TYPE_CHECKING, Any, Mapping, Sequence

if TYPE_CHECKING:
    from etfagents.agents.schemas import PortfolioDecision, TraderProposal

_PERCENT_RANGE_PATTERN = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*(?:%|％)\s*(?:-|–|—|~|～|至|到)\s*(?P<high>\d+(?:\.\d+)?)\s*(?:%|％)"
)
_PERCENT_SINGLE_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:%|％)")
_RATING_LINE_PATTERN = re.compile(
    r"(?im)^\s*(?:研究结论|最终配置建议|最终交易建议|执行倾向|final allocation proposal|final transaction proposal|execution bias|research view)\s*[:：].*$"
)

_TARGET_HINTS = (
    "target allocation",
    "target exposure",
    "allocation band",
    "target weight",
    "目标仓位",
    "目标配置",
    "目标暴露",
    "配置带",
    "基础仓位",
    "基准仓位",
)
_INITIAL_HINTS = (
    "initial",
    "starter",
    "base position",
    "试探仓",
    "初始",
    "底仓",
    "首仓",
    "建仓",
)
_RELATIVE_TARGET_HINTS = (
    "target allocation of",
    "target exposure of",
    "target weight of",
    "目标仓位的",
    "目标配置的",
)

_ADD_HINTS = (
    "add",
    "increase exposure",
    "build",
    "accumulate",
    "加仓",
    "增持",
    "回补",
    "上调",
    "提高仓位",
    "扩大仓位",
)
_REDUCE_HINTS = (
    "reduce",
    "trim",
    "cut position",
    "lower exposure",
    "减仓",
    "减持",
    "降低仓位",
    "降低敞口",
    "降仓",
    "止盈",
)
_EXIT_HINTS = (
    "exit",
    "close position",
    "sell",
    "stop out",
    "清仓",
    "卖出",
    "退出",
    "止损离场",
)
_REBALANCE_HINTS = (
    "rebalance",
    "rotate",
    "调仓",
    "再平衡",
    "轮动",
)
_RISK_HINTS = (
    "risk",
    "stop loss",
    "cut loss",
    "invalidation",
    "风控",
    "风险",
    "止损",
    "失效",
)
_MONITOR_HINTS = (
    "monitor",
    "watch",
    "track",
    "verify",
    "关注",
    "跟踪",
    "观察",
    "监控",
    "验证",
)

_DEFAULT_TARGET_WEIGHT_PCT = {
    "BUY": 35.0,
    "OVERWEIGHT": 25.0,
    "HOLD": 15.0,
    "UNDERWEIGHT": 5.0,
    "SELL": 0.0,
}

_RATING_PATTERNS = (
    ("BUY", re.compile(r"(?:buy|买入)", re.IGNORECASE)),
    ("OVERWEIGHT", re.compile(r"(?:overweight|增持)", re.IGNORECASE)),
    ("HOLD", re.compile(r"(?:hold|持有)", re.IGNORECASE)),
    ("UNDERWEIGHT", re.compile(r"(?:underweight|减持)", re.IGNORECASE)),
    ("SELL", re.compile(r"(?:sell|卖出)", re.IGNORECASE)),
)


@dataclass
class BacktestSignal:
    ticker: str
    decision_date: str
    source: str
    source_section: str
    rating: str
    target_weight_pct: float | None = None
    target_weight_min_pct: float | None = None
    target_weight_max_pct: float | None = None
    weight_source: str = "unknown"
    execution_delay: str = "next_open"
    starter_size_text: str = ""
    add_conditions: list[str] = field(default_factory=list)
    reduce_conditions: list[str] = field(default_factory=list)
    exit_conditions: list[str] = field(default_factory=list)
    rebalance_conditions: list[str] = field(default_factory=list)
    risk_controls: list[str] = field(default_factory=list)
    monitoring_points: list[str] = field(default_factory=list)
    signal_text_snapshot: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_trader_backtest_signal(
    ticker: str,
    decision_date: str,
    rendered_text: str,
    structured_plan: TraderProposal | None = None,
) -> dict[str, Any]:
    rating = _normalize_rating(
        getattr(structured_plan, "rating", None) or _parse_rating(rendered_text)
    )
    action_text = (
        _normalize_text(getattr(structured_plan, "execution_plan", ""))
        or _extract_markdown_section(
            rendered_text,
            ("## Allocation Execution Plan", "## 配置执行计划"),
        )
    )
    risk_text = (
        _normalize_text(getattr(structured_plan, "risk_management", ""))
        or _extract_markdown_section(
            rendered_text,
            ("## Rebalance and Risk Controls", "## 再平衡与风险控制"),
        )
    )
    signal = _build_signal(
        ticker=ticker,
        decision_date=decision_date,
        source="trader",
        source_section="execution_plan",
        rating=rating,
        primary_text=action_text,
        secondary_text=risk_text,
    )
    return signal.to_dict()


def build_portfolio_backtest_signal(
    ticker: str,
    decision_date: str,
    rendered_text: str,
    structured_plan: PortfolioDecision | None = None,
) -> dict[str, Any]:
    rating = _normalize_rating(
        getattr(structured_plan, "rating", None) or _parse_rating(rendered_text)
    )
    action_text = (
        _normalize_text(getattr(structured_plan, "positioning_recommendation", ""))
        or _strip_rating_lines(
            _extract_markdown_section(
                rendered_text,
                ("### （二）建议", "## Positioning Recommendation", "## 持仓建议"),
            )
        )
    )
    risk_text = (
        _normalize_text(getattr(structured_plan, "action_logic", ""))
        or _extract_markdown_section(
            rendered_text,
            ("## Action Logic", "## 行为逻辑"),
        )
    )
    signal = _build_signal(
        ticker=ticker,
        decision_date=decision_date,
        source="portfolio_manager",
        source_section="positioning_recommendation",
        rating=rating,
        primary_text=action_text,
        secondary_text=risk_text,
    )
    return signal.to_dict()


def build_state_backtest_signal(
    state: Mapping[str, Any],
    *,
    default_ticker: str | None = None,
    default_trade_date: str | None = None,
) -> dict[str, Any]:
    existing = _get_state_value(state, "backtest_signal", None)
    if isinstance(existing, Mapping) and existing:
        return dict(existing)

    portfolio_signal = state.get("portfolio_backtest_signal")
    if isinstance(portfolio_signal, Mapping) and portfolio_signal:
        return dict(portfolio_signal)

    trader_signal = state.get("trader_backtest_signal")
    if isinstance(trader_signal, Mapping) and trader_signal:
        return dict(trader_signal)

    ticker = default_ticker or _get_asset_symbol(state)
    trade_date = str(_get_state_value(state, "trade_date", default_trade_date or ""))
    final_decision = str(_get_state_value(state, "final_allocation_decision", ""))
    if final_decision:
        return build_portfolio_backtest_signal(
            ticker,
            trade_date,
            final_decision,
            None,
        )

    trader_plan = str(_get_state_value(state, "trader_allocation_plan", ""))
    if trader_plan:
        return build_trader_backtest_signal(
            ticker,
            trade_date,
            trader_plan,
            None,
        )

    rating = _parse_rating(str(_get_state_value(state, "research_allocation_plan", "")))
    return _build_signal(
        ticker=ticker,
        decision_date=trade_date,
        source="state_fallback",
        source_section="rating_only",
        rating=rating,
        primary_text="",
        secondary_text="",
    ).to_dict()


def build_candidate_backtest_signal(
    candidate: Mapping[str, Any],
    decision_date: str,
) -> dict[str, Any]:
    base = candidate.get("backtest_signal")
    signal = dict(base) if isinstance(base, Mapping) and base else {}
    ticker = str(candidate.get("ticker", signal.get("ticker", "")))
    rating = _normalize_rating(candidate.get("rating", signal.get("rating", "HOLD")))
    try:
        suggested_weight_pct = round(float(candidate.get("suggested_weight_pct", 0.0)), 4)
    except (TypeError, ValueError):
        suggested_weight_pct = 0.0

    signal.update(
        {
            "ticker": ticker,
            "decision_date": decision_date,
            "source": "candidate_pool",
            "source_section": signal.get("source_section", "positioning_recommendation"),
            "rating": rating,
            "target_weight_pct": suggested_weight_pct,
            "target_weight_min_pct": suggested_weight_pct,
            "target_weight_max_pct": suggested_weight_pct,
            "weight_source": "candidate_pool",
            "execution_delay": signal.get("execution_delay", "next_open"),
            "starter_size_text": signal.get("starter_size_text", ""),
            "add_conditions": list(signal.get("add_conditions", [])),
            "reduce_conditions": list(signal.get("reduce_conditions", [])),
            "exit_conditions": list(signal.get("exit_conditions", [])),
            "rebalance_conditions": list(signal.get("rebalance_conditions", [])),
            "risk_controls": list(signal.get("risk_controls", [])),
            "monitoring_points": list(signal.get("monitoring_points", [])),
            "signal_text_snapshot": str(
                signal.get("signal_text_snapshot")
                or candidate.get("final_allocation_decision", "")
            ).strip(),
        }
    )
    return signal


def _build_signal(
    *,
    ticker: str,
    decision_date: str,
    source: str,
    source_section: str,
    rating: str,
    primary_text: str,
    secondary_text: str,
) -> BacktestSignal:
    target_range, weight_source = _extract_target_weight(primary_text, secondary_text)
    if target_range is None:
        default_weight = _DEFAULT_TARGET_WEIGHT_PCT.get(rating, _DEFAULT_TARGET_WEIGHT_PCT["HOLD"])
        target_weight_pct = default_weight
        target_weight_min_pct = default_weight
        target_weight_max_pct = default_weight
        weight_source = "rating_map"
    else:
        low, high = target_range
        target_weight_pct = round((low + high) / 2, 4)
        target_weight_min_pct = round(low, 4)
        target_weight_max_pct = round(high, 4)

    starter_sentence = _extract_sentence_with_hints(primary_text, _INITIAL_HINTS)
    add_conditions = _collect_conditions(primary_text, secondary_text, hints=_ADD_HINTS)
    reduce_conditions = _collect_conditions(primary_text, secondary_text, hints=_REDUCE_HINTS)
    exit_conditions = _collect_conditions(primary_text, secondary_text, hints=_EXIT_HINTS)
    rebalance_conditions = _collect_conditions(
        primary_text,
        secondary_text,
        hints=_REBALANCE_HINTS,
    )
    risk_controls = _collect_conditions(primary_text, secondary_text, hints=_RISK_HINTS)
    monitoring_points = _collect_conditions(
        primary_text,
        secondary_text,
        hints=_MONITOR_HINTS,
    )
    snapshot = "\n".join(part for part in (_normalize_text(primary_text), _normalize_text(secondary_text)) if part)

    return BacktestSignal(
        ticker=ticker,
        decision_date=decision_date,
        source=source,
        source_section=source_section,
        rating=rating,
        target_weight_pct=target_weight_pct,
        target_weight_min_pct=target_weight_min_pct,
        target_weight_max_pct=target_weight_max_pct,
        weight_source=weight_source,
        starter_size_text=starter_sentence,
        add_conditions=add_conditions,
        reduce_conditions=reduce_conditions,
        exit_conditions=exit_conditions,
        rebalance_conditions=rebalance_conditions,
        risk_controls=risk_controls,
        monitoring_points=monitoring_points,
        signal_text_snapshot=snapshot,
    )


def _extract_target_weight(*texts: str) -> tuple[tuple[float, float] | None, str]:
    target_sentence = _extract_sentence_with_hints(" ".join(texts), _TARGET_HINTS)
    if target_sentence:
        weight = _extract_weight_range_from_sentence(target_sentence)
        if weight is not None:
            return weight, "parsed_target_range"

    for text in texts:
        starter_sentence = _extract_sentence_with_hints(text, _INITIAL_HINTS)
        if starter_sentence and not _contains_relative_target_reference(starter_sentence):
            weight = _extract_weight_range_from_sentence(starter_sentence)
            if weight is not None:
                return weight, "parsed_initial_range"

    return None, "unknown"


def _extract_weight_range_from_sentence(sentence: str) -> tuple[float, float] | None:
    if _contains_relative_target_reference(sentence):
        return None
    match = _PERCENT_RANGE_PATTERN.search(sentence)
    if match:
        low = float(match.group("low"))
        high = float(match.group("high"))
        return (min(low, high), max(low, high))
    single = _PERCENT_SINGLE_PATTERN.search(sentence)
    if single:
        value = float(single.group("value"))
        return (value, value)
    return None


def _contains_relative_target_reference(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered or hint in text for hint in _RELATIVE_TARGET_HINTS)


def _collect_conditions(*texts: str, hints: Sequence[str]) -> list[str]:
    collected: list[str] = []
    for text in texts:
        for sentence in _iter_sentences(text):
            lowered = sentence.lower()
            if any(hint in lowered or hint in sentence for hint in hints):
                collected.append(sentence)
    return _dedupe(collected)


def _extract_sentence_with_hints(text: str, hints: Sequence[str]) -> str:
    for sentence in _iter_sentences(text):
        lowered = sentence.lower()
        if any(hint in lowered or hint in sentence for hint in hints):
            return sentence
    return ""


def _iter_sentences(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    pieces = re.split(r"(?<=[。！？!?；;])\s+|\n+", normalized)
    return [piece.strip(" -\t") for piece in pieces if piece.strip(" -\t")]


def _extract_markdown_section(text: str, headings: Sequence[str]) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for heading in headings:
        pattern = re.compile(
            rf"(?m)^(?P<marks>#+)\s+{re.escape(heading.lstrip('#').strip())}\s*$"
        )
        match = pattern.search(normalized)
        if not match:
            continue
        level = len(match.group("marks"))
        remainder = normalized[match.end():]
        next_heading = re.search(rf"(?m)^#{{1,{level}}}\s+\S", remainder)
        section = remainder[: next_heading.start() if next_heading else len(remainder)]
        return _normalize_text(section)
    return ""


def _strip_rating_lines(text: str) -> str:
    return _normalize_text(_RATING_LINE_PATTERN.sub("", text))


def _normalize_text(text: str) -> str:
    content = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not content:
        return ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in content.split("\n")]
    return "\n".join(line for line in lines if line)


def _normalize_rating(rating: Any) -> str:
    return _parse_rating(str(getattr(rating, "value", rating or "HOLD")))


def _parse_rating(text: str) -> str:
    content = (text or "").strip()
    if not content:
        return "HOLD"
    normalized = content.upper()
    if normalized in _DEFAULT_TARGET_WEIGHT_PCT:
        return normalized
    for rating, pattern in _RATING_PATTERNS:
        if pattern.search(content):
            return rating
    return "HOLD"


def _get_state_value(state: Mapping[str, Any], key: str, default: Any = None) -> Any:
    aliases = {
        "asset_of_interest": ("company_of_interest",),
        "research_allocation_plan": ("investment_plan",),
        "trader_allocation_plan": ("trader_investment_plan",),
        "final_allocation_decision": ("final_trade_decision",),
        "backtest_signal": (),
        "trade_date": (),
    }
    candidates = (key, *aliases.get(key, ()))
    empty_seen = False
    for candidate in candidates:
        if candidate not in state:
            continue
        value = state[candidate]
        if value not in (None, ""):
            return value
        empty_seen = True
    return "" if empty_seen and default is None else default


def _get_asset_symbol(state: Mapping[str, Any], default: str = "unknown") -> str:
    return str(_get_state_value(state, "asset_of_interest", default) or default)


def _dedupe(items: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output
