from etfagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_instrument_context,
    extract_feedback_snapshot,
    get_language_instruction,
    make_display_snapshot,
    get_localized_research_view_instruction,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    get_output_language,
    load_snapshot_file,
    localize_label,
    localize_rating_term,
    localize_role_name,
    normalize_chinese_manager_terms,
    save_snapshot_file,
    strip_feedback_snapshot,
    synthesize_side_report,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, get_state_value, with_state_aliases
from etfagents.agents.schemas import ResearchPlan, render_research_plan
from etfagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext
from etfagents.agents.utils.analysis_memory import (
    build_memory_prompt_block,
    get_memory_usage_instruction,
)


def _is_chinese_output() -> bool:
    return get_output_language().strip().lower() in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}


def _research_action_logic_instruction() -> str:
    if _is_chinese_output():
        return (
            "- 说明 ETF 的宏观风险暴露、当前主导宏观因子冲击是正向还是反向、行业供需是否平衡、利润增长前景是否改善，以及这些因素如何与市场结构、资金流、催化节奏和下行边界共同导向你的配置决策。"
            " 每个触发条件必须引用上方报告中的具体数据——如价格、均线、成交量、份额变化、溢折价、持仓集中度、宏观指标、利差、实际利率、行业供需与盈利线索等——并给出明确阈值。"
            ' 不能只写\u201c等待确认\u201d\u201c观察变化\u201d\u201c关注资金流\u201d这类泛化表述，必须写明\u201c达到什么数值才算确认\u201d。'
        )
    return (
        "- Explain how the ETF's macro risk exposures, the direction of the dominant macro-factor shock, industry supply-demand balance, profit-growth outlook, market structure, fund flows, catalyst timing, downside boundaries, and confirmation or invalidation signals lead to your allocation decision."
        " Every trigger condition must quote specific data from the reports above — prices, moving averages, volume levels, share changes, premium-discount, holdings concentration, macro indicators, rate spreads, real yields, supply-demand evidence, and profit signals — with explicit numeric thresholds."
        " Do not use vague phrases like 'wait for confirmation', 'watch volume', or 'monitor fund flows' without stating exactly what numeric level constitutes confirmation."
    )


def _research_detail_instruction(section: str) -> str:
    if _is_chinese_output():
        if section == "conclusion":
            return (
                "- 这一部分必须写成连贯分析段落，至少 4 句，不能只写简短观点或要点摘录。"
                " 必须引用报告中的具体数据来支撑判断——包括价格水平、均线位置、成交量、份额变化、溢折价、持仓集中度、宏观指标、利差、实际利率、供需与盈利线索等。"
            )
        if section == "positioning":
            return (
                "- 这一部分必须写成详细执行段落，至少 4 句，不能只给一句“维持持有/增持”。"
                " 必须明确写出初始仓位带、最多先建多少仓、何时加仓/减仓/轮动、什么条件触发再平衡，以及下一步重点监控哪些验证指标。"
                " 不要重复“行为逻辑”里的原句，而要把研究结论翻译成可执行的仓位动作。"
            )
        return (
            "- 这一部分必须写成详细推理段落，至少 4 句，要把 ETF 的宏观风险暴露、宏观因子冲击方向、行业供需、利润增长前景、市场结构、资金流、催化节奏、价格信号和风险触发条件串成完整逻辑链。"
            " 每个论据都必须引用上方报告中的具体数据，不能只写泛化判断。对于配置建议，必须给出以下具体标准：\n"
            "  (a) 关键支撑和阻力位的具体价格或均线位置（引用市场报告中的技术指标，并给出具体数值）；\n"
            "  (b) 成交量或资金流改善的具体阈值（如“成交量需达到近20日均量的1.3倍以上”）；\n"
            "  (c) ETF 产品层验证的具体指标（如份额变化幅度、溢折价偏离、跟踪误差、前十大持仓集中度百分比）；\n"
            "  (d) 宏观与行业验证的具体条件（如利率决议时间、利差阈值、实际利率方向、供需拐点、盈利修正、指数成分调整窗口、资金流向阈值等）。"
        )
    if section == "conclusion":
        return (
            "- Write this section as a coherent analysis paragraph with at least 4 full sentences; do not output terse fragments or simple bullet-style restatements."
            " You must cite specific data from the reports to support every judgment — prices, moving averages, volume, share changes, premium-discount, holdings concentration, macro indicators, rate spreads, real yields, supply-demand, and profit signals."
        )
    if section == "positioning":
        return (
            "- Write this section as a detailed execution paragraph with at least 4 full sentences; do not stop at a one-line 'hold/overweight' statement."
            " You must spell out the initial allocation band, maximum starter size, add / reduce / rotate conditions, rebalance triggers, and the next monitoring priorities."
            " Do not repeat the action-logic sentences verbatim; translate the research conclusion into concrete position-management instructions."
        )
    return (
        "- Write this section as a detailed reasoning paragraph with at least 4 full sentences, explicitly connecting the ETF's macro risk exposures, macro-factor shock direction, industry supply-demand balance, profit-growth outlook, market structure, flows, catalysts, price action, and risk triggers to the recommendation."
        " Every argument must quote specific data from the reports above — do not rely on generic judgments. For allocation recommendations, you MUST provide these specific criteria:\n"
        "  (a) Specific price levels or moving-average positions for key support/resistance (reference the market report — with exact numbers);\n"
        "  (b) Specific volume or fund-flow improvement thresholds (e.g., 'volume must reach 1.3x the 20-day average of N shares');\n"
        "  (c) Specific ETF product checks (e.g., share change magnitude, premium-discount deviation, tracking error, top-10 holdings concentration percentage);\n"
        "  (d) Specific macro and industry confirmation conditions (e.g., rate decision dates, spread thresholds, real-yield direction, supply-demand turning points, earnings revisions, index rebalancing windows, fund-flow thresholds)."
    )


