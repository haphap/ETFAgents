import copy
import re
from typing import Any, Dict

from langgraph.prebuilt import ToolNode

from etfagents.agents.utils.agent_utils import (
    get_etf_holdings,
    get_etf_info,
    get_commodity_cluster_data,
    get_etf_indicators,
    get_etf_industry_research,
    get_etf_nav,
    get_etf_price_data,
    get_etf_share,
    get_etf_top_holdings_research,
    get_etf_universe,
    get_macro_regime_data,
    get_global_news,
    get_news,
)
from etfagents.agents.utils.state_keys import get_state_value
from etfagents.agents.utils.report_leads import strip_refine_preamble
from etfagents.backtest.signals import (
    build_candidate_backtest_signal,
    build_state_backtest_signal,
)
from etfagents.backtest.cache import BacktestSignalStore
from etfagents.backtest.backtrader_engine import (
    BacktraderBacktestResult,
    run_candidate_pool_backtest,
)
from etfagents.default_config import DEFAULT_CONFIG

from .replay import ReplayResult, run_candidate_pool_replay
from .etf_setup import ETFGraphSetup
from .trading_graph import TradingAgentsGraph


ETF_DEFAULT_CONFIG = copy.deepcopy(DEFAULT_CONFIG)
ETF_DEFAULT_CONFIG["data_vendors"].update(
    {
        "etf_market_data": "tushare",
        "etf_reference_data": "tushare",
    }
)
ETF_DEFAULT_CONFIG["tool_vendors"].update(
    {
        "get_etf_price_data": "tushare",
        "get_etf_indicators": "tushare",
        "get_etf_info": "tushare",
        "get_etf_nav": "tushare",
        "get_etf_holdings": "tushare",
        "get_etf_share": "tushare",
        "get_etf_universe": "tushare",
    }
)

_CANDIDATE_PAYLOAD_TEXT_SUFFIXES = ("_report", "_plan", "_decision")
_SELECTED_ANALYST_REPORT_KEYS = {
    "market_flow": "market_flow_report",
    "catalyst_sentiment": "catalyst_sentiment_report",
    "macro_regime": "macro_regime_report",
    "meso_commodity": "meso_commodity_report",
    "holdings_industry": "holdings_industry_report",
    "top_holdings": "top_holdings_report",
    "market": "market_flow_report",
    "social": "catalyst_sentiment_report",
    "news": "macro_regime_report",
    "etf_structure": "meso_commodity_report",
    "broker_research": "holdings_industry_report",
    "stock_research": "top_holdings_report",
    "etf_flow": "market_flow_report",
    "etf_macro": "holdings_industry_report",
}
_LEADING_CANDIDATE_PROCESS_RE = re.compile(
    r"^\s*(?:"
    r"(?:报告|内容).{0,12}(?:已|已经)?(?:就绪|完成|生成|整理好|准备好)[。！!；;，,]?\s*(?:以下|下面|现在|接下来|下一步)"
    r"|(?:数据|资料|信息).{0,12}?(?:已经|已)?(?:全部)?(?:获取|收集|整理|拿到|完成)(?:完毕)?[。！!；;，,]?\s*(?:以下|下面|现在|接下来|下一步)"
    r"|以下(?:是|为)"
    r")"
)


def _looks_like_candidate_process_opening(opening: str) -> bool:
    return bool(
        opening
        and len(opening) <= 200
        and len(opening.splitlines()) <= 2
        and not re.search(r"(?m)^\s*(?:#|\||[一二三四五六七八九十]+、|（[一二三四五六七八九十\d]+）)", opening)
        and not re.search(r"\d|[%％]", opening)
        and _LEADING_CANDIDATE_PROCESS_RE.match(opening)
    )


def _sanitize_candidate_payload_text(text: str) -> str:
    normalized_original = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    original_paragraphs = re.split(r"\n\s*\n", normalized_original, maxsplit=1)
    if len(original_paragraphs) == 2 and _looks_like_candidate_process_opening(original_paragraphs[0].strip()):
        return strip_refine_preamble(original_paragraphs[1]).strip()

    cleaned = strip_refine_preamble(text).strip()
    if not cleaned:
        return ""

    normalized = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n\s*\n", normalized, maxsplit=1)
    opening = paragraphs[0].strip()
    if len(paragraphs) == 2 and _looks_like_candidate_process_opening(opening):
        return paragraphs[1].strip()
    return cleaned


