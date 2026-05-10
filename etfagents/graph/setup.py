from typing import Any, Callable, Dict

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from etfagents.agents import (
    AgentState,
    create_aggressive_debator,
    create_bear_researcher,
    create_broker_research_analyst,
    create_bull_researcher,
    create_conservative_debator,
    create_fundamentals_analyst,
    create_market_analyst,
    create_msg_delete,
    create_neutral_debator,
    create_news_analyst,
    create_portfolio_manager,
    create_research_manager,
    create_social_media_analyst,
    create_stock_research_analyst,
    create_trader,
)

from .conditional_logic import ConditionalLogic


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    DEFAULT_SELECTED_ANALYSTS = (
        "market",
        "social",
        "news",
        "fundamentals",
        "broker_research",
        "stock_research",
    )

    ANALYST_BUILDERS: Dict[str, Callable[[Any], Any]] = {
        "market": create_market_analyst,
        "social": create_social_media_analyst,
        "news": create_news_analyst,
        "fundamentals": create_fundamentals_analyst,
        "broker_research": create_broker_research_analyst,
        "stock_research": create_stock_research_analyst,
    }

    def __init__(
        self,
        quick_thinking_llm: Any,
        deep_thinking_llm: Any,
        tool_nodes: Dict[str, ToolNode],
        conditional_logic: ConditionalLogic,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.conditional_logic = conditional_logic

    # Display names for analysts with underscores in their keys
    _ANALYST_DISPLAY_NAMES = {
        "broker_research": "Industry Research",
        "stock_research": "Stock Research",
    }
    _CLEAR_ROUTE_ALIASES = {
        "market": ("Msg Clear Market",),
        "market_flow": ("Msg Clear Market", "Msg Clear Market Flow", "Msg Clear ETF Flow"),
        "social": ("Msg Clear Social",),
        "catalyst_sentiment": ("Msg Clear Social",),
        "news": ("Msg Clear News",),
        "macro_regime": ("Msg Clear News", "Msg Clear ETF Macro"),
        "fundamentals": ("Msg Clear Fundamentals",),
        "etf_structure": ("Msg Clear ETF Structure",),
        "meso_commodity": ("Msg Clear ETF Structure",),
        "etf_flow": ("Msg Clear ETF Flow",),
        "etf_macro": ("Msg Clear ETF Macro",),
        "broker_research": ("Msg Clear Industry Research",),
        "holdings_industry": ("Msg Clear Industry Research", "Msg Clear Holdings-Industry Research", "Msg Clear ETF Industry Research"),
        "stock_research": ("Msg Clear Stock Research",),
        "top_holdings": ("Msg Clear Stock Research", "Msg Clear Top Holdings Research", "Msg Clear ETF Top Holdings Research"),
    }

    def _analyst_display_name(self, analyst_type: str) -> str:
        """Return display name for an analyst type (handles underscores)."""
        return self._ANALYST_DISPLAY_NAMES.get(analyst_type, analyst_type.capitalize())

    def _analyst_route_map(self, analyst_type: str) -> Dict[str, str]:
        """Map conditional route labels to actual node names.

        ConditionalLogic still returns several legacy clear-node labels from the
        pre-ETF-renaming era. Accept both those stable labels and the current
        display-derived node name so routing keeps working when visible analyst
        titles change.
        """
        display = self._analyst_display_name(analyst_type)
        tool_node = f"tools_{analyst_type}"
        clear_node = f"Msg Clear {display}"
        route_map = {
            tool_node: tool_node,
            clear_node: clear_node,
        }
        for alias in self._CLEAR_ROUTE_ALIASES.get(analyst_type, ()):
            route_map[alias] = clear_node
        return route_map

    def setup_graph(self, selected_analysts=None):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
                - "broker_research": Industry research analyst — industry reports (A-share only)
                - "stock_research": Stock research analyst — individual stock reports (A-share only)
        """
        if selected_analysts is None:
            selected_analysts = list(self.DEFAULT_SELECTED_ANALYSTS)
        else:
            selected_analysts = list(selected_analysts)

        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        for analyst_type in selected_analysts:
            builder = self.ANALYST_BUILDERS.get(analyst_type)
            if builder is None:
                raise ValueError(f"Unsupported analyst type '{analyst_type}'.")
            analyst_nodes[analyst_type] = builder(self.quick_thinking_llm)
            delete_nodes[analyst_type] = create_msg_delete()
            tool_nodes[analyst_type] = self.tool_nodes[analyst_type]

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(self.quick_thinking_llm)
        bear_researcher_node = create_bear_researcher(self.quick_thinking_llm)
        research_manager_node = create_research_manager(self.deep_thinking_llm)
        trader_node = create_trader(self.deep_thinking_llm)

        # Create risk analysis nodes
        aggressive_analyst = create_aggressive_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        conservative_analyst = create_conservative_debator(self.quick_thinking_llm)
        portfolio_manager_node = create_portfolio_manager(self.deep_thinking_llm)

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            display = self._analyst_display_name(analyst_type)
            workflow.add_node(f"{display} Analyst", node)
            workflow.add_node(
                f"Msg Clear {display}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Aggressive Analyst", aggressive_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Conservative Analyst", conservative_analyst)
        workflow.add_node("Portfolio Manager", portfolio_manager_node)

        # Define edges
        # Start with the first analyst
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{self._analyst_display_name(first_analyst)} Analyst")

        # Connect analysts in sequence
        for i, analyst_type in enumerate(selected_analysts):
            display = self._analyst_display_name(analyst_type)
            current_analyst = f"{display} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {display}"

            # Add conditional edges for current analyst
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                self._analyst_route_map(analyst_type),
            )
            workflow.add_edge(current_tools, current_analyst)

            # Connect to next analyst or to Bull Researcher if this is the last analyst
            if i < len(selected_analysts) - 1:
                next_analyst = f"{self._analyst_display_name(selected_analysts[i+1])} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Aggressive Analyst")
        workflow.add_conditional_edges(
            "Aggressive Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Conservative Analyst": "Conservative Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Conservative Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Aggressive Analyst": "Aggressive Analyst",
                "Portfolio Manager": "Portfolio Manager",
            },
        )

        workflow.add_edge("Portfolio Manager", END)

        return workflow
