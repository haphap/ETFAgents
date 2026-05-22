"""Non-UI services used by the Textual TUI."""

from __future__ import annotations

import copy
import csv
import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from etfagents.default_config import DEFAULT_CONFIG


ANALYST_KEYS = [
    "market_flow",
    "catalyst_sentiment",
    "macro_regime",
    "meso_commodity",
    "holdings_industry",
    "top_holdings",
]


@dataclass(frozen=True)
class SectionDefinition:
    key: str
    team: str
    title: str
    path_candidates: tuple[str, ...]


SECTION_DEFINITIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition("market_flow_report", "分析师团队", "市场与资金流", ("reports/market_flow_report.md", "1_analysts/market_flow.md")),
    SectionDefinition("catalyst_sentiment_report", "分析师团队", "舆情与事件", ("reports/catalyst_sentiment_report.md", "1_analysts/catalyst_sentiment.md")),
    SectionDefinition("macro_regime_report", "分析师团队", "宏观框架", ("reports/macro_regime_report.md", "1_analysts/macro_regime.md")),
    SectionDefinition("meso_commodity_report", "分析师团队", "中观大宗商品", ("reports/meso_commodity_report.md", "1_analysts/meso_commodity.md")),
    SectionDefinition("holdings_industry_report", "分析师团队", "持仓行业", ("reports/holdings_industry_report.md", "1_analysts/holdings_industry.md")),
    SectionDefinition("top_holdings_report", "分析师团队", "头部持仓", ("reports/top_holdings_report.md", "1_analysts/top_holdings.md")),
    SectionDefinition("bull", "研究团队", "多头", ("2_research/bull.md",)),
    SectionDefinition("bear", "研究团队", "空头", ("2_research/bear.md",)),
    SectionDefinition("research_manager", "研究团队", "研究经理综合结论", ("2_research/manager.md", "2_research/rounds.md", "reports/research_allocation_plan.md")),
    SectionDefinition("trader_logic", "交易员", "配置逻辑", ("3_trading/trader.md", "reports/trader_allocation_plan.md")),
    SectionDefinition("trader_execution", "交易员", "配置执行计划", ("3_trading/trader.md", "reports/trader_allocation_plan.md")),
    SectionDefinition("trader_rebalance", "交易员", "再平衡与风险控制", ("3_trading/trader.md", "reports/trader_allocation_plan.md")),
    SectionDefinition("trader_bias", "交易员", "执行倾向", ("3_trading/trader.md", "reports/trader_allocation_plan.md")),
    SectionDefinition("aggressive", "风险管理", "激进", ("4_risk/aggressive.md",)),
    SectionDefinition("neutral", "风险管理", "中性", ("4_risk/neutral.md",)),
    SectionDefinition("conservative", "风险管理", "保守", ("4_risk/conservative.md",)),
    SectionDefinition("portfolio_manager", "风险管理", "投资组合经理", ("5_portfolio/decision.md", "reports/final_allocation_decision.md")),
    SectionDefinition("final_allocation_decision", "结论", "最终组合经理决策", ("5_portfolio/decision.md", "reports/final_allocation_decision.md")),
)


STREAM_SECTION_KEYS = {
    "market_flow_report",
    "catalyst_sentiment_report",
    "macro_regime_report",
    "meso_commodity_report",
    "holdings_industry_report",
    "top_holdings_report",
    "trader_allocation_plan",
    "final_allocation_decision",
}


@dataclass
class ReportRecord:
    ticker: str
    date: str
    path: Path
    rating: str | None = None
    sections: dict[str, Path] = field(default_factory=dict)


