import copy
import unittest
from unittest.mock import MagicMock

from etfagents.agents.managers.portfolio_manager import create_portfolio_manager
from etfagents.agents.managers.research_manager import create_research_manager
from etfagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    TraderProposal,
)
from etfagents.agents.trader.trader import create_trader


class _FakeResponse:
    def __init__(self, content):
        self.content = content


def _base_state():
    return {
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-10",
        "past_context": "",
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "research_report": "",
        "stock_report": "",
        "investment_plan": "Research plan.",
        "trader_investment_plan": "Trader plan.",
        "investment_debate_state": {
            "history": "",
            "bear_history": "",
            "bull_history": "",
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
            "count": 1,
        },
        "risk_debate_state": {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
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
            "debate_brief": "",
            "judge_decision": "",
            "judge_snapshot": "",
            "judge_snapshot_path": "",
            "count": 1,
        },
    }


class StructuredAgentTests(unittest.TestCase):
    def test_trader_renders_structured_output(self):
        llm = MagicMock()
        structured = MagicMock()
        structured.invoke.return_value = TraderProposal(
            thesis="Wait for confirmation before adding.",
            execution_plan="Enter in tranches above support.",
            risk_management="Reduce if support breaks.",
            rating=PortfolioRating.HOLD,
        )
        llm.with_structured_output.return_value = structured

        result = create_trader(llm)(copy.deepcopy(_base_state()))

        self.assertIn("## ETF Allocation Thesis", result["trader_investment_plan"])
        self.assertIn("EXECUTION BIAS: **HOLD**", result["trader_investment_plan"])

    def test_research_manager_renders_structured_output(self):
        llm = MagicMock()
        llm.invoke.return_value = _FakeResponse("Side synthesis.")
        structured = MagicMock()
        structured.invoke.return_value = ResearchPlan(
            debate_conclusion="Bull evidence is stronger overall.",
            action_logic="Catalysts still need confirmation before sizing up.",
            positioning_recommendation="Maintain an overweight stance with staged adds.",
            rating=PortfolioRating.OVERWEIGHT,
            snapshot_stance="Overweight",
            snapshot_new_and_rebuttal="Added a clearer catalyst sequence and rebutted valuation-only objections.",
            snapshot_to_verify="Track orders, gross margin, and capex.",
        )
        llm.with_structured_output.return_value = structured

        result = create_research_manager(llm)(copy.deepcopy(_base_state()))

        self.assertIn("## Debate Conclusion", result["investment_plan"])
        self.assertIn("Research View: **Overweight**", result["investment_plan"])
        self.assertIn("FEEDBACK SNAPSHOT:", result["investment_plan"])

    def test_portfolio_manager_falls_back_to_freetext(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = _FakeResponse(
            "## Debate Conclusion\nBalanced view.\n\n"
            "## Action Logic\nWait for confirmation.\n\n"
            "## Positioning Recommendation\nKeep the position light.\n\n"
            "FINAL TRANSACTION PROPOSAL: **HOLD**\n\n"
            "FEEDBACK SNAPSHOT:\n"
            "- Stance: Hold\n"
            "- New this round & rebuttal: Added more cautious sizing.\n"
            "- To verify: Watch earnings."
        )

        result = create_portfolio_manager(llm)(copy.deepcopy(_base_state()))

        self.assertIn("FINAL TRANSACTION PROPOSAL: **HOLD**", result["final_trade_decision"])
        self.assertIn("FEEDBACK SNAPSHOT:", result["final_trade_decision"])

    def test_trader_falls_back_when_structured_invoke_fails(self):
        llm = MagicMock()
        structured = MagicMock()
        structured.invoke.side_effect = ValueError("bad structured payload")
        llm.with_structured_output.return_value = structured
        llm.invoke.return_value = _FakeResponse(
            "## Trading Thesis\nFallback thesis.\n\n"
            "## Execution Plan\nWait.\n\n"
            "## Risk Management\nWatch support.\n\n"
            "FINAL TRANSACTION PROPOSAL: **HOLD**"
        )

        result = create_trader(llm)(copy.deepcopy(_base_state()))

        self.assertIn("Fallback thesis.", result["trader_investment_plan"])
        self.assertIn("FINAL TRANSACTION PROPOSAL: **HOLD**", result["trader_investment_plan"])


if __name__ == "__main__":
    unittest.main()
