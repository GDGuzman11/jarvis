"""Gmail integration for Helix — read inbox, send and draft email.

This module wraps the Google Gmail API (v1) behind a small async facade so the
voice pipeline and agents can read and write mail without touching Google's
synchronous client library or OAuth plumbing.

Async over a sync SDK
---------------------
``google-api-python-client`` is synchronous and blocking. Every network call is
therefore dispatched to the default thread executor via
:func:`asyncio.to_thread` so the FastAPI event loop is never blocked. The public
methods are ``async`` and await those threads.

Credentials (Security Rule 1)
-----------------------------
OAuth client config and the long-lived refresh token are read lazily from
:mod:`backend.security.keystore` (Windows Credential Manager), never from a
``.env`` file or source:

* ``GMAIL_CLIENT_ID`` / ``GMAIL_CLIENT_SECRET`` — the OAuth app credentials.
* ``GMAIL_REFRESH_TOKEN`` — the long-lived token used to mint short-lived access
  tokens; google-auth refreshes automatically on demand.

Graceful degradation
---------------------
If any credential is missing the client logs a warning and degrades to a safe
no-op: :meth:`get_inbox` returns ``[]``, :meth:`send_email` returns ``False``,
and :meth:`draft_email` returns ``""``. Helix must boot and run with Gmail
unconfigured.

Minimal scopes (Security Rule 5)
--------------------------------
Only ``gmail.readonly`` (read inbox) and ``gmail.send`` (send + draft) are
requested. ``gmail.send`` covers creating drafts via ``users.drafts.create``.
"""

from __future__ import annotations

import asyncio
import base64
from email.message import EmailMessage
from typing import Any

from backend.logging_config import get_logger
from backend.memory import database
from backend.security import keystore
from backend.security.keystore import MissingCredentialError

log = get_logger(__name__)

# Audit log actor id for Gmail actions (metadata only — Security Rule 6).
_AUDIT_AGENT_ID = "integration:gmail"

# OAuth token endpoint used to refresh the access token from the refresh token.
# This is Google's public token URL, not a secret (S105 false positive).
_TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105

# Minimal scopes (Security Rule 5). gmail.send permits drafts.create + send;
# gmail.readonly permits reading the inbox.
SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
)


