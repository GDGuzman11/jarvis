"""Phase 15B — WebSocket Event Wiring verification tests.

Phase 15B closes the WS contract drift documented in HEALTH.md: the frontend
handles 9 event types but the backend only broadcast 6, leaving three windows
rendering skeletons. These tests assert the three newly-wired broadcasts fire
with the exact shapes the frontend (``frontend/src/lib/types.ts``) expects, and
that no secret ever rides a ``tool_call`` preview.

Covered:

1. ``tool_call`` — a successful ``call_tool`` broadcasts a ``ToolCall`` event
   carrying the tool name, agent id, scrubbed args, and a truncated result.
2. Secret scrubbing — credential-looking arg keys are redacted and long string
   values are length-capped before broadcast (Security Rule 1).
3. ``tool_permissions`` — ``grant``/``revoke`` broadcast the live matrix; the
   ``permissions_event`` snapshot has the ``{permissions, tools}`` shape.
4. ``comms`` — a Slack read and a Gmail read each broadcast a ``CommsEvent``
   mapped to the frontend ``SlackMessage`` / ``GmailMessage`` shapes.

Everything runs against an in-memory fake hub and patched audit writes, so no
network, credentials, or on-disk DB are touched.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.events import CommsEvent, ToolCall, ToolPermissionsEvent
from backend.tools.registry import ToolRegistry


class FakeHub:
    """Minimal hub stand-in that records every broadcast event in order."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def broadcast(self, event: Any) -> int:
        self.events.append(event)
        return 1


@pytest.fixture(autouse=True)
def _no_audit_writes():
    """Stub the registry's audit writer so tests never touch the real DB."""
    with patch(
        "backend.tools.registry.database.log_audit",
        new=AsyncMock(return_value=None),
    ):
        yield


def _registry_with_tool(hub: FakeHub) -> ToolRegistry:
    """A registry granting 'backend' a single echo tool, wired to ``hub``."""
    reg = ToolRegistry(permissions={"backend": {"echo"}}, hub=hub)

    def echo(**kwargs: Any) -> dict[str, Any]:
        return {"echoed": kwargs}

    reg.register_tool("echo", echo, {"name": "echo", "input_schema": {}})
    return reg


# --- 1. tool_call broadcast -------------------------------------------------


async def test_call_tool_broadcasts_tool_call_event() -> None:
    hub = FakeHub()
    reg = _registry_with_tool(hub)

    await reg.call_tool("backend", "echo", {"message": "hi"})

    tool_calls = [e for e in hub.events if isinstance(e, ToolCall)]
    assert len(tool_calls) == 1
    event = tool_calls[0]
    assert event.type == "tool_call"
    assert event.tool_name == "echo"
    assert event.agent_id == "backend"
    assert event.args == {"message": "hi"}
    # result is a truncated string preview, not the raw object.
    assert "echoed" in event.result


async def test_denied_call_does_not_broadcast() -> None:
    hub = FakeHub()
    reg = _registry_with_tool(hub)

    from backend.tools.registry import PermissionError as ToolPermissionError

    with pytest.raises(ToolPermissionError):
        await reg.call_tool("security", "echo", {"message": "hi"})
    assert not [e for e in hub.events if isinstance(e, ToolCall)]


# --- 2. secret scrubbing ----------------------------------------------------


async def test_tool_call_redacts_secret_args_and_truncates() -> None:
    hub = FakeHub()
    reg = _registry_with_tool(hub)

    long_value = "x" * 500
    await reg.call_tool(
        "backend",
        "echo",
        {
            "api_key": "sk-supersecret",
            "password": "hunter2",
            "authorization": "Bearer abc",
            "body": long_value,
        },
    )

    event = next(e for e in hub.events if isinstance(e, ToolCall))
    # Credential-looking keys never carry their real value.
    assert event.args["api_key"] == "***redacted***"
    assert event.args["password"] == "***redacted***"
    assert event.args["authorization"] == "***redacted***"
    assert "supersecret" not in str(event.args)
    assert "hunter2" not in str(event.args)
    # Long values are capped so a big body can't flood the UI.
    assert len(event.args["body"]) <= 201
    # The whole result preview is bounded too.
    assert len(str(event.result)) <= 201


