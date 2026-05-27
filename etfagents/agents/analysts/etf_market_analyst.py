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
from etfagents.agents.utils.analysis_memory import (
    build_memory_prompt_section,
    inject_memory_prompt_section,
)
from etfagents.agents.utils.report_leads import (
    collect_top_section_marks,
    get_concise_heading_instruction,
    get_no_process_narration_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
    has_invalid_opening_cap,
    post_judge_clean,
    pre_judge_clean,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.agents.utils.validate_refine import AnalystReportSpec, static_validate, validate_and_refine
from etfagents.tool_report_utils import date_days_before, run_tool_report_chain

logger = logging.getLogger(__name__)


_REPORT_SPEC = AnalystReportSpec(
    analyst_name="market_flow",
    required_top_sections=("一", "二", "三", "四"),
    required_indicator_tokens=("MACD", "RSI"),
    required_tail_tokens=("综合结论和指标总览",),
    require_tail_table=True,
    custom_rules_markdown=(
        "### 内容覆盖\n"
        "- 是否包含四个一级章节：一、市场结构与量价诊断；二、交易确认与执行计划；三、关键价位与条件情景推演；四、综合结论和指标总览？\n"
        "- 每个分析章节（一、二、三）标题后是否直接写2-3句结论段，先给方向、证据和交易含义？\n"
        "- 是否覆盖趋势指标（SMA/EMA）、动量（MACD）、超买超卖（RSI）、波动率（Bollinger）和量能确认（VWMA）？\n"
        "- 是否结合份额变化、NAV溢价/折价和换手率分析资金积累/分配/拥挤状态？\n"
        "- 第三部分是否使用连贯段落而非标签式清单？\n"
        "- 第四部分是否在“综合结论和指标总览”一级标题下整合配置方向、关键价位、资金状态与指标总览表？\n"
        "- 指标总览表是否包含指标、数值、位置、交易含义和关键阈值五列？"
    ),
)

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
# The acceptance gate requires the three analysis sections plus an indicator table.
# The fourth combined tail heading is enforced by the report spec and normalizer.
_MARKET_FLOW_REQUIRED_TOP_SECTIONS = {"一", "二", "三"}
_MARKET_FLOW_COMBINED_TAIL_HEADING = "四、综合结论和指标总览"
_MARKET_FLOW_TABLE_SEPARATOR_RE = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
_MARKET_FLOW_CONCLUSION_LABEL_RE = re.compile(r"^\s*综合结论\s*[:：]\s*(.+)$")
_MARKET_FLOW_COMBINED_TAIL_LINE_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?[一二三四五六七八九十]+[、.．]\s*综合结论和指标总览(?:[。.]|\s|$)"
)
_MARKET_FLOW_COMBINED_TAIL_WITH_TEXT_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?"
    r"[一二三四五六七八九十]+[、.．]\s*综合结论和指标总览"
    r"(?:[。.]?\s*)?(?P<tail>.*)$"
)


def _etf_indicator_catalog() -> str:
    return "\n".join(
        f"- {indicator}: {purpose}" for indicator, purpose in _ETF_MARKET_INDICATORS.items()
    )


def _looks_like_complete_market_flow_report(report: str) -> bool:
    """Positive contract for accepting a market-flow report into graph state."""
    content = report or ""
    if not content.strip():
        return False

    if has_invalid_opening_cap(content):
        return False

    section_marks = collect_top_section_marks(content)
    if not _MARKET_FLOW_REQUIRED_TOP_SECTIONS.issubset(section_marks):
        return False

    # Section 四 must contain an indicator overview table
    if not any(_MARKET_FLOW_TABLE_SEPARATOR_RE.match(line.strip()) for line in content.splitlines()):
        return False

    return True


def _find_last_markdown_table(lines: list[str]) -> tuple[int, int] | None:
    last_table: tuple[int, int] | None = None
    index = 0
    while index < len(lines) - 1:
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if not (header.startswith("|") and "|" in header and _MARKET_FLOW_TABLE_SEPARATOR_RE.match(separator)):
            index += 1
            continue
        end = index + 2
        while end < len(lines) and lines[end].strip().startswith("|"):
            end += 1
        last_table = (index, end)
        index = end
    return last_table


