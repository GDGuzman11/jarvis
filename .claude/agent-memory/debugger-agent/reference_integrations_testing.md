---
name: integrations-testing
description: Non-obvious gotchas when testing the Phase 5 Slack + Gmail integration clients
metadata:
  type: reference
---

Verifying Phase 5 (`backend/integrations/slack_client.py`, `gmail_client.py`). Both clients build their SDK lazily and store it on a private attr — inject mocks directly to skip keyring/network: `SlackClient()._web = mock` and `GmailClient()._service = mock`. That bypasses `_ensure_web`/`_ensure_service` so no credential is read.

**Patch keystore where it is looked up, not at source.** Both modules do `from backend.security import keystore` then call `keystore.get_*`. Patch `backend.integrations.slack_client.keystore.get_slack_bot_token` (and `get_slack_app_token`), and `backend.integrations.gmail_client.keystore.get_gmail_client_id`/`_secret`/`_refresh_token`. Make the patch a function that *raises* `MissingCredentialError(username)` to exercise the no-op degradation path (sends→False, reads→[], draft→"").

**Stub `database.log_audit` or you write the real DB.** Every success/inbound path calls `database.log_audit`, which opens the default on-disk SQLite (`data/jarvis.db`). In unit tests patch `backend.integrations.{slack_client,gmail_client}.database.log_audit` with an `AsyncMock` (autouse fixture) so mocked tests don't touch shared state.

**Gmail service is a deep chained mock.** Calls look like `service.users().messages().send(...).execute()` and `.drafts().create(...).execute()` and `.messages().list(...).execute()` + `.messages().get(...).execute()`. With a `MagicMock`, set `service.users.return_value.messages.return_value.send.return_value.execute.return_value = {...}` etc. `get_inbox` returns `{id, from, subject, snippet}` (lowercases header names). Slack web mock needs `chat_postMessage`/`conversations_open`/`conversations_history` as `AsyncMock` (async web client).

**Lifespan test:** patch all keystore getters to raise so Slack listener doesn't start and Gmail never builds a service, then `with TestClient(app)`: assert `app.state.slack_client`/`app.state.gmail_client` are set and `/health` 200. Same TestClient pattern as [[lifespan-testing]] / [[agent-testing]].

Test file: `backend/integrations/test_phase5_verify.py` (9 cases, 6 checks). venv python: see [[uv-path]].
