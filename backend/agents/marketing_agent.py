"""Marketing agent — campaign planning and social content strategy.

The Marketing agent plans campaigns, shapes positioning, and devises social
content strategy. When a task concerns marketing, growth, launch, or campaign
planning, it routes here. (Drafting the actual copy is the Content Creator's
job — this agent owns the strategy; the Content Creator owns the words.)

Reasoning uses the shared Claude client (inherited Ollama fallback) under a
marketing-flavoured system prompt layered on the Jarvis persona base.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.ai.persona import build_system_prompt

AGENT_ID = "marketing"
AGENT_NAME = "Vega"
AGENT_ROLE = "Marketing specialist — campaign planning and social content strategy"

# Marketing researches the market and references the workspace; no code/exec.
DEFAULT_TOOLS: list[str] = ["web_search", "browser", "file_ops"]

_EXPERTISE = """\
You are acting as Vega, Jarvis's marketing specialist agent.
Your domain is marketing strategy: campaign planning, positioning, audience and channel \
selection, messaging pillars, and social content strategy across platforms. You think in \
terms of goals, audience, funnel stage, channel fit, and measurable outcomes. When given a \
task, respond with a concrete plan: the objective, the target audience, the core message, \
the channels and cadence, and how success is measured. Drafting finished copy is the Content \
Creator's job — you set the strategy and the brief. Lead with the strategy, then the \
specifics; be sharp and brief."""


class MarketingAgent(BaseAgent):
    """Vega: handles campaign planning and content-strategy tasks."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id=AGENT_ID,
            name=AGENT_NAME,
            role=AGENT_ROLE,
            tools=list(DEFAULT_TOOLS),
            **kwargs,
        )

    async def handle_task(self, task: dict[str, Any]) -> str:
        """Produce a marketing plan for ``task`` using the Vega persona."""
        description = task.get("description", "").strip()
        system_prompt = build_system_prompt(context=_EXPERTISE)
        return await self.reason(description, system_prompt)


__all__ = ["MarketingAgent", "AGENT_ID", "AGENT_NAME", "AGENT_ROLE", "DEFAULT_TOOLS"]