class GmailClient:
    """Async facade over the Gmail API for reading and sending mail.

    Construction is cheap and never touches the keyring or network: the
    underlying Google service is built lazily on first use, in a worker thread.
    This keeps imports/tests fast and lets the backend construct a ``GmailClient``
    even when Gmail is unconfigured (methods then degrade to no-ops).
    """

    def __init__(self) -> None:
        # Lazily-built Google API service object. Typed Any to avoid importing the
        # SDK at module import time.
        self._service: Any | None = None
        # Guards lazy build so concurrent first calls don't race on construction.
        self._build_lock = asyncio.Lock()

    # --- Lazy service construction -----------------------------------------

    def _build_service_sync(self) -> Any | None:
        """Build the Gmail API service from keyring credentials (blocking).

        Runs inside a thread executor. Returns ``None`` (after a single warning)
        when any credential is missing so callers degrade to a no-op.
        """
        try:
            client_id = keystore.get_gmail_client_id()
            client_secret = keystore.get_gmail_client_secret()
            refresh_token = keystore.get_gmail_refresh_token()
        except MissingCredentialError as exc:
            log.warning("gmail_unconfigured", reason=str(exc.username))
            return None

        # Imported lazily so an unconfigured Gmail never breaks module import.
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri=_TOKEN_URI,
            scopes=list(SCOPES),
        )
        # cache_discovery=False avoids a noisy file-cache warning and keeps the
        # build self-contained (no on-disk discovery cache to manage).
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        log.info("gmail_service_initialised")
        return service

    async def _ensure_service(self) -> Any | None:
        """Return the Gmail service, building it in a thread on first use."""
        if self._service is not None:
            return self._service
        async with self._build_lock:
            if self._service is None:
                self._service = await asyncio.to_thread(self._build_service_sync)
            return self._service

    # --- Read ---------------------------------------------------------------

    async def get_inbox(self, limit: int = 10) -> list[dict]:
        """Return up to ``limit`` recent unread inbox messages.

        Each item: ``{"id", "from", "subject", "snippet"}``. Returns ``[]`` when
        Gmail is unconfigured or any call fails — never raises to the caller.
        """
        service = await self._ensure_service()
        if service is None:
            return []
        try:
            messages = await asyncio.to_thread(self._get_inbox_sync, service, limit)
        except Exception as exc:  # noqa: BLE001 — never let Gmail crash a caller
            log.error("gmail_get_inbox_failed", error=str(exc))
            return []

        await database.log_audit(
            _AUDIT_AGENT_ID, "gmail_get_inbox", detail=str(len(messages))
        )
        return messages

    @staticmethod
    def _get_inbox_sync(service: Any, limit: int) -> list[dict]:
        """Blocking inbox read: list unread inbox ids, then fetch each header."""
        listing = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX", "UNREAD"], maxResults=limit)
            .execute()
        )
        out: list[dict] = []
        for ref in listing.get("messages", []):
            # 'metadata' format avoids pulling full bodies — cheaper and keeps us
            # within the spirit of reading just enough to summarise.
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"],
                )
                .execute()
            )
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            out.append(
                {
                    "id": msg.get("id"),
                    "from": headers.get("from", ""),
                    "subject": headers.get("subject", ""),
                    "snippet": msg.get("snippet", ""),
                }
            )
        return out

    # --- Write --------------------------------------------------------------

    @staticmethod
    def _encode_message(to: str, subject: str, body: str) -> dict[str, str]:
        """Build a base64url-encoded raw RFC 2822 message for the Gmail API."""
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return {"raw": raw}

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send an email. Returns ``True`` on success.

        Returns ``False`` when Gmail is unconfigured or the API call fails — the
        voice pipeline/agent is never crashed by a send failure.
        """
        service = await self._ensure_service()
        if service is None:
            return False
        try:
            await asyncio.to_thread(self._send_sync, service, to, subject, body)
        except Exception as exc:  # noqa: BLE001
            log.error("gmail_send_failed", error=str(exc))
            await database.log_audit(
                _AUDIT_AGENT_ID, "gmail_send_email", target=to, detail="failed"
            )
            return False

        await database.log_audit(
            _AUDIT_AGENT_ID, "gmail_send_email", target=to, detail="ok"
        )
        return True

    def _send_sync(self, service: Any, to: str, subject: str, body: str) -> dict:
        """Blocking send via users.messages.send."""
        return (
            service.users()
            .messages()
            .send(userId="me", body=self._encode_message(to, subject, body))
            .execute()
        )

    async def draft_email(self, to: str, subject: str, body: str) -> str:
        """Create a draft email. Returns the draft id, or ``""`` on failure.

        Returns ``""`` when Gmail is unconfigured or the API call fails.
        """
        service = await self._ensure_service()
        if service is None:
            return ""
        try:
            draft = await asyncio.to_thread(
                self._draft_sync, service, to, subject, body
            )
        except Exception as exc:  # noqa: BLE001
            log.error("gmail_draft_failed", error=str(exc))
            return ""

        draft_id = draft.get("id", "")
        await database.log_audit(
            _AUDIT_AGENT_ID, "gmail_draft_email", target=to, detail=draft_id or "no_id"
        )
        return draft_id

    def _draft_sync(self, service: Any, to: str, subject: str, body: str) -> dict:
        """Blocking draft creation via users.drafts.create."""
        return (
            service.users()
            .drafts()
            .create(
                userId="me",
                body={"message": self._encode_message(to, subject, body)},
            )
            .execute()
        )


__all__ = ["GmailClient", "SCOPES"]
