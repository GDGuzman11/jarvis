"""Kado — the Backend specialist agent.

Kado owns the Python backend: FastAPI, the WebSocket hub, the SQLite persistence
layer, the FAISS vector memory, the voice pipeline, the Claude/Ollama clients,
and performance. When a task touches APIs, the database, the voice loop, or
runtime performance, it routes to Kado.

Reasoning uses the shared Claude client (with the inherited Ollama fallback)
under a backend-flavoured system prompt layered on the Jarvis persona base.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.ai.persona import build_system_prompt

AGENT_ID = "backend"
AGENT_NAME = "Kado"
AGENT_ROLE = "Backend specialist — APIs, database, voice pipeline, and performance"

# Kado may run code (sandboxed) and touch files in the workspace, plus search.
DEFAULT_TOOLS: list[str] = ["file_ops", "code_executor", "web_search"]

_EXPERTISE = """\
You are acting as Kado, Jarvis's backend specialist agent.
Your domain is the Python backend: Python 3.12, FastAPI, WebSockets, Uvicorn, the single \
WebSocket hub, SQLite via aiosqlite, FAISS + sentence-transformers semantic memory, the \
Anthropic and Ollama clients (streaming + prompt caching), the faster-whisper / ElevenLabs \
voice pipeline, and runtime performance on a 4GB-VRAM laptop. You follow the project's \
security rules: secrets only in Windows Credential Manager via keyring, the server bound to \
127.0.0.1, sanitised voice input, sandboxed code execution, and metadata-only audit logging. \
When given a task, respond with concrete backend guidance: endpoints, async patterns, schema, \
data flow, and how it broadcasts over the WebSocket hub. Lead with the approach, then the \
load-bearing detail; be precise and brief."""


class BackendAgent(BaseAgent):
    """Kado: handles backend, database, voice, and performance tasks."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id=AGENT_ID,
            name=AGENT_NAME,
            role=AGENT_ROLE,
            tools=list(DEFAULT_TOOLS),
            **kwargs,
        )

    async def handle_task(self, task: dict[str, Any]) -> str:
        """Produce backend guidance for ``task`` using the Kado persona.

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


__all__ = ["BackendAgent", "AGENT_ID", "AGENT_NAME", "AGENT_ROLE", "DEFAULT_TOOLS"]