def _strip_duplicate_market_flow_combined_tail(lines: list[str]) -> list[str]:
    first_heading_seen = False
    kept: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        is_combined_heading = (
            stripped == _MARKET_FLOW_COMBINED_TAIL_HEADING
            or bool(_MARKET_FLOW_COMBINED_TAIL_LINE_RE.match(stripped))
        )
        if is_combined_heading:
            if first_heading_seen:
                break
            first_heading_seen = True
        kept.append(lines[index])
        index += 1
    return kept


def _market_flow_combined_tail_inline_text(line: str) -> str:
    match = _MARKET_FLOW_COMBINED_TAIL_WITH_TEXT_RE.match(line.strip())
    if not match:
        return ""
    tail = match.group("tail").strip()
    return "" if not tail or tail in {"。", "."} else tail


def _find_previous_market_flow_combined_tail_heading(lines: list[str], start: int) -> int | None:
    for index in range(start, -1, -1):
        stripped = lines[index].strip()
        if (
            stripped == _MARKET_FLOW_COMBINED_TAIL_HEADING
            or _MARKET_FLOW_COMBINED_TAIL_LINE_RE.match(stripped)
        ):
            return index
    return None


def _collect_market_flow_tail_conclusion(lines: list[str], start: int, end: int) -> str:
    parts: list[str] = []
    for raw_line in lines[start:end]:
        stripped = raw_line.strip()
        if not stripped:
            continue
        normalized = re.sub(r"^#{1,6}\s*", "", stripped)
        if normalized in {"指标总览", "四、指标总览", "综合结论", _MARKET_FLOW_COMBINED_TAIL_HEADING}:
            continue
        label_match = _MARKET_FLOW_CONCLUSION_LABEL_RE.match(stripped)
        if label_match:
            stripped = label_match.group(1).strip()
        if stripped:
            parts.append(stripped)
    return "\n".join(parts).strip()


def _normalize_market_flow_tail_sections(report: str) -> str:
    """Migrate legacy tail shapes into the combined market-flow tail section.

    Legacy shapes include a standalone ``指标总览`` / ``四、指标总览`` heading
    before the table, a standalone ``综合结论`` heading after the table, or an
    inline ``综合结论：...`` label. Canonical output uses
    ``四、综合结论和指标总览`` with any conclusion paragraph before the table.
    """
    if not report:
        return ""

    lines = report.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    table_span = _find_last_markdown_table(lines)
    if table_span is not None:
        table_start, table_end = table_span
        table_lines = lines[table_start:table_end]
        replacement_start = table_start
        conclusion_text = ""

        before_idx = table_start - 1
        while before_idx >= 0 and not lines[before_idx].strip():
            before_idx -= 1
        before_stripped = re.sub(r"^#{1,6}\s*", "", lines[before_idx].strip()) if before_idx >= 0 else ""
        if before_idx >= 0 and before_stripped in {"指标总览", "四、指标总览"}:
            replacement_start = before_idx
            heading_idx = _find_previous_market_flow_combined_tail_heading(lines, before_idx - 1)
            if heading_idx is not None:
                replacement_start = heading_idx
                inline_text = _market_flow_combined_tail_inline_text(lines[heading_idx])
                paragraph_text = _collect_market_flow_tail_conclusion(lines, heading_idx + 1, before_idx)
                conclusion_text = "\n".join(
                    part for part in (inline_text, paragraph_text) if part
                ).strip()
        elif before_idx >= 0 and (
            before_stripped == _MARKET_FLOW_COMBINED_TAIL_HEADING
            or bool(_MARKET_FLOW_COMBINED_TAIL_LINE_RE.match(lines[before_idx].strip()))
        ):
            replacement_start = before_idx
            conclusion_text = _market_flow_combined_tail_inline_text(lines[before_idx])
        elif before_idx >= 0:
            paragraph_start = before_idx
            while paragraph_start >= 0 and lines[paragraph_start].strip():
                paragraph_start -= 1
            heading_idx = paragraph_start
            while heading_idx >= 0 and not lines[heading_idx].strip():
                heading_idx -= 1
            if heading_idx >= 0 and _MARKET_FLOW_COMBINED_TAIL_LINE_RE.match(lines[heading_idx].strip()):
                replacement_start = heading_idx
                inline_text = _market_flow_combined_tail_inline_text(lines[heading_idx])
                paragraph_text = "\n".join(
                    line.strip() for line in lines[heading_idx + 1:table_start] if line.strip()
                ).strip()
                conclusion_text = "\n".join(part for part in (inline_text, paragraph_text) if part).strip()

        replacement_end = table_end
        conclusion_idx = table_end
        while conclusion_idx < len(lines) and not lines[conclusion_idx].strip():
            conclusion_idx += 1
        if conclusion_idx < len(lines):
            match = _MARKET_FLOW_CONCLUSION_LABEL_RE.match(lines[conclusion_idx])
            if match:
                conclusion_text = match.group(1).strip()
                replacement_end = conclusion_idx + 1
            elif lines[conclusion_idx].strip() == "综合结论":
                paragraph_start = conclusion_idx + 1
                while paragraph_start < len(lines) and not lines[paragraph_start].strip():
                    paragraph_start += 1
                paragraph_end = paragraph_start
                while paragraph_end < len(lines) and lines[paragraph_end].strip():
                    paragraph_end += 1
                conclusion_text = "\n".join(
                    line.strip() for line in lines[paragraph_start:paragraph_end]
                ).strip()
                replacement_end = paragraph_end

        replacement = [_MARKET_FLOW_COMBINED_TAIL_HEADING, ""]
        if conclusion_text:
            replacement.extend([conclusion_text, ""])
        replacement.extend(table_lines)
        if replacement_start > 0 and lines[replacement_start - 1].strip():
            replacement.insert(0, "")
        lines[replacement_start:replacement_end] = replacement
    else:
        for index, line in enumerate(lines):
            match = _MARKET_FLOW_CONCLUSION_LABEL_RE.match(line)
            if not match:
                continue
            lines[index] = _MARKET_FLOW_COMBINED_TAIL_HEADING
            lines.insert(index + 1, "")
            lines.insert(index + 2, match.group(1).strip())
            break

    lines = _strip_duplicate_market_flow_combined_tail(lines)
    return "\n".join(lines).strip()


