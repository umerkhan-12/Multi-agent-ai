"""Orchestrator: the daily loop + event routing.

Attribution model (how a sale is traced to a post):
  every post has a short code `utm` like "p12". It travels in
    • link UTMs           → ?utm_content=p12   (Calendly / landing page / Stripe metadata)
    • click-to-WhatsApp   → wa.me/<num>?text=Hi%20ref:p12
    • lead-form hidden field
  lead.source_post_id is set from that code; sales link to leads by email/phone.
"""
from __future__ import annotations

import re
from typing import Any

from . import agents, db, guardrails, integrations

REF = re.compile(r"\b(?:ref[:=\s]*)?(p\d{1,6})\b", re.I)


# ── helpers ─────────────────────────────────────────────────────────────────

def post_id_from_code(*candidates: str | None) -> int | None:
    for c in candidates:
        if not c:
            continue
        m = REF.search(str(c))
        if m:
            row = db.one("SELECT id FROM posts WHERE lower(utm)=lower(?)", (m.group(1),))
            if row:
                return row["id"]
    return None


def upsert_lead(*, email: str | None = None, handle: str | None = None, name: str | None = None,
                source: str = "unknown", post_id: int | None = None, **extra: Any) -> int:
    email = (email or "").strip().lower() or None
    row = None
    if email:
        row = db.one("SELECT * FROM leads WHERE email=?", (email,))
    if not row and handle:
        row = db.one("SELECT * FROM leads WHERE handle=?", (handle,))
    if row:
        changes = {k: v for k, v in {"name": name or row["name"], "email": email or row["email"],
                                     "handle": handle or row["handle"], **extra}.items() if v is not None}
        if post_id and not row["source_post_id"]:      # first touch wins
            changes["source_post_id"] = post_id
        db.update("leads", row["id"], **changes)
        return row["id"]
    return db.insert("leads", email=email, handle=handle, name=name, source=source,
                     source_post_id=post_id, **extra)


# ── daily loop (n8n Schedule Trigger → POST /run/daily) ─────────────────────

def run_daily(days: int = 30) -> dict:
    db.init_db()
    analysis = agents.post_analyst(days)
    calls = agents.call_tracker(days)
    revenue = agents.revenue_tracker(days)
    email = agents.email_analyst(days)
    fed = agents.loop_feeder(analysis)
    brief = agents.brief_writer(db.status_today(), analysis, calls, revenue, email)
    try:
        integrations.notify.send(brief)
    except Exception as exc:
        db.log_event("orchestrator", "notify_failed", str(exc))
    return {"brief": brief, "insights": analysis["insights"], "viral": analysis["viral"],
            "calls": calls, "revenue": revenue, "email_tip": email["tip"], "loop": fed}


# ── events ──────────────────────────────────────────────────────────────────

def on_message(channel: str, sender: str, text: str, name: str | None = None,
               post_ref: str | None = None, reply: bool = True) -> dict:
    """WhatsApp message / DM / comment → lead + triage + reply/escalation."""
    post_id = post_id_from_code(post_ref, text)
    lead_id = upsert_lead(handle=sender, name=name, source=channel, post_id=post_id)
    tri = agents.message_triage(text, channel, sender)
    db.log_event("Message Triage", "triaged", {"lead": lead_id, **tri})

    if tri.get("escalate"):
        trig = "angry_comment" if tri.get("intent") == "angry" else "customer_wants_person"
        guardrails.escalate(trig, f"{name or sender} on {channel}: “{text[:160]}”", "lead", lead_id)
    elif reply and tri.get("intent") != "spam":
        if channel == "whatsapp" and integrations.whatsapp:
            try:
                integrations.whatsapp.send_text(sender, tri["reply"])
            except Exception as exc:
                db.log_event("Message Triage", "reply_failed", str(exc))
        db.log_event("Message Triage", "reply_sent", {"lead": lead_id, "reply": tri["reply"]})

    score = agents.lead_scorer(lead_id, text)
    return {"lead_id": lead_id, "post_id": post_id, "score": score, **tri}


