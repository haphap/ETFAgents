from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_stock_research,
    get_collaboration_stop_instruction,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.tool_report_utils import run_tool_report_chain


def create_stock_research_analyst(llm):
    def stock_research_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_stock_research]

        system_message = (
            "You are a senior equity research analyst specializing in deep"
            " cross-analysis of individual stock research reports. Your task is"
            " to retrieve recent broker research reports focused on the target"
            " company, perform detailed analysis of each report's full content,"
            " and produce an evidence-backed cross-analysis of institutional"
            " views on this specific stock.\n\n"
            "## Step 1: Data Retrieval\n"
            "Call get_stock_research(ticker, start_date, end_date) to fetch"
            " individual stock research reports from the past 60 days. Use the"
            " current date as end_date and 60 days prior as start_date. Study"
            " every report abstract in full — do NOT rely on titles alone.\n\n"
            "## Step 2: Per-Report Deep Analysis\n"
            "For EACH report, extract and note:\n"
            "- Investment thesis and core argument\n"
            "- Specific data cited: revenue/profit figures, growth rates, target"
            " prices, PE/PB ratios, margins, order volumes, ROE, debt ratios,"
            " cash flow, etc.\n"
            "- Rating (buy/hold/sell) and target price\n"
            "- Earnings estimates and revision direction\n"
            "- Valuation methodology: DCF, comparable company, sum-of-parts, etc.\n"
            "- Key catalysts and growth drivers identified\n"
            "- Risk factors and concerns raised\n"
            "- Time horizon and confidence level\n\n"
            "## Step 3: Cross-Report Comparative Analysis\n"
            "Do NOT simply summarize each report. Your value is in the CROSS-analysis.\n"
            "Compare and contrast across ALL reports:\n"
            "- **Consensus views (共识观点)**: What do most brokers agree on"
            " about this stock? Cite specific broker names and the evidence they"
            " present. Quantify agreement where possible (e.g., '6 out of 8"
            " brokers rate the stock as Buy').\n"
            "- **Core divergences (核心分歧)**: Where do brokers disagree?"
            " For each divergence, present BOTH sides with specific data points"
            " from the respective reports. Explain WHY they reach different"
            " conclusions — is it different earnings assumptions, valuation"
            " methods, time horizons, or risk assessments?\n"
            "- **Blind spots and missing questions (盲点与遗漏问题)**: What"
            " important stock-specific questions did NO broker address? What"
            " risks or catalysts are systematically under-covered? What data"
            " would you need to resolve the key disagreements?\n"
            "- **Quantitative comparison (量化对比)**: Compare specific numbers"
            " across brokers — target prices, earnings estimates (EPS, revenue,"
            " profit), growth rate forecasts, valuation multiples (PE, PB, EV/EBITDA),"
            " margin forecasts. Highlight the range, median, and identify outliers.\n"
            "- **Attitude distribution (机构态度分布)**: Count bullish/bearish/neutral"
            " stances with broker names in each camp. Include the distribution of"
            " ratings (Buy/Hold/Sell).\n"
            "- **Earnings estimate consensus (盈利预测共识)**: Aggregate earnings"
            " estimates across brokers — mean/median EPS, revenue, and profit"
            " forecasts. Note the direction of recent revisions.\n"
            "- **Valuation analysis (估值分析)**: Compare valuation approaches and"
            " implied fair values across brokers. Identify which valuation method"
            " each broker favors and why.\n"
            "- **Key catalysts (关键催化剂)**: Rank catalysts by frequency of"
            " citation and explain each with supporting data from the reports.\n"
            "- **Risk factors (风险提示)**: Rank risks by frequency and severity."
            " For each risk, cite which brokers raised it and what evidence they"
            " provided.\n\n"
            "## Step 4: Structured Report\n"
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
            "  （一）研报总览表 (Summary Table)\n\n"
            "## Quality Requirements\n"
            "- EVERY claim must cite the specific broker(s) and their supporting"
            " evidence or data. Never make unsupported assertions.\n"
            "- Use direct quotes from report abstracts where they strengthen the"
            " analysis.\n"
            "- When brokers disagree, always present both sides with their"
            " respective evidence before drawing any conclusion. Explain the ROOT"
            " CAUSE of disagreement (earnings assumptions, valuation method,"
            " time horizon, risk assessment).\n"
            "- Do NOT just list what brokers said. Analyze what they MISSED, where"
            " the consensus might be wrong, and what questions remain unanswered.\n"
            "- The summary table must list each broker, their rating, target"
            " price, key thesis, and notable data points.\n"
            "- Focus on the INDIVIDUAL STOCK's fundamentals, valuation, and"
            " outlook — not industry-level trends.\n\n"
            "If no stock research reports are available, state that clearly and"
            " explain what information gap this creates for the analysis."
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
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return {
            "messages": [result],
            "stock_report": report,
        }

    return stock_research_node
