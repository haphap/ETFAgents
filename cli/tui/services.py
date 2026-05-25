"""Non-UI services used by the Textual TUI.

This module must NOT import textual.
"""

from __future__ import annotations

import copy
import csv
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.llm_clients.model_catalog import (
    RESEARCH_DEPTH_REQUIREMENTS as RESEARCH_DEPTH_REQUIREMENTS,
)


# ---------------------------------------------------------------------------
# Section definitions (9 sections matching AgentState)
# ---------------------------------------------------------------------------
#
# Mapping convention:
#   section_id  — stable UI identifier (e.g. "market_flow")
#   state_key   — AgentState field that holds the section content
#                 (e.g. "market_flow_report")
#
# When AnalysisRunner lands (M2), it will walk SECTION_DEFINITIONS to map
# stream-chunk keys back to UI section_ids.  detection_keys (for multi-key
# triggers like research/portfolio_manager) will be added to SectionDef at
# that time.

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
        "research_debate", "_research_debate_formatted",
        ("investment_debate_state",),
        "研究", "多空辩论",
        ("2_research/bull.md", "2_research/bear.md"),
    ),
    SectionDef(
        "research", "research_allocation_plan",
        ("research_allocation_plan",),
        "研究", "研究经理",
        ("reports/research_allocation_plan.md", "2_research/manager.md"),
    ),
    SectionDef(
        "trader", "trader_allocation_plan",
        ("trader_allocation_plan",),
        "交易", "交易员",
        ("reports/trader_allocation_plan.md", "3_trading/trader.md"),
    ),
    SectionDef(
        "risk_debate", "_risk_debate_formatted",
        ("risk_debate_state",),
        "风险", "风险辩论",
        ("4_risk/aggressive.md", "4_risk/neutral.md", "4_risk/conservative.md"),
    ),
    SectionDef(
        "portfolio_manager", "final_allocation_decision",
        ("final_allocation_decision",),
        "决策", "投资组合经理",
        ("reports/final_allocation_decision.md", "5_portfolio/decision.md"),
    ),
)

SECTION_BY_ID = {defn.section_id: defn for defn in SECTION_DEFINITIONS}


def section_definitions_for(selected_analysts: list[str] | None = None) -> tuple[SectionDef, ...]:
    """Return sections that should be visible for the selected analysis config."""
    if selected_analysts is None:
        selected = set(ANALYST_KEYS)
    else:
        selected = set(selected_analysts)
    return tuple(
        defn
        for defn in SECTION_DEFINITIONS
        if defn.team != "分析师" or defn.section_id in selected
    )


# ---------------------------------------------------------------------------
# Analysis configuration
# ---------------------------------------------------------------------------

@dataclass
class AnalysisConfig:
    selected_analysts: list[str] = field(default_factory=lambda: list(ANALYST_KEYS))
    analysis_date: str | None = None
    depth_name: str = "标准"
    llm_provider: str = "openai"
    backend_url: str | None = None
    quick_model: str | None = None
    deep_model: str | None = None
    output_language: str = "Chinese"


# ---------------------------------------------------------------------------
# TUI settings — canonical definitions live in cli.tui.settings
# ---------------------------------------------------------------------------

from cli.tui.settings import (  # noqa: F401, E402
    AVAILABLE_THEMES,
    DENSITY_OPTIONS,
    PANEL_WIDTH_PRESETS,
    SETTINGS_PATH,
    TuiSettings,
)


# ---------------------------------------------------------------------------
# Ticker state and events
# ---------------------------------------------------------------------------

class TickerState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


@dataclass(frozen=True)
class DebateProgress:
    """Emitted when debate round counts change in research or risk stages."""
    ticker: str
    section_id: str  # "research" or "risk_debate"
    current_round: int
    max_rounds: int


