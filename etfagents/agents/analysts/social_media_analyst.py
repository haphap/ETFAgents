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
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases

_DEFAULT_TITLE_LEAD_ZH = (
    "当前影响该ETF定价的关键变量不在产品 headline 数量，而在主导行业与高权重成分股的事件催化能否继续向净值传导。"
    "若产业与重仓股层面的正反馈强于产品层面的噪声波动，配置上更适合顺势持有；若热点扩散无法落到权重资产，情绪脉冲更可能只是短期扰动。"
)
_DEFAULT_TITLE_LEAD_EN = (
    "What matters for this ETF is not the raw count of headlines around the product, but whether event and sentiment shocks are transmitting into its dominant industries and heavyweight holdings. "
    "If industry and top-holding feedback loops stay stronger than ETF-level noise, the setup favors staying with the trend; if the buzz never reaches the weighted exposures, the sentiment pulse is likely short-lived."
)
_REPORT_TITLE_ZH = "舆情与事件影响分析"
_REPORT_TITLE_EN = "Sentiment & Catalyst Impact Analysis"


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
            "你是一名ETF催化剂与情绪分析师。你的工作不限于ETF产品本身："
            "必须分析公众讨论、近期新闻和宏观事件如何通过基准暴露、主导行业和高权重持仓影响ETF价格支撑或拖累。\n\n"
            "工作流程：\n"
            f"1. 先调用 get_etf_info(ticker='{asset_symbol}', curr_date='{current_date}') 和 get_etf_holdings(ticker='{asset_symbol}', curr_date='{current_date}') "
            "识别ETF的基准、主导行业和最高权重持仓。\n"
            "2. 多次使用 get_news(query, start_date, end_date) 搜索：\n"
            "   - ETF代码/产品本身\n"
            "   - 基准或主导暴露主题\n"
            "   - ETF的主要行业\n"
            "   - 对ETF表现有实质驱动的最高权重持仓\n"
            "3. 调用 get_global_news(curr_date, look_back_days, limit) 捕捉可能传导至这些行业或持仓的宏观事件。\n"
            "4. 判断每个事件可能支撑、压制还是拖累ETF价格，解释传导路径：新闻/情绪/宏观事件 → 持仓/行业影响 → ETF价格含义。\n\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "每个一级章节（一、二、三、四）以2-3句导语开头总结该节核心结论，然后空行进入子章节。\n\n"
            "一、情绪主线与权重影响\n"
            "  （一）产品情绪与讨论强弱: ETF产品层面的情绪与讨论强度\n"
            "  （二）行业与重仓股事件主线: 主导行业与头部持仓的新闻和情绪\n"
            "二、事件传导与定价辨别\n"
            "  （一）宏观事件传导: 相关宏观事件是否放大或对冲ETF论点\n"
            "  （二）真实支撑与短期噪声: 哪些事件真正支撑ETF价格、哪些拖累、哪些仅是噪声\n"
            "三、后续触发与验证要点\n"
            "  （一）后续监控要点: 配置者接下来应监控什么以确认或证伪\n"
            "四、结论与跟踪表\n\n"
            "不得停留在ETF代码标题层面。将分析扩展到ETF重行业和权重股，然后将发现转回ETF定价。"
            "中文输出时使用中文章节标题，如'真实支撑与短期噪声'；不得使用英文标签如'Genuine Support'。"
            "末尾附Markdown表格整理报告关键要点。\n\n"
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
        report = normalize_chinese_section_headings(report) if report else report
        report = ensure_title_lead_paragraph(
            report,
            _DEFAULT_TITLE_LEAD_ZH,
            _DEFAULT_TITLE_LEAD_EN,
        ) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "catalyst_sentiment_report": report,
        })

    return social_media_analyst_node
