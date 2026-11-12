"""One tiny interface over several LLM providers.

    text = complete(system, prompt)               -> str
    data = complete_json(system, prompt, default)  -> dict

Providers: gemini (free tier), groq (free tier), claude (paid), offline (no key).
Agents only ask for text or JSON, so any provider works and you can switch with
MT_LLM_PROVIDER without touching agent code. Every call is logged to `runs`
with tokens and cost, and checked against the daily budget first.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from . import db, guardrails
from .config import PRICING, settings


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "offline"

    @property
    def cost_usd(self) -> float:
        pin, pout = PRICING.get(self.model, (0.0, 0.0))
        return (self.input_tokens * pin + self.output_tokens * pout) / 1_000_000


# ── Provider calls ──────────────────────────────────────────────────────────

def _gemini(system: str, prompt: str, want_json: bool) -> LLMResult:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json" if want_json else "text/plain",
    )
    r = client.models.generate_content(model=settings.gemini_model, contents=prompt, config=cfg)
    u = r.usage_metadata
    return LLMResult(r.text or "", getattr(u, "prompt_token_count", 0) or 0,
                     getattr(u, "candidates_token_count", 0) or 0, settings.gemini_model)


def _groq(system: str, prompt: str, want_json: bool) -> LLMResult:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    kwargs = {"response_format": {"type": "json_object"}} if want_json else {}
    r = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        **kwargs,
    )
    return LLMResult(r.choices[0].message.content or "", r.usage.prompt_tokens,
                     r.usage.completion_tokens, settings.groq_model)


def _claude(system: str, prompt: str, want_json: bool) -> LLMResult:
    import anthropic

    client = anthropic.Anthropic()
    r = client.messages.create(
        model=settings.claude_model,
        max_tokens=16000,
        output_config={"effort": "low"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if r.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request")
    text = "".join(b.text for b in r.content if b.type == "text")
    return LLMResult(text, r.usage.input_tokens, r.usage.output_tokens, settings.claude_model)


PROVIDERS = {"gemini": _gemini, "groq": _groq, "claude": _claude}


# ── Public API ──────────────────────────────────────────────────────────────

def _calls_today() -> int:
    row = db.one("SELECT COUNT(*) n FROM runs WHERE created_at >= ? AND output != 'offline'", (db.today(),))
    return row["n"] if row else 0


def _run(agent: str, system: str, prompt: str, want_json: bool, offline: str) -> str:
    provider = settings.provider
    if provider != "offline":
        guardrails.check_budget()
        if _calls_today() >= settings.daily_llm_calls:
            guardrails.escalate("credits_low", f"Hit {settings.daily_llm_calls} LLM calls today; "
                                "falling back to offline mode.")
            provider = "offline"

    if provider == "offline":
        res = LLMResult(offline)
    else:
        try:
            res = PROVIDERS[provider](system, prompt, want_json)
        except Exception as exc:  # free tiers rate-limit: degrade instead of crashing
            db.log_event(agent, "llm_error", f"{provider}: {exc}")
            res = LLMResult(offline)

    db.insert("runs", agent=agent, department="analytics", task=prompt[:500],
              output="offline" if res.model == "offline" else res.text[:4000],
              input_tokens=res.input_tokens, output_tokens=res.output_tokens,
              cost_usd=res.cost_usd, ok=1)
    return res.text


def complete(agent: str, system: str, prompt: str, offline: str = "") -> str:
    return _run(agent, system, prompt, False, offline).strip()


def complete_json(agent: str, system: str, prompt: str, default: dict) -> dict:
    system += "\nRespond with a single JSON object only. No markdown fences."
    raw = _run(agent, system, prompt, True, json.dumps(default))
    match = re.search(r"\{.*\}", raw, flags=re.S)
    try:
        data = json.loads(match.group(0)) if match else default
    except json.JSONDecodeError:
        data = default
    return {**default, **data} if isinstance(data, dict) else default