AnalysisEvent = TickerStarted | SectionDone | TickerDone | TickerFailed | TickerCancelled | DebateProgress


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

    # Explicit exclusions for non-underscore-prefixed dirs that aren't ticker
    # directories.  Dirs starting with "_" (e.g. _candidate_pools) are already
    # filtered by the startswith("_") check below.
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

        if section_id == "research_debate":
            return self._read_research_debate(record)

        if section_id == "research":
            return self._read_research_manager(record)

        if section_id == "risk_debate":
            return self._read_risk_debate(record)

        if section_id == "portfolio_manager":
            return self._read_portfolio_decision(record)

        # normal section
        section_path = record.sections.get(section_id)
        if section_path and section_path.exists():
            return section_path.read_text(encoding="utf-8")

        # fallback to complete report
        complete = record.path / "complete_report.md"
        return complete.read_text(encoding="utf-8") if complete.exists() else ""

    def _read_research_debate(self, record: ReportRecord) -> str:
        parts: list[str] = []
        for name, rel in [("多头", "2_research/bull.md"), ("空头", "2_research/bear.md")]:
            p = record.path / rel
            if p.exists():
                parts.append(f"### {name}\n{p.read_text(encoding='utf-8')}")
        return "\n\n".join(parts) if parts else ""

    def _read_research_manager(self, record: ReportRecord) -> str:
        for rel in ("reports/research_allocation_plan.md", "2_research/manager.md", "2_research/rounds.md"):
            p = record.path / rel
            if p.exists():
                return p.read_text(encoding="utf-8")
        return ""

    def _read_risk_debate(self, record: ReportRecord) -> str:
        parts: list[str] = []
        for name, rel in [
            ("激进", "4_risk/aggressive.md"),
            ("中性", "4_risk/neutral.md"),
            ("保守", "4_risk/conservative.md"),
        ]:
            p = record.path / rel
            if p.exists():
                parts.append(f"### {name}\n{p.read_text(encoding='utf-8')}")
        return "\n\n".join(parts) if parts else ""

    def _read_portfolio_decision(self, record: ReportRecord) -> str:
        for rel in ("reports/final_allocation_decision.md", "5_portfolio/decision.md"):
            p = record.path / rel
            if p.exists():
                return p.read_text(encoding="utf-8")
        return ""

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
            rating = parse_rating(text, default="")
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
        """Build a ▁▂▃▄▅▆▇█ sparkline from nav rows.

        Public so that callers (including tests) can compute sparklines
        for arbitrary nav data without going through load().
        """
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
# AnalysisRunner (M2)
# ---------------------------------------------------------------------------

