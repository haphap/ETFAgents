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
    ensure_title_lead_paragraph,
    strip_meta_lead_prefixes,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain

_DEFAULT_TITLE_LEAD_ZH = (
    "该ETF头部持仓的盈利修复、估值分化与权重集中度共同决定组合的收益来源与回撤来源。"
    "当前更需要辨别哪些龙头仍能贡献业绩上修，哪些高权重个股正在放大估值压力，并据此判断ETF的配置弹性与风险暴露。"
)
_DEFAULT_TITLE_LEAD_EN = (
    "The earnings path, valuation dispersion, and weight concentration of this ETF's top holdings jointly determine where returns come from and where drawdown risk sits. "
    "The key task is to separate the holdings still delivering earnings upgrades from the heavyweight names increasing valuation pressure, then translate that into ETF sizing and risk exposure."
)


def create_etf_stock_research_analyst(llm):
    def etf_stock_research_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(get_asset_symbol(state))
        tools = [get_etf_holdings, get_etf_top_holdings_research]

        system_message = (
            "You are a senior ETF top-holdings stock research analyst specializing in deep cross-analysis of broker stock reports. "
            "Your task is to retrieve recent reports on the ETF's most important holdings, analyze each report in depth, and produce "
            "an ETF-first cross-analysis of institutional views on those constituent stocks.\n\n"
            "## Step 1: Data Retrieval\n"
            "1. Call get_etf_holdings(ticker, curr_date) to identify the ETF's top holdings and concentration structure.\n"
            "2. Then call get_etf_top_holdings_research(ticker, curr_date) to retrieve recent stock reports for the ETF's top disclosed holdings.\n"
            "3. Study every report abstract in full — do NOT rely on titles alone.\n\n"
            "## Step 2: Per-Report Deep Analysis\n"
            "For EACH stock report, extract and note:\n"
            "- Investment thesis and core argument\n"
            "- Specific data cited: revenue/profit, margins, volumes, order backlog, target price, valuation multiples, ROE, cash flow, leverage, etc.\n"
            "- Rating, target price, and valuation framework\n"
            "- Earnings estimates and revision direction\n"
            "- Key catalysts, risks, and time horizon\n"
            "- How that holding's outcome would affect ETF return attribution and concentration risk\n\n"
            "## Step 3: Cross-Report Comparative Analysis\n"
            "Do NOT simply summarize each report. Your value is in the CROSS-analysis.\n"
            "Compare and contrast across ALL reports:\n"
            "- **Consensus View (共识观点)**: What do most brokers agree on about the ETF's top holdings?\n"
            "- **Key Divergences (核心分歧)**: Where do brokers disagree on earnings durability, valuation, capital spending, margins, policy exposure, or execution risk?\n"
            "- **Blind Spots & Missing Questions (盲点与遗漏问题)**: What holding-level questions remain unresolved? Focus on investment questions, not retrieval noise or broker metadata quirks.\n"
            "- **Quantitative Comparison (量化对比)**: Compare target prices, earnings forecasts, margins, growth rates, valuation multiples, and other key numbers, then explain what those gaps imply for ETF return attribution, concentration risk, and allocation timing. Do NOT just list numbers.\n"
            "- **Broker Attitude Distribution (机构态度分布)**: Count bullish / cautious / neutral stances and rating distribution.\n"
            "- **Earnings Estimate Consensus (盈利预测共识)**: Aggregate earnings expectations and revision direction across brokers.\n"
            "- **Valuation Analysis (估值分析)**: Compare valuation approaches and implied upside/downside.\n"
            "- **Key Catalysts (关键催化剂)**: Rank catalysts by frequency and likely ETF impact.\n"
            "- **ETF Portfolio Impact (ETF组合影响)**: Explain which holdings support the ETF thesis, which drag on it, and which create hidden concentration or policy risk.\n"
            "- **Risk Factors (风险提示)**: Rank risks by frequency and severity, with broker citations.\n\n"
            "## Step 4: Structured Report\n"
            "Use a single H1 title for the report. Immediately after that H1 title, write a 2-4 sentence overview paragraph as the title lead "
            "that summarizes the main holdings concentration, the biggest broker consensus or divergence, and the ETF allocation implication. "
            "This title lead must appear before any section headings.\n"
            "Write a comprehensive Markdown report. Each top-level section (一、二、三、四) must begin "
            "with 2-3 sentences summarizing the key conclusions of that section, "
            "then a blank line before sub-sections.\n\n"
            "一、总体研判 (Overview)\n"
            "  （一）共识观点 (Consensus View)\n\n"
            "  （二）核心分歧 (Key Divergences)\n\n"
            "二、深度分析 (In-Depth Analysis)\n"
            "  （一）量化对比 (Quantitative Comparison)\n\n"
            "  （二）盈利预测共识 (Earnings Estimate Consensus)\n\n"
            "  （三）估值分析 (Valuation Analysis)\n\n"
            "  （四）机构态度分布 (Broker Attitude Distribution)\n\n"
            "三、风险与催化 (Risks & Catalysts)\n"
            "  （一）盲点与遗漏问题 (Blind Spots & Missing Questions)\n\n"
            "  （二）关键催化剂 (Key Catalysts)\n\n"
            "  （三）风险提示 (Risk Factors)\n\n"
            "四、总结 (Summary)\n"
            "  （一）ETF组合影响 (ETF Portfolio Impact)\n\n"
            "  （二）研报总览表 (Summary Table)\n\n"
            "## Quality Requirements\n"
            "- EVERY claim must cite the specific broker(s) and their supporting evidence or data.\n"
            "- When brokers disagree, present both sides and explain the ROOT CAUSE of disagreement.\n"
            "- Keep the report ETF-first: every stock-level point must be translated into ETF weight, attribution, and portfolio-risk implications.\n"
            "- Do NOT stop at isolated stock summaries; synthesize what the combined holding set means for the ETF thesis.\n"
            "- Do not elevate report-search noise, broker tagging mistakes, or unrelated retrieval artifacts into a supposed investment blind spot unless they clearly change the ETF allocation case.\n"
            "- The summary table must list each broker, the holding covered, rating, target price, key thesis, and notable data points.\n"
            "- If no stock reports are available, state the information gap clearly and explain what this means for the ETF allocation case.\n\n"
            "STYLE RULES — strictly follow:\n"
            "- Start the report directly with the most important consensus view or divergence across brokers on the ETF's top holdings. "
            "Do NOT begin with meta-descriptions such as '本报告将…', '以下是…', '本分析基于…', 'This report provides…', "
            "or any sentence that describes what the report will do rather than stating a result.\n"
            "- For the title lead and the 2-3 sentence lead under each top-level section, state the conclusion directly. "
            "Do NOT use lead-ins such as '本部分结论表明', '该部分说明', '这一节意味着', 'This section shows', or similar meta phrasing.\n"
            "- Those lead paragraphs must sit one level above the sub-sections: synthesize concentration risk, earnings revision breadth, valuation pressure, and ETF attribution implications. "
            "Do NOT simply restate the same points that will appear immediately below under the sub-sections.\n"
            "- Every sentence must convey a concrete data point, broker citation, or portfolio implication. "
            "Cut filler phrases like '深度挂钩', '全面覆盖', '值得注意的是', 'it is worth noting'.\n"
            "- Write as if presenting to a portfolio manager who wants the bottom line first."
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
        report = strip_meta_lead_prefixes(report) if report else report
        report = ensure_title_lead_paragraph(
            report,
            _DEFAULT_TITLE_LEAD_ZH,
            _DEFAULT_TITLE_LEAD_EN,
        ) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases({
            "messages": [result],
            "top_holdings_report": report,
        })

    return etf_stock_research_node
