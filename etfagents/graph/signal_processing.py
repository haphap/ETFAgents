# TradingAgents/graph/signal_processing.py

from etfagents.agents.utils.rating import parse_rating


class SignalProcessor:
    """Processes allocation signals to extract actionable ETF decisions."""

    def __init__(self, quick_thinking_llm=None):
        """Keep backward compatibility with the previous constructor signature."""
        self.quick_thinking_llm = quick_thinking_llm

    def process_signal(self, full_signal: str) -> str:
        return parse_rating(full_signal)
