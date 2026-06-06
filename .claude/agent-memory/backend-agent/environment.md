---
name: environment
description: Backend dev environment quirks — how to run Python, missing toolchains, repo state
metadata:
  type: project
---

The Jarvis backend runs from a local venv, NOT via `uv` (uv is not on PATH in this shell). Invoke Python directly: `.venv\Scripts\python.exe -m backend.main` (or `.venv/Scripts/python.exe` from Bash tool).

**Why:** uv was used to create the env during Phase 1 but isn't exposed on PATH here.
**How to apply:** When running/verifying backend code, call the venv interpreter at `C:\Users\User\appsbyG\Jarvis\.venv\Scripts\python.exe` directly. Don't reach for `uv run`.

Other env facts:
- Project root IS a git repo (branch `master`, remote github.com/GDGuzman11/jarvis). `git log`/`git blame` are available.
- Rust/cargo NOT installed — Tauri native build (Phases 7 & 10) will need rustup first.
- `starlette.testclient.TestClient` works for both HTTP and WebSocket tests and drives the real lifespan. To broadcast from the app's event loop inside a TestClient block, use `client.portal.call(hub.broadcast, event)`.
