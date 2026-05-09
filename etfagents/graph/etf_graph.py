import copy
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

    def analyze_candidate_pool(self, tickers: list[str], trade_date: str) -> list[dict[str, object]]:
        """Analyze a candidate pool sequentially and rank it by final allocation rating."""
        results: list[dict[str, object]] = []
        for ticker in tickers:
            final_state, rating = self.propagate(ticker, trade_date)
            results.append(
                {
                    "ticker": ticker,
                    "rating": rating,
                    "score": str(self._RATING_SCORE.get(rating, 0)),
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
                }
            )
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
        return ranked

    def replay_candidate_pool(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
        rebalance_interval_days: int = 21,
        top_k: int = 3,
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
            price_loader=price_loader,
        )
