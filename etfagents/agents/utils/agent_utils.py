from langchain_core.messages import HumanMessage, RemoveMessage
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation
import logging
import os
import re

logger = logging.getLogger(__name__)

from etfagents.agents.utils.rating import (
    detect_chinese_rating as _shared_detect_chinese_rating,
    detect_english_rating as _shared_detect_english_rating,
    parse_rating,
)
from etfagents.content_utils import extract_text_content

# Re-export data tools for backward compatibility (analysts import them from here)
from etfagents.agents.utils.core_stock_tools import get_stock_data
from etfagents.agents.utils.etf_data_tools import (
    get_commodity_cluster_data,
    get_etf_holdings,
    get_etf_indicators,
    get_etf_industry_research,
    get_etf_info,
    get_etf_nav,
    get_etf_price_data,
    get_etf_share,
    get_etf_top_holdings_research,
    get_etf_universe,
    get_macro_regime_data,
)
from etfagents.agents.utils.technical_indicators_tools import get_indicators
from etfagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
)
from etfagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news,
)
from etfagents.agents.utils.research_report_tools import get_broker_research, get_stock_research


def collapse_blank_lines(text: str) -> str:
    """Collapse excessive blank lines while preserving one Markdown blank line."""
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\n(?:[ \t]*\n){2,}", "\n\n", normalized).strip()


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from etfagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return (
        f" Write your entire response in {lang}."
        " Translate mixed English finance terms into Chinese as well, including items such as"
        " Capex, Forward PE, quarterly earnings, and scalability."
        " Follow Chinese publishing number style: use Arabic numerals for dates, times,"
        " percentages, prices, quantities, ticker symbols, securities codes, model numbers,"
        " and other codes/serial numbers; keep approximate expressions such as"
        " '三四个月', '十余次', '一千多件', and '约三千名' in Chinese unless a local"
        " statistical comparison clearly requires Arabic numerals. For very large currency"
        " figures written in Arabic numerals, rescale raw `元/美元/港元` amounts into"
        " `万` or `亿` units when that produces a clean, publication-style expression"
        " (e.g. `300000000000元` -> `3000亿元`). In visible Chinese prose, replace raw"
        " technical-indicator parameter keys such as `close_10_ema`, `boll_ub`, and"
        " `vwma` with reader-friendly labels such as `10日EMA`, `布林带上轨`, and"
        " `成交量加权移动平均线`."
        " Use Chinese official-document heading hierarchy numbering throughout the report:"
        " first level 一、二、三、; second level （一）（二）（三）; third level 1. 2. 3.;"
        " fourth level (1) (2) (3); fifth level ① ② ③. "
        " Keep paragraphs distinct and numbering consistent from start to finish."
    )


def get_no_greeting_instruction() -> str:
    """Return a prompt instruction forbidding greeting openers."""
    if _is_chinese_output():
        return (
            " 直接进入正文，严禁以问候语开头（如「你好，空头分析师」、「大家好」等），"
            "也不要在正文中重复自己的角色名称。"
        )
    return (
        " Start directly with your argument. Do not open with greetings or salutations "
        "(e.g. 'Hello, Bear Analyst'). Do not repeat your own role name in the body."
    )


def get_output_language() -> str:
    from etfagents.dataflows.config import get_config

    return get_config().get("output_language", "English")


CHINESE_OUTPUT_VALUES = {"chinese", "中文", "zh", "zh-cn", "zh-hans"}


def _is_chinese_output() -> bool:
    return get_output_language().strip().lower() in CHINESE_OUTPUT_VALUES


def truncate_for_prompt(
    text: str,
    limit_key: str = "report_context_char_limit",
    default_limit: int = 16000,
) -> str:
    """Trim long context text to keep prompts within a stable token budget."""
    if not text:
        return ""

    from etfagents.dataflows.config import get_config

    cfg = get_config()
    limit = int(cfg.get(limit_key, default_limit) or default_limit)
    if limit <= 0 or len(text) <= limit:
        return text

    omitted = len(text) - limit
    return f"[Content trimmed, omitted {omitted} characters]\n{text[-limit:]}"


def truncate_response_for_prompt(text: str) -> str:
    """Truncate a previous agent argument/response for inclusion as debate context.

    Uses a tighter limit than full reports to prevent debate history from bloating
    the prompt beyond the local model's context window.
    """
    return truncate_for_prompt(text, limit_key="response_context_char_limit", default_limit=3000)


def join_memory_recommendations(memories: list[dict]) -> str:
    """Render retrieved memory recommendations for prompt injection."""
    if not memories:
        return ""

    recommendations = []
    for record in memories:
        recommendation = str(record.get("recommendation", "")).strip()
        if recommendation:
            recommendations.append(recommendation)
    return "\n\n".join(recommendations)


def get_snapshot_template(round_index: int = 1) -> str:
    if _is_chinese_output():
        return """反馈快照:
- 立场:
- 本轮新增与反驳:
- 待验证:"""

    return """FEEDBACK SNAPSHOT:
- Stance:
- New this round & rebuttal:
- To verify:"""


def get_snapshot_writing_instruction(round_index: int = 1) -> str:
    if _is_chinese_output():
        return (
            "反馈快照是对本轮核心内容的完整、详细记录，必须用自己的语言概括，禁止从正文中直接复制句子。\n"
            "每个字段应展开2-4句，包含完整的逻辑链和具体数据，让读者无需阅读正文即可理解本轮论点的全貌。"
            "普通列表如需编号，优先使用阿拉伯数字，例如 1. 2. 3.；若是中文章节标题，可保留「一、二、三」：\n\n"
            "「立场」：明确评级 + 核心理由 + 当前最关键的支撑或风险因素。"
            "如「维持减持——30倍PE在商品周期顶部严重透支，MACD死叉确认趋势转弱，"
            "36元支撑位一旦击穿将触发止损盘连锁卖出，下行目标看至32元」；\n\n"
            "「本轮新增与反驳」：把本轮新增的信息增量与它对对手观点的冲击合并写成一个连贯段落。"
            "先写本轮首次提出的新证据、新逻辑或新数据，再明确说明它如何削弱对手【本轮最新主张】。"
            "若本轮引入了新数据，必须解释该数据的含义、为何改变判断，以及它为什么让对手推论难以成立；"
            "若本轮没有新增数据，也要写出本轮最关键的增量判断，并顺带点明它反驳了对手的哪一点；\n\n"
            "「待验证」：列出2-3个下轮需跟踪的具体指标或事件，说明每个指标的阈值和触发含义。"
            "如「1. 金价能否守稳4800美元——若跌破则确认地缘溢价消退，黄金收益贡献将从30%缩水至15%；"
            "2. Q2铜价走势——若跌破8000美元/吨则62%利润增速将面临均值回归压力；"
            "3. 6月美联储议息——若维持高利率则紫金美元债务成本上升0.3-0.5个百分点」；\n\n"
            "【关键约束】：将你的上轮快照与本轮快照逐字段对比，确保「本轮新增与反驳」"
            "体现了本轮独有的信息增量，而不是复制正文或机械重复上轮表述。\n"
            "严禁开场白，严禁重复角色名，三项内容各不相同。"
        )
    return (
        "The feedback snapshot is a detailed, well-supported record of this round's key content. "
        "Each field should be 2-4 sentences with complete logic chain and specific data. "
        "Use Arabic numerals such as 1. 2. 3. for numbered items rather than circled digits or non-Arabic numbering, "
        "so the reader can understand the full picture without reading the main argument:\n\n"
        "'Stance': rating + core rationale + the single most critical supporting or risk factor right now. "
        "e.g. 'Maintain Sell — 30x PE at the top of a commodity cycle is severely stretched; "
        "MACD death cross confirms trend weakening; if $36 support breaks, stop-loss cascade targets $32';\n\n"
        "'New this round & rebuttal': merge the incremental content and the rebuttal into one coherent field. "
        "First state the genuinely new evidence, framing, or data introduced this round, then explain how it weakens "
        "the opponent's latest claim. If a new metric appears, explain why it matters and why it undermines the opposing inference;\n\n"
        "'To verify': 2-3 specific indicators or events with thresholds and trigger meanings. "
        "e.g. '1. Copper holding above $8,000 — if it breaks, 62% profit growth faces mean-reversion; "
        "2. Fed June decision — if rates held, USD debt cost rises 30-50bps; "
        "3. Q2 earnings capex — if above $5B, confirms sustainable expansion thesis'.\n\n"
        "KEY CONSTRAINT: Compare previous snapshot with this one field by field — "
        "'New this round & rebuttal' must contain real incremental content instead of copied body text or repeated phrasing.\n"
        "No greetings. No role names. No two fields alike."
    )

def localize_label(english: str, chinese: str) -> str:
    return chinese if _is_chinese_output() else english


ROLE_LOCALIZATION_MAP: dict[str, str] = {
    "Bull Analyst": "多头分析师",
    "Bull Researcher": "多头分析师",
    "Bear Analyst": "空头分析师",
    "Bear Researcher": "空头分析师",
    "Aggressive Analyst": "激进风险分析师",
    "Conservative Analyst": "保守风险分析师",
    "Neutral Analyst": "中性风险分析师",
    "Market Analyst": "市场分析师",
    "Market & Flow Analyst": "市场与资金流分析师",
    "Sentiment & Catalyst Analyst": "舆情与事件分析师",
    "Social Analyst": "社交情绪分析师",
    "News Analyst": "新闻分析师",
    "Macro Analyst": "宏观分析师",
    "Macro Regime Analyst": "宏观框架分析师",
    "ETF Structure Analyst": "ETF结构分析师",
    "Commodity Analyst": "商品集群分析师",
    "Meso Commodity Analyst": "中观大宗商品分析师",
    "ETF Flow Analyst": "ETF资金流分析师",
    "ETF Macro Analyst": "ETF宏观暴露分析师",
    "Fundamentals Analyst": "基本面分析师",
    "Industry Research Analyst": "行业研究分析师",
    "ETF Industry Research Analyst": "ETF行业研究分析师",
    "ETF Holdings-Industry Research Analyst": "行业研究分析师",
    "Broker Research Analyst": "行业研究分析师",
    "Stock Research Analyst": "个股研究分析师",
    "ETF Top Holdings Research Analyst": "个股研究分析师",
    "Portfolio Manager": "投资组合经理",
    "Research Manager": "研究经理",
    "Trader": "交易员",
    "Judge": "裁决者",
}


ROLE_VARIANT_NAMES: dict[str, set[str]] = {
    "Bull Analyst": {"Bull Analyst", "Bull Researcher", "多头分析师"},
    "Bull Researcher": {"Bull Analyst", "Bull Researcher", "多头分析师"},
    "Bear Analyst": {"Bear Analyst", "Bear Researcher", "空头分析师"},
    "Bear Researcher": {"Bear Analyst", "Bear Researcher", "空头分析师"},
    "Aggressive Analyst": {"Aggressive Analyst", "激进分析师", "激进风险分析师"},
    "Conservative Analyst": {"Conservative Analyst", "保守分析师", "保守风险分析师"},
    "Neutral Analyst": {"Neutral Analyst", "中性分析师", "中性风险分析师"},
    "Market & Flow Analyst": {"Market & Flow Analyst", "Market Analyst", "市场与资金流分析师", "市场分析师"},
    "Sentiment & Catalyst Analyst": {"Sentiment & Catalyst Analyst", "Social Analyst", "舆情与事件分析师", "社交情绪分析师"},
    "Macro Analyst": {"Macro Analyst", "News Analyst", "宏观分析师", "新闻分析师"},
    "Macro Regime Analyst": {"Macro Regime Analyst", "Macro Analyst", "News Analyst", "宏观框架分析师", "宏观分析师", "新闻分析师"},
    "Commodity Analyst": {"Commodity Analyst", "Meso Commodity Analyst", "ETF Structure Analyst", "商品集群分析师", "中观大宗商品分析师", "ETF结构分析师"},
    "Meso Commodity Analyst": {"Commodity Analyst", "Meso Commodity Analyst", "ETF Structure Analyst", "商品集群分析师", "中观大宗商品分析师", "ETF结构分析师"},
    "ETF Structure Analyst": {"ETF Structure Analyst", "ETF结构分析师"},
    "ETF Flow Analyst": {"ETF Flow Analyst", "ETF资金流分析师"},
    "ETF Macro Analyst": {"ETF Macro Analyst", "ETF宏观暴露分析师"},
    "Industry Research Analyst": {
        "Industry Research Analyst",
        "ETF Industry Research Analyst",
        "ETF Holdings-Industry Research Analyst",
        "Broker Research Analyst",
        "行业研究分析师",
        "ETF行业研究分析师",
        "ETF持仓映射行业研究分析师",
        "券商研报分析师",
    },
    "Stock Research Analyst": {
        "Stock Research Analyst",
        "ETF Top Holdings Research Analyst",
        "个股研究分析师",
        "个股研报分析师",
        "ETF头部企业研究分析师",
        "ETF头部成分股研究分析师",
    },
    "Portfolio Manager": {"Portfolio Manager", "投资组合经理"},
    "Research Manager": {"Research Manager", "研究经理"},
    "Trader": {"Trader", "交易员"},
    "Judge": {"Judge", "裁决者"},
}


def localize_role_name(role: str) -> str:
    return ROLE_LOCALIZATION_MAP.get(role, role) if _is_chinese_output() else role


