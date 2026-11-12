"""'What interrupts the loop' — enforced in code, not just in prompts.

Prompts can be ignored by a model; these checks can't. Every trigger creates an
escalation row and pings the human through the notify adapter.

  Trigger                    Source
  ─────────────────────────  ─────────────────────────────────────────────
  customer_wants_person      Comment & DM Agent → escalate_to_human tool
  angry_comment              Comment & DM Agent → escalate_to_human tool
  risky_claim                any draft → check_compliance() (banned phrases)
  post_viral                 Post Analyst → check_viral() on metrics refresh
  hot_lead                   Lead Scorer → check_hot_lead() on score update
  music_unlicensed           Editor → escalate_to_human tool
  unsubscribe                webhook / Segmenter → handle_unsubscribe()
  credits_low                LLM layer → check_budget() before each run
"""
from __future__ import annotations

import re
import statistics

from . import db, integrations
from .config import KNOWLEDGE_DIR, settings

TRIGGERS = {
    "customer_wants_person": "high",
    "angry_comment": "high",
    "risky_claim": "high",
    "post_viral": "normal",
    "hot_lead": "high",
    "music_unlicensed": "normal",
    "unsubscribe": "low",
    "credits_low": "high",
}


def escalate(trigger: str, detail: str, ref_type: str | None = None, ref_id: int | None = None) -> int:
    if trigger not in TRIGGERS:
        trigger_detail = f"[{trigger}] {detail}"
        trigger, detail = "customer_wants_person", trigger_detail
    # De-duplicate: one open escalation per trigger+ref
    existing = db.one("SELECT id FROM escalations WHERE status='open' AND trigger=? "
                      "AND IFNULL(ref_type,'')=IFNULL(?, '') AND IFNULL(ref_id,-1)=IFNULL(?, -1)",
                      (trigger, ref_type, ref_id))
    if existing:
        return existing["id"]
    esc_id = db.insert("escalations", trigger=trigger, severity=TRIGGERS[trigger],
                       ref_type=ref_type, ref_id=ref_id, detail=detail)
    try:
        integrations.notify.send(f"⚠️ {trigger.replace('_', ' ').title()}: {detail}")
    except Exception as exc:  # notifications must never crash the loop
        db.log_event("guardrails", "notify_failed", str(exc))
    return esc_id


# ── Compliance ──────────────────────────────────────────────────────────────

def banned_phrases() -> list[str]:
    text = (KNOWLEDGE_DIR / "compliance.md").read_text(encoding="utf-8")
    section = text.split("## Banned claims", 1)[-1].split("##", 1)[0]
    return [m.strip().lower() for m in re.findall(r"^-\s*(.+)$", section, flags=re.M)]


def check_compliance(*texts: str | None) -> list[str]:
    blob = " ".join(t for t in texts if t).lower()
    return [p for p in banned_phrases() if p and p in blob]


# ── Metrics-driven triggers ─────────────────────────────────────────────────

def check_viral(post_id: int) -> bool:
    post = db.one("SELECT id, title, views FROM posts WHERE id=?", (post_id,))
    others = [r["views"] for r in db.query(
        "SELECT views FROM posts WHERE status='published' AND id != ? AND views > 0", (post_id,))]
    if not post or len(others) < 3:
        return False
    if post["views"] >= settings.viral_multiplier * statistics.median(others):
        escalate("post_viral", f"'{post['title']}' hit {post['views']:,} views — reply to comments "
                 "and consider a follow-up post.", "post", post_id)
        return True
    return False


def check_hot_lead(lead_id: int) -> bool:
    lead = db.one("SELECT id, name, email, score FROM leads WHERE id=?", (lead_id,))
    if lead and lead["score"] >= settings.hot_lead_score:
        escalate("hot_lead", f"{lead['name'] or lead['email']} scored {lead['score']} — "
                 "reach out personally.", "lead", lead_id)
        return True
    return False


def handle_unsubscribe(email: str) -> None:
    lead = db.one("SELECT id FROM leads WHERE email=?", (email,))
    if lead:
        db.update("leads", lead["id"], stage="unsubscribed")
        escalate("unsubscribe", f"{email} unsubscribed — removed from all sequences.", "lead", lead["id"])


class BudgetExceeded(RuntimeError):
    pass


def check_budget() -> None:
    spent = db.spend_today()
    if spent >= settings.daily_budget_usd:
        escalate("credits_low", f"Daily AI budget used up (${spent:.2f}/${settings.daily_budget_usd:.2f}). "
                 "Agents paused until tomorrow or until you raise MT_DAILY_BUDGET_USD.")
        raise BudgetExceeded(f"Daily budget ${settings.daily_budget_usd} reached")
    if spent >= settings.budget_warn_ratio * settings.daily_budget_usd:
        escalate("credits_low", f"AI spend at ${spent:.2f} of ${settings.daily_budget_usd:.2f} today.")
