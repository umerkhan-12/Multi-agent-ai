"""Central settings. Everything is overridable with environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("MT_DATA_DIR", ROOT.parent / "data"))
KNOWLEDGE_DIR = Path(os.getenv("MT_KNOWLEDGE_DIR", ROOT / "knowledge"))


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _has(name: str) -> bool:
    v = os.getenv(name, "").strip()
    return bool(v) and not v.startswith("your_")   # ignore .env.example placeholders


def _default_provider() -> str:
    """Pick the first provider that has a key. Free tiers first."""
    if _has("GOOGLE_API_KEY"):
        return "gemini"      # free tier: aistudio.google.com
    if _has("GROQ_API_KEY"):
        return "groq"        # free tier: console.groq.com
    if _has("ANTHROPIC_API_KEY"):
        return "claude"      # paid, best quality
    return "offline"         # no key → deterministic templates, demo still works


@dataclass
class Settings:
    # ── LLM ────────────────────────────────────────────────────────────────
    provider: str = os.getenv("MT_LLM_PROVIDER", _default_provider())
    gemini_model: str = os.getenv("MT_GEMINI_MODEL", "gemini-2.5-flash")
    groq_model: str = os.getenv("MT_GROQ_MODEL", "llama-3.3-70b-versatile")
    claude_model: str = os.getenv("MT_CLAUDE_MODEL", "claude-opus-5-5")

    # ── Budget ("Credits running low" interrupt). Free tiers cost $0 but have
    #    rate limits, so we also cap LLM calls per day.
    daily_budget_usd: float = float(os.getenv("MT_DAILY_BUDGET_USD", "2.0"))
    budget_warn_ratio: float = float(os.getenv("MT_BUDGET_WARN_RATIO", "0.8"))
    daily_llm_calls: int = int(os.getenv("MT_DAILY_LLM_CALLS", "200"))

    # ── Guardrail thresholds ──────────────────────────────────────────────
    hot_lead_score: int = int(os.getenv("MT_HOT_LEAD_SCORE", "80"))
    viral_multiplier: float = float(os.getenv("MT_VIRAL_MULTIPLIER", "5"))

    # ── API security (n8n → API calls send this header) ──────────────────
    api_key: str = os.getenv("MT_API_KEY", "")

    # ── Storage ───────────────────────────────────────────────────────────
    db_path: Path = field(default_factory=lambda: DATA_DIR / "marketing.db")
    brief_dir: Path = field(default_factory=lambda: DATA_DIR / "briefs")

    # ── Brand ─────────────────────────────────────────────────────────────
    brand_name: str = os.getenv("MT_BRAND_NAME", "Jev Fitness")


settings = Settings()

# Pricing per 1M tokens (input, output). Free tiers are $0.
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
