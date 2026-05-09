import openai
from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_history_turn,
    extract_feedback_snapshot,
    get_analyst_decision_instruction,
    get_analyst_decision_template,
    get_bear_proposal_instruction,
    get_language_instruction,
    get_no_greeting_instruction,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    localize_role_name,
    make_display_snapshot,
    normalize_chinese_role_terms,
    save_snapshot_file,
    strip_analyst_decision_summary,
    strip_feedback_snapshot,
    strip_role_prefix,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, get_state_value


def create_bear_researcher(llm, memory=None):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        bear_history = investment_debate_state.get("bear_history", "")
        bull_history = investment_debate_state.get("bull_history", "")
        round_index = investment_debate_state.get("count", 0)
        current_response = investment_debate_state.get("current_bull_response", "")
        bull_snapshot = investment_debate_state.get("bull_snapshot", "")
        bear_snapshot = investment_debate_state.get("bear_snapshot", "")
        debate_brief = investment_debate_state.get("debate_brief", "")
        market_research_report = get_state_value(state, "market_flow_report", "")
        sentiment_report = get_state_value(state, "catalyst_sentiment_report", "")
        news_report = get_state_value(state, "macro_regime_report", "")
        fundamentals_report = get_state_value(state, "meso_commodity_report", "")
        research_report = get_state_value(state, "market_flow_report", "")
        stock_report = get_state_value(state, "holdings_industry_report", "")
        holdings_report = get_state_value(state, "top_holdings_report", "")

        prompt = f"""You are a Bear Analyst making the case against increasing ETF exposure. Your task is to build an ETF-product-aware bearish case that explains why current macro shocks, benchmark exposure, industry fundamentals, or constituent earnings trends could translate into weaker ETF returns, fragile implementation, or poor timing for adding risk.

Key points to focus on:

- Macro exposure mismatch: Identify the ETF's main macro risk exposures and explain why the dominant macro shock is a headwind rather than a tailwind.
- Factor transmission: Explain the chain from macro factors -> industry supply-demand deterioration / pricing pressure -> weaker profit-growth outlook -> downside risk for ETF benchmark earnings or valuation.
- Product-layer weaknesses: Emphasize concentration risk, benchmark fragility, crowding, unstable share creation-redemption, premium-discount slippage, or execution/liquidity weaknesses.
- Negative confirmation: Use market-and-flow evidence to show the thesis lacks validation, is being distributed, or is vulnerable to false-strength signals.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, especially where the bull side overstates diversification, ignores macro-factor headwinds, or assumes profit growth that is not supported by industry and holdings research.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Do not force your argument into a rigid five-point checklist.
Instead, identify the dimensions that matter most for this ETF right now and expand or contract them accordingly.
At minimum, cover the most decision-relevant mix of:
1. Macro exposure vulnerability to the dominant shock
2. Oversupply, weak demand, inventory stress, or pricing-pressure anomalies
3. Profit-growth, revision, margin, or earnings-quality weakness in the main industries / top holdings
4. Market structure, flows, crowding, and implementation fragility
5. Benchmark, concentration, duration, FX, policy, or wrapper-level risks
6. Any ETF-specific anomaly revealed by the reports that could accelerate downside or invalidate the bullish case

Resources available:

Market research report: {market_research_report}
Sentiment and catalyst impact report: {sentiment_report}
Latest macro regime report: {news_report}
Meso commodity analysis: {fundamentals_report}
Market and flow analysis: {research_report}
ETF holdings-industry research: {stock_report}
ETF top holdings research: {holdings_report}
Rolling debate brief: {debate_brief}
Your PREVIOUS round snapshot (do NOT repeat its content in new snapshot): {bear_snapshot}
Latest bull feedback snapshot: {bull_snapshot}
Your complete debate history: {bear_history}
Bull's complete debate history: {bull_history}
Last bull argument body: {current_response}
When making claims, tie them back to ETF allocation rather than discussing single names in isolation.
When writing in Chinese, use the exact role names "{localize_role_name('Bear Analyst')}" and "{localize_role_name('Bull Analyst')}". Do not use variants like "熊派分析师" or "牛派分析师".
For ordinary lists, use Arabic numerals such as 1. 2. 3.; if you use Chinese section headings, keep forms like 一、二、三.
Your main argument body must be written entirely in Chinese. {get_bear_proposal_instruction()}
{get_analyst_decision_instruction()}
Use this exact decision-summary template:
{get_analyst_decision_template()}
After the decision summary, append an exact feedback snapshot block using this template:
{get_snapshot_template(round_index)}
{get_snapshot_writing_instruction(round_index)}{get_language_instruction()}{get_no_greeting_instruction()}"""

        try:
            response = llm.invoke(prompt)
            raw_content = normalize_chinese_role_terms(
                extract_text_content(response.content)
            )
        except (openai.InternalServerError, openai.APIError, openai.APIConnectionError) as e:
            fallback = (
                f"{localize_role_name('Bear Analyst')}：本轮因服务器错误未能生成论点（{type(e).__name__}），维持上轮立场。"
            )
            raw_content = fallback

        visible_argument_body = strip_role_prefix(
            strip_analyst_decision_summary(strip_feedback_snapshot(raw_content)),
            "Bear Analyst",
        )
        history_turn = build_history_turn(raw_content, "Bear Analyst")
        new_bear_snapshot_full = extract_feedback_snapshot(raw_content)

        ticker = get_asset_symbol(state)
        trade_date = state.get("trade_date", "unknown")
        snapshot_path = save_snapshot_file(new_bear_snapshot_full, "Bear Analyst", ticker, trade_date, round_index + 1)
        new_bear_snapshot = make_display_snapshot(new_bear_snapshot_full, snapshot_path)

        new_debate_brief = build_debate_brief(
            {
                "Bull Analyst": bull_snapshot,
                "Bear Analyst": new_bear_snapshot,
            },
            latest_speaker="Bear Analyst",
        )

        new_investment_debate_state = {
            "history": investment_debate_state.get("history", "") + "\n" + history_turn,
            "bear_history": bear_history + "\n" + history_turn,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": f"{localize_role_name('Bear Analyst')}: {visible_argument_body}",
            "current_bear_response": f"{localize_role_name('Bear Analyst')}: {visible_argument_body}",
            "current_bull_response": investment_debate_state.get("current_bull_response", ""),
            "bull_snapshot": bull_snapshot,
            "bear_snapshot": new_bear_snapshot,
            "bull_snapshot_path": investment_debate_state.get("bull_snapshot_path", ""),
            "bear_snapshot_path": snapshot_path,
            "judge_snapshot": investment_debate_state.get("judge_snapshot", ""),
            "judge_snapshot_path": investment_debate_state.get("judge_snapshot_path", ""),
            "debate_brief": new_debate_brief,
            "latest_speaker": "Bear Analyst",
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
