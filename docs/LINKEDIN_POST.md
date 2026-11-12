# LinkedIn launch kit

## Post (copy, then edit in your own words)

My most viewed video got 390,000 views and made $0.
A video with half the views made $1,090.

Creators measure views. Businesses get paid in sales. And almost nobody can connect the two,
because views live in Instagram, calls in Calendly, and payments in Stripe.

So I built an AI marketing team that connects them 👇

🔗 Every post gets a tracking code that follows the customer: link → WhatsApp chat → booked call → payment
🤖 8 AI agents: Post Analyst, Revenue Tracker, Lead Scorer, Message Triage, Loop Feeder…
💬 Customers message on WhatsApp → AI replies on-brand, scores the lead, and pings ME when someone is angry or ready to buy
🔁 Every morning it analyses what made money, writes down the lesson, and queues tomorrow's content ideas for my approval
⚙️ n8n runs the automations, FastAPI + SQLite the backend, Streamlit the dashboard

The most important design decision: numbers come from SQL, judgement comes from the LLM.
The AI never does maths on revenue, so it can't make up numbers.

The whole stack has free tiers: Gemini/Groq, n8n, WhatsApp Cloud API, Cal.com, Streamlit Cloud.

🎥 Demo below · 💻 Code: <your GitHub link> · 📊 Live dashboard: <your Streamlit link>

I'm a CS student at FAST Karachi learning GenAI and agentic systems. If you run a coaching or
creator business and want this for your numbers, DM me.

#AgenticAI #n8n #GenAI #WhatsApp #Python #BuildInPublic #FASTNUCES

## 60-second demo video (record your screen, OBS is free)

1. **0–8s**: dashboard. Point at "Filming my morning: 390K views → $0".
2. **8–20s**: phone. Send a WhatsApp message *"How much is coaching? ref:p1"*. The bot replies.
3. **20–30s**: dashboard. The new lead appears, scored and linked to "Zone 2 myths".
4. **30–40s**: send *"this is a scam"*. You get a WhatsApp alert and it shows up in "Waiting on you".
5. **40–55s**: click *Run daily loop*. The morning brief arrives on WhatsApp, and a new content idea waits for approval.
6. **55–60s**: n8n canvas with the workflows. End on the GitHub link.

## Portfolio / resume line

> **AI Marketing Analytics Agents** (Python, FastAPI, n8n, WhatsApp Cloud API, Gemini, MCP, Streamlit)
> Multi-agent system that attributes revenue to social posts through UTM/WhatsApp tracking,
> triages inbound WhatsApp leads with LLM scoring and code-enforced guardrails, and runs a
> daily self-improving analytics loop. 8 agents, 4 n8n workflows, tested with pytest.
