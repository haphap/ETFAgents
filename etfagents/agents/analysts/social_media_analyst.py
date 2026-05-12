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
from etfagents.agents.utils.report_leads import (
    strip_meta_lead_prefixes,
    strip_title_lead_paragraph,
)
from langchain_core.messages import AIMessage
from etfagents.tool_report_utils import run_tool_report_chain
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)

        tools = [
            get_etf_info,
            get_etf_holdings,
            get_news,
            get_global_news,
        ]

        # NOTE: This agent uses news tools (get_news, get_global_news), not social media APIs.
        # Social media data sources (e.g. Reddit, Twitter/X) are not yet integrated.
        system_message = (
            "You are an ETF catalyst and sentiment analyst. Your job is not limited to the ETF product itself: "
            "you must analyze how public discussion, recent news, and macro events affect the ETF's price support or drag through its "
            "benchmark exposure, dominant industries, and top-weight holdings.\n\n"
            "Required workflow:\n"
            f"1. First call get_etf_info(ticker='{asset_symbol}', curr_date='{current_date}') and get_etf_holdings(ticker='{asset_symbol}', curr_date='{current_date}') "
            "to identify the ETF's benchmark, dominant industries, and highest-weight holdings.\n"
            "2. Then use get_news(query, start_date, end_date) multiple times to search:\n"
            "   - the ETF ticker / product itself,\n"
            "   - the benchmark or dominant exposure theme,\n"
            "   - the ETF's main industries,\n"
            "   - the highest-weight holdings that materially drive ETF performance.\n"
            "3. Also call get_global_news(curr_date, look_back_days, limit) to capture macro events that could transmit into those industries or holdings.\n"
            "4. Judge whether each development is likely to support, cap, or drag ETF price action, and explain the transmission path from news / sentiment / macro event -> holdings / industry impact -> ETF price implication.\n\n"
            "The final markdown report must explicitly cover:\n"
            "Each top-level section (一、二、三、四) must begin with 2-3 sentences summarizing the key conclusions "
            "of that section, then a blank line before sub-sections.\n\n"
            "一、总体研判 (Overview)\n"
            "  （一）ETF产品情绪与讨论: ETF-specific sentiment and product-level discussion\n"
            "  （二）行业与重仓股舆情: News and sentiment around dominant industries and top holdings\n"
            "二、深度分析 (In-Depth Analysis)\n"
            "  （一）宏观事件传导: Relevant macro events and whether they amplify or offset the ETF thesis\n"
            "  （二）真实支撑、真实拖累与噪声区分: which developments truly support ETF price, which ones drag on it, and which are just noise\n"
            "三、风险与催化 (Risks & Catalysts)\n"
            "  （一）后续监控要点: What the allocator should monitor next for confirmation or invalidation\n"
            "四、总结 (Summary)\n\n"
            "Do not stay at the ETF ticker headline level. Expand the analysis to the ETF's heavy industries and weight stocks, then map those findings back to ETF pricing."
            " When writing in Chinese, use Chinese section titles such as '真实支撑、真实拖累与噪声区分'; do not use English labels like 'Genuine Support'."
            " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.\n\n"
            "Start the visible report body directly at '一、总体研判' after the H1 title; do NOT insert a separate title lead, overview paragraph, or summary paragraph before section one.\n"
            "For the 2-3 sentence lead under each top-level section, state the conclusion directly. "
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
        report = strip_title_lead_paragraph(report) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "catalyst_sentiment_report": report,
        })

    return social_media_analyst_node
