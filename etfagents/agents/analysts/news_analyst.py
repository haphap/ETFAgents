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
            "1. Benchmark / style / sector exposure analysis: identify the ETF's dominant sleeves, top holdings concentration, and which macro variables each sleeve is sensitive to\n"
            "2. Core macro and policy drivers: integrate global rates, real yields, credit pricing, geopolitics, China policy context, and the Tushare eco-calendar / cn_schedule release calendar\n"
            "3. Key anomalies and transmission chain: explain which spread, real-rate, credit, safe-haven, or calendar/event anomalies are abnormal versus the recent baseline and how they transmit into this ETF\n"
            "4. Scenario sensitivity: explain which macro scenarios favor or hurt the ETF's main exposure mix\n"
            "5. Next rebalance-window catalysts: highlight the most important scheduled macro releases and policy events to watch next\n"
            "6. Key macro risks and invalidation points: state what evidence would break the current base case\n\n"
            "End with a markdown summary table. Keep the framework coherent and ETF-specific rather than generic macro commentary."
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
