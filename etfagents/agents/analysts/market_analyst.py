from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import re

from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_indicators,
    get_language_instruction,
    get_stock_data,
    normalize_chinese_role_terms,
    truncate_for_prompt,
)
from etfagents.agents.utils.state_keys import get_asset_symbol
from etfagents.tool_report_utils import run_tool_report_chain


_REQUIRED_MARKET_INDICATORS = {
    "close_50_sma": 90,
    "close_200_sma": 260,
    "close_10_ema": 45,
    "macd": 60,
    "macds": 60,
    "macdh": 60,
    "rsi": 60,
    "boll": 60,
    "boll_ub": 60,
    "boll_lb": 60,
    "atr": 60,
    "vwma": 60,
}


_INDICATOR_MISSING_ALIASES = {
    "close_50_sma": ("50日SMA", "50日简单移动平均线", "50日均线"),
    "close_200_sma": ("200日SMA", "200日简单移动平均线", "200日均线"),
    "close_10_ema": ("10日EMA", "10日指数移动平均线", "10日均线"),
    "macd": ("MACD",),
    "macds": ("MACD信号线",),
    "macdh": ("MACD柱状图",),
    "rsi": ("RSI",),
    "boll": ("布林带中轨", "布林带"),
    "boll_ub": ("布林带上轨",),
    "boll_lb": ("布林带下轨",),
    "atr": ("ATR", "ATR波动率"),
    "vwma": ("VWMA", "成交量加权移动平均线"),
}


def _market_intro_requirements() -> str:
    return (
        "Opening paragraph requirements:\n"
        "1. The first paragraph must be a concise takeaway, not a process disclaimer.\n"
        "2. Summarize the dominant trend, the key support / resistance or confirmation level, and the practical stance (follow trend, wait, reduce on weakness, etc.).\n"
        "3. Do not write boilerplate such as 'this report is based on trading data', 'the report is divided into dimensions', or 'all conclusions map from raw outputs'."
    )


def _market_depth_requirements() -> str:
    return (
        "Depth requirements for the final report:\n"
        "1. Do not stop at textbook definitions or a bare latest reading. For every indicator you mention, explain what the current reading means now for trend, momentum, volatility, or confirmation.\n"
        "2. When the data permits, compare the latest close with 10 EMA / 50 SMA / 200 SMA, compare 10 EMA with the longer averages, compare MACD with the signal line and histogram sign, and compare price with the Bollinger middle / upper / lower bands and VWMA.\n"
        "3. Convert those comparisons into trading significance: identify support / resistance, trend continuation vs. exhaustion risk, what would confirm the move, what would invalidate it, and which condition would justify adding, holding, reducing, or waiting.\n"
        "4. If an indicator is missing, do not only say 'data unavailable' — also state which part of the technical judgment becomes less reliable because of that missing indicator.\n"
        "5. Avoid boilerplate phrases like 'this indicator is a long-term trend benchmark' unless you immediately tie them to the specific latest reading and a concrete implication."
    )


def _message_text(message) -> str:
    return extract_text_content(getattr(message, "content", None))


def _collected_market_context(messages) -> str:
    return "\n\n".join(filter(None, (_message_text(message) for message in messages)))


def _indicator_has_numeric_value(messages, indicator: str) -> bool:
    conversation = _collected_market_context(messages)
    match = re.search(
        rf"## {re.escape(indicator)} values[^\n]*:\n\n(?P<body>.*?)(?:\n\n|$)",
        conversation,
        re.DOTALL,
    )
    if not match:
        return False
    return bool(
        re.search(
            r"^\d{4}-\d{2}-\d{2}:\s*-?\d+(?:\.\d+)?$",
            match.group("body"),
            re.MULTILINE,
        )
    )


def _missing_market_indicators(messages) -> list[str]:
    conversation = _collected_market_context(messages).lower()
    missing = []
    for indicator in _REQUIRED_MARKET_INDICATORS:
        if f"## {indicator} values" not in conversation:
            missing.append(indicator)
    return missing


def _report_has_full_market_coverage(report: str) -> bool:
    normalized = (report or "").lower()
    required_keyword_groups = (
        ("sma", "ema"),
        ("macd",),
        ("rsi",),
        ("boll", "布林"),
        ("vwma", "成交量加权移动平均线", "volume weighted"),
    )
    return all(any(keyword in normalized for keyword in group) for group in required_keyword_groups)


def _report_has_actionable_market_intro(report: str) -> bool:
    text = (report or "").strip()
    if not text:
        return False

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return False
    first = paragraphs[0]
    first_lower = first.lower()
    boilerplate_signals = (
        "基于",
        "本报告",
        "结构化拆解",
        "四大维度",
        "严格依据系统输出",
        "原始数据输出",
        "未引入任何外部假设",
        "based on trading data",
        "structured breakdown",
        "four dimensions",
        "raw outputs",
    )
    actionable_signals = (
        "偏多",
        "偏空",
        "震荡",
        "承压",
        "企稳",
        "支撑",
        "压力",
        "加仓",
        "减仓",
        "等待",
        "突破",
        "跌破",
        "trend",
        "support",
        "resistance",
        "breakout",
        "breakdown",
        "hold",
        "reduce",
        "add",
        "wait",
    )
    if any(signal in first for signal in boilerplate_signals) or any(
        signal in first_lower for signal in boilerplate_signals
    ):
        return False
    return any(signal in first for signal in actionable_signals) or any(
        signal in first_lower for signal in actionable_signals
    )


