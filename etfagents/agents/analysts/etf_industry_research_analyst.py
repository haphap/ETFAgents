from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_holdings,
    get_etf_industry_research,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.report_leads import (
    collect_top_section_marks,
    contains_markdown_table,
    find_top_sections_missing_leads,
    get_concise_heading_instruction,
    get_no_process_narration_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
    has_invalid_opening_cap,
    post_judge_clean,
    pre_judge_clean,
)
from etfagents.agents.utils.validate_refine import AnalystReportSpec, validate_and_refine
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.agents.utils.analysis_memory import (
    build_memory_prompt_section,
    inject_memory_prompt_section,
)
from etfagents.tool_report_utils import run_tool_report_chain


_REPORT_SPEC = AnalystReportSpec(
    analyst_name="holdings_industry",
    required_top_sections=("一", "二", "三", "四"),
    require_top_section_leads=True,
    custom_rules_markdown=(
        "### 内容覆盖\n"
        "- 是否逐份深度分析每份行业报告（而非仅凭标题判断）？\n"
        "- 是否进行了跨报告交叉分析（共识、分歧、量化对比）？\n"
        "- 是否将行业结论转化为ETF持仓影响和配置含义？\n"
        "- 是否统计了机构态度分布（看多/谨慎/中性）？\n"
        "- 末尾是否附研报总览表？"
    ),
)

_HOLDINGS_INDUSTRY_REQUIRED_TOP_SECTIONS = set(_REPORT_SPEC.required_top_sections)
# Anchors must match the section names emitted by the prompt template below.
_HOLDINGS_INDUSTRY_REQUIRED_MARKERS = ("ETF暴露", "研报总览")
_HOLDINGS_INDUSTRY_DRAFT_MARKERS = ("券商", "共识", "分歧", "ETF")


def _looks_like_complete_holdings_industry_report(report: str) -> bool:
    """Positive contract for accepting holdings-industry research into graph state."""
    content = report or ""
    if not content.strip() or has_invalid_opening_cap(content):
        return False

    section_marks = collect_top_section_marks(content)
    if not _HOLDINGS_INDUSTRY_REQUIRED_TOP_SECTIONS.issubset(section_marks):
        return False

    if find_top_sections_missing_leads(content, _REPORT_SPEC.required_top_sections):
        return False

    return (
        all(marker in content for marker in _HOLDINGS_INDUSTRY_REQUIRED_MARKERS)
        and contains_markdown_table(content)
    )


def _looks_like_holdings_industry_draft(report: str) -> bool:
    """Accept report-shaped drafts so validate_and_refine can repair lead issues."""
    content = pre_judge_clean(report or "")
    if not content.strip() or has_invalid_opening_cap(content):
        return False

    section_marks = collect_top_section_marks(content)
    has_strict_sections = _HOLDINGS_INDUSTRY_REQUIRED_TOP_SECTIONS.issubset(section_marks)

    return (
        (has_strict_sections or all(marker in content for marker in _HOLDINGS_INDUSTRY_DRAFT_MARKERS))
        and "研报总览" in content
        and contains_markdown_table(content)
    )


def _holdings_industry_strict_failures(report: str) -> list[str]:
    """Explain why a holdings-industry report still fails the final contract."""
    content = report or ""
    failures: list[str] = []
    if not content.strip():
        return ["报告为空"]
    if has_invalid_opening_cap(content):
        failures.append("开篇帽段无效：不得以标题、章节、列表、表格、结论标签或过程话术开头")

    section_marks = collect_top_section_marks(content)
    missing_sections = sorted(_HOLDINGS_INDUSTRY_REQUIRED_TOP_SECTIONS - section_marks)
    if missing_sections:
        failures.append("缺少一级章节：" + "、".join(missing_sections))

    missing_leads = find_top_sections_missing_leads(content, _REPORT_SPEC.required_top_sections)
    if missing_leads:
        failures.append(
            "一级章节标题后缺少1-2句引导句："
            + "、".join(missing_leads)
        )

    missing_markers = [
        marker for marker in _HOLDINGS_INDUSTRY_REQUIRED_MARKERS if marker not in content
    ]
    if missing_markers:
        failures.append("缺少关键词：" + "、".join(missing_markers))
    if not contains_markdown_table(content):
        failures.append("缺少Markdown表格，研报总览表必须使用以 | 开头和结尾的表格")
    return failures


