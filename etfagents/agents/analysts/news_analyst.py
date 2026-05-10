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
from langchain_core.messages import AIMessage
from etfagents.tool_report_utils import run_tool_report_chain
from etfagents.dataflows.config import get_config
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state.get("trade_date") or state.get("analysis_date")
        if not current_date:
            raise KeyError("trade_date")
        instrument_context = build_instrument_context(get_asset_symbol(state))

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
            "Each top-level section (一、二、三、四) must begin with 2-3 sentences summarizing the key conclusions "
            "of that section, then a blank line before sub-sections.\n\n"
            "一、总体研判 (Overview)\n"
            "  （一）ETF暴露分析: identify the ETF's dominant sleeves, top holdings concentration, and which macro variables each sleeve is sensitive to\n"
            "  （二）核心宏观驱动: integrate global rates, real yields, credit pricing, geopolitics, China policy context, and the Tushare eco-calendar\n"
            "二、深度分析 (In-Depth Analysis)\n"
            "  （一）关键异常与传导链: explain which spread, real-rate, credit, safe-haven, or calendar/event anomalies are abnormal versus the recent baseline and how they transmit into this ETF\n"
            "  （二）情景敏感性: explain which macro scenarios favor or hurt the ETF's main exposure mix\n"
            "三、风险与催化 (Risks & Catalysts)\n"
            "  （一）下一个再平衡窗口催化: highlight the most important scheduled macro releases and policy events to watch next\n"
            "  （二）关键宏观风险与失效点: state what evidence would break the current base case\n"
            "四、总结 (Summary)\n\n"
            "End with a markdown summary table. Keep the framework coherent and ETF-specific rather than generic macro commentary.\n\n"
            "The report must begin with a 2-4 sentence overview paragraph that summarizes: "
            "(a) the current macro regime label (e.g. reflationary, stagflationary, goldilocks, tightening cycle), "
            "(b) the single most important macro driver for this ETF right now and its direction of travel, "
            "(c) whether the macro backdrop is favorable, headwind, or neutral for the ETF's dominant exposure. "
            "This overview must come before any section headings. Do NOT start with '本报告将…' or '以下是…' — state the conclusion directly."
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
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "macro_regime_report": report,
        })

    return news_analyst_node
