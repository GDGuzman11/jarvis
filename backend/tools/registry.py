"""ToolRegistry — the per-agent tool permission matrix for Helix.

The registry is the single gatekeeper between the 6 agents and every tool. It:

* holds each tool's callable and its Claude API ``tool_use`` JSON schema
  (:meth:`register_tool`);
* knows which tools each agent is allowed to use (the permission matrix);
* hands an agent exactly the schemas it may call, for inclusion in a Claude
  request (:meth:`get_tools_for_agent`);
* enforces those permissions and dispatches the call (:meth:`call_tool`),
  raising :class:`PermissionError` for a tool an agent is not allowed to use;
* writes an ``audit_log`` row for **every** tool call — allowed, denied, or
  errored — recording metadata only (agent id, tool name, outcome), never the
  arguments or result (Security Rule 6).

Permission matrix
-----------------
:data:`DEFAULT_PERMISSIONS` maps each ``agent_id`` to the set of tool names it
may use. The Production Lead (Atlas) gets everything; the Security agent
(Sentinel) gets read-only tools; the others get a task-appropriate subset. The
matrix is data, so the Tools window (Phase 7) can later toggle entries live via
:meth:`grant` / :meth:`revoke`.

Async + sync tools
------------------
:meth:`call_tool` is ``async`` and transparently awaits coroutine tools (web
search, browser, Slack/Gmail wrappers) while running plain sync tools (file ops,
which are fast and local) directly. This keeps the call site uniform for callers.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.logging_config import get_logger
from backend.memory import database

log = get_logger(__name__)

# Tool name -> tool name groupings used to express the default matrix concisely.
# Read-only tools never mutate external state; the Security agent is limited to
# these. Communication tools can send/draft; write/exec tools touch the
# workspace or run code.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "web_search",
        "browse_url",
        "read_file",
        "list_files",
        "gmail_get_inbox",
        "slack_get_dm_history",
        "slack_get_unread_mentions",
    }
)

WRITE_TOOLS: frozenset[str] = frozenset({"write_file", "execute_code"})

COMMS_TOOLS: frozenset[str] = frozenset(
    {
        "slack_send_message",
        "gmail_send_email",
        "gmail_draft_email",
    }
)

# Every tool the system knows about — the union used to grant "all" to the lead.
ALL_TOOLS: frozenset[str] = READ_ONLY_TOOLS | WRITE_TOOLS | COMMS_TOOLS

# Default per-agent permission matrix. Agent ids match the agents table /
# AGENT_ID constants: production_lead, frontend, backend, security, marketing,
# content. Stored as sets so the live UI can grant/revoke individual tools.
DEFAULT_PERMISSIONS: dict[str, set[str]] = {
    # Production Lead (Atlas) orchestrates everything — full access.
    "production_lead": set(ALL_TOOLS),
    # Ben (frontend) — research + workspace files + code sandbox for snippets.
    "frontend": {"web_search", "browse_url", "read_file", "write_file",
                 "list_files", "execute_code"},
    # Kado (backend) — same builder toolkit as frontend.
    "backend": {"web_search", "browse_url", "read_file", "write_file",
                "list_files", "execute_code"},
    # Sentinel (security) — strictly read-only: it audits, never mutates.
    "security": set(READ_ONLY_TOOLS),
    # Vega (marketing) — research + comms (send Slack, draft email) + read files.
    "marketing": {"web_search", "browse_url", "read_file", "list_files",
                  "slack_send_message", "slack_get_unread_mentions",
                  "gmail_get_inbox", "gmail_draft_email"},
    # Quill (content) — research, drafting to workspace, and draft email.
    "content": {"web_search", "browse_url", "read_file", "write_file",
                "list_files", "gmail_draft_email"},
}


class PermissionError(Exception):  # noqa: A001 - deliberately shadow builtin in this domain
    """Raised when an agent attempts to call a tool it is not permitted to use."""


class ToolNotFoundError(KeyError):
    """Raised when a referenced tool name has not been registered."""


@dataclass(frozen=True)
class _Tool:
    """A registered tool: its callable and its Claude ``tool_use`` schema."""

    name: str
    fn: Callable[..., Any]
    schema: dict[str, Any]


class ToolRegistry:
    """Holds tools and the per-agent permission matrix; enforces and audits calls.

    Parameters
    ----------
    permissions:
        Optional override of the agent -> allowed-tool-names matrix. Defaults to
        a deep copy of :data:`DEFAULT_PERMISSIONS` so mutations (grant/revoke)
        never leak into the module-level default.
    db_path:
        Optional SQLite path override threaded through to the audit log (tests
        point this at a temp database).
    """

    def __init__(
        self,
        permissions: dict[str, set[str]] | None = None,
        *,
        db_path: Any | None = None,
    ) -> None:
        self._tools: dict[str, _Tool] = {}
        source = permissions if permissions is not None else DEFAULT_PERMISSIONS
        # Deep-copy the sets so callers/tests can't mutate the shared default.
        self._permissions: dict[str, set[str]] = {
            agent: set(tools) for agent, tools in source.items()
        }
        self._db_path = db_path

    # --- Registration -------------------------------------------------------

    def register_tool(
        self, name: str, tool_fn: Callable[..., Any], schema: dict[str, Any]
    ) -> None:
        """Register ``name`` -> (callable, Claude schema).

        The schema's ``name`` field, if present, must match ``name`` so the
        model and the dispatcher never disagree. Re-registering a name replaces
        the prior entry (handy across hot reloads / re-wiring in tests).
        """
        schema_name = schema.get("name")
        if schema_name is not None and schema_name != name:
            raise ValueError(
                f"tool schema name {schema_name!r} != registered name {name!r}"
            )
        self._tools[name] = _Tool(name=name, fn=tool_fn, schema=schema)
        log.info("tool_registered", tool=name)

    def register_many(
        self,
        callables: dict[str, Callable[..., Any]],
        schemas: dict[str, dict[str, Any]],
    ) -> None:
        """Register every name present in both ``callables`` and ``schemas``."""
        for name, fn in callables.items():
            if name in schemas:
                self.register_tool(name, fn, schemas[name])

    # --- Permission matrix --------------------------------------------------

    def is_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Return whether ``agent_id`` may call ``tool_name``."""
        return tool_name in self._permissions.get(agent_id, set())

    def grant(self, agent_id: str, tool_name: str) -> None:
        """Allow ``agent_id`` to use ``tool_name`` (live matrix edit)."""
        self._permissions.setdefault(agent_id, set()).add(tool_name)

    def revoke(self, agent_id: str, tool_name: str) -> None:
        """Disallow ``agent_id`` from using ``tool_name`` (live matrix edit)."""
        self._permissions.get(agent_id, set()).discard(tool_name)

    def permissions_matrix(self) -> dict[str, list[str]]:
        """Return a JSON-serialisable snapshot of the matrix (for the Tools UI)."""
        return {
            agent: sorted(tools) for agent, tools in self._permissions.items()
        }

    # --- Schema access for Claude requests ---------------------------------

    def get_tools_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        """Return the Claude ``tool_use`` schemas ``agent_id`` is allowed to use.

        Only tools that are *both* registered and permitted for the agent are
        returned, so the list handed to the Claude API never advertises a tool
        the agent cannot actually call. Sorted by name for deterministic output.
        """
        allowed = self._permissions.get(agent_id, set())
        return [
            self._tools[name].schema
            for name in sorted(allowed)
            if name in self._tools
        ]

    def list_tools(self) -> list[str]:
        """Return every registered tool name, sorted."""
        return sorted(self._tools)

    # --- Dispatch -----------------------------------------------------------

    async def call_tool(
        self, agent_id: str, tool_name: str, args: dict[str, Any] | None = None
    ) -> Any:
        """Invoke ``tool_name`` on behalf of ``agent_id`` with ``args``.

        Enforces the permission matrix (raises :class:`PermissionError` if the
        agent may not use the tool) and that the tool exists (raises
        :class:`ToolNotFoundError`). Sync tools run directly; async tools are
        awaited. Every outcome — denied, not-found, error, ok — is written to the
        audit log as metadata only (Security Rule 6): agent id, tool name, and a
        one-word outcome, never the arguments or the result.
        """
        kwargs = dict(args or {})

        # 1) Permission check — denied calls are audited and refused.
        if not self.is_allowed(agent_id, tool_name):
            await self._audit(agent_id, tool_name, "denied")
            raise PermissionError(
                f"agent {agent_id!r} is not permitted to use tool {tool_name!r}"
            )

        # 2) Existence check.
        tool = self._tools.get(tool_name)
        if tool is None:
            await self._audit(agent_id, tool_name, "not_found")
            raise ToolNotFoundError(tool_name)

        # 3) Dispatch, awaiting coroutine tools transparently.
        try:
            result = tool.fn(**kwargs)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            await self._audit(agent_id, tool_name, "error")
            log.error(
                "tool_call_failed", agent=agent_id, tool=tool_name, error=str(exc)
            )
            raise

        await self._audit(agent_id, tool_name, "ok")
        return result

    async def _audit(self, agent_id: str, tool_name: str, outcome: str) -> None:
        """Write one metadata-only audit row for a tool call (best-effort)."""
        try:
            kwargs = {"db_path": self._db_path} if self._db_path is not None else {}
            await database.log_audit(
                agent_id, "tool_call", target=tool_name, detail=outcome, **kwargs
            )
        except Exception as exc:  # noqa: BLE001 - auditing must never break a call
            log.warning("tool_audit_failed", tool=tool_name, error=str(exc))


__all__ = [
    "ToolRegistry",
    "PermissionError",
    "ToolNotFoundError",
    "DEFAULT_PERMISSIONS",
    "READ_ONLY_TOOLS",
    "WRITE_TOOLS",
    "COMMS_TOOLS",
    "ALL_TOOLS",
]
