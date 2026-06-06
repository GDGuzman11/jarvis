"""Content Creator agent — drafts posts, emails, copy, and documentation.

The Content Creator turns briefs into finished words: social posts, emails,
marketing copy, and documentation. When a task asks to *write* or *draft*
something, it routes here. (Strategy and the brief come from the Marketing
agent; this agent produces the prose.)

Reasoning uses the shared Claude client (inherited Ollama fallback) under a
copywriting-flavoured system prompt layered on the Jarvis persona base.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.ai.persona import build_system_prompt

AGENT_ID = "content"
AGENT_NAME = "Quill"
AGENT_ROLE = "Content creator — drafts posts, emails, copy, and documentation"

# Quill researches for accuracy and writes drafts to the workspace; no code/exec.
DEFAULT_TOOLS: list[str] = ["web_search", "file_ops"]

_EXPERTISE = """\
You are acting as Quill, Jarvis's content creator agent.
Your domain is the written word: social posts, emails, landing-page and ad copy, and product \
documentation. You adapt tone and length to the medium and audience, write clear and \
compelling prose, and keep a consistent brand voice. When given a task — usually a brief from \
the marketing strategist — produce the finished draft, ready to use, with any necessary \
variants (e.g. a short and a long version, or platform-specific cuts) clearly labelled. Note \
that for emails or social posts that would actually be sent, the user confirms before anything \
goes out. Deliver the copy first, then a one-line note on choices made if it helps."""


class ContentCreatorAgent(BaseAgent):
    """Quill: handles drafting of posts, emails, copy, and documentation."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id=AGENT_ID,
            name=AGENT_NAME,
            role=AGENT_ROLE,
            tools=list(DEFAULT_TOOLS),
            **kwargs,
        )

    async def handle_task(self, task: dict[str, Any]) -> str:
        """Produce finished copy for ``task`` using the Quill persona.

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


__all__ = [
    "ContentCreatorAgent",
    "AGENT_ID",
    "AGENT_NAME",
    "AGENT_ROLE",
    "DEFAULT_TOOLS",
]
