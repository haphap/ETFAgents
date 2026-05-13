from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import time
import json
from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_holdings,
    get_etf_info,
    get_macro_regime_data,
    get_global_news,
    get_language_instruction,
    get_news,
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
from langchain_core.messages import AIMessage
from etfagents.tool_report_utils import run_tool_report_chain
from etfagents.dataflows.config import get_config
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases

_DEFAULT_TITLE_LEAD_ZH = (
    "该ETF当前的宏观胜负手取决于利率路径、信用环境、政策节奏与核心暴露方向能否形成同向共振。"
    "若宏观与政策变量继续顺着主要暴露传导，配置逻辑更稳固；若跨资产信号开始互相打架，再平衡窗口就应优先防范预期反转。"
)
_DEFAULT_TITLE_LEAD_EN = (
    "The macro outcome for this ETF depends on whether rates, credit, policy timing, and the fund's core exposures are reinforcing each other or starting to conflict. "
    "If macro and policy variables keep transmitting through the dominant sleeves, the allocation case stays intact; if cross-asset signals start fighting each other, the next rebalance window should be managed more defensively."
)
_REPORT_TITLE_ZH = "宏观框架分析"
_REPORT_TITLE_EN = "Macro Regime Analysis"
def create_macro_analyst(llm):
    def macro_analyst_node(state):
        current_date = state.get("trade_date") or state.get("analysis_date")
        if not current_date:
            raise KeyError("trade_date")
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)

        tools = [
            get_etf_info,
            get_etf_holdings,
            get_macro_regime_data,
            get_global_news,
            get_news,
        ]

        system_message = (
            "你是一名ETF宏观分析师。你的任务是将ETF暴露结构、全球宏观定价、中国宏观发布日历数据和已验证的新闻催化剂整合为一个连贯的配置框架。"
            "先调用 get_etf_info 和 get_etf_holdings 识别基准/风格/行业暴露，再调用 get_macro_regime_data(curr_date, look_back_days) 构建跨资产制度图谱（含Tushare经济日历，通过cn_schedule实现）。"
            "仅使用 get_global_news 和针对性 get_news 验证或挑战数据已暗示的驱动因素。\n\n"
            "不得产出割裂的清单。建立一条逻辑链：ETF暴露 → 宏观与政策制度 → 异常信号 → 情景敏感性 → 下个再平衡窗口催化剂 → 配置含义。\n\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "一级和二级标题只写中文标题，不要在括号中追加英文标题、英文翻译或英文注释。\n"
            "每个一级章节（一、二、三、四）以2-3句导语开头总结该节核心结论，然后空行进入子章节。\n\n"
            "一、暴露与宏观主线\n"
            "  （一）ETF暴露与敏感因子: 识别ETF主导仓位、头部持仓集中度及各仓位对哪些宏观变量敏感\n"
            "  （二）利率信用与政策主驱动: 整合全球利率、实际收益率、信用定价、地缘政治、中国政策背景和Tushare经济日历\n"
            "二、异常信号与情景推演\n"
            "  （一）异常信号与传导链: 解释哪些利差、实际利率、信用、避险或日历/事件异常相对近期基线偏离，以及如何传导至本ETF\n"
            "  （二）情景敏感性与再平衡含义: 解释哪些宏观情景有利或不利ETF主要暴露组合，以及对下次再平衡的含义\n"
            "三、催化窗口与失效条件\n"
            "  （一）下个窗口关键催化: 列出下一个再平衡窗口最重要的宏观发布与政策事件\n"
            "  （二）基准情景失效点: 说明哪些证据会打破当前基准判断\n"
            "四、配置结论与跟踪表\n\n"
            "末尾附markdown摘要表。保持框架连贯且ETF特定，而非泛泛的宏观评论。\n\n"
            "标题导语与每个一级章节导语直接陈述结论。"
            "不得使用'本部分结论表明'、'该部分说明'、'这一节意味着'、'This section shows'等元描述。"
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
        report = strip_meta_lead_prefixes(report) if report else report
        report = strip_report_title(report) if report else report
        report = normalize_chinese_section_headings(
            report,
            strip_english_for_subheadings=True,
        ) if report else report
        report = ensure_title_lead_paragraph(
            report,
            _DEFAULT_TITLE_LEAD_ZH,
            _DEFAULT_TITLE_LEAD_EN,
        ) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "macro_regime_report": report,
        })

    return macro_analyst_node
