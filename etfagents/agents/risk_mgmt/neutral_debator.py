import re

import openai
from etfagents.content_utils import extract_text_content
from etfagents.agents.utils.agent_utils import (
    build_debate_brief,
    build_history_turn,
    extract_analyst_decision_summary,
    extract_feedback_snapshot,
    get_analyst_decision_instruction,
    get_analyst_decision_template,
    get_language_instruction,
    get_no_greeting_instruction,
    get_neutral_risk_instruction,
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


def _paragraphize_neutral_body(text: str) -> str:
    content = (text or "").strip()
    if not content or "\n\n" in content:
        return content

    if re.search(r"[。！？]", content):
        sentences = [segment.strip() for segment in re.split(r"(?<=[。！？!?])\s*", content) if segment.strip()]
        joiner = ""
    else:
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", content) if segment.strip()]
        joiner = " "

    if len(sentences) < 4:
        return content

    paragraphs = []
    for index in range(0, len(sentences), 2):
        paragraph = joiner.join(sentences[index:index + 2]).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs).strip() or content


def _rebuild_neutral_visible_turn(body: str, decision_summary: str, snapshot: str) -> str:
    parts = [segment.strip() for segment in (body, decision_summary, snapshot) if segment and segment.strip()]
    return "\n\n".join(parts).strip()


def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        neutral_history = risk_debate_state.get("neutral_history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")
        round_index = risk_debate_state.get("count", 0)
        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
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

        prompt = f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's allocation plan. You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, macro shifts, correlation, and diversification strategy. Here is the trader's allocation plan:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market & Flow Report: {market_research_report}
Sentiment & Catalyst Impact Report: {sentiment_report}
Latest Macro Regime Report: {news_report}
Meso Commodity Analysis: {fundamentals_report}
Market and Flow Analysis: {research_report}
ETF Holdings-Industry Research: {stock_report}
ETF Top Holdings Research: {holdings_report}
Rolling risk debate brief: {debate_brief}
Your PREVIOUS round snapshot (do NOT repeat its content in new snapshot): {neutral_snapshot}
Latest aggressive feedback snapshot: {aggressive_snapshot}
Latest conservative feedback snapshot: {conservative_snapshot}
Your complete debate history: {neutral_history}
Aggressive's complete debate history: {aggressive_history}
Conservative's complete debate history: {conservative_history}
Last aggressive argument body: {current_aggressive_response}
Last conservative argument body: {current_conservative_response}
If there are no responses from the other viewpoints yet, present your own argument based on the available data.

        Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Write the visible body in 3-5 short paragraphs with blank lines between paragraphs; do not use bullet points or numbered lists.
        {get_neutral_risk_instruction()}
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
            decision_summary = extract_analyst_decision_summary(raw_content)
            snapshot_full = extract_feedback_snapshot(raw_content)
            argument_body = _paragraphize_neutral_body(strip_role_prefix(
                strip_analyst_decision_summary(strip_feedback_snapshot(raw_content)),
                "Neutral Analyst",
            ))
            history_turn = build_history_turn(
                _rebuild_neutral_visible_turn(argument_body, decision_summary, snapshot_full),
                "Neutral Analyst",
            )
            new_neutral_snapshot_full = snapshot_full
            ticker = get_asset_symbol(state)
            trade_date = state.get("trade_date", "unknown")
            snapshot_path = save_snapshot_file(new_neutral_snapshot_full, "Neutral Analyst", ticker, trade_date, round_index + 1)
            new_neutral_snapshot = make_display_snapshot(new_neutral_snapshot_full, snapshot_path)
        except (openai.InternalServerError, openai.APIError, openai.APIConnectionError) as e:
            argument_body = f"本轮因服务器错误未能生成论点（{type(e).__name__}），维持上轮立场。"
            history_turn = f"{localize_role_name('Neutral Analyst')}: {argument_body}"
            new_neutral_snapshot = risk_debate_state.get("neutral_snapshot", "")
            snapshot_path = risk_debate_state.get("neutral_snapshot_path", "")
        new_debate_brief = build_debate_brief(
            {
                "Aggressive Analyst": aggressive_snapshot,
                "Conservative Analyst": conservative_snapshot,
                "Neutral Analyst": new_neutral_snapshot,
            },
            latest_speaker="Neutral Analyst",
        )

        new_risk_debate_state = {
            "history": risk_debate_state.get("history", "") + "\n" + history_turn,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + history_turn,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": f"{localize_role_name('Neutral Analyst')}: {argument_body}",
            "aggressive_snapshot": aggressive_snapshot,
            "conservative_snapshot": conservative_snapshot,
            "neutral_snapshot": new_neutral_snapshot,
            "aggressive_snapshot_path": risk_debate_state.get("aggressive_snapshot_path", ""),
            "conservative_snapshot_path": risk_debate_state.get("conservative_snapshot_path", ""),
            "neutral_snapshot_path": snapshot_path,
            "debate_brief": new_debate_brief,
            "judge_decision": risk_debate_state.get("judge_decision", ""),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
