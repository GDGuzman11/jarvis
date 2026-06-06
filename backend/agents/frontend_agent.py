"""Ben — the Frontend specialist agent.

Ben owns the Tauri + React + TypeScript UI: component design, the
glassmorphism HUD aesthetic, the Three.js orb, Zustand state, and the
WebSocket wiring that keeps all 5 windows live. When a task touches anything
the user can see, it routes to Ben.

The agent reasons with the shared Claude client (Ollama fallback inherited from
:class:`~backend.agents.base_agent.BaseAgent`) under a frontend-flavoured system
prompt built on the Jarvis persona base, so its replies stay in the project's
voice while being grounded in frontend expertise.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.ai.persona import build_system_prompt

# Stable identity used as the ``agents`` table primary key and for routing.
AGENT_ID = "frontend"
AGENT_NAME = "Ben"
AGENT_ROLE = "Frontend specialist — Tauri/React UI, design, and visual polish"

# Default tools Ben may use (enforced by the Phase 6 tool registry).
DEFAULT_TOOLS: list[str] = ["file_ops", "web_search", "browser"]

# Per-agent expertise appended after the cached Jarvis persona base. Kept as
# situational context so the persona prefix stays byte-stable and cacheable.
_EXPERTISE = """\
You are acting as Ben, Jarvis's frontend specialist agent.
Your domain is the Jarvis user interface: Tauri 2, React 19, TypeScript 5, Vite 6, \
Tailwind CSS 4, Zustand state, Three.js / React Three Fiber, and the WebSocket sync \
that drives all five windows. You favour the project's aesthetic — dark glassmorphism, \
electric blue and cyan accents, gold highlights, sharp glowing edges, no rounded cards. \
When given a task, respond with concrete, implementable frontend guidance: components, \
props, state shape, styling, and how it binds to the backend WebSocket events. Be precise \
and brief; lead with the approach, then the key details."""


class FrontendAgent(BaseAgent):
    """Ben: handles UI/UX and frontend implementation tasks."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id=AGENT_ID,
            name=AGENT_NAME,
            role=AGENT_ROLE,
            tools=list(DEFAULT_TOOLS),
            **kwargs,
        )

    async def handle_task(self, task: dict[str, Any]) -> str:
        """Produce frontend guidance for ``task`` using the Ben persona.

        Records the task outcome to ``agent_performance`` (Phase 12C) so the
        agent's success/failure history accrues as self-improvement memory.
        """
        description = task.get("description", "").strip()
        system_prompt = build_system_prompt(context=_EXPERTISE)
        try:
            result = await self.reason(description, system_prompt)
        except Exception:
            self._record_performance(task, "failed")
            raise
        self._record_performance(task, "success")
        return result


__all__ = ["FrontendAgent", "AGENT_ID", "AGENT_NAME", "AGENT_ROLE", "DEFAULT_TOOLS"]