_CIRCLED_DIGIT_MAP = {
    "①": "1",
    "②": "2",
    "③": "3",
    "④": "4",
    "⑤": "5",
    "⑥": "6",
    "⑦": "7",
    "⑧": "8",
    "⑨": "9",
    "⑩": "10",
}
_CHINESE_NUMBERING_MAP = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_CHINESE_DIGIT_VALUES = {
    "零": 0,
    "〇": 0,
    "○": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_SMALL_UNITS = {"十": 10, "百": 100, "千": 1000}
_CHINESE_LARGE_UNITS = {"万": 10_000, "亿": 100_000_000}
_CHINESE_NUMERIC_TOKEN_RE = r"[负零〇○一二两三四五六七八九十百千万亿点]+"
_CHINESE_BASE_NUMERIC_TOKEN_RE = r"[负零〇○一二两三四五六七八九十百点]+"
_CHINESE_DIGIT_SEQUENCE_RE = r"[零〇○一二两三四五六七八九]{2,}"
_CHINESE_COMPOSITE_CURRENCY_TOKEN_RE = (
    r"[负零〇○一二两三四五六七八九十百千点]+亿(?:零?[负零〇○一二两三四五六七八九十百千点]+)?万"
)
_CHINESE_APPROX_PREFIX_RE = r"(?:近|约|大约|约莫|将近|接近|不到|不足|超|超过|逾|至少)"
_CHINESE_APPROX_SUFFIX_RE = r"(?:余|多|几|来)"
_NUMERIC_UNIT_OPTIONS = tuple(
    sorted(
        {
            "亿美元",
            "亿港元",
            "亿元",
            "万元",
            "美元",
            "港元",
            "元",
            "日均线",
            "周均线",
            "月均线",
            "年均线",
            "均线",
            "日线",
            "周线",
            "月线",
            "个月",
            "小时",
            "分钟",
            "秒",
            "时",
            "天",
            "周",
            "年",
            "月",
            "日",
            "手",
            "股",
            "倍",
            "太",
        },
        key=len,
        reverse=True,
    )
)
_NUMERIC_UNIT_RE = "|".join(re.escape(unit) for unit in _NUMERIC_UNIT_OPTIONS)
_RISK_ACTION_RATING_RULES = (
    ("卖出", (r"立即止损", r"清仓", r"全部卖出", r"坚决卖出")),
    (
        "减持",
        (
            r"减仓",
            r"减持",
            r"分批卖出",
            r"逐步减仓",
            r"小幅减仓",
            r"坚决减仓",
            r"降低敞口",
            r"保留底仓",
            r"底仓",
            r"对冲",
            r"动态对冲",
            r"保护性对冲",
            r"锁定利润",
        ),
    ),
    ("买入", (r"坚决买入", r"分批建仓", r"满仓做多", r"激进加仓")),
    ("增持", (r"小幅加仓", r"加仓", r"增持", r"提高仓位", r"扩大仓位")),
    ("持有", (r"设止损后持有", r"谨慎持有", r"持仓不动", r"维持现仓", r"谨慎观望", r"分批调整", r"持有", r"观望")),
)


def normalize_display_numbering(text: str) -> str:
    """Normalize awkward visible numbering while preserving Chinese heading numerals."""
    if not text:
        return ""

    normalized = text
    for circled, digit in _CIRCLED_DIGIT_MAP.items():
        normalized = re.sub(
            rf"{re.escape(circled)}\s*",
            f"{digit}. ",
            normalized,
        )
    return normalized


def _chinese_integer_to_int(token: str) -> int:
    normalized = (token or "").replace("两", "二").replace("〇", "零").replace("○", "零")
    if not normalized:
        return 0

    total = 0
    section = 0
    number = 0
    for char in normalized:
        if char in _CHINESE_DIGIT_VALUES:
            number = _CHINESE_DIGIT_VALUES[char]
            continue
        if char in _CHINESE_SMALL_UNITS:
            if number == 0:
                number = 1
            section += number * _CHINESE_SMALL_UNITS[char]
            number = 0
            continue
        if char in _CHINESE_LARGE_UNITS:
            section = (section + number) * _CHINESE_LARGE_UNITS[char]
            total += section
            section = 0
            number = 0
    return total + section + number


def _convert_chinese_numeric_token(token: str) -> str:
    token = (token or "").strip()
    if not token:
        return token

    sign = ""
    if token.startswith("负"):
        sign = "-"
        token = token[1:]

    if "点" in token:
        integer_part, decimal_part = token.split("点", 1)
        integer_value = _chinese_integer_to_int(integer_part or "零")
        decimals = "".join(
            str(_CHINESE_DIGIT_VALUES[ch])
            for ch in decimal_part
            if ch in _CHINESE_DIGIT_VALUES
        )
        if decimals:
            return f"{sign}{integer_value}.{decimals}"
        return f"{sign}{integer_value}"

    return f"{sign}{_chinese_integer_to_int(token)}"


def _convert_chinese_digit_sequence(token: str) -> str | None:
    token = (token or "").strip()
    if not token:
        return None

    normalized = token.replace("两", "二").replace("〇", "零").replace("○", "零")
    if not re.fullmatch(_CHINESE_DIGIT_SEQUENCE_RE, normalized):
        return None
    return "".join(str(_CHINESE_DIGIT_VALUES[ch]) for ch in normalized)


def _safe_convert_chinese_numeric_token(token: str) -> str | None:
    token = (token or "").strip()
    if not token:
        return None

    normalized = token.replace("两", "二").replace("〇", "零").replace("○", "零")
    if re.fullmatch(_CHINESE_DIGIT_SEQUENCE_RE, normalized):
        return None
    if re.fullmatch(r"负?[万亿]+", normalized):
        return None

    converted = _convert_chinese_numeric_token(token)
    if converted in {"0", "-0"} and not re.fullmatch(r"负?[零]+", normalized):
        return None
    return converted


def _protect_chinese_approximate_expressions(text: str) -> tuple[str, list[str]]:
    protected: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__CN_APPROX_{len(protected) - 1}__"

    protected_text = re.sub(
        rf"(?<![第0-9.])({_CHINESE_NUMERIC_TOKEN_RE})({_CHINESE_APPROX_SUFFIX_RE})({_NUMERIC_UNIT_RE})(以上|以下|以内|以外|左右|上下)?",
        _stash,
        text,
    )
    protected_text = re.sub(
        rf"(?<![第0-9.])({_CHINESE_APPROX_PREFIX_RE})({_CHINESE_NUMERIC_TOKEN_RE})({_NUMERIC_UNIT_RE})(以上|以下|以内|以外|左右|上下)?",
        _stash,
        protected_text,
    )
    return protected_text, protected


def _restore_chinese_approximate_expressions(text: str, protected: list[str]) -> str:
    restored = text
    for index, original in enumerate(protected):
        restored = restored.replace(f"__CN_APPROX_{index}__", original)
    return restored


def normalize_chinese_identifier_codes(text: str) -> str:
    """Normalize Chinese-spelled codes and digit-by-digit years to Arabic forms."""
    if not text or not _is_chinese_output():
        return text or ""

    normalized = text

    normalized = re.sub(
        rf"(?<![A-Za-z0-9])({_CHINESE_DIGIT_SEQUENCE_RE})\s*(?:点|\.|．)\s*([A-Za-z]{{1,5}})(?![A-Za-z])",
        lambda match: (
            f"{converted}.{match.group(2).upper()}"
            if (converted := _convert_chinese_digit_sequence(match.group(1)))
            else match.group(0)
        ),
        normalized,
    )
    normalized = re.sub(
        rf"((?:证券代码|股票代码|代码|代号)\s*(?:为|是)?\s*[:：]?\s*)({_CHINESE_DIGIT_SEQUENCE_RE})(?![A-Za-z0-9])",
        lambda match: (
            f"{match.group(1)}{converted}"
            if (converted := _convert_chinese_digit_sequence(match.group(2)))
            else match.group(0)
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![0-9])({_CHINESE_DIGIT_SEQUENCE_RE})年({_CHINESE_NUMERIC_TOKEN_RE})月({_CHINESE_NUMERIC_TOKEN_RE})日",
        lambda match: (
            f"{year}年{month}月{day}日"
            if (
                (year := _convert_chinese_digit_sequence(match.group(1))) is not None
                and (month := _convert_chinese_numeric_token(match.group(2)))
                and (day := _convert_chinese_numeric_token(match.group(3)))
            )
            else match.group(0)
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![0-9])({_CHINESE_DIGIT_SEQUENCE_RE})年({_CHINESE_NUMERIC_TOKEN_RE})月",
        lambda match: (
            f"{year}年{month}月"
            if (
                (year := _convert_chinese_digit_sequence(match.group(1))) is not None
                and (month := _convert_chinese_numeric_token(match.group(2)))
            )
            else match.group(0)
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![0-9])({_CHINESE_DIGIT_SEQUENCE_RE})年",
        lambda match: (
            f"{year}年"
            if (year := _convert_chinese_digit_sequence(match.group(1))) is not None
            else match.group(0)
        ),
        normalized,
    )
    return normalized


def _format_decimal_plain(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _decimal_places(value: Decimal) -> int:
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    return -exponent if exponent < 0 else 0


def _normalize_large_arabic_currency_units(text: str) -> str:
    if not text:
        return ""

    unit_map = {
        "元": ("亿元", "万元"),
        "美元": ("亿美元", "万美元"),
        "港元": ("亿港元", "万港元"),
    }

    def _rewrite(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        amount_text = match.group(2)
        currency = match.group(3)
        suffix = match.group(4) or ""

        try:
            amount = Decimal(amount_text.replace(",", ""))
        except InvalidOperation:
            return match.group(0)

        abs_amount = abs(amount)
        high_unit, low_unit = unit_map[currency]

        if abs_amount >= Decimal("100000000"):
            high_value = amount / Decimal("100000000")
            if _decimal_places(high_value) <= 2:
                return f"{prefix}{_format_decimal_plain(high_value)}{high_unit}{suffix}"

        if abs_amount >= Decimal("10000"):
            low_value = amount / Decimal("10000")
            if _decimal_places(low_value) <= 2:
                return f"{prefix}{_format_decimal_plain(low_value)}{low_unit}{suffix}"

        return match.group(0)

    return re.sub(
        rf"(?<![0-9A-Za-z.])({_CHINESE_APPROX_PREFIX_RE})?(-?\d{{5,}}(?:\.\d+)?)(元|美元|港元)(以上|以下|以内|以外|左右|上下)?",
        _rewrite,
        text,
    )


def normalize_chinese_numeric_expressions(text: str) -> str:
    """Normalize visible Chinese numerals per publishing conventions."""
    if not text or not _is_chinese_output():
        return text or ""

    normalized = normalize_chinese_identifier_codes(text)
    normalized, protected = _protect_chinese_approximate_expressions(normalized)
    normalized = re.sub(
        rf"百分之({_CHINESE_NUMERIC_TOKEN_RE})(?:至|到|—|－|-|~|～)百分之({_CHINESE_NUMERIC_TOKEN_RE})(以上|以下|以内|以外|左右|上下)?",
        lambda match: (
            (
                f"{start}%—{end}%{match.group(3) or ''}"
                if (
                    (start := _safe_convert_chinese_numeric_token(match.group(1))) is not None
                    and (end := _safe_convert_chinese_numeric_token(match.group(2))) is not None
                )
                else match.group(0)
            )
        ),
        normalized,
    )
    normalized = re.sub(
        rf"百分之({_CHINESE_NUMERIC_TOKEN_RE})(以上|以下|以内|以外|左右|上下)?",
        lambda match: (
            (
                f"{converted}%{match.group(2) or ''}"
                if (converted := _safe_convert_chinese_numeric_token(match.group(1)))
                else match.group(0)
            )
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![第0-9.])({_CHINESE_COMPOSITE_CURRENCY_TOKEN_RE})(美元|港元|元)(以上|以下|以内|以外|左右|上下)?",
        lambda match: (
            (
                f"{converted}{match.group(2)}{match.group(3) or ''}"
                if (converted := _safe_convert_chinese_numeric_token(match.group(1)))
                else match.group(0)
            )
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![第0-9.])({_CHINESE_BASE_NUMERIC_TOKEN_RE})(亿|万)(美元|港元|元)(以上|以下|以内|以外|左右|上下)?",
        lambda match: (
            (
                f"{converted}{match.group(2)}{match.group(3)}{match.group(4) or ''}"
                if (converted := _safe_convert_chinese_numeric_token(match.group(1)))
                else match.group(0)
            )
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![第0-9.])({_CHINESE_NUMERIC_TOKEN_RE})(美元|港元|元)(以上|以下|以内|以外|左右|上下)?",
        lambda match: (
            (
                f"{converted}{match.group(2)}{match.group(3) or ''}"
                if (converted := _safe_convert_chinese_numeric_token(match.group(1)))
                else match.group(0)
            )
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![第0-9.])({_CHINESE_NUMERIC_TOKEN_RE})(?:至|到|—|－|-|~|～)({_CHINESE_NUMERIC_TOKEN_RE})({_NUMERIC_UNIT_RE})(以上|以下|以内|以外|左右|上下)?",
        lambda match: (
            (
                f"{start}—{end}{match.group(3)}{match.group(4) or ''}"
                if (
                    (start := _safe_convert_chinese_numeric_token(match.group(1))) is not None
                    and (end := _safe_convert_chinese_numeric_token(match.group(2))) is not None
                )
                else match.group(0)
            )
        ),
        normalized,
    )
    normalized = re.sub(
        rf"(?<![第0-9.])({_CHINESE_NUMERIC_TOKEN_RE})({_NUMERIC_UNIT_RE})(以上|以下|以内|以外|左右|上下)?",
        lambda match: (
            (
                f"{converted}{match.group(2)}{match.group(3) or ''}"
                if (converted := _safe_convert_chinese_numeric_token(match.group(1)))
                else match.group(0)
            )
        ),
        normalized,
    )
    normalized = _restore_chinese_approximate_expressions(normalized, protected)
    return _normalize_large_arabic_currency_units(normalized)


def normalize_chinese_finance_terms(text: str) -> str:
    """Normalize mixed Chinese/English finance terms in visible Chinese output."""
    if not text or not _is_chinese_output():
        return text or ""

    replacements = (
        (r"\bForward PE Status\b", "前瞻市盈率状态"),
        (r"\bForward EPS\b", "前瞻每股收益"),
        (r"\bForward PE\b", "前瞻市盈率"),
        (r"\bforward EPS\b", "前瞻每股收益"),
        (r"\bforward PE\b", "前瞻市盈率"),
        (r"\bForward Valuation\b", "前瞻估值"),
        (r"\bforward valuation\b", "前瞻估值"),
        (r"\bforward earnings\b", "前瞻业绩"),
        (r"\bEarnings Guidance\b", "业绩指引"),
        (r"\bearnings guidance\b", "业绩指引"),
        (r"\bquarterly earnings\b", "单季度业绩"),
        (r"\bquarterly results\b", "单季度业绩"),
        (r"\bquarterly report\b", "季度报告"),
        (r"\bquarterly guidance\b", "单季度指引"),
        (r"\bquarterly balance sheet\b", "季度资产负债表"),
        (r"\bquarterly cashflow\b", "季度现金流量表"),
        (r"\bquarterly income statement\b", "季度利润表"),
        (r"\bcompany profile\b", "公司概况"),
        (r"\bmain business\b", "主营业务"),
        (r"\bbusiness mix\b", "业务结构"),
        (r"\bsegment mix\b", "业务结构"),
        (r"\bpeer sample\b", "同业样本"),
        (r"\bCapex Cash Outflow\b", "资本开支现金流出"),
        (r"\bcapex cash outflow\b", "资本开支现金流出"),
        (r"\bCapex\b", "资本开支"),
        (r"\bCAPEX\b", "资本开支"),
        (r"\bcapex\b", "资本开支"),
        (r"\bScalability\b", "规模扩张能力"),
        (r"\bscalability\b", "规模扩张能力"),
        (r"\bclose_10_ema\b", "10日EMA"),
        (r"\bclose_50_sma\b", "50日SMA"),
        (r"\bclose_200_sma\b", "200日SMA"),
        (r"\bboll_ub\b", "布林带上轨"),
        (r"\bboll_lb\b", "布林带下轨"),
        (r"\bboll\b", "布林带中轨"),
        (r"\bmacds\b", "MACD信号线"),
        (r"\bmacdh\b", "MACD柱状图"),
        (r"\bmacd\b", "MACD"),
        (r"\batr\b", "ATR波动率"),
        (r"\bvwma\b", "成交量加权移动平均线"),
        (r"\bForward\b", "前瞻"),
        (r"\bforward\b", "前瞻"),
        (r"\bquarterly\b", "季度"),
    )

    normalized = text
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)

    return (
        normalized.replace("全轮次交锋", "全轮次辩论")
        .replace("多轮交锋", "多轮辩论")
        .replace("交锋记录", "辩论记录")
    )


# Reverse mapping: Chinese → English (for always-include-both logic)
_ROLE_BOTH_NAMES: dict[str, set[str]] = {
    role: set(variants) for role, variants in ROLE_VARIANT_NAMES.items()
}


_CHINESE_SECTION_BREAK_PATTERN = re.compile(
    r"(?<=[^\n])(?=[一二三四五六七八九十]+、)"
    r"|(?<=[^\n])(?=（[一二三四五六七八九十\d]+）)"
)


def _ensure_chinese_section_breaks(text: str) -> str:
    """Insert newlines before Chinese section numbering that appears inline."""
    return _CHINESE_SECTION_BREAK_PATTERN.sub("\n", text)


def normalize_chinese_role_terms(text: str) -> str:
    """Normalize user-facing Chinese role terms to a single preferred wording."""
    if not text:
        return ""
    normalized = CHINESE_ROLE_TERM_PATTERN.sub(
        lambda match: CHINESE_ROLE_TERM_REPLACEMENTS[match.group(0)],
        text,
    )
    normalized = _normalize_risk_recommendation_text(normalized)
    normalized = normalize_display_numbering(normalized)
    normalized = normalize_chinese_numeric_expressions(normalized)
    normalized = _ensure_chinese_section_breaks(normalized)
    return normalize_chinese_finance_terms(normalized)


def localize_rating_term(term: str) -> str:
    mapping = {
        "Buy": "买入",
        "Overweight": "增持",
        "Hold": "持有",
        "Underweight": "减持",
        "Sell": "卖出",
        "BUY": "买入",
        "HOLD": "持有",
        "SELL": "卖出",
    }
    return mapping.get(term, term) if _is_chinese_output() else term


def get_localized_rating_scale() -> str:
    if _is_chinese_output():
        return """**评级体系**（只能选择一个）:
- **买入**: 对开仓或加仓有很强信心
- **增持**: 前景偏积极，建议逐步提高仓位
- **持有**: 维持当前仓位，暂不动作
- **减持**: 降低敞口，分批止盈或收缩仓位
- **卖出**: 退出仓位或避免入场"""

    return """**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry"""


def get_localized_final_proposal_instruction() -> str:
    if _is_chinese_output():
        return (
            "以明确的配置建议结束，最后一行必须使用格式："
            "'最终配置建议: **买入/增持/持有/减持/卖出**'。"
        )
    return (
        "End with a firm allocation decision and always conclude your response with "
        "'FINAL ALLOCATION PROPOSAL: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL**' to confirm your recommendation."
    )


def get_localized_execution_bias_instruction() -> str:
    if _is_chinese_output():
        return (
            "以明确的执行倾向结束，最后一行必须使用格式："
            "'执行倾向: **买入/增持/持有/减持/卖出**'。"
            "这里表达的是交易执行层的倾向，不要冒充最终投资组合决策。"
        )
    return (
        "End with a clear execution-bias line and always conclude your response with "
        "'EXECUTION BIAS: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL**'. "
        "This is an execution-layer stance, not the final portfolio decision."
    )


def get_localized_research_view_instruction() -> str:
    if _is_chinese_output():
        return (
            "在“持仓建议”部分只保留一个明确的研究结论行，使用格式："
            "'研究结论: **买入/增持/持有/减持/卖出**'。"
            "不要再额外重复“建议评级”“配置评级”或其他同义评级标签。"
        )
    return (
        "In the positioning section, keep exactly one explicit research-view line using "
        "'RESEARCH VIEW: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL**'. "
        "Do not repeat separate rating labels with different wording."
    )


def get_bear_proposal_instruction() -> str:
    """Consistency instruction for the Bear/Short Analyst.
    The conclusion must logically follow from the bearish arguments presented.
    """
    if _is_chinese_output():
        return (
            "在给出最终结论前，先自我审查：你的评级是否与你所列举的风险和负面证据一致？"
            "作为空头分析师，如果你的论点强调了下行风险，结论就应反映这一判断（通常为减持或卖出）。"
            "不允许出现论点强调风险、结论却比多头分析师还乐观的情形。"
            "在文末输出“决策摘要”块，并在其中给出“评级: 减持/卖出”（或在有力证据支撑时用“持有”）。"
        )
    return (
        "Before stating your conclusion, verify self-consistency: does your rating logically follow from the risks "
        "and downsides you've argued? As a Bear Analyst, if your argument emphasizes significant risks, your "
        "conclusion should reflect that (typically UNDERWEIGHT or SELL). You must not conclude more optimistically "
        "than your own arguments warrant — a bearish case cannot end with BUY or OVERWEIGHT. "
        "End with a 'DECISION SUMMARY' block whose rating is UNDERWEIGHT or SELL "
        "(or HOLD only when your arguments genuinely support a neutral stance)."
    )


def get_bull_proposal_instruction() -> str:
    """Consistency instruction for the Bull/Long Analyst.
    The conclusion must logically follow from the bullish arguments presented.
    """
    if _is_chinese_output():
        return (
            "在给出最终结论前，先自我审查：你的评级是否与你所列举的增长潜力和正面证据一致？"
            "作为多头分析师，如果你的论点强调了上行机会，结论就应反映这一判断（通常为买入或增持）。"
            "不允许出现论点强调机会、结论却比空头分析师还悲观的情形。"
            "在文末输出“决策摘要”块，并在其中给出“评级: 买入/增持”（或在有力证据支撑时用“持有”）。"
        )
    return (
        "Before stating your conclusion, verify self-consistency: does your rating logically follow from the "
        "growth potential and positive indicators you've argued? As a Bull Analyst, if your argument emphasizes "
        "strong upside, your conclusion should reflect that (typically BUY or OVERWEIGHT). You must not conclude "
        "more pessimistically than your own arguments warrant — a bullish case cannot end with SELL or UNDERWEIGHT. "
        "End with a 'DECISION SUMMARY' block whose rating is BUY or OVERWEIGHT "
        "(or HOLD only when your arguments genuinely support a neutral stance)."
    )


def get_analyst_decision_template() -> str:
    if _is_chinese_output():
        return """决策摘要:
- 评级:
- 置信度:
- 时间区间:
- 关键假设:
  1.
  2.
  3."""
    return """DECISION SUMMARY:
- Rating:
- Confidence:
- Time Horizon:
- Key Assumptions:
  1.
  2.
  3."""


def get_analyst_decision_instruction() -> str:
    if _is_chinese_output():
        return (
            "请在正文结束后、反馈快照之前，追加一个严格使用 Markdown 的“决策摘要”块。"
            "该块必须包含四项：评级、置信度、时间区间、关键假设（3条）。"
            "不要输出 XML、JSON、代码块、<final_answer> 标签，也不要输出英文标题 "
            "“Reflections from similar situations and lessons learned”。"
            "历史经验只允许内部吸收，不得在可见答案中直接引用、复述或翻译。"
        )
    return (
        "After the main argument and before the feedback snapshot, append a strict Markdown "
        "'DECISION SUMMARY' block with exactly four fields: Rating, Confidence, Time Horizon, "
        "and Key Assumptions (3 bullets). Do not output XML, JSON, code fences, or "
        "'<final_answer>' tags. Use past lessons internally only — do not quote or restate them."
    )


def get_aggressive_risk_instruction() -> str:
    """Consistency instruction for the Aggressive Risk Analyst.
    Natural tendency: bullish/aggressive, but any action is allowed if evidence warrants.
    The conclusion uses the dedicated '风险建议' format with pace/scale vocabulary.
    """
    if _is_chinese_output():
        return (
            "先自我审查：你「立场」字段是否与你本轮实际论点一致？"
            "作为激进风险分析师，你的自然倾向是寻找高回报机会，但若本轮证据确实指向风险，"
            "也可以选择逐步减仓或立即止损——重要的是结论与论点保持自洽，而非机械地执行激进立场。"
            "请在正文结尾处使用格式 '风险建议: **[行动]**'。"
            "若输出“决策摘要”，其中“评级”必须严格使用“买入/增持/持有/减持/卖出”五档之一，并与风险建议保持一致。\n"
            "风险建议的主动作必须与五档评级一一对应：买入=分批建仓，增持=小幅加仓，持有=维持现仓，减持=分批减仓，卖出=立即止损；不要混用跨档位动作。\n"
            "请从以下完整词汇表中选择最符合你本轮论点的行动，可加修饰词体现节奏、幅度和条件：\n激进加仓 / 坚决买入 / 分批建仓 / 满仓做多 / 小幅加仓 / 持仓不动 /\n维持现仓 / 谨慎观望 / 分批调整 / 设止损后持有 / 小幅减仓 /\n逐步减仓 / 分批卖出 / 谨慎持有 / 坚决减仓 / 立即止损\n示例：风险建议: **逐步减仓，控制回撤至5%以内**  或  风险建议: **分批建仓，首批仓位不超过30%**"
        )
    return (
        "Before appending the snapshot, verify self-consistency: does your 'Stance' field "
        "match what your arguments actually argued this round? "
        "As the Aggressive Analyst your natural lean is high-reward entry, but if evidence "
        "this round clearly points to risk, gradual reduction or a stop-loss is valid — "
        "what matters is that your conclusion is self-consistent, not mechanically aggressive. "
        "Conclude your main argument body with a line using format 'RISK RECOMMENDATION: **[action]**'. "
        "If you output a DECISION SUMMARY, its Rating must be exactly one of BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL and must align with the risk recommendation.\n"
        "The primary action in the risk recommendation must map cleanly to the 5-tier rating: BUY=Build in Batches, OVERWEIGHT=Add Selectively, HOLD=Maintain Position, UNDERWEIGHT=Trim in Batches, SELL=Immediate Stop-Loss. Do not mix actions from different tiers.\n"
        "Choose the action that best fits your argument this round from the full vocabulary below, adding modifiers for pace, scale, and conditions as needed:\nAggressively Accumulate / Decisively Buy / Build in Batches / Go All-In / Slightly Increase / Hold Firm /\nMaintain Position / Cautiously Observe / Adjust in Batches / Hold with Stop-Loss / Slightly Reduce /\nGradually Reduce / Sell in Batches / Hold with Caution / Decisively Reduce / Immediate Stop-Loss\nExample: RISK RECOMMENDATION: **Gradually Reduce, Cap Drawdown at 5%**  or  RISK RECOMMENDATION: **Build in Batches, Initial Position <=30%**"
    )

def get_conservative_risk_instruction() -> str:
    """Consistency instruction for the Conservative Risk Analyst.
    Natural tendency: cautious/defensive, but any action is allowed if evidence warrants.
    The conclusion uses the dedicated '风险建议' format with pace/scale vocabulary.
    """
    if _is_chinese_output():
        return (
            "先自我审查：你「立场」字段是否与你本轮实际论点一致？"
            "作为保守风险分析师，你的自然倾向是保护资产、控制回撤，但若本轮证据确实支持机会，"
            "也可以选择维持仓位甚至小幅加仓——重要的是结论与论点保持自洽，而非机械地执行保守立场。"
            "请在正文结尾处使用格式 '风险建议: **[行动]**'。"
            "若输出“决策摘要”，其中“评级”必须严格使用“买入/增持/持有/减持/卖出”五档之一，并与风险建议保持一致。\n"
            "风险建议的主动作必须与五档评级一一对应：买入=分批建仓，增持=小幅加仓，持有=维持现仓，减持=分批减仓，卖出=立即止损；不要混用跨档位动作。\n"
            "请从以下完整词汇表中选择最符合你本轮论点的行动，可加修饰词体现节奏、幅度和条件：\n激进加仓 / 坚决买入 / 分批建仓 / 满仓做多 / 小幅加仓 / 持仓不动 /\n维持现仓 / 谨慎观望 / 分批调整 / 设止损后持有 / 小幅减仓 /\n逐步减仓 / 分批卖出 / 谨慎持有 / 坚决减仓 / 立即止损\n示例：风险建议: **逐步减仓，控制回撤至5%以内**  或  风险建议: **分批建仓，首批仓位不超过30%**"
        )
    return (
        "Before appending the snapshot, verify self-consistency: does your 'Stance' field "
        "match what your arguments actually argued this round? "
        "As the Conservative Analyst your natural lean is capital protection, but if evidence "
        "this round genuinely supports a position, holding or a small increase is valid — "
        "what matters is that your conclusion is self-consistent, not mechanically cautious. "
        "Conclude your main argument body with a line using format 'RISK RECOMMENDATION: **[action]**'. "
        "If you output a DECISION SUMMARY, its Rating must be exactly one of BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL and must align with the risk recommendation.\n"
        "The primary action in the risk recommendation must map cleanly to the 5-tier rating: BUY=Build in Batches, OVERWEIGHT=Add Selectively, HOLD=Maintain Position, UNDERWEIGHT=Trim in Batches, SELL=Immediate Stop-Loss. Do not mix actions from different tiers.\n"
        "Choose the action that best fits your argument this round from the full vocabulary below, adding modifiers for pace, scale, and conditions as needed:\nAggressively Accumulate / Decisively Buy / Build in Batches / Go All-In / Slightly Increase / Hold Firm /\nMaintain Position / Cautiously Observe / Adjust in Batches / Hold with Stop-Loss / Slightly Reduce /\nGradually Reduce / Sell in Batches / Hold with Caution / Decisively Reduce / Immediate Stop-Loss\nExample: RISK RECOMMENDATION: **Gradually Reduce, Cap Drawdown at 5%**  or  RISK RECOMMENDATION: **Build in Batches, Initial Position <=30%**"
    )

def get_neutral_risk_instruction() -> str:
    """Consistency instruction for the Neutral Risk Analyst.
    Natural tendency: balanced, but any action is allowed if evidence clearly leans one way.
    The conclusion uses the dedicated '风险建议' format with pace/scale vocabulary.
    """
    if _is_chinese_output():
        return (
            "先自我审查：你「立场」字段是否与你本轮实际论点一致？"
            "作为中性风险分析师，你的自然倾向是平衡两方观点，但若本轮证据明确偏向某一侧，"
            "也可以选择激进加仓或坚决减仓——重要的是结论与论点保持自洽，而非机械地居中立场。"
            "请在正文结尾处使用格式 '风险建议: **[行动]**'。"
            "若输出“决策摘要”，其中“评级”必须严格使用“买入/增持/持有/减持/卖出”五档之一，并与风险建议保持一致。\n"
            "风险建议的主动作必须与五档评级一一对应：买入=分批建仓，增持=小幅加仓，持有=维持现仓，减持=分批减仓，卖出=立即止损；不要混用跨档位动作。\n"
            "请从以下完整词汇表中选择最符合你本轮论点的行动，可加修饰词体现节奏、幅度和条件：\n激进加仓 / 坚决买入 / 分批建仓 / 满仓做多 / 小幅加仓 / 持仓不动 /\n维持现仓 / 谨慎观望 / 分批调整 / 设止损后持有 / 小幅减仓 /\n逐步减仓 / 分批卖出 / 谨慎持有 / 坚决减仓 / 立即止损\n示例：风险建议: **逐步减仓，控制回撤至5%以内**  或  风险建议: **分批建仓，首批仓位不超过30%**"
        )
    return (
        "Before appending the snapshot, verify self-consistency: does your 'Stance' field "
        "match what your arguments actually argued this round? "
        "As the Neutral Analyst your natural lean is balance, but if evidence "
        "this round clearly favors one side, aggressive accumulation or decisive reduction is valid — "
        "what matters is that your conclusion is self-consistent, not mechanically neutral. "
        "Conclude your main argument body with a line using format 'RISK RECOMMENDATION: **[action]**'. "
        "If you output a DECISION SUMMARY, its Rating must be exactly one of BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL and must align with the risk recommendation.\n"
        "The primary action in the risk recommendation must map cleanly to the 5-tier rating: BUY=Build in Batches, OVERWEIGHT=Add Selectively, HOLD=Maintain Position, UNDERWEIGHT=Trim in Batches, SELL=Immediate Stop-Loss. Do not mix actions from different tiers.\n"
        "Choose the action that best fits your argument this round from the full vocabulary below, adding modifiers for pace, scale, and conditions as needed:\nAggressively Accumulate / Decisively Buy / Build in Batches / Go All-In / Slightly Increase / Hold Firm /\nMaintain Position / Cautiously Observe / Adjust in Batches / Hold with Stop-Loss / Slightly Reduce /\nGradually Reduce / Sell in Batches / Hold with Caution / Decisively Reduce / Immediate Stop-Loss\nExample: RISK RECOMMENDATION: **Gradually Reduce, Cap Drawdown at 5%**  or  RISK RECOMMENDATION: **Build in Batches, Initial Position <=30%**"
    )



def get_collaboration_stop_instruction() -> str:
    if _is_chinese_output():
        return (
            " 如果你或其他助手已经给出了最终结论，请在响应中包含："
            "'最终配置建议: **买入/增持/持有/减持/卖出**'，团队将以此为停止信号。"
        )
    return (
        " If you or any other assistant has the FINAL ALLOCATION PROPOSAL: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL** or deliverable,"
        " prefix your response with FINAL ALLOCATION PROPOSAL: **BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL** so the team knows to stop."
    )


SNAPSHOT_MARKERS = ("FEEDBACK SNAPSHOT:", "反馈快照:")
SNAPSHOT_TEMPLATE = get_snapshot_template()
DECISION_SUMMARY_MARKERS = ("DECISION SUMMARY:", "决策摘要:")
_XML_FINAL_ANSWER_RE = re.compile(
    r"```xml\s*(<final_answer>.*?</final_answer>)\s*```|(<final_answer>.*?</final_answer>)",
    re.IGNORECASE | re.DOTALL,
)
_REFLECTIONS_HEADING_RE = re.compile(
    r"\*{0,2}Reflections from similar situations and lessons learned:?\*{0,2}",
    re.IGNORECASE,
)
_RISK_RECOMMENDATION_RE = re.compile(
    r"(?:风险建议|RISK RECOMMENDATION)\s*[:：]\s*\**(.+?)\**(?:$|\n)",
    re.IGNORECASE,
)
CHINESE_RATING_EXPLICIT_PATTERNS = [
    ("买入", re.compile(r"(?:最终配置建议|最终交易建议|执行倾向|研究结论|配置评级|评级)\s*[:：]\s*\**买入\**")),
    ("增持", re.compile(r"(?:最终配置建议|最终交易建议|执行倾向|研究结论|配置评级|评级)\s*[:：]\s*\**增持\**")),
    ("持有", re.compile(r"(?:最终配置建议|最终交易建议|执行倾向|研究结论|配置评级|评级)\s*[:：]\s*\**持有\**")),
    ("减持", re.compile(r"(?:最终配置建议|最终交易建议|执行倾向|研究结论|配置评级|评级)\s*[:：]\s*\**减持\**")),
    ("卖出", re.compile(r"(?:最终配置建议|最终交易建议|执行倾向|研究结论|配置评级|评级)\s*[:：]\s*\**卖出\**")),
    ("买入", re.compile(r"(?:立场|当前观点)\s*[:：]\s*\**买入(?:/增持)?\**")),
    ("增持", re.compile(r"(?:立场|当前观点)\s*[:：]\s*\**增持(?:/买入)?\**")),
    ("持有", re.compile(r"(?:立场|当前观点)\s*[:：]\s*\**持有\**")),
    ("减持", re.compile(r"(?:立场|当前观点)\s*[:：]\s*\**减持\**")),
    ("卖出", re.compile(r"(?:立场|当前观点)\s*[:：]\s*\**卖出\**")),
    ("买入", re.compile(r"(?:建议|维持|转为)\s*买入")),
    ("增持", re.compile(r"(?:建议|维持|转为)\s*增持")),
    ("持有", re.compile(r"(?:建议|维持|转为)\s*持有")),
    ("减持", re.compile(r"(?:建议|维持|转为)\s*减持")),
    ("卖出", re.compile(r"(?:建议|维持|转为)\s*卖出")),
]
CHINESE_RATING_NEGATION_PATTERN = re.compile(
    r"(不建议|不宜|不是|并非|避免|不要|勿|难言|无法|不能|非|不|别)\s*$"
)
CHINESE_RATING_HEURISTIC_PATTERNS = [
    ("卖出", re.compile(r"(清仓|退出(?:仓位|头寸)?|止损离场|果断卖出|卖出为主)")),
    ("减持", re.compile(r"(降低仓位|分批止盈|降低敞口|部分卖出|先减仓|逢高减仓|止盈减仓)")),
    ("增持", re.compile(r"(加仓|提高仓位|逢低布局|继续增持|扩大仓位)")),
    ("买入", re.compile(r"(买入机会|积极布局|值得买入|坚定看多|继续买入)")),
    ("持有", re.compile(r"(继续观察|暂不动作|维持仓位|等待确认|持仓观望)")),
]
ENGLISH_RATING_EXPLICIT_PATTERNS = [
    ("SELL", re.compile(r"(?:final allocation proposal|final transaction proposal|rating)\s*:\s*\**sell\**", re.IGNORECASE)),
    ("UNDERWEIGHT", re.compile(r"(?:final allocation proposal|final transaction proposal|rating)\s*:\s*\**underweight\**", re.IGNORECASE)),
    ("HOLD", re.compile(r"(?:final allocation proposal|final transaction proposal|rating)\s*:\s*\**hold\**", re.IGNORECASE)),
    ("OVERWEIGHT", re.compile(r"(?:final allocation proposal|final transaction proposal|rating)\s*:\s*\**overweight\**", re.IGNORECASE)),
    ("BUY", re.compile(r"(?:final allocation proposal|final transaction proposal|rating)\s*:\s*\**buy\**", re.IGNORECASE)),
    ("BUY", re.compile(r"(?:stance|current thesis)\s*:\s*\**buy(?:/overweight)?\**", re.IGNORECASE)),
    ("OVERWEIGHT", re.compile(r"(?:stance|current thesis)\s*:\s*\**overweight(?:/buy)?\**", re.IGNORECASE)),
    ("HOLD", re.compile(r"(?:stance|current thesis)\s*:\s*\**hold\**", re.IGNORECASE)),
    ("UNDERWEIGHT", re.compile(r"(?:stance|current thesis)\s*:\s*\**underweight\**", re.IGNORECASE)),
    ("SELL", re.compile(r"(?:stance|current thesis)\s*:\s*\**sell\**", re.IGNORECASE)),
    ("SELL", re.compile(r"(?:recommend|maintain|shift to|move to)\s+sell", re.IGNORECASE)),
    ("UNDERWEIGHT", re.compile(r"(?:recommend|maintain|shift to|move to)\s+underweight", re.IGNORECASE)),
    ("HOLD", re.compile(r"(?:recommend|maintain|shift to|move to)\s+hold", re.IGNORECASE)),
    ("OVERWEIGHT", re.compile(r"(?:recommend|maintain|shift to|move to)\s+overweight", re.IGNORECASE)),
    ("BUY", re.compile(r"(?:recommend|maintain|shift to|move to)\s+buy", re.IGNORECASE)),
]
ENGLISH_RATING_NEGATION_PATTERN = re.compile(
    r"(do not|don't|not|avoid|never|no|cannot|can't)\s*$",
    re.IGNORECASE,
)
ENGLISH_RATING_HEURISTIC_PATTERNS = [
    ("SELL", re.compile(r"(exit position|sell the stock|close the position|fully exit)", re.IGNORECASE)),
    ("UNDERWEIGHT", re.compile(r"(reduce exposure|trim the position|take partial profits)", re.IGNORECASE)),
    ("OVERWEIGHT", re.compile(r"(add to position|increase exposure|build the position)", re.IGNORECASE)),
    ("BUY", re.compile(r"(buy the stock|enter the position|strong upside)", re.IGNORECASE)),
    ("HOLD", re.compile(r"(maintain the position|wait for confirmation|stay on hold)", re.IGNORECASE)),
]


def _condense_excerpt(text: str, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _get_rating_patterns() -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("买入", ("最终配置建议: **买入**", "最终交易建议: **买入**", "执行倾向: **买入**", "研究结论: **买入**", "配置评级: 买入", "评级: 买入", "建议买入", "维持买入", "转为买入", "买入")),
        ("增持", ("最终配置建议: **增持**", "最终交易建议: **增持**", "执行倾向: **增持**", "研究结论: **增持**", "配置评级: 增持", "评级: 增持", "建议增持", "维持增持", "转为增持", "增持")),
        ("持有", ("最终配置建议: **持有**", "最终交易建议: **持有**", "执行倾向: **持有**", "研究结论: **持有**", "配置评级: 持有", "评级: 持有", "建议持有", "维持持有", "转为持有", "持有")),
        ("减持", ("最终配置建议: **减持**", "最终交易建议: **减持**", "执行倾向: **减持**", "研究结论: **减持**", "配置评级: 减持", "评级: 减持", "建议减持", "维持减持", "转为减持", "减持")),
        ("卖出", ("最终配置建议: **卖出**", "最终交易建议: **卖出**", "执行倾向: **卖出**", "研究结论: **卖出**", "配置评级: 卖出", "评级: 卖出", "建议卖出", "维持卖出", "转为卖出", "卖出")),
    ]


def _detect_risk_stance(text: str) -> str:
    content = normalize_chinese_role_terms(text or "")
    if not content.strip():
        return ""

    match = _RISK_RECOMMENDATION_RE.search(content)
    if match:
        return match.group(1).strip().strip("*").strip()
    return ""


def _detect_chinese_rating(text: str) -> str:
    content = normalize_chinese_role_terms(text or "")
    return _shared_detect_chinese_rating(content)


def _detect_english_rating(text: str) -> str:
    return _shared_detect_english_rating(text)


def _canonicalize_risk_action_rating(action: str) -> str:
    normalized = normalize_chinese_role_terms(action or "")
    if not normalized:
        return ""

    for rating, patterns in _RISK_ACTION_RATING_RULES:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return rating
    return ""


def _canonical_risk_recommendation_text(rating: str, chinese: bool = True) -> str:
    if chinese:
        mapping = {
            "买入": "分批建仓，积极布局",
            "增持": "小幅加仓，控制节奏",
            "持有": "维持现仓，等待确认信号",
            "减持": "分批减仓，控制回撤",
            "卖出": "立即止损，退出观察",
        }
        return mapping.get(rating, "")
    mapping = {
        "BUY": "Build in Batches, Lean Long",
        "OVERWEIGHT": "Add Selectively, Control Pace",
        "HOLD": "Maintain Position, Wait for Confirmation",
        "UNDERWEIGHT": "Trim in Batches, Control Drawdown",
        "SELL": "Stop Out, Stay Defensive",
    }
    return mapping.get(rating, "")


def _normalize_risk_recommendation_text(text: str) -> str:
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        marker = match.group(1)
        raw_action = match.group(2).strip().strip("*").strip()
        source_text = text
        if "风险建议" in marker:
            rating = _canonicalize_risk_action_rating(raw_action) or _shared_detect_chinese_rating(source_text)
            canonical_action = _canonical_risk_recommendation_text(rating, chinese=True) or raw_action
            return f"{marker} **{canonical_action}**"

        upper_action = raw_action.upper()
        rating = parse_rating(upper_action, default="HOLD")
        canonical_action = _canonical_risk_recommendation_text(rating, chinese=False) or raw_action
        return f"{marker} **{canonical_action}**"

    return re.sub(
        r"((?:风险建议|RISK RECOMMENDATION)\s*[:：])\s*\**(.+?)\**(?=$|\n)",
        _replace,
        text,
        flags=re.IGNORECASE,
    )


def _canonicalize_decision_rating(value: str, source_text: str = "") -> str:
    risk_rating = _canonicalize_risk_action_rating(_detect_risk_stance(source_text))
    if risk_rating:
        if _is_chinese_output():
            return risk_rating
        english_mapping = {
            "买入": "BUY",
            "增持": "OVERWEIGHT",
            "持有": "HOLD",
            "减持": "UNDERWEIGHT",
            "卖出": "SELL",
        }
        return english_mapping.get(risk_rating, risk_rating)

    if re.search(r"[A-Za-z]", value or "") and not re.search(r"[\u4e00-\u9fff]", value or ""):
        detected_english = _detect_english_rating(value)
        if detected_english:
            return detected_english

    if _is_chinese_output():
        return _detect_chinese_rating(value)
    return _detect_english_rating(value)


def _normalize_decision_fields(fields: dict[str, str], source_text: str = "") -> dict[str, str]:
    normalized_fields = {key: value.strip() for key, value in fields.items()}

    if _is_chinese_output():
        normalized_fields = {
            key: normalize_chinese_role_terms(value) if value else value
            for key, value in normalized_fields.items()
        }

    rating = _canonicalize_decision_rating(normalized_fields.get("rating", ""), source_text)
    if rating:
        normalized_fields["rating"] = rating
    return normalized_fields


def _extract_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[。！？!?\.])\s+|\n+", compact)
    return [part.strip() for part in parts if part.strip()]


def _pick_sentence(sentences: list[str], keywords: tuple[str, ...]) -> str:
    for sentence in sentences:
        if any(keyword in sentence for keyword in keywords):
            return _condense_excerpt(sentence, 120)
    return ""


def _strip_snapshot_discourse_openers(text: str) -> str:
    cleaned = _strip_any_role_prefix_from_value(text)
    cleaned = re.sub(r"^(?:各位|大家)[，,、:：!\s]*", "", cleaned)
    cleaned = re.sub(
        r"^(?:首先|其次|再看|另外|此外|最后|总体来看|总的来说|需要注意的是|值得注意的是|更重要的是|具体来说)[，,、:：\s]*",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"^(?:first|second|third|next|finally|overall|more importantly|in addition|however)\b[,\s:;.-]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _normalize_overlap_text(text: str) -> str:
    lowered = normalize_chinese_role_terms((text or "").lower())
    return re.sub(r"[\W_]+", "", lowered, flags=re.UNICODE)


def _contains_placeholder_snapshot(snapshot: str) -> bool:
    placeholders = (
        "未明确说明",
        "暂无",
        "同上",
        "无变化",
        "Not explicitly stated",
        "None yet",
        "same as above",
        "no change",
    )
    return any(token in snapshot for token in placeholders)


def _snapshot_output_is_chinese(chinese: bool | None = None) -> bool:
    return _is_chinese_output() if chinese is None else chinese


def _snapshot_uses_chinese(snapshot: str) -> bool:
    if SNAPSHOT_MARKERS[1] in snapshot:
        return True
    if SNAPSHOT_MARKERS[0] in snapshot:
        return False
    if re.search(r"- (?:立场|本轮新增与反驳|本轮新增|发生了什么变化|为什么变化|关键反驳|待验证|下一轮教训):", snapshot):
        return True
    if re.search(r"- (?:Stance|Current thesis|New this round & rebuttal|New this round|What changed|Why it changed|Key rebuttal|To verify|Lesson for next round):", snapshot):
        return False
    return _is_chinese_output()


def _snapshot_field_labels(chinese: bool | None = None) -> list[str]:
    if _snapshot_output_is_chinese(chinese):
        return ["立场", "本轮新增与反驳", "待验证"]
    return ["Stance", "New this round & rebuttal", "To verify"]


def _snapshot_field_aliases() -> dict[str, tuple[str, ...]]:
    return {
        # primary label first; legacy labels kept for backward-compatible parsing
        "stance": ("立场", "Stance", "当前观点", "Current thesis"),
        "new_and_rebuttal": (
            "本轮新增与反驳",
            "New this round & rebuttal",
            "本轮新增/反驳",
            "New this round / rebuttal",
            "本轮新增",
            "New this round",
            "发生了什么变化",
            "What changed",
            "为什么变化",
            "Why it changed",
            "关键反驳",
            "Key rebuttal",
        ),
        "to_verify": ("待验证", "To verify", "下一轮教训", "Lesson for next round"),
    }


def _decision_field_labels() -> list[str]:
    if _is_chinese_output():
        return ["评级", "置信度", "时间区间", "关键假设"]
    return ["Rating", "Confidence", "Time Horizon", "Key Assumptions"]


def _decision_field_aliases() -> dict[str, tuple[str, ...]]:
    return {
        "rating": ("评级", "Rating", "结论", "Conclusion"),
        "confidence": ("置信度", "Confidence", "Confidence Level"),
        "time_horizon": ("时间区间", "Time Horizon", "持有周期"),
        "key_assumptions": ("关键假设", "Key Assumptions"),
    }


def _empty_decision_fields() -> dict[str, str]:
    return {key: "" for key in _decision_field_aliases()}


def _parse_markdown_decision_fields(block: str) -> dict[str, str]:
    fields = _empty_decision_fields()
    if not block:
        return fields

    current_key = None
    for raw_line in block.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped in DECISION_SUMMARY_MARKERS:
            continue

        matched = False
        for field_key, aliases in _decision_field_aliases().items():
            for label in aliases:
                prefix = f"- {label}:"
                if stripped.startswith(prefix):
                    fields[field_key] = stripped[len(prefix):].strip()
                    current_key = field_key
                    matched = True
                    break
            if matched:
                break

        if matched:
            continue

        if current_key == "key_assumptions" and re.match(r"^(?:[-*]|\d+\.)\s+", stripped):
            existing = fields[current_key]
            fields[current_key] = (
                existing + ("\n" if existing else "") + stripped
            )
            continue

        if current_key and not stripped.startswith("-"):
            fields[current_key] = (fields[current_key] + " " + stripped).strip()

    return fields


def _parse_xml_decision_fields(text: str) -> dict[str, str]:
    fields = _empty_decision_fields()
    if not text:
        return fields

    match = _XML_FINAL_ANSWER_RE.search(text)
    if not match:
        return fields

    xml = match.group(1) or match.group(2) or ""
    tag_mapping = {
        "rating": ("conclusion",),
        "confidence": ("confidence_level",),
        "time_horizon": ("time_horizon",),
        "key_assumptions": ("key_assumptions",),
    }
    for field_key, tags in tag_mapping.items():
        for tag in tags:
            tag_match = re.search(
                rf"<{tag}>\s*(.*?)\s*</{tag}>",
                xml,
                re.IGNORECASE | re.DOTALL,
            )
            if tag_match:
                fields[field_key] = tag_match.group(1).strip()
                break

    assumptions = []
    if fields["key_assumptions"]:
        for line in fields["key_assumptions"].splitlines():
            cleaned = line.strip()
            if cleaned:
                assumptions.append(cleaned)
        fields["key_assumptions"] = "\n".join(assumptions)

    return fields


def _format_decision_summary_from_fields(fields: dict[str, str], source_text: str = "") -> str:
    normalized_fields = _normalize_decision_fields(fields, source_text=source_text)
    if not any(value.strip() for value in normalized_fields.values()):
        return ""

    title = DECISION_SUMMARY_MARKERS[1] if _is_chinese_output() else DECISION_SUMMARY_MARKERS[0]
    labels = _decision_field_labels()
    keys = list(_decision_field_aliases().keys())
    lines = [title]

    for key, label in zip(keys[:-1], labels[:-1]):
        value = normalized_fields.get(key, "").strip()
        if value:
            lines.append(f"- {label}: {value}")

    assumptions = normalized_fields.get("key_assumptions", "").strip()
    if assumptions:
        lines.append(f"- {labels[-1]}:")
        for line in assumptions.splitlines():
            lines.append(f"  {line.strip()}")

    return "\n".join(lines)


def extract_analyst_decision_summary(text: str) -> str:
    """Extract a structured analyst decision summary block, normalizing legacy XML."""
    if not text:
        return ""

    best_idx = -1
    best_marker = None
    for marker in DECISION_SUMMARY_MARKERS:
        idx = text.rfind(marker)
        if idx > best_idx:
            best_idx = idx
            best_marker = marker

    if best_idx != -1 and best_marker is not None:
        end = len(text)
        for marker in SNAPSHOT_MARKERS:
            idx = text.find(marker, best_idx)
            if idx != -1:
                end = min(end, idx)
        block = text[best_idx:end].strip()
        fields = _parse_markdown_decision_fields(block)
        normalized = _format_decision_summary_from_fields(fields, source_text=text)
        return normalized or block

    fields = _parse_xml_decision_fields(text)
    return _format_decision_summary_from_fields(fields, source_text=text)


def _strip_reflections_section(text: str) -> str:
    if not text:
        return ""
    match = _REFLECTIONS_HEADING_RE.search(text)
    if not match:
        return text

    start = match.start()
    end = len(text)
    for marker in (*DECISION_SUMMARY_MARKERS, *SNAPSHOT_MARKERS):
        idx = text.find(marker, match.end())
        if idx != -1:
            end = min(end, idx)
    return (text[:start] + text[end:]).strip()


def strip_analyst_decision_summary(text: str) -> str:
    """Remove decision-summary/meta blocks from visible analyst body text."""
    if not text:
        return ""

    cleaned = _strip_reflections_section(text)
    cleaned = _XML_FINAL_ANSWER_RE.sub("", cleaned)

    best_idx = -1
    for marker in DECISION_SUMMARY_MARKERS:
        idx = cleaned.rfind(marker)
        if idx > best_idx:
            best_idx = idx
    if best_idx != -1:
        cleaned = cleaned[:best_idx].rstrip()

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_ALL_ROLE_NAMES: tuple[str, ...] = tuple(
    sorted(
        {name for variants in ROLE_VARIANT_NAMES.values() for name in variants},
        key=len,
        reverse=True,
    )
)


def _strip_any_role_prefix_from_value(value: str) -> str:
    """Strip a leading role self-label and greeting from a snapshot field value.

    e.g. '保守分析师: 各位分析师好，我是保守风险分析师。针对...' → '针对...'
    """
    import re
    pattern = "|".join(re.escape(n) for n in _ALL_ROLE_NAMES)
    # Strip "rolename：/: " at the very start
    value = re.sub(r"^(?:" + pattern + r")[：:]\s*", "", value)
    # Strip common self-introduction sentences at the start:
    # e.g. "各位分析师好，我是保守风险分析师。" / "大家好，我是激进分析师。"
    value = re.sub(
        r"^(?:各位\S{0,6}好[，,。！!]?\s*)?(?:我是|作为)\S{2,12}(?:分析师|经理)[，,。！!。]\s*",
        "",
        value,
    )
    return value.strip()


def _parse_snapshot_fields(snapshot: str) -> dict[str, str]:
    fields = {key: "" for key in _snapshot_field_aliases()}
    if not snapshot:
        return fields

    chinese_snapshot = _snapshot_uses_chinese(snapshot)
    current_key = None
    for line in snapshot.splitlines():
        stripped = line.strip()
        matched = False
        for field_key, aliases in _snapshot_field_aliases().items():
            for label in aliases:
                prefix = f"- {label}:"
                if stripped.startswith(prefix):
                    new_value = stripped[len(prefix):].strip()
                    fields[field_key] = _merge_snapshot_field_values(
                        fields[field_key],
                        new_value,
                        chinese_snapshot,
                    )
                    current_key = field_key
                    matched = True
                    break
            if matched:
                break
        if not matched and current_key and stripped and not stripped.startswith("-"):
            # Continuation line for the current field — join with a space
            fields[current_key] = (fields[current_key] + " " + stripped).strip()

    # Strip role prefixes after full value is assembled
    for key in fields:
        fields[key] = _strip_any_role_prefix_from_value(fields[key])
    return fields


def _format_snapshot_from_fields(fields: dict[str, str], chinese: bool | None = None) -> str:
    title = SNAPSHOT_MARKERS[1] if _snapshot_output_is_chinese(chinese) else SNAPSHOT_MARKERS[0]
    labels = _snapshot_field_labels(chinese)
    lines = [title]
    for field_key, label in zip(_snapshot_field_aliases().keys(), labels):
        value = fields.get(field_key, "").strip()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _snapshot_has_missing_fields(snapshot: str) -> bool:
    fields = _parse_snapshot_fields(snapshot)
    for value in fields.values():
        normalized = value.strip()
        if not normalized:
            return True
        if normalized in {"。", ".", "...", "……", "-", "--"}:
            return True
    return False


def _merge_snapshot_with_inferred(
    snapshot: str,
    inferred_snapshot: str,
    replacement_fields: set[str] | None = None,
    chinese: bool | None = None,
) -> str:
    explicit = _parse_snapshot_fields(snapshot)
    inferred = _parse_snapshot_fields(inferred_snapshot)
    replacement_fields = replacement_fields or set()

    lines = [SNAPSHOT_MARKERS[1] if _snapshot_output_is_chinese(chinese) else SNAPSHOT_MARKERS[0]]
    display_labels = _snapshot_field_labels(chinese)
    for field_key, label in zip(_snapshot_field_aliases().keys(), display_labels):
        value = explicit.get(field_key, "").strip()
        if (
            not value
            or value in {"。", ".", "...", "……", "-", "--"}
            or field_key in replacement_fields
        ):
            value = inferred.get(field_key, "").strip()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _copied_snapshot_field_keys(snapshot: str, source_text: str) -> set[str]:
    fields = _parse_snapshot_fields(snapshot)
    body = _strip_snapshot_discourse_openers(
        normalize_chinese_role_terms(
            strip_analyst_decision_summary(strip_feedback_snapshot(source_text))
        )
    )
    normalized_body = _normalize_overlap_text(body)
    copied_fields = set()
    if not normalized_body:
        return copied_fields

    for field_key, value in fields.items():
        cleaned_value = _strip_snapshot_discourse_openers(value)
        normalized_value = _normalize_overlap_text(cleaned_value)
        if len(normalized_value) < 30:
            continue
        if normalized_value in normalized_body:
            copied_fields.add(field_key)
            continue
        if len(normalized_value) >= 45 and normalized_value[:45] in normalized_body:
            copied_fields.add(field_key)
    return copied_fields


def _snapshot_fields_substantially_overlap(left: str, right: str) -> bool:
    normalized_left = _normalize_overlap_text(_strip_snapshot_discourse_openers(left))
    normalized_right = _normalize_overlap_text(_strip_snapshot_discourse_openers(right))
    if len(normalized_left) < 24 or len(normalized_right) < 24:
        return False
    if normalized_left == normalized_right:
        return True

    shorter, longer = sorted((normalized_left, normalized_right), key=len)
    if len(shorter) >= 30 and shorter in longer:
        return True

    similarity = SequenceMatcher(
        None,
        normalized_left[:800],
        normalized_right[:800],
    ).ratio()
    if similarity >= 0.72:
        return True

    left_topics = set(_extract_snapshot_topics(left))
    right_topics = set(_extract_snapshot_topics(right))
    shared_topics = left_topics & right_topics

    number_pattern = r"\d+(?:\.\d+)?(?:%|％|亿|万|元|天)?"
    left_numbers = set(re.findall(number_pattern, left))
    right_numbers = set(re.findall(number_pattern, right))
    shared_numbers = left_numbers & right_numbers

    if shared_topics and shared_numbers:
        return True

    prefix_len = min(len(shorter), len(longer), 60)
    return prefix_len >= 36 and shorter[:prefix_len] == longer[:prefix_len]


def _snapshot_values_are_near_duplicates(left: str, right: str) -> bool:
    normalized_left = _normalize_overlap_text(_strip_snapshot_discourse_openers(left))
    normalized_right = _normalize_overlap_text(_strip_snapshot_discourse_openers(right))
    if not normalized_left or not normalized_right:
        return False
    if normalized_left == normalized_right:
        return True

    shorter, longer = sorted((normalized_left, normalized_right), key=len)
    if len(shorter) >= 24 and shorter in longer and len(shorter) >= int(len(longer) * 0.7):
        return True

    similarity = SequenceMatcher(
        None,
        normalized_left[:800],
        normalized_right[:800],
    ).ratio()
    return similarity >= 0.88


def _merge_snapshot_field_values(existing_value: str, new_value: str, chinese_snapshot: bool) -> str:
    existing_value = existing_value.strip()
    new_value = new_value.strip()
    if not existing_value:
        return new_value
    if not new_value:
        return existing_value
    if _snapshot_values_are_near_duplicates(existing_value, new_value):
        return existing_value if len(existing_value) >= len(new_value) else new_value
    separator = "；" if chinese_snapshot else "; "
    return f"{existing_value}{separator}{new_value}"


def _looks_like_snapshot_rebuttal(value: str) -> bool:
    normalized = normalize_chinese_role_terms((value or "").strip())
    if not normalized:
        return False
    if len(normalized) <= 80:
        return True

    keywords = (
        "对手", "空头分析师", "多头分析师", "激进风险分析师", "保守风险分析师", "中性风险分析师",
        "bull analyst", "bear analyst", "aggressive analyst", "conservative analyst",
        "neutral analyst", "忽略", "误判", "高估", "低估", "但", "然而", "却", "反驳",
        "质疑", "难以成立", "does not hold", "missed", "ignored", "however", "but ",
        "challenge", "rebut",
    )
    lowered = normalized.lower()
    return any(keyword in normalized or keyword in lowered for keyword in keywords)


def _looks_like_snapshot_new_content(value: str) -> bool:
    normalized = normalize_chinese_role_terms((value or "").strip())
    if not normalized:
        return False
    if len(normalized) <= 80:
        return True

    lowered = normalized.lower()
    bad_starts = (
        "空头分析师，", "多头分析师，", "激进风险分析师，", "保守风险分析师，", "中性风险分析师，",
        "bear analyst,", "bull analyst,", "aggressive analyst,", "conservative analyst,",
        "neutral analyst,",
        "我理解你对", "让我用", "各位", "大家", "我们必须",
    )
    if any(normalized.startswith(prefix) or lowered.startswith(prefix) for prefix in bad_starts):
        return False

    discourse_patterns = (
        r"^.{0,12}(?:分析师|manager)[，,:：]",
        r"^(?:我理解你对|让我用|各位|大家|首先|总的来说)",
    )
    return not any(re.search(pattern, normalized, re.IGNORECASE) for pattern in discourse_patterns)


def _looks_like_snapshot_verification(value: str) -> bool:
    normalized = normalize_chinese_role_terms((value or "").strip())
    if not normalized:
        return False

    if (
        normalized.startswith("**")
        or normalized.startswith("#")
        or "理性框架" in normalized
        or "decision framework" in normalized.lower()
    ):
        return False
    if len(normalized) <= 80:
        return True

    lowered = normalized.lower()
    keywords = (
        "跟踪", "验证", "观察", "等待", "确认", "关注", "若", "如果", "一旦", "突破", "跌破",
        "守稳", "高于", "低于", "阈值", "财报", "订单", "毛利率", "利润率", "量能", "成交量",
        "业绩", "指引", "track", "verify", "watch", "monitor", "confirm", "earnings",
        "orders", "margin", "volume", "guidance", "above", "below", "break", "if ",
    )
    if any(keyword in normalized or keyword in lowered for keyword in keywords):
        return True

    return False


def _snapshot_replacement_fields(snapshot: str, source_text: str) -> set[str]:
    fields = _parse_snapshot_fields(snapshot)
    replacement_fields = set(_copied_snapshot_field_keys(snapshot, source_text))

    new_and_rebuttal = fields.get("new_and_rebuttal", "")
    to_verify = fields.get("to_verify", "")

    if _snapshot_fields_substantially_overlap(new_and_rebuttal, to_verify):
        replacement_fields.add("to_verify")

    if new_and_rebuttal and not _looks_like_snapshot_new_content(new_and_rebuttal):
        replacement_fields.add("new_and_rebuttal")
    if to_verify and not _looks_like_snapshot_verification(to_verify):
        replacement_fields.add("to_verify")

    return replacement_fields


def is_feedback_snapshot_inferred(text: str) -> bool:
    """Return True when the displayed snapshot will be inferred from the body."""
    if not text or not text.strip():
        return True

    for marker in SNAPSHOT_MARKERS:
        idx = text.rfind(marker)
        if idx != -1:
            snapshot = text[idx:].strip()
            return (
                _contains_placeholder_snapshot(snapshot)
                or _snapshot_has_missing_fields(snapshot)
                or bool(_snapshot_replacement_fields(snapshot, text))
            )
    return True


def _extract_snapshot_topics(body: str, chinese: bool | None = None) -> list[str]:
    topics = []
    use_chinese = _snapshot_output_is_chinese(chinese)
    patterns = (
        (r"库存|存货", "库存与备货压力" if use_chinese else "inventory positioning"),
        (r"需求|订单|出货", "需求与订单兑现" if use_chinese else "demand and order conversion"),
        (r"金价|黄金", "金价走势" if use_chinese else "gold price trend"),
        (r"并购|收购|整合", "并购进度" if use_chinese else "M&A execution"),
        (r"地缘|关税|出口|海外", "地缘与海外政策风险" if use_chinese else "geopolitical and export-policy risk"),
        (r"价格战|定价权", "价格战下的定价权" if use_chinese else "pricing power through the price war"),
        (r"财报|业绩|一季报|q[1-4]", "业绩验证" if use_chinese else "earnings confirmation"),
        (r"储能", "储能需求兑现" if use_chinese else "storage-demand conversion"),
        (r"1\.6t|良率", "1.6T良率爬坡" if use_chinese else "1.6T yield ramp"),
        (r"估值|pe|市盈率", "高估值消化能力" if use_chinese else "valuation absorption"),
        (r"毛利率|利润率", "毛利率变化" if use_chinese else "margin trend"),
        (r"支撑|底部|macd|金叉|死叉", "技术支撑与动量修复" if use_chinese else "technical support and momentum repair"),
        (r"成交量|量能|放量|缩量|vwma", "量能确认" if use_chinese else "volume confirmation"),
        (r"情绪|热度|社交媒体|抢筹", "情绪热度" if use_chinese else "sentiment heat"),
        (r"资本开支|capex", "资本开支验证" if use_chinese else "capex follow-through"),
        (r"波动|atr|止损", "波动率与止损边界" if use_chinese else "volatility and stop-loss bands"),
    )
    lowered = body.lower()
    for pattern, topic in patterns:
        if re.search(pattern, lowered, re.IGNORECASE):
            topics.append(topic)
    return topics


def _infer_feedback_snapshot_from_body(
    text: str,
    paraphrase: bool = False,
    chinese: bool | None = None,
) -> str:
    body = _strip_snapshot_discourse_openers(
        normalize_chinese_role_terms(
            strip_analyst_decision_summary(strip_feedback_snapshot(text))
        )
    )
    sentences = _extract_sentences(body)
    first = _condense_excerpt(sentences[0], 120) if sentences else _condense_excerpt(body, 120)
    second = _condense_excerpt(sentences[1], 120) if len(sentences) > 1 else first
    use_chinese = _snapshot_output_is_chinese(chinese)
    topics = _extract_snapshot_topics(body, chinese=use_chinese)

    if use_chinese:
        rating = _detect_risk_stance(text) or _detect_chinese_rating(text)
        if paraphrase:
            joined_topics = "、".join(topics[:3]) if topics else f"“{rating}”逻辑"
            follow_up_topics = "、".join(topics[:3]) if topics else "关键数据与风险触发条件"
            new_and_rebuttal = (
                f"本轮新增了对{joined_topics}的归因和执行含义说明，并据此反驳对手把这些信号"
                f"线性等同于单边风险的推断，说明其结论仍需结合兑现节奏、盈利韧性和价格信号综合判断。"
            )
            to_verify = f"下一轮继续跟踪{follow_up_topics}这几项指标是否同步验证；若关键数据没有改善，就需要重新评估“{rating}”判断。"
        else:
            new_and_rebuttal = (
                _pick_sentence(sentences, ("新增", "补充", "转向", "强调", "原因", "估值", "库存", "需求", "订单"))
                or first
                or f"本轮围绕“{rating}”补充了关键证据、风险边界和执行依据。"
            )
            to_verify = (
                _pick_sentence(sentences, ("跟踪", "验证", "观察", "等待", "确认", "关注"))
                or (second if second and second != new_and_rebuttal else "")
                or f"下一轮验证支持“{rating}”的关键数据和风险触发条件。"
            )
        return (
            "反馈快照:\n"
            f"- 立场: {rating}\n"
            f"- 本轮新增与反驳: {new_and_rebuttal}\n"
            f"- 待验证: {to_verify}"
        )

    rating = _detect_english_rating(text)
    if paraphrase:
        joined_topics = ", ".join(topics[:3]) if topics else f"the {rating} thesis"
        new_and_rebuttal = (
            f"This round added clearer causality and execution context around {joined_topics}, and used that"
            f" incremental evidence to challenge the opposing side's one-way risk interpretation."
        )
        to_verify = f"Next round should verify whether {joined_topics} continue to improve enough to sustain the {rating} stance."
    else:
        new_and_rebuttal = (
            _pick_sentence(sentences, ("added", "new", "shifted", "because", "valuation", "demand", "inventory", "orders"))
            or first
            or f"Added key evidence, risk boundaries, and execution rationale behind the {rating} call."
        )
        to_verify = (
            _pick_sentence(sentences, ("track", "verify", "watch", "wait", "confirm", "monitor"))
            or (second if second and second != new_and_rebuttal else "")
            or f"Verify core data assumptions, risk triggers, and timing conditions behind the {rating} stance."
        )
    return (
        "FEEDBACK SNAPSHOT:\n"
        f"- Stance: {rating}\n"
        f"- New this round & rebuttal: {new_and_rebuttal}\n"
        f"- To verify: {to_verify}"
    )

def extract_feedback_snapshot(text: str) -> str:
    """Extract the structured feedback snapshot block from an agent response."""
    if not text:
        if _is_chinese_output():
            return "反馈快照:\n- 立场: 暂无。\n- 本轮新增与反驳: 暂无。\n- 待验证: 暂无。"
        return "FEEDBACK SNAPSHOT:\n- Stance: None yet.\n- New this round & rebuttal: None yet.\n- To verify: None yet."

    for marker in SNAPSHOT_MARKERS:
        idx = text.rfind(marker)
        if idx != -1:
            snapshot = text[idx:].strip()
            source_is_chinese = _snapshot_uses_chinese(snapshot)
            if _contains_placeholder_snapshot(snapshot):
                return _infer_feedback_snapshot_from_body(
                    text,
                    paraphrase=True,
                    chinese=source_is_chinese,
                )
            normalized_snapshot = normalize_chinese_role_terms(snapshot)
            replacement_fields = _snapshot_replacement_fields(normalized_snapshot, text)
            has_missing_fields = _snapshot_has_missing_fields(normalized_snapshot)
            if has_missing_fields or replacement_fields:
                inferred_snapshot = _infer_feedback_snapshot_from_body(
                    text,
                    paraphrase=True,
                    chinese=source_is_chinese,
                )
                return _merge_snapshot_with_inferred(
                    normalized_snapshot,
                    inferred_snapshot,
                    replacement_fields=replacement_fields,
                    chinese=source_is_chinese,
                )
            return _format_snapshot_from_fields(
                _parse_snapshot_fields(normalized_snapshot),
                chinese=source_is_chinese,
            )

    return _infer_feedback_snapshot_from_body(text, paraphrase=True)


def save_snapshot_file(
    snapshot: str,
    role: str,
    ticker: str,
    trade_date: str,
    round_num: int,
) -> str:
    """Save the full snapshot text to a dedicated file and return its path."""
    from etfagents.dataflows.config import get_config

    results_dir = get_config().get("results_dir", "./results")
    safe_ticker = ticker.replace("/", "_").replace("\\", "_")
    snap_dir = os.path.join(results_dir, safe_ticker, trade_date, "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    safe_role = role.lower().replace(" ", "_")
    filename = f"{safe_role}_round_{round_num}.md"
    path = os.path.join(snap_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {role} — Round {round_num} Snapshot\n\n")
        f.write(snapshot)
    return path


def load_snapshot_file(file_path: str) -> str:
    """Load snapshot content from a file. Returns empty string if missing."""
    if not file_path:
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _clean_snapshot_display_value(value: str) -> str:
    if not value:
        return ""

    if "；" in value:
        separator = "；"
        segments = value.split("；")
    elif ";" in value:
        separator = "; "
        segments = value.split(";")
    else:
        separator = ""
        segments = [value]

    cleaned_segments = []
    for segment in segments:
        cleaned = _strip_snapshot_discourse_openers(segment.strip())
        if cleaned:
            cleaned_segments.append(cleaned)

    if not cleaned_segments:
        return ""
    if not separator:
        return cleaned_segments[0]
    return separator.join(cleaned_segments)


def make_display_snapshot(
    full_snapshot: str,
    file_path: str = "",
    include_link: bool = False,
) -> str:
    """Create a brief inline display of the snapshot.

    Snapshot files remain available through the stored ``*_snapshot_path`` state,
    but user-facing displays hide file links by default to keep the report clean.
    """
    fields = _parse_snapshot_fields(full_snapshot)
    labels = _snapshot_field_labels()
    field_keys = list(_snapshot_field_aliases().keys())

    lines = []
    for key, label in zip(field_keys, labels):
        value = fields.get(key, "").strip()
        if value:
            cleaned_value = _clean_snapshot_display_value(value)
            lines.append(f"- {label}: {cleaned_value}")

    display = "\n".join(lines) if lines else full_snapshot[:200]
    if include_link and file_path:
        link_label = "完整内容见" if _is_chinese_output() else "Full snapshot"
        display += f"\n({link_label}: {file_path})"
    return display


def build_history_turn(raw_content: str, role: str) -> str:
    """Preserve the visible turn content, including structured blocks, for round history."""
    cleaned = strip_role_prefix((raw_content or "").strip(), role)
    speaker = localize_role_name(role)
    if not cleaned:
        return f"{speaker}:"
    return f"{speaker}: {cleaned}"


_VISIBLE_DEBATE_LIST_RE = re.compile(
    r"^\s*(?:[-*•]\s+|\d+\s*[.)、．]\s+|[（(]\d+[)）]\s+|[一二三四五六七八九十]+\s*[、.．]\s+)"
)


def normalize_visible_debate_body(text: str) -> str:
    """Normalize visible debate bodies for display without touching structured blocks."""
    content = (text or "").strip()
    if not content:
        return ""

    normalized_blocks = []
    for raw_block in re.split(r"\n\s*\n", content):
        lines = []
        list_line_count = 0
        for raw_line in raw_block.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
            line = re.sub(r"(?<!\*)\*\*(.+?)\*\*(?!\*)", r"\1", line)
            line = re.sub(r"(?<!_)__(.+?)__(?!_)", r"\1", line)
            line = re.sub(r"^\s*>+\s*", "", line)
            line = line.strip()
            if not line:
                continue
            lines.append(line)
            if _VISIBLE_DEBATE_LIST_RE.match(line):
                list_line_count += 1

        if not lines:
            continue

        is_list_like = len(lines) >= 2 and list_line_count >= max(2, len(lines) - 1)
        if is_list_like:
            cleaned_items = []
            for line in lines:
                item = _VISIBLE_DEBATE_LIST_RE.sub("", line).strip()
                if item:
                    cleaned_items.append(item)
            normalized_blocks.extend(cleaned_items)
            continue

        normalized_blocks.append("\n".join(lines))

    return collapse_blank_lines("\n\n".join(normalized_blocks).strip())


def rebuild_visible_debate_turn(
    body: str, decision_summary: str = "", snapshot: str = ""
) -> str:
    parts = [
        segment.strip()
        for segment in (body, decision_summary, snapshot)
        if segment and segment.strip()
    ]
    return "\n\n".join(parts).strip()


def strip_role_prefix(text: str, role: str) -> str:
    """Remove self-labeling role prefixes that the LLM may inject.

    Handles four patterns:
    1. Leading markdown heading containing the role name, e.g. '# 多头分析师辩论：...'
    2. Leading 'role: ' / 'role：' prefix at the start of the body
    3. Mid-text paragraphs that open with 'role：' / 'role: ' (inline self-labeling)
    4. Leading greeting sentences directed at another role, e.g. '你好，空头分析师。'
    """
    if not text:
        return text

    import re

    candidates = _ROLE_BOTH_NAMES.get(role, {role, localize_role_name(role)})
    ordered_candidates = sorted(candidates, key=len, reverse=True)
    candidate_pattern = "|".join(re.escape(name) for name in ordered_candidates)

    # 1. Strip leading markdown heading line(s) that contain the role name
    lines = text.split("\n")
    while lines and lines[0].lstrip().startswith("#") and any(
        name in lines[0] for name in candidates
    ):
        lines.pop(0)
    text = "\n".join(lines).lstrip()

    # 2. Strip leading 'role: ' / 'role：' prefix
    for name in candidates:
        for sep in ("：", ": ", ":", "- "):
            prefix = name + sep
            if text.startswith(prefix):
                text = text[len(prefix):].lstrip()
                break
        else:
            continue
        break

    # 3. Remove mid-text self-labeling: 'role：' or 'role: ' at the start of any line
    text = re.sub(r"(?m)^(?:" + candidate_pattern + r")[：:] *", "", text)

    # 4. Strip leading greeting sentences (e.g. '你好，空头分析师。' / '空头分析师，你好。')
    # Match one or two greeting sentences at the very start (up to first period/exclamation).
    _GREETING_RE = re.compile(
        r"^(?:"
        r"(?:你好|大家好|各位好|亲爱的)[，、,！!]?[^\n。！!?？]{0,30}[。！!?？\n]?"
        r"|[^\n，。！!?？]{0,20}[，,][你妳]好[。！!?？\n]?"
        r")\s*",
        re.UNICODE,
    )
    text = _GREETING_RE.sub("", text).lstrip()

    # 5. Strip repeated bare self-labels and explicit self-introductions.
    text = re.sub(
        r"^(?:(?:" + candidate_pattern + r")(?:[，,。！!：:\-]\s*)+)",
        "",
        text,
    ).lstrip()
    text = re.sub(
        r"^(?:我是|作为)(?:一名)?(?:" + candidate_pattern + r")(?:[，,。！!：:\-]\s*)*",
        "",
        text,
    ).lstrip()

    return text.strip()


def strip_feedback_snapshot(text: str) -> str:
    """Remove the feedback snapshot block from the visible argument body."""
    if not text:
        return ""
    best_idx = -1
    for marker in SNAPSHOT_MARKERS:
        idx = text.rfind(marker)
        if idx > best_idx:
            best_idx = idx
    if best_idx == -1:
        return text.strip()
    return text[:best_idx].strip()


def strip_all_feedback_snapshots(text: str) -> str:
    """Remove repeated feedback snapshot blocks from the visible body."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    while True:
        updated = strip_feedback_snapshot(cleaned)
        if updated == cleaned:
            return cleaned
        cleaned = updated


_MANAGER_INSTRUCTION_MARKERS = (
    "这一部分必须写成",
    "必须引用报告中的具体数据",
    "Give a clear, actionable ETF",
    "Include concrete execution guidance",
    "When writing in Chinese, avoid mixed English labels",
    "The rating, the positioning recommendation text, and the final transaction proposal",
    "Keep exactly one explicit final recommendation label",
)

_MANAGER_INSTRUCTION_INLINE_PATTERNS = (
    re.compile(r"这一部分必须写成连贯分析段落[^。]*。?"),
    re.compile(r"这一部分必须写成详细推理段落[^。]*。?"),
    re.compile(r"必须引用报告中的具体数据来支撑判断[^。]*。?"),
    re.compile(r"Give a clear, actionable ETF(?: portfolio)? recommendation[^.\n]*\.?"),
    re.compile(r"Include concrete execution guidance:[^\n]*"),
    re.compile(r"When writing in Chinese, avoid mixed English labels[^\n]*"),
    re.compile(r"The rating, the positioning recommendation text, and the final transaction proposal[^\n]*"),
    re.compile(r"Keep exactly one explicit final recommendation label[^\n]*"),
)


def strip_manager_instruction_leakage(text: str) -> str:
    """Remove prompt-instruction fragments that occasionally leak into manager output."""
    cleaned = text or ""
    if not cleaned:
        return ""

    cleaned = "\n".join(
        line
        for line in cleaned.splitlines()
        if not any(marker in line for marker in _MANAGER_INSTRUCTION_MARKERS)
    )
    for pattern in _MANAGER_INSTRUCTION_INLINE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _collapse_duplicate_markdown_headings(text: str) -> str:
    lines = (text or "").splitlines()
    if not lines:
        return ""

    deduped_lines = []
    last_heading_key = ""
    heading_open = False
    for line in lines:
        stripped = line.strip()
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if match:
            heading_key = re.sub(r"\s+", " ", match.group(2)).strip().lower()
            if heading_open and heading_key == last_heading_key:
                continue
            deduped_lines.append(line)
            last_heading_key = heading_key
            heading_open = True
            continue
        if stripped:
            heading_open = False
        deduped_lines.append(line)
    return "\n".join(deduped_lines).strip()


_MANAGER_SECTION_KEYS = {"辩论结论", "行为逻辑", "持仓建议", "研究结论"}
_RATING_ONLY_LINE_PATTERN = re.compile(
    r"^(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)\s*[:：]\s*\**(?:买入|增持|持有|减持|卖出)\**[。！!？?\s]*$"
)


def _normalize_manager_section_key(title: str) -> str:
    cleaned = (title or "").strip()
    cleaned = re.sub(r"^[一二三四五六七八九十]+[、.．]?\s*", "", cleaned)
    cleaned = re.sub(r"^[（(][一二三四五六七八九十\d]+[）)]\s*", "", cleaned)
    cleaned = re.sub(r"^\d+(?:\.\d+)*[、.．)）-]?\s*", "", cleaned)
    return re.sub(r"\s+", "", cleaned)


def _trim_section_lines(lines: list[str]) -> list[str]:
    trimmed = list(lines)
    while trimmed and not trimmed[0].strip():
        trimmed.pop(0)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def _default_manager_positioning_content(rating: str) -> str:
    mapping = {
        "BUY": (
            "先按目标仓位的一半到六成分批建仓，再把加仓动作绑定在价格站稳关键均线、成交量持续高于近20日均量、"
            "份额或资金流继续净流入的共振验证上。若价格重新跌回关键支撑下方或产品层确认信号转弱，则暂停扩仓并把仓位收回到底仓水平。"
        ),
        "OVERWEIGHT": (
            "在保留底仓基础上先把仓位提升到目标上限的七成到八成，只有在价格承接、量能、溢折价和份额变化继续同步改善时才进一步增配。"
            "若催化落空或资金承接转弱，则先回到基准仓位并重新评估是否继续保留超配。"
        ),
        "HOLD": (
            "维持当前仓位，不新增方向性敞口，把后续动作绑定在价格、量能、份额变化和产品结构信号的共同确认上。"
            "若验证链条继续改善，只做小幅上调；若关键支撑失守或资金流重新转弱，则先降回更保守的基准仓位。"
        ),
        "UNDERWEIGHT": (
            "以降低敞口为主，先把仓位压回风险预算下沿，反弹只有在量能与资金承接同步恢复时才允许暂缓减仓。"
            "若价格修复失败、溢折价走弱或行业盈利验证继续下修，则继续分批减仓并收缩风险预算。"
        ),
        "SELL": (
            "以退出仓位或避免入场为主，把剩余风险暴露压到最低，只有在基本面、价格结构和产品层信号共同修复后才考虑重新评估。"
            "若后续仍看不到量价承接与资金回流，则继续保持空仓或极低试探仓位。"
        ),
    }
    return mapping.get(rating, mapping["HOLD"])


def _dedupe_and_fill_manager_sections(text: str) -> str:
    lines = (text or "").splitlines()
    if not lines:
        return ""

    sections = []
    prefix_lines = []
    current_section = None
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    for line in lines:
        match = heading_pattern.match(line.strip())
        if match:
            key = _normalize_manager_section_key(match.group(2))
            if key in _MANAGER_SECTION_KEYS:
                current_section = {
                    "heading": line.strip(),
                    "key": key,
                    "lines": [],
                }
                sections.append(current_section)
                continue
        if current_section is None:
            prefix_lines.append(line)
        else:
            current_section["lines"].append(line)

    if not sections:
        return text.strip()

    merged_sections = []
    section_index_by_key: dict[str, int] = {}
    for section in sections:
        normalized_lines = _trim_section_lines(section["lines"])
        key = section["key"]
        if key not in section_index_by_key:
            merged_sections.append({
                "heading": section["heading"],
                "key": key,
                "lines": normalized_lines,
            })
            section_index_by_key[key] = len(merged_sections) - 1
            continue

        target = merged_sections[section_index_by_key[key]]
        new_block = "\n".join(normalized_lines).strip()
        existing_block = "\n".join(target["lines"]).strip()
        if not new_block or new_block == existing_block or new_block in existing_block:
            continue
        if target["lines"] and target["lines"][-1].strip():
            target["lines"].append("")
        target["lines"].extend(normalized_lines)

    rating = parse_rating(text, default="HOLD")
    for section in merged_sections:
        if section["key"] not in {"持仓建议", "研究结论"}:
            continue
        has_non_rating_content = any(
            line.strip() and not _RATING_ONLY_LINE_PATTERN.match(line.strip())
            for line in section["lines"]
        )
        if has_non_rating_content:
            continue
        if section["lines"] and section["lines"][-1].strip():
            section["lines"].append("")
        section["lines"].append(_default_manager_positioning_content(rating))

    rebuilt = _trim_section_lines(prefix_lines)
    for index, section in enumerate(merged_sections):
        if rebuilt:
            rebuilt.append("")
        rebuilt.append(section["heading"])
        rebuilt.extend(_trim_section_lines(section["lines"]))
        if index != len(merged_sections) - 1:
            rebuilt.append("")
    return "\n".join(rebuilt).strip()


def normalize_chinese_manager_terms(text: str) -> str:
    """Normalize Chinese manager wording without altering snapshot semantics."""
    normalized = normalize_chinese_role_terms(text or "")
    if not normalized or not _is_chinese_output():
        return normalized

    has_explicit_snapshot = any(marker in normalized for marker in SNAPSHOT_MARKERS)
    body = strip_manager_instruction_leakage(strip_all_feedback_snapshots(normalized))
    snapshot = extract_feedback_snapshot(normalized) if has_explicit_snapshot else ""
    replacements = (
        ("## Debate Verdict", "## 辩论结论"),
        ("## Debate Conclusion", "## 辩论结论"),
        ("## Risk Debate Conclusion", "## 辩论结论"),
        ("## Action Logic", "## 行为逻辑"),
        ("## Positioning Recommendation", "## 持仓建议"),
        ("## Research View", "## 研究结论"),
        ("## Executive Summary", "## 执行摘要"),
        ("## Investment Thesis", "## 投资逻辑"),
        ("Risk Debate Conclusion", "辩论结论"),
        ("Debate Verdict", "辩论结论"),
        ("Debate Conclusion", "辩论结论"),
        ("Action Logic", "行为逻辑"),
        ("Positioning Recommendation", "持仓建议"),
        ("Research View", "研究结论"),
        ("Executive Summary", "执行摘要"),
        ("Investment Thesis", "投资逻辑"),
        ("Time Horizon", "时间区间"),
        ("time horizon", "时间区间"),
        ("EXECUTION BIAS", "执行倾向"),
        ("FINAL ALLOCATION PROPOSAL", "最终配置建议"),
        ("FINAL TRANSACTION PROPOSAL", "最终配置建议"),
    )
    for source, target in replacements:
        body = body.replace(source, target)
    body = re.sub(
        r"(?<=\S)\s+(?=(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)\s*[:：])",
        "\n",
        body,
    )
    inline_rating_pattern = re.compile(
        r"(?:[ \t]+|(?<=[。！？!?；;]))[ \t]*(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)\s*[:：]\s*\**(?:买入|增持|持有|减持|卖出)\**[。！!？?\s]*$"
    )
    body = "\n".join(
        inline_rating_pattern.sub("", line).rstrip()
        for line in body.splitlines()
    )
    body = re.sub(r"\b[Cc]atalyst timing\b", "催化节奏", body)
    body = re.sub(r"\b[Tt]iming\b", "时机", body)
    body = (
        body.replace("本轮双方论点势均力敌", "整场辩论中双方论据势均力敌")
        .replace("本轮双方", "整场辩论双方")
        .replace("本轮辩论", "整场辩论")
    )
    body = re.sub(
        r"(?m)^((?:建议评级|评级|Recommendation|Rating)[:：][^\n]+)\n(?!\n|[#>*-]|\d+\.\s|最终配置建议|最终交易建议|FINAL ALLOCATION PROPOSAL|FINAL TRANSACTION PROPOSAL)(\S)",
        r"\1\n\n\2",
        body,
    )
    rating_lines = []
    for index, line in enumerate(body.splitlines()):
        stripped = line.strip()
        if re.match(
            r"^(?:建议评级|评级|配置评级|研究结论|执行倾向|最终配置建议|最终交易建议)\s*[:：]\s*[^。！？!?]{0,20}$",
            stripped,
        ):
            rating_lines.append((index, stripped))
    if len(rating_lines) > 1:
        preferred_index = rating_lines[-1][0]
        for idx, stripped in reversed(rating_lines):
            if stripped.startswith(("最终配置建议", "最终交易建议")):
                preferred_index = idx
                break
        deduped_lines = []
        for index, line in enumerate(body.splitlines()):
            if any(index == candidate for candidate, _ in rating_lines) and index != preferred_index:
                continue
            deduped_lines.append(line)
        body = "\n".join(deduped_lines)
    body = _dedupe_and_fill_manager_sections(
        _collapse_duplicate_markdown_headings(
            normalize_chinese_finance_terms(normalize_display_numbering(body)).strip()
        )
    )
    if snapshot:
        return collapse_blank_lines(f"{body}\n\n{snapshot}")
    return collapse_blank_lines(body)


def build_debate_brief(snapshots: dict[str, str], latest_speaker: str = "") -> str:
    """Build a compact cross-agent brief from the latest structured snapshots."""
    sections = []
    if latest_speaker:
        if _is_chinese_output():
            sections.append(f"最新更新来自: {localize_role_name(latest_speaker)}")
        else:
            sections.append(f"Latest update came from: {latest_speaker}")

    for speaker, snapshot in snapshots.items():
        if snapshot:
            if _is_chinese_output():
                sections.append(f"{localize_role_name(speaker)} 最新快照:\n{snapshot}")
            else:
                sections.append(f"{speaker} latest snapshot:\n{snapshot}")

    return "\n\n".join(sections).strip()


def synthesize_side_report(llm, role: str, full_history: str, snapshot: str) -> str:
    """Use the LLM to distill a debater's full multi-round history into a structured
    comprehensive position report for the manager to read.

    This replaces the raw 'last round only' approach with a coherent synthesis that
    captures argument evolution, strongest evidence, and final stance across all rounds.
    """
    if not full_history:
        return snapshot or ""

    role_label = localize_role_name(role) if _is_chinese_output() else role
    history_input = truncate_for_prompt(full_history, default_limit=12000)

    if _is_chinese_output():
        prompt = (
            f"以下是【{role_label}】在多轮辩论中的完整发言记录：\n\n"
            f"{history_input}\n\n"
            f"最新快照摘要（供参考）：\n{snapshot}\n\n"
            "请基于以上全部内容，生成一份结构化的【综合立场报告】，涵盖：\n"
            "1. **最终立场**：明确的评级及核心判断（1-2句）\n"
            "2. **核心论点**：跨轮次最有力的3-5个论点，附关键数据或事实支撑\n"
            "3. **主要反驳**：对对手观点最有效的反驳（2-3条）\n"
            "4. **立场演变**：若立场在辩论过程中有调整，简述原因\n"
            "5. **核心风险/机会**：一句话点明最关键的尾部风险或上行机会\n"
            "报告应客观、具体、有数据支撑，避免重复，控制在500字以内。"
        )
    else:
        prompt = (
            f"Below is the complete multi-round debate record from [{role_label}]:\n\n"
            f"{history_input}\n\n"
            f"Latest snapshot (for reference):\n{snapshot}\n\n"
            "Based on the full record above, produce a structured **Comprehensive Position Report** covering:\n"
            "1. **Final Stance**: Clear rating and core thesis (1-2 sentences)\n"
            "2. **Key Arguments**: The 3-5 strongest arguments across all rounds, with data/evidence\n"
            "3. **Main Rebuttals**: Most effective counter-arguments to the opponent (2-3 points)\n"
            "4. **Stance Evolution**: If the position shifted during debate, briefly explain why\n"
            "5. **Key Risk/Opportunity**: One sentence on the most critical tail risk or upside\n"
            "Be concrete, data-anchored, non-repetitive. Max 400 words."
        )

    try:
        response = llm.invoke(prompt)
        return extract_text_content(response.content)
    except Exception as exc:
        logger.warning("Side report synthesis failed for %s: %s", role, exc)
        return truncate_for_prompt(full_history, default_limit=4000)


def _resolve_company_name(ticker: str) -> str:
    """Best-effort lookup of the company name for a ticker.

    Tries Tushare first (accurate for Chinese A-shares / HK stocks), then
    falls back to yfinance.  Returns an empty string when both fail so the
    caller can decide whether to include the name.
    """
    # --- Tushare (A-share / HK) ---
    suffix = ticker.rsplit(".", 1)[-1].upper() if "." in ticker else ""
    if suffix in ("SH", "SZ", "BJ", "HK"):
        try:
            from etfagents.dataflows.tushare import _get_pro_client, _normalize_ts_code

            pro = _get_pro_client()
            ts_code = _normalize_ts_code(ticker)
            etf_df = pro.query("fund_basic", ts_code=ts_code)
            if etf_df is not None and not etf_df.empty and "name" in etf_df.columns:
                return str(etf_df["name"].iloc[0])
            df = pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
            if not df.empty:
                return df["name"].iloc[0]
        except Exception as exc:
            logger.debug("Tushare company name lookup failed for %s: %s", ticker, exc)

    # --- yfinance fallback ---
    try:
        import yfinance as yf
        _YF_MAP = {"SH": "SS", "SSE": "SS"}
        if "." in ticker:
            code, sfx = ticker.rsplit(".", 1)
            yf_sym = f"{code}.{_YF_MAP.get(sfx.upper(), sfx)}".upper()
        else:
            yf_sym = ticker.upper()
        info = yf.Ticker(yf_sym).info
        name = info.get("longName") or info.get("shortName") or ""
        return name
    except Exception as exc:
        logger.debug("yfinance company name lookup failed for %s: %s", ticker, exc)

    return ""


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    name = _resolve_company_name(ticker)
    name_clause = f" ({name})" if name else ""
    return (
        f"The instrument to analyze is `{ticker}`{name_clause}. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`). "
        "Never spell ticker digits in Chinese and never replace `.` with `点`."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
CHINESE_ROLE_TERM_REPLACEMENTS = {
    "熊派分析师": "空头分析师",
    "熊派投资者": "空头投资者",
    "熊观点": "空头观点",
    "熊派": "空头",
    "牛派分析师": "多头分析师",
    "牛派投资者": "多头投资者",
    "牛观点": "多头观点",
    "牛派": "多头",
    "激进分析师": "激进风险分析师",
    "保守分析师": "保守风险分析师",
    "中性分析师": "中性风险分析师",
    "根本分析": "基本面分析",
    "根本面分析": "基本面分析",
    "ETF持仓映射行业研究分析师": "行业研究分析师",
    "ETF头部企业研究分析师": "个股研究分析师",
    "ETF头部成分股研究分析师": "个股研究分析师",
    "个股研报分析师": "个股研究分析师",
    "辩论裁决": "辩论结论",
    "判决结果": "综合结论",
}
CHINESE_ROLE_TERM_PATTERN = re.compile(
    "|".join(
        sorted(
            (re.escape(term) for term in CHINESE_ROLE_TERM_REPLACEMENTS),
            key=len,
            reverse=True,
        )
    )
)
