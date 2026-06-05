# Jarvis — Security Audit History

> Maintained by security-agent. Add new audit entries at the top. Each entry includes date, scope, result, and findings.

---

## Phase 10 — Final Security Audit (2026-06-03) — PASSED, 0 Critical / 0 High

Final pre-packaging audit. Re-ran every Phase 8 check plus 7 Phase 10-specific items. No new findings; all prior accepted risks unchanged.

| # | Check | Result |
|---|---|---|
| 1 | Secret-pattern grep across codebase (`sk-ant-`, `xoxb-`, `xapp-`, `AIza…`, `GOCSPX-`, `AKIA…`, PEM keys; excl. `OpenJarvis/`) | **0 real matches** — only doc/test lines that name the patterns themselves |
| 2 | FastAPI binds 127.0.0.1 only | **Pass** — `main.HOST == "127.0.0.1"`; `uvicorn.run(host=HOST)`; no `host="0.0.0.0"` |
| 3 | WebSocket Origin validation present | **Pass** — `_is_allowed_ws_origin()` + `ALLOWED_WS_ORIGINS` still guard `/ws`; untrusted Origin → close 1008 before accept |
| 4 | `setup_wizard.py` POST /setup/credential allowlists name + never echoes value | **Pass** — `name` validated against `_NAME_TO_KEYSTORE`/`REQUIRED_CREDENTIALS`, unknown → 400; response returns only `{stored(name), complete, missing}` — no value |
| 5 | Rename endpoint validates input + no internal-state leak | **Pass** — `name.strip()`, empty → 400, >50 chars → 400, unknown agent → 404 |
| 6 | `AudioLevelEvent` carries no sensitive data | **Pass** — fields are `level: float` (0.0–1.0) + `type` + `timestamp` only |
| 7 | No new real `.env` created in Phase 10 | **Pass** — only `.env.example` (placeholders) at repo root |

Also re-confirmed (no regressions): keystore.py keyring-only/no hardcoded secrets; no `verify=False`/`CERT_NONE`/unverified SSL context anywhere; Gmail/Slack scopes minimal; `audit_log` metadata-only.

---

## Phase 8 — Security Hardening Audit (2026-06-03) — 0 Critical, 0 High after fixes

All 12 audit items checked. 1 Medium fixed, Low/Info items documented below.

| Severity | Description | File:Line | Status |
|---|---|---|---|
| Medium | WebSocket `/ws` endpoint had no Origin-header validation — any local/remote browser page could open `ws://127.0.0.1:8000/ws` and read Jarvis's live event stream (cross-site WebSocket hijacking). | `backend/main.py:194` (pre-fix) | **Fixed** — added `_is_allowed_ws_origin()` + `ALLOWED_WS_ORIGINS`; `/ws` now rejects untrusted Origins with close code 1008 before accept. Verified: `http://evil.com` rejected, `tauri://localhost` accepted, native (no-Origin) clients allowed. |
| Low | No `auth.py` in `backend/security/` (referenced in the project file-structure tree). OAuth token refresh is instead handled inline by google-auth in `gmail_client.py`. | `backend/security/` | **Accepted** — google-auth auto-refreshes via the stored refresh token (`GMAIL_REFRESH_TOKEN` in keyring); a separate `auth.py` is not required. |
| Low | Project root had no `.gitignore` — risk of accidentally committing a real `.env`/`data/jarvis.db`. | repo root | **Resolved (2026-06-04)** — `.gitignore` added (excludes `.env`, `data/`, `workspace/`, `.venv/`, `target/`, `*.db`, `*.faiss`, audio files, installer artifacts). Repo pushed to https://github.com/GDGuzman11/jarvis. |
| Info | `browse_url` tool blocks `file://`/`data://`/`javascript:` schemes but does not block requests to private/loopback IP ranges (SSRF to internal services). | `backend/tools/browser.py:44` | **Accepted for now** — agent-initiated, local-only deployment. Consider an IP-range denylist if the browser tool is ever exposed beyond trusted agents. |
| Info | All external API calls go through official SDKs with default SSL verification. No `verify=False` / `CERT_NONE` anywhere. | backend-wide | **Pass** — HTTPS + SSL verification confirmed. |

### Verification Details (Phase 8)
- **Secrets:** grep for `sk-ant-`, `xoxb-`, `xapp-`, `AIza…`, `GOCSPX-`, PEM private keys across all `.py/.ts/.tsx/.json` (excl. `OpenJarvis/`) → **0 matches**.
- **Keystore:** `keystore.py` is keyring-only, no hardcoded values; typed get/set for all 10 credentials.
- **Bind:** `HOST == "127.0.0.1"` (asserted at import); no real `0.0.0.0` binding.
- **WS Origin:** guard verified via import test (evil rejected / tauri accepted / native allowed).
- **Voice sanitisation:** `stt.transcribe()` calls `sanitize_transcript()` (strip Unicode-C control chars, cap 2000).
- **File sandbox:** `../../etc/passwd`, abs `C:/Windows/...`, `..\..\secret.txt` all raise `PathTraversalError`.
- **Code sandbox:** `os.system`, `import sys`, `import subprocess`, `open(...)`, `().__class__.__bases__` all blocked.
- **Scopes:** Gmail = `gmail.readonly` + `gmail.send` only; Slack = `chat:write`, `im:read`, `channels:read` only.
- **OAuth refresh:** google-auth `Credentials(refresh_token=…)` auto-refreshes Gmail; Slack bot tokens are long-lived.
- **Audit log:** `audit_log` columns = `id, agent_id, action, target, detail, created_at` — **no message-content column**.
