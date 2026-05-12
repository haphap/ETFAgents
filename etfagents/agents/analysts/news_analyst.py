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
    normalize_section_headings,
    get_topic_and_term_style_instruction,
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
_NEWS_HEADING_MAP = {
    "一、总体研判": "一、暴露与宏观主线",
    "（一）ETF暴露分析": "（一）ETF暴露与敏感因子",
    "（二）核心宏观驱动": "（二）利率信用与政策主驱动",
    "二、深度分析": "二、异常信号与情景推演",
    "（一）关键异常与传导链": "（一）异常信号与传导链",
    "（二）情景敏感性": "（二）情景敏感性与再平衡含义",
    "三、风险与催化": "三、催化窗口与失效条件",
    "（一）下一个再平衡窗口催化": "（一）下个窗口关键催化",
    "（二）关键宏观风险与失效点": "（二）基准情景失效点",
    "四、总结": "四、配置结论与跟踪表",
}


def create_news_analyst(llm):
    def news_analyst_node(state):
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
            "You are an ETF macro analyst. Your job is to merge ETF exposure mapping, global macro pricing, Chinese macro release calendar data, and verified news catalysts into one coherent allocation framework. "
            "Start with get_etf_info and get_etf_holdings to identify benchmark/style/sector exposure, then call get_macro_regime_data(curr_date, look_back_days) to build the cross-asset regime map including the Tushare eco-calendar feed (implemented with cn_schedule). "
            "Use get_global_news and targeted get_news only to verify or challenge the drivers already suggested by the data.\n\n"
            "Do not produce a disconnected checklist. Build one logical chain from ETF exposure -> macro and policy regime -> anomalies -> scenario sensitivity -> next rebalance-window catalysts -> allocation implication.\n\n"
            "The final markdown report must follow this unified framework:\n"
            "Write a 2-4 sentence overview paragraph before any section headings "
            "that summarizes the dominant macro driver, the main transmission path, and the ETF allocation implication. "
            "This lead paragraph must appear before any section headings.\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "Each top-level section (一、二、三、四) must begin with 2-3 sentences summarizing the key conclusions "
            "of that section, then a blank line before sub-sections.\n\n"
            "一、暴露与宏观主线 (Exposure & Macro Thesis)\n"
            "  （一）ETF暴露与敏感因子: identify the ETF's dominant sleeves, top holdings concentration, and which macro variables each sleeve is sensitive to\n"
            "  （二）利率信用与政策主驱动: integrate global rates, real yields, credit pricing, geopolitics, China policy context, and the Tushare eco-calendar\n"
            "二、异常信号与情景推演 (Signals & Scenario Analysis)\n"
            "  （一）异常信号与传导链: explain which spread, real-rate, credit, safe-haven, or calendar/event anomalies are abnormal versus the recent baseline and how they transmit into this ETF\n"
            "  （二）情景敏感性与再平衡含义: explain which macro scenarios favor or hurt the ETF's main exposure mix and what that means for the next rebalance\n"
            "三、催化窗口与失效条件 (Catalysts & Invalidation)\n"
            "  （一）下个窗口关键催化: highlight the most important scheduled macro releases and policy events to watch next\n"
            "  （二）基准情景失效点: state what evidence would break the current base case\n"
            "四、配置结论与跟踪表 (Allocation Conclusion & Tracking Table)\n\n"
            "End with a markdown summary table. Keep the framework coherent and ETF-specific rather than generic macro commentary.\n\n"
            "For the title lead and the 2-3 sentence lead under each top-level section, state the conclusion directly. "
            "Do NOT use lead-ins such as '本部分结论表明', '该部分说明', '这一节意味着', 'This section shows', or similar meta phrasing."
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
        report = normalize_section_headings(report, _NEWS_HEADING_MAP) if report else report
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

    return news_analyst_node
