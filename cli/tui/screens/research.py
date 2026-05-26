"""Research analysis screens: input, config modal, and run screen."""

from __future__ import annotations

import re
import textwrap
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Select,
    Static,
)

from cli.tui.services import (
    ANALYST_KEYS,
    AnalysisConfig,
    AnalysisEvent,
    AnalysisRunner,
    DebateProgress,
    IdRegistry,
    RESEARCH_DEPTH_REQUIREMENTS,
    ReportRepository,
    SECTION_BY_ID,
    SECTION_DEFINITIONS,
    SectionDone,
    SectionDef,
    TickerCancelled,
    TickerDone,
    TickerFailed,
    TickerStarted,
    WatchlistBoardRow,
    WatchlistBoardSnapshot,
    load_watchlist_board,
    section_definitions_for,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

LLM_PROVIDER_OPTIONS: list[tuple[str, str, str | None]] = [
    ("OpenAI", "openai", "https://api.openai.com/v1"),
    ("Google", "google", "https://generativelanguage.googleapis.com/v1"),
    ("Anthropic", "anthropic", "https://api.anthropic.com/"),
    ("DeepSeek", "deepseek", "https://api.deepseek.com"),
    ("xAI", "xai", "https://api.x.ai/v1"),
    ("MiniMax", "minimax", "https://api.minimax.chat/v1"),
    ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
    ("Ollama / llama.cpp", "ollama", "http://localhost:4000/v1"),
    ("vLLM", "vllm", "http://127.0.0.1:8020/v1"),
]

LLM_PROVIDER_ENDPOINTS = {
    provider: endpoint for _, provider, endpoint in LLM_PROVIDER_OPTIONS
}

# Sections that complete on first SectionDone (non-debate, single-shot)
_INSTANT_DONE_SECTIONS = set(ANALYST_KEYS) | {"research", "trader", "portfolio_manager"}
_RECENT_ETF_FALLBACKS = ("510300.SH", "159915.SZ", "513500.SH", "588000.SH", "518880.SH")
_ETF_DISPLAY_NAMES = {
    "510300.SH": "沪深300ETF",
    "159915.SZ": "创业板ETF",
    "513500.SH": "标普500ETF",
    "588000.SH": "科创50ETF",
    "518880.SH": "黄金ETF",
}


def _depth_option_label(depth_name: str) -> str:
    req = RESEARCH_DEPTH_REQUIREMENTS.get(depth_name, {})
    debate_rounds = req.get("debate_rounds", "?")
    risk_rounds = req.get("risk_rounds", "?")
    return f"{depth_name} (多空×{debate_rounds}, 风控×{risk_rounds})"


def _model_select_options(provider: str, mode: str) -> list[tuple[str, str]]:
    from etfagents.llm_clients.model_catalog import get_model_options

    if provider in ("vllm", "ollama"):
        from etfagents.llm_clients.model_catalog import fetch_local_models

        base_url = LLM_PROVIDER_ENDPOINTS.get(provider, "")
        live = fetch_local_models(base_url, provider)
        if live:
            return [(name, value) for name, value in live]

    options = get_model_options(provider, mode)
    if options:
        return [(_short_model_label(label), value) for label, value in options]
    return [("Custom / provider default", "custom")]


def _short_model_label(label: str) -> str:
    return label.split(" - ", 1)[0].strip()


def _safe_call_from_thread(screen: Any, callback: Any, *args: Any) -> None:
    """call_from_thread that silently exits if the app is shutting down."""
    try:
        if not getattr(screen.app, "_running", False):
            return
        screen.app.call_from_thread(callback, *args)
    except (RuntimeError, EOFError):
        pass


def _format_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _format_detail_text(detail: dict) -> str:
    lines: list[str] = []
    name = detail.get("name") or detail.get("ticker", "")
    ticker = detail.get("ticker", "")
    close = detail.get("close")
    pct = detail.get("pct_chg")

    if name:
        suffix = f" ({ticker})" if ticker and ticker != name else ""
        lines.append(f"名称：{name}{suffix}")

    if close is not None:
        pct_str = "--"
        if pct is not None:
            sign = "+" if pct >= 0 else ""
            pct_str = f"{sign}{pct:.2f}%"
        lines.append(f"收盘：{close:.3f} ({pct_str})")

    vol = detail.get("volume")
    if vol is not None:
        vc = detail.get("volume_change_pct")
        vc_str = "--"
        if vc is not None:
            vc_str = f"{vc:+.1f}%"
        lines.append(f"交易量：{vol / 1e4:.0f}万手 ({vc_str})")

    share = detail.get("fund_share")
    if share is not None:
        sc = detail.get("share_change_pct")
        sc_str = "--"
        if sc is not None:
            sc_str = f"{sc:+.1f}%"
        lines.append(f"份额：{share / 1e4:.0f}亿份 ({sc_str})")

    holdings = detail.get("holdings") or []
    if holdings:
        holding_parts: list[str] = []
        for index, h in enumerate(holdings[:5], 1):
            w = h.get("weight_pct")
            w_str = f"{w:.1f}%" if w is not None else "?"
            holding_parts.append(f"{index}. {h.get('name') or h.get('code') or '?'} {w_str}")
        lines.append(f"头部持仓：{'；'.join(holding_parts)}")

    return "\n".join(lines) if lines else "无数据"


def _format_price_rich(close: float | None, pct_chg: float | None) -> Text:
    """Rich Text with bold price and A-share colored change (red=up, green=down)."""
    price_str = f"{close:.3f}" if close is not None else "--"
    text = Text()
    text.append(price_str, style="bold")
    text.append("  ")
    if pct_chg is not None:
        sign = "+" if pct_chg >= 0 else ""
        pct_str = f"{sign}{pct_chg:.2f}%"
        if pct_chg > 0:
            text.append(pct_str, style="bold red")
        elif pct_chg < 0:
            text.append(pct_str, style="bold green")
        else:
            text.append(pct_str, style="dim")
    else:
        text.append("--", style="dim")
    return text


def _format_holdings_bars(holdings: list[dict] | None, max_bar: int = 6) -> Text:
    """Unicode bar chart for top holdings. E.g. '████ 中国石油 5.2%'."""
    if not holdings:
        return Text("无持仓数据", style="dim")
    top = holdings[:5]
    weights = [h.get("weight_pct") or 0 for h in top]
    max_w = max(weights) if weights else 1
    text = Text()
    for i, h in enumerate(top):
        w = h.get("weight_pct") or 0
        bar_len = round(w / max_w * max_bar) if max_w > 0 else 0
        bar = "█" * max(bar_len, 1)
        pad = " " * (max_bar - len(bar))
        name = str(h.get("name") or h.get("code") or "?").strip() or "?"
        display_name = name if len(name) <= 8 else f"{name[:7]}…"
        w_str = f"{w:.1f}%" if w else "?"
        if i > 0:
            text.append("\n")
        text.append(f"{bar}{pad} ", style="bold")
        text.append(f"{display_name} {w_str}")
    return text


def _format_detail_rich(detail: dict) -> dict[str, Any]:
    """Parse ETF detail dict into structured Rich renderables for card widgets."""
    name = detail.get("name") or detail.get("ticker", "")
    ticker = detail.get("ticker", "")
    display_name = name or ticker or "--"
    name_text = Text(f"代码: {display_name}", style="bold")

    close = detail.get("close")
    pct_chg = detail.get("pct_chg")
    price_text = Text("现价: ")
    price_text.append(_format_price_rich(close, pct_chg))

    parts: list[str] = []
    vol = detail.get("volume")
    if vol is not None:
        vc = detail.get("volume_change_pct")
        vc_str = f"{vc:+.1f}%" if vc is not None else "--"
        parts.append(f"量  : {vol / 1e4:.0f}万手 ({vc_str})")
    turnover = detail.get("turnover_rate") or detail.get("turnover")
    if turnover is not None:
        parts.append(f"换手: {turnover:.1f}%")
    else:
        parts.append("换手: --")
    share = detail.get("fund_share")
    if share is not None:
        sc = detail.get("share_change_pct")
        sc_str = f"{sc:+.1f}%" if sc is not None else "--"
        parts.append(f"份额: {share / 1e4:.0f}亿份 ({sc_str})")
    metrics_text = "\n".join(parts) if parts else ""

    holdings_bars = Text("持仓占比 TOP5:\n", style="bold")
    holdings_bars.append(_format_holdings_bars(detail.get("holdings")))

    return {
        "name_text": name_text,
        "price_text": price_text,
        "metrics_text": metrics_text,
        "holdings_bars": holdings_bars,
    }


_RATING_LABELS = {
    "BUY": "买入",
    "OVERWEIGHT": "增持",
    "HOLD": "持有",
    "UNDERWEIGHT": "减持",
    "SELL": "卖出",
}


def _signal_number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "--"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if suffix == "%":
        return f"{num:.1f}%"
    return f"{num:.3f}".rstrip("0").rstrip(".")


def _signal_threshold(rule: dict[str, Any]) -> str:
    threshold = rule.get("threshold")
    if isinstance(threshold, (list, tuple)) and len(threshold) == 2:
        return f"{_signal_number(threshold[0])}-{_signal_number(threshold[1])}"
    return _signal_number(threshold)


_CONDITION_STRIP_RE = re.compile(r"^\s*\d+[.、)）]\s*|^[-*•]\s*|`[^`]*`")
_PRICE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)(?:\s*元)")