def create_research_manager(llm, memory=None):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(get_asset_symbol(state))
        market_flow_report = get_state_value(state, "market_flow_report", "")
        catalyst_sentiment_report = get_state_value(state, "catalyst_sentiment_report", "")
        macro_regime_report = get_state_value(state, "macro_regime_report", "")
        meso_commodity_report = get_state_value(state, "meso_commodity_report", "")
        holdings_industry_report = get_state_value(state, "holdings_industry_report", "")
        top_holdings_report = get_state_value(state, "top_holdings_report", "")

        investment_debate_state = state["investment_debate_state"]
        bull_snapshot_display = investment_debate_state.get("bull_snapshot", "")
        bear_snapshot_display = investment_debate_state.get("bear_snapshot", "")
        debate_brief = investment_debate_state.get("debate_brief", "")

        # Load full snapshots from files
        bull_snapshot_full = load_snapshot_file(investment_debate_state.get("bull_snapshot_path", "")) or bull_snapshot_display
        bear_snapshot_full = load_snapshot_file(investment_debate_state.get("bear_snapshot_path", "")) or bear_snapshot_display

        # Synthesize each side's full debate history into a comprehensive position report
        bull_history = investment_debate_state.get("bull_history", "")
        bear_history = investment_debate_state.get("bear_history", "")
        bull_report = synthesize_side_report(llm, "Bull Analyst", bull_history, bull_snapshot_full)
        bear_report = synthesize_side_report(llm, "Bear Analyst", bear_history, bear_snapshot_full)
        memory_block = build_memory_prompt_block(state, role="research_manager")
        memory_section = f"{memory_block}\n\n{get_memory_usage_instruction()}\n\n" if memory_block else ""

        prompt = f"""As the ETF research manager and debate facilitator, your role is to critically evaluate the full multi-round debate and make a definitive allocation decision: align with the {localize_role_name("Bear Analyst")}, the {localize_role_name("Bull Analyst")}, or choose {localize_rating_term("Hold")} only if it is strongly justified based on the arguments presented.

Your response must evaluate both sides before giving a position. Do not jump straight to the allocation suggestion.
For ordinary lists, use Arabic numerals such as 1. 2. 3.; if you use Chinese section headings, keep forms like 一、二、三.
Output only the finished report. Never copy, quote, or paraphrase the writing rules or bullet instructions from this prompt into the answer, and do not repeat a section heading once it has already appeared.

Use this exact output order with Markdown headings:
## {localize_label("Debate Conclusion", "辩论结论")}
- Assess which side presented the stronger case across the full debate, not just the latest exchange.
- Summarize the strongest points from both the {localize_role_name("Bull Analyst")} and the {localize_role_name("Bear Analyst")}.
- Explicitly point out the decisive weakness in the losing side's case.
- You must explicitly judge whether the ETF's macro risk exposures are aligned with or vulnerable to the current dominant macro-factor shock, whether industry supply-demand is improving or deteriorating, and whether the profit-growth outlook across the ETF's main industries / holdings supports the winning side.
- Open with a direct verdict sentence that states your chosen side and the current research view for this ETF before expanding into evidence.
- If a report shows an anomaly (spread break, real-rate divergence, inventory surprise, abnormal flows, earnings miss / beat concentration), explain why it is abnormal relative to the recent baseline and why it changes or fails to change the allocation case.
{_research_detail_instruction("conclusion")}
- When writing in Chinese, use neutral investment wording such as "综合结论" and refer to the entire debate as "整场辩论"; avoid judicial wording like "判决" and avoid phrasing that sounds limited to "本轮".

## {localize_label("Action Logic", "行为逻辑")}
- Write your own ETF allocation logic from evidence to action, not just a repetition of either side.
- Explain the transmission path from macro shock -> industry balance -> earnings / profit-growth outlook -> ETF benchmark and holdings impact -> implementation and timing.
- The first sentence must state what the ETF holder should do now and why now, not after a list of scenarios.
- Do not write generic scenario catalogs. Use the current base case as the main thread, then explain what specific evidence would invalidate it.
{_research_action_logic_instruction()}
- This section must make clear what would cause you to maintain, add, reduce, rotate, or reverse ETF exposure.
{_research_detail_instruction("action")}

## {localize_label("Positioning Recommendation", "持仓建议")}
        - When writing in Chinese, split this section into exactly two second-level subsections: `（一）评级` and `（二）建议`.
        - Do NOT create extra top-level headings such as `四、评级` or `五、建议`; both must stay under `持仓建议`.
        - Put the single explicit recommendation label only in `（一）评级`.
        - Put all execution detail, allocation band, add / reduce / rotate conditions, rebalance triggers, risk controls, and monitoring priorities in `（二）建议`.
        - Give a clear, actionable ETF allocation recommendation—{localize_rating_term("Buy")}, {localize_rating_term("Overweight")}, {localize_rating_term("Hold")}, {localize_rating_term("Underweight")}, or {localize_rating_term("Sell")}—grounded in the debate's strongest arguments.
        - Include concrete execution guidance for the trader: initial allocation band, add / reduce / rotate conditions, rebalance triggers, risk controls, and what to monitor next.
        - The rating field and the positioning recommendation text must point to the same action. Do not restate a different recommendation in prose.
        - Keep exactly one explicit recommendation label in this section. {get_localized_research_view_instruction()}
        {_research_detail_instruction("positioning")}

Only after the three sections above, append a feedback block in this exact format. Do not place the feedback snapshot before the conclusion:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}

{get_language_instruction()}
{instrument_context}

{memory_section}

{localize_label("Rolling debate brief:", "滚动辩论摘要:")}
{debate_brief}

{localize_label("Bull Analyst comprehensive position report (synthesized from all rounds):", f"{localize_role_name('Bull Analyst')} 综合立场报告（基于全轮次辩论）:")}
{bull_report}

{localize_label("Bear Analyst comprehensive position report (synthesized from all rounds):", f"{localize_role_name('Bear Analyst')} 综合立场报告（基于全轮次辩论）:")}
{bear_report}

        {localize_label("Macro regime analysis:", "宏观框架分析:")}
        {macro_regime_report}

        {localize_label("Meso commodity analysis:", "中观大宗商品分析:")}
        {meso_commodity_report}

        {localize_label("Sentiment and catalyst impact analysis:", "舆情与事件影响分析:")}
        {catalyst_sentiment_report}

        {localize_label("Market and flow analysis:", "市场与资金流分析:")}
        {market_flow_report}

        {localize_label("ETF holdings-industry research:", "ETF持仓行业研究:")}
        {holdings_industry_report}

        {localize_label("ETF top holdings research:", "ETF头部持仓研究:")}
        {top_holdings_report}
        """
        normalized_content = normalize_chinese_manager_terms(
            invoke_structured_or_freetext(
                structured_llm,
                llm,
                prompt,
                render_research_plan,
                "Research Manager",
            )
        )
        judge_snapshot_full = extract_feedback_snapshot(normalized_content)
        debate_round = max(1, investment_debate_state.get("count", 0) // 2)
        judge_snapshot_path = save_snapshot_file(
            judge_snapshot_full,
            "Research Manager",
            get_asset_symbol(state),
            state.get("trade_date", "unknown"),
            debate_round,
        )
        judge_snapshot = make_display_snapshot(
            judge_snapshot_full, judge_snapshot_path
        )
        updated_brief = build_debate_brief(
            {
                "Bull Analyst": bull_snapshot_display,
                "Bear Analyst": bear_snapshot_display,
                "Research Manager": judge_snapshot,
            },
            latest_speaker="Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": normalized_content,
            "judge_snapshot": judge_snapshot,
            "judge_snapshot_path": judge_snapshot_path,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": strip_feedback_snapshot(normalized_content),
            "current_bull_response": investment_debate_state.get("current_bull_response", ""),
            "current_bear_response": investment_debate_state.get("current_bear_response", ""),
            "bull_snapshot": bull_snapshot_display,
            "bear_snapshot": bear_snapshot_display,
            "bull_snapshot_path": investment_debate_state.get("bull_snapshot_path", ""),
            "bear_snapshot_path": investment_debate_state.get("bear_snapshot_path", ""),
            "debate_brief": updated_brief,
            "latest_speaker": "Research Manager",
            "count": investment_debate_state["count"],
        }

        return with_state_aliases({
            "investment_debate_state": new_investment_debate_state,
            "research_allocation_plan": normalized_content,
        })

    return research_manager_node
