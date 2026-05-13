# TradingAgents/graph/conditional_logic.py

from etfagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    @staticmethod
    def _analyst_route(state: AgentState, tool_node: str, clear_node: str):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return tool_node
        return clear_node

    def should_continue_market_flow(self, state: AgentState):
        return self._analyst_route(state, "tools_market_flow", "Msg Clear Market Flow")

    def should_continue_social(self, state: AgentState):
        """Determine if social media analysis should continue."""
        return self.should_continue_catalyst_sentiment(state)

    def should_continue_catalyst_sentiment(self, state: AgentState):
        return self._analyst_route(
            state,
            "tools_catalyst_sentiment",
            "Msg Clear Sentiment & Catalyst",
        )

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        return self.should_continue_macro_regime(state)

    def should_continue_macro_regime(self, state: AgentState):
        return self._analyst_route(state, "tools_macro_regime", "Msg Clear Macro Regime")

    def should_continue_etf_structure(self, state: AgentState):
        return self.should_continue_meso_commodity(state)

    def should_continue_meso_commodity(self, state: AgentState):
        return self._analyst_route(
            state,
            "tools_meso_commodity",
            "Msg Clear Meso Commodity",
        )

    def should_continue_etf_flow(self, state: AgentState):
        return self.should_continue_market_flow(state)

    def should_continue_etf_macro(self, state: AgentState):
        return self.should_continue_holdings_industry(state)

    def should_continue_holdings_industry(self, state: AgentState):
        return self._analyst_route(
            state,
            "tools_holdings_industry",
            "Msg Clear Holdings-Industry Research",
        )

    def should_continue_top_holdings(self, state: AgentState):
        return self._analyst_route(
            state,
            "tools_top_holdings",
            "Msg Clear Top Holdings Research",
        )

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Research Manager"
        latest_speaker = state["investment_debate_state"].get("latest_speaker", "")
        if latest_speaker.startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Determine if risk analysis should continue."""
        if (
            state["risk_debate_state"]["count"] >= 3 * self.max_risk_discuss_rounds
        ):  # 3 rounds of back-and-forth between 3 agents
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        return "Aggressive Analyst"
