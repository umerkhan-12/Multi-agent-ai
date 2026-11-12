"""The agents.

Design rule: **numbers come from SQL, judgement comes from the LLM.** An LLM never
does arithmetic on revenue; it receives computed facts and writes insights,
scores, replies or plans. Each agent also has an offline fallback so the system
keeps running when a free tier is rate-limited.

Scheduled (The Analytics Loop, runs daily via n8n):
    PostAnalyst → CallTracker → RevenueTracker → EmailAnalyst → LoopFeeder → BriefWriter
Event-driven (WhatsApp / comments / forms / Stripe / Calendly):
    MessageTriage, LeadScorer
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from . import db, guardrails, integrations, llm
from .config import KNOWLEDGE_DIR, settings


def knowledge(*names: str) -> str:
    parts = []
    for n in names:
        p = KNOWLEDGE_DIR / f"{n}.md"
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def _system(role: str, *files: str) -> str:
    return (f"You are the {role} on the AI marketing team for {settings.brand_name}. "
            "Be concise, specific and practical. Use only the data you are given; "
            "never invent numbers.\n\n" + knowledge(*files))


@dataclass
class AgentInfo:
    name: str
    department: str
    trigger: str
    does: str


ROSTER = [
    AgentInfo("Post Analyst", "Analytics Loop", "daily", "Syncs post metrics, flags viral posts, finds what converts"),
    AgentInfo("Call Tracker", "Analytics Loop", "daily", "Links booked calls back to the post that caused them"),
    AgentInfo("Revenue Tracker", "Analytics Loop", "daily", "Links Stripe payments back to posts"),
    AgentInfo("Email Analyst", "Analytics Loop", "daily", "Open/click rates and what to fix"),
    AgentInfo("Loop Feeder", "Analytics Loop", "daily", "Writes learnings + next content ideas back into the system"),
    AgentInfo("Brief Writer", "Reporting", "daily 07:00", "Morning brief to WhatsApp"),
    AgentInfo("Message Triage", "Inbox", "on message", "Classifies WhatsApp/DMs/comments, drafts replies, escalates"),
    AgentInfo("Lead Scorer", "Inbox", "on lead", "Scores leads 0-100, flags hot leads"),
]


# ═════════════════════════════════ Analytics Loop ═══════════════════════════

def post_analyst(days: int = 30) -> dict:
    """Refresh metrics for published posts, flag viral ones, and explain what works."""
    viral = []
    for p in db.query("SELECT id, platform, external_id FROM posts WHERE status='published'"):
        if p["external_id"]:
            m = integrations.social.metrics(p["platform"], p["external_id"])
            db.update("posts", p["id"], **m)
        if guardrails.check_viral(p["id"]):
            viral.append(p["id"])

    rows = db.attribution(days)
    facts = [{k: r[k] for k in ("title", "platform", "format", "views", "leads", "calls", "sales", "revenue")}
             for r in rows]
    default = {
        "winning_pattern": _offline_pattern(rows),
        "losing_pattern": "Low-intent posts get views but no calls — they lack a clear CTA.",
        "recommendations": ["Make more of the top revenue post's format and topic.",
                            "Add the lead-magnet CTA to every high-view post."],
    }
    insights = llm.complete_json(
        "Post Analyst",
        _system("Post Analyst", "content", "offer", "learnings"),
        "Here are the last {d} days of posts with attributed leads, calls, sales and revenue:\n"
        "{facts}\n\nReturn JSON with keys: winning_pattern (string), losing_pattern (string), "
        "recommendations (array of 3 short actions). Judge posts by revenue and calls, not views."
        .format(d=days, facts=json.dumps(facts, indent=1)),
        default,
    )
    db.log_event("Post Analyst", "analysis", {"posts": len(rows), "viral": viral})
    return {"posts": facts, "viral": viral, "insights": insights}


def _offline_pattern(rows: list[dict]) -> str:
    if not rows:
        return "Not enough published posts yet."
    top = rows[0]
    return (f"'{top['title']}' ({top['format']} on {top['platform']}) drove the most revenue "
            f"(${top['revenue']:.0f}) from {top['calls']} calls — views alone don't predict sales.")


def call_tracker(days: int = 30) -> dict:
    r = db.one("""SELECT COUNT(*) total,
                  SUM(CASE WHEN source_post_id IS NOT NULL THEN 1 ELSE 0 END) attributed,
                  SUM(CASE WHEN stage IN ('call_done','customer') THEN 1 ELSE 0 END) showed
                  FROM leads WHERE call_at IS NOT NULL AND created_at >= date('now', ?)""", (f"-{days} days",))
    r = {k: (v or 0) for k, v in (r or {}).items()}
    r["show_rate"] = round(r["showed"] / r["total"], 2) if r.get("total") else 0
    db.log_event("Call Tracker", "summary", r)
    return r


def revenue_tracker(days: int = 30) -> dict:
    period = f"-{days} days"
    total = db.one("SELECT COALESCE(SUM(amount_usd),0) s, COUNT(*) n FROM sales "
                   "WHERE status='paid' AND created_at >= date('now', ?)", (period,))
    attributed = db.one("""SELECT COALESCE(SUM(s.amount_usd),0) s FROM sales s JOIN leads l ON l.id = s.lead_id
                           WHERE s.status='paid' AND l.source_post_id IS NOT NULL
                           AND s.created_at >= date('now', ?)""", (period,))
    by_product = db.query("SELECT product, COUNT(*) n, SUM(amount_usd) revenue FROM sales WHERE status='paid' "
                          "AND created_at >= date('now', ?) GROUP BY product ORDER BY revenue DESC", (period,))
    out = {"revenue": round(total["s"], 2), "sales": total["n"],
           "attributed_revenue": round(attributed["s"], 2),
           "attribution_rate": round(attributed["s"] / total["s"], 2) if total["s"] else 0,
           "by_product": by_product}
    db.log_event("Revenue Tracker", "summary", out)
    return out


def email_analyst(days: int = 30) -> dict:
    rows = db.query("SELECT subject, kind, sent_count, opens, clicks FROM emails WHERE status='sent' "
                    "AND created_at >= date('now', ?) ORDER BY created_at DESC LIMIT 20", (f"-{days} days",))
    for r in rows:
        r["open_rate"] = round(r["opens"] / r["sent_count"], 3) if r["sent_count"] else 0
        r["click_rate"] = round(r["clicks"] / r["sent_count"], 3) if r["sent_count"] else 0
    tip = "No emails sent yet — start a weekly newsletter using your top post as the topic."
    if rows:
        best = max(rows, key=lambda r: r["click_rate"])
        tip = llm.complete(
            "Email Analyst", _system("Email Analyst", "reporting"),
            f"Email results:\n{json.dumps(rows, indent=1)}\n\nIn 2 sentences: what is working and one fix.",
            offline=f"Best click rate: '{best['subject']}' ({best['click_rate']:.0%}). "
                    "Reuse its subject-line style.")
    return {"emails": rows, "tip": tip}


def loop_feeder(analysis: dict) -> dict:
    """Close the loop: write learnings to knowledge/learnings.md and queue next content ideas."""
    insights = analysis.get("insights", {})
    default = {"learning": insights.get("winning_pattern", ""),
               "ideas": [{"title": "Zone 2 myths part 2", "platform": "tiktok", "format": "reel",
                          "hook": "You've been doing cardio wrong — here's myth #4."}]}
    plan = llm.complete_json(
        "Loop Feeder", _system("Loop Feeder", "content", "channels", "offer", "audience"),
        f"Analyst insights:\n{json.dumps(insights, indent=1)}\n\nReturn JSON: learning (one sentence to "
        "remember), ideas (array of 3 objects: title, platform, format, hook) that double down on what "
        "made money.", default)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if plan.get("learning"):
        with open(KNOWLEDGE_DIR / "learnings.md", "a", encoding="utf-8") as f:
            f.write(f"- {stamp}: {plan['learning']}\n")

    created = []
    for idea in plan.get("ideas", [])[:3]:
        if not isinstance(idea, dict) or not idea.get("title"):
            continue
        risky = guardrails.check_compliance(idea.get("title"), idea.get("hook"))
        pid = db.insert("posts", title=idea["title"][:200], platform=idea.get("platform", "instagram"),
                        format=idea.get("format", "reel"), hook=idea.get("hook"),
                        status="needs_approval", created_by="Loop Feeder")
        db.insert("approvals", kind="post", ref_id=pid, requested_by="Loop Feeder",
                  summary=f"New idea: {idea['title']} — {idea.get('hook', '')}")
        if risky:
            guardrails.escalate("risky_claim", f"Idea '{idea['title']}' contains: {', '.join(risky)}", "post", pid)
        created.append(pid)
    db.log_event("Loop Feeder", "fed_loop", {"ideas": created})
    return {"learning": plan.get("learning"), "idea_post_ids": created}


def brief_writer(status: dict, analysis: dict, calls: dict, revenue: dict, email: dict) -> str:
    top = analysis["posts"][0] if analysis.get("posts") else None
    waiting = db.query("SELECT trigger, detail FROM escalations WHERE status='open' ORDER BY id DESC LIMIT 5")
    facts = {"status_today": status, "top_post": top, "calls": calls, "revenue": revenue,
             "email_tip": email.get("tip"), "insights": analysis.get("insights"), "waiting_on_you": waiting}

    offline = "\n".join([
        f"☀️ {settings.brand_name} — morning brief",
        f"💰 ${revenue['revenue']:,.0f} from {revenue['sales']} sales (30d), "
        f"{revenue['attribution_rate']:.0%} traced to posts",
        f"📞 {calls.get('total', 0)} calls booked, show rate {calls.get('show_rate', 0):.0%}",
        f"🏆 Top post: {top['title']} → ${top['revenue']:,.0f}" if top else "🏆 No published posts yet",
        f"💡 {analysis.get('insights', {}).get('recommendations', [''])[0]}",
        f"⏳ Waiting on you: {status['waiting_on_you']}",
    ])
    text = llm.complete(
        "Brief Writer", _system("Brief Writer", "reporting"),
        f"Write today's WhatsApp morning brief from these facts:\n{json.dumps(facts, indent=1, default=str)}\n"
        "Plain text, emojis OK, max 120 words. Numbers first, then one recommendation, then what is "
        "waiting on the owner.", offline=offline)

    settings.brief_dir.mkdir(parents=True, exist_ok=True)
    (settings.brief_dir / f"morning-brief-{db.today()}.md").write_text(text, encoding="utf-8")
    return text


# ═════════════════════════════════ Inbox (event-driven) ═════════════════════

ANGRY = re.compile(r"\b(scam|fraud|refund|worst|angry|terrible|cheat|hate|useless|disappointed)\b", re.I)
HUMAN = re.compile(r"\b(real person|human|talk to (you|someone)|call me|speak to)\b", re.I)
BUYING = re.compile(r"\b(price|cost|how much|buy|join|sign ?up|enroll|plan|coaching|interested|pay)\b", re.I)


def message_triage(text: str, channel: str, sender: str) -> dict:
    """Classify an inbound message and draft a reply. Returns intent, sentiment, reply, escalate."""
    if ANGRY.search(text):
        intent = "angry"
    elif HUMAN.search(text):
        intent = "wants_person"
    elif BUYING.search(text):
        intent = "buying"
    else:
        intent = "question"
    default = {"intent": intent, "sentiment": "negative" if intent == "angry" else "neutral",
               "reply": "Thanks for reaching out! Reply PLAN and I'll send you the free 7-day starter plan 💪",
               "escalate": intent in {"angry", "wants_person"}}

    out = llm.complete_json(
        "Message Triage", _system("Comment & DM agent", "voice", "offer", "rules", "compliance"),
        f"Channel: {channel}\nFrom: {sender}\nMessage: {text}\n\nReturn JSON: intent (one of question, "
        "buying, wants_person, angry, spam), sentiment (positive|neutral|negative), reply (on-brand reply, "
        "max 2 sentences, follow offer.md CTAs), escalate (true if angry or wants a human).", default)

    # Guardrails in code: the model can't talk us out of escalating.
    if ANGRY.search(text) or out.get("intent") == "angry":
        out["intent"], out["escalate"] = "angry", True
    if HUMAN.search(text):
        out["escalate"] = True
    risky = guardrails.check_compliance(out.get("reply"))
    if risky:
        out["reply"], out["escalate"] = default["reply"], True
    return out


def lead_scorer(lead_id: int, context: str = "") -> int:
    lead = db.one("SELECT * FROM leads WHERE id=?", (lead_id,))
    if not lead:
        return 0
    heuristic = 20 + (30 if BUYING.search(context or "") else 0) + (20 if lead["source_post_id"] else 0) \
        + (20 if lead["call_at"] else 0) + (10 if lead["email"] else 0)
    out = llm.complete_json(
        "Lead Scorer", _system("Lead Scorer", "audience", "offer"),
        f"Lead: {json.dumps({k: lead[k] for k in ('name', 'source', 'stage', 'call_at')}, default=str)}\n"
        f"Latest message/context: {context}\n\nReturn JSON: score (0-100 buying intent), segment "
        "(cold|warm|hot), reason (one sentence).",
        {"score": min(heuristic, 100), "segment": "hot" if heuristic >= 80 else "warm", "reason": "heuristic"})
    try:
        score = max(0, min(100, int(out.get("score", heuristic))))
    except (TypeError, ValueError):
        score = min(heuristic, 100)
    db.update("leads", lead_id, score=score, segment=out.get("segment"), notes=out.get("reason"))
    guardrails.check_hot_lead(lead_id)
    return score
