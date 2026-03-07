"""
Gemini Agent — Google Gemini (Fact-Checking & Verification)
FREE tier: ai.google.dev  (15 requests/min, 1 million tokens/day FREE)
Model: gemini-1.5-flash (fast + free)
"""
import os
import google.generativeai as genai
from .base_agent import BaseAgent

# Gemini 1.5 Flash is completely FREE within quota limits
COST_PER_1M_TOKENS = 0.0   # Free tier


class GeminiAgent(BaseAgent):
    """
    Specialised in: Fact-checking, verification, grounding claims in reality,
    identifying inaccuracies, and providing balanced perspectives.
    """

    def __init__(self):
        super().__init__(
            name="Gemini",
            role="Fact-Checking & Verification Expert",
            model="gemini-1.5-flash",
        )
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY not set. Get a FREE key at https://ai.google.dev"
            )
        genai.configure(api_key=api_key)
        self.model_client = genai.GenerativeModel(
            model_name=self.model,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=1024,
                temperature=0.2,   # low temp = factual / precise
            ),
        )

    def _call_api(self, prompt: str, system_prompt: str) -> dict:
        sys = system_prompt or (
            "You are a meticulous fact-checker and verification specialist. "
            "Your job is to critically evaluate claims, identify any inaccuracies, "
            "verify facts, provide corrections where needed, and assess confidence "
            "levels. Be precise, objective, and thorough. "
            "Label each claim as: ✅ Verified | ⚠️ Uncertain | ❌ Incorrect."
        )

        full_prompt = f"{sys}\n\n{prompt}"
        response = self.model_client.generate_content(full_prompt)

        # Gemini free tier — token count may vary; estimate if unavailable
        try:
            tokens = response.usage_metadata.total_token_count
        except Exception:
            tokens = len(full_prompt.split()) + len(response.text.split())

        return {
            "content": response.text,
            "tokens_used": tokens,
            "cost_usd": 0.0,   # Free tier
        }
