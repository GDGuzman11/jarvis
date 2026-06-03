"""Assemble a fully-wired :class:`ToolRegistry` for the running app.

:func:`build_tool_registry` is the single place every Phase 6 tool is registered
into one registry with the default per-agent permission matrix. The FastAPI
lifespan calls it once, after the Slack and Gmail clients are constructed, and
exposes the result on ``app.state.tool_registry`` for the agents to use.

Keeping this wiring separate from :mod:`backend.tools.registry` (which holds the
matrix logic) means the registry stays import-light and unit-testable without
pulling in Playwright, DuckDuckGo, or the integration clients.
"""

from __future__ import annotations

from typing import Any

from backend.integrations.gmail_client import GmailClient
from backend.integrations.slack_client import SlackClient
from backend.logging_config import get_logger
from backend.tools import browser, code_executor, file_ops, web_search
from backend.tools.gmail_tool import GmailTools
from backend.tools.registry import ToolRegistry
from backend.tools.slack_tool import SlackTools

log = get_logger(__name__)


def build_tool_registry(
    *,
    slack_client: SlackClient | None = None,
    gmail_client: GmailClient | None = None,
    db_path: Any | None = None,
) -> ToolRegistry:
    """Construct a :class:`ToolRegistry` with every tool registered.

    The standalone tools (web search, browser, file ops, code executor) are
    always registered. The Slack and Gmail wrappers are registered only when
    their respective clients are supplied — agents can still be granted those
    tools in the matrix, but a call will surface as not-found until the client
    exists (the integrations themselves no-op gracefully when unconfigured).
    """
    registry = ToolRegistry(db_path=db_path)

    # Standalone tools — callable + schema, one register_tool each.
    registry.register_tool(
        "web_search", web_search.web_search, web_search.WEB_SEARCH_SCHEMA
    )
    registry.register_tool(
        "browse_url", browser.browse_url, browser.BROWSE_URL_SCHEMA
    )
    registry.register_tool(
        "read_file", file_ops.read_file, file_ops.READ_FILE_SCHEMA
    )
    registry.register_tool(
        "write_file", file_ops.write_file, file_ops.WRITE_FILE_SCHEMA
    )
    registry.register_tool(
        "list_files", file_ops.list_files, file_ops.LIST_FILES_SCHEMA
    )
    registry.register_tool(
        "execute_code", code_executor.execute_code, code_executor.EXECUTE_CODE_SCHEMA
    )

    # Integration-backed tools — only when a client is available.
    if slack_client is not None:
        slack_tools = SlackTools(slack_client)
        registry.register_many(slack_tools.callables(), slack_tools.schemas())
    if gmail_client is not None:
        gmail_tools = GmailTools(gmail_client)
        registry.register_many(gmail_tools.callables(), gmail_tools.schemas())

    log.info("tool_registry_built", tools=len(registry.list_tools()))
    return registry


__all__ = ["build_tool_registry"]
