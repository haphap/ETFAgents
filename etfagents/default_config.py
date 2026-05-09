import os

_ETFAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".etfagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv(
        "ETFAGENTS_RESULTS_DIR",
        os.getenv(
            "TRADINGAGENTS_RESULTS_DIR",
            os.path.join(_ETFAGENTS_HOME, "logs"),
        ),
    ),
    "data_cache_dir": os.getenv(
        "ETFAGENTS_CACHE_DIR",
        os.getenv(
            "TRADINGAGENTS_CACHE_DIR",
            os.path.join(_ETFAGENTS_HOME, "cache"),
        ),
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "report_context_char_limit": 16000,
    "debate_history_char_limit": 12000,
    "memory_min_similarity": 0.15,
    "benchmark_ticker": os.getenv(
        "ETFAGENTS_BENCHMARK_TICKER",
        os.getenv("TRADINGAGENTS_BENCHMARK_TICKER"),
    ),
    "checkpoint_enabled": False,
    "memory_log_path": os.path.join(
        os.getenv("ETFAGENTS_RESULTS_DIR", os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")),
        "trading_memory.md",
    ),
    "memory_log_max_entries": None,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "qlib,tushare,yfinance",       # Options: qlib, tushare, yfinance
        "technical_indicators": "qlib,tushare,yfinance",  # Options: qlib, tushare, yfinance
        "fundamental_data": "tushare,yfinance",           # Options: tushare, yfinance
        "news_data": "opencli,brave,yfinance",            # Options: opencli, brave, yfinance
        "etf_market_data": "tushare",                     # Options: tushare
        "etf_reference_data": "tushare",                  # Options: tushare
        "broker_research": "tushare",                     # Options: tushare (A-share only)
        "stock_research": "tushare",                      # Options: tushare (A-share only)
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        "get_stock_data": "qlib,tushare",
        "get_indicators": "qlib,tushare",
        "get_fundamentals": "tushare",
        "get_balance_sheet": "tushare",
        "get_cashflow": "tushare",
        "get_income_statement": "tushare",
        "get_news": "opencli",
        "get_global_news": "opencli",
        "get_insider_transactions": "tushare,yfinance",
        "get_etf_price_data": "tushare",
        "get_etf_indicators": "tushare",
        "get_etf_info": "tushare",
        "get_etf_nav": "tushare",
        "get_etf_holdings": "tushare",
        "get_etf_share": "tushare",
        "get_etf_universe": "tushare",
        "get_broker_research": "tushare",
        "get_stock_research": "tushare",
    },
}
