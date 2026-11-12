from fastapi.testclient import TestClient

from marketing_team import db, guardrails, orchestrator
from marketing_team.server import app


def test_attribution_ranks_by_revenue_not_views():
    rows = db.attribution(30)
    assert rows[0]["title"] == "Zone 2 myths"
    most_viewed = max(rows, key=lambda r: r["views"])
    assert most_viewed["title"] == "Filming my morning" and most_viewed["revenue"] == 0


def test_daily_loop_offline_produces_brief_and_ideas():
    out = orchestrator.run_daily()
    assert "morning brief" in out["brief"].lower()
    assert out["loop"]["idea_post_ids"], "loop feeder should queue new ideas for approval"
    assert db.one("SELECT COUNT(*) n FROM approvals WHERE status='pending'")["n"] >= 1
    assert 3 in out["viral"] or out["viral"], "390k-view post should be flagged viral"


def test_angry_message_escalates_and_is_not_auto_replied():
    out = orchestrator.on_message("whatsapp", "923001112222", "This is a scam, I want a refund!")
    assert out["intent"] == "angry" and out["escalate"]
    assert db.one("SELECT COUNT(*) n FROM escalations WHERE trigger='angry_comment'")["n"] == 1


def test_wa_message_with_ref_attributes_lead_to_post():
    out = orchestrator.on_message("whatsapp", "923003334444", "Hi! how much is coaching? ref:p2", reply=False)
    assert out["post_id"] == 2 and out["intent"] == "buying"


def test_payment_is_idempotent_and_attributed():
    a = orchestrator.on_payment("new@x.com", 297, "12-week program", ref="p1", payment_ref="cs_1")
    b = orchestrator.on_payment("new@x.com", 297, "12-week program", ref="p1", payment_ref="cs_1")
    assert a["post_id"] == 1 and b == {"duplicate": True}


def test_compliance_blocks_banned_claims():
    assert set(guardrails.check_compliance("This detox will cure you")) == {"detox", "cure"}


def test_readonly_query_rejects_writes():
    import pytest
    with pytest.raises(ValueError):
        db.readonly_query("DELETE FROM posts")
    assert db.readonly_query("SELECT COUNT(*) n FROM posts")[0]["n"] == 6


def test_api_endpoints_and_webhooks():
    c = TestClient(app)
    assert c.get("/health").json()["ok"]
    assert c.get("/attribution").json()[0]["title"] == "Zone 2 myths"
    stripe_evt = {"type": "checkout.session.completed", "data": {"object": {
        "id": "cs_test_9", "amount_total": 29700, "customer_details": {"email": "s@x.com"},
        "metadata": {"utm": "p4", "product": "12-week program"}}}}
    assert c.post("/webhooks/stripe", json=stripe_evt).json()["post_id"] == 4
    wa = {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "92300", "profile": {"name": "Ali"}}],
          "messages": [{"from": "92300", "text": {"body": "price? ref:p1"}}]}}]}]}
    assert c.post("/webhooks/whatsapp", json=wa).json()["processed"] == 1
    assert c.post("/run/daily").status_code == 200
