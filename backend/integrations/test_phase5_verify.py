"""Phase 5 — Communication Integrations verification tests.

Covers the six Phase 5 acceptance checks for Slack + Gmail:

1. Missing credentials: every keystore getter raises MissingCredentialError, so
   each client degrades to a safe no-op (sends False, reads [], drafts "",
   listener False).
2. Slack send: chat_postMessage -> {"ok": True} => send_message True.
3. Slack read: conversations_history -> messages => get_dm_history returns
   normalized {user, text, ts} dicts.
4. Slack listener dispatch: _dispatch_notification awaits the on_notification
   callback with the payload.
5. Gmail send/draft/inbox: against a mocked Google service, send_email True,
   draft_email returns an id string, get_inbox returns {from, subject, snippet}
   dicts.
6. Lifespan wiring: TestClient(app) with keystore patched -> app.state has both
   clients and /health returns 200.

All tests mock the Slack/Google SDKs and patch database.log_audit, so no real
credentials, network, or shared on-disk DB writes occur.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.integrations.gmail_client import GmailClient
from backend.integrations.slack_client import SlackClient
from backend.security.keystore import MissingCredentialError


# --- shared fixtures --------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_audit_writes():
    """Stub database.log_audit so tests never touch the real on-disk DB.

    Both clients call database.log_audit (imported as ``database`` in each
    module) on success/inbound paths; patch it where it is looked up.
    """
    with (
        patch(
            "backend.integrations.slack_client.database.log_audit",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "backend.integrations.gmail_client.database.log_audit",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


def _raise_missing(username: str = "TEST") -> Any:
    raise MissingCredentialError(username)


# --- 1. Missing credentials => safe no-ops ----------------------------------


@patch("backend.integrations.slack_client.keystore.get_slack_app_token", _raise_missing)
@patch("backend.integrations.slack_client.keystore.get_slack_bot_token", _raise_missing)
async def test_slack_missing_credentials_degrades_to_noop() -> None:
    client = SlackClient(on_notification=AsyncMock())

    assert await client.send_message("C123", "hi") is False
    assert await client.get_dm_history("U123") == []
    assert await client.get_unread_mentions() == []
    assert await client.start_listener() is False


@patch(
    "backend.integrations.gmail_client.keystore.get_gmail_refresh_token",
    _raise_missing,
)
@patch(
    "backend.integrations.gmail_client.keystore.get_gmail_client_secret",
    _raise_missing,
)
@patch(
    "backend.integrations.gmail_client.keystore.get_gmail_client_id",
    _raise_missing,
)
async def test_gmail_missing_credentials_degrades_to_noop() -> None:
    client = GmailClient()

    assert await client.get_inbox() == []
    assert await client.send_email("a@b.com", "s", "b") is False
    assert await client.draft_email("a@b.com", "s", "b") == ""


# --- 2. Slack send ----------------------------------------------------------


async def test_slack_send_message_success() -> None:
    web = MagicMock()
    web.chat_postMessage = AsyncMock(return_value={"ok": True})

    client = SlackClient()
    # Inject the mocked web client directly so _ensure_web short-circuits.
    client._web = web

    assert await client.send_message("C123", "hello") is True
    web.chat_postMessage.assert_awaited_once_with(channel="C123", text="hello")


# --- 3. Slack read ----------------------------------------------------------


async def test_slack_get_dm_history_normalizes() -> None:
    web = MagicMock()
    web.conversations_open = AsyncMock(
        return_value={"channel": {"id": "D999"}}
    )
    web.conversations_history = AsyncMock(
        return_value={
            "messages": [
                {"user": "U1", "text": "first", "ts": "1.1"},
                {"user": "U2", "text": "second", "ts": "2.2"},
            ]
        }
    )

    client = SlackClient()
    client._web = web

    history = await client.get_dm_history("U1", limit=10)
    assert history == [
        {"user": "U1", "text": "first", "ts": "1.1"},
        {"user": "U2", "text": "second", "ts": "2.2"},
    ]
    for item in history:
        assert set(item) == {"user", "text", "ts"}
    web.conversations_history.assert_awaited_once_with(channel="D999", limit=10)


# --- 4. Slack listener dispatch ---------------------------------------------


async def test_slack_dispatch_notification_awaits_callback() -> None:
    callback = AsyncMock()
    client = SlackClient(on_notification=callback)

    payload = {
        "source": "slack",
        "kind": "dm",
        "channel": "D1",
        "user": "U1",
        "text": "ping",
        "ts": "3.3",
    }
    await client._dispatch_notification(payload)

    callback.assert_awaited_once_with(payload)


# --- 5. Gmail send / draft / inbox ------------------------------------------


def _gmail_service_mock(
    *, send_id: str = "msg-1", draft_id: str = "draft-1"
) -> MagicMock:
    """Build a MagicMock mimicking the chained Gmail service call surface."""
    service = MagicMock()
    users = service.users.return_value

    # users().messages().send(...).execute()
    users.messages.return_value.send.return_value.execute.return_value = {
        "id": send_id
    }
    # users().drafts().create(...).execute()
    users.drafts.return_value.create.return_value.execute.return_value = {
        "id": draft_id
    }
    # users().messages().list(...).execute() -> ids
    users.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    # users().messages().get(...).execute() -> headers + snippet
    users.messages.return_value.get.return_value.execute.return_value = {
        "id": "m1",
        "snippet": "a short preview",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Hello there"},
            ]
        },
    }
    return service


async def test_gmail_send_email_success() -> None:
    service = _gmail_service_mock()
    client = GmailClient()
    client._service = service

    assert await client.send_email("a@b.com", "Subj", "Body") is True


async def test_gmail_draft_email_returns_id() -> None:
    service = _gmail_service_mock(draft_id="draft-xyz")
    client = GmailClient()
    client._service = service

    draft_id = await client.draft_email("a@b.com", "Subj", "Body")
    assert isinstance(draft_id, str)
    assert draft_id == "draft-xyz"


async def test_gmail_get_inbox_normalizes() -> None:
    service = _gmail_service_mock()
    client = GmailClient()
    client._service = service

    inbox = await client.get_inbox(limit=10)
    assert len(inbox) == 1
    item = inbox[0]
    assert {"from", "subject", "snippet"} <= set(item)
    assert item["from"] == "sender@example.com"
    assert item["subject"] == "Hello there"
    assert item["snippet"] == "a short preview"


# --- 6. Lifespan wiring (TestClient) ----------------------------------------


def test_lifespan_wires_both_clients() -> None:
    """Drive the real ASGI lifespan with keystore patched so Slack/Gmail stay in
    no-op mode; assert both clients are on app.state and /health is 200.

    Patches every keystore getter to raise MissingCredentialError, so the Slack
    listener does not start and Gmail never builds a real service — yet both
    client objects must still be constructed and exposed on app.state.
    """
    from starlette.testclient import TestClient

    from backend.main import app

    with (
        patch(
            "backend.integrations.slack_client.keystore.get_slack_bot_token",
            _raise_missing,
        ),
        patch(
            "backend.integrations.slack_client.keystore.get_slack_app_token",
            _raise_missing,
        ),
        patch(
            "backend.integrations.gmail_client.keystore.get_gmail_client_id",
            _raise_missing,
        ),
        patch(
            "backend.integrations.gmail_client.keystore.get_gmail_client_secret",
            _raise_missing,
        ),
        patch(
            "backend.integrations.gmail_client.keystore.get_gmail_refresh_token",
            _raise_missing,
        ),
        TestClient(app) as client,
    ):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        assert isinstance(app.state.slack_client, SlackClient)
        assert isinstance(app.state.gmail_client, GmailClient)
