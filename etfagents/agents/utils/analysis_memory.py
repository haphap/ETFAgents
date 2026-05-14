from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import re
import hashlib
from typing import Any, Mapping, Sequence

from etfagents.agents.utils.agent_utils import get_output_language
from etfagents.agents.utils.state_keys import get_asset_symbol, get_state_value
from etfagents.backtest.cache import BacktestSignalStore
from etfagents.backtest.signals import build_state_backtest_signal
from etfagents.dataflows.config import get_backtest_context


def _safe_path_token(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in (value or "").strip())


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_after_days(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=int(days))).isoformat()


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value).strip()[:10])


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _truncate(text: str, limit: int) -> str:
    compact = _collapse_whitespace(text)
    if limit <= 0 or len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _clean_lines(text: str) -> list[str]:
    cleaned: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        lowered = line.lower()
        if lowered.startswith(("feedback snapshot", "decision summary", "决策摘要", "反馈快照")):
            continue
        line = re.sub(r"^[\-\*\d\.\)\(（）、\s]+", "", line).strip()
        if line:
            cleaned.append(line)
    return cleaned


def _summarize_text(text: str, limit: int = 400) -> str:
    return _truncate(" ".join(_clean_lines(text)), limit)


def _coerce_str_list(values: Any, *, max_items: int = 4, item_limit: int = 180) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    items: list[str] = []
    for value in values:
        text = _truncate(str(value).strip(), item_limit)
        if text:
            items.append(text)
        if len(items) >= max_items:
            break
    return items


def _format_rule(rule: Mapping[str, Any]) -> str:
    metric = str(rule.get("metric", "")).strip()
    op = str(rule.get("op", "")).strip()
    threshold = rule.get("threshold")
    action = str(rule.get("action", "")).strip()
    pieces = [piece for piece in (metric, op, str(threshold), f"-> {action}" if action else "") if piece]
    if rule.get("target_weight_pct") is not None:
        pieces.append(f"target {rule['target_weight_pct']}%")
    elif rule.get("delta_pct") is not None:
        pieces.append(f"delta {rule['delta_pct']}%")
    note = _truncate(str(rule.get("note", "")).strip(), 80)
    if note:
        pieces.append(note)
    return " | ".join(pieces)


def _signal_rule_list(signal: Mapping[str, Any], key: str, *, max_items: int = 3) -> list[str]:
    raw_rules = signal.get(key)
    if not isinstance(raw_rules, Sequence) or isinstance(raw_rules, (str, bytes)):
        return []
    rendered: list[str] = []
    for rule in raw_rules:
        if isinstance(rule, Mapping):
            text = _format_rule(rule)
        else:
            text = _truncate(str(rule).strip(), 160)
        if text:
            rendered.append(text)
        if len(rendered) >= max_items:
            break
    return rendered


def _derive_watch_items(signal: Mapping[str, Any]) -> list[str]:
    items = _coerce_str_list(signal.get("monitoring_points"), max_items=3)
    if items:
        return items
    items = _coerce_str_list(signal.get("rebalance_conditions"), max_items=3)
    if items:
        return items
    return _signal_rule_list(signal, "rebalance_triggers", max_items=3)


def _derive_invalidation_signals(signal: Mapping[str, Any]) -> list[str]:
    for key in ("exit_conditions", "risk_controls"):
        items = _coerce_str_list(signal.get(key), max_items=3)
        if items:
            return items
    for key in ("exit_triggers", "risk_rules"):
        items = _signal_rule_list(signal, key, max_items=3)
        if items:
            return items
    return []


def _signal_target_summary(signal: Mapping[str, Any]) -> str:
    rating = str(signal.get("rating", "")).strip()
    pieces = [rating] if rating else []
    if signal.get("target_weight_pct") is not None:
        pieces.append(f"target {signal['target_weight_pct']}%")
    elif signal.get("target_weight_min_pct") is not None or signal.get("target_weight_max_pct") is not None:
        pieces.append(
            f"target {signal.get('target_weight_min_pct', '?')}%-{signal.get('target_weight_max_pct', '?')}%"
        )
    delay = str(signal.get("execution_delay", "")).strip()
    if delay:
        pieces.append(delay)
    return ", ".join(piece for piece in pieces if piece)


