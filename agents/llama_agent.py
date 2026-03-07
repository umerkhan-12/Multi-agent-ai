"""
Llama Agent — Meta Llama 3 via Groq (Code Generation)
FREE tier: console.groq.com  (very generous — 14,400 req/day FREE)
Model: llama-3.3-70b-versatile (latest Llama 3, excellent at code)
"""
import os
from groq import Groq
from .base_agent import BaseAgent

# Groq free tier — no cost for free quota
COST_PER_1M_TOKENS = 0.0


class LlamaAgent(BaseAgent):
    """
    Specialised in: Code generation, debugging, technical implementations,
    algorithms, and software architecture.
    Uses Meta's Llama 3.3 70B via Groq's ultra-fast inference API.
    """

    def __init__(self):
        super().__init__(
            name="Llama",
            role="Code Generation & Technical Expert",
            model="llama-3.3-70b-versatile",
        )
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GROQ_API_KEY not set. Get a FREE key at https://console.groq.com"
            )
        self.client = Groq(api_key=api_key)

    def _call_api(self, prompt: str, system_prompt: str) -> dict:
        sys = system_prompt or (
            "You are an expert software engineer and code generation specialist. "
            "When asked about code: write clean, well-commented, production-ready code. "
            "Always include: language identifier in code blocks, brief explanation, "
            "edge-case handling, and usage examples. "
            "Prefer modern best practices and idiomatic patterns."
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1024,
            temperature=0.3,   # low temp = precise / deterministic code
        )

        usage = response.usage
        tokens = usage.total_tokens if usage else 0

        return {
            "content": response.choices[0].message.content,
            "tokens_used": tokens,
            "cost_usd": 0.0,   # Free tier
        }
