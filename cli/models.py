from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel


class AnalystType(str, Enum):
    MARKET_FLOW = "market_flow"
    CATALYST_SENTIMENT = "catalyst_sentiment"
    MACRO_REGIME = "macro_regime"
    MESO_COMMODITY = "meso_commodity"
    HOLDINGS_INDUSTRY = "holdings_industry"
    TOP_HOLDINGS = "top_holdings"

    MARKET = "market_flow"
    SOCIAL = "catalyst_sentiment"
    NEWS = "macro_regime"
    ETF_STRUCTURE = "meso_commodity"
    ETF_FLOW = "market_flow"
    ETF_MACRO = "holdings_industry"
    FUNDAMENTALS = "meso_commodity"
    BROKER_RESEARCH = "holdings_industry"
    STOCK_RESEARCH = "top_holdings"
