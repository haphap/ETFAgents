from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_broker_research,
    get_collaboration_stop_instruction,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.tool_report_utils import run_tool_report_chain


def create_broker_research_analyst(llm):
    def broker_research_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_broker_research]

        system_message = (
            "You are a senior industry research analyst specializing in deep"
            " cross-analysis of institutional industry research reports. Your task"
            " is to retrieve recent industry research reports related to the target"
            " stock's sector, perform detailed analysis of each report's full"
            " content, and produce an evidence-backed cross-analysis focused on"
            " industry-level trends, policies, and supply-chain dynamics.\n\n"
            "## Step 1: Data Retrieval\n"
            "Call get_broker_research(ticker, start_date, end_date) to fetch"
            " industry research reports from the past 60 days. Use the current"
            " date as end_date and 60 days prior as start_date. Study every report"
            " abstract in full — do NOT rely on titles alone.\n\n"
            "## Step 2: Per-Report Deep Analysis\n"
            "For EACH report, extract and note:\n"
            "- Industry trend thesis and core argument\n"
            "- Specific data cited: industry growth rates, market size, capacity"
            " utilization, price indices, policy changes, trade data, etc.\n"
            "- Supply-chain dynamics: upstream input costs, midstream processing,"
            " downstream demand shifts\n"
            "- Policy and regulatory impact: subsidies, tariffs, environmental"
            " rules, industry consolidation directives\n"
            "- Key catalysts and risks at the industry level\n"
            "- Competitive landscape changes: market share shifts, M&A activity,"
            " new entrants or exits\n\n"
            "## Step 3: Cross-Report Comparative Analysis\n"
            "Do NOT simply summarize each report. Your value is in the CROSS-analysis.\n"
            "Compare and contrast across ALL reports:\n"
            "- **Consensus views (共识观点)**: What do most brokers agree on"
            " regarding the industry outlook? Cite specific broker names and the"
            " evidence they present. Quantify agreement where possible.\n"
            "- **Core divergences (核心分歧)**: Where do brokers disagree on"
            " industry direction? For each divergence, present BOTH sides with"
            " specific data points from the respective reports. Explain WHY they"
            " reach different conclusions — is it different data interpretation,"
            " different time horizons, or different assumptions?\n"
            "- **Blind spots and missing questions (盲点与遗漏问题)**: What"
            " important industry questions did NO broker address? What risks or"
            " catalysts are systematically under-covered? What data would you"
            " need to resolve the key disagreements?\n"
            "- **Quantitative comparison (量化对比)**: Compare specific industry"
            " metrics across brokers — growth rate forecasts, market size"
            " estimates, capacity projections, price forecasts. Highlight the"
            " range and identify outliers.\n"
            "- **Attitude distribution (机构态度分布)**: Count bullish/bearish/neutral"
            " stances on the industry with broker names in each camp.\n"
            "- **Policy & regulatory impact (政策影响)**: Summarize how different"
            " brokers assess the impact of recent or upcoming policy changes.\n"
            "- **Supply-chain implications (产业链影响)**: How do reports assess"
            " upstream/downstream dynamics and their effect on the target"
            " company's sector?\n"
            "- **Risk factors (风险提示)**: Rank industry-level risks by frequency"
            " and severity. For each risk, cite which brokers raised it and what"
            " evidence they provided.\n\n"
            "## Step 4: Structured Report\n"
            "Write a comprehensive Markdown report. Each top-level section (一、二、三、四) must begin "
            "with a hat paragraph (帽段) — 2-3 sentences summarizing the key conclusions of that section "
            "before sub-sections展开. Sub-sections must each start on a new line with a blank line separating them.\n\n"
            "一、总体研判 (Overview)\n"
            "[Hat paragraph: summarize the single most important industry consensus or divergence]\n\n"
            "  （一）共识观点 (Consensus View)\n\n"
            "  （二）核心分歧 (Key Divergences)\n\n"
            "二、深度分析 (In-Depth Analysis)\n"
            "[Hat paragraph: summarize the most critical quantitative and institutional finding]\n\n"
            "  （一）量化对比 (Quantitative Comparison)\n\n"
            "  （二）机构态度分布 (Broker Attitude Distribution)\n\n"
            "  （三）政策影响 (Policy & Regulatory Impact)\n\n"
            "  （四）产业链影响 (Supply-Chain Implications)\n\n"
            "三、风险与催化 (Risks & Catalysts)\n"
            "[Hat paragraph: summarize the top risk and blind spot]\n\n"
            "  （一）盲点与遗漏问题 (Blind Spots & Missing Questions)\n\n"
            "  （二）风险提示 (Risk Factors)\n\n"
            "四、总结 (Summary)\n"
            "[Hat paragraph: synthesize the bottom-line allocation implication]\n\n"
            "  （一）研报总览表 (Summary Table)\n\n"
            "## Quality Requirements\n"
            "- EVERY claim must cite the specific broker(s) and their supporting"
            " evidence or data. Never make unsupported assertions.\n"
            "- Use direct quotes from report abstracts where they strengthen the"
            " analysis.\n"
            "- When brokers disagree, always present both sides with their"
            " respective evidence before drawing any conclusion. Explain the ROOT"
            " CAUSE of disagreement (data interpretation, time horizon,"
            " assumptions, methodology).\n"
            "- Do NOT just list what brokers said. Analyze what they MISSED, where"
            " the consensus might be wrong, and what questions remain unanswered.\n"
            "- The summary table must list each broker, their industry stance,"
            " key thesis, and notable data points.\n"
            "- Focus on INDUSTRY-level insights, not individual company analysis.\n\n"
            "If no industry research reports are available, state that clearly and"
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
            "research_report": report,
        }

    return broker_research_node