def _clean_condition_text(text: str) -> str:
    """Strip leading numbering, backtick wrappers, and key prefixes from condition text."""
    cleaned = _CONDITION_STRIP_RE.sub("", text).strip()
    # Strip leading key-like prefixes: "加仓触发条件：" / "reduce_triggers: ..."
    cleaned = re.sub(r"^[\w_]+\s*[:：]\s*", "", cleaned)
    # Strip leading quoted labels like `加仓触发条件` –
    cleaned = re.sub(r"^[`「『].*?[`」』]\s*[-–—]\s*", "", cleaned)
    return cleaned.strip()


def _first_rule_line(signal: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = signal.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                note = first.get("note") or first.get("action") or ""
                threshold = _signal_threshold(first)
                metric = first.get("metric") or ""
                op = first.get("op") or ""
                parts = [part for part in (metric, op, threshold) if part and part != "--"]
                prefix = " ".join(parts)
                return f"{prefix} {note}".strip() if note else prefix
            if isinstance(first, str):
                return _clean_condition_text(first)
    return ""


def _extract_price_rule(signal: dict[str, Any], rule_keys: tuple[str, ...], actions: tuple[str, ...]) -> float | None:
    # First try structured trigger rules
    for key in rule_keys:
        rules = signal.get(key)
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            metric = str(rule.get("metric") or "").lower()
            action = str(rule.get("action") or "").lower()
            if metric not in {"close", "price", "nav"}:
                continue
            if actions and not any(hint in action for hint in actions):
                continue
            threshold = rule.get("threshold")
            if isinstance(threshold, (int, float)):
                return float(threshold)
    return None


def _extract_price_from_text(
    signal: dict[str, Any],
    text_keys: tuple[str, ...],
    hint_patterns: tuple[str, ...],
) -> float | None:
    """Extract a price from condition text using hint patterns near '元' prices."""
    for key in text_keys:
        items = signal.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, str):
                continue
            for hint in hint_patterns:
                # Look for pattern: hint...price元 or price元...hint (within ~30 chars)
                for m in _PRICE_PATTERN.finditer(item):
                    price_pos = m.start()
                    try:
                        price = float(m.group(1))
                    except ValueError:
                        continue
                    # Check if any hint is near this price (within 40 chars)
                    context_start = max(0, price_pos - 40)
                    context_end = min(len(item), price_pos + 40)
                    context = item[context_start:context_end]
                    if hint in context:
                        return price
    return None


def _weight_bar(pct: float | None, max_pct: float = 50.0, bar_width: int = 10) -> str:
    """Render a Unicode bar chart for portfolio weight, e.g. '██░░░░░░░░ **2.0%**'."""
    if pct is None:
        return "--"
    filled = round(pct / max_pct * bar_width) if max_pct > 0 else 0
    filled = max(0, min(filled, bar_width))
    return "█" * filled + "░" * (bar_width - filled) + f" **{pct:.1f}%**"


def _price_ruler(stop: float, current: float, target: float, width: int = 36) -> str:
    """Draw a text ruler with labels ordered by their numeric price.

    Returns empty string when the range is degenerate.
    """
    values = [
        ("止损价", stop),
        ("现价", current),
        ("目标价", target),
    ]
    ordered = sorted(values, key=lambda item: item[1])
    grouped: list[tuple[float, list[str]]] = []
    for label, value in ordered:
        if grouped and value == grouped[-1][0]:
            grouped[-1][1].append(label)
        else:
            grouped.append((value, [label]))

    span = grouped[-1][0] - grouped[0][0]
    if span <= 0:
        return ""

    labels = [
        f"{'╋ ' if '现价' in label_group else ''}{'/'.join(label_group)} {_signal_number(value)}"
        for value, label_group in grouped
    ]
    connectors: list[str] = []
    connector_budget = max(width, 6)
    for index in range(len(grouped) - 1):
        distance = grouped[index + 1][0] - grouped[index][0]
        length = max(3, round(distance / span * connector_budget))
        connectors.append("─" * length)

    parts: list[str] = []
    for index, label in enumerate(labels):
        if index:
            parts.append(connectors[index - 1])
        parts.append(label)
    ruler_line = " ".join(parts)

    return (
        f"```\n"
        f"{ruler_line}\n"
        f"```"
    )


def _price_trend_chart(
    prices: list[float],
    *,
    height: int = 6,
    width: int = 38,
    stop_price: float | None = None,
    target_price: float | None = None,
) -> str:
    """Render a multi-line ASCII price trend chart inside Markdown code fences.

    Args:
        prices: Chronological close prices (oldest first).
        height: Number of Y-axis rows.
        width: Maximum character width including Y-axis labels.
        stop_price: Optional stop-loss reference line.
        target_price: Optional target reference line.

    Returns:
        Markdown code-fenced chart string, or "" if data is insufficient.
    """
    if len(prices) < 2:
        return ""

    lo, hi = min(prices), max(prices)
    # Extend range to include reference prices if within 20% of range
    span = hi - lo if hi != lo else abs(hi) * 0.1 or 0.1
    margin = span * 0.2
    for ref in (stop_price, target_price):
        if ref is not None:
            if lo - margin <= ref <= hi + margin:
                lo = min(lo, ref)
                hi = max(hi, ref)

    if hi == lo:
        # Flat prices — render a simple single-row line
        label = f"{hi:.2f}" if hi < 100 else f"{hi:.1f}"
        label_w = len(label) + 2  # "label ┤"
        plot_w = max(width - label_w - 1, len(prices))
        dots = "·" * (len(prices) - 1) + "●"
        if len(dots) > plot_w:
            dots = dots[:plot_w]
        return f"```\n{label:>{label_w - 2}} ┤{dots}\n{'':>{label_w - 2}} └{'─' * len(dots)}\n```"

    # Y-axis label formatting
    decimals = 2 if hi < 100 else 1
    fmt = f".{decimals}f"
    levels = [hi - i * (hi - lo) / (height - 1) for i in range(height)]
    labels = [f"{lv:{fmt}}" for lv in levels]
    label_w = max(len(lb) for lb in labels) + 1  # +1 for space before ┤

    # Available plot width
    plot_w = width - label_w - 1  # subtract ┤
    if plot_w < 4:
        plot_w = 4

    # Downsample if needed (preserve first and last)
    if len(prices) > plot_w:
        indices = [round(i * (len(prices) - 1) / (plot_w - 1)) for i in range(plot_w)]
        sampled = [prices[idx] for idx in indices]
    else:
        sampled = list(prices)

    n = len(sampled)

    # Determine reference line rows
    def _row_for_price(p: float) -> int | None:
        if p < lo or p > hi:
            return None
        return round((hi - p) / (hi - lo) * (height - 1))

    stop_row = _row_for_price(stop_price) if stop_price is not None else None
    target_row = _row_for_price(target_price) if target_price is not None else None

    # Build grid
    chart_lines: list[str] = []
    for row in range(height):
        level = levels[row]
        half_step = (hi - lo) / (height - 1) / 2
        cells: list[str] = []
        for col in range(n):
            val = sampled[col]
            if abs(val - level) <= half_step:
                if col == n - 1:
                    cells.append("●")
                elif col >= n - 3:
                    cells.append("○")
                else:
                    cells.append("·")
            else:
                cells.append(" ")
        plot = "".join(cells)

        # Add reference line dashes in empty positions
        ref_label = ""
        is_ref_row = False
        if stop_row == row and target_row == row:
            ref_label = "止/标"
            is_ref_row = True
        elif stop_row == row:
            ref_label = "止"
            is_ref_row = True
        elif target_row == row:
            ref_label = "标"
            is_ref_row = True

        if is_ref_row:
            plot_chars = list(plot)
            for i in range(len(plot_chars)):
                if plot_chars[i] == " ":
                    plot_chars[i] = "╌"
            plot = "".join(plot_chars)

        label = labels[row]
        line = f"{label:>{label_w}}┤{plot}"
        if ref_label:
            line += f" {ref_label}"
        chart_lines.append(line)

    # X-axis
    x_axis = f"{'':>{label_w}}└{'─' * n}"
    chart_lines.append(x_axis)

    return "```\n" + "\n".join(chart_lines) + "\n```"


_RATING_EMOJI = {
    "BUY": "🟢",
    "OVERWEIGHT": "🟢",
    "HOLD": "🟡",
    "UNDERWEIGHT": "🔴",
    "SELL": "🔴",
}


