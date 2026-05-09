import openai
from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_history_turn,
    extract_feedback_snapshot,
    get_analyst_decision_instruction,
    get_analyst_decision_template,
    get_conservative_risk_instruction,
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


def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        conservative_history = risk_debate_state.get("conservative_history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")
        round_index = risk_debate_state.get("count", 0)
        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
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

        prompt = f"""As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable portfolio growth. You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, liquidity stress, and ETF crowding risk. When evaluating the trader's allocation plan, critically examine high-risk elements, pointing out where the plan may expose the portfolio to undue risk and where more cautious alternatives could secure long-term gains. Here is the trader's allocation plan:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

Market & Flow Report: {market_research_report}
Sentiment & Catalyst Impact Report: {sentiment_report}
Latest Macro Regime Report: {news_report}
Meso Commodity Analysis: {fundamentals_report}
Market and Flow Analysis: {research_report}
ETF Holdings-Industry Research: {stock_report}
ETF Top Holdings Research: {holdings_report}
Rolling risk debate brief: {debate_brief}
Your PREVIOUS round snapshot (do NOT repeat its content in new snapshot): {conservative_snapshot}
Latest aggressive feedback snapshot: {aggressive_snapshot}
Latest neutral feedback snapshot: {neutral_snapshot}
Your complete debate history: {conservative_history}
Aggressive's complete debate history: {aggressive_history}
Neutral's complete debate history: {neutral_history}
Last aggressive argument body: {current_aggressive_response}
Last neutral argument body: {current_neutral_response}
If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting.
{get_conservative_risk_instruction()}
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
                "Conservative Analyst",
            )
            history_turn = build_history_turn(raw_content, "Conservative Analyst")
            new_conservative_snapshot_full = extract_feedback_snapshot(raw_content)
            ticker = get_asset_symbol(state)
            trade_date = state.get("trade_date", "unknown")
            snapshot_path = save_snapshot_file(new_conservative_snapshot_full, "Conservative Analyst", ticker, trade_date, round_index + 1)
            new_conservative_snapshot = make_display_snapshot(new_conservative_snapshot_full, snapshot_path)
        except (openai.InternalServerError, openai.APIError, openai.APIConnectionError) as e:
            argument_body = f"本轮因服务器错误未能生成论点（{type(e).__name__}），维持上轮立场。"
            history_turn = f"{localize_role_name('Conservative Analyst')}: {argument_body}"
            new_conservative_snapshot = risk_debate_state.get("conservative_snapshot", "")
            snapshot_path = risk_debate_state.get("conservative_snapshot_path", "")
        new_debate_brief = build_debate_brief(
            {
                "Aggressive Analyst": aggressive_snapshot,
                "Conservative Analyst": new_conservative_snapshot,
                "Neutral Analyst": neutral_snapshot,
            },
            latest_speaker="Conservative Analyst",
        )

        new_risk_debate_state = {
            "history": risk_debate_state.get("history", "") + "\n" + history_turn,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + history_turn,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": f"{localize_role_name('Conservative Analyst')}: {argument_body}",
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "aggressive_snapshot": aggressive_snapshot,
            "conservative_snapshot": new_conservative_snapshot,
            "neutral_snapshot": neutral_snapshot,
            "aggressive_snapshot_path": risk_debate_state.get("aggressive_snapshot_path", ""),
            "conservative_snapshot_path": snapshot_path,
            "neutral_snapshot_path": risk_debate_state.get("neutral_snapshot_path", ""),
            "debate_brief": new_debate_brief,
            "judge_decision": risk_debate_state.get("judge_decision", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
