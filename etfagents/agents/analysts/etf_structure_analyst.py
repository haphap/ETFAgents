from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_commodity_cluster_data,
    get_collaboration_stop_instruction,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain


def create_etf_structure_analyst(llm):
    def etf_structure_node(state):
        current_date = state.get("trade_date") or state.get("analysis_date")
        if not current_date:
            raise KeyError("trade_date")
        instrument_context = build_instrument_context(get_asset_symbol(state))
        tools = [get_commodity_cluster_data]

        system_message = (
            "You are a meso commodity analyst for ETF allocation. Build a commodity-cluster map that links price behavior to macro friction, "
            "China demand, inflation persistence, and policy room.\n\n"
            "Use direct Tushare futures and warehouse-receipt evidence where available rather than equity or ETF proxy instruments. "
            "Your main task is to find commodity anomalies that matter for the ETF: unusual price moves, open-interest expansion or collapse, warehouse / inventory stress, and divergences between price and positioning. "
            "Explain why each anomaly is abnormal relative to the recent baseline and what macro or industry trend it supports or challenges.\n\n"
            "The final markdown report must cover:\n"
            "1. Precious metals and what they imply about fiat trust, real rates, and safe-haven demand\n"
            "2. Industrial metals and what they imply about real manufacturing and infrastructure demand\n"
            "3. Crude / energy and what they imply about recession risk and policy tightening room\n"
            "4. Energy-transition metals and what they imply about the profit split inside the transition chain\n"
            "5. Ferrous / building materials and what they imply about China domestic investment-cycle strength and PPI direction\n"
            "6. Soft commodities / forestry and what they imply about climate shocks, substitution, and service/logistics inflation\n\n"
            "You may emphasize some clusters more than others depending on ETF relevance instead of giving each cluster equal weight by template. "
            "Tie the cluster read-through back to ETF allocation and rotation decisions. End with a markdown summary table and a dedicated 'Key anomalies' section."
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
            "meso_commodity_report": report,
        })

    return etf_structure_node