def _strict_refine_holdings_industry_report(report: str, llm) -> str:
    """One targeted repair pass for reports that fail the holdings-industry contract."""
    failures = _holdings_industry_strict_failures(report)
    if not failures:
        return report

    prompt = (
        "你是一名ETF持仓行业研究报告修订员。下面的报告没有通过最终结构检查。"
        "请重新生成一份完整报告，不要解释修订过程，只输出最终Markdown正文。\n\n"
        "必须满足以下硬性结构：\n"
        "1. 第一段是2-4句开篇帽段，不得以标题、编号、表格、项目符号或“结论：”开头。\n"
        "2. 必须且只能使用以下四个一级章节：\n"
        "一、行业主线与分歧焦点\n"
        "二、景气、政策与产业链验证\n"
        "三、未解问题与风险边界\n"
        "四、ETF影响与研报总览\n"
        "3. 每个一级章节标题下一行必须先写1-2句引导句，然后才能写（一）格式子章节；"
        "引导句必须是具体判断句，包含券商证据、ETF暴露、权重贡献、配置含义或风险边界。\n"
        "4. 第四章必须包含“（一）ETF暴露与配置含义”和“（二）研报总览表”。\n"
        "5. 研报总览表必须是标准Markdown表格，表头至少包含：券商、行业关键词、立场、核心论点、重要数据点。\n"
        "6. 不得使用#或##标题，不得写过程话术，不得输出方括号提示语，不得使用“本章/本节/本部分旨在”等自指句。\n\n"
        "未通过原因：\n"
        + "\n".join(f"- {failure}" for failure in failures)
        + "\n\n原始报告：\n"
        + report
    )
    try:
        response = llm.invoke(prompt)
    except Exception:
        return report
    refined = extract_text_content(getattr(response, "content", response))
    return refined or report


