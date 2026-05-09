# TradingAgents/graph/propagation.py

from typing import Dict, Any, List, Optional
from etfagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from etfagents.agents.utils.state_keys import with_state_aliases


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self, asset_symbol: str, trade_date: str, past_context: str = ""
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        return with_state_aliases({
            "messages": [("human", asset_symbol)],
            "asset_of_interest": asset_symbol,
            "trade_date": str(trade_date),
            "past_context": past_context or "",
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "current_bull_response": "",
                    "current_bear_response": "",
                    "bull_snapshot": "",
                    "bear_snapshot": "",
                    "bull_snapshot_path": "",
                    "bear_snapshot_path": "",
                    "debate_brief": "",
                    "latest_speaker": "",
                    "judge_decision": "",
                    "judge_snapshot": "",
                    "judge_snapshot_path": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "debate_brief": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "aggressive_snapshot": "",
                    "conservative_snapshot": "",
                    "neutral_snapshot": "",
                    "aggressive_snapshot_path": "",
                    "conservative_snapshot_path": "",
                    "neutral_snapshot_path": "",
                    "judge_decision": "",
                    "judge_snapshot_path": "",
                    "count": 0,
                }
            ),
            "market_flow_report": "",
            "meso_commodity_report": "",
            "catalyst_sentiment_report": "",
            "macro_regime_report": "",
            "holdings_industry_report": "",
            "top_holdings_report": "",
            "research_allocation_plan": "",
            "trader_allocation_plan": "",
            "final_allocation_decision": "",
        })

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
