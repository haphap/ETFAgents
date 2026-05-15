from typing import Annotated, Sequence
from datetime import date, timedelta, datetime
from typing_extensions import TypedDict, Optional
from langchain_openai import ChatOpenAI
from etfagents.agents import *
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, StateGraph, START, MessagesState


# Researcher team state
class InvestDebateState(TypedDict):
    bull_history: Annotated[
        str, "Bullish Conversation history"
    ]  # Bullish Conversation history
    bear_history: Annotated[
        str, "Bearish Conversation history"
    ]  # Bullish Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    current_response: Annotated[str, "Latest response"]  # Last response
    bull_snapshot: Annotated[str, "Latest bull feedback snapshot"]
    bear_snapshot: Annotated[str, "Latest bear feedback snapshot"]
    bull_snapshot_path: Annotated[str, "Path to full bull snapshot file"]
    bear_snapshot_path: Annotated[str, "Path to full bear snapshot file"]
    current_bull_response: Annotated[str, "Last full argument by bull analyst"]
    current_bear_response: Annotated[str, "Last full argument by bear analyst"]
    debate_brief: Annotated[str, "Compact latest debate brief"]
    latest_speaker: Annotated[str, "Speaker that updated the brief last"]
    judge_decision: Annotated[str, "Final judge decision"]  # Last response
    judge_snapshot: Annotated[str, "Latest research manager feedback snapshot"]
    judge_snapshot_path: Annotated[str, "Path to full research manager snapshot file"]
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


# Risk management team state
class RiskDebateState(TypedDict):
    aggressive_history: Annotated[
        str, "Aggressive Agent's Conversation history"
    ]  # Conversation history
    conservative_history: Annotated[
        str, "Conservative Agent's Conversation history"
    ]  # Conversation history
    neutral_history: Annotated[
        str, "Neutral Agent's Conversation history"
    ]  # Conversation history
    history: Annotated[str, "Conversation history"]  # Conversation history
    debate_brief: Annotated[str, "Compact latest risk debate brief"]
    latest_speaker: Annotated[str, "Analyst that spoke last"]
    current_aggressive_response: Annotated[
        str, "Latest response by the aggressive analyst"
    ]  # Last response
    current_conservative_response: Annotated[
        str, "Latest response by the conservative analyst"
    ]  # Last response
    current_neutral_response: Annotated[
        str, "Latest response by the neutral analyst"
    ]  # Last response
    aggressive_snapshot: Annotated[str, "Latest aggressive feedback snapshot"]
    conservative_snapshot: Annotated[str, "Latest conservative feedback snapshot"]
    neutral_snapshot: Annotated[str, "Latest neutral feedback snapshot"]
    aggressive_snapshot_path: Annotated[str, "Path to full aggressive snapshot file"]
    conservative_snapshot_path: Annotated[str, "Path to full conservative snapshot file"]
    neutral_snapshot_path: Annotated[str, "Path to full neutral snapshot file"]
    judge_decision: Annotated[str, "Judge's decision"]
    judge_snapshot: Annotated[str, "Latest portfolio manager feedback snapshot"]
    judge_snapshot_path: Annotated[str, "Path to full portfolio manager snapshot file"]
    count: Annotated[int, "Length of the current conversation"]  # Conversation length


class AgentState(MessagesState):
    asset_of_interest: Annotated[str, "ETF ticker or candidate that the framework is analyzing"]
    company_of_interest: Annotated[str, "Legacy alias for asset_of_interest"]
    trade_date: Annotated[str, "What date we are trading at"]
    past_context: Annotated[str, "Resolved lessons from prior decisions"]
    continuity_context: Annotated[dict[str, str], "Role-aware continuity briefs from the latest same-ticker analysis"]
    lesson_context: Annotated[dict[str, str], "Role-aware resolved historical lessons"]
    method_context: Annotated[dict[str, str], "Role-aware reusable analysis-method reminders"]

    sender: Annotated[str, "Agent that sent this message"]

    # research step
    market_flow_report: Annotated[str, "Report from the market and flow analyst"]
    market_report: Annotated[str, "Legacy alias for market_flow_report"]
    research_report: Annotated[str, "Legacy alias for market_flow_report"]
    etf_flow_report: Annotated[str, "Legacy alias for market_flow_report"]

    catalyst_sentiment_report: Annotated[str, "Report from the sentiment and catalyst analyst"]
    sentiment_report: Annotated[str, "Legacy alias for catalyst_sentiment_report"]

    macro_regime_report: Annotated[str, "Report from the macro regime analyst"]
    news_report: Annotated[str, "Legacy alias for macro_regime_report"]

    meso_commodity_report: Annotated[str, "Report from the meso commodity analyst"]
    etf_structure_report: Annotated[str, "Legacy alias for meso_commodity_report"]
    fundamentals_report: Annotated[str, "Legacy alias for meso_commodity_report"]

    holdings_industry_report: Annotated[str, "Report from the ETF holdings-industry research analyst"]
    etf_macro_report: Annotated[str, "Legacy alias for holdings_industry_report"]
    stock_report: Annotated[str, "Legacy alias for holdings_industry_report"]

    top_holdings_report: Annotated[str, "Report from the ETF top holdings research analyst"]
    etf_stock_research_report: Annotated[str, "Legacy alias for top_holdings_report"]

    # researcher team discussion step
    investment_debate_state: Annotated[
        InvestDebateState, "Current state of the debate on if to invest or not"
    ]
    research_allocation_plan: Annotated[str, "Allocation view generated by the research manager"]
    investment_plan: Annotated[str, "Legacy alias for research_allocation_plan"]

    trader_allocation_plan: Annotated[str, "ETF allocation plan generated by the trader"]
    trader_investment_plan: Annotated[str, "Legacy alias for trader_allocation_plan"]
    trader_backtest_signal: Annotated[
        dict[str, object],
        "Framework-agnostic signal extracted from the trader execution plan",
    ]

    # risk management team discussion step
    risk_debate_state: Annotated[
        RiskDebateState, "Current state of the debate on evaluating risk"
    ]
    final_allocation_decision: Annotated[str, "Final ETF portfolio allocation decision"]
    final_trade_decision: Annotated[str, "Legacy alias for final_allocation_decision"]
    portfolio_backtest_signal: Annotated[
        dict[str, object],
        "Framework-agnostic signal extracted from the portfolio manager recommendation",
    ]
    backtest_signal: Annotated[
        dict[str, object],
        "Preferred final backtest signal for this analysis run",
    ]
    analysis_memory_entry: Annotated[
        dict[str, object],
        "Structured memory snapshot written after the final portfolio decision",
    ]
