from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_indicators,
    get_etf_nav,
    get_etf_price_data,
    get_etf_share,
    get_etf_universe,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain


_ETF_MARKET_INDICATORS = {
    "close_10_ema": "short-term trend and pullback timing",
    "close_20_sma": "common moving-average baseline behind generic 'MA' requests",
    "close_50_sma": "intermediate trend confirmation and support/resistance",
    "close_200_sma": "long-term regime assessment",
    "macd": "momentum direction",
    "macds": "MACD signal-line confirmation",
    "macdh": "momentum acceleration / deceleration",
    "rsi": "overbought / oversold context",
    "boll": "Bollinger middle-band mean-reversion context",
    "boll_ub": "upper volatility boundary",
    "boll_lb": "lower volatility boundary",
    "atr": "volatility and stop-distance calibration",
    "vwma": "price-volume confirmation",
}


def _etf_indicator_catalog() -> str:
    return "\n".join(
        f"- {indicator}: {purpose}" for indicator, purpose in _ETF_MARKET_INDICATORS.items()
    )


def create_etf_market_analyst(llm):
    def etf_market_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(get_asset_symbol(state))

        tools = [get_etf_price_data, get_etf_indicators, get_etf_share, get_etf_nav, get_etf_universe]

        system_message = (
            "You are an ETF market and flow analyst focused on entry timing, liquidity, and implementation quality."
            " Build a combined technical-and-flow report for the target ETF using price action, moving averages, momentum,"
            " volatility, share changes, NAV clues, and execution depth.\n\n"
            "You should normally pull 3-6 months of ETF price history and explicitly cover:\n"
            "1. Trend regime (10 EMA / 20 SMA / 50 SMA / 200 SMA comparisons when available)\n"
            "2. Momentum (MACD, signal line, histogram, RSI)\n"
            "3. Volatility and risk boundaries (Bollinger bands, ATR)\n"
            "4. Flow and liquidity confirmation (share change, NAV / premium-discount clues, VWMA, turnover)\n"
            "5. Whether flow confirms or contradicts the chart setup\n"
            "6. Actionable implementation levels for add / hold / reduce / wait decisions\n\n"
            "When using `get_etf_indicators`, you must call the tool with the exact supported indicator IDs below."
            " Do not use generic aliases such as `MA`, `SMA`, `EMA`, or natural-language indicator names unless they"
            " exactly match one of these tool parameters:\n"
            f"{_etf_indicator_catalog()}\n\n"
            "If you need a generic moving-average baseline, use `close_20_sma` rather than `MA`.\n\n"
            "The final report must explain what current readings imply for ETF allocation timing and whether capital is accumulating, distributing, or crowding the product."
            " End with a compact markdown summary table."
            + get_language_instruction()
        )

        prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a helpful AI assistant, collaborating with other assistants."
                        " Use the provided tools to progress towards answering the question."
                        " If you are unable to fully answer, that's OK; another assistant with different tools"
                        " will help where you left off. Execute what you can to make progress."
                        + get_collaboration_stop_instruction()
                        + " You have access to the following tools: {tool_names}.\n{system_message}"
                        + " For your reference, the current date is {current_date}. {instrument_context}"
                    ),
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        result, report = run_tool_report_chain(
            prompt_template,
            llm,
            tools,
            state["messages"],
            system_message=system_message,
            tool_names=", ".join(tool.name for tool in tools),
            current_date=current_date,
            instrument_context=instrument_context,
        )
        report = normalize_chinese_role_terms(report) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "market_flow_report": report,
            }
        )

    return etf_market_node
