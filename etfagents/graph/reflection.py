import logging

from etfagents.content_utils import extract_text_content

logger = logging.getLogger(__name__)


class Reflector:
    """Generate concise post-trade reflections for the memory log."""

    def __init__(self, quick_thinking_llm):
        self.quick_thinking_llm = quick_thinking_llm

    def reflect_on_final_decision(
        self,
        final_decision: str,
        raw_return: float,
        alpha_return: float,
    ) -> str:
        messages = [
            (
                "system",
                "You are reviewing a completed trading decision. Explain in 3-5 sentences what was right or wrong, "
                "which evidence mattered most, and one concrete lesson to repeat or avoid next time.",
            ),
            (
                "human",
                f"Final decision:\n{final_decision}\n\n"
                f"Outcome:\n- Raw return: {raw_return:+.1%}\n- Alpha vs SPY: {alpha_return:+.1%}",
            ),
        ]
        try:
            response = self.quick_thinking_llm.invoke(messages)
            return extract_text_content(getattr(response, "content", response)).strip()
        except Exception as exc:
            logger.warning("Reflection generation failed: %s", exc)
            return ""
