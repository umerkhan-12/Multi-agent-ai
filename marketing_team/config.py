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


@dataclass
class Settings:
    # ── LLM ────────────────────────────────────────────────────────────────
    model: str = os.getenv("MT_MODEL", "claude-opus-5-5")
    # Cheaper model for high-volume, low-judgement agents (comment replies, reminders…)
    fast_model: str = os.getenv("MT_FAST_MODEL", "claude-opus-5-5")
    max_tokens: int = int(os.getenv("MT_MAX_TOKENS", "16000"))
    max_tool_rounds: int = int(os.getenv("MT_MAX_TOOL_ROUNDS", "12"))
    # Server-side refusal fallback (beta). Disable if your platform lacks it.
    use_fallbacks: bool = _bool("MT_USE_FALLBACKS", True)
    # No API key → run in dry-run mode (no LLM calls, deterministic stubs).
    dry_run: bool = _bool("MT_DRY_RUN", not bool(os.getenv("ANTHROPIC_API_KEY")))

    # ── Budget / credits ("Credits running low" interrupt) ────────────────
    daily_budget_usd: float = float(os.getenv("MT_DAILY_BUDGET_USD", "5.0"))
    budget_warn_ratio: float = float(os.getenv("MT_BUDGET_WARN_RATIO", "0.8"))

    # ── Guardrail thresholds ──────────────────────────────────────────────
    hot_lead_score: int = int(os.getenv("MT_HOT_LEAD_SCORE", "80"))
    viral_multiplier: float = float(os.getenv("MT_VIRAL_MULTIPLIER", "5"))
    # Auto-publish without a human click? Keep False until you trust the system.
    auto_publish: bool = _bool("MT_AUTO_PUBLISH", False)

    # ── Storage ───────────────────────────────────────────────────────────
    db_path: Path = field(default_factory=lambda: DATA_DIR / "marketing.db")
    brief_dir: Path = field(default_factory=lambda: DATA_DIR / "briefs")

    # ── Brand ─────────────────────────────────────────────────────────────
    brand_name: str = os.getenv("MT_BRAND_NAME", "Jev Fitness")


settings = Settings()

# Pricing per 1M tokens (input, output) — keep in sync with your provider bill.
PRICING = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
