from etfagents.agents import (
    create_etf_industry_research_analyst,
    create_etf_market_analyst,
    create_etf_stock_research_analyst,
    create_etf_structure_analyst,
)

from .setup import GraphSetup


class ETFGraphSetup(GraphSetup):
    """ETF-specific workflow assembly on top of the shared LangGraph skeleton."""

    DEFAULT_SELECTED_ANALYSTS = (
        "market_flow",
        "catalyst_sentiment",
        "macro_regime",
        "meso_commodity",
        "holdings_industry",
        "top_holdings",
    )
    ANALYST_BUILDERS = {
        **GraphSetup.ANALYST_BUILDERS,
        "market_flow": create_etf_market_analyst,
        "catalyst_sentiment": GraphSetup.ANALYST_BUILDERS["social"],
        "macro_regime": GraphSetup.ANALYST_BUILDERS["news"],
        "meso_commodity": create_etf_structure_analyst,
        "holdings_industry": create_etf_industry_research_analyst,
        "top_holdings": create_etf_stock_research_analyst,
        "market": create_etf_market_analyst,
        "etf_structure": create_etf_structure_analyst,
        "broker_research": create_etf_industry_research_analyst,
        "stock_research": create_etf_stock_research_analyst,
        "etf_macro": create_etf_industry_research_analyst,
    }
    _ANALYST_DISPLAY_NAMES = {
        **GraphSetup._ANALYST_DISPLAY_NAMES,
        "market_flow": "Market & Flow",
        "catalyst_sentiment": "Sentiment & Catalyst",
        "macro_regime": "Macro Regime",
        "meso_commodity": "Meso Commodity",
        "holdings_industry": "ETF Holdings-Industry Research",
        "top_holdings": "ETF Top Holdings Research",
        "market": "Market & Flow",
        "news": "Macro Regime",
        "etf_structure": "Meso Commodity",
        "broker_research": "ETF Holdings-Industry Research",
        "stock_research": "ETF Top Holdings Research",
        "etf_macro": "ETF Holdings-Industry Research",
    }
    _CLEAR_ROUTE_ALIASES = {
        **GraphSetup._CLEAR_ROUTE_ALIASES,
        "market": ("Msg Clear Market", "Msg Clear Market Flow", "Msg Clear ETF Flow"),
        "broker_research": ("Msg Clear Industry Research", "Msg Clear Holdings-Industry Research", "Msg Clear ETF Industry Research"),
        "stock_research": ("Msg Clear Stock Research", "Msg Clear Top Holdings Research", "Msg Clear ETF Top Holdings Research"),
    }