def create_etf_market_analyst(llm):
    def etf_market_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
        memory_section = build_memory_prompt_section(state, role="market_flow", aliases=("market",))

        tools = [get_etf_price_data, get_etf_indicators, get_etf_share, get_etf_nav, get_etf_universe]

        system_message = inject_memory_prompt_section((
            "你是一名ETF市场与资金流分析师，聚焦入场时机、流动性与执行质量。"
            "基于价格走势、均线、动量、波动率、份额变化、NAV线索与执行深度，为目标ETF构建一份技术面与资金流综合诊断报告。\n\n"
            "先按以下顺序取数并直接据此成文：\n"
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
            + get_no_process_narration_instruction() + "\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "Use EXACTLY four top-level sections (一、二、三、四). Do NOT create additional top-level sections.\n"
            "前三个一级章节（一、二、三）标题后直接写2-3句结论段，先给方向、证据和交易含义，然后空行进入子章节或正文。\n\n"
            "一、市场结构与量价诊断\n"
            "  （一）趋势与动量\n"
            "    覆盖10 EMA / 20 SMA / 50 SMA / 200 SMA对比、MACD、信号线、柱状图、RSI。\n\n"
            "  （二）波动与流动性\n"
            "    覆盖布林带、ATR、份额变化、NAV/溢折价线索、VWMA、换手率。\n\n"
            "二、交易确认与执行计划\n"
            "  Write the body of this section directly without any sub-heading. Explain why the judgment is bullish / bearish / neutral, whether flow confirms or contradicts the setup, and the exact add / hold / reduce / wait conditions, support / resistance, and risk controls.\n\n"
            "三、关键价位与条件情景推演\n"
            "  （一）关键价位与触发条件\n"
            "    用连贯段落而非清单，说明最重要的支撑/阻力/加仓/减仓/止损价位。\n"
            "  （二）条件情景推演\n"
            "    用连贯段落将价位与核心情景路径、确认或证伪条件、以及赋予该情景更高权重的理由联系起来。\n\n"
            "四、综合结论和指标总览\n"
            "  标题后先用一段话整合配置方向（偏多/偏空/中性）、关键价位区间和资金状态判断，随后只放一个Markdown表格。\n"
            "  表格包含指标、数值、位置、交易含义和关键阈值五列，覆盖本报告讨论的所有主要技术指标与资金指标；不得再写“指标总览”或“综合结论”独立标题。\n\n"
            "## 风格要求\n"
            '- 当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用"分别为"连接，例如"10日均线、20日均线、50日均线值分别为2.01元、2.02元、2.03元"，不得逐个单独陈述。\n'
            '- 若某项数据在已获取的数据源中不存在，直接省略该分析维度，不得输出"数据缺失""数据不足"等提示。\n'
            '- 开篇帽段和前三个一级章节标题后的结论段都必须直接陈述结论，不得使用"本节""本部分""该部分""这一节"等自指式开头（如"本节核心结论指出""本部分结论表明""该部分说明"）。\n'
            "- 标题后的结论段必须高于小节层面：综合方向、动量质量、资金确认与交易含义，不得简单复述下方小节内容。\n"
            '- 使用上述精确的四段章节结构，不得引入"核心交易信号"、"结论依据"等额外标题。\n'
            '- 可直接使用"多头排列"、"空头排列"、"金叉"、"死叉"、"发散"、"背离"、"放量突破"等技术术语，不得追加括号名词解释或术语定义。\n'
            '- 每个主要信号之后必须回答两个问题："这意味着什么"和"对交易应该怎么做"。'
            '但不得将"这意味着什么""对交易应该怎么做"作为标题或标签输出，应将答案自然融入段落中。\n'
            '- 第三部分采用段落式表达，不得使用"判断："、"证据："、"关键价位："、"条件情景："等标签。信号、判断、证据、信心水平与触发路径应融入完整的策略段落中。\n'
            "- 反面示例（禁止）：'判断：偏多。关键价位：448-450。条件情景：若放量突破则继续加仓。'\n"
            "- 正面示例（目标风格）：'当前448-450一带既是20日均线与前期密集成交区重叠的支撑带，也是判断这轮偏多结构是否仍有效的第一道关口。若价格回踩后成交量没有明显失速、且VWMA继续向上抬升，说明资金承接并未破坏，基准情景仍是震荡后继续上攻；反之，一旦跌破该区间且量能放大为抛压主导，就应把情景切换为结构转弱并优先减仓。'\n\n"
            "## 完整报告示例（仅作风格参考，实际内容以目标ETF数据为准）\n\n"
            "价格站稳50日均线上方，短中期均线同步向上，MACD柱状图持续扩张，量价结构偏多，但RSI接近超买区需要警惕短期回踩。\n\n"
            "一、市场结构与量价诊断\n\n"
            "趋势、动量与资金流三者仍在同向确认偏多结构，短期回踩风险可控但需关注RSI超买信号。\n\n"
            "（一）趋势与动量\n\n"
            "10日均线、20日均线、50日均线、200日均线值分别为452元、448元、443元、425元，短中长期均线全部向上发散——这意味着不同时间维度的买盘力量都在主导。MACD的DIF为1.05、DEA为0.78，两者均在零轴上方且差值持续扩大，柱状图连续五天走高，说明上涨动能正在增强。RSI读数64，距超买区70尚有余地，未出现顶背离信号。综合来看，趋势与动量同步确认偏多方向。\n\n"
            "（二）波动与流动性\n\n"
            "布林带中轨449元、上轨462元，价格在中轨与上轨之间运行，带宽扩张但方向向上，说明波动率上升有利于趋势延续。ATR为1.8元，约占价格4%，若以ATR设置止损可参考446元（中轨下方）。份额近一周增长2.3%，NAV溢价率0.18%处于正常范围，换手率1.3%未见异常拥挤信号。VWMA稳步上行，确认放量突破有效，资金持续流入。\n\n"
            "二、交易确认与执行计划\n\n"
            "趋势、动量、波动率与资金流四维共振偏多，执行上以回踩支撑加仓为主、条件化风控为辅。若RSI进入超买区后出现死叉，应优先收缩仓位而非追高；若份额从净流入转为净流出，则说明资金在撤退，需重新评估偏多逻辑。当前建议维持偏多配置，仓位控制在5-6成，回踩448-450区间可加至7成，止损设在446元下方。\n\n"
            "三、关键价位与条件情景推演\n\n"
            "当前448-450一带既是20日均线与前期密集成交区重叠的支撑带，也是判断这轮偏多结构是否仍有效的第一道关口。若价格回踩后成交量没有明显失速、且VWMA继续向上抬升，说明资金承接并未破坏，基准情景仍是震荡后继续上攻462-465阻力带。操作上，若回踩448-450不破且量能未失速，可加仓至6-7成，止损446元下方；若放量跌破448则先减至3-4成，进一步跌破440则止损离场。最乐观情景下，若放量突破462元可追加至8成，目标470元以上。基于当前信号强度，基准情景权重约65%，最乐观情景约25%，转弱情景约10%。需警惕的风险包括：RSI进入超买区后死叉可能触发短期回调，份额从净流入转为净流出将否定偏多逻辑。\n\n"
            "四、综合结论和指标总览\n\n"
            "偏多配置，回踩448-450加仓，止损446，目标462-465。资金状态：份额增长、溢价正常且换手率适中，说明资金仍在积累但尚未拥挤。\n\n"
            "| 指标 | 数值 | 位置 | 交易含义 | 关键阈值 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 10/20/50/200 SMA | 452/448/443/425 | 上方 | 多头排列，趋势偏多 | 跌破448则短期转弱 |\n"
            "| MACD | DIF 1.05, DEA 0.78 | 零轴上方 | 动能增强 | DIF下穿DEA则动能衰减 |\n"
            "| RSI | 64 | 中性偏强 | 尚有空间但接近超买 | 上穿70则警惕回踩 |\n"
            "| 布林带 | 中轨449, 上轨462 | 中轨与上轨之间 | 波动率扩张，方向向上 | 跌破中轨则趋势减弱 |\n"
            "| 份额变化 | +2.3% | — | 资金净流入 | 连续下降则资金撤退 |\n"
            "| 换手率 | 1.3% | 正常 | 未见拥挤 | 超过3%则拥挤加剧 |\n\n"
            "## 语言\n"
            "分析文本使用中文。工具名称、指标ID与行情代码保持英文。\n"
            + get_language_instruction()
        ), memory_section)

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
            report_acceptance_check=_looks_like_complete_market_flow_report,
            rejected_report_fallback="last_attempt",
            unexecuted_tool_recovery={
                "trigger_tool_names": [tool.name for tool in tools],
                "tool_payloads": [
                    {
                        "tool": get_etf_price_data,
                        "payload": {
                            "symbol": asset_symbol,
                            "start_date": date_days_before(current_date, 180),
                            "end_date": current_date,
                        },
                    },
                    {
                        "tool": get_etf_indicators,
                        "payload": {
                            "symbol": asset_symbol,
                            "indicator": ",".join(_ETF_MARKET_INDICATORS),
                            "curr_date": current_date,
                            "look_back_days": 180,
                        },
                    },
                    {
                        "tool": get_etf_share,
                        "payload": {"ticker": asset_symbol, "curr_date": current_date},
                    },
                    {
                        "tool": get_etf_nav,
                        "payload": {"ticker": asset_symbol, "curr_date": current_date},
                    },
                    {
                        "tool": get_etf_universe,
                        "payload": {"curr_date": current_date, "limit": 20},
                    },
                ],
            },
        )
        report = normalize_chinese_role_terms(report) if report else report
        report = pre_judge_clean(report) if report else report
        report = validate_and_refine(report, llm, _REPORT_SPEC) if report else report
        report = post_judge_clean(report) if report else report
        report = _normalize_market_flow_tail_sections(report) if report else report
        if report and not _looks_like_complete_market_flow_report(report):
            logger.warning(
                "Market & flow report failed strict acceptance after retries; keeping last cleaned draft."
            )
        if report:
            verdict = static_validate(report, _REPORT_SPEC)
            if verdict.missing_elements:
                logger.warning(
                    "Market & flow report still missing expected elements after validation/refine: %s",
                    "; ".join(verdict.missing_elements),
                )
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "market_flow_report": report,
            }
        )

    return etf_market_node