async def test_tool_call_result_preview_is_capped() -> None:
    hub = FakeHub()
    reg = ToolRegistry(permissions={"backend": {"big"}}, hub=hub)
    reg.register_tool(
        "big", lambda **_: "y" * 1000, {"name": "big", "input_schema": {}}
    )

    await reg.call_tool("backend", "big", {})
    event = next(e for e in hub.events if isinstance(e, ToolCall))
    assert len(event.result) <= 201


# --- 3. tool_permissions broadcast ------------------------------------------


def test_permissions_event_shape() -> None:
    reg = ToolRegistry(permissions={"backend": {"echo"}})
    reg.register_tool("echo", lambda **_: None, {"name": "echo", "input_schema": {}})

    event = reg.permissions_event()
    assert isinstance(event, ToolPermissionsEvent)
    assert event.type == "tool_permissions"
    assert event.permissions == {"backend": ["echo"]}
    assert event.tools == ["echo"]


async def test_grant_and_revoke_broadcast_permissions() -> None:
    hub = FakeHub()
    reg = ToolRegistry(permissions={"backend": set()}, hub=hub)

    reg.grant("backend", "web_search")
    reg.revoke("backend", "web_search")
    # grant/revoke schedule the async broadcast as a task; let them run.
    await asyncio.sleep(0)

    perm_events = [e for e in hub.events if isinstance(e, ToolPermissionsEvent)]
    assert len(perm_events) == 2
    assert perm_events[0].permissions["backend"] == ["web_search"]
    assert perm_events[1].permissions["backend"] == []


def test_grant_without_running_loop_is_safe() -> None:
    """grant outside an event loop must not raise (no loop to schedule onto)."""
    hub = FakeHub()
    reg = ToolRegistry(permissions={"backend": set()}, hub=hub)
    reg.grant("backend", "web_search")  # no running loop — silent no-op broadcast
    assert reg.is_allowed("backend", "web_search")
    assert not hub.events


# --- 4. comms broadcast (Slack + Gmail) -------------------------------------


async def test_slack_read_broadcasts_comms_event() -> None:
    from backend.integrations.slack_client import SlackClient

    hub = FakeHub()
    web = MagicMock()
    web.conversations_open = AsyncMock(return_value={"channel": {"id": "D999"}})
    web.conversations_history = AsyncMock(
        return_value={"messages": [{"user": "U1", "text": "hi", "ts": "1.1"}]}
    )

    client = SlackClient(hub=hub)
    client._web = web

    with patch(
        "backend.integrations.slack_client.database.log_audit",
        new=AsyncMock(return_value=None),
    ):
        await client.get_dm_history("U1")

    comms = next(e for e in hub.events if isinstance(e, CommsEvent))
    assert comms.type == "comms"
    assert comms.gmail is None
    assert comms.slack == [
        {
            "id": "1.1",
            "sender": "U1",
            "channel": "D999",
            "text": "hi",
            "unread": True,
            "timestamp": "1.1",
        }
    ]


async def test_gmail_read_broadcasts_comms_event() -> None:
    from backend.integrations.gmail_client import GmailClient

    hub = FakeHub()
    service = MagicMock()
    users = service.users.return_value
    users.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    users.messages.return_value.get.return_value.execute.return_value = {
        "id": "m1",
        "snippet": "preview",
        "payload": {
            "headers": [
                {"name": "From", "value": "a@b.com"},
                {"name": "Subject", "value": "Hello"},
                {"name": "Date", "value": "Mon, 16 Jun 2026 10:00:00 +0000"},
            ]
        },
    }

    client = GmailClient(hub=hub)
    client._service = service

    with patch(
        "backend.integrations.gmail_client.database.log_audit",
        new=AsyncMock(return_value=None),
    ):
        await client.get_inbox()

    comms = next(e for e in hub.events if isinstance(e, CommsEvent))
    assert comms.type == "comms"
    assert comms.slack is None
    assert comms.gmail == [
        {
            "id": "m1",
            "sender": "a@b.com",
            "subject": "Hello",
            "snippet": "preview",
            "unread": True,
            "timestamp": "Mon, 16 Jun 2026 10:00:00 +0000",
        }
    ]