def _strip_explicit_recommendation(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"(?im)^.*(?:final transaction proposal|final allocation proposal|最终交易建议|最终配置建议).*$", "", cleaned)
    cleaned = re.sub(r"\*\*(?:BUY|OVERWEIGHT|HOLD|UNDERWEIGHT|SELL|买入|增持|持有|减持|卖出)\*\*", "", cleaned, flags=re.IGNORECASE)
    return _collapse_whitespace(cleaned)


def _is_chinese_output() -> bool:
    return get_output_language().strip().lower() in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}


_DEFAULT_ROLE_BRIEF_SPECS: dict[str, list[str]] = {
    "analyst": ["summary", "key_drivers", "watch_items", "invalidation_signals"],
    "trader": ["trader_summary", "stance", "trigger_summary", "invalidation_signals"],
    "research_manager": ["summary", "stance", "research_summary", "watch_items", "invalidation_signals"],
    "portfolio_manager": ["summary", "stance", "portfolio_summary", "watch_items", "invalidation_signals"],
}


@dataclass
class AnalysisMemoryEntry:
    id: str
    ticker: str
    trade_date: str
    run_id: str
    created_at: str
    config_hash: str
    signal: dict[str, Any]
    thesis_summary: str
    bull_case_summary: str = ""
    bear_case_summary: str = ""
    key_drivers: list[str] = field(default_factory=list)
    key_risks: list[str] = field(default_factory=list)
    watch_items: list[str] = field(default_factory=list)
    invalidation_signals: list[str] = field(default_factory=list)
    research_summary: str = ""
    trader_summary: str = ""
    portfolio_summary: str = ""
    outcome_status: str = "pending"
    outcome_lesson_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AnalysisMemoryEntry:
        return cls(**dict(payload))


@dataclass
class OutcomeLessonEntry:
    id: str
    ticker: str
    trade_date: str
    created_at: str
    source_analysis_id: str
    raw_return: float
    alpha_return: float
    holding_days: int
    outcome_status: str
    lesson_summary: str
    reflection: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> OutcomeLessonEntry:
        return cls(**dict(payload))


@dataclass
class MethodPlaybookEntry:
    id: str
    role: str
    ticker: str | None
    created_at: str
    source_lesson_id: str
    rule: str
    rationale: str = ""
    status: str = "draft"
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MethodPlaybookEntry:
        return cls(**dict(payload))


@dataclass
class MemoryContextBundle:
    continuity_context: dict[str, str] = field(default_factory=dict)
    lesson_context: dict[str, str] = field(default_factory=dict)
    method_context: dict[str, str] = field(default_factory=dict)
    past_context: str = ""


