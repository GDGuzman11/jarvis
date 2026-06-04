---
name: build-run-commands
description: Exact commands to run backend, build frontend, and push for the Jarvis project (uv is NOT on PATH)
metadata:
  type: reference
---

Project root: `C:\Users\User\appsbyG\Jarvis`. Git remote: https://github.com/GDGuzman11/jarvis

- Backend run: `.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
- Backend tests: `.venv\Scripts\python.exe -m pytest backend/ -v`
- Frontend build: `cd frontend && pnpm build` (clean = tsc 0 errors + vite "built in Xs")
- Native launch: `pnpm tauri dev` (Rust 1.96.0 IS installed as of 2026-06-04)

**Why:** `uv` is not on PATH — always invoke Python via the venv binary directly. `pnpm build` is the
frontend verification gate since there is no Vitest harness yet.

**How to apply:** Use these exact invocations when delegating to agents or when the debugger-agent runs
verification. Commit + push after each completed+verified task (user instruction, 2026-06-04).
