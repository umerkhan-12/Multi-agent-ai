"""
Base Agent — Abstract class for all LLM agents.
Each agent inherits this and implements the `run()` method.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class AgentResponse:
    """Structured response returned by every agent."""
    agent_name: str
    role: str
    content: str
    model: str
    tokens_used: int = 0
    latency_seconds: float = 0.0
    cost_usd: float = 0.0
    error: Optional[str] = None
    success: bool = True


class BaseAgent(ABC):
    """
    Abstract base class for all LLM agents.
    Provides common interface + timing utilities.
    """

    def __init__(self, name: str, role: str, model: str):
        self.name = name
        self.role = role
        self.model = model

    @abstractmethod
    def _call_api(self, prompt: str, system_prompt: str) -> dict:
        """
        Make the actual API call. Must return:
          { "content": str, "tokens_used": int, "cost_usd": float }
        """
        pass

    def run(self, prompt: str, system_prompt: str = "") -> AgentResponse:
        """Execute the agent and return a structured AgentResponse."""
        start = time.time()
        try:
            result = self._call_api(prompt, system_prompt)
            latency = round(time.time() - start, 2)
            return AgentResponse(
                agent_name=self.name,
                role=self.role,
                content=result["content"],
                model=self.model,
                tokens_used=result.get("tokens_used", 0),
                latency_seconds=latency,
                cost_usd=result.get("cost_usd", 0.0),
                success=True,
            )
        except Exception as exc:
            latency = round(time.time() - start, 2)
            return AgentResponse(
                agent_name=self.name,
                role=self.role,
                content="",
                model=self.model,
                latency_seconds=latency,
                error=str(exc),
                success=False,
            )

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} model={self.model!r}>"
