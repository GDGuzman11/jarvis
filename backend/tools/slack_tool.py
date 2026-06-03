"""Slack tool wrappers — expose :class:`SlackClient` methods as Claude tools.

The Phase 5 :class:`~backend.integrations.slack_client.SlackClient` already does
the real work (auth, Web API calls, graceful degradation). This module adapts a
*single client instance* into the shape the tool registry and the Claude API
expect: named async callables plus their ``tool_use`` JSON schemas.

:class:`SlackTools` is constructed with the app-wide ``SlackClient`` (from
``app.state.slack_client``) so every agent shares one authenticated client and a
single audit trail. The wrapper methods return JSON-serialisable values suitable
for handing straight back to the model as a ``tool_result``.
"""

from __future__ import annotations

from typing import Any

from backend.integrations.slack_client import SlackClient

# --- Claude API tool_use schemas -------------------------------------------

SLACK_SEND_MESSAGE_SCHEMA: dict[str, Any] = {
    "name": "slack_send_message",
    "description": (
        "Send a message to a Slack channel, DM, or user. 'channel' accepts a "
        "channel id (C…), a DM channel id (D…), or a user id (U…). Returns "
        "whether the send succeeded."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "channel": {
                "type": "string",
                "description": "Slack channel id, DM id, or user id to send to.",
            },
            "text": {
                "type": "string",
                "description": "The message text to post.",
            },
        },
        "required": ["channel", "text"],
    },
}

SLACK_GET_DM_HISTORY_SCHEMA: dict[str, Any] = {
    "name": "slack_get_dm_history",
    "description": (
        "Read recent direct messages exchanged with a given Slack user. Returns "
        "a list of {user, text, ts} entries, newest first."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The Slack user id (U…) whose DM history to read.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum messages to return (default 10).",
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": ["user_id"],
    },
}

SLACK_GET_UNREAD_MENTIONS_SCHEMA: dict[str, Any] = {
    "name": "slack_get_unread_mentions",
    "description": (
        "List recent messages that @-mention the Jarvis bot across the channels "
        "it belongs to. Returns a list of {channel, user, text, ts} entries."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum mentions to return (default 10).",
                "minimum": 1,
                "maximum": 50,
            }
        },
        "required": [],
    },
}


class SlackTools:
    """Adapts a shared :class:`SlackClient` into named, schema-backed tools.

    Parameters
    ----------
    client:
        The application's ``SlackClient`` instance. Shared so all callers reuse
        one authenticated client and audit trail.
    """

    def __init__(self, client: SlackClient) -> None:
        self._client = client

    async def slack_send_message(self, channel: str, text: str) -> dict[str, Any]:
        """Send a Slack message; returns ``{"ok": bool}``."""
        ok = await self._client.send_message(channel, text)
        return {"ok": ok}

    async def slack_get_dm_history(
        self, user_id: str, limit: int = 10
    ) -> list[dict]:
        """Return recent DM messages with ``user_id`` as ``{user, text, ts}`` dicts."""
        return await self._client.get_dm_history(user_id, limit=limit)

    async def slack_get_unread_mentions(self, limit: int = 10) -> list[dict]:
        """Return recent bot @-mentions as ``{channel, user, text, ts}`` dicts."""
        return await self._client.get_unread_mentions(limit=limit)

    def schemas(self) -> dict[str, dict[str, Any]]:
        """Map each tool name to its Claude ``tool_use`` schema."""
        return {
            "slack_send_message": SLACK_SEND_MESSAGE_SCHEMA,
            "slack_get_dm_history": SLACK_GET_DM_HISTORY_SCHEMA,
            "slack_get_unread_mentions": SLACK_GET_UNREAD_MENTIONS_SCHEMA,
        }

    def callables(self) -> dict[str, Any]:
        """Map each tool name to its bound async callable."""
        return {
            "slack_send_message": self.slack_send_message,
            "slack_get_dm_history": self.slack_get_dm_history,
            "slack_get_unread_mentions": self.slack_get_unread_mentions,
        }


__all__ = [
    "SlackTools",
    "SLACK_SEND_MESSAGE_SCHEMA",
    "SLACK_GET_DM_HISTORY_SCHEMA",
    "SLACK_GET_UNREAD_MENTIONS_SCHEMA",
]
