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
from etfagents.agents.utils.analysis_memory import (
    build_memory_prompt_block,
    get_memory_usage_instruction,
)
from etfagents.agents.utils.report_leads import (
    clean_generated_report,
    get_concise_heading_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.agents.utils.validate_refine import validate_and_refine
from etfagents.tool_report_utils import run_tool_report_chain

logger = logging.getLogger(__name__)


_VALIDATION_RULES = (
    "### 内容覆盖\n"
    "- 是否包含三个一级章节：一、市场结构与量价诊断；二、交易确认与执行计划；三、关键价位与条件情景推演？\n"
    "- 每个一级章节（一、二、三）是否以2-3句导语开头总结该节核心结论？\n"
    "- 是否覆盖趋势指标（SMA/EMA）、动量（MACD）、超买超卖（RSI）、波动率（Bollinger）和量能确认（VWMA）？\n"
    "- 是否结合份额变化、NAV溢价/折价和换手率分析资金积累/分配/拥挤状态？\n"
    "- 第三部分是否使用连贯段落而非标签式清单？\n"
    "- 末尾是否附指标总览表（含指标、数值、位置、交易含义、关键阈值列）？\n"
    "- 末尾是否附综合结论段落（含配置方向、关键价位、资金状态）？"
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


def _etf_indicator_catalog() -> str:
    return "\n".join(
        f"- {indicator}: {purpose}" for indicator, purpose in _ETF_MARKET_INDICATORS.items()
    )



def create_etf_market_analyst(llm):
    def etf_market_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
        memory_block = build_memory_prompt_block(state, role="market_flow", aliases=("market",))
        memory_section = f"\n\n{memory_block}\n\n{get_memory_usage_instruction()}" if memory_block else ""

        tools = [get_etf_price_data, get_etf_indicators, get_etf_share, get_etf_nav, get_etf_universe]

        system_message = (
            "你是一名ETF市场与资金流分析师，聚焦入场时机、流动性与执行质量。"
            "基于价格走势、均线、动量、波动率、份额变化、NAV线索与执行深度，为目标ETF构建一份技术面与资金流综合诊断报告。\n\n"
            + memory_section + "\n\n"
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
            "每个一级章节（一、二、三）以2-3句导语开头总结该节核心结论，然后空行进入子章节或正文。\n\n"
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
            "在所有分析章节之后，报告最末附一个标题为'指标总览'的markdown表格，"
            "包含指标、数值、位置、交易含义和关键阈值五列，覆盖本报告讨论的所有主要技术指标与资金指标。"
            "表格之后附一段综合结论，明确配置方向（偏多/偏空/中性）、关键价位区间和资金状态判断。\n\n"
            "## 风格要求\n"
            '- 当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用"分别为"连接，例如"10日均线、20日均线、50日均线值分别为2.01元、2.02元、2.03元"，不得逐个单独陈述。\n'
            '- 若某项数据在已获取的数据源中不存在，直接省略该分析维度，不得输出"数据缺失""数据不足"等提示。\n'
            '- 标题导语与每个一级章节导语直接陈述结论，不得使用"本节""本部分""该部分""这一节"等自指式开头（如"本节核心结论指出""本部分结论表明""该部分说明"）。\n'
            "- 导语段落必须高于小节层面：综合方向、动量质量、资金确认与交易含义，不得简单复述下方小节内容。\n"
            '- 使用上述精确的三段章节结构，不得引入"核心交易信号"、"结论依据"等额外标题。\n'
            '- 若使用"多头排列"、"金叉"、"发散"、"背离"、"放量突破"等技术术语，必须立即用通俗语言解释并说明交易含义，不得出现"标准多头发散形态"等未解释行话。\n'
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
        report = validate_and_refine(report, llm, _VALIDATION_RULES) if report else report
        report = clean_generated_report(report) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "market_flow_report": report,
            }
        )

    return etf_market_node
