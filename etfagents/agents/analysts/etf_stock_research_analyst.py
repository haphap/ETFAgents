from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_holdings,
    get_etf_top_holdings_research,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.report_leads import (
    get_concise_heading_instruction,
    get_no_title_instruction,
    get_topic_and_term_style_instruction,
    strip_report_title,
    strip_self_referential_meta_leads,
)
from etfagents.agents.utils.validate_refine import validate_and_refine
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain


_VALIDATION_RULES = (
    "### 内容覆盖\n"
    "- 是否逐份分析每份个股报告的论点、数据和评级？\n"
    "- 是否进行了跨报告交叉分析（共识分歧、盈利预测、估值对比）？\n"
    "- 是否将个股结论转化为ETF权重、归因和组合风险含义？\n"
    "- 是否统计了机构评级分布？\n"
    "- 末尾是否附研报总览表？"
)


def create_etf_stock_research_analyst(llm):
    def etf_stock_research_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
        tools = [get_etf_holdings, get_etf_top_holdings_research]

        system_message = (
            "你是一名资深ETF头部持仓研究分析师，专注于券商个股研究报告的深度交叉分析。"
            "你的任务是检索ETF最重要持仓的近期报告，深入分析每份报告，"
            "产出以ETF为优先的机构观点交叉分析。\n\n"
            "## 第一步：数据获取\n"
            "1. 调用 get_etf_holdings(ticker, curr_date) 获取ETF前十大持仓与集中度结构。\n"
            "2. 调用 get_etf_top_holdings_research(ticker, curr_date) 获取ETF头部披露持仓的近期个股报告。\n"
            "3. 逐份研读报告摘要全文——不得仅凭标题判断。\n\n"
            "## 第二步：逐份深度分析\n"
            "对每份个股报告，提取并记录：\n"
            "- 投资论点与核心论据\n"
            "- 引用的具体数据：营收/利润、毛利率、销量、订单 backlog、目标价、估值倍数、ROE、现金流、杠杆等\n"
            "- 评级、目标价与估值框架\n"
            "- 盈利预测与修正方向\n"
            "- 关键催化剂、风险与时间跨度\n"
            "- 该持仓的结果如何影响ETF收益归因与集中度风险\n\n"
            "## 第三步：跨报告比较分析\n"
            "不得简单罗列各报告。你的价值在于交叉分析。\n"
            "对比所有报告：\n"
            "- **共识观点 (Consensus View)**：多数券商对ETF头部持仓持何共识？\n"
            "- **核心分歧 (Key Divergences)**：券商在盈利持续性、估值、资本开支、利润率、政策暴露或执行风险上有何分歧？\n"
            "- **盲点与遗漏问题 (Blind Spots & Missing Questions)**：哪些持仓层面的问题仍未解决？聚焦投资问题，而非检索噪声或券商标签错误。\n"
            "- **量化对比 (Quantitative Comparison)**：比较目标价、盈利预测、利润率、增速、估值倍数等关键数字，解释这些差异对ETF收益归因、集中度风险和配置节奏的含义。不得仅罗列数字。\n"
            "- **机构态度分布 (Broker Attitude Distribution)**：统计看多/谨慎/中性立场与评级分布。\n"
            "- **盈利预测共识 (Earnings Estimate Consensus)**：汇总各券商盈利预期与修正方向。\n"
            "- **估值分析 (Valuation Analysis)**：比较估值方法与隐含上行/下行空间。\n"
            "- **关键催化剂 (Key Catalysts)**：按频次与可能的ETF影响排列催化剂。\n"
            "- **ETF组合影响 (ETF Portfolio Impact)**：解释哪些持仓支撑ETF论点、哪些拖累、哪些造成隐性集中度或政策风险。\n"
            "- **风险提示 (Risk Factors)**：按频次与严重程度排列风险，附券商引用。\n\n"
            "## 第四步：结构化报告\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "撰写全面的Markdown报告。每个一级章节（一、二、三、四）以2-3句导语开头总结该节核心结论，"
            "然后空行进入子章节。\n\n"
            "一、核心持仓共识与分歧\n"
            "  （一）共识主线\n\n"
            "  （二）分歧焦点\n\n"
            "二、盈利、估值与机构态度\n"
            "  （一）关键数据对比\n\n"
            "  （二）盈利预期对比\n\n"
            "  （三）估值分层\n\n"
            "  （四）机构观点分布\n\n"
            "三、催化、盲点与风险边界\n"
            "  （一）未解问题\n\n"
            "  （二）关键催化\n\n"
            "  （三）风险边界\n\n"
            "四、ETF影响与研报总览\n"
            "  （一）ETF组合影响\n\n"
            "  （二）研报总览表\n\n"
            "## 质量要求\n"
            "- 每项论点必须引用具体券商及支撑证据或数据。\n"
            "- 券商分歧时，呈现双方观点并解释分歧根源。\n"
            "- 保持ETF优先：每个个股层面的要点必须转化为ETF权重、归因和组合风险含义。\n"
            "- 不得停留在孤立的个股摘要；综合持仓集合对ETF论点的整体含义。\n"
            "- 不得将报告搜索噪声、券商标签错误或无关检索伪影提升为投资盲点，除非它们明确改变ETF配置逻辑。\n"
            "- 摘要表必须列出每家券商、覆盖的持仓、评级、目标价、核心论点和重要数据点。\n"
            "- 若无个股报告，明确说明信息缺口及其对ETF配置逻辑的含义。\n\n"
            "## 风格要求\n"
            "- 直接以券商对ETF头部持仓最重要的共识或分歧开篇。"
            "不得以'本报告将…'、'以下是…'、'本分析基于…'、'This report provides…'等元描述开头。\n"
            "- 标题导语与每个一级章节导语直接陈述结论。"
            "不得使用'本节''本部分''该部分''这一节'等自指式开头（如'本节核心结论指出''本部分结论表明''该部分说明'）。\n"
            "- 当连续出现同类变量（如多条均线、多个价位、多个指标值）时，合并为一句并用'分别为'连接，不得逐个单独陈述。\n"
            "- 若某项数据在已获取的数据源中不存在，直接省略该分析维度，不得输出'数据缺失''数据不足'等提示。\n"
            "- 导语段落必须高于子章节层面：综合集中度风险、盈利修正广度、估值压力和ETF归因含义。"
            "不得简单复述即将在子章节中出现的相同要点。\n"
            "- 每句话必须传达具体数据点、券商引用或组合含义。"
            "删除'深度挂钩'、'全面覆盖'、'值得注意的是'、'it is worth noting'等填充语。\n"
            "- 像向只想看结论的投资组合经理汇报一样写作。"
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
        report = validate_and_refine(report, llm, _VALIDATION_RULES) if report else report
        report = strip_report_title(report) if report else report
        report = strip_self_referential_meta_leads(report) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "top_holdings_report": report,
        })

    return etf_stock_research_node
