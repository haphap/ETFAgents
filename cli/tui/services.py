"""Non-UI services used by the Textual TUI.

This module must NOT import textual.
"""

from __future__ import annotations

import copy
import csv
import datetime as _dt
import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from etfagents.default_config import DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Section definitions (9 sections matching AgentState)
# ---------------------------------------------------------------------------

ANALYST_KEYS = [
    "market_flow",
    "catalyst_sentiment",
    "macro_regime",
    "meso_commodity",
    "holdings_industry",
    "top_holdings",
]


@dataclass(frozen=True)
class SectionDef:
    section_id: str
    state_key: str
    detection_keys: tuple[str, ...]
    team: str
    title: str
    disk_paths: tuple[str, ...]


SECTION_DEFINITIONS: tuple[SectionDef, ...] = (
    SectionDef(
        "market_flow", "market_flow_report",
        ("market_flow_report",),
        "分析师", "市场与资金流",
        ("reports/market_flow_report.md", "1_analysts/market_flow.md"),
    ),
    SectionDef(
        "catalyst_sentiment", "catalyst_sentiment_report",
        ("catalyst_sentiment_report",),
        "分析师", "舆情与事件",
        ("reports/catalyst_sentiment_report.md", "1_analysts/catalyst_sentiment.md"),
    ),
    SectionDef(
        "macro_regime", "macro_regime_report",
        ("macro_regime_report",),
        "分析师", "宏观框架",
        ("reports/macro_regime_report.md", "1_analysts/macro_regime.md"),
    ),
    SectionDef(
        "meso_commodity", "meso_commodity_report",
        ("meso_commodity_report",),
        "分析师", "中观大宗",
        ("reports/meso_commodity_report.md", "1_analysts/meso_commodity.md"),
    ),
    SectionDef(
        "holdings_industry", "holdings_industry_report",
        ("holdings_industry_report",),
        "分析师", "持仓行业",
        ("reports/holdings_industry_report.md", "1_analysts/holdings_industry.md"),
    ),
    SectionDef(
        "top_holdings", "top_holdings_report",
        ("top_holdings_report",),
        "分析师", "头部持仓",
        ("reports/top_holdings_report.md", "1_analysts/top_holdings.md"),
    ),
    SectionDef(
        "research", "research_allocation_plan",
        ("research_allocation_plan", "investment_debate_state"),
        "研究", "研究团队",
        ("reports/research_allocation_plan.md", "2_research/manager.md"),
    ),
    SectionDef(
        "trader", "trader_allocation_plan",
        ("trader_allocation_plan",),
        "交易", "交易员",
        ("reports/trader_allocation_plan.md", "3_trading/trader.md"),
    ),
    SectionDef(
        "portfolio_manager", "final_allocation_decision",
        ("final_allocation_decision", "risk_debate_state"),
        "决策", "投资组合经理",
        ("reports/final_allocation_decision.md", "5_portfolio/decision.md"),
    ),
)

SECTION_BY_ID = {defn.section_id: defn for defn in SECTION_DEFINITIONS}


# ---------------------------------------------------------------------------
# Ticker state
# ---------------------------------------------------------------------------

class TickerState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# ID registry
# ---------------------------------------------------------------------------

class IdRegistry:
    """Map arbitrary values to Textual-safe widget ids."""

    def __init__(self, prefix: str):
        self.prefix = prefix
        self._value_to_id: dict[str, str] = {}
        self._id_to_value: dict[str, str] = {}

    def register(self, value: str) -> str:
        if value in self._value_to_id:
            return self._value_to_id[value]
        base = self._sanitize(value)
        candidate = base
        index = 2
        while candidate in self._id_to_value:
            candidate = f"{base}-{index}"
            index += 1
        self._value_to_id[value] = candidate
        self._id_to_value[candidate] = value
        return candidate

    def resolve(self, item_id: str) -> str:
        return self._id_to_value[item_id]

    def __contains__(self, item_id: object) -> bool:
        return isinstance(item_id, str) and item_id in self._id_to_value

    def clear(self) -> None:
        self._value_to_id.clear()
        self._id_to_value.clear()

    def _sanitize(self, value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in value)
        if not safe or safe[0].isdigit():
            safe = f"{self.prefix}_{safe}"
        return safe


# ---------------------------------------------------------------------------
# Analysis events (tagged union)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TickerStarted:
    ticker: str
    total_sections: int


@dataclass(frozen=True)
class SectionDone:
    ticker: str
    section_id: str
    content: str
    completed: int
    total: int


@dataclass(frozen=True)
class TickerDone:
    ticker: str
    report_path: Path
    rating: str | None


