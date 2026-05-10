import logging

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

logger = logging.getLogger(__name__)


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


_ETF_COVERAGE_GROUPS = [
    ("trend", ("sma", "ema")),
    ("momentum", ("macd",)),
    ("overbought_oversold", ("rsi",)),
    ("volatility", ("boll", "布林")),
    ("volume_confirm", ("vwma", "成交量加权移动平均线", "volume weighted")),
]

_INTRO_BOILERPLATE_MARKERS = (
    "本报告将", "本报告基于", "以下是一份", "structured breakdown",
    "raw outputs", "以下是对", "本分析将",
)

_ACTIONABLE_INTRO_TERMS = (
    "偏多", "偏空", "承压", "支撑", "突破", "回落", "震荡", "强势", "弱势",
    "bullish", "bearish", "trend", "support", "resistance", "breakout",
    "hold", "add", "reduce", "wait", "accumulate", "distribute",
)

_DEPTH_KEYWORD_GROUPS = [
    ("above", "below", "高于", "低于", "crossover", "cross"),
    ("支撑", "压力", "support", "resistance", "stop", "add", "reduce"),
    ("若", "如果", "if ", "unless", "when"),
    ("超买", "超卖", "金叉", "死叉", "divergence", "overbought", "oversold"),
]


def _etf_report_has_full_coverage(report: str) -> bool:
    lower = report.lower()
    return all(
        any(kw in lower for kw in group)
        for _, group in _ETF_COVERAGE_GROUPS
    )


def _etf_report_has_actionable_intro(report: str) -> bool:
    lines = [line.strip() for line in report.split("\n") if line.strip()]
    if not lines:
        return False
    first_para = lines[0].lower()
    if any(marker in first_para for marker in _INTRO_BOILERPLATE_MARKERS):
        return False
    return any(term in first_para for term in _ACTIONABLE_INTRO_TERMS)


def _etf_report_has_actionable_depth(report: str) -> bool:
    if len(report) < 400:
        return False
    lower = report.lower()
    matched = sum(
        1 for group in _DEPTH_KEYWORD_GROUPS
        if any(kw in lower for kw in group)
    )
    return matched >= 3


def _etf_market_report_needs_rewrite(report: str) -> bool:
    if not report:
        return True
    if not _etf_report_has_full_coverage(report):
        return True
    if not _etf_report_has_actionable_intro(report):
        return True
    if not _etf_report_has_actionable_depth(report):
        return True
    return False


def create_etf_market_analyst(llm):
    def etf_market_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(get_asset_symbol(state))

        tools = [get_etf_price_data, get_etf_indicators, get_etf_share, get_etf_nav, get_etf_universe]

        system_message = (
            "You are an ETF market and flow analyst focused on entry timing, liquidity, and implementation quality."
            " Build a combined technical-and-flow report for the target ETF using price action, moving averages, momentum,"
            " volatility, share changes, NAV clues, and execution depth.\n\n"
            "You should normally pull 3-6 months of ETF price history and explicitly cover:\n\n"
            "Each top-level section (一、二、三) must begin with a hat paragraph (帽段) — 2-3 sentences "
            "summarizing the key conclusions of that section before sub-sections展开. "
            "Sub-sections must each start on a new line with a blank line separating them.\n\n"
            "一、趋势与动量 (Trend & Momentum)\n"
            "[Hat paragraph: summarize trend regime and momentum stance]\n\n"
            "  （一）Trend regime (10 EMA / 20 SMA / 50 SMA / 200 SMA comparisons when available)\n\n"
            "  （二）Momentum (MACD, signal line, histogram, RSI)\n\n"
            "二、波动与流动性 (Volatility & Liquidity)\n"
            "[Hat paragraph: summarize volatility state and flow direction]\n\n"
            "  （一）Volatility and risk boundaries (Bollinger bands, ATR)\n\n"
            "  （二）Flow and liquidity confirmation (share change, NAV / premium-discount clues, VWMA, turnover)\n\n"
            "三、信号确认与决策 (Confirmation & Decision)\n"
            "[Hat paragraph: summarize whether signals align and the actionable stance]\n\n"
            "  （一）Whether flow confirms or contradicts the chart setup\n\n"
            "  （二）Actionable implementation levels for add / hold / reduce / wait decisions\n\n"
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

        # Quality validation: rewrite if coverage/intro/depth checks fail
        if report and not getattr(result, "tool_calls", None) and _etf_market_report_needs_rewrite(report):
            logger.info("ETF market report failed quality checks; rewriting")
            rewrite_prompt = (
                "Your previous ETF market report was incomplete or lacked actionable depth. "
                "Please produce a new report that:\n"
                "- Covers ALL of: trend (SMA/EMA), momentum (MACD), overbought/oversold (RSI), "
                "volatility (Bollinger), and volume confirmation (VWMA)\n"
                "- Opens with a clear actionable signal (bullish/bearish/neutral and why)\n"
                "- Includes specific support/resistance levels and conditional scenarios\n"
                "- Ends with a compact markdown summary table\n\n"
                f"Previous report:\n{report}"
            )
            try:
                rewrite_response = llm.invoke(rewrite_prompt)
                from etfagents.content_utils import extract_text_content
                rewritten = extract_text_content(rewrite_response.content)
                if rewritten and _etf_report_has_full_coverage(rewritten):
                    report = normalize_chinese_role_terms(rewritten)
                    result = AIMessage(content=report)
            except Exception as exc:
                logger.warning("ETF market report rewrite failed: %s", exc)

        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "market_flow_report": report,
            }
        )

    return etf_market_node
