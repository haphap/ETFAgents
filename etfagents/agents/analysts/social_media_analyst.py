import csv
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_holdings,
    get_etf_info,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.report_leads import (
    get_concise_heading_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
    strip_report_title,
    strip_refine_preamble,
    strip_self_referential_meta_leads,
)
from etfagents.agents.utils.validate_refine import validate_and_refine
from etfagents.dataflows.opencli_news import get_global_news, get_news, get_news_for_queries
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases

logger = logging.getLogger(__name__)

_VALIDATION_RULES = (
    "### 内容覆盖\n"
    "- 是否将分析扩展到ETF重行业和权重股，而非仅停留在ETF代码层面？\n"
    "- 是否对每个事件说明传导路径：新闻/情绪/宏观事件 → 持仓/行业影响 → ETF价格含义？\n"
    "- 是否区分了真实支撑、真实拖累与短期噪声？\n"
    "- 是否对跨数据源的分歧或一致性进行了分析？\n"
    "- 末尾是否附Markdown摘要表格？"
)

_HOLDING_NAME_COLUMNS = ("name", "stk_name", "sec_name")


def _extract_holding_names(holdings_csv: str, max_names: int = 3) -> list[str]:
    """Extract top holding company names from the CSV-formatted holdings output."""
    if not holdings_csv or "No ETF holdings" in holdings_csv:
        return []

    # Find the CSV data after the header comments
    lines = holdings_csv.split("\n")
    csv_lines = [line for line in lines if not line.startswith("#") and line.strip()]
    if not csv_lines:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(csv_lines)))
    if not reader.fieldnames:
        return []

    # Find the column that contains company names
    name_col = None
    for col in _HOLDING_NAME_COLUMNS:
        if col in reader.fieldnames:
            name_col = col
            break

    names = []
    for row in reader:
        if name_col and row.get(name_col):
            name = row[name_col].strip()
            if name and name not in names:
                names.append(name)
        if len(names) >= max_names:
            break

    return names


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    etf_info: str,
    etf_holdings: str,
    ticker_news: str,
    holdings_news: str,
    global_news: str,
) -> str:
    """Assemble the sentiment-analyst system message with pre-fetched data blocks."""
    return (
        "你是一名ETF催化剂与情绪分析师。你的工作不限于ETF产品本身："
        "必须分析公众讨论、近期新闻和宏观事件如何通过基准暴露、主导行业和高权重持仓影响ETF价格支撑或拖累。\n\n"
        "## 数据来源（已获取，直接使用）\n\n"
        f"### ETF基本信息\n<etf_info>\n{etf_info}\n</etf_info>\n\n"
        f"### ETF持仓构成\n<etf_holdings>\n{etf_holdings}\n</etf_holdings>\n\n"
        f"### ETF相关新闻（过去7天）\n<ticker_news>\n{ticker_news}\n</ticker_news>\n\n"
        f"### 重仓股相关新闻（过去7天）\n<holdings_news>\n{holdings_news}\n</holdings_news>\n\n"
        f"### 宏观新闻与市场情绪\n<global_news>\n{global_news}\n</global_news>\n\n"
        "## 分析指引\n"
        "基于上述已获取的数据，完成以下分析：\n\n"
        "1. 从ETF持仓构成中识别基准、主导行业和最高权重持仓。\n"
        "2. 分析新闻和情绪数据如何影响这些持仓和行业。\n"
        "3. 判断每个事件可能支撑、压制还是拖累ETF价格，解释传导路径：新闻/情绪/宏观事件 → 持仓/行业影响 → ETF价格含义。\n"
        "4. 跨数据源比对：如果某个事件在多个来源中出现，信号更强；如果不同源指向矛盾方向，需要明确指出分歧。\n"
        "5. 区分事实与观点：新闻标题是事实，社交媒体评论是观点，两者权重不同。\n"
        "6. 如果某个数据源返回为空或数据不足，在分析中明确标注该信号的置信度较低。\n\n"
        + get_no_title_instruction() + "\n"
        + get_topic_and_term_style_instruction() + "\n"
        + get_concise_heading_instruction() + "\n"
        "每个一级章节（一、二、三、四）以2-3句导语开头总结该节核心结论，然后空行进入子章节。\n\n"
        "一、情绪主线与权重影响\n"
        "  （一）产品情绪与讨论强弱\n"
        "    分析ETF产品层面的情绪与讨论强度。\n"
        "  （二）行业与重仓股事件主线\n"
        "    分析主导行业与头部持仓的新闻和情绪。\n"
        "二、事件传导与定价辨别\n"
        "  （一）宏观事件传导\n"
        "    分析相关宏观事件是否放大或对冲ETF论点。\n"
        "  （二）真实支撑与短期噪声\n"
        "    区分哪些事件真正支撑ETF价格、哪些拖累、哪些仅是噪声。\n"
        "三、后续触发与验证要点\n"
        "  （一）后续监控要点\n"
        "    说明配置者接下来应监控什么以确认或证伪。\n"
        "四、结论与跟踪表\n\n"
        "不得停留在ETF代码标题层面。将分析扩展到ETF重行业和权重股，然后将发现转回ETF定价。"
        "中文输出时使用中文章节标题，如'真实支撑与短期噪声'；不得使用英文标签如'Genuine Support'。"
        "末尾附Markdown表格整理报告关键要点。\n\n"
        "当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用'分别为'连接，不得逐个单独陈述。"
        "若某项数据在已获取的数据源中不存在，直接省略该分析维度，不得输出'数据缺失''数据不足'等提示。"
        "标题导语与每个一级章节导语直接陈述结论。"
        "不得使用'本节''本部分''该部分''这一节'等自指式开头（如'本节核心结论指出''本部分结论表明''该部分说明'）。"
        + get_language_instruction()
    )


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        end_date = current_date
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        instrument_context = build_instrument_context(asset_symbol)

        # Phase 1: ETF context (fast tushare calls)
        etf_info = get_etf_info.func(asset_symbol, current_date)
        etf_holdings = get_etf_holdings.func(asset_symbol, current_date)

        # Phase 2: Derive search terms from holdings
        holding_names = _extract_holding_names(etf_holdings)

        # Phase 3: Parallel news fetch
        with ThreadPoolExecutor(max_workers=4) as pool:
            future_ticker_news = pool.submit(get_news, asset_symbol, start_date, end_date)
            future_global = pool.submit(get_global_news, current_date, 7, 10)
            future_holdings_news = None
            if holding_names:
                future_holdings_news = pool.submit(
                    get_news_for_queries, holding_names, start_date, end_date
                )

            ticker_news = future_ticker_news.result()
            global_news = future_global.result()
            holdings_news = future_holdings_news.result() if future_holdings_news else "<无重仓股搜索词>"

        # Phase 4: Build system message with structured blocks
        system_message = _build_system_message(
            ticker=asset_symbol,
            start_date=start_date,
            end_date=end_date,
            etf_info=etf_info,
            etf_holdings=etf_holdings,
            ticker_news=ticker_news,
            holdings_news=holdings_news,
            global_news=global_news,
        )

        prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a helpful AI assistant, collaborating with other assistants."
                        " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                        " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                        + get_collaboration_stop_instruction()
                        + "\n{system_message}\n"
                        + "For your reference, the current date is {current_date}. {instrument_context}"
                    ),
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # Phase 5: Single LLM call (no tool-calling)
        chain = prompt_template.partial(
            system_message=system_message,
            current_date=current_date,
            instrument_context=instrument_context,
        ) | llm
        result = chain.invoke(state["messages"])

        # Phase 6: Post-process
        report = normalize_chinese_role_terms(result.content) if result.content else ""
        report = validate_and_refine(report, llm, _VALIDATION_RULES) if report else report
        report = strip_report_title(report) if report else report
        report = strip_refine_preamble(report) if report else report
        report = strip_self_referential_meta_leads(report) if report else report
        if report:
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "catalyst_sentiment_report": report,
        })

    return social_media_analyst_node