def _sanitize_candidate_payload(payload: dict[str, object]) -> dict[str, object]:
    sanitized = dict(payload)
    for key, value in tuple(sanitized.items()):
        if isinstance(value, str) and key.endswith(_CANDIDATE_PAYLOAD_TEXT_SUFFIXES):
            sanitized[key] = _sanitize_candidate_payload_text(value)
    signal = sanitized.get("backtest_signal")
    if isinstance(signal, dict):
        snapshot = signal.get("signal_text_snapshot")
        if isinstance(snapshot, str):
            signal = dict(signal)
            signal["signal_text_snapshot"] = _sanitize_candidate_payload_text(snapshot)
            sanitized["backtest_signal"] = signal
    return sanitized


def _selected_analyst_report_keys(selected_analysts: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    keys = [
        _SELECTED_ANALYST_REPORT_KEYS[analyst]
        for analyst in selected_analysts
        if analyst in _SELECTED_ANALYST_REPORT_KEYS
    ]
    return tuple(dict.fromkeys(keys))


def _has_missing_selected_reports(
    payload: dict[str, object],
    expected_report_keys: tuple[str, ...],
) -> bool:
    for key in expected_report_keys:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            return True
    return False


def _cacheable_candidate_payload(
    payload: dict[str, object],
    expected_report_keys: tuple[str, ...],
) -> dict[str, object]:
    cacheable = dict(payload)
    for key, value in tuple(cacheable.items()):
        if key.endswith("_report") and isinstance(value, str) and not value.strip():
            cacheable.pop(key, None)
    return cacheable


class EtfAgentsGraph(TradingAgentsGraph):
    """ETF-oriented graph that reuses the shared execution/runtime infrastructure."""

    A_SHARE_ONLY_ANALYSTS: tuple[str, ...] = ()
    DEFAULT_SELECTED_ANALYSTS = ETFGraphSetup.DEFAULT_SELECTED_ANALYSTS
    DEFAULT_GRAPH_CONFIG = ETF_DEFAULT_CONFIG
    GRAPH_SETUP_CLASS = ETFGraphSetup
    _RATING_SCORE = {
        "BUY": 5,
        "OVERWEIGHT": 4,
        "HOLD": 3,
        "UNDERWEIGHT": 2,
        "SELL": 1,
    }

    @classmethod
    def resolve_selected_analysts(
        cls,
        selected_analysts: list[str],
        ticker: str,
    ) -> tuple[list[str], list[str]]:
        aliases = {
            "market": "market_flow",
            "social": "catalyst_sentiment",
            "news": "macro_regime",
            "etf_structure": "meso_commodity",
            "broker_research": "holdings_industry",
            "stock_research": "top_holdings",
            "etf_flow": "market_flow",
            "etf_macro": "holdings_industry",
        }
        normalized = [aliases.get(analyst, analyst) for analyst in selected_analysts]
        return list(dict.fromkeys(normalized)), []

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        return {
            "market_flow": ToolNode([get_etf_price_data, get_etf_indicators, get_etf_share, get_etf_nav, get_etf_universe]),
            "catalyst_sentiment": ToolNode([get_etf_info, get_etf_holdings, get_news, get_global_news]),
            "macro_regime": ToolNode([get_etf_info, get_etf_holdings, get_macro_regime_data, get_global_news, get_news]),
            "meso_commodity": ToolNode([get_commodity_cluster_data]),
            "holdings_industry": ToolNode([get_etf_holdings, get_etf_industry_research]),
            "top_holdings": ToolNode([get_etf_holdings, get_etf_top_holdings_research]),
            "market": ToolNode([get_etf_price_data, get_etf_indicators, get_etf_share, get_etf_nav, get_etf_universe]),
            "social": ToolNode([get_etf_info, get_etf_holdings, get_news, get_global_news]),
            "news": ToolNode([get_etf_info, get_etf_holdings, get_macro_regime_data, get_global_news, get_news]),
            "etf_structure": ToolNode([get_commodity_cluster_data]),
            "broker_research": ToolNode([get_etf_holdings, get_etf_industry_research]),
            "stock_research": ToolNode([get_etf_holdings, get_etf_top_holdings_research]),
            "etf_macro": ToolNode([get_etf_holdings, get_etf_industry_research]),
        }

    def analyze_candidate_pool(
        self,
        tickers: list[str],
        trade_date: str,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, object]]:
        """Analyze a candidate pool sequentially and rank it by final allocation rating."""
        results: list[dict[str, object]] = []
        selected_report_keys = _selected_analyst_report_keys(
            getattr(self, "selected_analysts", self.DEFAULT_SELECTED_ANALYSTS)
        )
        for ticker in tickers:
            memory_signature = None
            if getattr(self, "config", {}).get("memory_in_backtest"):
                store = getattr(self, "analysis_memory_store", None)
                if store is not None:
                    memory_signature = store.memory_signature(ticker, trade_date)
            cache = BacktestSignalStore(
                getattr(self, "config", self.DEFAULT_GRAPH_CONFIG),
                getattr(self, "selected_analysts", self.DEFAULT_SELECTED_ANALYSTS),
                force_refresh=force_refresh,
                memory_signature=memory_signature,
            )
            cached = cache.get(ticker, trade_date)
            if cached is not None:
                cached_payload = _sanitize_candidate_payload(dict(cached))
                if not _has_missing_selected_reports(cached_payload, selected_report_keys):
                    results.append(cached_payload)
                    continue
            final_state, rating = self.propagate(ticker, trade_date)
            result = {
                "ticker": ticker,
                "rating": rating,
                "score": str(self._RATING_SCORE.get(rating, 0)),
                "market_flow_report": get_state_value(
                    final_state,
                    "market_flow_report",
                    "",
                ),
                "catalyst_sentiment_report": get_state_value(
                    final_state,
                    "catalyst_sentiment_report",
                    "",
                ),
                "macro_regime_report": get_state_value(
                    final_state,
                    "macro_regime_report",
                    "",
                ),
                "meso_commodity_report": get_state_value(
                    final_state,
                    "meso_commodity_report",
                    "",
                ),
                "holdings_industry_report": get_state_value(
                    final_state,
                    "holdings_industry_report",
                    "",
                ),
                "top_holdings_report": get_state_value(
                    final_state,
                    "top_holdings_report",
                    "",
                ),
                "research_allocation_plan": get_state_value(
                    final_state,
                    "research_allocation_plan",
                    "",
                ),
                "trader_allocation_plan": get_state_value(
                    final_state,
                    "trader_allocation_plan",
                    "",
                ),
                "final_allocation_decision": get_state_value(
                    final_state,
                    "final_allocation_decision",
                    "",
                ),
                "backtest_signal": build_state_backtest_signal(
                    final_state,
                    default_ticker=ticker,
                    default_trade_date=trade_date,
                ),
            }
            result = _sanitize_candidate_payload(result)
            cache.put(
                ticker,
                trade_date,
                _cacheable_candidate_payload(result, selected_report_keys),
            )
            results.append(result)
        ranked = sorted(
            results,
            key=lambda item: (-int(item["score"]), item["ticker"]),
        )
        total_conviction = sum(max(int(item["score"]) - 2, 0) for item in ranked)
        for item in ranked:
            conviction = max(int(item["score"]) - 2, 0)
            item["suggested_weight_pct"] = (
                round(conviction / total_conviction * 100, 1) if total_conviction else 0.0
            )
            item["backtest_signal"] = build_candidate_backtest_signal(
                item,
                trade_date,
            )
        return ranked

    def replay_candidate_pool(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        rebalance_interval_days: int = 21,
        top_k: int = 3,
        execution_timing: str = "same_close",
        force_refresh: bool = False,
        price_loader=None,
    ) -> ReplayResult:
        """Replay ranked ETF allocation decisions across historical rebalance windows."""
        return run_candidate_pool_replay(
            self,
            tickers,
            start_date,
            end_date,
            rebalance_interval_days=rebalance_interval_days,
            top_k=top_k,
            execution_timing=execution_timing,
            force_refresh=force_refresh,
            price_loader=price_loader,
        )

    def backtest_candidate_pool(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        rebalance_interval_days: int = 21,
        top_k: int = 3,
        execution_timing: str = "same_close",
        initial_cash: float = 1_000_000.0,
        commission: float = 0.0,
        slippage_perc: float = 0.0,
        cash_buffer_pct: float = 0.0,
        benchmark_tickers: list[str] | None = None,
        force_refresh: bool = False,
        price_loader=None,
    ) -> BacktraderBacktestResult:
        """Run a formal Backtrader backtest over ranked ETF candidate-pool decisions."""
        return run_candidate_pool_backtest(
            self,
            tickers,
            start_date,
            end_date,
            rebalance_interval_days=rebalance_interval_days,
            top_k=top_k,
            execution_timing=execution_timing,
            initial_cash=initial_cash,
            commission=commission,
            slippage_perc=slippage_perc,
            cash_buffer_pct=cash_buffer_pct,
            benchmark_tickers=benchmark_tickers,
            force_refresh=force_refresh,
            price_loader=price_loader,
        )
