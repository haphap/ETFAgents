# DEPRECATED: Not wired into default ETF graph. Use news_analyst (macro_regime) instead.
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_holdings,
    get_etf_info,
    get_global_news,
    get_language_instruction,
    get_news,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain


def create_etf_macro_analyst(llm):
    def etf_macro_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(get_asset_symbol(state))
        tools = [get_etf_info, get_etf_holdings, get_news, get_global_news]

        system_message = (
            "You are an ETF macro and benchmark-exposure analyst. Explain how the ETF's benchmark, holdings mix,"
            " style tilt, and current macro / policy backdrop interact. Focus on scenario sensitivity rather than"
            " company-specific bottom-up valuation.\n\n"
            "The final markdown report should cover:\n"
            "1. Benchmark / style / sector exposure\n"
            "2. Macro and policy drivers most relevant to this ETF\n"
            "3. Which scenarios favor or hurt the ETF's exposure mix\n"
            "4. Catalysts to watch over the next rebalancing window\n"
            "5. Key macro risks that could invalidate a bullish allocation case\n\n"
            "Tie every conclusion back to ETF allocation and timing decisions. End with a markdown summary table."
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
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "etf_macro_report": report,
        })

    return etf_macro_node
