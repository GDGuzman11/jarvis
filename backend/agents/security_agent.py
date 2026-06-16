"""Security agent — vulnerability scans, key rotation, and audits.

The Security agent enforces the project's security rules: it audits for leaked
secrets, confirms the server stays bound to loopback, checks OAuth scopes and
sandbox boundaries, and flags risky changes. When a task concerns security,
auditing, or credential handling, it routes here.

Reasoning uses the shared Claude client (inherited Ollama fallback) under a
security-flavoured system prompt layered on the Helix persona base.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.ai.persona import build_system_prompt

AGENT_ID = "security"
AGENT_NAME = "Sentinel"
AGENT_ROLE = "Security specialist — vulnerability scans, key rotation, audits"

# The Security agent reads files and searches; it does not execute code.
DEFAULT_TOOLS: list[str] = ["file_ops", "web_search"]

_EXPERTISE = """\
You are acting as Sentinel, Helix's security specialist agent.
Your domain is the security posture of the whole system. You enforce the project's rules: \
zero secrets in files (all keys live in Windows Credential Manager via keyring; only an \
.env.example template is allowed), the FastAPI server bound to 127.0.0.1 and never 0.0.0.0, \
voice input sanitised and capped before reaching the model, sandboxed code execution with no \
os/sys/subprocess or network access, least-privilege OAuth scopes for Gmail and Slack, and \
metadata-only audit logging. When given a task, audit for concrete vulnerabilities and report \
findings with a severity (Critical/High/Medium/Low), the location, and a remediation. Be \
exact and unsparing; lead with the highest-severity finding."""


class SecurityAgent(BaseAgent):
    """Sentinel: handles security audits and vulnerability scanning tasks."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id=AGENT_ID,
            name=AGENT_NAME,
            role=AGENT_ROLE,
            tools=list(DEFAULT_TOOLS),
            **kwargs,
        )

    async def handle_task(self, task: dict[str, Any]) -> str:
        """Produce a security assessment for ``task`` using the Sentinel persona.

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


__all__ = ["SecurityAgent", "AGENT_ID", "AGENT_NAME", "AGENT_ROLE", "DEFAULT_TOOLS"]
