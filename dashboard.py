"""Analytics Loop dashboard — "What you see every morning".

Run locally : streamlit run dashboard.py
Deploy free : Streamlit Community Cloud → main file: dashboard.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import streamlit as st  # noqa: E402

# Mirror Streamlit Cloud secrets into env before importing the package.
try:
    for k, v in st.secrets.items():
        if isinstance(v, str):
            os.environ.setdefault(k, v)
except Exception:
    pass

from marketing_team import agents, db, orchestrator, seed  # noqa: E402
from marketing_team.config import settings  # noqa: E402

st.set_page_config(page_title="AI Marketing Team", page_icon="📈", layout="wide")
db.init_db()
if not db.one("SELECT id FROM posts LIMIT 1"):
    seed.seed()  # first run on a fresh deploy → demo data

# ── header ──────────────────────────────────────────────────────────────────
st.title("📈 The Analytics Loop")
st.caption(f"{settings.brand_name} · which posts brought calls and sales · "
           f"LLM: **{settings.provider}** · {len(agents.ROSTER)} agents")

days = st.sidebar.select_slider("Window", options=[7, 14, 30, 90], value=30)
if st.sidebar.button("▶ Run daily loop now", use_container_width=True):
    with st.spinner("Agents working…"):
        st.session_state["last_run"] = orchestrator.run_daily(days)
if st.sidebar.button("↺ Reset demo data", use_container_width=True):
    seed.seed()
    st.session_state.pop("last_run", None)
    st.rerun()

# ── KPI row ─────────────────────────────────────────────────────────────────
rows = db.attribution(days)
rev = agents.revenue_tracker(days)
calls = agents.call_tracker(days)
status = db.status_today()
c = st.columns(5)
c[0].metric("Revenue", f"${rev['revenue']:,.0f}", f"{rev['attribution_rate']:.0%} traced to posts")
c[1].metric("Sales", rev["sales"])
c[2].metric("Calls booked", calls.get("total", 0), f"show rate {calls.get('show_rate', 0):.0%}")
c[3].metric("Leads", sum(r["leads"] for r in rows))
c[4].metric("Waiting on you", status["waiting_on_you"])

# ── attribution table ───────────────────────────────────────────────────────
st.subheader("Which posts brought calls and sales")
if rows:
    max_rev = max(r["revenue"] for r in rows) or 1
    st.dataframe(
        [{"Post": r["title"], "Platform": r["platform"], "Format": r["format"], "Views": r["views"],
          "Leads": r["leads"], "Calls": r["calls"], "Sales": r["sales"], "Revenue": r["revenue"],
          "$ / 1k views": round(r["revenue"] / r["views"] * 1000, 2) if r["views"] else 0}
         for r in rows],
        use_container_width=True, hide_index=True,
        column_config={"Revenue": st.column_config.ProgressColumn(format="$%.0f", min_value=0,
                                                                  max_value=float(max_rev)),
                       "Views": st.column_config.NumberColumn(format="%d")},
    )
    top_views = max(rows, key=lambda r: r["views"])
    if top_views is not rows[0]:
        st.info(f"🔎 Most viewed: **{top_views['title']}** ({top_views['views']:,} views → "
                f"${top_views['revenue']:,.0f}). Top earner: **{rows[0]['title']}** "
                f"(${rows[0]['revenue']:,.0f}). Views ≠ revenue.")
else:
    st.write("No published posts in this window.")

left, right = st.columns([3, 2])

# ── morning brief + insights ────────────────────────────────────────────────
with left:
    st.subheader("☀️ Morning brief")
    run = st.session_state.get("last_run")
    if run:
        st.text(run["brief"])
        ins = run["insights"]
        st.markdown(f"**Winning pattern:** {ins.get('winning_pattern')}")
        st.markdown(f"**Losing pattern:** {ins.get('losing_pattern')}")
        for r in ins.get("recommendations", []):
            st.markdown(f"- {r}")
        st.markdown(f"**Email:** {run['email_tip']}")
    else:
        st.caption("Click **Run daily loop now** in the sidebar (n8n does this every morning at 7:00).")

    st.subheader("💬 Try the inbox (WhatsApp / DM / comment)")
    with st.form("msg"):
        text = st.text_input("Incoming message", "Hi! How much is the 12-week program? ref:p1")
        cc = st.columns(2)
        channel = cc[0].selectbox("Channel", ["whatsapp", "instagram", "tiktok", "linkedin"])
        sender = cc[1].text_input("Sender", "923001234567")
        if st.form_submit_button("Send to agents"):
            st.json(orchestrator.on_message(channel, sender, text, reply=False))

# ── human handoff ───────────────────────────────────────────────────────────
with right:
    st.subheader("🙋 Waiting on you")
    for e in db.query("SELECT * FROM escalations WHERE status='open' ORDER BY id DESC LIMIT 15"):
        with st.container(border=True):
            st.markdown(f"**{e['trigger'].replace('_', ' ').title()}** · {e['severity']}")
            st.caption(e["detail"])
            if st.button("Resolve", key=f"esc{e['id']}"):
                orchestrator.resolve_escalation(e["id"])
                st.rerun()
    for a in db.query("SELECT * FROM approvals WHERE status='pending' ORDER BY id DESC LIMIT 10"):
        with st.container(border=True):
            st.markdown(f"**Approve {a['kind']}?** · from {a['requested_by']}")
            st.caption(a["summary"])
            b = st.columns(2)
            if b[0].button("✅ Approve", key=f"ok{a['id']}"):
                orchestrator.decide_approval(a["id"], True)
                st.rerun()
            if b[1].button("❌ Reject", key=f"no{a['id']}"):
                orchestrator.decide_approval(a["id"], False)
                st.rerun()

    st.subheader("🤖 Agents")
    st.dataframe([{"Agent": a.name, "Team": a.department, "When": a.trigger, "Does": a.does}
                  for a in agents.ROSTER], hide_index=True, use_container_width=True)

with st.expander("Activity log"):
    st.dataframe(db.query("SELECT created_at, agent, action, payload FROM events ORDER BY id DESC LIMIT 50"),
                 use_container_width=True, hide_index=True)
