"""
Prompt Engine — Builds specialised prompts for each agent role and synthesis.
Good prompt engineering significantly improves output quality.
"""
from __future__ import annotations
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base_agent import AgentResponse


# ──────────────────────────────────────────────────────────────────────────────
# Per-agent role instructions (few-shot style)
# ──────────────────────────────────────────────────────────────────────────────

AGENT_ROLE_PROMPTS: dict[str, str] = {
    "claude": """You are the RESEARCH & ANALYSIS agent.
Your specific task:
  • Provide deep background research on the topic
  • Break down complex concepts with structured analysis
  • Identify key themes, causes, effects, and implications
  • Use numbered lists and clear section headers
  • Be thorough but concise — quality over quantity

Question to research: {query}
""",

    "gpt": """You are the CREATIVE GENERATION & EXPLANATION agent.
Your specific task:
  • Generate creative, engaging perspectives on the topic
  • Use analogies and vivid examples to make ideas accessible
  • Brainstorm innovative angles or solutions
  • Write in a clear, compelling, human-friendly style
  • Add any relevant creative approaches not covered by pure analysis

Question to answer creatively: {query}
""",

    "gemini": """You are the FACT-CHECKING & VERIFICATION agent.
Your specific task:
  • Identify and verify the core factual claims in the question
  • Flag anything that could be misleading or uncertain
  • Provide up-to-date, grounded information
  • Rate each key claim: ✅ Verified | ⚠️ Uncertain | ❌ Incorrect
  • Add relevant statistics, dates, or authoritative sources where possible

Question to fact-check: {query}
""",

    "llama": """You are the CODE GENERATION & TECHNICAL agent.
Your specific task:
  • If code is needed, write clean, production-ready, well-commented code
  • Provide technical implementation details
  • Suggest algorithms, data structures, or architecture patterns
  • Include:
      - Code in properly labelled code blocks
      - Step-by-step explanation
      - Edge cases and error handling
      - Usage example

Technical question: {query}
""",
}

# ──────────────────────────────────────────────────────────────────────────────
# Synthesis prompt template
# ──────────────────────────────────────────────────────────────────────────────

SYNTHESIS_TEMPLATE = """You have received outputs from {n} specialised AI agents, each analysing the following question from a different angle.

═══════════════════════════════════════════
ORIGINAL QUESTION:
{query}
═══════════════════════════════════════════

{agent_sections}

═══════════════════════════════════════════
YOUR TASK — SYNTHESIS:
═══════════════════════════════════════════
Combine the above agent outputs into ONE comprehensive, well-structured final answer.

Requirements:
1. **Executive Summary** (2-3 sentences at the top — the essential answer)
2. **Key Findings** — best insights from all agents, no redundancy
3. **Detailed Breakdown** — organised sections drawing on each agent's expertise
4. **Code / Technical Section** (if applicable) — include the best code snippet
5. **Verified Facts** — highlight fact-checked points
6. **Conclusion** — clear takeaway

Use markdown formatting with headers (##), bold (**text**), and bullet points.
"""

AGENT_SECTION_TEMPLATE = """
┌─────────────────────────────────────
│ AGENT: {name} ({role})
│ Model: {model} | Latency: {latency}s | Tokens: {tokens} | Cost: ${cost}
└─────────────────────────────────────
{content}
"""


# ──────────────────────────────────────────────────────────────────────────────
# PromptEngine class
# ──────────────────────────────────────────────────────────────────────────────

class PromptEngine:
    """Builds and formats prompts for agents and the synthesis step."""

    def build_agent_prompt(self, agent_key: str, query: str) -> str:
        """Return a role-specific prompt for the given agent."""
        template = AGENT_ROLE_PROMPTS.get(agent_key, "Answer the following question:\n{query}")
        return template.format(query=query)

    def build_synthesis_prompt(
        self, query: str, responses: "List[AgentResponse]"
    ) -> str:
        """Build the meta-prompt that synthesises all agent outputs."""
        sections = ""
        successful = [r for r in responses if r.success and r.content]
        for r in successful:
            sections += AGENT_SECTION_TEMPLATE.format(
                name=r.agent_name,
                role=r.role,
                model=r.model,
                latency=r.latency_seconds,
                tokens=r.tokens_used,
                cost=f"{r.cost_usd:.6f}",
                content=r.content,
            )

        if not sections:
            return f"No agent responses available. Original query: {query}"

        return SYNTHESIS_TEMPLATE.format(
            n=len(successful),
            query=query,
            agent_sections=sections,
        )
