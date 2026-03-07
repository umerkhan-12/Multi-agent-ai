"""
Claude Agent — Anthropic Claude (Research & Deep Analysis)
Free tier: console.anthropic.com
Model: claude-3-haiku-20240307 (cheapest / fastest)
"""
import os
import anthropic
from .base_agent import BaseAgent

# Pricing per 1M tokens (claude-3-haiku)
INPUT_COST_PER_1M  = 0.25   # $0.25 / 1M input tokens
OUTPUT_COST_PER_1M = 1.25   # $1.25 / 1M output tokens


class ClaudeAgent(BaseAgent):
    """
    Specialised in: Research, deep analysis, structured reasoning.
    Uses Anthropic's Claude-3-Haiku (cheapest model, still very capable).
    """

    def __init__(self):
        super().__init__(
            name="Claude",
            role="Research & Analysis Expert",
            model="claude-3-haiku-20240307",
        )
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not set. Get a free key at https://console.anthropic.com"
            )
        self.client = anthropic.Anthropic(api_key=api_key)

    def _call_api(self, prompt: str, system_prompt: str) -> dict:
        sys = system_prompt or (
            "You are an expert researcher and analyst. "
            "Provide thorough, well-structured research and deep analysis. "
            "Use bullet points, clear sections, and cite key facts where relevant."
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=sys,
            messages=[{"role": "user", "content": prompt}],
        )

        input_tokens  = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        total_tokens  = input_tokens + output_tokens
        cost = (input_tokens / 1_000_000 * INPUT_COST_PER_1M) + \
               (output_tokens / 1_000_000 * OUTPUT_COST_PER_1M)

        return {
            "content": message.content[0].text,
            "tokens_used": total_tokens,
            "cost_usd": round(cost, 6),
        }
