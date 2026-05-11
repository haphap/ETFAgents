import openai
from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    CHINESE_OUTPUT_VALUES,
    build_debate_brief,
    build_history_turn,
    extract_analyst_decision_summary,
    extract_feedback_snapshot,
    get_analyst_decision_instruction,
    get_analyst_decision_template,
    get_bull_proposal_instruction,
    get_language_instruction,
    get_no_greeting_instruction,
    get_output_language,
    get_snapshot_template,
    get_snapshot_writing_instruction,
    localize_role_name,
    make_display_snapshot,
    normalize_chinese_role_terms,
    normalize_visible_debate_body,
    rebuild_visible_debate_turn,
    save_snapshot_file,
    strip_analyst_decision_summary,
    strip_feedback_snapshot,
    strip_role_prefix,
)
from etfagents.agents.utils.state_keys import get_asset_symbol, get_state_value


def create_bull_researcher(llm, memory=None):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        bull_history = investment_debate_state.get("bull_history", "")
        bear_history = investment_debate_state.get("bear_history", "")
        round_index = investment_debate_state.get("count", 0)
        current_response = investment_debate_state.get("current_bear_response", "")
        bull_snapshot = investment_debate_state.get("bull_snapshot", "")
        bear_snapshot = investment_debate_state.get("bear_snapshot", "")
        debate_brief = investment_debate_state.get("debate_brief", "")
        market_research_report = get_state_value(state, "market_flow_report", "")
        sentiment_report = get_state_value(state, "catalyst_sentiment_report", "")
        news_report = get_state_value(state, "macro_regime_report", "")
        fundamentals_report = get_state_value(state, "meso_commodity_report", "")
        stock_report = get_state_value(state, "holdings_industry_report", "")
        holdings_report = get_state_value(state, "top_holdings_report", "")

        prompt = f"""You are a Bull Analyst advocating for increasing ETF exposure. Your task is to build an ETF-product-aware bullish case that explains why the current macro regime, benchmark exposure, industry fundamentals, and constituent earnings path should translate into better ETF returns, cleaner implementation, and favorable allocation timing.

Key points to focus on:
 - Macro exposure fit: Identify the ETF's main macro risk exposures (rates, liquidity, inflation, growth, FX / USD, commodity beta, policy sensitivity) and explain why the dominant shock is a tailwind or at least not a decisive headwind.
 - Factor transmission: Explain the chain from macro factors -> industry supply-demand / pricing -> profit-growth outlook -> ETF benchmark earnings or valuation support.
 - ETF product suitability: Emphasize wrapper-level advantages such as benchmark purity, holdings breadth versus concentration, share creation-redemption health, premium-discount behavior, and execution liquidity.
 - Confirmation quality: Use market-and-flow evidence to show the bullish thesis is being confirmed rather than remaining a story with no capital support.
 - Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, especially where the bear side overstates macro headwinds, ignores improving industry balance, or misses the ETF's portfolio diversification benefit.
 - Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Do not force your argument into a rigid five-point checklist.
Instead, identify the dimensions that matter most for this ETF right now and expand or contract them accordingly.
At minimum, cover the most decision-relevant mix of:
1. Macro exposure fit or resilience to the dominant shock
2. Industry supply-demand, inventory, capex, or pricing anomalies
3. Profit-growth, revision, or earnings-quality evidence in the main industries / top holdings
4. Market structure, flows, and implementation confirmation
5. Benchmark, concentration, duration, FX, policy, or wrapper-level risks
6. Any ETF-specific anomaly revealed by the reports that could accelerate upside or invalidate the bull case

Resources available:
Market research report: {market_research_report}
Sentiment and catalyst impact report: {sentiment_report}
Latest macro regime report: {news_report}
Meso commodity analysis: {fundamentals_report}
ETF holdings-industry research: {stock_report}
ETF top holdings research: {holdings_report}
Rolling debate brief: {debate_brief}
Your PREVIOUS round snapshot (do NOT repeat its content in new snapshot): {bull_snapshot}
Latest bear feedback snapshot: {bear_snapshot}
Your complete debate history: {bull_history}
Bear's complete debate history: {bear_history}
Last bear argument body: {current_response}
When making claims, tie them back to ETF allocation rather than discussing single names in isolation.
When writing in Chinese, use the exact role names "{localize_role_name('Bull Analyst')}" and "{localize_role_name('Bear Analyst')}". Do not use variants like "牛派分析师" or "熊派分析师".
For ordinary lists, use Arabic numerals such as 1. 2. 3.; if you use Chinese section headings, keep forms like 一、二、三.
{"Your main argument body must be written entirely in Chinese." if get_output_language().strip().lower() in CHINESE_OUTPUT_VALUES else f"Write your main argument body in {get_output_language()}."} {get_bull_proposal_instruction()}
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
                f"{localize_role_name('Bull Analyst')}：本轮因服务器错误未能生成论点（{type(e).__name__}），维持上轮立场。"
                if hasattr(e, '__class__') else str(e)
            )
            raw_content = fallback

        decision_summary = extract_analyst_decision_summary(raw_content)
        visible_argument_body = normalize_visible_debate_body(
            strip_role_prefix(
                strip_analyst_decision_summary(strip_feedback_snapshot(raw_content)),
                "Bull Analyst",
            )
        )
        new_bull_snapshot_full = extract_feedback_snapshot(raw_content)
        history_turn = build_history_turn(
            rebuild_visible_debate_turn(
                visible_argument_body, decision_summary, new_bull_snapshot_full
            ),
            "Bull Analyst",
        )

        ticker = get_asset_symbol(state)
        trade_date = state.get("trade_date", "unknown")
        snapshot_path = save_snapshot_file(new_bull_snapshot_full, "Bull Analyst", ticker, trade_date, round_index + 1)
        new_bull_snapshot = make_display_snapshot(new_bull_snapshot_full, snapshot_path)

        new_debate_brief = build_debate_brief(
            {
                "Bull Analyst": new_bull_snapshot,
                "Bear Analyst": bear_snapshot,
            },
            latest_speaker="Bull Analyst",
        )

        new_investment_debate_state = {
            "history": investment_debate_state.get("history", "") + "\n" + history_turn,
            "bull_history": bull_history + "\n" + history_turn,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": f"{localize_role_name('Bull Analyst')}: {visible_argument_body}",
            "current_bull_response": f"{localize_role_name('Bull Analyst')}: {visible_argument_body}",
            "current_bear_response": investment_debate_state.get("current_bear_response", ""),
            "bull_snapshot": new_bull_snapshot,
            "bear_snapshot": bear_snapshot,
            "bull_snapshot_path": snapshot_path,
            "bear_snapshot_path": investment_debate_state.get("bear_snapshot_path", ""),
            "judge_snapshot": investment_debate_state.get("judge_snapshot", ""),
            "judge_snapshot_path": investment_debate_state.get("judge_snapshot_path", ""),
            "debate_brief": new_debate_brief,
            "latest_speaker": "Bull Analyst",
            "judge_decision": investment_debate_state.get("judge_decision", ""),
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