def create_etf_industry_research_analyst(llm):
    def etf_industry_research_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
        memory_section = build_memory_prompt_section(
            state,
            role="holdings_industry",
            aliases=("broker_research", "etf_macro"),
        )
        tools = [get_etf_holdings, get_etf_industry_research]

        system_message = inject_memory_prompt_section((
            "你是一名资深ETF行业研究分析师，专注于机构行业研究报告的深度交叉分析。"
            "你的任务是从ETF重仓股出发，追溯这些持仓在券商研究报告中实际使用的行业关键词，"
            "然后产出一份有证据支撑的ETF主导行业暴露交叉分析。\n\n"
            "先完成以下取数动作并直接据此成文：\n"
            "1. 调用 get_etf_holdings(ticker, curr_date) 获取ETF前十大持仓与集中度结构。\n"
            "2. 调用 get_etf_industry_research(ticker, curr_date) 获取基于重仓股衍生的行业研究。"
            "该工具已尽可能从持仓级个股报告中解析出券商搜索关键词，视为本ETF的权威行业报告集。\n"
            "3. 逐份研读报告摘要全文——不得仅凭标题判断。\n\n"
            "对每份行业报告，逐份提取并记录：\n"
            "- 行业趋势论点与核心论据\n"
            "- 引用的具体数据：需求增速、产能、价格、库存、开工率、进出口、政策目标等\n"
            "- 产业链动态：上游成本压力、中游加工、下游需求与替代\n"
            "- 政策与监管影响：补贴、配额、关税、环保约束、整合指令\n"
            "- 行业层面的关键催化剂与风险\n"
            "- 哪些ETF持仓对该行业论点暴露最大\n\n"
            "跨报告比较时，不得简单罗列各报告。你的价值在于交叉分析。\n"
            "对比所有报告：\n"
            "- **共识观点 (Consensus View)**：多数券商对ETF主导行业持何共识？引用券商名称与证据。\n"
            "- **核心分歧 (Key Divergences)**：券商在行业方向、定价权、政策影响、供需平衡或节奏上有何分歧？\n"
            "- **盲点与遗漏问题 (Blind Spots & Missing Questions)**：哪些重要的ETF-行业问题没有任何券商涉及？此模块仅关注真正的行业未知——供需、定价权、政策传导、库存、资本开支、竞争格局或成本转嫁。不得讨论数据源分类噪声、券商标签噪声、搜索错配或检索伪影。\n"
            "- **量化对比 (Quantitative Comparison)**：比较增速预测、价格假设、产能/库存信号和政策敏感指标，解释这些区间对行业配置节奏、ETF盈利敏感度和加权持仓收益归因的含义。不得仅罗列数字。\n"
            "- **机构态度分布 (Broker Attitude Distribution)**：按行业主题统计看多/谨慎/中性立场。\n"
            "- **政策影响 (Policy & Regulatory Impact)**：解释政策变化如何传导至ETF的行业暴露。\n"
            "- **产业链影响 (Supply-Chain Implications)**：解释上下游传导及哪些持仓受益或受损。\n"
            "- **ETF暴露与配置含义 (ETF Exposure Read-Through)**：将每个主要行业结论与ETF权重集中度、周期性、政策敏感度和配置节奏挂钩。\n"
            "- **风险提示 (Risk Factors)**：按频次与严重程度排列行业风险，附券商引用。\n\n"
            + get_no_process_narration_instruction() + "\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "撰写全面的Markdown报告。保持视觉节奏紧凑，与其他分析师报告一致："
            "每个一级章节（一、二、三、四）必须按'一级标题 -> 1-2句引导句 -> 子章节标题'的顺序输出。"
            "开篇帽段负责统领全文：同时覆盖行业主线、宏观或政策约束、ETF配置含义。"
            "第一章标题后的引导句只负责导入本章：点明哪些券商形成共识、哪些券商或证据构成分歧，不再重复全文配置判断；"
            "二、三、四章标题后的引导句必须是带券商证据、ETF权重或配置含义的判断句，不是任务说明；"
            "不得写'本章''本节''本部分''旨在''梳理''等自指式开头，也不得写'导语：'标签。"
            "不得在结论段与首个子章节之间插入额外空行、重复标题行或松散填充。\n\n"
            "下面结构中的引导句说明用于约束写作，不得把方括号说明原样输出到报告中。\n"
            "一、行业主线与分歧焦点\n"
            "[直接写1-2句引导句：点明券商共识来源、分歧来源和ETF配置含义]\n"
            "  （一）共识主线\n\n"
            "  （二）分歧焦点\n\n"
            "二、景气、政策与产业链验证\n"
            "[直接写1-2句引导句：用价格、库存、政策或产业链证据说明景气验证结论]\n"
            "  （一）景气与价格对比\n\n"
            "  （二）机构观点分布\n\n"
            "  （三）政策传导\n\n"
            "  （四）产业链验证\n\n"
            "三、未解问题与风险边界\n"
            "[直接写1-2句引导句：说明未解问题、主要风险和ETF配置边界]\n"
            "  （一）未解问题\n\n"
            "  （二）风险边界\n\n"
            "四、ETF影响与研报总览\n"
            "[直接写1-2句引导句：把行业结论映射到ETF暴露、权重贡献和配置节奏]\n"
            "  （一）ETF暴露与配置含义\n\n"
            "  （二）研报总览表\n\n"
            "## 质量要求\n"
            "- 每项论点必须引用具体券商及支撑证据或数据。\n"
            "- 券商分歧时，呈现双方观点并解释分歧根源。\n"
            "- 保持ETF优先：行业结论必须转化为持仓影响与ETF配置含义。\n"
            "- 不得偏移到独立的个股估值分析。重点是行业交叉分析与ETF传导。\n"
            "- 数据源分类噪声、券商标签噪声、搜索关键词泄漏和检索错配绝不能作为本分析师的报告内容。应完全排除，而非作为盲点、注意事项或信息缺口呈现。\n"
            "- 摘要表必须列出每家券商、覆盖的行业关键词、立场、核心论点和重要数据点。\n"
            "- 若无行业研究报告，明确说明信息缺口及其对ETF暴露评估的含义。\n\n"
            "## 风格要求\n"
            "- 直接以最重要的行业共识或分歧发现开篇。"
            "不得以'本报告将…'、'以下是…'、'本分析基于…'、'This report provides…'等元描述开头。\n"
            "- 开篇帽段和每个一级章节标题后的引导句都必须直接陈述结论。"
            "不得使用'本章''本节''本部分''该部分''这一节'等自指式开头（如'本章旨在梳理''本节核心结论指出''本部分结论表明''该部分说明'）。\n"
            "- 开篇帽段要统领全文；第一章引导句要承接'行业主线与分歧焦点'，只概括共识来源与分歧来源，避免再次写成全文总判断。\n"
            "- 当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用'分别为'连接，不得逐个单独陈述。\n"
            "- 若某项数据在已获取的数据源中不存在，直接省略该分析维度，不得输出'数据缺失''数据不足'等提示。\n"
            "- 标题后的结论段必须高于子章节层面：综合更广泛的ETF暴露、风格、周期敏感度、估值/风险传导和配置含义。"
            "不得简单复述即将在子章节中出现的相同要点。\n"
            "- 每句话必须传达具体数据点、券商引用或配置含义。"
            "删除'深度挂钩'、'全面覆盖'、'值得注意的是'、'it is worth noting'等填充语。\n"
            "- 像向只想看结论的投资组合经理汇报一样写作。"
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
            report_acceptance_check=_looks_like_holdings_industry_draft,
            unexecuted_tool_recovery={
                "trigger_tool_names": [tool.name for tool in tools],
                "tool_payloads": [
                    {
                        "tool": get_etf_holdings,
                        "payload": {"ticker": asset_symbol, "curr_date": current_date},
                    },
                    {
                        "tool": get_etf_industry_research,
                        "payload": {"ticker": asset_symbol, "curr_date": current_date},
                    },
                ],
            },
        )
        report = normalize_chinese_role_terms(report) if report else report
        report = pre_judge_clean(report) if report else report
        report = validate_and_refine(report, llm, _REPORT_SPEC) if report else report
        report = post_judge_clean(report) if report else report
        if report and not _looks_like_complete_holdings_industry_report(report):
            report = _strict_refine_holdings_industry_report(report, llm)
            report = post_judge_clean(report) if report else report
        if report and not _looks_like_complete_holdings_industry_report(report):
            report = ""
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "holdings_industry_report": report,
            }
        )

    return etf_industry_research_node
