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
from etfagents.agents.utils.report_leads import (
    ensure_title_lead_paragraph,
    get_concise_heading_instruction,
    get_no_title_instruction,
    normalize_section_headings,
    get_topic_and_term_style_instruction,
    strip_report_title,
    strip_meta_lead_prefixes,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, with_state_aliases
from etfagents.tool_report_utils import run_tool_report_chain

_DEFAULT_TITLE_LEAD_ZH = (
    "该ETF的行业暴露强弱取决于重仓股映射出的主导产业，是否同时具备景气延续、政策支撑与盈利兑现三重确认。"
    "若主导产业的共识继续强化且分歧集中在节奏而非方向，配置逻辑更清晰；若行业分歧开始落到价格、供需和政策传导的根部，ETF暴露就需要重新评估。"
)
_DEFAULT_TITLE_LEAD_EN = (
    "The strength of this ETF's industry exposure depends on whether the dominant industries mapped from its heavyweight holdings still have simultaneous confirmation from cycle, policy, and earnings transmission. "
    "If broker consensus remains constructive and the disagreement is mostly about timing, the allocation case stays clearer; if the split reaches pricing, supply-demand, or policy transmission itself, the ETF exposure should be reassessed."
)
_REPORT_TITLE_ZH = "持仓映射行业研究分析"
_REPORT_TITLE_EN = "Holdings-Mapped Industry Research Analysis"
_INDUSTRY_NOISE_PARAGRAPH_TERMS = (
    "行业分类噪声",
    "分类噪声",
    "数据源中被归类",
    "检索噪声",
    "标签噪声",
    "搜索关键词泄漏",
    "搜索错配",
    "检索错配",
    "broker tagging noise",
    "search mismatches",
    "retrieval artifacts",
    "classification slippage",
    "metadata quirks",
)
_INDUSTRY_HEADING_MAP = {
    "一、总体研判": "一、行业主线与分歧焦点",
    "（一）共识观点": "（一）共识主线",
    "（二）核心分歧": "（二）分歧焦点",
    "二、深度分析": "二、景气、政策与产业链验证",
    "（一）量化对比": "（一）景气与价格对比",
    "（二）机构态度分布": "（二）机构观点分布",
    "（三）政策影响": "（三）政策传导",
    "（四）产业链影响": "（四）产业链验证",
    "三、风险与催化": "三、未解问题与风险边界",
    "（一）盲点与遗漏问题": "（一）未解问题",
    "（二）风险提示": "（二）风险边界",
    "四、总结": "四、ETF映射与研报总览",
    "（一）ETF暴露映射": "（一）ETF暴露映射",
    "（二）研报总览表": "（二）研报总览表",
}


def _strip_industry_noise_paragraphs(report: str) -> str:
    if not report:
        return ""
    normalized = report.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = normalized.split("\n\n")
    kept: list[str] = []
    for paragraph in paragraphs:
        lower = paragraph.lower()
        if any(term.lower() in lower for term in _INDUSTRY_NOISE_PARAGRAPH_TERMS):
            continue
        kept.append(paragraph)
    return "\n\n".join(kept)


def create_etf_industry_research_analyst(llm):
    def etf_industry_research_node(state):
        current_date = state["trade_date"]
        asset_symbol = get_asset_symbol(state)
        instrument_context = build_instrument_context(asset_symbol)
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
            "- **Blind Spots & Missing Questions (盲点与遗漏问题)**: What important ETF-industry questions did no broker address? This module must focus only on real industry unknowns such as supply, demand, pricing power, policy transmission, inventory, capex, competition, or cost pass-through. Never discuss data-source classification noise, broker tagging noise, search mismatches, retrieval artifacts, or metadata quirks here.\n"
            "- **Quantitative Comparison (量化对比)**: Compare growth forecasts, price assumptions, capacity/inventory signals, and policy-sensitive metrics, then explain what those ranges imply for industry allocation timing, ETF earnings sensitivity, and weighted-holdings return attribution. Do NOT just list numbers.\n"
            "- **Broker Attitude Distribution (机构态度分布)**: Count bullish / cautious / neutral stances by industry theme.\n"
            "- **Policy & Regulatory Impact (政策影响)**: Explain how policy changes transmit into the ETF's industry exposures.\n"
            "- **Supply-Chain Implications (产业链影响)**: Explain upstream/downstream transmission and which holdings benefit or get hurt.\n"
            "- **ETF Exposure Mapping (ETF暴露映射)**: Map each major industry conclusion back to ETF weight concentration, cyclicality, policy sensitivity, and allocation timing.\n"
            "- **Risk Factors (风险提示)**: Rank industry-level risks by frequency and severity, with broker citations.\n\n"
            "## Step 4: Structured Report\n"
            "Write a 2-4 sentence overview paragraph before any section headings "
            "that summarizes the dominant industry exposure, the main broker consensus or divergence, and the ETF allocation implication. "
            "This lead paragraph must appear before any section headings.\n"
            + get_no_title_instruction() + "\n"
            + get_topic_and_term_style_instruction() + "\n"
            + get_concise_heading_instruction() + "\n"
            "Write a comprehensive Markdown report. Keep the visual rhythm compact and aligned with the other analyst reports: "
            "every top-level section (一、二、三、四) should open with a compact 1-2 sentence lead paragraph, then move directly into sub-sections with only standard markdown separation. "
            "Do NOT insert extra spacer lines, repeated heading lines, or loose padding between a section lead and its first sub-section.\n\n"
            "一、行业主线与分歧焦点 (Industry Thesis & Divergence Focus)\n"
            "  （一）共识主线 (Consensus Thesis)\n\n"
            "  （二）分歧焦点 (Divergence Focus)\n\n"
            "二、景气、政策与产业链验证 (Cycle, Policy & Chain Verification)\n"
            "  （一）景气与价格对比 (Cycle & Price Comparison)\n\n"
            "  （二）机构观点分布 (Broker View Distribution)\n\n"
            "  （三）政策传导 (Policy Transmission)\n\n"
            "  （四）产业链验证 (Supply-Chain Verification)\n\n"
            "三、未解问题与风险边界 (Open Questions & Risk Boundaries)\n"
            "  （一）未解问题 (Open Questions)\n\n"
            "  （二）风险边界 (Risk Boundaries)\n\n"
            "四、ETF映射与研报总览 (ETF Mapping & Research Digest)\n"
            "  （一）ETF暴露映射 (ETF Exposure Mapping)\n\n"
            "  （二）研报总览表 (Summary Table)\n\n"
            "## Quality Requirements\n"
            "- EVERY claim must cite the specific broker(s) and supporting evidence or data.\n"
            "- When brokers disagree, present both sides and explain the ROOT CAUSE of disagreement.\n"
            "- Keep the report ETF-first: industry conclusions must be translated into holdings impact and ETF allocation implications.\n"
            "- Do NOT drift into standalone single-stock valuation work. The emphasis is industry cross-analysis and ETF transmission.\n"
            "- Data-source classification noise, broker tagging noise, search-keyword leakage, and retrieval mismatches are NEVER valid report content for this analyst. Exclude them entirely instead of presenting them as blind spots, caveats, or information gaps.\n"
            "- The summary table must list each broker, the industry keyword covered, the stance, the key thesis, and notable data points.\n"
            "- If no industry reports are available, state the information gap clearly and explain what this means for ETF exposure assessment.\n\n"
            "STYLE RULES — strictly follow:\n"
            "- Start the report directly with the single most important industry consensus or divergence finding. "
            "Do NOT begin with meta-descriptions such as '本报告将…', '以下是…', '本分析基于…', 'This report provides…', "
            "or any sentence that describes what the report will do rather than stating a result.\n"
            "- For the title lead and the 2-3 sentence lead under each top-level section, state the conclusion directly. "
            "Do NOT use lead-ins such as '本部分结论表明', '该部分说明', '这一节意味着', 'This section shows', or similar meta phrasing.\n"
            "- Those lead paragraphs must sit one level above the sub-sections: synthesize the broader ETF exposure, style, cycle sensitivity, valuation/risk transmission, and allocation implication. "
            "Do NOT simply restate the same points that will appear immediately below under the sub-sections.\n"
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
        report = strip_meta_lead_prefixes(report) if report else report
        report = _strip_industry_noise_paragraphs(report) if report else report
        report = strip_report_title(report) if report else report
        report = normalize_section_headings(report, _INDUSTRY_HEADING_MAP) if report else report
        report = ensure_title_lead_paragraph(
            report,
            _DEFAULT_TITLE_LEAD_ZH,
            _DEFAULT_TITLE_LEAD_EN,
        ) if report else report
        if report and not getattr(result, "tool_calls", None):
            result = AIMessage(content=report)

        return with_state_aliases(
            {
                "messages": [result],
                "holdings_industry_report": report,
            }
        )

    return etf_industry_research_node
