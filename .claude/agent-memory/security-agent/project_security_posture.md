---
name: project-security-posture
description: Jarvis security architecture decisions and accepted-risk notes a future audit should not re-flag as new findings
metadata:
  type: project
---

Jarvis Phase 8 security audit passed 2026-06-03 with 0 Critical / 0 High. Key
architecture facts so future audits don't re-investigate from scratch or
re-raise accepted risks as new findings.

**Fact:** OAuth refresh has no dedicated `backend/security/auth.py` despite the
CLAUDE.md file-structure tree listing one. Gmail token refresh is handled inline
by google-auth via `Credentials(refresh_token=...)` in `gmail_client.py`. Slack
bot tokens (`xoxb-`) are long-lived and need no refresh.
**Why:** A separate auth module would be redundant — google-auth already
auto-refreshes. Decided not to add a placeholder module.
**How to apply:** Do NOT flag missing `auth.py` as a finding; it's accepted Low.

**Fact:** `browse_url` (`backend/tools/browser.py`) blocks `file://`/`data:`/
`javascript:` via a scheme allowlist but does NOT block private/loopback IP
ranges (no SSRF IP denylist).
**Why:** Agent-initiated, local-only deployment; scheme allowlist removes the
local-file/inline-payload vector, which was the priority.
**How to apply:** This is a known Info-level accepted risk. Only escalate if the
browser tool gets exposed beyond trusted agents.

**Fact:** The Medium finding fixed this round was missing WebSocket Origin
validation on `/ws` in `backend/main.py`. CORS middleware does NOT protect the WS
handshake. Fix = `_is_allowed_ws_origin()` + `ALLOWED_WS_ORIGINS`, rejecting
untrusted Origins with close code 1008 before accept; native (no-Origin) clients
are intentionally allowed.
**How to apply:** If this guard ever disappears in a future diff, that's a
regression of a known Medium — re-raise immediately.

**Verified-good (don't re-derive):** keystore.py is keyring-only; only
`.env.example` exists (no real `.env`); HOST pinned to 127.0.0.1; voice input
sanitised via `stt.sanitize_transcript()` (the only path to Claude); file_ops
raises `PathTraversalError` on escape; code_executor (RestrictedPython) blocks
imports/open/dunder-escape; Gmail scopes = readonly+send, Slack = chat:write/
im:read/channels:read; `audit_log` table is metadata-only (cols: id, agent_id,
action, target, detail, created_at — no message-content column).