def _report_has_actionable_market_depth(report: str) -> bool:
    normalized = (report or "").lower()
    if len(normalized.strip()) < 400:
        return False

    keyword_groups = (
        ("高于", "低于", "上穿", "下穿", "位于", "above", "below", "cross", "crossover", "spread"),
        ("支撑", "压力", "止损", "加仓", "减仓", "入场", "退出", "support", "resistance", "stop", "add", "reduce", "entry", "exit"),
        ("若", "如果", "一旦", "则", "when ", "if ", "unless "),
        ("超买", "超卖", "金叉", "死叉", "背离", "bullish", "bearish", "overbought", "oversold", "divergence"),
    )
    matched_groups = sum(any(keyword in normalized for keyword in group) for group in keyword_groups)
    return matched_groups >= 3


def _report_falsely_claims_missing_indicator(report: str, messages) -> bool:
    text = report or ""
    for indicator, aliases in _INDICATOR_MISSING_ALIASES.items():
        if not _indicator_has_numeric_value(messages, indicator):
            continue
        for alias in aliases:
            if re.search(
                rf"{re.escape(alias)}[^\n。；;]*?(?:未提供|暂无|缺失|不可用|暂无法|无法纳入|数据不足)",
                text,
                re.IGNORECASE,
            ):
                return True
    return False


def _fetch_missing_indicator_data(symbol: str, current_date: str, missing_indicators: list[str]) -> str:
    outputs = []
    for indicator in missing_indicators:
        outputs.append(
            get_indicators.invoke(
                {
                    "symbol": symbol,
                    "indicator": indicator,
                    "curr_date": current_date,
                    "look_back_days": _REQUIRED_MARKET_INDICATORS[indicator],
                }
            )
        )
    return "\n\n".join(outputs)


def _rewrite_market_report(llm, symbol: str, current_date: str, instrument_context: str, messages, missing_indicators: list[str]) -> str:
    existing_context = truncate_for_prompt(_collected_market_context(messages), default_limit=24000)
    additional_indicator_data = _fetch_missing_indicator_data(symbol, current_date, missing_indicators)
    rewrite_prompt = f"""You are a trading assistant writing the final market technical report.
Use only the stock data and indicator outputs supplied below. Do not invent values.

You must explicitly cover all of these categories in the final report.
Each top-level section (一、二) must begin with 2-3 sentences summarizing the key conclusions
of that section, then a blank line before sub-sections.

一、趋势与动量 (Trend & Momentum)
（一）Trend and moving averages: close_50_sma, close_200_sma, close_10_ema
（二）Momentum: macd, macds, macdh, rsi
二、波动与量能 (Volatility & Volume)
（一）Volatility: boll, boll_ub, boll_lb, atr
（二）Volume confirmation: vwma

If any indicator is unavailable, state that clearly instead of skipping the section.
{_market_intro_requirements()}
{_market_depth_requirements()}
Do not output tool calls. Write a detailed, data-backed markdown report and end with a markdown summary table.
{instrument_context}{get_language_instruction()}

Current date: {current_date}

Existing conversation data:
{existing_context}

Additional indicator data fetched to complete the report:
{additional_indicator_data}
"""
    return normalize_chinese_role_terms(extract_text_content(llm.invoke(rewrite_prompt).content))


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)

        tools = [
            get_stock_data,
            get_indicators,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. Your price and technical analysis must rely only on the data returned by `get_stock_data` and `get_indicators`. Do not infer price action, volume behavior, momentum, or technical signals from company news, macro news, or social sentiment. You must produce a comprehensive technical report, not a minimal one. Unless a tool explicitly fails, cover all of the following indicators in the final report:

- close_50_sma
- close_200_sma
- close_10_ema
- macd
- macds
- macdh
- rsi
- boll
- boll_ub
- boll_lb
- atr
- vwma

Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + f" {_market_intro_requirements()}"
            + f" {_market_depth_requirements()}"
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
                        + "For your reference, the current date is {current_date}. {instrument_context}"
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
            tool_names=", ".join([tool.name for tool in tools]),
            current_date=current_date,
            instrument_context=instrument_context,
        )
        report = normalize_chinese_role_terms(report) if report else report

        needs_completion = (
            not getattr(result, "tool_calls", None)
            and (
                not report
                or not _report_has_full_market_coverage(report)
                or not _report_has_actionable_market_intro(report)
                or not _report_has_actionable_market_depth(report)
                or _report_falsely_claims_missing_indicator(report, [*state["messages"], result])
                or bool(_missing_market_indicators([*state["messages"], result]))
            )
        )
        if needs_completion:
            missing_indicators = _missing_market_indicators([*state["messages"], result])
            completed_report = _rewrite_market_report(
                llm,
                asset_symbol,
                current_date,
                instrument_context,
                [*state["messages"], result],
                missing_indicators,
            )
            if completed_report:
                result = AIMessage(content=completed_report)
                report = completed_report
        elif report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return {
            "messages": [result],
            "market_report": report,
        }

    return market_analyst_node
