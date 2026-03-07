"""
Orchestrator — The brain of the Multi-Agent AI System.

Flow:
  1. Analyse the user question → decide which agents to call and in what order.
  2. Run agents (in parallel where possible via threads).
  3. Synthesise all responses → produce a final unified answer.
  4. Return full metadata (cost, latency, per-agent output).
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from agents.base_agent import AgentResponse
from agents.claude_agent  import ClaudeAgent
from agents.gpt_agent     import GPTAgent
from agents.gemini_agent  import GeminiAgent
from agents.llama_agent   import LlamaAgent
from utils.prompt_engine  import PromptEngine
from utils.cost_tracker   import CostTracker


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    """Complete result returned by the orchestrator."""
    user_query: str
    final_answer: str
    agent_responses: List[AgentResponse] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    total_latency_seconds: float = 0.0
    agents_used: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Manages a panel of specialised LLM agents and synthesises their outputs.

    Agents & their roles
    ─────────────────────
    Claude  → Deep research & structured analysis
    GPT-4   → Creative generation & clear explanation
    Gemini  → Fact-checking & verification
    Llama   → Code generation & technical tasks
    """

    AGENT_DESCRIPTIONS = {
        "claude": "Deep research, analysis, academic context, history, science",
        "gpt":    "Creative writing, brainstorming, explanations, storytelling",
        "gemini": "Fact-checking, verification, recent events, grounding",
        "llama":  "Code generation, debugging, algorithms, technical how-to",
    }

    def __init__(self, available_agents: Optional[List[str]] = None):
        """
        available_agents: list of agent keys to load.
          Defaults to all: ["claude", "gpt", "gemini", "llama"]
          Pass a subset if you only have certain API keys.
        """
        self.agents: Dict[str, object] = {}
        self.prompt_engine = PromptEngine()
        self.cost_tracker  = CostTracker()

        to_load = available_agents or ["claude", "gpt", "gemini", "llama"]
        self._load_agents(to_load)

    # ── Agent Loading ──────────────────────────────────────────────────────────

    def _load_agents(self, keys: List[str]):
        loader_map = {
            "claude": ClaudeAgent,
            "gpt":    GPTAgent,
            "gemini": GeminiAgent,
            "llama":  LlamaAgent,
        }
        for key in keys:
            try:
                self.agents[key] = loader_map[key]()
                print(f"  ✅ {key.capitalize()} agent loaded — {loader_map[key].__doc__.strip().split(chr(10))[0]}")
            except Exception as exc:
                print(f"  ⚠️  {key.capitalize()} agent SKIPPED — {exc}")

    # ── Query Analysis ─────────────────────────────────────────────────────────

    def _select_agents(self, query: str) -> List[str]:
        """
        Simple keyword-based agent selector.
        A smarter version could use an LLM to route the query.
        """
        q = query.lower()

        # Always use all available agents for rich responses
        # But prioritise by relevance:
        selected = list(self.agents.keys())   # use all that are loaded

        # Boost order based on query type
        if any(w in q for w in ["code", "function", "algorithm", "script",
                                 "program", "implement", "debug", "class"]):
            # Move llama to front for code-heavy queries
            if "llama" in selected:
                selected.insert(0, selected.pop(selected.index("llama")))

        elif any(w in q for w in ["explain", "creative", "write", "story",
                                   "idea", "generate", "describe"]):
            if "gpt" in selected:
                selected.insert(0, selected.pop(selected.index("gpt")))

        elif any(w in q for w in ["fact", "true", "verify", "check",
                                   "accurate", "correct", "news"]):
            if "gemini" in selected:
                selected.insert(0, selected.pop(selected.index("gemini")))

        return selected

    # ── Parallel Execution ────────────────────────────────────────────────────

    def _run_agents_parallel(
        self, selected: List[str], query: str
    ) -> List[AgentResponse]:
        """Run all selected agents concurrently via a thread pool."""
        results = []

        def run_one(key: str) -> AgentResponse:
            agent = self.agents[key]
            agent_prompt = self.prompt_engine.build_agent_prompt(key, query)
            return agent.run(agent_prompt)

        with ThreadPoolExecutor(max_workers=len(selected)) as pool:
            future_map = {pool.submit(run_one, k): k for k in selected}
            for future in as_completed(future_map):
                results.append(future.result())

        return results

    # ── Synthesis ─────────────────────────────────────────────────────────────

    def _synthesise(
        self, query: str, responses: List[AgentResponse]
    ) -> str:
        """
        Combine all agent outputs into a single, coherent final answer.
        Uses a meta-prompt sent to the best available agent (Claude → GPT fallback).
        """
        # Build the synthesis prompt
        synthesis_prompt = self.prompt_engine.build_synthesis_prompt(
            query, responses
        )

        # Pick synthesiser (prefer Claude, then GPT, then any)
        synthesiser_key = next(
            (k for k in ["claude", "gpt", "gemini", "llama"] if k in self.agents),
            None,
        )
        if not synthesiser_key:
            return "Error: No agents available for synthesis."

        synthesiser = self.agents[synthesiser_key]
        sys_prompt = (
            "You are a master synthesiser. You receive outputs from multiple "
            "specialised AI agents and combine them into the best possible, "
            "comprehensive, well-structured answer. "
            "Eliminate redundancy. Highlight key insights. "
            "Format with clear sections, bullet points where appropriate, "
            "and a brief executive summary at the top."
        )

        synth_result = synthesiser.run(synthesis_prompt, system_prompt=sys_prompt)
        return synth_result.content if synth_result.success else (
            "Synthesis failed. Raw agent outputs available above."
        )

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def run(self, query: str) -> OrchestratorResult:
        """
        Process a user query through the multi-agent pipeline.

        Returns OrchestratorResult with final_answer + per-agent metadata.
        """
        if not self.agents:
            return OrchestratorResult(
                user_query=query,
                final_answer="No agents are available. Please set at least one API key.",
                errors=["No agents loaded."],
            )

        overall_start = time.time()

        # 1. Select and order agents
        selected = self._select_agents(query)

        # 2. Run agents in parallel
        responses = self._run_agents_parallel(selected, query)

        # 3. Track costs
        for r in responses:
            self.cost_tracker.record(r)

        # 4. Synthesise
        final_answer = self._synthesise(query, responses)

        # 5. Build result
        total_latency = round(time.time() - overall_start, 2)
        errors = [f"{r.agent_name}: {r.error}" for r in responses if not r.success]

        return OrchestratorResult(
            user_query=query,
            final_answer=final_answer,
            agent_responses=responses,
            total_cost_usd=round(sum(r.cost_usd for r in responses), 6),
            total_tokens=sum(r.tokens_used for r in responses),
            total_latency_seconds=total_latency,
            agents_used=[r.agent_name for r in responses if r.success],
            errors=errors,
        )