def on_lead_form(name: str | None, email: str | None, phone: str | None = None,
                 utm: str | None = None, source: str = "form", message: str = "") -> dict:
    post_id = post_id_from_code(utm)
    lead_id = upsert_lead(email=email, handle=phone, name=name, source=source, post_id=post_id)
    return {"lead_id": lead_id, "post_id": post_id, "score": agents.lead_scorer(lead_id, message)}


def on_call_booked(email: str, name: str | None, start_time: str, utm: str | None = None) -> dict:
    """Calendly invitee.created (or any booking tool)."""
    post_id = post_id_from_code(utm)
    lead_id = upsert_lead(email=email, name=name, source="booking", post_id=post_id,
                          call_at=start_time, stage="call_booked")
    db.log_event("Call Tracker", "call_booked", {"lead": lead_id, "post": post_id, "at": start_time})
    return {"lead_id": lead_id, "post_id": post_id, "score": agents.lead_scorer(lead_id, "booked a call")}


def on_payment(email: str | None, amount_usd: float, product: str | None = None,
               ref: str | None = None, payment_ref: str | None = None, phone: str | None = None) -> dict:
    """Stripe checkout.session.completed (or JazzCash/Easypaisa via n8n)."""
    if payment_ref and db.one("SELECT id FROM sales WHERE payment_ref=?", (payment_ref,)):
        return {"duplicate": True}  # webhooks retry; stay idempotent
    post_id = post_id_from_code(ref)
    lead_id = upsert_lead(email=email, handle=phone, source="payment", post_id=post_id, stage="customer")
    sale_id = db.insert("sales", lead_id=lead_id, amount_usd=float(amount_usd), product=product,
                        status="paid", payment_ref=payment_ref)
    db.log_event("Revenue Tracker", "sale", {"sale": sale_id, "lead": lead_id, "amount": amount_usd})
    integrations.notify.send(f"💰 New sale: ${amount_usd:,.0f} {product or ''} from {email or phone}")
    return {"sale_id": sale_id, "lead_id": lead_id, "post_id": post_id}


def on_unsubscribe(email: str) -> dict:
    guardrails.handle_unsubscribe(email.strip().lower())
    return {"ok": True}


# ── human decisions ─────────────────────────────────────────────────────────

def decide_approval(approval_id: int, approve: bool, feedback: str = "") -> dict:
    a = db.one("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not a or a["status"] != "pending":
        return {"ok": False, "error": "not found or already decided"}
    status = "approved" if approve else "rejected"
    db.update("approvals", approval_id, status=status, decided_at=db.now(), feedback=feedback)
    if a["kind"] == "post" and a["ref_id"]:
        db.update("posts", a["ref_id"], status=status)
    db.log_event("human", f"approval_{status}", {"approval": approval_id, "feedback": feedback})
    return {"ok": True, "status": status}


def resolve_escalation(esc_id: int) -> dict:
    db.update("escalations", esc_id, status="resolved")
    return {"ok": True}


# ── normalisers for raw vendor webhooks ─────────────────────────────────────

def parse_whatsapp(payload: dict) -> list[dict]:
    """Meta WhatsApp Cloud API webhook → [{sender, name, text}]."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                text = (m.get("text") or {}).get("body") or (m.get("button") or {}).get("text") or ""
                if text:
                    out.append({"sender": m.get("from"), "name": names.get(m.get("from")), "text": text})
    return out


def parse_stripe(event: dict) -> dict | None:
    if event.get("type") != "checkout.session.completed":
        return None
    o = event["data"]["object"]
    md = o.get("metadata") or {}
    return {"email": (o.get("customer_details") or {}).get("email"),
            "amount_usd": (o.get("amount_total") or 0) / 100,
            "product": md.get("product"), "ref": md.get("utm") or o.get("client_reference_id"),
            "payment_ref": o.get("id")}


def parse_calendly(event: dict) -> dict | None:
    if event.get("event") != "invitee.created":
        return None
    p = event["payload"]
    return {"email": p.get("email"), "name": p.get("name"),
            "start_time": (p.get("scheduled_event") or {}).get("start_time") or db.now(),
            "utm": (p.get("tracking") or {}).get("utm_content")}
