"""
Streamlit Web UI — Multi-Agent AI System
Run locally : streamlit run app.py
Deploy      : Streamlit Community Cloud (reads keys from st.secrets)
"""
import sys, os

# ── Make sure project root is on sys.path ─────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as st
from dotenv import load_dotenv

# ── Load API keys ──────────────────────────────────────────────────────────────
# Priority: Streamlit Cloud secrets (production) → .env file (local dev)
load_dotenv()   # loads .env if present; safe no-op if missing on Cloud

_SECRET_KEYS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_MODEL",
]
# On Streamlit Community Cloud, st.secrets are injected via the dashboard.
# We mirror them into os.environ so every agent picks them up automatically.
try:
    for _k in _SECRET_KEYS:
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = st.secrets[_k]
except Exception:
    pass   # st.secrets not available locally without secrets.toml — that's fine

from orchestrator.orchestrator import Orchestrator, OrchestratorResult

# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Multi-Agent AI System",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .agent-card {
        background: #1e1e2e;
        border: 1px solid #44475a;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .agent-header {
        font-size: 1.1rem;
        font-weight: bold;
        margin-bottom: 6px;
    }
    .meta-badge {
        display: inline-block;
        background: #282a36;
        border: 1px solid #6272a4;
        border-radius: 6px;
        padding: 2px 8px;
        font-size: 0.75rem;
        margin-right: 6px;
        color: #8be9fd;
    }
    .final-answer-box {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-left: 4px solid #50fa7b;
        border-radius: 8px;
        padding: 20px;
    }
    .error-badge {
        background: #ff5555;
        color: white;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.75rem;
    }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — Configuration
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuration")
    st.markdown("---")

    st.subheader("🔑 API Keys")
    st.caption("Keys are read from your `.env` file automatically. Override below if needed.")

    with st.expander("Override API Keys (optional)"):
        anthropic_key = st.text_input("Anthropic (Claude)",  type="password",
                                       value=os.getenv("ANTHROPIC_API_KEY", ""))
        openai_key    = st.text_input("OpenAI (GPT-4)",       type="password",
                                       value=os.getenv("OPENAI_API_KEY", ""))
        google_key    = st.text_input("Google (Gemini)",       type="password",
                                       value=os.getenv("GOOGLE_API_KEY", ""))
        groq_key      = st.text_input("Groq (Llama)",          type="password",
                                       value=os.getenv("GROQ_API_KEY", ""))

        if st.button("💾 Apply Keys"):
            if anthropic_key: os.environ["ANTHROPIC_API_KEY"] = anthropic_key
            if openai_key:    os.environ["OPENAI_API_KEY"]    = openai_key
            if google_key:    os.environ["GOOGLE_API_KEY"]    = google_key
            if groq_key:      os.environ["GROQ_API_KEY"]      = groq_key
            st.success("Keys applied for this session!")
            st.cache_resource.clear()

    st.markdown("---")
    st.subheader("🤖 Active Agents")

    agent_toggles = {
        "claude": st.checkbox("🔵 Claude (Research)",    value=bool(os.getenv("ANTHROPIC_API_KEY"))),
        "gpt":    st.checkbox("🟢 GPT-4 (Creative)",     value=bool(os.getenv("OPENAI_API_KEY"))),
        "gemini": st.checkbox("🟡 Gemini (Fact-Check)",  value=bool(os.getenv("GOOGLE_API_KEY"))),
        "llama":  st.checkbox("🟠 Llama (Code)",         value=bool(os.getenv("GROQ_API_KEY"))),
    }

    selected_agents = [k for k, v in agent_toggles.items() if v]

    st.markdown("---")
    st.subheader("📝 Example Questions")
    examples = [
        "Explain how transformers work in AI",
        "Write a Python web scraper with error handling",
        "What are the latest facts about climate change?",
        "Create a business plan for an AI startup",
        "How does a binary search tree work? Include code.",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["query_input"] = ex

    st.markdown("---")
    st.markdown("**Free API Links:**")
    st.markdown("- [Anthropic](https://console.anthropic.com)")
    st.markdown("- [OpenAI](https://platform.openai.com)")
    st.markdown("- [Google AI](https://ai.google.dev)")
    st.markdown("- [Groq](https://console.groq.com)")


# ──────────────────────────────────────────────────────────────────────────────
# Cache orchestrator so it doesn't reload on every interaction
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_orchestrator(agents_key: str):
    agents = agents_key.split(",") if agents_key else []
    return Orchestrator(available_agents=agents or None)


# ──────────────────────────────────────────────────────────────────────────────
# Main UI
# ──────────────────────────────────────────────────────────────────────────────
st.title("🤖 Multi-Agent AI System")
st.markdown(
    "Ask a complex question — **Claude**, **GPT-4**, **Gemini**, and **Llama** "
    "work together to give you the best possible answer."
)

col1, col2, col3, col4 = st.columns(4)
agent_info = [
    (col1, "🔵", "Claude",  "Research & Analysis",       "#6272a4"),
    (col2, "🟢", "GPT-4",   "Creative Generation",        "#50fa7b"),
    (col3, "🟡", "Gemini",  "Fact-Checking",              "#f1fa8c"),
    (col4, "🟠", "Llama",   "Code Generation",            "#ffb86c"),
]
for col, icon, name, role, color in agent_info:
    with col:
        active = name.lower().split("-")[0].replace("4","") in selected_agents or \
                 name.lower().replace("-4","").replace("pt","pt") in selected_agents
        # simpler check:
        key_map = {"Claude": "claude", "GPT-4": "gpt", "Gemini": "gemini", "Llama": "llama"}
        is_active = key_map[name] in selected_agents
        status = "🟢 Active" if is_active else "🔴 Disabled"
        st.metric(label=f"{icon} {name}", value=role, delta=status)

st.markdown("---")

# ── Query input ───────────────────────────────────────────────────────────────
query = st.text_area(
    "💬 Ask your question",
    value=st.session_state.get("query_input", ""),
    placeholder="e.g. 'How does quantum computing work? Include a code simulation.'",
    height=120,
    key="main_query",
)

run_btn = st.button("🚀 Run Multi-Agent Analysis", type="primary", use_container_width=True)

# ── History ───────────────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state["history"] = []

# ──────────────────────────────────────────────────────────────────────────────
# Run the pipeline
# ──────────────────────────────────────────────────────────────────────────────
if run_btn and query.strip():
    if not selected_agents:
        st.error("⚠️ No agents selected or enabled. Please set API keys and enable at least one agent.")
    else:
        # Build / retrieve orchestrator
        agents_key = ",".join(sorted(selected_agents))
        orchestrator = get_orchestrator(agents_key)

        # Progress UI
        progress_bar  = st.progress(0, text="Initialising agents...")
        status_holder = st.empty()

        status_holder.info(f"🔄 Running {len(selected_agents)} agent(s) in parallel...")
        progress_bar.progress(20, text="Agents working...")

        with st.spinner("Gathering expert perspectives..."):
            result: OrchestratorResult = orchestrator.run(query.strip())

        progress_bar.progress(80, text="Synthesising answers...")
        progress_bar.progress(100, text="Done!")
        status_holder.empty()
        progress_bar.empty()

        # Store in history
        st.session_state["history"].insert(0, result)

        # ── Final Answer ──────────────────────────────────────────────────────
        st.markdown("## ✨ Final Synthesised Answer")
        st.markdown(
            f'<div class="final-answer-box">{result.final_answer}</div>',
            unsafe_allow_html=True,
        )

        # ── Metrics row ───────────────────────────────────────────────────────
        st.markdown("---")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("⚡ Total Latency",  f"{result.total_latency_seconds}s")
        m2.metric("🪙 Total Tokens",   f"{result.total_tokens:,}")
        m3.metric("💵 Est. Cost",      f"${result.total_cost_usd:.6f}")
        m4.metric("🤖 Agents Used",    len(result.agents_used))

        # ── Per-agent outputs ─────────────────────────────────────────────────
        st.markdown("## 📋 Individual Agent Outputs")
        tabs = st.tabs([
            f"{'✅' if r.success else '❌'} {r.agent_name}" for r in result.agent_responses
        ])
        for tab, r in zip(tabs, result.agent_responses):
            with tab:
                col_l, col_r = st.columns([3, 1])
                with col_r:
                    st.markdown(f"**Model:** `{r.model}`")
                    st.markdown(f"**Role:** {r.role}")
                    st.markdown(f"**Latency:** {r.latency_seconds}s")
                    st.markdown(f"**Tokens:** {r.tokens_used:,}")
                    st.markdown(f"**Cost:** ${r.cost_usd:.6f}")
                with col_l:
                    if r.success:
                        st.markdown(r.content)
                    else:
                        st.error(f"Agent failed: {r.error}")

        # ── Errors ────────────────────────────────────────────────────────────
        if result.errors:
            st.warning("⚠️ Some agents encountered errors:")
            for err in result.errors:
                st.code(err)

elif run_btn and not query.strip():
    st.warning("Please enter a question first.")

# ──────────────────────────────────────────────────────────────────────────────
# History panel
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state["history"]:
    st.markdown("---")
    with st.expander(f"📜 Query History ({len(st.session_state['history'])} queries)"):
        for i, past in enumerate(st.session_state["history"]):
            with st.container():
                st.markdown(f"**Q{i+1}:** {past.user_query}")
                st.caption(
                    f"Agents: {', '.join(past.agents_used)} | "
                    f"Tokens: {past.total_tokens:,} | "
                    f"Cost: ${past.total_cost_usd:.6f} | "
                    f"Latency: {past.total_latency_seconds}s"
                )
                if st.button(f"View Answer #{i+1}", key=f"hist_{i}"):
                    st.markdown(past.final_answer)
                st.divider()
