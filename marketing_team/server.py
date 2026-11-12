"""FastAPI service. n8n workflows and vendor webhooks talk to the team through here.

Run:  uvicorn marketing_team.server:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import agents, db, orchestrator
from .config import settings

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="AI Marketing Team — Analytics Loop", version="1.0.0", lifespan=lifespan)


def require_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Internal endpoints (n8n, dashboard) need MT_API_KEY when it is set."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(401, "Invalid or missing X-API-Key")


# ── models ──────────────────────────────────────────────────────────────────

class Message(BaseModel):
    channel: str = "instagram"      # whatsapp | instagram | tiktok | youtube | linkedin
    sender: str
    text: str
    name: Optional[str] = None
    post_ref: Optional[str] = None  # e.g. "p12"


class LeadForm(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    utm: Optional[str] = None
    source: str = "form"
    message: str = ""


class Booking(BaseModel):
    email: str
    name: Optional[str] = None
    start_time: str
    utm: Optional[str] = None


class Payment(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    amount_usd: float
    product: Optional[str] = None
    ref: Optional[str] = None
    payment_ref: Optional[str] = None


class Decision(BaseModel):
    approve: bool
    feedback: str = ""


# ── read endpoints ──────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "llm_provider": settings.provider}


@app.get("/status", dependencies=[Depends(require_key)])
def status():
    return db.status_today()


@app.get("/attribution", dependencies=[Depends(require_key)])
def attribution(days: int = 30):
    return db.attribution(days)


@app.get("/agents")
def roster():
    return [a.__dict__ for a in agents.ROSTER]


@app.get("/inbox", dependencies=[Depends(require_key)])
def inbox():
    return {"approvals": db.query("SELECT * FROM approvals WHERE status='pending' ORDER BY id DESC"),
            "escalations": db.query("SELECT * FROM escalations WHERE status='open' ORDER BY id DESC")}


# ── actions ─────────────────────────────────────────────────────────────────

@app.post("/run/daily", dependencies=[Depends(require_key)])
def run_daily(days: int = 30):
    return orchestrator.run_daily(days)


@app.post("/approvals/{approval_id}", dependencies=[Depends(require_key)])
def decide(approval_id: int, d: Decision):
    return orchestrator.decide_approval(approval_id, d.approve, d.feedback)


@app.post("/escalations/{esc_id}/resolve", dependencies=[Depends(require_key)])
def resolve(esc_id: int):
    return orchestrator.resolve_escalation(esc_id)


# ── normalised events (n8n sends these) ─────────────────────────────────────

@app.post("/events/message", dependencies=[Depends(require_key)])
def ev_message(m: Message):
    return orchestrator.on_message(m.channel, m.sender, m.text, m.name, m.post_ref)


@app.post("/events/lead", dependencies=[Depends(require_key)])
def ev_lead(f: LeadForm):
    return orchestrator.on_lead_form(f.name, f.email, f.phone, f.utm, f.source, f.message)


@app.post("/events/booking", dependencies=[Depends(require_key)])
def ev_booking(b: Booking):
    return orchestrator.on_call_booked(b.email, b.name, b.start_time, b.utm)


@app.post("/events/payment", dependencies=[Depends(require_key)])
def ev_payment(p: Payment):
    return orchestrator.on_payment(p.email, p.amount_usd, p.product, p.ref, p.payment_ref, p.phone)


@app.post("/events/unsubscribe", dependencies=[Depends(require_key)])
def ev_unsub(email: str):
    return orchestrator.on_unsubscribe(email)


# ── raw vendor webhooks (point the vendor straight here, no n8n needed) ─────

@app.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def wa_verify(mode: str = Query(alias="hub.mode", default=""),
              token: str = Query(alias="hub.verify_token", default=""),
              challenge: str = Query(alias="hub.challenge", default="")):
    if mode == "subscribe" and token and token == os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return challenge
    raise HTTPException(403, "verification failed")


@app.post("/webhooks/whatsapp")
async def wa_inbound(request: Request):
    results = [orchestrator.on_message("whatsapp", m["sender"], m["text"], m["name"])
               for m in orchestrator.parse_whatsapp(await request.json())]
    return {"processed": len(results)}


@app.post("/webhooks/stripe")
async def stripe_hook(request: Request, stripe_signature: Optional[str] = Header(default=None)):
    body = await request.body()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if secret:
        import stripe
        try:
            event = stripe.Webhook.construct_event(body, stripe_signature, secret)
        except Exception:
            raise HTTPException(400, "bad signature")
        event = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    else:
        event = await request.json()
    parsed = orchestrator.parse_stripe(event)
    return orchestrator.on_payment(**parsed) if parsed else {"ignored": event.get("type")}


@app.post("/webhooks/calendly")
async def calendly_hook(request: Request):
    parsed = orchestrator.parse_calendly(await request.json())
    return orchestrator.on_call_booked(**parsed) if parsed else {"ignored": True}
