import functools

from etfagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_instrument_context,
    extract_feedback_snapshot,
    get_language_instruction,
    get_localized_final_proposal_instruction,
    get_localized_rating_scale,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    get_output_language,
    load_snapshot_file,
    localize_label,
    localize_rating_term,
    localize_role_name,
    make_display_snapshot,
    normalize_chinese_manager_terms,
    save_snapshot_file,
    synthesize_side_report,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, get_state_value, with_state_aliases
from etfagents.agents.schemas import PortfolioDecision, render_portfolio_decision
from etfagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_with_result,
)
from etfagents.backtest.signals import build_portfolio_backtest_signal


def _is_chinese_output() -> bool:
    return get_output_language().strip().lower() in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}


def _portfolio_action_logic_instruction() -> str:
    if _is_chinese_output():
        return (
            "- 说明 ETF 结构、资金流、催化节奏、下行边界、仓位大小以及加仓 / 减仓 / 轮动 / 对冲触发条件如何共同导向你的决策。"
            " 每个触发条件必须引用上方报告中的具体数据——如价格、均线、成交量、份额变化、溢折价、持仓集中度、宏观指标等——并给出明确阈值。"
            ' 不能只写\u201c等待确认\u201d\u201c观察成交量\u201d\u201c关注资金流\u201d这类泛化表述，必须写明\u201c达到什么数值才算确认\u201d。'
            ' 不要写“市场报告中的关键位”或“前文提到的50日均线”这种回指句式，必须把具体数值直接重写在当前句子里。'
            ' 若没有上方报告中的具体价位、均线数值、量能基数或份额/溢折价数据，就不要直接给出加减仓动作。'
        )
    return (
        "- Explain how ETF structure, fund flows, catalyst timing, downside boundaries, position sizing, and add / reduce / rotate / hedge triggers lead to your decision."
        " Every trigger condition must quote specific data from the reports above — prices, moving averages, volume levels, share changes, premium-discount, holdings concentration, macro indicators — with explicit numeric thresholds."
        " Do not use vague phrases like 'wait for confirmation', 'watch volume', or 'monitor fund flows' without stating exactly what numeric level constitutes confirmation."
        " If you cannot cite concrete price levels, moving-average values, volume baselines, or ETF share / premium-discount data from the reports above, do not issue add or reduce instructions."
    )


def _portfolio_detail_instruction(section: str) -> str:
    if _is_chinese_output():
        if section == "conclusion":
            return (
                "- 这一部分必须写成连贯分析段落，至少 4 句，不能只写简短观点或要点摘录。"
                " 必须引用报告中的具体数据来支撑判断——包括价格水平、均线位置、成交量、份额变化、溢折价、持仓集中度、宏观指标等。"
            )
        return (
            "- 这一部分必须写成详细推理段落，至少 4 句，要把 ETF 结构、资金流、催化节奏、仓位大小以及对冲 / 减仓 / 轮动触发条件串成完整逻辑链。"
            " 每个论据都必须引用上方报告中的具体数据，不能只写泛化判断。对于执行计划和风险控制，必须给出以下具体标准：\n"
            "  (a) 关键支撑和阻力位的具体价格或均线位置（引用市场报告中的技术指标，如50日均线、布林中轨、前低或密集成交区，并给出具体数值）；\n"
            '  (b) 成交量或资金流改善的具体阈值（相对近5日或20日均量达到什么倍数，如\u201c成交量需达到近20日均量的1.3倍以上\u201d）；\n'
            "  (c) ETF 结构验证的具体指标（如份额变化幅度、溢折价偏离、跟踪误差、前十大持仓集中度百分比）；\n"
            '  (d) 宏观、风格或政策催化确认的具体条件（如利率决议时间、指数成分调整窗口、资金流向阈值）。\n'
            ' 不要写“参考市场报告中的50日均线”这种表述，而要直接写成“50日均线 2.08 元、布林中轨 2.05 元”这类可执行句子。\n'
            ' 若缺少这些具体数值，就不要把“回踩确认后加仓”“等待放量后减仓”写成最终执行结论。'
        )
    if section == "conclusion":
        return (
            "- Write this section as a coherent analysis paragraph with at least 4 full sentences; do not output terse fragments or simple bullet-style restatements."
            " You must cite specific data from the reports to support every judgment — prices, moving averages, volume, share changes, premium-discount, holdings concentration, macro indicators, etc."
        )
    return (
        "- Write this section as a detailed reasoning paragraph with at least 4 full sentences, explicitly connecting ETF structure, flows, catalyst timing, position sizing, and hedge / reduce / rotate triggers to the recommendation."
        " Every argument must quote specific data from the reports above — do not rely on generic judgments. For execution plan and risk controls, you MUST provide these specific criteria:\n"
        "  (a) Specific price levels or moving-average positions for key support/resistance (reference the market report — e.g., 50-day SMA at X, Bollinger mid-band at Y, prior swing low at Z — with exact numbers);\n"
        "  (b) Specific volume or fund-flow improvement thresholds (e.g., 'volume must reach 1.3x the 20-day average of N shares');\n"
        "  (c) Specific ETF structure checks (e.g., share change magnitude, premium-discount deviation, tracking error, top-10 holdings concentration percentage);\n"
        "  (d) Specific macro, style, or policy catalyst confirmation conditions (e.g., rate decision dates, index rebalancing windows, fund-flow thresholds).\n"
        " If those concrete numbers are missing, do not turn 'wait for confirmation' into a final execution instruction."
    )


