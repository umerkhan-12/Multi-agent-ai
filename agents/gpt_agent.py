"""
GPT-4 Agent — OpenAI (Creative Generation & Explanation)
Free credits: platform.openai.com (new accounts get $5 free)
Model: gpt-3.5-turbo  (free-tier friendly, swap to gpt-4o if you have credits)
"""
import os
from openai import OpenAI
from .base_agent import BaseAgent

# Pricing per 1M tokens (gpt-3.5-turbo)
INPUT_COST_PER_1M  = 0.50
OUTPUT_COST_PER_1M = 1.50


class GPTAgent(BaseAgent):
    """
    Specialised in: Creative writing, clear explanations, ideation, brainstorming.
    Uses OpenAI's GPT-3.5-turbo by default (swap to gpt-4o in .env if available).
    """

    def __init__(self):
        model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        super().__init__(
            name="GPT-4",
            role="Creative Generation & Explanation Expert",
            model=model,
        )
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY not set. Get free credits at https://platform.openai.com"
            )
        self.client = OpenAI(api_key=api_key)

    def _call_api(self, prompt: str, system_prompt: str) -> dict:
        sys = system_prompt or (
            "You are a highly creative expert at generating ideas, stories, "
            "explanations, and innovative solutions. Make your responses engaging, "
            "clear, and imaginative. Use examples and analogies to make complex "
            "concepts easy to understand."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1024,
            temperature=0.8,   # higher temp = more creative
        )

        usage        = response.usage
        total_tokens = usage.total_tokens
        cost = (usage.prompt_tokens / 1_000_000 * INPUT_COST_PER_1M) + \
               (usage.completion_tokens / 1_000_000 * OUTPUT_COST_PER_1M)

        return {
            "content": response.choices[0].message.content,
            "tokens_used": total_tokens,
            "cost_usd": round(cost, 6),
        }