class AnalysisRunner:
    """Stream graph execution for ETF analysis.

    run_queue() is a sync generator designed for worker threads.
    Events are yielded as analysis progresses.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = copy.deepcopy(config or DEFAULT_CONFIG)
        self.states: dict[str, TickerState] = {}
        self._cancel_event = threading.Event()
        self._stats_handler: Any = None

    def request_cancel(self) -> None:
        self._cancel_event.set()

    def run_queue(
        self,
        tickers: list[str],
        analysis_date: str | None = None,
        selected_analysts: list[str] | None = None,
    ) -> Iterator[AnalysisEvent]:
        """Run analysis on a queue of tickers, yielding events."""
        date = analysis_date or datetime.now().date().isoformat()
        analysts = selected_analysts or list(ANALYST_KEYS)
        normalized = [t.strip().upper() for t in tickers if t.strip()]
        self._cancel_event.clear()
        self.states = {t: TickerState.PENDING for t in normalized}

        for ticker in normalized:
            if self._cancel_event.is_set():
                self.states[ticker] = TickerState.CANCELLED
                yield TickerCancelled(ticker=ticker)
                continue
            yield from self.run_one(ticker, date, analysts)

    def run_one(
        self,
        ticker: str,
        analysis_date: str,
        selected_analysts: list[str],
    ) -> Iterator[AnalysisEvent]:
        """Run a single ticker's analysis."""
        graph = None
        try:
            self.states[ticker] = TickerState.RUNNING
            graph = self._make_graph(selected_analysts)

            active_sections = section_definitions_for(selected_analysts)
            yield TickerStarted(ticker=ticker, total_sections=len(active_sections))

            init_state, args, _ = graph.prepare_run(
                ticker,
                analysis_date,
                callbacks=[self._ensure_stats_handler()],
            )
            accumulated = copy.deepcopy(init_state)

            from cli.report_utils import merge_stream_state

            emitted_sections: dict[str, str] = {}
            last_debate_counts: dict[str, int] = {}

            for chunk in graph.graph.stream(init_state, **args):
                if self._cancel_event.is_set():
                    self.states[ticker] = TickerState.CANCELLED
                    yield TickerCancelled(ticker=ticker)
                    return

                merge_stream_state(accumulated, chunk)
                for dp in self._detect_debate_progress(
                    chunk, last_debate_counts, ticker
                ):
                    yield dp
                for event in self._detect_section_updates(
                    chunk, accumulated, emitted_sections, ticker, active_sections
                ):
                    yield event

            # Finalize and save (skip if cancelled during stream)
            if self._cancel_event.is_set():
                self.states[ticker] = TickerState.CANCELLED
                yield TickerCancelled(ticker=ticker)
                return

            graph.finalize_run(analysis_date, accumulated)
            report_path = self._save_report(accumulated, ticker, analysis_date)
            rating = self._extract_rating_from_report(report_path)
            self.states[ticker] = TickerState.DONE
            yield TickerDone(ticker=ticker, report_path=report_path, rating=rating)

        except Exception as exc:
            self.states[ticker] = TickerState.FAILED
            yield TickerFailed(ticker=ticker, error=str(exc))
        finally:
            if graph:
                graph.close_run()

    def _detect_section_updates(
        self,
        chunk: dict,
        accumulated: dict,
        emitted_sections: dict[str, str],
        ticker: str,
        section_definitions: tuple[SectionDef, ...] = SECTION_DEFINITIONS,
    ) -> Iterator[SectionDone]:
        """Yield SectionDone events when section content changes.

        Deviation from plan §7.2: SectionDone is emitted on every content
        change, not only on final completion.  For debate sections (research,
        risk) this means the UI can show intermediate progress — e.g. bull
        arguments appear before the judge decides.  Deduplication is by
        content equality (``emitted_sections[id] == content``), so unchanged
        chunks are silently skipped.
        """
        for defn in section_definitions:
            for det_key in defn.detection_keys:
                value = self._get_chunk_value(chunk, det_key)
                if value is None:
                    continue

                # Determine content and trigger
                if det_key == defn.state_key:
                    content = str(value)
                elif det_key == "investment_debate_state":
                    if not isinstance(value, dict):
                        continue
                    content = self._format_research(value)
                elif det_key == "risk_debate_state":
                    if not isinstance(value, dict):
                        continue
                    content = self._format_risk(value)
                else:
                    content = str(value)

                if not content.strip() or emitted_sections.get(defn.section_id) == content:
                    continue

                is_new_section = defn.section_id not in emitted_sections
                emitted_sections[defn.section_id] = content
                completed = len(emitted_sections) if is_new_section else len(emitted_sections)
                yield SectionDone(
                    ticker=ticker,
                    section_id=defn.section_id,
                    content=content,
                    completed=completed,
                    total=len(section_definitions),
                )
                break

    def _detect_debate_progress(
        self,
        chunk: dict,
        last_counts: dict[str, int],
        ticker: str,
    ) -> Iterator[DebateProgress]:
        """Yield DebateProgress when debate round counts change."""
        invest_state = self._get_chunk_value(chunk, "investment_debate_state")
        if isinstance(invest_state, dict):
            count = invest_state.get("count", 0)
            if count != last_counts.get("research_debate", 0):
                last_counts["research_debate"] = count
                max_rounds = self.config.get("max_debate_rounds", 1)
                yield DebateProgress(
                    ticker=ticker,
                    section_id="research_debate",
                    current_round=count // 2,
                    max_rounds=max_rounds,
                )

        risk_state = self._get_chunk_value(chunk, "risk_debate_state")
        if isinstance(risk_state, dict):
            count = risk_state.get("count", 0)
            if count != last_counts.get("risk_debate", 0):
                last_counts["risk_debate"] = count
                max_rounds = self.config.get("max_risk_discuss_rounds", 1)
                yield DebateProgress(
                    ticker=ticker,
                    section_id="risk_debate",
                    current_round=(count + 2) // 3,
                    max_rounds=max_rounds,
                )

    def _get_chunk_value(self, chunk: dict, key: str) -> Any:
        """Extract value from chunk, checking top-level and nested node outputs."""
        if not isinstance(chunk, dict):
            return None

        # Direct key
        if key in chunk:
            return chunk.get(key)

        # Nested under node name
        for value in chunk.values():
            if isinstance(value, dict) and key in value:
                return value.get(key)
        return None

    def _format_research(self, debate: dict) -> str:
        """Format research debate state to Markdown."""
        from cli.main import format_research_team_history
        return format_research_team_history(debate)

    def _format_risk(self, risk: dict) -> str:
        """Format risk debate state to Markdown (debaters only, no PM)."""
        from cli.main import format_risk_management_history
        return format_risk_management_history(risk, include_manager=False)

    def _make_graph(self, selected_analysts: list[str] | None = None) -> Any:
        """Lazy import and create graph."""
        from etfagents.graph.etf_graph import EtfAgentsGraph
        return EtfAgentsGraph(
            selected_analysts=selected_analysts,
            config=self.config,
            debug=False,
            callbacks=[self._ensure_stats_handler()],
        )

    def _ensure_stats_handler(self) -> Any:
        if self._stats_handler is None:
            from cli.stats_handler import StatsCallbackHandler
            self._stats_handler = StatsCallbackHandler()
        return self._stats_handler

    def get_stats(self) -> dict[str, Any]:
        """Return current LLM/tool/token usage stats."""
        return self._ensure_stats_handler().get_stats()

    def _save_report(self, state: dict, ticker: str, analysis_date: str) -> Path:
        """Save complete report to disk."""
        from cli.main import save_report_to_disk
        save_path = (
            Path(self.config["results_dir"]).expanduser() /
            ticker / analysis_date
        )
        return save_report_to_disk(state, ticker, save_path)

    def _extract_rating_from_report(self, report_path: Path) -> str | None:
        """Extract rating from complete_report.md."""
        complete = report_path.parent / "complete_report.md"
        if not complete.exists():
            return None
        try:
            text = complete.read_text(encoding="utf-8")
            from etfagents.agents.utils.rating import parse_rating
            return parse_rating(text, default="")
        except (ImportError, AttributeError, OSError):
            return None


