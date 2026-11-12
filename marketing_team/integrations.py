"""External services behind small adapter interfaces.

Each adapter has a Mock implementation so the whole team runs end-to-end on a
laptop with zero accounts. To go live, implement the Real class for a service
and select it with an env var, e.g. MT_SOCIAL=real. Agents never call vendor
SDKs directly — they call tools, tools call adapters. That keeps vendor lock-in
and API keys out of prompts.

Diagram mapping:
  social   → TikTok, Instagram, YouTube, LinkedIn  (+ Buffer/Metricool scheduling)
  media    → Higgsfield (video), Canva/Midjourney (graphics), ElevenLabs (voice)
  crm      → HubSpot
  booking  → Calendly
  payments → Stripe
  email    → Beehiiv / Kit (ConvertKit)
  notify   → Slack / Telegram  (the "You approve" + interrupt channel)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import urllib.request
from typing import Protocol


# ── Interfaces ──────────────────────────────────────────────────────────────

class Social(Protocol):
    def publish(self, platform: str, caption: str, asset_url: str | None) -> str: ...
    def metrics(self, platform: str, external_id: str) -> dict: ...


class Media(Protocol):
    def make_video(self, script: str, voiceover: bool = True) -> str: ...
    def make_graphic(self, brief: str) -> str: ...


class Payments(Protocol):
    def payment_link(self, product: str, amount_usd: float, ref: str) -> str: ...


class Booking(Protocol):
    def booking_link(self, lead_ref: str) -> str: ...


class Email(Protocol):
    def send(self, segment: str, subject: str, body: str) -> int: ...


class Notify(Protocol):
    def send(self, text: str) -> None: ...


# ── Mock implementations (default) ──────────────────────────────────────────

def _id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:10]


class MockSocial:
    def publish(self, platform, caption, asset_url):
        return f"{platform}_{_id(caption)}"

    def metrics(self, platform, external_id):
        rnd = random.Random(external_id)  # stable per post
        views = int(rnd.lognormvariate(9.5, 1.1))
        return {"views": views, "likes": views // rnd.randint(15, 40),
                "comments": views // rnd.randint(200, 600), "shares": views // rnd.randint(300, 900),
                "saves": views // rnd.randint(100, 400)}


class MockMedia:
    def make_video(self, script, voiceover=True):
        return f"https://assets.local/video/{_id(script)}.mp4"

    def make_graphic(self, brief):
        return f"https://assets.local/img/{_id(brief)}.png"


class MockPayments:
    def payment_link(self, product, amount_usd, ref):
        return f"https://pay.local/{_id(product, ref)}?amount={amount_usd}"


class MockBooking:
    def booking_link(self, lead_ref):
        return f"https://book.local/15min?ref={lead_ref}"


class MockEmail:
    def send(self, segment, subject, body):
        return {"all": 1200, "hot": 40, "new": 300}.get(segment, 500)


class MockNotify:
    def send(self, text):
        print(f"[notify] {text}")


# ── Real implementations (fill in as you connect accounts) ──────────────────

class SlackNotify:
    """Real Slack incoming-webhook notifier. Set SLACK_WEBHOOK_URL."""

    def __init__(self, url: str):
        self.url = url

    def send(self, text):
        req = urllib.request.Request(self.url, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()


class TelegramNotify:
    """Real Telegram bot notifier. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."""

    def __init__(self, token: str, chat_id: str):
        self.token, self.chat_id = token, chat_id

    def send(self, text):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        req = urllib.request.Request(url, data=json.dumps({"chat_id": self.chat_id, "text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()


class StripePayments:
    """Real Stripe Payment Links. `pip install stripe` and set STRIPE_API_KEY."""

    def __init__(self, key: str):
        import stripe  # lazy import: optional dependency
        stripe.api_key = key
        self.stripe = stripe

    def payment_link(self, product, amount_usd, ref):
        price = self.stripe.Price.create(unit_amount=int(amount_usd * 100), currency="usd",
                                         product_data={"name": product})
        link = self.stripe.PaymentLink.create(line_items=[{"price": price.id, "quantity": 1}],
                                              metadata={"lead_ref": ref})
        return link.url


# ── Factory ─────────────────────────────────────────────────────────────────

def _notify() -> Notify:
    if os.getenv("SLACK_WEBHOOK_URL"):
        return SlackNotify(os.environ["SLACK_WEBHOOK_URL"])
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        return TelegramNotify(os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"])
    return MockNotify()


def _payments() -> Payments:
    if os.getenv("STRIPE_API_KEY"):
        return StripePayments(os.environ["STRIPE_API_KEY"])
    return MockPayments()


social: Social = MockSocial()      # TODO: TikTok/IG/YT/LinkedIn or Buffer/Metricool API
media: Media = MockMedia()         # TODO: Higgsfield / Canva / ElevenLabs APIs
booking: Booking = MockBooking()   # TODO: Calendly scheduling links API
email: Email = MockEmail()         # TODO: Beehiiv / Kit API
payments: Payments = _payments()
notify: Notify = _notify()
