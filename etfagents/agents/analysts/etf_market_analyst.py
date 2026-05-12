import logging
import re

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
from etfagents.agents.utils.report_leads import (
    ensure_title_lead_paragraph,
    get_concise_heading_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
    strip_report_title,
    strip_meta_lead_prefixes,
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
_EXPLANATION_TERMS = (
    "意味着", "说明", "也就是说", "换句话说", "对交易而言", "交易含义",
    "which means", "that means", "in other words", "for trading",
)
_TRADING_IMPLICATION_TERMS = (
    "加仓", "减仓", "持有", "等待", "追高", "回踩", "止损", "仓位", "入场", "离场",
    "add", "reduce", "hold", "wait", "entry", "exit", "stop", "position",
)
_JARGON_TERMS = (
    "多头排列", "空头排列", "金叉", "死叉", "背离", "发散", "缩量", "放量", "钝化",
    "bullish crossover", "bearish crossover", "divergence", "dispersion",
)
_DEFAULT_TITLE_LEAD_ZH = (
    "该ETF当前量价结构更接近趋势延续还是震荡回撤，取决于均线斜率、动量强弱与资金流是否同向。"
    "若价格、波动率与成交确认继续共振，交易上更适合顺势持有或回踩加仓；若量价背离扩大，则应优先等待确认而非追高。"
)
_DEFAULT_TITLE_LEAD_EN = (
    "Whether this ETF is set up for trend continuation or a choppy pullback depends on whether moving-average slope, momentum, and fund flow are aligned. "
    "If price, volatility, and volume confirmation keep reinforcing each other, the setup favors holding or buying pullbacks; if price-flow divergence widens, waiting for confirmation is better than chasing."
)
_REPORT_TITLE_ZH = "技术面与资金流综合诊断"
_REPORT_TITLE_EN = "Technical & Flow Diagnosis"
_MARKET_STRUCTURE_TITLES = (
    ("市场结构与量价诊断", "Market Structure & Price-Flow Diagnosis"),
    ("交易确认与执行计划", "Trade Confirmation & Execution Plan"),
    ("关键价位与条件情景推演", "Key Levels & Conditional Scenario Analysis"),
)
_MARKET_SCAFFOLD_LABEL_PATTERN = re.compile(
    r"(?m)^(\s*(?:[-*]\s*)?)\*{0,2}结论依据\*{0,2}[:：]\s*"
)
_SECOND_SECTION_SUBHEADING_PATTERN = re.compile(
    r"(?m)^\s*#{1,6}\s*(?:（一）\s*)?(?:信号确认与决策|Confirmation & Decision)\s*\n+"
)


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
    first_para = ""
    for line in lines:
        if line.startswith("#"):
            continue
        first_para = line.lower()
        break
    if not first_para:
        return False
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


def _etf_report_has_explanatory_clarity(report: str) -> bool:
    if not report:
        return False
    lower = report.lower()
    explanation_hits = sum(lower.count(term.lower()) for term in _EXPLANATION_TERMS)
    implication_hits = sum(lower.count(term.lower()) for term in _TRADING_IMPLICATION_TERMS)
    jargon_hits = sum(lower.count(term.lower()) for term in _JARGON_TERMS)
    if jargon_hits:
        return explanation_hits >= 2 and implication_hits >= 2
    return explanation_hits >= 1 and implication_hits >= 2


def _etf_report_has_compact_structure(report: str) -> bool:
    if not report:
        return False
    return all(
        chinese in report or english in report
        for chinese, english in _MARKET_STRUCTURE_TITLES
    )


def _strip_etf_market_scaffold_labels(report: str) -> str:
    if not report:
        return ""
    return _MARKET_SCAFFOLD_LABEL_PATTERN.sub(r"\1", report)


def _strip_etf_market_second_section_subheading(report: str) -> str:
    if not report:
        return ""
    return _SECOND_SECTION_SUBHEADING_PATTERN.sub("", report)


def _etf_market_report_needs_rewrite(report: str) -> bool:
    if not report:
        return True
    if not _etf_report_has_compact_structure(report):
        return True
    if not _etf_report_has_full_coverage(report):
        return True
    if not _etf_report_has_actionable_intro(report):
        return True
    if not _etf_report_has_actionable_depth(report):
        return True
    if not _etf_report_has_explanatory_clarity(report):
        return True
    return False


def create_etf_market_analyst(llm):
    def etf_market_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)

        tools = [get_etf_price_data, get_etf_indicators, get_etf_share, get_etf_nav, get_etf_universe]

        system_message = (
            "You are an ETF market and flow analyst focused on entry timing, liquidity, and implementation quality."
            " Build a combined technical-and-flow report for the target ETF using price action, moving averages, momentum,"
            " volatility, share changes, NAV clues, and execution depth.\n\n"
            "You should normally pull 3-6 months of ETF price history and explicitly cover:\n\n"
            "Write a 2-4 sentence overview paragraph before any section headings "
            "that summarizes the current directional bias, the most important confirming or contradicting signal, and the trading implication. "
            "This lead paragraph must appear before any section headings.\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "Use EXACTLY three top-level sections (一、二、三). Do NOT create additional top-level sections.\n"
            "Section one must begin with a 2-3 sentence lead paragraph summarizing the key conclusions of that section, then a blank line before sub-sections.\n"
            "Section two must NOT have a separate lead paragraph or hat paragraph; write the body directly under the heading.\n\n"
            "一、市场结构与量价诊断 (Market Structure & Price-Flow Diagnosis)\n"
            "  （一）趋势与动量 (Trend & Momentum): 10 EMA / 20 SMA / 50 SMA / 200 SMA comparisons, MACD, signal line, histogram, RSI\n\n"
            "  （二）波动与流动性 (Volatility & Liquidity): Bollinger bands, ATR, share change, NAV / premium-discount clues, VWMA, turnover\n\n"
            "二、交易确认与执行计划 (Trade Confirmation & Execution Plan)\n"
            "  Write the body of this section directly without any sub-heading. Explain why the judgment is bullish / bearish / neutral, whether flow confirms or contradicts the setup, and the exact add / hold / reduce / wait conditions, support / resistance, and risk controls.\n\n"
            "三、关键价位与条件情景推演 (Key Levels & Conditional Scenario Analysis)\n"
            "  （一）关键价位与触发条件 (Key Levels & Trigger Conditions): explain the most important support / resistance / add / reduce / stop levels in coherent paragraphs rather than a checklist.\n"
            "  （二）条件情景推演 (Conditional Scenario Analysis): use coherent paragraphs to connect those levels to the core scenario path, confirmation or falsification conditions, and the reason you assign higher weight to that scenario.\n\n"
            "When using `get_etf_indicators`, you must call the tool with the exact supported indicator IDs below."
            " Do not use generic aliases such as `MA`, `SMA`, `EMA`, or natural-language indicator names unless they"
            " exactly match one of these tool parameters:\n"
            f"{_etf_indicator_catalog()}\n\n"
            "If you need a generic moving-average baseline, use `close_20_sma` rather than `MA`.\n\n"
            "The final report must explain what current readings imply for ETF allocation timing and whether capital is accumulating, distributing, or crowding the product."
            " End with a compact markdown summary table.\n\n"
            "STYLE RULES — strictly follow:\n"
            "- For the title lead and the 2-3 sentence lead under section one, state the conclusion directly. "
            "Do NOT use lead-ins such as '本部分结论表明', '该部分说明', '这一节意味着', 'This section shows', or similar meta phrasing.\n"
            "- Section two is direct body only: do NOT insert a separate lead paragraph, hat paragraph, or mini-summary before the main analysis.\n"
            "- Section three must restore the former '关键价位与条件情景推演' function, but now organize it into exactly two sub-sections: （一）关键价位与触发条件 and （二）条件情景推演.\n"
            "- Use the exact three-section hierarchy above. Do NOT introduce headings like '核心交易信号', '结论依据', emojis, or extra first-level sections.\n"
            "- Those lead paragraphs must sit one level above the sub-sections: synthesize direction, momentum quality, flow confirmation, and trading implication. "
            "Do NOT simply restate the same indicator observations that will appear immediately below under the sub-sections.\n"
            "- If you use technical jargon such as '多头排列', '金叉', '发散', '背离', '放量突破', or similar shorthand, immediately explain it in plain language and state the trading meaning. "
            "Do NOT write unexplained phrases such as '标准多头发散形态'.\n"
            "- After every major signal, answer both questions: '这意味着什么' and '对交易应该怎么做'.\n"
            "- Paragraph-based expression: in section three, do NOT use quiz-like labels such as '判断：', '证据：', '关键价位：', '条件情景：', or '这意味着什么：'. "
            "Instead, let the signal, judgment, evidence, confidence, and trigger path flow naturally inside complete strategy paragraphs.\n"
            "- Anti-example (forbidden): '判断：偏多。关键价位：448-450。条件情景：若放量突破则继续加仓。'\n"
            "- Positive example (target style): '当前448-450一带既是20日均线与前期密集成交区重叠的支撑带，也是判断这轮偏多结构是否仍有效的第一道关口。若价格回踩后成交量没有明显失速、且VWMA继续向上抬升，说明资金承接并未破坏，基准情景仍是震荡后继续上攻；反之，一旦跌破该区间且量能放大为抛压主导，就应把情景切换为结构转弱并优先减仓。'\n"
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
        report = strip_meta_lead_prefixes(report) if report else report
        report = _strip_etf_market_scaffold_labels(report) if report else report
        report = _strip_etf_market_second_section_subheading(report) if report else report

        # Quality validation: rewrite if coverage/intro/depth checks fail
        if report and not getattr(result, "tool_calls", None) and _etf_market_report_needs_rewrite(report):
            logger.info("ETF market report failed quality checks; rewriting")
            rewrite_prompt = (
                "Your previous ETF market report was incomplete or lacked actionable depth. "
                "Please produce a new report that:\n"
                "- Does NOT use any report title or H1 heading; start directly with a 2-4 sentence overview paragraph before any section headings\n"
                "- Do NOT repeat the report subject in the body or create pseudo-title lines from exchange-only suffixes such as SH / SZ / HK\n"
                "- Uses EXACTLY these three top-level sections and no others:\n"
                "  一、市场结构与量价诊断\n"
                "    [starts with a 2-3 sentence lead paragraph]\n"
                "    （一）趋势与动量\n"
                "    （二）波动与流动性\n"
                "  二、交易确认与执行计划\n"
                "    [direct body only; no sub-heading and no separate lead paragraph under section two]\n"
                "  三、关键价位与条件情景推演\n"
                "    （一）关键价位与触发条件\n"
                "    （二）条件情景推演\n"
                "- Covers ALL of: trend (SMA/EMA), momentum (MACD), overbought/oversold (RSI), "
                "volatility (Bollinger), and volume confirmation (VWMA)\n"
                "- Opens with a clear actionable signal (bullish/bearish/neutral and why)\n"
                "- Restores the original '关键价位与条件情景推演' purpose with specific support/resistance levels and conditional scenarios\n"
                "- Explains every technical term in plain language and immediately states the trading implication; "
                "do not leave phrases like '标准多头发散形态' unexplained\n"
                "- For the title lead and each top-level section lead, state the conclusion directly instead of using meta phrases like '本部分结论表明'\n"
                "- In section three, do NOT use labels such as '判断：', '证据：', '关键价位：', '条件情景：' or similar scaffolding; write flowing paragraphs instead\n"
                "- Do NOT add headings or labels such as '核心交易信号', '结论依据', emoji banners, or similar scaffolding\n"
                "- Ends with a compact markdown summary table\n\n"
                f"Previous report:\n{report}"
            )
            try:
                rewrite_response = llm.invoke(rewrite_prompt)
                from etfagents.content_utils import extract_text_content
                rewritten = extract_text_content(rewrite_response.content)
                if rewritten and not _etf_market_report_needs_rewrite(rewritten):
                    report = normalize_chinese_role_terms(rewritten)
                    report = strip_meta_lead_prefixes(report)
                    report = _strip_etf_market_scaffold_labels(report)
                    report = _strip_etf_market_second_section_subheading(report)
                    result = AIMessage(content=report)
            except Exception as exc:
                logger.warning("ETF market report rewrite failed: %s", exc)

        report = strip_report_title(report) if report else report
        report = ensure_title_lead_paragraph(
            report,
            _DEFAULT_TITLE_LEAD_ZH,
            _DEFAULT_TITLE_LEAD_EN,
        ) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "market_flow_report": report,
            }
        )

    return etf_market_node
