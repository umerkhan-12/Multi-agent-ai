"""
Gemini Agent — Google Gemini 2.0 Flash (Fact-Checking & Verification)
FREE tier: ai.google.dev  (15 requests/min, 1 million tokens/day FREE)
Model: gemini-2.0-flash (latest fast + free model)
SDK: google-genai (official new SDK — google-generativeai is deprecated)
"""
import os
from google import genai
from google.genai import types
from .base_agent import BaseAgent

# Gemini 2.0 Flash is completely FREE within quota limits
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
            model="gemini-2.0-flash",
        )
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY not set. Get a FREE key at https://ai.google.dev"
            )
        self.client = genai.Client(api_key=api_key)

    def _call_api(self, prompt: str, system_prompt: str) -> dict:
        sys = system_prompt or (
            "You are a meticulous fact-checker and verification specialist. "
            "Your job is to critically evaluate claims, identify any inaccuracies, "
            "verify facts, provide corrections where needed, and assess confidence "
            "levels. Be precise, objective, and thorough. "
            "Label each claim as: ✅ Verified | ⚠️ Uncertain | ❌ Incorrect."
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=sys,
                max_output_tokens=1024,
                temperature=0.2,   # low temp = factual / precise
            ),
        )

        # Token count from usage metadata
        try:
            tokens = response.usage_metadata.total_token_count
        except Exception:
            tokens = len(prompt.split()) + len(response.text.split())

        return {
            "content": response.text,
            "tokens_used": tokens,
            "cost_usd": 0.0,   # Free tier
        }
