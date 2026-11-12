"""Realistic demo data so the dashboard looks alive on first run (and in your demo video)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from . import db

POSTS = [
    # title, platform, format, views, leads, calls, sales
    ("Zone 2 myths", "instagram", "reel", 212_000, 38, 9, 4),
    ("Meal prep in 20 min", "instagram", "carousel", 48_000, 22, 6, 3),
    ("Filming my morning", "tiktok", "reel", 390_000, 6, 1, 0),
    ("5 stretches after a run", "instagram", "carousel", 31_000, 14, 4, 2),
    ("Walk 30 min a day", "youtube", "short", 64_000, 11, 2, 1),
    ("Why you're always tired", "linkedin", "carousel", 12_000, 9, 3, 2),
]
NAMES = ["Ayesha Khan", "Bilal Ahmed", "Sara Malik", "Hamza Ali", "Zara Sheikh", "Usman Tariq",
         "Fatima Noor", "Ali Raza", "Hira Qureshi", "Omar Farooq", "Mahnoor Iqbal", "Saad Javed"]


def _ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def seed(reset: bool = True) -> dict:
    db.init_db()
    if reset:
        with db.connect() as c:
            for t in ("sales", "leads", "emails", "approvals", "escalations", "events", "runs", "posts"):
                c.execute(f"DELETE FROM {t}")
            c.execute("DELETE FROM sqlite_sequence")  # restart ids so demo refs p1..p6 are stable
    rnd = random.Random(42)
    n_leads = 0
    for i, (title, platform, fmt, views, leads, calls, sales) in enumerate(POSTS):
        published = _ago(rnd.uniform(3, 25))
        pid = db.insert("posts", title=title, platform=platform, format=fmt, status="published",
                        published_at=published, views=views, likes=views // 25, comments=views // 400,
                        shares=views // 600, saves=views // 150, created_by="Post Writer",
                        created_at=published)
        db.update("posts", pid, utm=f"p{pid}")
        for j in range(leads):
            n_leads += 1
            name = rnd.choice(NAMES)
            booked = j < calls
            lid = db.insert("leads", name=name, email=f"{name.split()[0].lower()}{n_leads}@example.com",
                            source=rnd.choice(["whatsapp", "dm", "comment", "form"]), source_post_id=pid,
                            score=rnd.randint(55, 95) if booked else rnd.randint(10, 60),
                            stage="customer" if j < sales else ("call_done" if booked and rnd.random() < 0.7
                                                                    else "call_booked" if booked else "nurturing"),
                            call_at=_ago(rnd.uniform(0, 10)) if booked else None, created_at=_ago(rnd.uniform(0, 20)))
            if j < sales:
                product, amount = rnd.choice([("12-week program", 297), ("1:1 coaching", 199)])
                db.insert("sales", lead_id=lid, amount_usd=amount, product=product, status="paid",
                          payment_ref=f"cs_demo_{lid}", created_at=_ago(rnd.uniform(0, 10)))
    # Some sales can't be traced (word of mouth, untagged links) — real data looks like this.
    for name, amount in [("Walk-in Client", 297), ("Referral Client", 199)]:
        lid = db.insert("leads", name=name, email=f"{name.split()[0].lower()}@example.com", source="referral",
                        stage="customer", score=90, created_at=_ago(rnd.uniform(1, 15)))
        db.insert("sales", lead_id=lid, amount_usd=amount, product="12-week program" if amount == 297
                  else "1:1 coaching", payment_ref=f"cs_demo_ref_{lid}", created_at=_ago(rnd.uniform(0, 10)))
    for subj, sent, opens, clicks in [("The Zone 2 mistake 90% make", 1200, 540, 96),
                                      ("Your 20-min meal prep plan", 1180, 410, 52),
                                      ("Quick question", 1150, 610, 31)]:
        db.insert("emails", kind="newsletter", segment="all", subject=subj, status="sent",
                  sent_count=sent, opens=opens, clicks=clicks, created_at=_ago(rnd.uniform(1, 20)))
    return {"posts": len(POSTS), "leads": n_leads}


if __name__ == "__main__":
    print(seed())
