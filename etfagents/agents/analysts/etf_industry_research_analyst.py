from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from etfagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_collaboration_stop_instruction,
    get_etf_holdings,
    get_etf_industry_research,
    get_language_instruction,
    normalize_chinese_role_terms,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain


def create_etf_industry_research_analyst(llm):
    def etf_industry_research_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(get_asset_symbol(state))
        tools = [get_etf_holdings, get_etf_industry_research]

        system_message = (
            "You are a senior ETF industry research analyst specializing in deep cross-analysis of institutional industry reports. "
            "Your task is to start from the ETF's heavy holdings, map those holdings into the industry keywords actually used by broker "
            "research reports, and then produce an evidence-backed cross-analysis of the ETF's dominant industry exposures.\n\n"
            "## Step 1: Data Retrieval\n"
            "1. Call get_etf_holdings(ticker, curr_date) to identify the ETF's top holdings and concentration structure.\n"
            "2. Then call get_etf_industry_research(ticker, curr_date) to retrieve industry research that is derived from those heavy holdings. "
            "That tool already resolves the broker-search keyword from holding-level stock reports when possible, so treat it as the authoritative "
            "industry-report set for this ETF.\n"
            "3. Study every report abstract in full — do NOT rely on report titles alone.\n\n"
            "## Step 2: Per-Report Deep Analysis\n"
            "For EACH industry report, extract and note:\n"
            "- Industry trend thesis and core argument\n"
            "- Specific data cited: demand growth, capacity, prices, inventories, utilization, import/export, policy targets, etc.\n"
            "- Supply-chain dynamics: upstream cost pressure, midstream processing, downstream demand and substitution\n"
            "- Policy and regulatory impact: subsidies, quotas, tariffs, environmental constraints, consolidation directives\n"
            "- Key catalysts and risks at the industry level\n"
            "- Which ETF holdings are most exposed to that industry thesis\n\n"
            "## Step 3: Cross-Report Comparative Analysis\n"
            "Do NOT simply summarize each report. Your value is in the CROSS-analysis.\n"
            "Compare and contrast across ALL reports:\n"
            "- **Consensus View (共识观点)**: What do most brokers agree on regarding the ETF's dominant industries? Cite broker names and evidence.\n"
            "- **Key Divergences (核心分歧)**: Where do brokers disagree on industry direction, pricing power, policy impact, supply-demand balance, or timing?\n"
            "- **Blind Spots & Missing Questions (盲点与遗漏问题)**: What important ETF-industry questions did no broker address? Do NOT treat broker tagging noise, search mismatches, or retrieval artifacts as an investment blind spot unless they recur across reports and directly change the ETF allocation case.\n"
            "- **Quantitative Comparison (量化对比)**: Compare growth forecasts, price assumptions, capacity/inventory signals, and policy-sensitive metrics, then explain what those ranges imply for industry allocation timing, ETF earnings sensitivity, and weighted-holdings return attribution. Do NOT just list numbers.\n"
            "- **Broker Attitude Distribution (机构态度分布)**: Count bullish / cautious / neutral stances by industry theme.\n"
            "- **Policy & Regulatory Impact (政策影响)**: Explain how policy changes transmit into the ETF's industry exposures.\n"
            "- **Supply-Chain Implications (产业链影响)**: Explain upstream/downstream transmission and which holdings benefit or get hurt.\n"
            "- **ETF Exposure Mapping (ETF暴露映射)**: Map each major industry conclusion back to ETF weight concentration, cyclicality, policy sensitivity, and allocation timing.\n"
            "- **Risk Factors (风险提示)**: Rank industry-level risks by frequency and severity, with broker citations.\n\n"
            "## Step 4: Structured Report\n"
            "Write a comprehensive Markdown report. Each top-level section (一、二、三、四) must begin "
            "with 2-3 sentences summarizing the key conclusions of that section, "
            "then a blank line before sub-sections.\n\n"
            "一、总体研判 (Overview)\n"
            "  （一）共识观点 (Consensus View)\n\n"
            "  （二）核心分歧 (Key Divergences)\n\n"
            "二、深度分析 (In-Depth Analysis)\n"
            "  （一）量化对比 (Quantitative Comparison)\n\n"
            "  （二）机构态度分布 (Broker Attitude Distribution)\n\n"
            "  （三）政策影响 (Policy & Regulatory Impact)\n\n"
            "  （四）产业链影响 (Supply-Chain Implications)\n\n"
            "三、风险与催化 (Risks & Catalysts)\n"
            "  （一）盲点与遗漏问题 (Blind Spots & Missing Questions)\n\n"
            "  （二）风险提示 (Risk Factors)\n\n"
            "四、总结 (Summary)\n"
            "  （一）ETF暴露映射 (ETF Exposure Mapping)\n\n"
            "  （二）研报总览表 (Summary Table)\n\n"
            "## Quality Requirements\n"
            "- EVERY claim must cite the specific broker(s) and supporting evidence or data.\n"
            "- When brokers disagree, present both sides and explain the ROOT CAUSE of disagreement.\n"
            "- Keep the report ETF-first: industry conclusions must be translated into holdings impact and ETF allocation implications.\n"
            "- Do NOT drift into standalone single-stock valuation work. The emphasis is industry cross-analysis and ETF transmission.\n"
            "- Operational noise such as search-keyword leakage, broker classification slippage, or retrieval mismatches is not itself a macro or industry conclusion; mention it only if it materially distorts the ETF allocation case.\n"
            "- The summary table must list each broker, the industry keyword covered, the stance, the key thesis, and notable data points.\n"
            "- If no industry reports are available, state the information gap clearly and explain what this means for ETF exposure assessment.\n\n"
            "STYLE RULES — strictly follow:\n"
            "- Start the report directly with the single most important industry consensus or divergence finding. "
            "Do NOT begin with meta-descriptions such as '本报告将…', '以下是…', '本分析基于…', 'This report provides…', "
            "or any sentence that describes what the report will do rather than stating a result.\n"
            "- Every sentence must convey a concrete data point, broker citation, or allocation implication. "
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
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "holdings_industry_report": report,
            }
        )

    return etf_industry_research_node