def _truncate_condition(text: str, limit: int = 50) -> str:
    """Truncate a cleaned condition string with ellipsis."""
    if not text:
        return ""
    for sep in ("。", "；", "，", ",", ";"):
        idx = text.find(sep)
        if 0 < idx <= limit:
            return text[: idx + 1]
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _format_summary_note(label: str, text: str, width: int = 46) -> list[str]:
    if not text:
        return []
    wrapped = textwrap.wrap(
        text,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return [f"**{label}：**", *(wrapped or [text])]


def _format_execution_summary(signal: dict[str, Any] | None, detail: dict[str, Any] | None = None) -> str:
    """Build a Markdown execution summary from a backtest signal."""
    if not signal:
        return "*等待组合经理生成结构化投资策略。*"

    rating = str(signal.get("rating") or "HOLD").upper()
    rating_label = _RATING_LABELS.get(rating, rating)
    target_weight = signal.get("target_weight_pct")
    weight_min = signal.get("target_weight_min_pct")
    weight_max = signal.get("target_weight_max_pct")
    execution_delay = signal.get("execution_delay") or "--"
    add_line = _first_rule_line(signal, ("add_triggers", "add_conditions"))
    reduce_line = _first_rule_line(signal, ("reduce_triggers", "reduce_conditions", "exit_triggers", "exit_conditions"))
    risk_line = _first_rule_line(signal, ("risk_rules", "risk_controls"))
    current = detail.get("close") if detail else None

    target_price = _extract_price_rule(signal, ("add_triggers", "rebalance_triggers"), ("add", "buy", "rebalance"))
    if target_price is None:
        target_price = _extract_price_from_text(
            signal, ("add_conditions",), ("突破", "加仓", "目标", "上方", "上行"),
        )
    stop_price = _extract_price_rule(signal, ("risk_rules", "reduce_triggers", "exit_triggers"), ("reduce", "exit", "sell", "stop"))
    if stop_price is None:
        stop_price = _extract_price_from_text(
            signal, ("risk_controls", "reduce_conditions"), ("止损", "跌破", "防守", "下方", "stop"),
        )

    emoji = _RATING_EMOJI.get(rating, "🟡")
    lines: list[str] = []

    lines.append(f"{emoji} 研报结论：**{rating_label}**")
    lines.append("")

    weight_str = _weight_bar(target_weight)
    if weight_min is not None or weight_max is not None:
        weight_str += f"  (区间 {_signal_number(weight_min, '%')}-{_signal_number(weight_max, '%')})"
    lines.append(f"推荐仓位：{weight_str}")

    if target_price is not None:
        lines.append(f"目标价格：**{_signal_number(target_price)}** 🎯")
    if stop_price is not None:
        lines.append(f"止损价格：**{_signal_number(stop_price)}** 🛡️")
    if current is not None:
        lines.append(f"现价位置：**{_signal_number(current)}**")

    if stop_price is not None and target_price is not None and current is not None:
        ruler = _price_ruler(stop_price, current, target_price)
        if ruler:
            lines.append("")
            lines.append(ruler)

    # Price trend chart
    price_history = detail.get("price_history") if detail else None
    if price_history:
        close_prices = [p["close"] for p in price_history if p.get("close") is not None]
        if close_prices:
            chart = _price_trend_chart(
                close_prices,
                stop_price=stop_price,
                target_price=target_price,
            )
            if chart:
                lines.append("")
                lines.append("📉 价格趋势")
                lines.append(chart)

    lines.append("")
    lines.append(f"执行延迟：{execution_delay}")
    for note_line in _format_summary_note("加仓依据", add_line):
        lines.append(note_line)
    for note_line in _format_summary_note("减仓依据", reduce_line):
        lines.append(note_line)
    for note_line in _format_summary_note("风控规则", risk_line):
        lines.append(note_line)
    return "\n".join(lines)


_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![\w`*])("
    r"\d{4}-\d{2}-\d{2}|"
    r"[+-]?\d+(?:\.\d+)?\s*(?:%|％|倍|万手|亿份|元|日|天|周|月)?"
    r")(?![\w`*]|\.\s)"
)


def _highlight_report_numbers(markdown: str) -> str:
    """Bold numeric tokens in prose without disturbing code blocks or tables."""
    if not markdown:
        return markdown
    highlighted: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            highlighted.append(line)
            continue
        if in_fence or stripped.startswith("|"):
            highlighted.append(line)
            continue

        parts = re.split(r"(`[^`]*`)", line)
        rendered_parts: list[str] = []
        for part in parts:
            if part.startswith("`") and part.endswith("`"):
                rendered_parts.append(part)
            else:
                rendered_parts.append(_NUMERIC_TOKEN_RE.sub(r"**\1**", part))
        highlighted.append("".join(rendered_parts))
    return "\n".join(highlighted)


def _extract_ai_summary(pm_content: str) -> str:
    """Extract a one-line conclusion from portfolio manager content."""
    if not pm_content:
        return ""
    for marker in ("结论", "建议", "Decision Summary", "recommendation", "决策摘要"):
        for line in pm_content.splitlines():
            if marker.lower() in line.lower():
                clean = re.sub(r"^[#*\-\s]+", "", line).strip()
                clean = re.sub(r"^(结论|建议|Decision Summary|决策摘要)[：:]\s*", "", clean)
                if clean:
                    return clean[:60]
    return ""


def _fmt_price(value: float | None) -> str:
    return "--" if value is None else f"{value:.3f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "--"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _a_share_value_class(value: float | None) -> str:
    if value is None:
        return "muted"
    if value > 0:
        return "a-share-up"
    if value < 0:
        return "a-share-down"
    return "muted"


def _action_class(action: str) -> str:
    if action in {"减仓", "清仓"}:
        return "action-risk"
    if action in {"加仓", "增持"}:
        return "action-opportunity"
    return "action-neutral"


def _build_analysis_runner(cfg: AnalysisConfig) -> AnalysisRunner:
    from etfagents.default_config import DEFAULT_CONFIG
    import copy
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["llm_provider"] = cfg.llm_provider
    config["backend_url"] = cfg.backend_url or LLM_PROVIDER_ENDPOINTS.get(cfg.llm_provider)
    config["output_language"] = cfg.output_language
    depth_req = RESEARCH_DEPTH_REQUIREMENTS.get(cfg.depth_name, {})
    if depth_req:
        config["max_debate_rounds"] = depth_req.get("debate_rounds", 1)
        config["max_risk_discuss_rounds"] = depth_req.get("risk_rounds", 1)
    if cfg.quick_model:
        config["quick_think_llm"] = cfg.quick_model
    if cfg.deep_model:
        config["deep_think_llm"] = cfg.deep_model
    if not cfg.quick_model or not cfg.deep_model:
        _apply_provider_model_defaults(
            config,
            cfg,
            fill_quick=not cfg.quick_model,
            fill_deep=not cfg.deep_model,
        )
    return AnalysisRunner(config=config)


def _apply_provider_model_defaults(
    config: dict[str, Any],
    cfg: AnalysisConfig,
    *,
    fill_quick: bool = True,
    fill_deep: bool = True,
) -> None:
    """Keep TUI provider selection from reusing OpenAI default model names."""
    from etfagents.llm_clients.model_catalog import get_model_options, recommend_models

    provider = cfg.llm_provider.lower()
    rec = recommend_models(cfg.depth_name, provider)
    quick_model = rec.get("quick_model")
    deep_model = rec.get("deep_model")

    if not quick_model:
        quick_options = get_model_options(provider, "quick")
        quick_model = quick_options[0][1] if quick_options else None
    if not deep_model:
        deep_options = get_model_options(provider, "deep")
        deep_model = deep_options[0][1] if deep_options else None

    if fill_quick and quick_model:
        config["quick_think_llm"] = quick_model
    if fill_deep and deep_model:
        config["deep_think_llm"] = deep_model


def _debate_progress_bar(current: int, total: int) -> str:
    """Build ▓▓░ progress bar string."""
    if total <= 0:
        return ""
    filled = min(current, total)
    return "▓" * filled + "░" * (total - filled) + f" {current}/{total}"


# ---------------------------------------------------------------------------
# AnalysisConfigModal
# ---------------------------------------------------------------------------

