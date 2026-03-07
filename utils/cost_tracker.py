"""
Cost Tracker — Tracks API usage costs and token consumption per session.
Helps optimise spending across multiple LLM providers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from agents.base_agent import AgentResponse


@dataclass
class AgentUsage:
    agent_name: str
    calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class CostTracker:
    """
    Records per-agent usage: calls, tokens, and estimated cost.
    Provides a summary report for display in CLI and UI.
    """

    def __init__(self):
        self._usage: Dict[str, AgentUsage] = {}

    def record(self, response: "AgentResponse"):
        """Record a single agent response."""
        key = response.agent_name
        if key not in self._usage:
            self._usage[key] = AgentUsage(agent_name=key)
        u = self._usage[key]
        u.calls        += 1
        u.total_tokens += response.tokens_used
        u.total_cost_usd += response.cost_usd

    @property
    def total_cost(self) -> float:
        return round(sum(u.total_cost_usd for u in self._usage.values()), 6)

    @property
    def total_tokens(self) -> int:
        return sum(u.total_tokens for u in self._usage.values())

    @property
    def total_calls(self) -> int:
        return sum(u.calls for u in self._usage.values())

    def get_summary(self) -> List[dict]:
        """Return a list of dicts for easy tabular display."""
        rows = []
        for u in sorted(self._usage.values(), key=lambda x: x.total_cost_usd, reverse=True):
            rows.append({
                "Agent":        u.agent_name,
                "Calls":        u.calls,
                "Tokens":       u.total_tokens,
                "Cost (USD)":   f"${u.total_cost_usd:.6f}",
            })
        rows.append({
            "Agent":      "── TOTAL ──",
            "Calls":      self.total_calls,
            "Tokens":     self.total_tokens,
            "Cost (USD)": f"${self.total_cost:.6f}",
        })
        return rows

    def print_summary(self):
        """Pretty-print the cost table to stdout."""
        rows = self.get_summary()
        col_w = [12, 8, 10, 14]
        headers = list(rows[0].keys())

        sep = "─" * (sum(col_w) + len(col_w) * 3 + 1)
        print(f"\n{sep}")
        print("  📊  SESSION COST SUMMARY")
        print(sep)
        header_line = " │ ".join(h.ljust(w) for h, w in zip(headers, col_w))
        print(f"  {header_line}")
        print(sep)
        for row in rows:
            values = [str(v) for v in row.values()]
            line = " │ ".join(v.ljust(w) for v, w in zip(values, col_w))
            print(f"  {line}")
        print(f"{sep}\n")

    def reset(self):
        self._usage.clear()
