import openai
from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_history_turn,
    extract_feedback_snapshot,
    get_analyst_decision_instruction,
    get_analyst_decision_template,
    get_aggressive_risk_instruction,
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


def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        aggressive_history = risk_debate_state.get("aggressive_history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")
        round_index = risk_debate_state.get("count", 0)
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")
        aggressive_snapshot = risk_debate_state.get("aggressive_snapshot", "")
        conservative_snapshot = risk_debate_state.get("conservative_snapshot", "")
        neutral_snapshot = risk_debate_state.get("neutral_snapshot", "")
        debate_brief = risk_debate_state.get("debate_brief", "")

        market_research_report = get_state_value(state, "market_flow_report", "")
        sentiment_report = get_state_value(state, "catalyst_sentiment_report", "")
        news_report = get_state_value(state, "macro_regime_report", "")
        fundamentals_report = get_state_value(state, "meso_commodity_report", "")
        research_report = get_state_value(state, "market_flow_report", "")
        stock_report = get_state_value(state, "holdings_industry_report", "")
        holdings_report = get_state_value(state, "top_holdings_report", "")

        trader_decision = get_state_value(state, "trader_allocation_plan", "")

        prompt = f"""As the Aggressive Risk Analyst, your role is to actively champion high-reward ETF allocation opportunities, emphasizing bold positioning, rotation timing, and upside asymmetry. When evaluating the trader's allocation plan, focus intently on the potential upside, benchmark regime tailwinds, and opportunity cost of being underexposed—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative. Here is the trader's allocation plan:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

Market & Flow Report: {market_research_report}
Sentiment & Catalyst Impact Report: {sentiment_report}
Latest Macro Regime Report: {news_report}
Meso Commodity Analysis: {fundamentals_report}
Market and Flow Analysis: {research_report}
ETF Holdings-Industry Research: {stock_report}
ETF Top Holdings Research: {holdings_report}
Rolling risk debate brief: {debate_brief}
Your PREVIOUS round snapshot (do NOT repeat its content in new snapshot): {aggressive_snapshot}
Latest conservative feedback snapshot: {conservative_snapshot}
Latest neutral feedback snapshot: {neutral_snapshot}
Your complete debate history: {aggressive_history}
Conservative's complete debate history: {conservative_history}
Neutral's complete debate history: {neutral_history}
Last conservative argument body: {current_conservative_response}
Last neutral argument body: {current_neutral_response}
If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting.
{get_aggressive_risk_instruction()}
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
            argument_body = strip_role_prefix(
                strip_analyst_decision_summary(strip_feedback_snapshot(raw_content)),
                "Aggressive Analyst",
            )
            history_turn = build_history_turn(raw_content, "Aggressive Analyst")
            new_aggressive_snapshot_full = extract_feedback_snapshot(raw_content)
            ticker = get_asset_symbol(state)
            trade_date = state.get("trade_date", "unknown")
            snapshot_path = save_snapshot_file(new_aggressive_snapshot_full, "Aggressive Analyst", ticker, trade_date, round_index + 1)
            new_aggressive_snapshot = make_display_snapshot(new_aggressive_snapshot_full, snapshot_path)
        except (openai.InternalServerError, openai.APIError, openai.APIConnectionError) as e:
            argument_body = f"本轮因服务器错误未能生成论点（{type(e).__name__}），维持上轮立场。"
            history_turn = f"{localize_role_name('Aggressive Analyst')}: {argument_body}"
            new_aggressive_snapshot = risk_debate_state.get("aggressive_snapshot", "")
            snapshot_path = risk_debate_state.get("aggressive_snapshot_path", "")
        new_debate_brief = build_debate_brief(
            {
                "Aggressive Analyst": new_aggressive_snapshot,
                "Conservative Analyst": conservative_snapshot,
                "Neutral Analyst": neutral_snapshot,
            },
            latest_speaker="Aggressive Analyst",
        )

        new_risk_debate_state = {
            "history": risk_debate_state.get("history", "") + "\n" + history_turn,
            "aggressive_history": aggressive_history + "\n" + history_turn,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": f"{localize_role_name('Aggressive Analyst')}: {argument_body}",
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "aggressive_snapshot": new_aggressive_snapshot,
            "conservative_snapshot": conservative_snapshot,
            "neutral_snapshot": neutral_snapshot,
            "aggressive_snapshot_path": snapshot_path,
            "conservative_snapshot_path": risk_debate_state.get("conservative_snapshot_path", ""),
            "neutral_snapshot_path": risk_debate_state.get("neutral_snapshot_path", ""),
            "debate_brief": new_debate_brief,
            "judge_decision": risk_debate_state.get("judge_decision", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