@dataclass(frozen=True)
class TickerFailed:
    ticker: str
    error: str


@dataclass(frozen=True)
class TickerCancelled:
    ticker: str


AnalysisEvent = TickerStarted | SectionDone | TickerDone | TickerFailed | TickerCancelled


# ---------------------------------------------------------------------------
# Report data
# ---------------------------------------------------------------------------

@dataclass
class ReportRecord:
    ticker: str
    date: str
    path: Path
    rating: str | None = None
    sections: dict[str, Path] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ReportRepository
# ---------------------------------------------------------------------------

class ReportRepository:
    """Scan and read locally saved single-ETF reports.  Thread-safe (read-only + simple cache clear)."""

    _SKIP_DIRS = {"backtest", "memory"}

    def __init__(self, results_dir: str | Path | None = None):
        self.results_dir = Path(results_dir or DEFAULT_CONFIG["results_dir"]).expanduser()
        self._cache: list[ReportRecord] | None = None

    def invalidate(self) -> None:
        self._cache = None

    def list_reports(self) -> list[ReportRecord]:
        if self._cache is not None:
            return list(self._cache)
        if not self.results_dir.exists():
            return []
        records: list[ReportRecord] = []
        for ticker_dir in sorted(self.results_dir.iterdir()):
            if not ticker_dir.is_dir():
                continue
            if ticker_dir.name.startswith("_") or ticker_dir.name in self._SKIP_DIRS:
                continue
            for date_dir in sorted(ticker_dir.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                complete = date_dir / "complete_report.md"
                if not complete.exists():
                    continue
                sections = self._discover_sections(date_dir)
                records.append(
                    ReportRecord(
                        ticker=ticker_dir.name,
                        date=date_dir.name,
                        path=date_dir,
                        rating=self._extract_rating(complete),
                        sections=sections,
                    )
                )
        self._cache = sorted(records, key=lambda r: (r.ticker, r.date), reverse=True)
        return list(self._cache)

    def read_section(self, record: ReportRecord, section_id: str) -> str:
        if section_id == "complete":
            complete = record.path / "complete_report.md"
            return complete.read_text(encoding="utf-8") if complete.exists() else ""

        # research: merge bull + bear + manager
        if section_id == "research":
            return self._read_research_merged(record)

        # portfolio_manager: merge risk debaters + decision
        if section_id == "portfolio_manager":
            return self._read_portfolio_merged(record)

        # normal section
        section_path = record.sections.get(section_id)
        if section_path and section_path.exists():
            return section_path.read_text(encoding="utf-8")

        # fallback to complete report
        complete = record.path / "complete_report.md"
        return complete.read_text(encoding="utf-8") if complete.exists() else ""

    def _read_research_merged(self, record: ReportRecord) -> str:
        parts: list[str] = []
        for name, rel in [("多头", "2_research/bull.md"), ("空头", "2_research/bear.md")]:
            p = record.path / rel
            if p.exists():
                parts.append(f"### {name}\n{p.read_text(encoding='utf-8')}")

        # manager content — try several candidates
        manager_content = ""
        for rel in ("reports/research_allocation_plan.md", "2_research/manager.md", "2_research/rounds.md"):
            p = record.path / rel
            if p.exists():
                manager_content = p.read_text(encoding="utf-8")
                break
        if manager_content:
            parts.append(f"### 研究经理综合结论\n{manager_content}")

        return "\n\n".join(parts) if parts else ""

    def _read_portfolio_merged(self, record: ReportRecord) -> str:
        parts: list[str] = []
        for name, rel in [
            ("激进", "4_risk/aggressive.md"),
            ("中性", "4_risk/neutral.md"),
            ("保守", "4_risk/conservative.md"),
        ]:
            p = record.path / rel
            if p.exists():
                parts.append(f"### {name}\n{p.read_text(encoding='utf-8')}")

        decision_content = ""
        for rel in ("reports/final_allocation_decision.md", "5_portfolio/decision.md"):
            p = record.path / rel
            if p.exists():
                decision_content = p.read_text(encoding="utf-8")
                break
        if decision_content:
            parts.append(f"### 投资组合经理\n{decision_content}")

        return "\n\n".join(parts) if parts else ""

    def _discover_sections(self, report_dir: Path) -> dict[str, Path]:
        sections: dict[str, Path] = {}
        for defn in SECTION_DEFINITIONS:
            for relative in defn.disk_paths:
                candidate = report_dir / relative
                if candidate.exists():
                    sections[defn.section_id] = candidate
                    break
        return sections

    def _extract_rating(self, complete_report: Path) -> str | None:
        try:
            text = complete_report.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            from etfagents.agents.utils.rating import parse_rating
            rating = parse_rating(text)
            if rating:
                return rating
        except Exception:
            pass
        upper = text.upper()
        for rating in ("OVERWEIGHT", "UNDERWEIGHT", "BUY", "SELL", "HOLD"):
            if rating in upper:
                return rating
        return None


# ---------------------------------------------------------------------------
# Backtest data
# ---------------------------------------------------------------------------

@dataclass
class BacktestRecord:
    output_dir: Path
    tickers: list[str]
    start_date: str
    end_date: str
    cumulative_return: float | None


@dataclass
class BacktestViewModel:
    output_dir: Path
    summary: str | None
    metrics: dict[str, Any] | None
    nav: list[dict[str, str]] | None
    orders: list[dict[str, str]] | None
    trades: list[dict[str, str]] | None
    sparkline: str


# ---------------------------------------------------------------------------
# BacktestViewer (v1 view-only)
# ---------------------------------------------------------------------------

class BacktestViewer:
    """Read existing backtest artifacts.  Does not import Graph or cli.main."""

    def __init__(self, results_dir: str | Path | None = None):
        self.results_dir = Path(results_dir or DEFAULT_CONFIG["results_dir"]).expanduser()

    def list_results(self) -> list[BacktestRecord]:
        bt_root = self.results_dir / "backtest"
        if not bt_root.exists():
            return []
        records: list[BacktestRecord] = []
        for metrics_path in bt_root.glob("**/metrics.json"):
            output_dir = metrics_path.parent
            metrics = self._read_json(metrics_path)
            manifest = self._read_json(output_dir / "manifest.json")

            cumulative_return = None
            if metrics and "metrics" in metrics:
                cumulative_return = metrics["metrics"].get("cumulative_return")

            if manifest:
                tickers = manifest.get("tickers", [])
                start_date = manifest.get("start_date", "")
                end_date = manifest.get("end_date", "")
            else:
                tickers = []
                start_date = ""
                end_date = ""
                # try to parse from directory name: {start}_to_{end}
                parent_name = output_dir.parent.name
                if "_to_" in parent_name:
                    parts = parent_name.split("_to_")
                    start_date = parts[0]
                    end_date = parts[1] if len(parts) > 1 else ""

            records.append(BacktestRecord(
                output_dir=output_dir,
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                cumulative_return=cumulative_return,
            ))

        records.sort(key=lambda r: r.output_dir.stat().st_mtime, reverse=True)
        return records

    def load(self, output_dir: str | Path) -> BacktestViewModel:
        path = Path(output_dir)
        nav = self._read_csv(path / "nav.csv")
        return BacktestViewModel(
            output_dir=path,
            summary=self._read_text(path / "summary.md"),
            metrics=self._read_json(path / "metrics.json"),
            nav=nav,
            orders=self._read_csv(path / "orders.csv"),
            trades=self._read_csv(path / "trades.csv"),
            sparkline=self.sparkline(nav),
        )

    def sparkline(self, nav: list[dict[str, str]] | None) -> str:
        if not nav:
            return ""
        values: list[float] = []
        for row in nav:
            raw = row.get("nav") or row.get("value") or row.get("total_value")
            try:
                values.append(float(raw))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        if not values:
            return ""
        ticks = "▁▂▃▄▅▆▇█"
        lo, hi = min(values), max(values)
        if hi == lo:
            return ticks[0] * len(values)
        return "".join(
            ticks[int((v - lo) / (hi - lo) * (len(ticks) - 1))] for v in values
        )

    def _read_text(self, path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _read_csv(self, path: Path) -> list[dict[str, str]] | None:
        if not path.exists():
            return None
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
        except (OSError, csv.Error, UnicodeDecodeError):
            return None


# ---------------------------------------------------------------------------
# Paper trading
# ---------------------------------------------------------------------------

@dataclass
class PaperTradingSnapshot:
    account: dict[str, Any]
    positions: list[dict[str, Any]]
    trades: list[dict[str, Any]]


class PaperTradingViewModel:
    """Wraps PaperTradingEngine.  v1 only exposes snapshot() (read-only)."""

    def __init__(self, engine: Any | None = None):
        if engine is None:
            from etfagents.paper_trading.engine import PaperTradingEngine
            engine = PaperTradingEngine()
        self.engine = engine

    def snapshot(self, user_id: str | None = None, trade_limit: int = 20) -> PaperTradingSnapshot:
        return PaperTradingSnapshot(
            account=self.engine.get_account(user_id=user_id),
            positions=self.engine.get_positions(user_id=user_id),
            trades=self.engine.get_trades(user_id=user_id, limit=trade_limit),
        )
