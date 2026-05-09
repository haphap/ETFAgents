from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from etfagents.agents.utils.rating import parse_rating


def _canonical_rating(decision: str) -> str:
    return parse_rating(decision).title()


def _format_percent(value: float) -> str:
    return f"{value:+.1%}"


@dataclass
class _Entry:
    date: str
    ticker: str
    rating: str
    decision: str
    pending: bool = True
    raw: str | None = None
    alpha: str | None = None
    holding: str | None = None
    reflection: str = ""


class TradingMemoryLog:
    """Persistent append-only trading memory with deferred reflection."""

    _SEPARATOR = "\n\n<!-- trading-memory-entry -->\n\n"
    _PENDING_PATTERN = re.compile(r"^\[(?P<date>[^|]+)\|(?P<ticker>[^|]+)\|(?P<rating>[^|]+)\| pending\]$")
    _RESOLVED_PATTERN = re.compile(
        r"^\[(?P<date>[^|]+)\|(?P<ticker>[^|]+)\|(?P<rating>[^|]+)\| (?P<raw>[^|]+)\| (?P<alpha>[^|]+)\| (?P<holding>[^\]]+)\]$"
    )

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        configured_path = cfg.get("memory_log_path")
        if configured_path:
            self.log_path = Path(configured_path).expanduser()
        elif cfg.get("data_cache_dir"):
            self.log_path = Path(cfg["data_cache_dir"]).expanduser() / "trading_memory.md"
        else:
            self.log_path = None
        self.max_entries = cfg.get("memory_log_max_entries")

    def _ensure_parent(self) -> None:
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_text(self) -> str:
        if self.log_path is None or not self.log_path.exists():
            return ""
        return self.log_path.read_text(encoding="utf-8")

    def _write_entries(self, entries: list[_Entry]) -> None:
        if self.log_path is None:
            return
        self._ensure_parent()
        tmp_path = self.log_path.with_suffix(".tmp")
        content = self._SEPARATOR.join(self._format_entry(entry) for entry in entries).strip()
        if content:
            content += self._SEPARATOR
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(self.log_path)

    def _format_entry(self, entry: _Entry) -> str:
        if entry.pending:
            header = f"[{entry.date} | {entry.ticker} | {entry.rating} | pending]"
            return f"{header}\n\nDECISION:\n{entry.decision.strip()}"
        header = f"[{entry.date} | {entry.ticker} | {entry.rating} | {entry.raw} | {entry.alpha} | {entry.holding}]"
        return (
            f"{header}\n\n"
            f"DECISION:\n{entry.decision.strip()}\n\n"
            f"REFLECTION:\n{entry.reflection.strip()}"
        )

    def _parse_entry(self, raw_entry: str) -> _Entry | None:
        entry = raw_entry.strip()
        if not entry:
            return None
        lines = entry.splitlines()
        if not lines:
            return None
        header = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        if not body.startswith("DECISION:\n"):
            return None

        pending_match = self._PENDING_PATTERN.match(header)
        resolved_match = self._RESOLVED_PATTERN.match(header)
        decision_block = body[len("DECISION:\n") :]
        reflection = ""
        if "\n\nREFLECTION:\n" in decision_block:
            decision, reflection = decision_block.split("\n\nREFLECTION:\n", 1)
        else:
            decision = decision_block

        if pending_match:
            return _Entry(
                date=pending_match.group("date").strip(),
                ticker=pending_match.group("ticker").strip(),
                rating=pending_match.group("rating").strip(),
                decision=decision.strip(),
                pending=True,
            )
        if resolved_match:
            return _Entry(
                date=resolved_match.group("date").strip(),
                ticker=resolved_match.group("ticker").strip(),
                rating=resolved_match.group("rating").strip(),
                decision=decision.strip(),
                pending=False,
                raw=resolved_match.group("raw").strip(),
                alpha=resolved_match.group("alpha").strip(),
                holding=resolved_match.group("holding").strip(),
                reflection=reflection.strip(),
            )
        return None

    def load_entries(self) -> list[dict[str, Any]]:
        raw_text = self._read_text()
        if not raw_text.strip():
            return []
        parsed_entries = []
        for chunk in raw_text.split(self._SEPARATOR):
            parsed = self._parse_entry(chunk)
            if parsed is None:
                continue
            parsed_entries.append(
                {
                    "date": parsed.date,
                    "ticker": parsed.ticker,
                    "rating": parsed.rating,
                    "pending": parsed.pending,
                    "raw": parsed.raw,
                    "alpha": parsed.alpha,
                    "holding": parsed.holding,
                    "decision": parsed.decision,
                    "reflection": parsed.reflection,
                }
            )
        return parsed_entries

    def _load_entry_models(self) -> list[_Entry]:
        return [
            _Entry(**entry)
            for entry in self.load_entries()
        ]

    def store_decision(self, ticker: str, trade_date: str, decision: str) -> None:
        if self.log_path is None or not decision:
            return

        entries = self._load_entry_models()
        if any(entry.ticker == ticker and entry.date == str(trade_date) for entry in entries):
            return

        entries.append(
            _Entry(
                date=str(trade_date),
                ticker=ticker,
                rating=_canonical_rating(decision),
                decision=decision.strip(),
            )
        )
        self._write_entries(entries)

    def get_pending_entries(self) -> list[dict[str, Any]]:
        return [entry for entry in self.load_entries() if entry["pending"]]

    def update_with_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
    ) -> None:
        self.batch_update_with_outcomes(
            [
                {
                    "ticker": ticker,
                    "trade_date": trade_date,
                    "raw_return": raw_return,
                    "alpha_return": alpha_return,
                    "holding_days": holding_days,
                    "reflection": reflection,
                }
            ]
        )

    def batch_update_with_outcomes(self, updates: list[dict[str, Any]]) -> None:
        if self.log_path is None or not updates:
            return

        entries = self._load_entry_models()
        update_map = {
            (item["ticker"], str(item["trade_date"])): item
            for item in updates
        }
        for entry in entries:
            update = update_map.get((entry.ticker, entry.date))
            if update is None or not entry.pending:
                continue
            entry.pending = False
            entry.raw = _format_percent(update["raw_return"])
            entry.alpha = _format_percent(update["alpha_return"])
            entry.holding = f"{int(update['holding_days'])}d"
            entry.reflection = str(update["reflection"]).strip()

        self._write_entries(self._rotate_entries(entries))

    def _rotate_entries(self, entries: list[_Entry]) -> list[_Entry]:
        if not self.max_entries:
            return entries
        resolved = [entry for entry in entries if not entry.pending]
        pending = [entry for entry in entries if entry.pending]
        if len(resolved) <= int(self.max_entries):
            return entries
        resolved = resolved[-int(self.max_entries) :]
        return resolved + pending

    def get_past_context(self, ticker: str, n_same: int = 3, n_cross: int = 2) -> str:
        resolved = [entry for entry in self._load_entry_models() if not entry.pending]
        if not resolved:
            return ""

        same_ticker: list[_Entry] = []
        cross_ticker: list[_Entry] = []
        for entry in reversed(resolved):
            if entry.ticker == ticker and len(same_ticker) < n_same:
                same_ticker.append(entry)
            elif entry.ticker != ticker and len(cross_ticker) < n_cross:
                cross_ticker.append(entry)
            if len(same_ticker) >= n_same and len(cross_ticker) >= n_cross:
                break

        sections = []
        if same_ticker:
            sections.append(
                f"Past analyses of {ticker} (most recent first):\n"
                + "\n\n".join(self._context_block(entry) for entry in same_ticker)
            )
        if cross_ticker:
            sections.append(
                "Recent cross-ticker lessons:\n"
                + "\n\n".join(self._reflection_context_block(entry) for entry in cross_ticker)
            )
        return "\n\n".join(section.strip() for section in sections if section).strip()

    def _context_block(self, entry: _Entry) -> str:
        return (
            f"[{entry.date} | {entry.ticker} | {entry.rating} | {entry.raw} | {entry.alpha} | {entry.holding}]\n"
            f"DECISION:\n{entry.decision.strip()}\n\n"
            f"REFLECTION:\n{entry.reflection.strip()}"
        ).strip()

    def _reflection_context_block(self, entry: _Entry) -> str:
        tag = f"[{entry.date} | {entry.ticker} | {entry.rating} | {entry.raw or 'n/a'}]"
        if entry.reflection.strip():
            return f"{tag}\n{entry.reflection.strip()}"
        excerpt = entry.decision.strip()
        if len(excerpt) > 300:
            excerpt = excerpt[:297].rstrip() + "..."
        return f"{tag}\n{excerpt}".strip()