class AnalysisConfigModal(ModalScreen[AnalysisConfig | None]):
    """Modal to configure analysis parameters before running."""

    DEFAULT_CSS = """
    AnalysisConfigModal { align: center middle; }
    #acm_container { width: 84; height: auto; max-height: 42; border: solid $accent; background: $surface; padding: 1 2; }
    #acm_container .acm-row { height: auto; margin: 0; }
    #acm_container .acm-col { width: 1fr; height: auto; margin-right: 2; }
    #acm_container .acm-col:last-of-type { margin-right: 0; }
    #acm_container Static { height: 1; margin: 0; }
    #acm_container Checkbox { height: 1; margin: 0; }
    #acm_container Select { height: auto; margin: 0; }
    #acm_container Input { height: auto; margin: 0; }
    #acm_container .acm-label { color: $text-muted; text-style: bold; }
    #acm_container .analyst-panel { height: auto; border: solid $panel; padding: 0 1; margin: 0 0 1 0; }
    #acm_container .analyst-groups { height: auto; }
    #acm_container .analyst-group { width: 1fr; height: auto; margin-right: 2; }
    #acm_container .analyst-group:last-of-type { margin-right: 0; }
    #acm_container .analyst-group-title { color: $accent; }
    #acm_container .acm-summary { color: $text-muted; margin: 0 0 1 0; }
    #acm_container .acm-error { margin: 0 0 1 0; }
    #acm_container .acm-actions { height: 3; margin: 0; }
    #acm_container .acm-action-spacer { width: 1fr; }
    #acm_container .acm-confirm { width: 14; height: 3; margin: 0 0 0 1; border: solid $accent; background: $accent; color: $surface; content-align: center middle; text-style: bold; }
    #acm_container .acm-cancel { width: 10; height: 3; margin: 0 0 0 1; border: solid $panel; color: $text-muted; content-align: center middle; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="acm_container"):
            yield Static("分析配置", classes="pane-title")
            with Vertical(classes="analyst-panel"):
                yield Static("分析维度", classes="acm-label")
                with Horizontal(classes="analyst-groups"):
                    with Vertical(classes="analyst-group"):
                        yield Static("基本面 / 宏观", classes="analyst-group-title")
                        for defn in self._analyst_defs(("macro_regime", "meso_commodity", "holdings_industry")):
                            yield Checkbox(
                                defn.title,
                                value=True,
                                id=f"acm_cb_{defn.section_id}",
                                compact=True,
                            )
                    with Vertical(classes="analyst-group"):
                        yield Static("市场 / 微观", classes="analyst-group-title")
                        for defn in self._analyst_defs(("market_flow", "catalyst_sentiment", "top_holdings")):
                            yield Checkbox(
                                defn.title,
                                value=True,
                                id=f"acm_cb_{defn.section_id}",
                                compact=True,
                            )
            with Horizontal(classes="acm-row"):
                with Vertical(classes="acm-col"):
                    yield Static("日期", classes="acm-label")
                    yield Input(
                        value=datetime.now().date().isoformat(),
                        placeholder="YYYY-MM-DD",
                        id="acm_analysis_date",
                    )
                with Vertical(classes="acm-col"):
                    yield Static("深度", classes="acm-label")
                    depth_options = [
                        (_depth_option_label(name), name) for name in RESEARCH_DEPTH_REQUIREMENTS
                    ]
                    yield Select(depth_options, value="标准", id="acm_depth")
            with Horizontal(classes="acm-row"):
                with Vertical(classes="acm-col"):
                    yield Static("语言", classes="acm-label")
                    lang_options = [("中文", "Chinese"), ("English", "English")]
                    yield Select(lang_options, value="Chinese", id="acm_language")
                with Vertical(classes="acm-col"):
                    yield Static("提供商", classes="acm-label")
                    provider_options = [
                        (display, provider) for display, provider, _ in LLM_PROVIDER_OPTIONS
                    ]
                    yield Select(provider_options, value="openai", id="acm_provider")
            with Horizontal(classes="acm-row"):
                with Vertical(classes="acm-col"):
                    yield Static("快速模型", classes="acm-label")
                    quick_options = _model_select_options("openai", "quick")
                    yield Select(quick_options, value=quick_options[0][1], id="acm_quick_model")
                with Vertical(classes="acm-col"):
                    yield Static("深度模型", classes="acm-label")
                    deep_options = _model_select_options("openai", "deep")
                    yield Select(deep_options, value=deep_options[0][1], id="acm_deep_model")
            yield Static("", id="acm_summary", classes="acm-summary")
            yield Static("", id="acm_error", classes="error-text acm-error")
            with Horizontal(classes="acm-actions"):
                yield Static("", classes="acm-action-spacer")
                yield Button("取消", id="btn_acm_cancel", classes="acm-cancel")
                yield Button("确认分析", id="btn_acm_ok", classes="acm-confirm")

    def on_mount(self) -> None:
        self._refresh_summary()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_acm_ok":
            selected = [
                k for k in ANALYST_KEYS
                if self._checkbox_checked(f"acm_cb_{k}")
            ]
            depth = self.query_one("#acm_depth", Select).value
            provider = self.query_one("#acm_provider", Select).value
            quick_model = self.query_one("#acm_quick_model", Select).value
            deep_model = self.query_one("#acm_deep_model", Select).value
            language = self.query_one("#acm_language", Select).value
            analysis_date = self.query_one("#acm_analysis_date", Input).value.strip()
            if analysis_date:
                try:
                    datetime.strptime(analysis_date, "%Y-%m-%d")
                except ValueError:
                    self.query_one("#acm_error", Static).update("分析日期必须是 YYYY-MM-DD 格式。")
                    return
            self.query_one("#acm_error", Static).update("")
            self.dismiss(AnalysisConfig(
                selected_analysts=selected or list(ANALYST_KEYS),
                analysis_date=analysis_date or None,
                depth_name=str(depth) if depth != Select.BLANK else "标准",
                llm_provider=str(provider) if provider != Select.BLANK else "openai",
                backend_url=LLM_PROVIDER_ENDPOINTS.get(str(provider)),
                quick_model=str(quick_model) if quick_model != Select.BLANK else None,
                deep_model=str(deep_model) if deep_model != Select.BLANK else None,
                output_language=str(language) if language != Select.BLANK else "Chinese",
            ))
        elif event.button.id == "btn_acm_cancel":
            self.dismiss(None)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "acm_provider":
            provider = str(event.value) if event.value != Select.BLANK else "openai"
            quick_options = _model_select_options(provider, "quick")
            deep_options = _model_select_options(provider, "deep")
            quick_select = self.query_one("#acm_quick_model", Select)
            deep_select = self.query_one("#acm_deep_model", Select)
            quick_select.set_options(quick_options)
            quick_select.value = quick_options[0][1]
            deep_select.set_options(deep_options)
            deep_select.value = deep_options[0][1]
        self._refresh_summary()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        self._refresh_summary()

    def _analyst_defs(self, section_ids: tuple[str, ...]) -> list[SectionDef]:
        by_id = {defn.section_id: defn for defn in SECTION_DEFINITIONS if defn.team == "分析师"}
        return [by_id[section_id] for section_id in section_ids if section_id in by_id]

    def _refresh_summary(self) -> None:
        selected_titles = [
            SECTION_BY_ID[key].title for key in ANALYST_KEYS
            if self._checkbox_checked(f"acm_cb_{key}") and key in SECTION_BY_ID
        ]
        depth = self.query_one("#acm_depth", Select).value
        quick_model = self.query_one("#acm_quick_model", Select).value
        deep_model = self.query_one("#acm_deep_model", Select).value
        analyst_text = "、".join(selected_titles[:2])
        if len(selected_titles) > 2:
            analyst_text += f"等 {len(selected_titles)} 个维度"
        elif not analyst_text:
            analyst_text = "默认全选"
        self.query_one("#acm_summary", Static).update(
            f"已选择：{analyst_text}；深度：{depth or '标准'}；模型：{quick_model or '默认'} / {deep_model or '默认'}"
        )

    def _checkbox_checked(self, widget_id: str) -> bool:
        try:
            return self.query_one(f"#{widget_id}", Checkbox).value
        except Exception:
            return False


# ---------------------------------------------------------------------------
# ErrorDetailModal
# ---------------------------------------------------------------------------

class ErrorDetailModal(ModalScreen[None]):
    """Modal showing fatal analysis error with traceback."""

    DEFAULT_CSS = """
    ErrorDetailModal { align: center middle; }
    #err_container {
        width: 80; height: auto; max-height: 38;
        border: double $error; background: $surface; padding: 1 2;
    }
    #err_container .err-title {
        color: $error; text-style: bold; height: 1; margin-bottom: 1;
    }
    #err_container .err-desc {
        color: $text; height: auto; margin-bottom: 1;
    }
    #err_container .err-summary-box {
        height: auto; max-height: 6;
        border: solid $warning; padding: 0 1; margin-bottom: 1;
    }
    #err_container .err-summary {
        color: $warning; height: auto;
    }
    #err_container .err-tb-scroll {
        height: auto; max-height: 14;
        border: solid $panel; background: $surface-darken-1;
        padding: 0 1; scrollbar-size: 1 1;
    }
    #err_container .err-tb {
        color: $text-muted; height: auto;
    }
    #err_container .err-actions {
        height: 3; margin-top: 1; align-horizontal: center;
    }
    #err_container .err-close {
        width: 18; height: 3;
        border: solid $error; background: transparent;
        color: $error; content-align: center middle; text-style: bold;
    }
    """

    def __init__(self, ticker: str, error: str, traceback_text: str = "") -> None:
        super().__init__()
        self._ticker = ticker
        self._error = error
        self._traceback_text = traceback_text

    def compose(self) -> ComposeResult:
        with Vertical(id="err_container"):
            yield Static("✕  分析中断 — 致命错误", classes="err-title")
            yield Static(
                f"agents 运行过程中发生不可恢复的错误，{self._ticker} 分析已终止。",
                classes="err-desc",
            )
            summary_box = Vertical(classes="err-summary-box")
            summary_box.border_title = "错误摘要"
            with summary_box:
                yield Static(self._error, classes="err-summary")
            if self._traceback_text:
                tb_box = ScrollableContainer(classes="err-tb-scroll")
                tb_box.border_title = "完整 Traceback"
                with tb_box:
                    yield Static(self._traceback_text, classes="err-tb")
            with Horizontal(classes="err-actions"):
                yield Button("关闭  Esc", id="btn_err_close", classes="err-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_err_close":
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# ResearchAnalysisScreen (input)
# ---------------------------------------------------------------------------

class ResearchAnalysisScreen(Screen):
    """Collect ETF analysis input, then open the dedicated run screen."""

    def __init__(self, runner: AnalysisRunner | None = None, repository: ReportRepository | None = None):
        super().__init__()
        self.runner = runner
        self.repository = repository or ReportRepository()
        self._analysis_config: AnalysisConfig | None = None
        self._selected_tickers: list[str] = []
        self._selected_tag_generation = 0

    def compose(self) -> ComposeResult:
        recent_cards = self._recent_etf_cards()
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane research-entry-pane"):
                yield Static("创建研究任务", classes="pane-title")
                yield Static("ETF 代码", classes="input-label")
                yield Input(placeholder="输入代码后按 Enter 生成标签", id="ra_ticker_input")
                yield Static("可输入多个代码，用逗号或空格分隔。", classes="entry-help")
                with Horizontal(id="selected_ticker_tags", classes="selected-tags"):
                    yield Static("尚未选择 ETF", id="selected_ticker_empty", classes="selected-empty")
                yield Static("已选择 0 个 ETF", id="selected_ticker_count", classes="selected-count")
                with Horizontal(classes="entry-actions"):
                    yield Button("开始分析", id="btn_ra_start", classes="entry-primary", disabled=True)
                    yield Button("⚙ 配置", id="btn_ra_config", classes="entry-config")
                yield Static("近期研究", classes="entry-section-title")
                with Vertical(classes="recent-card-list"):
                    for card in recent_cards:
                        yield Button(
                            f"{card['ticker']}  {card['name']}\n{card['date']}  {card['rating']}",
                            id=f"recent-{IdRegistry('recent').register(card['ticker'])}",
                            classes="recent-card",
                        )
            with Vertical(classes="right-pane research-board-pane"):
                yield Static("自选股看板 / Watchlist Monitor", classes="pane-title")
                with ScrollableContainer(id="watchlist_cards"):
                    yield Static("加载自选股看板...", id="watchlist_status", classes="watchlist-status")
                yield Static("部分字段来自最新可用日线，非实时行情", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#ra_ticker_input", Input).focus()
        self._start_watchlist_loading()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in {"btn_ra_start", "btn_ra_config"}:
            self._start_config_flow()
        elif (event.button.id or "").startswith("recent-"):
            self._add_tickers_to_selection([str(event.button.label).split()[0]])
        elif (event.button.id or "").startswith("wl-"):
            self._add_tickers_to_selection([str(event.button.label)])
        elif (event.button.id or "").startswith("sel-"):
            self._remove_ticker_from_selection(str(event.button.label))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ra_ticker_input":
            self._commit_input_tickers()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "ra_ticker_input":
            self._refresh_start_button_state()

    def _start_config_flow(self) -> None:
        tickers = self._read_tickers()
        if not tickers:
            self.query_one("#selected_ticker_count", Static).update("请输入至少一个 ETF 代码。")
            return
        self.app.push_screen(AnalysisConfigModal(), self._on_config_result)

    def _commit_input_tickers(self) -> None:
        input_widget = self.query_one("#ra_ticker_input", Input)
        tickers = self._parse_tickers(input_widget.value)
        self._add_tickers_to_selection(tickers)
        input_widget.value = ""
        input_widget.focus()

    def _add_tickers_to_selection(self, tickers: list[str]) -> None:
        changed = False
        for ticker in tickers:
            cleaned = ticker.strip().upper()
            if cleaned and cleaned not in self._selected_tickers:
                self._selected_tickers.append(cleaned)
                changed = True
        if changed:
            self._refresh_selected_ticker_tags()
        else:
            self._refresh_start_button_state()
        self.query_one("#ra_ticker_input", Input).focus()

    def _refresh_selected_ticker_tags(self) -> None:
        tags = self.query_one("#selected_ticker_tags", Horizontal)
        self._selected_tag_generation += 1
        for child in list(tags.children):
            child.remove()
        if not self._selected_tickers:
            tags.mount(Static("尚未选择 ETF", id="selected_ticker_empty", classes="selected-empty"))
        else:
            registry = IdRegistry("sel")
            for ticker in self._selected_tickers:
                tags.mount(
                    Button(
                        f"{ticker} ×",
                        id=f"sel-{self._selected_tag_generation}-{registry.register(ticker)}",
                        classes="selected-chip",
                    )
                )
        self.query_one("#selected_ticker_count", Static).update(f"已选择 {len(self._selected_tickers)} 个 ETF")
        self._refresh_start_button_state()

    def _refresh_start_button_state(self) -> None:
        has_tickers = bool(self._selected_tickers or self._parse_tickers(self.query_one("#ra_ticker_input", Input).value))
        self.query_one("#btn_ra_start", Button).disabled = not has_tickers

    def _remove_ticker_from_selection(self, ticker: str) -> None:
        cleaned = ticker.replace("×", "").strip().upper()
        self._selected_tickers = [existing for existing in self._selected_tickers if existing != cleaned]
        self._refresh_selected_ticker_tags()
        self.query_one("#ra_ticker_input", Input).focus()

    def _start_watchlist_loading(self) -> None:
        threading.Thread(
            target=self._load_watchlist_snapshot,
            daemon=True,
            name="etfagents-tui-watchlist",
        ).start()

    def _load_watchlist_snapshot(self) -> None:
        try:
            snapshot = load_watchlist_board(self.repository)
            _safe_call_from_thread(self, self._apply_watchlist_snapshot, snapshot)
        except Exception as exc:
            _safe_call_from_thread(self, self._show_watchlist_error, str(exc))

    def _apply_watchlist_snapshot(self, snapshot: WatchlistBoardSnapshot) -> None:
        cards = self.query_one("#watchlist_cards", ScrollableContainer)
        for child in list(cards.children):
            child.remove()
        if not snapshot.rows:
            cards.mount(Static("暂无自选股。使用 watchlist 命令添加 ETF 后会显示在这里。", classes="watchlist-status"))
            return
        for row in snapshot.rows:
            cards.mount(self._watchlist_card(row))
        if snapshot.error_count:
            cards.mount(
                Static(
                    f"{snapshot.error_count} 个 ETF 数据加载失败，其余卡片已正常显示。",
                    classes="watchlist-status warning-text",
                )
            )

    def _show_watchlist_error(self, error: str) -> None:
        cards = self.query_one("#watchlist_cards", ScrollableContainer)
        for child in list(cards.children):
            child.remove()
        cards.mount(Static(f"自选股看板加载失败：{error}", classes="watchlist-status error-text"))

    def _recent_etf_cards(self) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        seen: set[str] = set()
        try:
            for record in self.repository.list_reports():
                ticker = record.ticker.strip().upper()
                if ticker and ticker not in seen:
                    cards.append({
                        "ticker": ticker,
                        "name": _ETF_DISPLAY_NAMES.get(ticker, "ETF"),
                        "date": record.date,
                        "rating": record.rating or "未评级",
                    })
                    seen.add(ticker)
                if len(cards) >= 5:
                    break
        except Exception:
            pass
        for ticker in _RECENT_ETF_FALLBACKS:
            if ticker not in seen:
                cards.append({
                    "ticker": ticker,
                    "name": _ETF_DISPLAY_NAMES.get(ticker, "ETF"),
                    "date": "暂无分析",
                    "rating": "未评级",
                })
                seen.add(ticker)
            if len(cards) >= 5:
                break
        return cards[:5]

    def _watchlist_card(self, row: WatchlistBoardRow) -> Vertical:
        price_class = _a_share_value_class(row.pct_chg)
        share_class = _a_share_value_class(row.share_change_pct)
        rating = row.rating or "--"
        rating_date = row.rating_date or "--"
        return Vertical(
            Button(row.ticker, id=f"wl-{IdRegistry('wl').register(row.ticker)}", classes="watchlist-card-title"),
            Static(row.name, classes="watchlist-card-name"),
            Static(
                f"现价 {_fmt_price(row.close)}   涨跌 {_fmt_pct(row.pct_chg)}   份额 {_fmt_pct(row.share_change_pct)}",
                classes=f"watchlist-card-price {price_class} {share_class}",
            ),
            Static(
                f"{row.trend_label}    {row.cross_label}    支撑位 {_fmt_price(row.support)}    压力位 {_fmt_price(row.resistance)}",
                classes="watchlist-card-tags",
            ),
            Static(
                f"[{row.action}]  {row.signal_summary}    近期评级 {rating} / {rating_date}",
                classes=f"watchlist-card-action {_action_class(row.action)}",
            ),
            Static(row.error or row.rationale, classes="watchlist-card-rationale"),
            classes="watchlist-card",
        )

    def _read_tickers(self) -> list[str]:
        tickers: list[str] = list(self._selected_tickers)
        for ticker in self._parse_tickers(self.query_one("#ra_ticker_input", Input).value):
            if ticker not in tickers:
                tickers.append(ticker)
        return tickers

    def _parse_tickers(self, raw: str) -> list[str]:
        return [t.strip().upper() for t in re.split(r"[\s,]+", raw.strip()) if t.strip()]

    def _on_config_result(self, config: AnalysisConfig | None) -> None:
        if config is None:
            return
        self._analysis_config = config
        self.app.push_screen(
            AnalysisRunScreen(
                tickers=self._read_tickers(),
                config=config,
                runner=self.runner,
                repository=self.repository,
            )
        )

    def _build_runner(self) -> AnalysisRunner:
        cfg = self._analysis_config
        if cfg is None:
            return AnalysisRunner()
        return _build_analysis_runner(cfg)


# ---------------------------------------------------------------------------
# AnalysisRunScreen — compact tabs + execution dashboard
# ---------------------------------------------------------------------------

class AnalysisRunScreen(Screen):
    """Run ETF analysis with compact team tabs and a report dashboard.

    Left pane: ETF detail, compact metadata, queue.
    Right-top: team tabs (分析团队 | 研究 | 风险 | 决策).
    Right-bottom: structured execution summary and selected section report.
    """

    def __init__(
        self,
        tickers: list[str],
        config: AnalysisConfig,
        runner: AnalysisRunner | None = None,
        repository: ReportRepository | None = None,
    ):
        super().__init__()
        self.tickers = tickers
        self._analysis_config = config
        self.runner = runner
        self._active_runner: AnalysisRunner | None = None
        self.repository = repository or ReportRepository()
        self.ticker_ids = IdRegistry("rtk")
        self.section_contents: dict[tuple[str, str], str] = {}
        self.section_status: dict[tuple[str, str], bool] = {}
        # Board state: (ticker, section_id) -> "pending" | "running" | "done" | "failed"
        self._board_state: dict[tuple[str, str], str] = {}
        # Debate progress: (ticker, section_id) -> (current_round, max_rounds)
        self._debate_rounds: dict[tuple[str, str], tuple[int, int]] = {}
        self._active_column: str = ""
        self.current_ticker: str | None = None
        self.current_section: str | None = None
        self._analysis_thread: threading.Thread | None = None
        self.progress_lines: list[str] = []
        self._started_at: float | None = None
        self._last_stats: dict[str, Any] = {}
        self._backtest_signals: dict[str, dict[str, Any]] = {}
        self._etf_details: dict[str, dict[str, Any]] = {}
        self._ticker_run_state: dict[str, str] = {}
        self.section_picker_ids = IdRegistry("pick")
        self._picker_open_group: str | None = None

    def compose(self) -> ComposeResult:
        defs = self._section_definitions()
        yield Header(show_clock=False)
        with Vertical(classes="run-layout"):
            with Horizontal(classes="screen-body run-main"):
                with Vertical(classes="left-pane"):
                    yield Static("📊 基本信息", classes="pane-title")
                    with Vertical(id="ra_etf_card", classes="sidebar-card etf-card"):
                        yield Static("", id="ra_etf_name", classes="etf-name")
                        yield Static("", id="ra_etf_price", classes="etf-price-line")
                        yield Static("", id="ra_etf_metrics", classes="etf-metrics")
                        yield Static("", id="ra_etf_holdings", classes="etf-holdings")
                    yield Static("", id="ra_ai_summary", classes="hidden-widget")
                    yield Static("", id="ra_etf_detail", classes="hidden-widget")
                    yield Static("📋 分析元数据", classes="pane-title")
                    with Vertical(id="ra_config_card", classes="sidebar-card config-card"):
                        yield Static(self._config_summary(), id="ra_run_config")
                    yield Button("⏹ 取消分析", id="btn_ra_cancel", classes="cancel-btn warning-text", disabled=True)
                    yield Static("🧠 研究队列", classes="pane-title")
                    yield Static("状态: ⚪ 0/0 排期中", id="ra_queue_status", classes="queue-status")
                    yield ListView(id="ra_queue")
                with Vertical(classes="right-pane"):
                    # Team tabs (right-top)
                    with Horizontal(classes="right-top", id="ra_sections"):
                        yield Button("📊 分析团队 0/0 ▾", id="rtab-analysts", classes="section-tab")
                        yield Button("📖 研究 0/0 ▾", id="rtab-research", classes="section-tab")
                        yield Button("⚠️ 风险 0/0 ▾", id="rtab-risk", classes="section-tab")
                        yield Button("🎯 决策 0/0 ▾", id="rtab-decision", classes="section-tab")
                    with Vertical(id="ra_section_picker", classes="section-picker-popover hidden-widget"):
                        yield Static("", id="section_picker_title", classes="section-picker-title")
                        yield ListView(id="section_picker_list")
                    # Report body (right-bottom)
                    with Vertical(classes="right-bottom"):
                        yield Static("整体进度", id="ra_body_title", classes="pane-title")
                        with ScrollableContainer(id="ra_body_scroll"):
                            yield Markdown("准备开始分析。", id="ra_body")
            with Horizontal(classes="stats-bar"):
                yield Static(self._stats_progress_text(), id="stats_progress", classes="stats-seg-accent")
                yield Static(self._stats_resources_text(), id="stats_resources", classes="stats-seg-panel")
                yield Static(self._stats_reports_text(), id="stats_reports", classes="stats-seg-success")
                yield Static(self._stats_right_text(), id="stats_right", classes="stats-seg-surface")

    def on_mount(self) -> None:
        self._start_analysis()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn_ra_cancel":
            self._hide_section_picker()
            self._cancel_analysis()
        elif btn_id.startswith("rtab-"):
            self._open_section_picker(btn_id[5:])

    def on_click(self, event) -> None:
        if not self._picker_open_group:
            return
        widget = getattr(event, "widget", None)
        while widget is not None:
            widget_id = getattr(widget, "id", None)
            if widget_id in {"ra_section_picker", "ra_sections"}:
                return
            widget = getattr(widget, "parent", None)
        self._hide_section_picker()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id in self.section_picker_ids:
            self._on_section_picked(self.section_picker_ids.resolve(item_id))
            return
        if item_id in self.ticker_ids:
            self._hide_section_picker()
            self.current_ticker = self.ticker_ids.resolve(item_id)
            self._refresh_body()
            self._refresh_board()
            self._load_etf_detail(self.current_ticker)

    def _open_section_picker(self, group: str) -> None:
        ticker = self.current_ticker
        if not ticker:
            return
        if self._picker_open_group == group:
            self._hide_section_picker()
            return
        defs = list(self._section_group_defs().get(group, []))
        if not defs:
            return
        options = []
        for defn in defs:
            options.append((
                defn.section_id,
                defn.title,
                self._board_state.get((ticker, defn.section_id), "pending"),
            ))
            if group == "decision" and defn.section_id == "portfolio_manager":
                summary_state = "done" if ticker in self._backtest_signals else "pending"
                options.append(("execution_summary", "核心执行摘要", summary_state))
        title = {
            "analysts": "📊 分析团队",
            "research": "📖 研究",
            "risk": "⚠️ 风险",
            "decision": "🎯 决策",
        }.get(group, "选择章节")
        self.section_picker_ids.clear()
        picker = self.query_one("#section_picker_list", ListView)
        picker.clear()
        for section_id, label, state in options:
            if section_id == "execution_summary":
                icon = "⭐"
            else:
                icon = {"pending": "○", "running": "▒", "done": "✓", "failed": "✗"}.get(state, "○")
            picker.append(ListItem(Label(f"{icon} {label}"), id=self.section_picker_ids.register(section_id)))
        self.query_one("#section_picker_title", Static).update(title)
        popover = self.query_one("#ra_section_picker")
        popover.remove_class("hidden-widget")
        popover.remove_class("picker-analysts", "picker-research", "picker-risk", "picker-decision")
        popover.add_class(f"picker-{group}")
        self._picker_open_group = group
        if options:
            picker.index = 0
        picker.focus()

    def _hide_section_picker(self) -> None:
        self._picker_open_group = None
        self.section_picker_ids.clear()
        try:
            self.query_one("#section_picker_list", ListView).clear()
            self.query_one("#ra_section_picker").add_class("hidden-widget")
        except Exception:
            pass

    def _on_section_picked(self, section_id: str | None) -> None:
        if not section_id:
            return
        self.current_section = section_id
        self._set_active_column(section_id)
        self._hide_section_picker()
        self._refresh_board()
        self._refresh_body()

    # --- Analysis lifecycle ---

    def _start_analysis(self) -> None:
        if not self.tickers:
            return

        self.section_contents.clear()
        self.section_status.clear()
        self._board_state.clear()
        self._debate_rounds.clear()
        self._backtest_signals.clear()
        self._etf_details.clear()
        self._ticker_run_state = {ticker: "pending" for ticker in self.tickers}
        self._active_column = ""
        self.ticker_ids.clear()
        self.progress_lines.clear()
        self.current_ticker = self.tickers[0]
        self.current_section = None
        self._started_at = time.time()

        queue = self.query_one("#ra_queue", ListView)
        queue.clear()
        for ticker in self.tickers:
            ticker_id = self.ticker_ids.register(ticker)
            queue.append(ListItem(Label(self._queue_item_label(ticker)), id=ticker_id))

        runner = self.runner or self._build_runner()
        self._active_runner = runner
        self.query_one("#btn_ra_cancel", Button).disabled = False
        self._append_progress(f"开始分析 {', '.join(self.tickers)}")
        self._refresh_board()
        self._refresh_queue_panel()
        self._refresh_stats_bar()
        self._analysis_thread = threading.Thread(
            target=self._run_analysis,
            args=(runner, self.tickers),
            daemon=True,
            name="etfagents-tui-analysis",
        )
        self._analysis_thread.start()

    def _build_runner(self) -> AnalysisRunner:
        return _build_analysis_runner(self._analysis_config)

    def _config_summary(self) -> str:
        cfg = self._analysis_config
        depth_req = RESEARCH_DEPTH_REQUIREMENTS.get(cfg.depth_name, {})
        debate_rounds = depth_req.get("debate_rounds", "?")
        risk_rounds = depth_req.get("risk_rounds", "?")
        provider = cfg.llm_provider or "default"
        if len(provider) > 16:
            provider = f"{provider[:15]}…"
        return (
            f"日期: {cfg.analysis_date or 'today'}\n"
            f"提供商: {provider}\n"
            f"深度: {cfg.depth_name} {debate_rounds}×{risk_rounds}"
        )

    def _cancel_analysis(self) -> None:
        if self._active_runner:
            self._active_runner.request_cancel()
        self.query_one("#btn_ra_cancel", Button).disabled = True

    def _load_etf_detail(self, ticker: str) -> None:
        try:
            self.query_one("#ra_etf_name", Static).update(ticker)
            self.query_one("#ra_etf_price", Static).update("加载中...")
            self.query_one("#ra_etf_metrics", Static).update("")
            self.query_one("#ra_etf_holdings", Static).update("")
        except Exception:
            pass

        analysis_date = self._analysis_config.analysis_date if self._analysis_config else None

        def _worker() -> None:
            try:
                from etfagents.detail import get_etf_detail
                detail = get_etf_detail(ticker, curr_date=analysis_date)
            except Exception as exc:
                detail = {"ticker": ticker, "_error": f"{type(exc).__name__}: {exc}"}
            _safe_call_from_thread(self, self._update_etf_card, detail)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_etf_card(self, detail: dict) -> None:
        """Populate the structured ETF card widgets from a detail dict."""
        error = detail.get("_error")
        if error:
            try:
                self.query_one("#ra_etf_price", Static).update(f"详情不可用: {error}")
            except Exception:
                pass
            return
        ticker = detail.get("ticker")
        if ticker:
            self._etf_details[str(ticker)] = dict(detail)
        try:
            components = _format_detail_rich(detail)
            self.query_one("#ra_etf_name", Static).update(components["name_text"])
            self.query_one("#ra_etf_price", Static).update(components["price_text"])
            self.query_one("#ra_etf_metrics", Static).update(components["metrics_text"])
            self.query_one("#ra_etf_holdings", Static).update(components["holdings_bars"])
            if self.current_section == "execution_summary":
                self._refresh_body()
        except Exception:
            pass
        # Also update hidden legacy widget
        try:
            self.query_one("#ra_etf_detail", Static).update(_format_detail_text(detail))
        except Exception:
            pass

    def _update_etf_detail(self, text: str) -> None:
        try:
            self.query_one("#ra_etf_detail", Static).update(text)
        except Exception:
            pass

    def on_unmount(self) -> None:
        if self._active_runner:
            self._active_runner.request_cancel()

    def _run_analysis(self, runner: AnalysisRunner, tickers: list[str]) -> None:
        """Worker thread: stream analysis events."""
        cfg = self._analysis_config
        selected = cfg.selected_analysts if cfg else None
        analysis_date = cfg.analysis_date if cfg else None
        try:
            for event in runner.run_queue(
                tickers,
                analysis_date=analysis_date,
                selected_analysts=selected,
            ):
                _safe_call_from_thread(self, self._apply_event, event)
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))
        finally:
            _safe_call_from_thread(self, self._on_analysis_done)

    def _on_analysis_done(self) -> None:
        self._last_stats = self._read_runner_stats()
        self._active_runner = None
        self._append_progress("分析线程已结束。")
        self._refresh_stats_bar()
        try:
            self.query_one("#btn_ra_cancel", Button).disabled = True
        except Exception:
            pass

    # --- Event dispatch ---

    def _apply_event(self, event: AnalysisEvent) -> None:
        """UI thread: handle event."""
        if isinstance(event, TickerStarted):
            self._handle_ticker_started(event)
        elif isinstance(event, SectionDone):
            self._handle_section_done(event)
        elif isinstance(event, DebateProgress):
            self._handle_debate_progress(event)
        elif isinstance(event, TickerDone):
            self._handle_ticker_done(event)
        elif isinstance(event, TickerFailed):
            self._handle_ticker_failed(event)
        elif isinstance(event, TickerCancelled):
            self._handle_ticker_cancelled(event)
        self._refresh_stats_bar()

    def _queue_item_label(self, ticker: str, suffix: str = "") -> str:
        status_label = {
            "pending": "排期中",
            "running": "分析中",
            "done": "已完成",
            "failed": "失败",
            "cancelled": "已取消",
        }.get(self._ticker_run_state.get(ticker, "pending"), "排期中")
        index = self.tickers.index(ticker) + 1 if ticker in self.tickers else len(self.tickers) + 1
        short_ticker = ticker.split(".", 1)[0]
        return f"> {index}. {short_ticker} ({status_label}{suffix})"

    def _sync_queue_item(self, ticker: str, suffix: str = "") -> None:
        ticker_id = self.ticker_ids.register(ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
        except Exception:
            try:
                self.query_one("#ra_queue", ListView).append(
                    ListItem(Label(self._queue_item_label(ticker, suffix)), id=ticker_id)
                )
            except Exception:
                pass
            return
        try:
            item.query_one(Label).update(self._queue_item_label(ticker, suffix))
        except Exception:
            pass

    def _refresh_queue_panel(self) -> None:
        ticker = self.current_ticker
        queue_defs = self._section_group_defs()["analysts"]
        total = len(queue_defs)
        completed = 0
        if ticker:
            completed = sum(
                1 for defn in queue_defs
                if self._board_state.get((ticker, defn.section_id)) == "done"
            )
        if any(state == "running" for state in self._ticker_run_state.values()):
            state_icon, state_text = "🟢", "运行中"
        elif any(state == "failed" for state in self._ticker_run_state.values()):
            state_icon, state_text = "🔴", "有失败"
        elif self._ticker_run_state and all(state == "done" for state in self._ticker_run_state.values()):
            state_icon, state_text = "✅", "已完成"
        else:
            state_icon, state_text = "⚪", "排期中"
        try:
            self.query_one("#ra_queue_status", Static).update(
                f"状态: {state_icon} {completed}/{total} {state_text}"
            )
        except Exception:
            pass

    def _handle_ticker_started(self, event: TickerStarted) -> None:
        self._ticker_run_state[event.ticker] = "running"
        self._sync_queue_item(event.ticker)
        self._append_progress(f"{event.ticker}: 开始运行，共 {event.total_sections} 个团队章节")
        if self.current_ticker is None:
            self.current_ticker = event.ticker
        if self.current_ticker == event.ticker:
            self._load_etf_detail(event.ticker)
        self._refresh_queue_panel()

    def _handle_section_done(self, event: SectionDone) -> None:
        self.section_contents[(event.ticker, event.section_id)] = event.content
        self.section_status[(event.ticker, event.section_id)] = True
        if event.backtest_signal:
            self._backtest_signals[event.ticker] = dict(event.backtest_signal)

        # Update board state
        if event.section_id in _INSTANT_DONE_SECTIONS:
            self._board_state[(event.ticker, event.section_id)] = "done"
        else:
            cur = self._board_state.get((event.ticker, event.section_id))
            if cur != "done":
                self._board_state[(event.ticker, event.section_id)] = "running"

        title = SECTION_BY_ID.get(event.section_id).title if event.section_id in SECTION_BY_ID else event.section_id
        self._append_progress(f"{event.ticker}: {title} 已更新 ({event.completed}/{event.total})")
        self._set_active_column(event.section_id)
        self._refresh_board()
        self._refresh_queue_panel()
        self._refresh_body()

    def _handle_debate_progress(self, event: DebateProgress) -> None:
        self._debate_rounds[(event.ticker, event.section_id)] = (
            event.current_round,
            event.max_rounds,
        )

        # Update debate board state
        if event.section_id in ("research_debate", "risk_debate"):
            key = (event.ticker, event.section_id)
            if event.current_round >= event.max_rounds:
                self._board_state[key] = "done"
            elif event.current_round > 0:
                self._board_state[key] = "running"

        self._refresh_board()
        self._refresh_queue_panel()

    def _handle_ticker_done(self, event: TickerDone) -> None:
        rating_str = f" {event.rating}" if event.rating else ""
        self._ticker_run_state[event.ticker] = "done"
        self._sync_queue_item(event.ticker, suffix=rating_str)

        # Mark all sections as done for this ticker
        for defn in self._section_definitions():
            self._board_state[(event.ticker, defn.section_id)] = "done"

        self.repository.invalidate()
        self._append_progress(f"{event.ticker}: 分析完成{rating_str}")
        self._refresh_board()
        self._refresh_queue_panel()

        # Show AI summary from portfolio manager content
        pm_content = self.section_contents.get((event.ticker, "portfolio_manager"), "")
        summary = _extract_ai_summary(pm_content)
        if summary and self.current_ticker == event.ticker:
            try:
                self.query_one("#ra_ai_summary", Static).update(f"💡 {summary}")
            except Exception:
                pass

    def _handle_ticker_failed(self, event: TickerFailed) -> None:
        self._ticker_run_state[event.ticker] = "failed"
        self._sync_queue_item(event.ticker)

        # Mark all unfinished sections as failed
        for defn in self._section_definitions():
            key = (event.ticker, defn.section_id)
            if self._board_state.get(key, "pending") != "done":
                self._board_state[key] = "failed"

        self._append_progress(f"{event.ticker}: 分析失败 - {event.error}")
        self._refresh_board()
        self._refresh_queue_panel()

        # Show error modal with traceback
        self.app.push_screen(ErrorDetailModal(
            ticker=event.ticker,
            error=event.error,
            traceback_text=event.traceback,
        ))

    def _handle_ticker_cancelled(self, event: TickerCancelled) -> None:
        self._ticker_run_state[event.ticker] = "cancelled"
        self._sync_queue_item(event.ticker)
        self._append_progress(f"{event.ticker}: 已取消")
        self._refresh_queue_panel()

    # --- Board refresh ---

    def _set_active_column(self, section_id: str) -> None:
        if section_id in ANALYST_KEYS:
            self._active_column = "rtab-analysts"
        elif section_id in ("research_debate", "research"):
            self._active_column = "rtab-research"
        elif section_id in ("trader", "risk_debate"):
            self._active_column = "rtab-risk"
        elif section_id in ("portfolio_manager", "execution_summary"):
            self._active_column = "rtab-decision"

    def _refresh_board(self) -> None:
        """Update board item labels, column headers, progress bars, and active column."""
        ticker = self.current_ticker
        if not ticker:
            return

        groups = self._section_group_defs()

        def _done_count(section_ids: list[str]) -> int:
            return sum(
                1 for sid in section_ids
                if self._board_state.get((ticker, sid)) == "done"
            )

        tab_defs = [
            ("rtab-analysts", "📊 分析团队", groups["analysts"]),
            ("rtab-research", "📖 研究", groups["research"]),
            ("rtab-risk", "⚠️ 风险", groups["risk"]),
            ("rtab-decision", "🎯 决策", groups["decision"]),
        ]
        for tab_id, label, group_defs in tab_defs:
            ids = [d.section_id for d in group_defs]
            try:
                tab = self.query_one(f"#{tab_id}", Button)
                tab.label = f"{label} {_done_count(ids)}/{len(ids)} ▾"
                tab.remove_class("section-tab-active")
                if tab_id == self._active_column:
                    tab.add_class("section-tab-active")
            except Exception:
                pass

    # --- Body refresh ---

    def _refresh_body(self) -> None:
        if not self.current_ticker:
            self.query_one("#ra_body", Markdown).update("请选择一个 ticker。")
            return
        if self.current_section is None:
            self.query_one("#ra_body_title", Static).update("整体进度")
            self.query_one("#ra_body", Markdown).update(self._progress_markdown())
            return

        if self.current_section == "execution_summary":
            self.query_one("#ra_body_title", Static).update("核心执行摘要")
            summary_md = _format_execution_summary(
                self._backtest_signals.get(self.current_ticker),
                self._etf_details.get(self.current_ticker),
            )
            self.query_one("#ra_body", Markdown).update(summary_md)
            return

        # risk_debate — show actual risk debate content
        if self.current_section == "risk_debate":
            self.query_one("#ra_body_title", Static).update("风险辩论")
            content = self.section_contents.get((self.current_ticker, "risk_debate"))
            if content:
                self.query_one("#ra_body", Markdown).update(_highlight_report_numbers(content))
            else:
                rounds = self._debate_rounds.get((self.current_ticker, "risk_debate"))
                if rounds:
                    self.query_one("#ra_body", Markdown).update(
                        f"风险辩论进行中 {_debate_progress_bar(rounds[0], rounds[1])}"
                    )
                else:
                    self.query_one("#ra_body", Markdown).update("风险辩论尚未开始。")
            return

        content = self.section_contents.get((self.current_ticker, self.current_section))
        title = SECTION_BY_ID.get(self.current_section).title if self.current_section in SECTION_BY_ID else self.current_section

        # Strip feedback snapshot from portfolio manager display
        if self.current_section == "portfolio_manager" and content:
            try:
                from etfagents.agents.utils.agent_utils import strip_feedback_snapshot
                content = strip_feedback_snapshot(content)
            except ImportError:
                pass

        self.query_one("#ra_body_title", Static).update(str(title))
        if content:
            self.query_one("#ra_body", Markdown).update(_highlight_report_numbers(content))
        else:
            self.query_one("#ra_body", Markdown).update("该团队尚未产出报告，分析仍在进行或尚未开始。")

    def _show_error(self, error: str) -> None:
        self._append_progress(f"分析出错：{error}")

    def _append_progress(self, message: str) -> None:
        self.progress_lines.append(message)
        if self.current_section is None:
            try:
                self._refresh_body()
            except Exception:
                pass

    def _progress_markdown(self) -> str:
        return "\n".join(f"- {line}" for line in self.progress_lines) or "等待分析事件。"

    # --- Stats bar ---

    def _refresh_stats_bar(self) -> None:
        try:
            self.query_one("#stats_progress", Static).update(self._stats_progress_text())
            self.query_one("#stats_resources", Static).update(self._stats_resources_text())
            self.query_one("#stats_reports", Static).update(self._stats_reports_text())
            self.query_one("#stats_right", Static).update(self._stats_right_text())
        except Exception:
            pass

    def _stats_progress_text(self) -> str:
        stats = self._read_runner_stats()
        agents_total = len(self._section_definitions()) * len(self.tickers)
        agents_done = sum(1 for done in self.section_status.values() if done)
        current_agent = self._current_agent_label()
        return f" ◉ Agents {agents_done}/{agents_total} · {current_agent}"

    def _stats_resources_text(self) -> str:
        stats = self._read_runner_stats()
        tokens_in = int(stats.get("tokens_in", 0) or 0)
        tokens_out = int(stats.get("tokens_out", 0) or 0)
        token_text = (
            f"{_format_tokens(tokens_in)}↑{_format_tokens(tokens_out)}↓"
            if tokens_in or tokens_out else "--"
        )
        return f"LLM {int(stats.get('llm_calls', 0) or 0)} · Tools {int(stats.get('tool_calls', 0) or 0)} · {token_text}"

    def _stats_reports_text(self) -> str:
        agents_total = len(self._section_definitions()) * len(self.tickers)
        agents_done = sum(1 for done in self.section_status.values() if done)
        return f"Reports {agents_done}/{agents_total}"

    def _stats_right_text(self) -> str:
        elapsed = self._elapsed_text()
        return f"{elapsed}  ?帮助  s设置  q退出"

    def _read_runner_stats(self) -> dict[str, Any]:
        runner = self._active_runner or self.runner
        if runner and hasattr(runner, "get_stats"):
            self._last_stats = runner.get_stats()
        return self._last_stats

    def _current_agent_label(self) -> str:
        if self.current_ticker and self.current_section:
            section = SECTION_BY_ID.get(self.current_section)
            if section:
                return section.title
        if self.current_ticker:
            latest = None
            for ticker, section_id in self.section_status:
                if ticker == self.current_ticker:
                    latest = section_id
            if latest:
                section = SECTION_BY_ID.get(latest)
                if section:
                    return section.title
        return "等待"

    def _section_definitions(self) -> tuple[SectionDef, ...]:
        return section_definitions_for(self._analysis_config.selected_analysts)

    def _section_group_defs(self) -> dict[str, list[SectionDef]]:
        defs = list(self._section_definitions())
        return {
            "analysts": [d for d in defs if d.team == "分析师"],
            "research": [d for d in defs if d.team == "研究"],
            "risk": [d for d in defs if d.section_id in {"trader", "risk_debate"}],
            "decision": [d for d in defs if d.team == "决策"],
        }

    def _elapsed_text(self) -> str:
        if self._started_at is None:
            return "00:00"
        elapsed = max(0, int(time.time() - self._started_at))
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"
