from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

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
from etfagents.agents.utils.analysis_memory import (
    build_memory_prompt_section,
    inject_memory_prompt_section,
)
from etfagents.agents.utils.report_leads import (
    collect_top_section_marks,
    contains_markdown_table,
    get_concise_heading_instruction,
    get_no_process_narration_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
    has_invalid_opening_cap,
    post_judge_clean,
    pre_judge_clean,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.agents.utils.validate_refine import AnalystReportSpec, validate_and_refine
from etfagents.tool_report_utils import date_days_before, run_tool_report_chain


_REPORT_SPEC = AnalystReportSpec(
    analyst_name="macro_regime",
    custom_rules_markdown=(
        "### 内容覆盖\n"
        "- 是否建立了逻辑链：ETF暴露 → 宏观与政策制度 → 异常信号 → 情景敏感性 → 配置含义？\n"
        "- 是否整合了利率、信用、地缘政治和中国经济日历数据？\n"
        "- 是否说明了基准情景失效点和替代触发条件？\n"
        "- 末尾是否附Markdown摘要表格？"
    ),
)

_MACRO_REQUIRED_TOP_SECTIONS = {"一", "二", "三", "四"}
# Anchors must match the section names emitted by the prompt template below.
_MACRO_REQUIRED_MARKERS = ("ETF暴露", "配置")


def _looks_like_complete_macro_report(report: str) -> bool:
    """Positive contract for accepting a macro report into graph state."""
    content = report or ""
    if not content.strip():
        return False

    if has_invalid_opening_cap(content):
        return False

    section_marks = collect_top_section_marks(content)
    if not _MACRO_REQUIRED_TOP_SECTIONS.issubset(section_marks):
        return False

    return (
        all(marker in content for marker in _MACRO_REQUIRED_MARKERS)
        and contains_markdown_table(content)
    )


def create_macro_analyst(llm):
    def macro_analyst_node(state):
        current_date = state.get("trade_date") or state.get("analysis_date")
        if not current_date:
            raise KeyError("trade_date")
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
        memory_section = build_memory_prompt_section(state, role="macro_regime", aliases=("news",))

        tools = [
            get_etf_info,
            get_etf_holdings,
            get_macro_regime_data,
            get_global_news,
            get_news,
        ]

        system_message = inject_memory_prompt_section((
            "你是一名ETF宏观分析师。你的任务是将ETF暴露结构、全球宏观定价、中国宏观发布日历数据和已验证的新闻催化剂整合为一个连贯的配置框架。"
            "先调用 get_etf_info 和 get_etf_holdings 识别基准/风格/行业暴露，再调用 get_macro_regime_data(curr_date, look_back_days) 构建跨资产制度图谱（含Tushare经济日历，通过cn_schedule实现）。"
            "仅使用 get_global_news 和针对性 get_news 验证或挑战数据已暗示的驱动因素。\n\n"
            + "不得产出割裂的清单。建立一条逻辑链：ETF暴露 → 宏观与政策制度 → 异常信号 → 情景敏感性 → 下个再平衡窗口催化剂 → 配置含义。\n\n"
            + get_no_process_narration_instruction() + "\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "开篇帽段必须直接给出宏观主判断、主导冲击方向和配置含义；不得以'概述：'、'结论：'等标签开头，"
            "不得写'本报告对…进行分析''本报告将…''本分析基于…'这类任务说明或背景交代。\n"
            "一级和二级标题只写中文标题，不要在括号中追加英文标题、英文翻译或英文注释。\n"
            "每个一级章节（一、二、三、四）标题后直接写2-3句结论段，先给宏观方向、冲击路径和配置含义，然后空行进入子章节。\n\n"
            "一、暴露与宏观主线\n"
            "  （一）ETF暴露与敏感因子\n"
            "    识别ETF主导仓位、头部持仓集中度及各仓位对哪些宏观变量敏感。\n"
            "  （二）利率信用与政策主驱动\n"
            "    整合全球利率、信用定价、地缘政治、中国政策背景和Tushare经济日历。\n"
            "二、异常信号与情景推演\n"
            "  （一）异常信号与传导链\n"
            "    解释哪些利差、实际利率、信用、避险或日历/事件异常相对近期基线偏离，以及如何传导至本ETF。\n"
            "  （二）情景敏感性与再平衡含义\n"
            "    解释哪些宏观情景有利或不利ETF主要暴露组合，以及对下次再平衡的含义。\n"
            "三、催化窗口与失效条件\n"
            "  （一）下个窗口关键催化\n"
            "    列出下一个再平衡窗口最重要的宏观发布与政策事件。\n"
            "  （二）基准情景失效点\n"
            "    说明哪些证据会打破当前基准判断。\n"
            "四、配置结论与跟踪表\n\n"
            "末尾附markdown摘要表。保持框架连贯且ETF特定，而非泛泛的宏观评论。\n\n"
            "当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用'分别为'连接，不得逐个单独陈述。"
            "若某项数据在已获取的数据源中不存在，直接省略该分析维度，不得输出'数据缺失''数据不足'等提示。"
            "开篇帽段和每个一级章节标题后的结论段都必须直接陈述结论。"
            "不得使用'本章''本节''本部分''该部分''这一节'等自指式开头（如'本章旨在梳理''本节核心结论指出''本部分结论表明''该部分说明'）。"
            + get_language_instruction()
        ), memory_section)

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
            report_acceptance_check=_looks_like_complete_macro_report,
            unexecuted_tool_recovery={
                "trigger_tool_names": [tool.name for tool in tools],
                "tool_payloads": [
                    {
                        "tool": get_etf_info,
                        "payload": {"ticker": asset_symbol, "curr_date": current_date},
                    },
                    {
                        "tool": get_etf_holdings,
                        "payload": {"ticker": asset_symbol, "curr_date": current_date},
                    },
                    {
                        "tool": get_macro_regime_data,
                        "payload": {"curr_date": current_date, "look_back_days": 365},
                    },
                    {
                        "tool": get_global_news,
                        "payload": {
                            "curr_date": current_date,
                            "look_back_days": 14,
                            "limit": 5,
                        },
                    },
                    {
                        "tool": get_news,
                        "payload": {
                            "ticker": asset_symbol,
                            "start_date": date_days_before(current_date, 30),
                            "end_date": current_date,
                        },
                    },
                ],
            },
        )
        report = normalize_chinese_role_terms(report) if report else report
        report = pre_judge_clean(report) if report else report
        report = validate_and_refine(report, llm, _REPORT_SPEC) if report else report
        report = post_judge_clean(report) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "macro_regime_report": report,
        })

    return macro_analyst_node