class ReportRepository:
    """Scan and read locally saved single-ETF reports."""

    def __init__(self, results_dir: str | Path | None = None):
        self.results_dir = Path(results_dir or DEFAULT_CONFIG["results_dir"]).expanduser()

    def list_reports(self) -> list[ReportRecord]:
        if not self.results_dir.exists():
            return []
        records: list[ReportRecord] = []
        for ticker_dir in sorted(self.results_dir.iterdir()):
            if not ticker_dir.is_dir() or ticker_dir.name.startswith("_") or ticker_dir.name == "backtest":
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
        return sorted(records, key=lambda item: (item.ticker, item.date), reverse=True)

    def latest_by_ticker(self) -> list[ReportRecord]:
        latest: dict[str, ReportRecord] = {}
        for record in self.list_reports():
            if record.ticker not in latest or record.date > latest[record.ticker].date:
                latest[record.ticker] = record
        return sorted(latest.values(), key=lambda item: item.ticker)

    def dates_for_ticker(self, ticker: str) -> list[ReportRecord]:
        return [record for record in self.list_reports() if record.ticker == ticker]

    def read_section(self, record: ReportRecord, section_key: str) -> str:
        section_path = record.sections.get(section_key)
        if section_path and section_path.exists():
            return section_path.read_text(encoding="utf-8")
        complete = record.path / "complete_report.md"
        return complete.read_text(encoding="utf-8") if complete.exists() else ""

    def _discover_sections(self, report_dir: Path) -> dict[str, Path]:
        sections: dict[str, Path] = {}
        for definition in SECTION_DEFINITIONS:
            for relative in definition.path_candidates:
                candidate = report_dir / relative
                if candidate.exists():
                    sections[definition.key] = candidate
                    break
        return sections

    def _extract_rating(self, complete_report: Path) -> str | None:
        text = complete_report.read_text(encoding="utf-8")
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


@dataclass
class AnalysisEvent:
    event_type: str
    ticker: str
    status: str | None = None
    section: str | None = None
    content: str | None = None
    current_agent: str | None = None
    completed_sections: int | None = None
    total_sections: int | None = None
    error: str | None = None
    report_path: Path | None = None