def create_portfolio_manager(llm, memory=None):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:

        instrument_context = build_instrument_context(get_asset_symbol(state))
        risk_debate_state = state["risk_debate_state"]
        market_flow_report = get_state_value(state, "market_flow_report", "")
        macro_regime_report = get_state_value(state, "macro_regime_report", "")
        meso_commodity_report = get_state_value(state, "meso_commodity_report", "")
        catalyst_sentiment_report = get_state_value(state, "catalyst_sentiment_report", "")
        holdings_industry_report = get_state_value(state, "holdings_industry_report", "")
        top_holdings_report = get_state_value(state, "top_holdings_report", "")
        research_plan = get_state_value(state, "research_allocation_plan", "")
        trader_plan = get_state_value(state, "trader_allocation_plan", "")
        aggressive_snapshot_display = risk_debate_state.get("aggressive_snapshot", "")
        conservative_snapshot_display = risk_debate_state.get("conservative_snapshot", "")
        neutral_snapshot_display = risk_debate_state.get("neutral_snapshot", "")
        debate_brief = risk_debate_state.get("debate_brief", "")

        # Load full snapshots from files
        aggressive_snapshot_full = load_snapshot_file(risk_debate_state.get("aggressive_snapshot_path", "")) or aggressive_snapshot_display
        conservative_snapshot_full = load_snapshot_file(risk_debate_state.get("conservative_snapshot_path", "")) or conservative_snapshot_display
        neutral_snapshot_full = load_snapshot_file(risk_debate_state.get("neutral_snapshot_path", "")) or neutral_snapshot_display

        # Synthesize each analyst's full debate history into a comprehensive position report
        aggressive_report = synthesize_side_report(llm, "Aggressive Analyst", risk_debate_state.get("aggressive_history", ""), aggressive_snapshot_full)
        conservative_report = synthesize_side_report(llm, "Conservative Analyst", risk_debate_state.get("conservative_history", ""), conservative_snapshot_full)
        neutral_report = synthesize_side_report(llm, "Neutral Analyst", risk_debate_state.get("neutral_history", ""), neutral_snapshot_full)
        past_context = state.get("past_context", "").strip()
        lessons_block = ""
        if past_context:
            lessons_header = (
                "历史决策复盘（仅供内部吸收，不要照抄到可见答案中）"
                if _is_chinese_output()
                else "Lessons from resolved past decisions (internal only; do not quote verbatim)"
            )
            lessons_block = f"**{lessons_header}:**\n{past_context}\n\n"

        prompt = f"""As the Portfolio Manager, synthesize the full risk debate and deliver the final ETF portfolio allocation decision.

Your response must evaluate all three risk perspectives before giving a position. Do not jump straight to the final recommendation.
For ordinary lists, use Arabic numerals such as 1. 2. 3.; if you use Chinese section headings, keep forms like 一、二、三.
Output only the finished report. Never copy, quote, or paraphrase the writing rules or bullet instructions from this prompt into the answer, and do not repeat a section heading once it has already appeared.
Populate the structured fields target_weight_pct, target_weight_band, and execution_timing whenever the evidence supports them; use null only when the reports truly do not justify a reliable value.

Use this exact output order with Markdown headings:
## {localize_label("Debate Conclusion", "辩论结论")}
- Assess which risk perspective presented the strongest case across the full debate.
- Summarize the strongest points from the {localize_role_name("Aggressive Analyst")}, {localize_role_name("Conservative Analyst")}, and {localize_role_name("Neutral Analyst")}.
- Explain the decisive weakness in the view you did not ultimately follow, or clarify why multiple views were overruled.
- Start with a direct verdict sentence stating the final action for this ETF and the dominant reason it wins.
- If the reports show anomalies, explain why they are anomalies versus the recent baseline and why they justify or fail to justify a different allocation.
{_portfolio_detail_instruction("conclusion")}

## {localize_label("Action Logic", "行为逻辑")}
- Write your own ETF portfolio decision logic from evidence to execution, not just a paraphrase of one analyst.
- The first sentence must state the current action now, the sizing stance now, and the core reason now. Do not open with generic prerequisites or abstract caveats.
- Build one clear base-case chain from macro / industry / holdings evidence to ETF implementation; only after that should you mention invalidation triggers.
{_portfolio_action_logic_instruction()}
- Make clear what would cause you to maintain, add, reduce, rotate, hedge, or reverse ETF exposure.
{_portfolio_detail_instruction("action")}

## {localize_label("Positioning Recommendation", "持仓建议")}
 - When writing in Chinese, split this section into exactly two second-level subsections: `（一）评级` and `（二）建议`.
 - Do NOT create extra top-level headings such as `四、评级` or `五、建议`; both must stay under `持仓建议`.
 - Put the single explicit rating label only in `（一）评级`, using `研究结论: **买入/增持/持有/减持/卖出**`.
 - Put all allocation band, add / reduce / rotate / hedge conditions, maximum initial sizing, rebalance triggers, risk controls, and monitoring priorities in `（二）建议`.
 - Give a clear, actionable ETF portfolio recommendation—{localize_rating_term("Buy")}, {localize_rating_term("Overweight")}, {localize_rating_term("Hold")}, {localize_rating_term("Underweight")}, or {localize_rating_term("Sell")}—grounded in the debate's strongest evidence.
 - Include concrete execution guidance: target allocation band, add / reduce / rotate conditions, maximum initial sizing, rebalance triggers, risk controls, and what to monitor next.
 - When writing in Chinese, avoid mixed English labels such as "Time Horizon", "Executive Summary", or "Investment Thesis".
 - The rating, the positioning recommendation text, and the final transaction proposal must all point to the same action. Do not restate a conflicting recommendation in prose.
- Keep exactly one explicit final recommendation label in this section and make the rest of the paragraph explanatory rather than repetitive.

{instrument_context}

---

{get_localized_rating_scale()}

**Context:**
- Research Manager's allocation plan: **{research_plan}**
- Trader's allocation proposal: **{trader_plan}**
{lessons_block.strip()}

**{localize_label("Rolling Risk Debate Brief", "滚动风险辩论摘要")}:**
{debate_brief}

**{localize_label("Aggressive Analyst comprehensive position report (synthesized from all rounds)", f"{localize_role_name('Aggressive Analyst')} 综合立场报告（基于全轮次辩论）")}:**
{aggressive_report}

**{localize_label("Conservative Analyst comprehensive position report (synthesized from all rounds)", f"{localize_role_name('Conservative Analyst')} 综合立场报告（基于全轮次辩论）")}:**
{conservative_report}

**{localize_label("Neutral Analyst comprehensive position report (synthesized from all rounds)", f"{localize_role_name('Neutral Analyst')} 综合立场报告（基于全轮次辩论）")}:**
{neutral_report}

        {localize_label("Market and flow analysis:", "市场与资金流分析:")}
        {market_flow_report}

        {localize_label("ETF holdings-industry research:", "ETF持仓行业研究:")}
        {holdings_industry_report}

        {localize_label("ETF top holdings research:", "ETF头部持仓研究:")}
        {top_holdings_report}

Be decisive and ground every conclusion in specific evidence from the analysts. {get_localized_final_proposal_instruction()}
Only after the three sections above, append a feedback block in this exact format:
{get_snapshot_template()}
{get_snapshot_writing_instruction()}{get_language_instruction()}"""

        rendered_content, structured_result = invoke_structured_or_freetext_with_result(
            structured_llm,
            llm,
            prompt,
            functools.partial(
                render_portfolio_decision,
                context_text="\n".join(
                    part
                    for part in (
                        market_flow_report,
                        research_plan,
                        trader_plan,
                    )
                    if part
                ),
            ),
            "Portfolio Manager",
        )
        normalized_content = normalize_chinese_manager_terms(rendered_content)
        portfolio_backtest_signal = build_portfolio_backtest_signal(
            get_asset_symbol(state),
            str(state.get("trade_date", "")),
            normalized_content,
            structured_result,
        )
        judge_snapshot_full = extract_feedback_snapshot(normalized_content)
        debate_round = max(1, (risk_debate_state.get("count", 0) + 2) // 3)
        judge_snapshot_path = save_snapshot_file(
            judge_snapshot_full,
            "Portfolio Manager",
            get_asset_symbol(state),
            state.get("trade_date", "unknown"),
            debate_round,
        )
        judge_snapshot = make_display_snapshot(judge_snapshot_full, judge_snapshot_path)
        updated_brief = build_debate_brief(
            {
                "Aggressive Analyst": aggressive_snapshot_display,
                "Conservative Analyst": conservative_snapshot_display,
                "Neutral Analyst": neutral_snapshot_display,
                "Portfolio Manager": judge_snapshot,
            },
            latest_speaker="Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": normalized_content,
            "history": risk_debate_state.get("history", ""),
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "debate_brief": updated_brief,
            "latest_speaker": "Portfolio Manager",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "aggressive_snapshot": aggressive_snapshot_display,
            "conservative_snapshot": conservative_snapshot_display,
            "neutral_snapshot": neutral_snapshot_display,
            "aggressive_snapshot_path": risk_debate_state.get("aggressive_snapshot_path", ""),
            "conservative_snapshot_path": risk_debate_state.get("conservative_snapshot_path", ""),
            "neutral_snapshot_path": risk_debate_state.get("neutral_snapshot_path", ""),
            "judge_snapshot": judge_snapshot,
            "judge_snapshot_path": judge_snapshot_path,
            "count": risk_debate_state["count"],
        }

        return with_state_aliases({
            "risk_debate_state": new_risk_debate_state,
            "final_allocation_decision": normalized_content,
            "portfolio_backtest_signal": portfolio_backtest_signal,
            "backtest_signal": portfolio_backtest_signal,
        })

    return portfolio_manager_node