class AnalysisMemoryStore:
    def __init__(self, config: Mapping[str, Any], selected_analysts: Sequence[str]):
        self.config = dict(config)
        self.selected_analysts = list(selected_analysts)
        self.root_dir = Path(self.config["results_dir"]).expanduser() / "memory"

    def is_enabled(self) -> bool:
        memory_mode = str(self.config.get("memory_mode", "full")).strip().lower()
        if memory_mode == "disabled":
            return False
        backtest = get_backtest_context()
        if backtest.mode == "backtest" and not bool(self.config.get("memory_in_backtest")):
            return False
        return True

    def config_hash(self) -> str:
        return BacktestSignalStore(self.config, self.selected_analysts)._config_hash()

    def append_analysis(self, entry: AnalysisMemoryEntry) -> None:
        if not self.is_enabled():
            return
        self._upsert_entry(self._analysis_path(entry.ticker), entry)

    def append_outcome(self, entry: OutcomeLessonEntry) -> None:
        if not self.is_enabled():
            return
        self._upsert_entry(self._outcome_path(entry.ticker), entry)

    def append_playbook(self, entry: MethodPlaybookEntry) -> None:
        if not self.is_enabled():
            return
        self._upsert_entry(self._playbook_path(entry.role, entry.ticker), entry)

    def load_playbook_entries(self, role: str | None = None, ticker: str | None = None) -> list[MethodPlaybookEntry]:
        if role is not None:
            paths = [self._playbook_path(role, ticker)]
        else:
            playbook_dir = self.root_dir / "playbook"
            paths = sorted(playbook_dir.glob("*.ndjson")) if playbook_dir.exists() else []
        entries: dict[str, MethodPlaybookEntry] = {}
        for path in paths:
            for entry in self._load_entries(path, MethodPlaybookEntry):
                entries[entry.id] = entry
        return list(entries.values())

    def promote_playbook(
        self,
        entry_id: str,
        *,
        expires_days: int | None = None,
        max_active: int | None = None,
    ) -> MethodPlaybookEntry:
        path, entry = self._find_playbook_entry(entry_id)
        if entry is None or path is None:
            raise KeyError(entry_id)

        promoted_at = _utc_now_iso()
        expiry = _date_after_days(expires_days or int(self.config.get("playbook_active_days", 90) or 90))
        promoted = replace(
            entry,
            created_at=promoted_at,
            status="active",
            expires_at=expiry,
        )
        self._upsert_entry(path, promoted)
        self._enforce_active_limit(path, max_active=max_active)
        return promoted

    def memory_signature(self, ticker: str, trade_date: str) -> str:
        if not self.is_enabled():
            return ""
        memory_mode = str(self.config.get("memory_mode", "full")).strip().lower()
        roles = list(dict.fromkeys([*self.selected_analysts, "research_manager", "trader", "portfolio_manager"]))
        parts: list[str] = [f"mode:{memory_mode}"]
        latest = self.get_latest_before(ticker, trade_date)
        if latest is not None:
            parts.append(f"analysis:{latest.id}")
        if memory_mode != "continuity-only":
            parts.extend(f"lesson:{entry.id}" for entry in self.get_recent_lessons(ticker, trade_date))
        if memory_mode == "full":
            playbook_ids: set[str] = set()
            for role in roles:
                playbook_ids.update(
                    entry.id
                    for entry in self.get_active_playbook_entries(role, ticker, trade_date)
                )
            parts.extend(f"playbook:{entry_id}" for entry_id in sorted(playbook_ids))
        encoded = json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def get_latest_before(self, ticker: str, trade_date: str) -> AnalysisMemoryEntry | None:
        entries = self._filtered_analyses(ticker, trade_date)
        return entries[-1] if entries else None

    def get_pending_analyses(self, ticker: str, trade_date: str) -> list[AnalysisMemoryEntry]:
        cutoff = self._effective_cutoff_date(trade_date)
        if cutoff is None:
            return []
        return [
            entry
            for entry in self.load_analysis_entries(ticker)
            if entry.outcome_status == "pending"
            and _parse_iso_date(entry.trade_date) is not None
            and _parse_iso_date(entry.trade_date) <= cutoff
        ]

    def get_recent_lessons(self, ticker: str, trade_date: str, *, limit: int = 3) -> list[OutcomeLessonEntry]:
        cutoff = self._effective_cutoff_date(trade_date)
        if cutoff is None:
            return []
        eligible = [
            entry
            for entry in self.load_outcome_entries(ticker)
            if _parse_iso_date(entry.trade_date) is not None
            and _parse_iso_date(entry.trade_date) <= cutoff
            and _parse_iso_date(entry.created_at) is not None
            and _parse_iso_date(entry.created_at) <= cutoff
        ]
        eligible.sort(key=lambda entry: (entry.trade_date, entry.created_at))
        return eligible[-limit:]

    def get_active_playbook_entries(
        self,
        role: str,
        ticker: str,
        trade_date: str,
        *,
        limit: int = 4,
    ) -> list[MethodPlaybookEntry]:
        cutoff = self._effective_cutoff_date(trade_date)
        if cutoff is None:
            return []
        candidates: dict[str, MethodPlaybookEntry] = {}
        for path in self._playbook_query_paths(role, ticker):
            for entry in self._load_entries(path, MethodPlaybookEntry):
                if not self._is_active_playbook(entry, cutoff):
                    continue
                candidates[entry.id] = entry
        ordered = sorted(candidates.values(), key=lambda entry: entry.created_at)
        return ordered[-limit:]

    def load_analysis_entries(self, ticker: str) -> list[AnalysisMemoryEntry]:
        return self._load_entries(self._analysis_path(ticker), AnalysisMemoryEntry)

    def load_outcome_entries(self, ticker: str) -> list[OutcomeLessonEntry]:
        return self._load_entries(self._outcome_path(ticker), OutcomeLessonEntry)

    def _filtered_analyses(self, ticker: str, trade_date: str) -> list[AnalysisMemoryEntry]:
        cutoff = self._effective_cutoff_date(trade_date)
        if cutoff is None:
            return []
        max_age_days = int(self.config.get("continuity_max_age_days", 30) or 30)
        entries = []
        for entry in self.load_analysis_entries(ticker):
            entry_date = _parse_iso_date(entry.trade_date)
            if entry_date is None or entry_date > cutoff:
                continue
            if max_age_days and (cutoff - entry_date).days > max_age_days:
                continue
            entries.append(entry)
        entries.sort(key=lambda entry: (entry.trade_date, entry.created_at))
        return entries

    def _effective_cutoff_date(self, trade_date: str) -> date | None:
        target_date = _parse_iso_date(trade_date)
        if target_date is None:
            return None
        backtest = get_backtest_context()
        as_of_date = _parse_iso_date(backtest.as_of_date)
        if backtest.mode == "backtest" and as_of_date is not None:
            return min(target_date, as_of_date)
        return target_date

    def _analysis_path(self, ticker: str) -> Path:
        return self.root_dir / _safe_path_token(ticker) / "analyses.ndjson"

    def _outcome_path(self, ticker: str) -> Path:
        return self.root_dir / _safe_path_token(ticker) / "outcomes.ndjson"

    def _playbook_path(self, role: str, ticker: str | None) -> Path:
        safe_role = _safe_path_token(role or "all")
        name = safe_role if not ticker else f"{safe_role}__{_safe_path_token(ticker)}"
        return self.root_dir / "playbook" / f"{name}.ndjson"

    def _playbook_query_paths(self, role: str, ticker: str) -> list[Path]:
        return [
            self._playbook_path("all", None),
            self._playbook_path(role, None),
            self._playbook_path("all", ticker),
            self._playbook_path(role, ticker),
        ]

    def _find_playbook_entry(self, entry_id: str) -> tuple[Path | None, MethodPlaybookEntry | None]:
        playbook_dir = self.root_dir / "playbook"
        if not playbook_dir.exists():
            return None, None
        for path in sorted(playbook_dir.glob("*.ndjson")):
            entries = self._load_entries(path, MethodPlaybookEntry)
            for entry in entries:
                if entry.id == entry_id:
                    return path, entry
        return None, None

    def _enforce_active_limit(self, path: Path, *, max_active: int | None = None) -> None:
        limit = int(max_active or self.config.get("playbook_max_active_per_scope", 20) or 20)
        if limit <= 0:
            return
        today = datetime.now(UTC).date()
        entries = self._load_entries(path, MethodPlaybookEntry)
        active = [
            entry
            for entry in entries
            if self._is_active_playbook(entry, today)
        ]
        active.sort(key=lambda entry: entry.created_at)
        stale = active[:-limit]
        for entry in stale:
            deprecated = replace(
                entry,
                created_at=_utc_now_iso(),
                status="deprecated",
            )
            self._upsert_entry(path, deprecated)

    @staticmethod
    def _is_active_playbook(entry: MethodPlaybookEntry, cutoff: date) -> bool:
        if entry.status != "active":
            return False
        created_date = _parse_iso_date(entry.created_at)
        if created_date is not None and created_date > cutoff:
            return False
        expires_date = _parse_iso_date(entry.expires_at)
        if expires_date is not None and expires_date <= cutoff:
            return False
        return True

    @staticmethod
    def _append_ndjson(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(payload), ensure_ascii=False) + "\n")

    @staticmethod
    def _load_entries(path: Path, entry_type):
        if not path.exists():
            return []
        items: dict[str, Any] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                payload = json.loads(raw)
                entry = entry_type.from_dict(payload)
                items[getattr(entry, "id")] = entry
        return list(items.values())

    @staticmethod
    def _write_entries(path: Path, entries: Sequence[Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(entries, key=lambda entry: (getattr(entry, "created_at", ""), getattr(entry, "id", "")))
        with path.open("w", encoding="utf-8") as handle:
            for entry in ordered:
                payload = entry.to_dict() if hasattr(entry, "to_dict") else dict(entry)
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _upsert_entry(self, path: Path, entry: Any) -> None:
        entries = self._load_entries(path, type(entry))
        items = {getattr(existing, "id"): existing for existing in entries}
        items[getattr(entry, "id")] = entry
        self._write_entries(path, list(items.values()))


class MemoryContextBuilder:
    def __init__(self, store: AnalysisMemoryStore, config: Mapping[str, Any], selected_analysts: Sequence[str]):
        self.store = store
        self.config = dict(config)
        self.selected_analysts = list(selected_analysts)

    def build(self, ticker: str, trade_date: str) -> MemoryContextBundle:
        roles = list(dict.fromkeys([*self.selected_analysts, "research_manager", "trader", "portfolio_manager"]))
        if not self.store.is_enabled():
            return MemoryContextBundle(
                continuity_context={role: "" for role in roles},
                lesson_context={role: "" for role in roles},
                method_context={role: "" for role in roles},
                past_context="",
            )

        memory_mode = str(self.config.get("memory_mode", "full")).strip().lower()
        latest = self.store.get_latest_before(ticker, trade_date)
        lessons = [] if memory_mode == "continuity-only" else self.store.get_recent_lessons(ticker, trade_date)

        continuity = {
            role: self._render_continuity(role, latest)
            for role in roles
        }
        lesson = {
            role: self._render_lessons(lessons)
            for role in roles
        }
        if memory_mode in {"continuity-only", "lesson"}:
            method = {role: "" for role in roles}
        else:
            method = {
                role: self._render_method_rules(
                    self.store.get_active_playbook_entries(role, ticker, trade_date)
                )
                for role in roles
            }

        return MemoryContextBundle(
            continuity_context=continuity,
            lesson_context=lesson,
            method_context=method,
            past_context=self._render_legacy_past_context(lessons),
        )

    def _render_continuity(self, role: str, entry: AnalysisMemoryEntry | None) -> str:
        if entry is None:
            return ""
        signal = entry.signal or {}
        target_summary = _signal_target_summary(signal)
        limit = int(self.config.get("continuity_brief_char_limit", 2000) or 2000)
        continuity_fields = self._continuity_field_map(entry, signal, target_summary)
        parts = [
            continuity_fields[field]
            for field in self._role_brief_spec(role)
            if continuity_fields.get(field)
        ]
        return _truncate("\n".join(parts), limit)

    def _render_lessons(self, lessons: Sequence[OutcomeLessonEntry]) -> str:
        if not lessons:
            return ""
        limit = int(self.config.get("lesson_brief_char_limit", 1500) or 1500)
        rendered = [
            f"[{entry.trade_date} | {entry.outcome_status} | raw {entry.raw_return:+.1%} | alpha {entry.alpha_return:+.1%}] {entry.lesson_summary}"
            for entry in lessons
        ]
        return _truncate("\n".join(rendered), limit)

    def _render_method_rules(self, entries: Sequence[MethodPlaybookEntry]) -> str:
        if not entries:
            return ""
        limit = int(self.config.get("method_brief_char_limit", 1500) or 1500)
        rendered = [
            f"[{self._playbook_scope_label(entry)}] {entry.rule}"
            for entry in entries
        ]
        return _truncate("\n".join(rendered), limit)

    @staticmethod
    def _render_legacy_past_context(lessons: Sequence[OutcomeLessonEntry]) -> str:
        if not lessons:
            return ""
        ticker = lessons[-1].ticker
        lines = [f"Past lessons for {ticker} (most recent first):"]
        for entry in reversed(list(lessons)):
            lines.append(
                f"[{entry.trade_date} | {entry.ticker} | {entry.outcome_status} | {entry.raw_return:+.1%} | {entry.alpha_return:+.1%} | {entry.holding_days}d]"
            )
            lines.append(entry.lesson_summary)
        return "\n".join(lines).strip()

    def _role_brief_spec(self, role: str) -> list[str]:
        configured = self.config.get("role_brief_specs") or {}
        if role in configured:
            return list(configured[role])
        if role in {"trader", "research_manager", "portfolio_manager"}:
            return list(configured.get(role, _DEFAULT_ROLE_BRIEF_SPECS[role]))
        return list(configured.get("analyst", _DEFAULT_ROLE_BRIEF_SPECS["analyst"]))

    @staticmethod
    def _playbook_scope_label(entry: MethodPlaybookEntry) -> str:
        if entry.role == "all" and entry.ticker:
            return f"General/{entry.ticker}"
        if entry.role == "all":
            return "General"
        if entry.ticker:
            return f"{entry.role}/{entry.ticker}"
        return entry.role

    @staticmethod
    def _continuity_field_map(
        entry: AnalysisMemoryEntry,
        signal: Mapping[str, Any],
        target_summary: str,
    ) -> dict[str, str]:
        analyst_thesis = entry.research_summary or _strip_explicit_recommendation(entry.thesis_summary)
        trigger_bits = []
        for key in ("add_triggers", "reduce_triggers", "exit_triggers", "risk_rules"):
            trigger_bits.extend(_signal_rule_list(signal, key, max_items=1))
        return {
            "summary": f"Latest same-ticker thesis ({entry.trade_date}): {analyst_thesis}",
            "stance": f"Last stance: {target_summary}" if target_summary else "",
            "research_summary": f"Research summary: {entry.research_summary}" if entry.research_summary else "",
            "trader_summary": f"Latest same-ticker execution snapshot ({entry.trade_date}): {entry.trader_summary or entry.thesis_summary}",
            "portfolio_summary": f"Portfolio summary: {entry.portfolio_summary}" if entry.portfolio_summary else "",
            "key_drivers": "Prior key drivers: " + "; ".join(entry.key_drivers[:3]) if entry.key_drivers else "",
            "watch_items": "Prior watch items: " + "; ".join(entry.watch_items[:3]) if entry.watch_items else "",
            "invalidation_signals": "Prior invalidation signals: " + "; ".join(entry.invalidation_signals[:3]) if entry.invalidation_signals else "",
            "trigger_summary": "Last execution triggers: " + "; ".join(trigger_bits[:3]) if trigger_bits else "",
        }


def build_analysis_memory_entry(
    state: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    selected_analysts: Sequence[str],
) -> AnalysisMemoryEntry:
    ticker = get_asset_symbol(state)
    trade_date = str(get_state_value(state, "trade_date", ""))
    created_at = _utc_now_iso()
    run_id = f"{trade_date}_{_safe_path_token(ticker)}_{created_at.replace(':', '').replace('-', '')}"
    signal = build_state_backtest_signal(
        state,
        default_ticker=ticker,
        default_trade_date=trade_date,
    )
    investment_state = get_state_value(state, "investment_debate_state", {}) or {}
    risk_state = get_state_value(state, "risk_debate_state", {}) or {}

    driver_sources = (
        ("Market & Flow", get_state_value(state, "market_flow_report", "")),
        ("Sentiment & Catalyst", get_state_value(state, "catalyst_sentiment_report", "")),
        ("Macro Regime", get_state_value(state, "macro_regime_report", "")),
        ("Meso Commodity", get_state_value(state, "meso_commodity_report", "")),
        ("Holdings Industry", get_state_value(state, "holdings_industry_report", "")),
        ("Top Holdings", get_state_value(state, "top_holdings_report", "")),
    )
    key_drivers = [
        f"{label}: {_summarize_text(text, 180)}"
        for label, text in driver_sources
        if _summarize_text(text, 180)
    ][:4]
    key_risks = [
        f"Aggressive: {_summarize_text(risk_state.get('current_aggressive_response', ''), 160)}",
        f"Conservative: {_summarize_text(risk_state.get('current_conservative_response', ''), 160)}",
        f"Neutral: {_summarize_text(risk_state.get('current_neutral_response', ''), 160)}",
    ]
    key_risks = [item for item in key_risks if not item.endswith(": ")]

    return AnalysisMemoryEntry(
        id=run_id,
        ticker=ticker,
        trade_date=trade_date,
        run_id=run_id,
        created_at=created_at,
        config_hash=BacktestSignalStore(config, selected_analysts)._config_hash(),
        signal=dict(signal),
        thesis_summary=_summarize_text(get_state_value(state, "final_allocation_decision", ""), 500)
        or _summarize_text(get_state_value(state, "research_allocation_plan", ""), 500),
        bull_case_summary=_summarize_text(investment_state.get("current_bull_response", ""), 240),
        bear_case_summary=_summarize_text(investment_state.get("current_bear_response", ""), 240),
        key_drivers=key_drivers,
        key_risks=key_risks[:3],
        watch_items=_derive_watch_items(signal),
        invalidation_signals=_derive_invalidation_signals(signal),
        research_summary=_summarize_text(get_state_value(state, "research_allocation_plan", ""), 320),
        trader_summary=_summarize_text(get_state_value(state, "trader_allocation_plan", ""), 320),
        portfolio_summary=_summarize_text(get_state_value(state, "final_allocation_decision", ""), 420),
        outcome_status="pending",
    )


def create_memory_writer(
    store: AnalysisMemoryStore,
    *,
    config: Mapping[str, Any],
    selected_analysts: Sequence[str],
):
    def memory_writer_node(state: Mapping[str, Any]) -> dict[str, Any]:
        if not store.is_enabled():
            return {"analysis_memory_entry": {}}
        entry = build_analysis_memory_entry(
            state,
            config=config,
            selected_analysts=selected_analysts,
        )
        store.append_analysis(entry)
        return {"analysis_memory_entry": entry.to_dict()}

    return memory_writer_node


def classify_outcome_status(raw_return: float, alpha_return: float) -> str:
    if abs(raw_return) < 0.01 and abs(alpha_return) < 0.005:
        return "irrelevant_market_change"
    if raw_return > 0 and alpha_return >= 0:
        return "confirmed_correct"
    if raw_return < 0 and alpha_return < 0:
        return "confirmed_wrong"
    return "partially_correct"


def build_outcome_lesson_entry(
    analysis: AnalysisMemoryEntry,
    *,
    raw_return: float,
    alpha_return: float,
    holding_days: int,
    reflection: str,
) -> OutcomeLessonEntry:
    created_at = _utc_now_iso()
    return OutcomeLessonEntry(
        id=f"{analysis.id}__outcome",
        ticker=analysis.ticker,
        trade_date=analysis.trade_date,
        created_at=created_at,
        source_analysis_id=analysis.id,
        raw_return=raw_return,
        alpha_return=alpha_return,
        holding_days=int(holding_days),
        outcome_status=classify_outcome_status(raw_return, alpha_return),
        lesson_summary=_summarize_text(reflection, 320)
        or _summarize_text(analysis.thesis_summary, 220),
        reflection=str(reflection or "").strip(),
    )


def build_method_playbook_entry(lesson: OutcomeLessonEntry) -> MethodPlaybookEntry:
    return MethodPlaybookEntry(
        id=f"{lesson.id}__method",
        role="all",
        ticker=lesson.ticker,
        created_at=_utc_now_iso(),
        source_lesson_id=lesson.id,
        rule=_truncate(
            lesson.lesson_summary
            or f"Reassess the thesis independently and explain what changed after {lesson.outcome_status}.",
            260,
        ),
        rationale=f"{lesson.ticker} {lesson.trade_date} resolved as {lesson.outcome_status} with raw {lesson.raw_return:+.1%} and alpha {lesson.alpha_return:+.1%}.",
        status="draft",
    )


def _lookup_role_context(
    state: Mapping[str, Any],
    context_key: str,
    roles: Sequence[str],
) -> str:
    context = state.get(context_key, {})
    if not isinstance(context, Mapping):
        return ""
    for role in roles:
        value = context.get(role)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_memory_prompt_block(
    state: Mapping[str, Any],
    *,
    role: str,
    aliases: Sequence[str] = (),
) -> str:
    roles = (role, *aliases)
    continuity = _lookup_role_context(state, "continuity_context", roles)
    lesson = _lookup_role_context(state, "lesson_context", roles)
    method = _lookup_role_context(state, "method_context", roles)
    labels = {
        "continuity": (
            "最近一次同标的分析摘要（仅供内部吸收，不要照抄到可见答案中）"
            if _is_chinese_output()
            else "Latest same-ticker analysis brief (internal only; do not quote verbatim)"
        ),
        "lesson": (
            "已验证历史复盘（仅供内部吸收，不要照抄到可见答案中）"
            if _is_chinese_output()
            else "Resolved historical lessons (internal only; do not quote verbatim)"
        ),
        "method": (
            "可复用分析方法提醒（仅供内部吸收，不要照抄到可见答案中）"
            if _is_chinese_output()
            else "Reusable analysis-method reminders (internal only; do not quote verbatim)"
        ),
    }
    blocks = []
    if continuity:
        blocks.append(f"**{labels['continuity']}:**\n{continuity}")
    if lesson:
        blocks.append(f"**{labels['lesson']}:**\n{lesson}")
    if method:
        blocks.append(f"**{labels['method']}:**\n{method}")
    return "\n\n".join(blocks).strip()


def build_memory_prompt_section(
    state: Mapping[str, Any],
    *,
    role: str,
    aliases: Sequence[str] = (),
) -> str:
    block = build_memory_prompt_block(state, role=role, aliases=aliases)
    if not block:
        return ""
    return f"{block}\n\n{get_memory_usage_instruction()}"


def inject_memory_prompt_section(system_message: str, memory_section: str) -> str:
    if not memory_section:
        return system_message
    return f"{memory_section}\n\n{system_message}".strip()


def get_memory_usage_instruction() -> str:
    if _is_chinese_output():
        return (
            "若提供了最近一次分析摘要、历史复盘或方法提醒，必须先独立基于当前证据完成判断，再明确说明哪些前提延续、哪些变化、哪些失效。"
            "上次结论仅作对照，不应成为本次结论的默认起点；不得机械复述旧记忆。"
        )
    return (
        "If prior analysis, lessons, or method reminders are provided, first reason independently from current evidence, then explain what still holds, what changed, and what is invalidated. "
        "Treat prior conclusions as checkpoints rather than the default answer, and do not mechanically restate memory text."
    )
