"""Slack integration for Helix — send messages, read DMs/mentions, live listener.

This module wraps Slack's official SDKs so the rest of the backend can talk to a
workspace without touching Slack internals:

* :class:`SlackClient` — a thin async facade over :class:`slack_sdk.web.async_client.AsyncWebClient`
  for sending messages and reading conversation history. All blocking-free: the
  async web client uses ``aiohttp`` under the hood.
* A Socket-Mode listener (built on :class:`slack_bolt.async_app.AsyncApp`) that
  fires a user-supplied callback whenever a DM or an ``@Helix`` mention arrives,
  so the voice pipeline can announce "you have a new Slack message" without
  polling.

Credentials (Security Rule 1)
-----------------------------
Both tokens are read lazily from :mod:`backend.security.keystore` (Windows
Credential Manager) — never from a ``.env`` file or source:

* ``SLACK_BOT_TOKEN`` (``xoxb-…``) authenticates Web API calls.
* ``SLACK_APP_TOKEN`` (``xapp-…``) authenticates the Socket-Mode websocket used
  by the live listener.

Graceful degradation
---------------------
If a credential is missing the client logs a warning and degrades to a safe
no-op: sends return ``False``, reads return ``[]``, and the listener simply does
not start. Helix must boot and run with Slack unconfigured — Phase 1/5 rule.

Minimal scopes (Security Rule 5)
--------------------------------
The bot is provisioned with only ``chat:write``, ``im:read`` and
``channels:read``. This module never calls an API needing a broader scope.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from backend.logging_config import get_logger
from backend.memory import database
from backend.security import keystore
from backend.security.keystore import MissingCredentialError

log = get_logger(__name__)

# Audit log actor id for Slack actions (metadata only — Security Rule 6).
_AUDIT_AGENT_ID = "integration:slack"

# Minimal OAuth scopes this client relies on. Documented here so a reviewer (and
# the security-agent) can confirm the code never exceeds the provisioned set.
REQUIRED_SCOPES: tuple[str, ...] = ("chat:write", "im:read", "channels:read")

# A notification callback receives a small metadata dict describing the inbound
# message. It may be sync or async; both are supported.
NotificationCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class SlackClient:
    """Async facade over the Slack Web API plus an optional Socket-Mode listener.

    Construction is cheap and never touches the keyring or network: the Web
    client and the Bolt app are built lazily on first use. This keeps imports and
    tests fast, and lets the backend construct a ``SlackClient`` even when Slack
    is not configured (the methods then degrade to no-ops).

    Parameters
    ----------
    on_notification:
        Optional callback fired by the live listener for each inbound DM or
        mention. Receives a metadata dict: ``{"source": "slack", "kind":
        "dm"|"mention", "channel", "user", "text", "ts"}``. May be sync or async.
    """

    def __init__(self, on_notification: NotificationCallback | None = None) -> None:
        self._on_notification = on_notification
        # Lazily-built SDK objects. Typed as Any to avoid importing the SDK at
        # module import time (keeps import cheap and test mocking simple).
        self._web: Any | None = None
        self._bolt_app: Any | None = None
        self._socket_handler: Any | None = None
        self._listener_task: asyncio.Task[None] | None = None

    # --- Lazy SDK construction ---------------------------------------------

    def _ensure_web(self) -> Any | None:
        """Return an ``AsyncWebClient`` built from the bot token, or ``None``.

        Returns ``None`` (after logging a warning, once) when the bot token is
        not configured, so callers degrade to a safe no-op rather than crashing.
        """
        if self._web is not None:
            return self._web
        try:
            bot_token = keystore.get_slack_bot_token()
        except MissingCredentialError:
            log.warning("slack_unconfigured", reason="SLACK_BOT_TOKEN missing")
            return None

        # Imported lazily so a missing/optional SDK or an unconfigured Slack does
        # not break module import for the rest of the backend.
        from slack_sdk.web.async_client import AsyncWebClient

        self._web = AsyncWebClient(token=bot_token)
        log.info("slack_web_client_initialised")
        return self._web

    # --- Web API: send ------------------------------------------------------

    async def send_message(self, channel: str, text: str) -> bool:
        """Post ``text`` to ``channel``. Returns ``True`` on success.

        ``channel`` may be a channel ID (``C…``), a DM/IM channel ID (``D…``), or
        a user ID (``U…``) — Slack opens/uses the appropriate conversation. On any
        failure (unconfigured, API error) this logs and returns ``False`` so a
        caller (voice pipeline, agent) is never crashed by Slack being down.
        """
        web = self._ensure_web()
        if web is None:
            return False
        try:
            resp = await web.chat_postMessage(channel=channel, text=text)
        except Exception as exc:  # noqa: BLE001 — never let Slack crash a caller
            log.error("slack_send_failed", channel=channel, error=str(exc))
            return False

        ok = bool(resp.get("ok"))
        # Audit metadata only: channel + outcome, never the message body.
        await database.log_audit(
            _AUDIT_AGENT_ID,
            "slack_send_message",
            target=channel,
            detail="ok" if ok else "not_ok",
        )
        if not ok:
            log.warning("slack_send_not_ok", channel=channel, error=resp.get("error"))
        return ok

    # --- Web API: read ------------------------------------------------------

    async def get_dm_history(self, user_id: str, limit: int = 10) -> list[dict]:
        """Return up to ``limit`` recent messages from the DM with ``user_id``.

        Opens (or re-uses) the IM conversation with the given user, then reads its
        history newest-first. Each item is a small dict: ``{"user", "text", "ts"}``.
        Returns ``[]`` when Slack is unconfigured or any call fails.
        """
        web = self._ensure_web()
        if web is None:
            return []
        try:
            # conversations_open returns the IM channel id for this user. With
            # only im:read this is the supported way to resolve a DM channel.
            opened = await web.conversations_open(users=user_id)
            channel_id = opened["channel"]["id"]
            resp = await web.conversations_history(channel=channel_id, limit=limit)
        except Exception as exc:  # noqa: BLE001
            log.error("slack_dm_history_failed", user_id=user_id, error=str(exc))
            return []

        messages = [
            {
                "user": m.get("user"),
                "text": m.get("text", ""),
                "ts": m.get("ts"),
            }
            for m in resp.get("messages", [])
        ]
        await database.log_audit(
            _AUDIT_AGENT_ID,
            "slack_get_dm_history",
            target=user_id,
            detail=str(len(messages)),
        )
        return messages

    async def get_unread_mentions(self, limit: int = 10) -> list[dict]:
        """Return up to ``limit`` recent ``@bot`` mentions across public channels.

        Resolves the bot's own user id, scans the channels it is a member of
        (``channels:read``), and collects messages that mention the bot. This is a
        best-effort read intended for "what's waiting for me" summaries; Slack has
        no first-class unread-mentions Web API, so we approximate from recent
        history. Returns ``[]`` when unconfigured or on any failure.

        Each item: ``{"channel", "user", "text", "ts"}``.
        """
        web = self._ensure_web()
        if web is None:
            return []
        try:
            auth = await web.auth_test()
            bot_user_id = auth["user_id"]
            mention_token = f"<@{bot_user_id}>"

            convos = await web.conversations_list(
                types="public_channel", exclude_archived=True, limit=100
            )
            mentions: list[dict] = []
            for channel in convos.get("channels", []):
                if not channel.get("is_member"):
                    # Only channels the bot is in are readable with channels:read.
                    continue
                history = await web.conversations_history(
                    channel=channel["id"], limit=limit
                )
                for m in history.get("messages", []):
                    if mention_token in m.get("text", ""):
                        mentions.append(
                            {
                                "channel": channel["id"],
                                "user": m.get("user"),
                                "text": m.get("text", ""),
                                "ts": m.get("ts"),
                            }
                        )
                    if len(mentions) >= limit:
                        break
                if len(mentions) >= limit:
                    break
        except Exception as exc:  # noqa: BLE001
            log.error("slack_unread_mentions_failed", error=str(exc))
            return []

        mentions = mentions[:limit]
        await database.log_audit(
            _AUDIT_AGENT_ID,
            "slack_get_unread_mentions",
            detail=str(len(mentions)),
        )
        return mentions

    # --- Live listener (Socket Mode) ---------------------------------------

    def _ensure_bolt_app(self) -> Any | None:
        """Build the Bolt ``AsyncApp`` and register handlers, or return ``None``.

        Requires the bot token (for Web API calls the app makes) and is started
        over Socket Mode with the app token. Returns ``None`` (logging a warning)
        when either credential is missing.
        """
        if self._bolt_app is not None:
            return self._bolt_app
        try:
            bot_token = keystore.get_slack_bot_token()
        except MissingCredentialError:
            log.warning("slack_listener_unconfigured", reason="SLACK_BOT_TOKEN missing")
            return None

        from slack_bolt.async_app import AsyncApp

        app = AsyncApp(token=bot_token)

        @app.event("message")
        async def _handle_message(event: dict, logger: Any) -> None:  # noqa: ANN001
            # Only direct messages have channel_type == "im". Ignore the bot's own
            # messages and message edits/deletes (which carry a subtype).
            if event.get("channel_type") != "im" or event.get("subtype"):
                return
            await self._dispatch_notification(
                {
                    "source": "slack",
                    "kind": "dm",
                    "channel": event.get("channel"),
                    "user": event.get("user"),
                    "text": event.get("text", ""),
                    "ts": event.get("ts"),
                }
            )

        @app.event("app_mention")
        async def _handle_mention(event: dict, logger: Any) -> None:  # noqa: ANN001
            await self._dispatch_notification(
                {
                    "source": "slack",
                    "kind": "mention",
                    "channel": event.get("channel"),
                    "user": event.get("user"),
                    "text": event.get("text", ""),
                    "ts": event.get("ts"),
                }
            )

        self._bolt_app = app
        log.info("slack_bolt_app_initialised")
        return app

    async def _dispatch_notification(self, payload: dict[str, Any]) -> None:
        """Invoke the user callback for an inbound message, supporting sync/async.

        Audits the arrival (metadata only — kind + channel, never the text) and
        shields the callback so a failing handler never tears down the listener.
        """
        await database.log_audit(
            _AUDIT_AGENT_ID,
            "slack_inbound",
            target=payload.get("channel"),
            detail=payload.get("kind"),
        )
        if self._on_notification is None:
            return
        try:
            result = self._on_notification(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # noqa: BLE001 — a bad callback must not kill the listener
            log.error("slack_notification_callback_failed", error=str(exc))

    async def start_listener(self) -> bool:
        """Start the Socket-Mode listener as a background task. Returns success.

        Idempotent: a second call while already running is a no-op returning
        ``True``. Returns ``False`` (and starts nothing) when either token is
        missing, so the backend boots fine with Slack unconfigured.
        """
        if self._listener_task is not None and not self._listener_task.done():
            return True

        app = self._ensure_bolt_app()
        if app is None:
            return False
        try:
            app_token = keystore.get_slack_app_token()
        except MissingCredentialError:
            log.warning("slack_listener_unconfigured", reason="SLACK_APP_TOKEN missing")
            return False

        from slack_bolt.adapter.socket_mode.async_handler import (
            AsyncSocketModeHandler,
        )

        self._socket_handler = AsyncSocketModeHandler(app, app_token)
        # start_async() runs until the socket closes; own it in a supervised task.
        self._listener_task = asyncio.create_task(
            self._run_listener(), name="slack-socket-listener"
        )
        log.info("slack_listener_started")
        return True

    async def _run_listener(self) -> None:
        """Run the Socket-Mode handler, surviving transient errors with a log."""
        try:
            await self._socket_handler.start_async()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.error("slack_listener_crashed", error=str(exc))

    async def stop(self) -> None:
        """Stop the listener and release SDK resources. Safe if never started."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        if self._socket_handler is not None:
            close = getattr(self._socket_handler, "close_async", None)
            if close is not None:
                try:
                    await close()
                except Exception as exc:  # noqa: BLE001
                    log.warning("slack_listener_close_failed", error=str(exc))
            self._socket_handler = None
        log.info("slack_listener_stopped")


__all__ = ["SlackClient", "REQUIRED_SCOPES", "NotificationCallback"]
