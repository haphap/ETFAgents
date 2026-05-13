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
    normalize_chinese_section_headings,
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
            "你是一名ETF市场与资金流分析师，聚焦入场时机、流动性与执行质量。"
            "基于价格走势、均线、动量、波动率、份额变化、NAV线索与执行深度，为目标ETF构建一份技术面与资金流综合诊断报告。\n\n"
            "## 数据获取\n"
            "1. 先调用 get_etf_price_data 获取价格数据，通常拉取3-6个月历史。\n"
            "2. 再调用 get_etf_indicators 获取技术指标，必须使用下方精确的指标ID，"
            "不得使用 MA、SMA、EMA 等通用别名。若需通用均线基准，请使用 close_20_sma。\n"
            "3. 调用 get_etf_share 与 get_etf_nav 获取份额与NAV数据，用于追踪资金流向。\n"
            "工具调用顺序：get_etf_price_data → get_etf_indicators → get_etf_share / get_etf_nav。"
            "若某个工具失败则跳过并继续，但至少确保价格数据与趋势、动量指标的覆盖。\n\n"
            f"可用指标ID：\n{_etf_indicator_catalog()}\n\n"
            "份额变化解读：份额增长代表资金净流入，份额下降代表赎回流出。"
            "份额持续增长且换手率适中，表明资金在积累；换手率急升但份额持平或下降，则暗示拥挤或投机。"
            "NAV溢价/折价也是资金信号：持续溢价说明需求旺盛，持续折价说明赎回压力，溢价收窄说明热情降温。\n\n"
            "Write a 2-4 sentence overview paragraph that summarizes the current directional bias, "
            "the most important confirming or contradicting signal, and the trading implication before section one.\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "Use EXACTLY three top-level sections (一、二、三). Do NOT create additional top-level sections.\n"
            "Section one must begin with a 2-3 sentence lead paragraph summarizing the key conclusions of that section, then a blank line before sub-sections.\n"
            "Section two must NOT have a separate lead paragraph or hat paragraph; write the body directly under the heading.\n\n"
            "一、市场结构与量价诊断\n"
            "  （一）趋势与动量: 10 EMA / 20 SMA / 50 SMA / 200 SMA comparisons, MACD, signal line, histogram, RSI\n\n"
            "  （二）波动与流动性: Bollinger bands, ATR, share change, NAV / premium-discount clues, VWMA, turnover\n\n"
            "二、交易确认与执行计划\n"
            "  Write the body of this section directly without any sub-heading. Explain why the judgment is bullish / bearish / neutral, whether flow confirms or contradicts the setup, and the exact add / hold / reduce / wait conditions, support / resistance, and risk controls.\n\n"
            "三、关键价位与条件情景推演\n"
            "  （一）关键价位与触发条件: explain the most important support / resistance / add / reduce / stop levels in coherent paragraphs rather than a checklist.\n"
            "  （二）条件情景推演: use coherent paragraphs to connect those levels to the core scenario path, confirmation or falsification conditions, and the reason you assign higher weight to that scenario.\n\n"
            "## 风格要求\n"
            '- 标题导语与第一部分导语直接陈述结论，不得使用"本部分结论表明"、"该部分说明"、"This section shows"等元描述。\n'
            "- 导语段落必须高于小节层面：综合方向、动量质量、资金确认与交易含义，不得简单复述下方小节内容。\n"
            "- 第二部分直接写正文，不得在标题下插入独立导语或帽段。\n"
            '- 使用上述精确的三段章节结构，不得引入"核心交易信号"、"结论依据"等额外标题。\n'
            '- 若使用"多头排列"、"金叉"、"发散"、"背离"、"放量突破"等技术术语，必须立即用通俗语言解释并说明交易含义，不得出现"标准多头发散形态"等未解释行话。\n'
            '- 每个主要信号之后必须回答两个问题："这意味着什么"和"对交易应该怎么做"。\n'
            '- 第三部分采用段落式表达，不得使用"判断："、"证据："、"关键价位："、"条件情景："等标签。信号、判断、证据、信心水平与触发路径应融入完整的策略段落中。\n'
            "- 反面示例（禁止）：'判断：偏多。关键价位：448-450。条件情景：若放量突破则继续加仓。'\n"
            "- 正面示例（目标风格）：'当前448-450一带既是20日均线与前期密集成交区重叠的支撑带，也是判断这轮偏多结构是否仍有效的第一道关口。若价格回踩后成交量没有明显失速、且VWMA继续向上抬升，说明资金承接并未破坏，基准情景仍是震荡后继续上攻；反之，一旦跌破该区间且量能放大为抛压主导，就应把情景切换为结构转弱并优先减仓。'\n\n"
            "## 完整报告示例（仅作风格参考，实际内容以目标ETF数据为准）\n\n"
            "价格站稳50日均线上方，短中期均线同步向上，MACD柱状图持续扩张，量价结构偏多，但RSI接近超买区需要警惕短期回踩。\n\n"
            "一、市场结构与量价诊断\n\n"
            "趋势、动量与资金流三者仍在同向确认偏多结构，短期回踩风险可控但需关注RSI超买信号。\n\n"
            "（一）趋势与动量\n\n"
            "10日均线452元、20日均线448元、50日均线443元、200日均线425元，短中长期均线全部向上发散——这意味着不同时间维度的买盘力量都在主导。MACD的DIF为1.05、DEA为0.78，两者均在零轴上方且差值持续扩大，柱状图连续五天走高，说明上涨动能正在增强。RSI读数64，距超买区70尚有余地，未出现顶背离信号。综合来看，趋势与动量同步确认偏多方向。\n\n"
            "（二）波动与流动性\n\n"
            "布林带中轨449元、上轨462元，价格在中轨与上轨之间运行，带宽扩张但方向向上，说明波动率上升有利于趋势延续。ATR为1.8元，约占价格4%，若以ATR设置止损可参考446元（中轨下方）。份额近一周增长2.3%，NAV溢价率0.18%处于正常范围，换手率1.3%未见异常拥挤信号。VWMA稳步上行，确认放量突破有效，资金持续流入。\n\n"
            "二、交易确认与执行计划\n\n"
            "趋势、动量、波动率与资金流四维共振偏多，执行上以回踩支撑加仓为主、条件化风控为辅。若RSI进入超买区后出现死叉，应优先收缩仓位而非追高；若份额从净流入转为净流出，则说明资金在撤退，需重新评估偏多逻辑。当前建议维持偏多配置，仓位控制在5-6成，回踩448-450区间可加至7成，止损设在446元下方。\n\n"
            "三、关键价位与条件情景推演\n\n"
            "当前448-450一带既是20日均线与前期密集成交区重叠的支撑带，也是判断这轮偏多结构是否仍有效的第一道关口。若价格回踩后成交量没有明显失速、且VWMA继续向上抬升，说明资金承接并未破坏，基准情景仍是震荡后继续上攻462-465阻力带。操作上，若回踩448-450不破且量能未失速，可加仓至6-7成，止损446元下方；若放量跌破448则先减至3-4成，进一步跌破440则止损离场。最乐观情景下，若放量突破462元可追加至8成，目标470元以上。基于当前信号强度，基准情景权重约65%，最乐观情景约25%，转弱情景约10%。需警惕的风险包括：RSI进入超买区后死叉可能触发短期回调，份额从净流入转为净流出将否定偏多逻辑。\n\n"
            "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 10/20/50/200 SMA | 452/448/443/425 | 上方 | 多头排列，趋势偏多 | 跌破448则短期转弱 |\n"
            "| MACD | DIF 1.05, DEA 0.78 | 零轴上方 | 动能增强 | DIF下穿DEA则动能衰减 |\n"
            "| RSI | 64 | 中性偏强 | 尚有空间但接近超买 | 上穿70则警惕回踩 |\n"
            "| 布林带 | 中轨449, 上轨462 | 中轨与上轨之间 | 波动率扩张，方向向上 | 跌破中轨则趋势减弱 |\n"
            "| 份额变化 | +2.3% | — | 资金净流入 | 连续下降则资金撤退 |\n"
            "| 换手率 | 1.3% | 正常 | 未见拥挤 | 超过3%则拥挤加剧 |\n\n"
            "综合结论：偏多配置，回踩448-450加仓，止损446，目标462-465。资金状态：份额增长+溢价正常+换手率适中=资金积累中。\n\n"
            "## 语言\n"
            "分析文本使用中文。工具名称、指标ID与行情代码保持英文。\n"
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
                "你上一份ETF市场报告不够完整或缺乏可操作深度。请严格按照以下要求重新生成：\n"
                "- 不要使用报告标题或H1标题，直接以2-4句概述段落开头\n"
                "- 恰好使用三个一级章节：一、市场结构与量价诊断（含趋势与动量、波动与流动性两个二级标题）、二、交易确认与执行计划（直接正文，无子标题）、三、关键价位与条件情景推演（含关键价位与触发条件、条件情景推演两个二级标题）\n"
                "- 必须覆盖趋势(SMA/EMA)、动量(MACD)、超买超卖(RSI)、波动率(Bollinger)和量能确认(VWMA)\n"
                "- 以清晰的可操作信号开头（偏多/偏空/中性及原因）\n"
                "- 结合份额变化、NAV溢价/折价和换手率判断资金积累/分配/拥挤状态\n"
                "- 每个技术术语用通俗语言解释并说明交易含义\n"
                '- 导语直接陈述结论，不得使用"本部分结论表明"等元描述\n'
                '- 第三部分使用段落式表达，不得使用"判断："、"证据："等标签\n'
                "- 以markdown摘要表结尾\n\n"
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
        report = normalize_chinese_section_headings(report) if report else report
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