class AnalysisRunner:
    """Sequentially run ETF analysis and expose UI-friendly events."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        graph_factory: Callable[..., Any] | None = None,
    ):
        self.config = copy.deepcopy(config or DEFAULT_CONFIG)
        self.graph_factory = graph_factory

    def run_queue(
        self,
        tickers: Iterable[str],
        analysis_date: str | None = None,
        selected_analysts: Iterable[str] | None = None,
    ) -> Iterator[AnalysisEvent]:
        date = analysis_date or _dt.date.today().isoformat()
        analysts = list(selected_analysts or ANALYST_KEYS)
        normalized = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
        for ticker in normalized:
            yield from self.run_one(ticker, date, analysts)

    def run_one(
        self,
        ticker: str,
        analysis_date: str,
        selected_analysts: Iterable[str],
    ) -> Iterator[AnalysisEvent]:
        graph = self._make_graph()
        report_dir = Path(self.config["results_dir"]).expanduser() / ticker / analysis_date / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        total_sections = len(STREAM_SECTION_KEYS)
        completed: set[str] = set()
        yield AnalysisEvent("ticker_started", ticker, status="分析中", total_sections=total_sections, completed_sections=0)
        try:
            cli_main = self._cli_main()
            init_state, args, _resumed = graph.prepare_run(ticker, analysis_date)
            accumulated = copy.deepcopy(init_state)
            for chunk in graph.graph.stream(init_state, **args):
                self._merge_stream_state(accumulated, chunk, cli_main)
                for section, content in self._section_updates(chunk, cli_main):
                    if not content:
                        continue
                    completed.add(section)
                    self._write_live_section(report_dir, section, content)
                    yield AnalysisEvent(
                        "section_update",
                        ticker,
                        status="生成中",
                        section=section,
                        content=content,
                        completed_sections=len(completed),
                        total_sections=total_sections,
                    )
                current_agent = self._current_agent_from_chunk(chunk)
                if current_agent:
                    yield AnalysisEvent("agent_update", ticker, current_agent=current_agent)
            graph.finalize_run(analysis_date, accumulated)
            report_path = self._save_report(cli_main, accumulated, ticker, Path(self.config["results_dir"]).expanduser() / ticker / analysis_date)
            yield AnalysisEvent(
                "ticker_done",
                ticker,
                status="完成",
                completed_sections=len(completed),
                total_sections=total_sections,
                report_path=report_path,
            )
        except Exception as exc:
            yield AnalysisEvent("ticker_error", ticker, status="失败", error=str(exc))
        finally:
            close_run = getattr(graph, "close_run", None)
            if callable(close_run):
                close_run()

    def _make_graph(self) -> Any:
        if self.graph_factory is not None:
            return self.graph_factory(config=self.config, debug=False)
        from etfagents.graph.etf_graph import EtfAgentsGraph

        return EtfAgentsGraph(config=self.config, debug=False)

    def _cli_main(self) -> Any:
        try:
            import cli.main as cli_main

            return cli_main
        except ModuleNotFoundError:
            return None

    def _merge_stream_state(self, accumulated: dict[str, Any], chunk: dict[str, Any], cli_main: Any) -> None:
        if cli_main is not None and hasattr(cli_main, "_merge_stream_state"):
            cli_main._merge_stream_state(accumulated, chunk)
            return
        for key, value in chunk.items():
            if isinstance(value, dict) and isinstance(accumulated.get(key), dict):
                accumulated[key].update(value)
            else:
                accumulated[key] = value

    def _section_updates(self, chunk: dict[str, Any], cli_main: Any) -> Iterator[tuple[str, str]]:
        for section in STREAM_SECTION_KEYS:
            value = self._get_state_value(cli_main, chunk, section, "")
            if value:
                yield section, str(value)
        debate = chunk.get("investment_debate_state")
        if debate:
            formatted = (
                cli_main.format_research_team_history(debate)
                if cli_main is not None and hasattr(cli_main, "format_research_team_history")
                else self._format_research_team_history(debate)
            )
            if formatted:
                yield "research_allocation_plan", formatted
        risk = chunk.get("risk_debate_state")
        if risk:
            formatted = (
                cli_main.format_risk_management_history(risk, include_manager=False)
                if cli_main is not None and hasattr(cli_main, "format_risk_management_history")
                else self._format_risk_management_history(risk)
            )
            if formatted:
                yield "risk_management_plan", formatted
            judge = risk.get("judge_decision")
            if judge:
                if cli_main is not None and hasattr(cli_main, "_format_manager_decision"):
                    yield "final_allocation_decision", cli_main._format_manager_decision(
                        judge,
                        risk.get("judge_snapshot_path", ""),
                        show_snapshot_summary=False,
                    )
                else:
                    yield "final_allocation_decision", str(judge)

    def _get_state_value(self, cli_main: Any, state: dict[str, Any], key: str, default: Any) -> Any:
        if cli_main is not None and hasattr(cli_main, "get_state_value"):
            return cli_main.get_state_value(state, key, default)
        return state.get(key, default)

    def _format_research_team_history(self, debate: dict[str, Any]) -> str:
        parts = []
        if debate.get("bull_history"):
            parts.append(f"### 多头\n{debate['bull_history']}")
        if debate.get("bear_history"):
            parts.append(f"### 空头\n{debate['bear_history']}")
        if debate.get("judge_decision"):
            parts.append(f"### 研究经理综合结论\n{debate['judge_decision']}")
        return "\n\n".join(parts)

    def _format_risk_management_history(self, risk: dict[str, Any]) -> str:
        parts = []
        if risk.get("aggressive_history"):
            parts.append(f"### 激进\n{risk['aggressive_history']}")
        if risk.get("neutral_history"):
            parts.append(f"### 中性\n{risk['neutral_history']}")
        if risk.get("conservative_history"):
            parts.append(f"### 保守\n{risk['conservative_history']}")
        return "\n\n".join(parts)

    def _save_report(self, cli_main: Any, final_state: dict[str, Any], ticker: str, save_path: Path) -> Path:
        if cli_main is not None and hasattr(cli_main, "save_report_to_disk"):
            return cli_main.save_report_to_disk(final_state, ticker, save_path)
        save_path.mkdir(parents=True, exist_ok=True)
        parts = [f"# ETF配置分析报告: {ticker}"]
        for section in STREAM_SECTION_KEYS:
            content = final_state.get(section)
            if content:
                parts.append(f"## {section}\n{content}")
        debate = final_state.get("investment_debate_state") or {}
        research = self._format_research_team_history(debate)
        if research:
            parts.append(f"## research_allocation_plan\n{research}")
        risk = final_state.get("risk_debate_state") or {}
        risk_text = self._format_risk_management_history(risk)
        if risk_text:
            parts.append(f"## risk_management_plan\n{risk_text}")
        if risk.get("judge_decision"):
            parts.append(f"## final_allocation_decision\n{risk['judge_decision']}")
        report_path = save_path / "complete_report.md"
        report_path.write_text("\n\n".join(parts), encoding="utf-8")
        return report_path

    def _write_live_section(self, report_dir: Path, section: str, content: str) -> None:
        (report_dir / f"{section}.md").write_text(str(content), encoding="utf-8")

    def _current_agent_from_chunk(self, chunk: dict[str, Any]) -> str | None:
        for key in ("current_agent", "agent", "sender"):
            value = chunk.get(key)
            if value:
                return str(value)
        return None


@dataclass
class BacktestViewModel:
    output_dir: Path
    summary: str
    metrics: dict[str, Any]
    nav: list[dict[str, str]]
    orders: list[dict[str, str]]
    trades: list[dict[str, str]]
    sparkline: str


class BacktestRunner:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        graph_factory: Callable[..., Any] | None = None,
        save_result: Callable[[Any, str | Path], Path] | None = None,
    ):
        self.config = copy.deepcopy(config or DEFAULT_CONFIG)
        self.graph_factory = graph_factory
        self.save_result = save_result

    def run(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        rebalance_interval_days: int = 20,
        top_k: int = 3,
    ) -> BacktestViewModel:
        cli_main = self._cli_main()
        graph = self._make_graph()
        output_dir = cli_main._default_backtest_output_dir(self.config, tickers, start_date, end_date)
        result = graph.backtest_candidate_pool(
            tickers,
            start_date,
            end_date,
            rebalance_interval_days=rebalance_interval_days,
            top_k=top_k,
        )
        saver = self.save_result or cli_main.save_backtest_result
        saved_dir = saver(result, output_dir)
        return self.load(saved_dir)

    def load(self, output_dir: str | Path) -> BacktestViewModel:
        path = Path(output_dir)
        summary_path = path / "summary.md"
        metrics_path = path / "metrics.json"
        nav = self._read_csv(path / "nav.csv")
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
        return BacktestViewModel(
            output_dir=path,
            summary=summary_path.read_text(encoding="utf-8") if summary_path.exists() else "",
            metrics=metrics,
            nav=nav,
            orders=self._read_csv(path / "orders.csv"),
            trades=self._read_csv(path / "trades.csv"),
            sparkline=self._sparkline(nav),
        )

    def latest_result(self) -> BacktestViewModel | None:
        root = Path(self.config["results_dir"]).expanduser() / "backtest"
        if not root.exists():
            return None
        candidates = [path for path in root.glob("**/metrics.json") if path.is_file()]
        if not candidates:
            return None
        latest_metrics = max(candidates, key=lambda path: path.stat().st_mtime)
        return self.load(latest_metrics.parent)

    def _make_graph(self) -> Any:
        if self.graph_factory is not None:
            return self.graph_factory(config=self.config, debug=False)
        from etfagents.graph.etf_graph import EtfAgentsGraph

        return EtfAgentsGraph(config=self.config, debug=False)

    def _cli_main(self) -> Any:
        import cli.main as cli_main

        return cli_main

    def _read_csv(self, path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _sparkline(self, nav: list[dict[str, str]]) -> str:
        values: list[float] = []
        for row in nav:
            raw = row.get("value") or row.get("nav") or row.get("total_value") or row.get("portfolio_value")
            try:
                values.append(float(raw))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        if not values:
            return ""
        ticks = "▁▂▃▄▅▆▇█"
        low = min(values)
        high = max(values)
        if high == low:
            return ticks[0] * len(values)
        return "".join(ticks[int((value - low) / (high - low) * (len(ticks) - 1))] for value in values)


@dataclass
class PaperTradingSnapshot:
    account: dict[str, Any]
    positions: list[dict[str, Any]]
    trades: list[dict[str, Any]]


class PaperTradingViewModel:
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

    def buy(self, ticker: str, quantity: int, user_id: str | None = None, analysis_id: str | None = None) -> dict[str, Any]:
        return self.engine.buy(ticker, quantity, user_id=user_id, analysis_id=analysis_id)

    def sell(self, ticker: str, quantity: int, user_id: str | None = None, analysis_id: str | None = None) -> dict[str, Any]:
        return self.engine.sell(ticker, quantity, user_id=user_id, analysis_id=analysis_id)
