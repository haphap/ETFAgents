from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from etfagents.dataflows.config import get_backtest_context


_CACHE_VERSION = 2


def _safe_path_token(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in (value or "").strip())


@dataclass
class BacktestSignalStore:
    config: Mapping[str, Any]
    selected_analysts: Sequence[str]
    force_refresh: bool = False
    memory_signature: str | None = None

    def is_enabled(self) -> bool:
        context = get_backtest_context()
        return context.mode == "backtest" and bool(context.as_of_date)

    def get(self, ticker: str, decision_date: str) -> dict[str, Any] | None:
        if self.force_refresh or not self.is_enabled():
            return None
        path = self._cache_path(ticker, decision_date)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, ticker: str, decision_date: str, payload: Mapping[str, Any]) -> None:
        if not self.is_enabled():
            return
        path = self._cache_path(ticker, decision_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(dict(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _cache_path(self, ticker: str, decision_date: str) -> Path:
        return (
            Path(self.config["results_dir"])
            / "backtest_cache"
            / self._config_hash()
            / _safe_path_token(ticker)
            / f"{decision_date}.json"
        )

    def _config_hash(self) -> str:
        material = {
            "version": _CACHE_VERSION,
            "selected_analysts": list(self.selected_analysts),
            "llm_provider": self.config.get("llm_provider"),
            "deep_think_llm": self.config.get("deep_think_llm"),
            "quick_think_llm": self.config.get("quick_think_llm"),
            "max_debate_rounds": self.config.get("max_debate_rounds"),
            "max_risk_discuss_rounds": self.config.get("max_risk_discuss_rounds"),
            "output_language": self.config.get("output_language"),
            "backend_url": self.config.get("backend_url"),
            "data_vendors": self.config.get("data_vendors"),
            "tool_vendors": self.config.get("tool_vendors"),
            "memory_signature": self.memory_signature or "",
        }
        encoded = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]
