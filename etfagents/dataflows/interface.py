# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .brave_news import get_news as get_brave_news, get_global_news as get_brave_global_news
from .opencli_news import get_news as get_opencli_news, get_global_news as get_opencli_global_news
from .tushare import (
    get_etf_daily as get_tushare_etf_daily,
    get_etf_holdings as get_tushare_etf_holdings,
    get_etf_indicator as get_tushare_etf_indicator,
    get_etf_info as get_tushare_etf_info,
    get_etf_nav as get_tushare_etf_nav,
    get_etf_share as get_tushare_etf_share,
    get_etf_universe as get_tushare_etf_universe,
    get_stock as get_tushare_stock,
    get_indicator as get_tushare_indicator,
    get_fundamentals as get_tushare_fundamentals,
    get_balance_sheet as get_tushare_balance_sheet,
    get_cashflow as get_tushare_cashflow,
    get_income_statement as get_tushare_income_statement,
    get_insider_transactions as get_tushare_insider_transactions,
    get_broker_reports as get_tushare_broker_reports,
    get_stock_reports as get_tushare_stock_reports,
    _classify_market as classify_tushare_market,
    _normalize_ts_code as normalize_tushare_ticker,
)
from .qlib_local import (
    get_stock as get_qlib_stock,
    get_indicator as get_qlib_indicator,
)
from .exceptions import DataVendorUnavailable

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    "etf_market_data": {
        "description": "ETF OHLCV and technical indicators",
        "tools": [
            "get_etf_price_data",
            "get_etf_indicators",
        ]
    },
    "etf_reference_data": {
        "description": "ETF profile, NAV, holdings, and share changes",
        "tools": [
            "get_etf_info",
            "get_etf_nav",
            "get_etf_holdings",
            "get_etf_share",
            "get_etf_universe",
        ]
    },
    "broker_research": {
        "description": "Industry research reports",
        "tools": [
            "get_broker_research",
        ]
    },
    "stock_research": {
        "description": "Individual stock research reports",
        "tools": [
            "get_stock_research",
        ]
    }
}

VENDOR_LIST = [
    "qlib",
    "yfinance",
    "tushare",
    "brave",
    "opencli",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "qlib": get_qlib_stock,
        "tushare": get_tushare_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "qlib": get_qlib_indicator,
        "tushare": get_tushare_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "tushare": get_tushare_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "tushare": get_tushare_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "tushare": get_tushare_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "tushare": get_tushare_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "opencli": get_opencli_news,
        "brave": get_brave_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "opencli": get_opencli_global_news,
        "brave": get_brave_global_news,
        "yfinance": get_global_news_yfinance,
    },
    "get_insider_transactions": {
        "tushare": get_tushare_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # etf_market_data
    "get_etf_price_data": {
        "tushare": get_tushare_etf_daily,
    },
    "get_etf_indicators": {
        "tushare": get_tushare_etf_indicator,
    },
    # etf_reference_data
    "get_etf_info": {
        "tushare": get_tushare_etf_info,
    },
    "get_etf_nav": {
        "tushare": get_tushare_etf_nav,
    },
    "get_etf_holdings": {
        "tushare": get_tushare_etf_holdings,
    },
    "get_etf_share": {
        "tushare": get_tushare_etf_share,
    },
    "get_etf_universe": {
        "tushare": get_tushare_etf_universe,
    },
    # broker_research
    "get_broker_research": {
        "tushare": get_tushare_broker_reports,
    },
    # stock_research
    "get_stock_research": {
        "tushare": get_tushare_stock_reports,
    },
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

_CHINESE_SUFFIXES = {"SH", "SZ", "BJ", "HK"}

def _is_chinese_ticker(ticker: str) -> bool:
    """Return True for Chinese/HK exchange-qualified tickers (e.g. 601899.SH)."""
    if isinstance(ticker, str) and "." in ticker:
        return ticker.rsplit(".", 1)[-1].upper() in _CHINESE_SUFFIXES
    return False


def is_a_share_ticker(ticker: str) -> bool:
    """Return True when *ticker* maps to an A-share market symbol."""
    if not isinstance(ticker, str) or not ticker.strip():
        return False

    try:
        return classify_tushare_market(normalize_tushare_ticker(ticker)) == "a_share"
    except DataVendorUnavailable:
        return False


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]
    last_error = None

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # For Chinese market tickers, prefer qlib (local) then tushare.
    ticker = args[0] if args else kwargs.get("ticker") or kwargs.get("symbol") or ""
    if _is_chinese_ticker(ticker):
        # Ensure qlib is first if available for this method, then tushare
        for preferred in reversed(["qlib", "tushare"]):
            if preferred in VENDOR_METHODS[method] and preferred not in primary_vendors:
                primary_vendors.insert(0, preferred)
            elif preferred in VENDOR_METHODS[method] and primary_vendors[0] != preferred:
                primary_vendors.remove(preferred)
                primary_vendors.insert(0, preferred)

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except DataVendorUnavailable as exc:
            last_error = exc
            continue  # Try next vendor in fallback chain

    if last_error is not None:
        raise RuntimeError(str(last_error)) from last_error

    raise RuntimeError(f"No available vendor for '{method}'")
