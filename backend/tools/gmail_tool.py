"""Gmail tool wrappers — expose :class:`GmailClient` methods as Claude tools.

Adapts the Phase 5 :class:`~backend.integrations.gmail_client.GmailClient` (which
owns OAuth, the Gmail API, and graceful degradation) into the shape the tool
registry and the Claude API expect: named async callables plus their ``tool_use``
JSON schemas.

:class:`GmailTools` is constructed with the app-wide ``GmailClient`` (from
``app.state.gmail_client``) so every agent shares one authenticated client and a
single audit trail. The wrapper methods return JSON-serialisable values suitable
for handing back to the model as a ``tool_result``.
"""

from __future__ import annotations

from typing import Any

from backend.integrations.gmail_client import GmailClient

# --- Claude API tool_use schemas -------------------------------------------

GMAIL_GET_INBOX_SCHEMA: dict[str, Any] = {
    "name": "gmail_get_inbox",
    "description": (
        "Read recent unread messages from the user's Gmail inbox. Returns a list "
        "of {id, from, subject, snippet} entries. Read-only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum messages to return (default 10).",
                "minimum": 1,
                "maximum": 25,
            }
        },
        "required": [],
    },
}

GMAIL_SEND_EMAIL_SCHEMA: dict[str, Any] = {
    "name": "gmail_send_email",
    "description": (
        "Send an email from the user's Gmail account. Returns whether the send "
        "succeeded. Use gmail_draft_email first if the user wants to review "
        "before sending."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address.",
            },
            "subject": {"type": "string", "description": "Email subject line."},
            "body": {"type": "string", "description": "Plain-text email body."},
        },
        "required": ["to", "subject", "body"],
    },
}

GMAIL_DRAFT_EMAIL_SCHEMA: dict[str, Any] = {
    "name": "gmail_draft_email",
    "description": (
        "Create a draft email in the user's Gmail account without sending it. "
        "Returns the draft id. Use this when the user wants to review before "
        "sending."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address.",
            },
            "subject": {"type": "string", "description": "Email subject line."},
            "body": {"type": "string", "description": "Plain-text email body."},
        },
        "required": ["to", "subject", "body"],
    },
}


class GmailTools:
    """Adapts a shared :class:`GmailClient` into named, schema-backed tools.

    Parameters
    ----------
    client:
        The application's ``GmailClient`` instance. Shared so all callers reuse
        one authenticated client and audit trail.
    """

    def __init__(self, client: GmailClient) -> None:
        self._client = client

    async def gmail_get_inbox(self, limit: int = 10) -> list[dict]:
        """Return recent unread inbox messages as ``{id, from, subject, snippet}``."""
        return await self._client.get_inbox(limit=limit)

    async def gmail_send_email(
        self, to: str, subject: str, body: str
    ) -> dict[str, Any]:
        """Send an email; returns ``{"ok": bool}``."""
        ok = await self._client.send_email(to, subject, body)
        return {"ok": ok}

    async def gmail_draft_email(
        self, to: str, subject: str, body: str
    ) -> dict[str, Any]:
        """Create a draft; returns ``{"draft_id": str}`` ("" when unavailable)."""
        draft_id = await self._client.draft_email(to, subject, body)
        return {"draft_id": draft_id}

    def schemas(self) -> dict[str, dict[str, Any]]:
        """Map each tool name to its Claude ``tool_use`` schema."""
        return {
            "gmail_get_inbox": GMAIL_GET_INBOX_SCHEMA,
            "gmail_send_email": GMAIL_SEND_EMAIL_SCHEMA,
            "gmail_draft_email": GMAIL_DRAFT_EMAIL_SCHEMA,
        }

    def callables(self) -> dict[str, Any]:
        """Map each tool name to its bound async callable."""
        return {
            "gmail_get_inbox": self.gmail_get_inbox,
            "gmail_send_email": self.gmail_send_email,
            "gmail_draft_email": self.gmail_draft_email,
        }


__all__ = [
    "GmailTools",
    "GMAIL_GET_INBOX_SCHEMA",
    "GMAIL_SEND_EMAIL_SCHEMA",
    "GMAIL_DRAFT_EMAIL_SCHEMA",
]