# ---------------------------------------------------------------------------
# Backtest runner (M4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BacktestStarted:
    tickers: list[str]
    start_date: str
    end_date: str


@dataclass(frozen=True)
class BacktestFinished:
    output_dir: Path


@dataclass(frozen=True)
class BacktestFailed:
    error: str


BacktestEvent = BacktestStarted | BacktestFinished | BacktestFailed


class BacktestRunner:
    """Run a backtest, yielding events.  Designed for worker threads."""

    def run(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        rebalance_interval_days: int = 21,
        top_k: int = 3,
        initial_cash: float = 1_000_000.0,
        config: dict[str, Any] | None = None,
    ) -> Iterator[BacktestEvent]:
        yield BacktestStarted(tickers=tickers, start_date=start_date, end_date=end_date)
        try:
            from etfagents.graph.etf_graph import EtfAgentsGraph
            from etfagents.backtest import save_backtest_result

            cfg = copy.deepcopy(config or DEFAULT_CONFIG)
            graph = EtfAgentsGraph(config=cfg, debug=False)
            result = graph.backtest_candidate_pool(
                tickers,
                start_date=start_date,
                end_date=end_date,
                rebalance_interval_days=rebalance_interval_days,
                top_k=top_k,
                initial_cash=initial_cash,
            )
            # Compute output directory mirroring CLI flow
            visible = tickers[:3]
            slug = "__".join(visible)
            if len(tickers) > 3:
                slug += f"__plus_{len(tickers) - 3}"
            slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = (
                Path(cfg["results_dir"]).expanduser()
                / "backtest" / slug
                / f"{start_date}_to_{end_date}"
                / timestamp
            )
            save_backtest_result(result, output_dir)
            yield BacktestFinished(output_dir=output_dir)
        except Exception as exc:
            yield BacktestFailed(error=str(exc))


# ---------------------------------------------------------------------------
# Paper trading
# ---------------------------------------------------------------------------

@dataclass
class PaperTradingSnapshot:
    account: dict[str, Any]
    positions: list[dict[str, Any]]
    trades: list[dict[str, Any]]


@dataclass
class OrderResult:
    success: bool
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


class PaperTradingViewModel:
    """Wraps PaperTradingEngine for the TUI."""

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

    def current_user(self) -> str:
        return self.engine.current_user

    def login(self, username: str, password: str) -> bool:
        return self.engine.login(username, password)

    def logout(self) -> str:
        return self.engine.logout()

    def buy(self, ticker: str, quantity: int) -> OrderResult:
        try:
            result = self.engine.buy(ticker, quantity)
            return OrderResult(success=True, message="买入成功", detail=result)
        except Exception as exc:
            return OrderResult(success=False, message=str(exc))

    def sell(self, ticker: str, quantity: int) -> OrderResult:
        try:
            result = self.engine.sell(ticker, quantity)
            return OrderResult(success=True, message="卖出成功", detail=result)
        except Exception as exc:
            return OrderResult(success=False, message=str(exc))
