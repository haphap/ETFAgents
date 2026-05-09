from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_nav,
    get_etf_price_data,
    get_etf_share,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain


def create_etf_flow_analyst(llm):
    def etf_flow_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(get_asset_symbol(state))
        tools = [get_etf_share, get_etf_nav, get_etf_price_data]

        system_message = (
            "You are an ETF fund-flow and liquidity analyst. Evaluate creation-redemption scale changes,"
            " share changes, NAV behavior, turnover, and trading liquidity to judge whether positioning is being accumulated,"
            " distributed, or crowded.\n\n"
            "The final markdown report must cover:\n"
            "1. Recent fund share / scale change and its likely interpretation\n"
            "2. NAV and premium-discount clues if available\n"
            "3. Trading liquidity and execution friendliness\n"
            "4. Whether flows validate or contradict the technical setup\n"
            "5. Risks of crowding, liquidity air pockets, or false breakouts\n\n"
            "Make the output useful for ETF allocation timing, not generic product marketing."
            " End with a markdown summary table."
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
            "etf_flow_report": report,
        })

    return etf_flow_node
