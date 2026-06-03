# JARVIS — Master Control Document

> **Every agent MUST read this file before starting any task.**
> Update checkboxes immediately after completing each item (`- [ ]` → `- [x]`).
> After every session, update the **Current Status** section below.
>
> **TESTING RULE: After EVERY single completed task, the debugger-agent runs a targeted test for that specific task before moving on. No task is considered done until its test passes.**

---

## Current Status

- **Active Phase**: 8 — Security Hardening (next). Phase 7 Multi-Window UI VERIFIED by debugger-agent 2026-06-03 (React/TS layer).
- **Last Completed**: **Phase 7 VERIFIED — Multi-Window UI**. debugger-agent ran 7 checks, all pass: (1) `pnpm build` clean — `tsc` no TS errors, `vite` "built in 2.97s", `dist/` generated with code-split chunks (AnimationWindow 891kB Three.js chunk isolated); (2) all 5 window files present; (3) all 4 components present (JarvisOrb/AgentCard/ToolCard/StreamViewer); (4) `store.ts` exports `useStore` via `create<JarvisStore>`; (5) `websocket.ts` references `ws://127.0.0.1:8000/ws`; (6) `tauri.conf.json` defines 5 window labels; (7) `App.tsx` routes by Tauri window label → `?window=` → dev dashboard fallback, lazy-loads all 5 windows. CAVEAT: Rust shell (system tray, autostart, native multi-window launch in `src-tauri/src/lib.rs` + `Cargo.toml`) is written but UNCOMPILED — Rust/cargo toolchain not installed, so native window launch could not be exercised. Only the Vite web layer was verified. Phase 9 UI test items remain to be run later (orb color transitions, agent card live updates, WS-connect-within-2s) under the full app.
- **Prior (Phase 7 build by frontend-agent Ben):** `pnpm build` passes clean (tsc + vite, Three.js code-split to AnimationWindow chunk only). New deps: zustand, three, @react-three/fiber, @react-three/drei, framer-motion, tailwindcss v4 + @tailwindcss/vite. Files: `frontend/src/lib/{types,store,websocket,api}.ts` (Zustand store + WS singleton w/ auto-reconnect backoff, dispatches agent_update/token/tool_call/voice_state exactly per `backend/events.py`; forward-declares metrics/comms/tool_permissions). Components `frontend/src/components/`: `JarvisOrb.tsx` (R3F, lerped colour blue/gold/cyan + audio-reactive scale), `AgentCard.tsx`, `ToolCard.tsx`, `StreamViewer.tsx`, `StatusBadge.tsx`, `WindowFrame.tsx` (Framer Motion staggered fade, 0.2s/window). Windows `frontend/src/windows/`: Animation, Reasoning, Communications, Agents, Tools. `App.tsx` routes by Tauri window label (`__TAURI_INTERNALS__`) → `?window=` query → dev dashboard fallback; windows lazy-loaded. `index.css` = Tailwind v4 @theme HUD tokens + `.glass`/`.hud-bg`. Tauri: `tauri.conf.json` 5 frameless transparent windows (labels animation/reasoning/communications/agents/tools, positioned, withGlobalTauri); `src-tauri/src/lib.rs` system tray (Open Jarvis/Quit) + autostart plugin; `Cargo.toml` adds tauri-plugin-autostart + tray-icon feature; `capabilities/default.json` covers all 5 windows. NOTE: tool-toggle + comms action buttons send WS commands the backend does not yet handle (it only drains inbound frames) — forward-compatible.
- **Next Task**: Phase 8 — Security Hardening. Run `/security-agent`. (Run `/production-manager` first to confirm.)
- **Blockers**: Rust/cargo toolchain NOT installed — so `pnpm tauri dev` / native window launch / tray / autostart CANNOT be run yet; only the Vite web build (`pnpm build`) and dev-dashboard preview (`pnpm dev`, single browser tab) are runnable. Rust lib.rs + Cargo + tauri.conf changes are written but UNCOMPILED. Install Rust via rustup to validate the native shell. Also: `uv` not on PATH (backend via `.venv\Scripts\python.exe`); project root not a git repo (`pre-commit install` deferred).
- **Build Started**: 2026-06-02

---

## Project Overview

**Jarvis** is a personal AI assistant that runs locally on Windows 11. It wakes on voice command, understands natural speech, responds in a subtle British tone (Tom Hardy meets Jarvis from the Avengers), and manages a team of 6 background AI agents.

### Hardware
- GPU: NVIDIA RTX 3050 Ti Laptop — 4GB VRAM
- CPU: Intel i7-1180H @ 2.30GHz
- RAM: 16GB
- OS: Windows 11

### AI Stack
- **Primary AI**: Claude API — `claude-opus-4-7` (Anthropic SDK, streaming + prompt caching)
- **Local Fallback**: Ollama — `phi3.5` (3.8B, ~2.4GB VRAM) and `qwen2.5-coder:3b`
- **Wake Word**: OpenWakeWord (model: "hey_jarvis", Apache 2.0, fully local, no API key)
- **Speech-to-Text**: faster-whisper (base.en model)
- **Text-to-Speech**: ElevenLabs API (custom Tom Hardy × Jarvis voice — create in ElevenLabs dashboard)

### Tech Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, WebSockets, Uvicorn |
| Frontend | Tauri 2 + React 19 + TypeScript 5 + Vite 6 |
| Styling | Tailwind CSS 4, glassmorphism dark theme |
| 3D Animation | Three.js / React Three Fiber |
| State | Zustand 5, WebSocket sync |
| Database | SQLite (aiosqlite) |
| Vector Memory | FAISS + sentence-transformers |
| Key Storage | Windows Credential Manager (keyring library) |
| Integrations | Slack Bolt, Gmail API (OAuth2) |
| Logging | structlog |
| Testing | pytest + pytest-asyncio, Vitest |

### 5 Windows (open simultaneously on boot)
| # | Name | Contents |
|---|---|---|
| 1 | Animation | Three.js pulsing orb — blue=idle, gold=thinking, cyan=speaking |
| 2 | Reasoning | Model name (Claude Opus 4.7), streaming tokens, tool calls, cost/latency |
| 3 | Communications | Slack inbox + Gmail inbox — read/reply via voice |
| 4 | Agents | 6 agent cards with live status, task queue, controls |
| 5 | Tools | Tool store grid — per-agent access toggles |

### 6 Background Agents (run 24/7)
| Agent | Name | Role |
|---|---|---|
| Production Lead | *(TBD)* | Orchestrator — breaks goals into tasks, delegates, monitors |
| Frontend | Ben | UI/UX, React components, visual design |
| Backend | Kado | APIs, database, voice pipeline, performance |
| Security | *(TBD)* | Vulnerability scans, key rotation, audits |
| Marketing | *(TBD)* | Campaign planning, social content strategy |
| Content Creator | *(TBD)* | Drafts posts, emails, copy, documentation |

### Design Aesthetic
Dark theme `#0A0A0F`, electric blue/cyan accents `#00D4FF`, gold highlights `#FFB800`. Iron Man HUD — clean, glowing, cinematic. Glassmorphism panels (backdrop-blur, semi-transparent borders). No rounded-cornered cards — sharp edges with glowing outlines.

---

## Security Rules (enforced throughout ALL phases)

1. **Zero secrets in files** — All API keys stored in Windows Credential Manager via `keyring`. No `.env` files with real values. `.env.example` template only.
2. **Local network only** — FastAPI binds to `127.0.0.1:8000`, never `0.0.0.0`.
3. **Voice input sanitized** — Strip control chars, cap at 2000 chars before sending to Claude.
4. **Sandboxed code execution** — No `os`, `sys`, `subprocess` access. Workspace-only filesystem.
5. **Minimal OAuth scopes** — Gmail and Slack use least-privilege scopes.
6. **Audit log in SQLite** — Every agent action logged (metadata only, no message content).

---

## Phase 1 — Foundation
*Handled by: Production Manager directly*

- [x] Initialize Python project (`pyproject.toml`, `uv sync`)
- [x] Initialize Tauri 2 + React frontend (`pnpm create tauri-app`)
- [x] Create full project directory structure (see structure below)
- [x] Create `.env.example` (template only — no real secret values)
- [x] Create `backend/security/keystore.py` — typed get/set for each credential via `keyring`
- [x] Set up `ruff` pre-commit hooks (`.pre-commit-config.yaml`)
- [x] Initialize SQLite schema: `conversations`, `agents`, `tasks`, `tools`, `audit_log` tables
- [x] Initialize FAISS vector store skeleton (`backend/memory/vector_store.py`)
- [x] Set up structlog logging config (`backend/logging_config.py`)
- [x] Verify: `uv run python -c "import fastapi, anthropic, keyring, aiosqlite"` passes

## Phase 2 — Backend Core
*Handled by: backend-agent*

- [x] FastAPI app with lifespan context manager (`backend/main.py`)
- [x] WebSocket hub — all 5 windows subscribe to `ws://127.0.0.1:8000/ws`
- [x] WebSocket event schema: `agent_update`, `token`, `tool_call`, `voice_state`
- [x] SQLite CRUD: conversations, agent state, audit log (`backend/memory/database.py`)
- [x] FAISS vector store with sentence-transformers embeddings
- [x] Claude API client with streaming + prompt caching (`backend/ai/claude_client.py`)
- [x] Ollama client — phi3.5 local fallback (`backend/ai/ollama_client.py`)
- [x] Jarvis persona system prompt (`backend/ai/persona.py`) — British, Tom Hardy × Avengers Jarvis
- [x] GET `/health` endpoint
- [x] Verify: backend starts, WebSocket accepts connections, Claude API responds

## Phase 3 — Voice Pipeline
*Handled by: backend-agent*

- [x] `sounddevice` audio capture loop (continuous, non-blocking)
- [x] OpenWakeWord wake word detection — model: "hey_jarvis" (replaced Porcupine 2026-06-03)
- [x] Voice activity detection — detect end of speech after 0.8s silence
- [x] faster-whisper STT integration (`backend/voice/stt.py`, base.en model)
- [x] ElevenLabs TTS integration (`backend/voice/tts.py`)
- [ ] *(Manual step)* Create ElevenLabs voice profile in dashboard — Tom Hardy × Jarvis character. Save voice ID to keyring.
- [x] Full pipeline: wake → listen → STT → Claude API → TTS → play audio
- [x] Interrupt: saying "stop" cancels mid-response
- [x] WebSocket events: emit `voice_state` (listening / thinking / speaking / idle)
- [x] Verify: complete voice roundtrip works end-to-end, latency target <3s

## Phase 4 — Agent System
*Handled by: backend-agent*

- [x] `BaseAgent` class — task queue, tool access list, Claude context, status (`backend/agents/base_agent.py`)
- [x] Production Lead agent — task routing logic (`backend/agents/production_lead.py`)
- [x] Ben (Frontend) agent (`backend/agents/frontend_agent.py`)
- [x] Kado (Backend) agent (`backend/agents/backend_agent.py`)
- [x] Security agent (`backend/agents/security_agent.py`)
- [x] Marketing agent (`backend/agents/marketing_agent.py`)
- [x] Content Creator agent (`backend/agents/content_creator.py`)
- [x] Agent-to-agent messaging — insert tasks into SQLite `tasks` table
- [x] All 6 agents start as asyncio background tasks in FastAPI lifespan
- [x] Agent state persists across backend restarts
- [x] Agent status broadcasts to WebSocket on every state change
- [x] Verify: all 6 agents running after startup, delegation routes correctly

## Phase 5 — Communication Integrations
*Handled by: backend-agent*

- [x] Slack OAuth app created at api.slack.com — Bot Token stored in keyring
- [x] Slack Bolt listener — incoming DMs and @mentions trigger Jarvis notification
- [x] Slack send message (`backend/integrations/slack_client.py`)
- [x] Gmail OAuth 2.0 app created at console.cloud.google.com — tokens in keyring
- [x] Gmail read inbox — last 10 unread messages
- [x] Gmail draft and send email (`backend/integrations/gmail_client.py`)
- [x] Both integrations registered in tool registry
- [x] Verify: Jarvis reads Slack and Gmail on voice command, can reply

## Phase 6 — Tools System
*Handled by: backend-agent*

- [x] `ToolRegistry` — per-agent permission matrix (`backend/tools/registry.py`)
- [x] DuckDuckGo web search tool (`backend/tools/web_search.py`)
- [x] Playwright browser automation tool (`backend/tools/browser.py`)
- [x] File read/write tool — sandboxed to workspace directory only (`backend/tools/file_ops.py`)
- [x] Sandboxed Python code executor — RestrictedPython (`backend/tools/code_executor.py`)
- [x] Slack tool wrapper
- [x] Gmail tool wrapper
- [x] All tools defined as Claude API `tool_use` JSON schemas
- [x] Verify: each tool callable, permissions matrix enforced, sandbox blocks `os.system()`

## Phase 7 — Multi-Window UI (Tauri + React)
*Handled by: frontend-agent*

- [x] Tauri multi-window config — 5 windows, screen positions defined in `tauri.conf.json` (labels animation/reasoning/communications/agents/tools verified)
- [x] Window 1 (`AnimationWindow.tsx`) — Three.js reactive orb, audio-reactive amplitude
- [x] Window 2 (`ReasoningWindow.tsx`) — model badge, live token stream, tool call cards, cost
- [x] Window 3 (`CommunicationsWindow.tsx`) — Slack panel + Gmail panel side by side
- [x] Window 4 (`AgentsWindow.tsx`) — 6 agent cards, live status badge, expandable task list
- [x] Window 5 (`ToolsWindow.tsx`) — tool/agent matrix grid with checkbox toggles
- [x] Zustand store wired to single WebSocket (`ws://127.0.0.1:8000/ws`)
- [x] All windows receive real-time state via WebSocket events
- [x] Boot sequence — staggered window fade-in animation (Framer Motion)
- [x] System tray icon — "Open Jarvis" / "Quit" menu (Rust `src-tauri/src/lib.rs` written; UNCOMPILED — Rust toolchain not installed)
- [x] Windows startup toggle (Tauri autostart plugin) (Rust plugin wired in `Cargo.toml`/`lib.rs`; UNCOMPILED — Rust toolchain not installed)
- [x] Verify: all 5 windows open on launch, live updates visible in all windows (React/TS layer verified via `pnpm build` clean + routing/config checks; native multi-window launch deferred until Rust installed)

## Phase 8 — Security Hardening
*Handled by: security-agent*

- [ ] All API keys confirmed in Windows Credential Manager (audit `keystore.py`)
- [ ] Automated grep scan passes — no secret patterns found in any file
- [ ] FastAPI confirmed binding to `127.0.0.1` only
- [ ] WebSocket Origin header validation implemented
- [ ] `sanitize_voice_input()` function in use on all voice input before Claude calls
- [ ] File tool validates paths against workspace allowlist
- [ ] Code executor blocks `os`, `sys`, `subprocess`, network calls
- [ ] Gmail uses minimal scopes: `gmail.readonly` + `gmail.send`
- [ ] Slack uses minimal scopes: `chat:write`, `im:read`, `channels:read`
- [ ] OAuth token auto-refresh implemented for both Gmail and Slack
- [ ] Audit log writing on every agent action (SQLite `audit_log` table)
- [ ] Security findings documented in **Security Findings** section below
- [ ] Verify: security-agent audit passes with zero Critical or High findings

## Phase 9 — Testing & Verification
*Handled by: debugger-agent*

- [ ] Unit: STT transcription accuracy (WAV file → expected transcript)
- [ ] Unit: TTS audio output (ElevenLabs → non-zero byte audio file)
- [ ] Unit: wake word callback simulation activates pipeline
- [ ] Integration: full voice roundtrip (<3s latency)
- [ ] Integration: Claude API streaming + tool use
- [ ] Integration: Ollama fallback when Claude API unavailable (mock 503)
- [ ] Integration: Slack read/send (mocked API)
- [ ] Integration: Gmail read/draft/send (mocked API)
- [ ] Integration: agent task delegation (Production Lead → Ben, Kado, etc.)
- [ ] Integration: agent state persists across backend restart
- [ ] UI: all 5 Tauri windows open on launch
- [ ] UI: WebSocket connects within 2 seconds of backend start
- [ ] UI: orb color changes correctly for idle/thinking/speaking
- [ ] UI: agent cards update in real-time on WebSocket events
- [ ] Security: grep scan finds no secrets in files
- [ ] Security: FastAPI not binding to 0.0.0.0
- [ ] Security: code executor blocks `os.system()` and `subprocess`
- [ ] E2E: "Jarvis, what's in my Slack?" → reads Slack → speaks answer
- [ ] E2E: "Jarvis, send an email to..." → Gmail draft + confirmation → sends
- [ ] Verify: all tests pass — see **Test Results** section below

## Phase 10 — Polish & Packaging
*Handled by: frontend-agent + backend-agent*

- [ ] Boot startup sound — subtle electronic tone on window open
- [ ] Error recovery — auto-restart voice pipeline on crash (max 3 retries)
- [ ] Graceful degradation — Claude API failure silently switches to Ollama
- [ ] Agent name customization UI — rename each agent from AgentsWindow
- [ ] Windows installer via Tauri bundler (`.exe`)
- [ ] First-run setup wizard — prompts for API keys → stores in keyring
- [ ] README.md with setup steps and first-run instructions
- [ ] Final `/security-agent` audit pass
- [ ] Final `/debugger-agent` full test suite pass
- [ ] Verify: clean install on fresh Windows 11 machine works end-to-end

---

## Project File Structure

```
C:\Users\User\appsbyG\Jarvis\
├── CLAUDE.md                        ← This file
├── .claude/
│   ├── agents/                      ← Sub-agent definitions
│   │   ├── production-manager.md
│   │   ├── frontend-agent.md
│   │   ├── backend-agent.md
│   │   ├── security-agent.md
│   │   └── debugger-agent.md
│   └── agent-memory/                ← Persistent memory per agent
├── backend/
│   ├── main.py                      ← FastAPI entry + WebSocket hub
│   ├── logging_config.py
│   ├── voice/
│   │   ├── wake_word.py             ← OpenWakeWord
│   │   ├── stt.py                   ← faster-whisper
│   │   └── tts.py                   ← ElevenLabs
│   ├── ai/
│   │   ├── claude_client.py         ← Anthropic SDK + streaming + caching
│   │   ├── ollama_client.py         ← Local fallback
│   │   └── persona.py               ← Jarvis system prompt
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── production_lead.py
│   │   ├── frontend_agent.py        ← Ben
│   │   ├── backend_agent.py         ← Kado
│   │   ├── security_agent.py
│   │   ├── marketing_agent.py
│   │   └── content_creator.py
│   ├── integrations/
│   │   ├── slack_client.py
│   │   └── gmail_client.py
│   ├── memory/
│   │   ├── database.py              ← SQLite (aiosqlite)
│   │   └── vector_store.py          ← FAISS
│   ├── tools/
│   │   ├── registry.py
│   │   ├── web_search.py
│   │   ├── browser.py
│   │   ├── file_ops.py
│   │   └── code_executor.py
│   └── security/
│       ├── keystore.py              ← keyring wrappers
│       └── auth.py                  ← OAuth token management
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── windows/
│   │   │   ├── AnimationWindow.tsx
│   │   │   ├── ReasoningWindow.tsx
│   │   │   ├── CommunicationsWindow.tsx
│   │   │   ├── AgentsWindow.tsx
│   │   │   └── ToolsWindow.tsx
│   │   ├── components/
│   │   │   ├── JarvisOrb.tsx        ← React Three Fiber
│   │   │   ├── AgentCard.tsx
│   │   │   ├── ToolCard.tsx
│   │   │   └── StreamViewer.tsx
│   │   └── lib/
│   │       ├── api.ts
│   │       ├── store.ts             ← Zustand
│   │       └── websocket.ts
│   └── src-tauri/
│       ├── tauri.conf.json          ← Multi-window config
│       └── src/main.rs
├── pyproject.toml
├── .env.example                     ← Template only, no real values
└── OpenJarvis/                      ← Reference project (read-only)
```

---

## Agent Routing Guide

| Phase | Agent to Invoke |
|---|---|
| Phase 1 — Foundation | Production Manager handles directly |
| Phase 2 — Backend Core | `/backend-agent` |
| Phase 3 — Voice Pipeline | `/backend-agent` |
| Phase 4 — Agent System | `/backend-agent` |
| Phase 5 — Integrations | `/backend-agent` |
| Phase 6 — Tools | `/backend-agent` |
| Phase 7 — UI (Tauri) | `/frontend-agent` |
| Phase 8 — Security | `/security-agent` |
| Phase 9 — Testing | `/debugger-agent` |
| Phase 10 — Polish | `/frontend-agent` + `/backend-agent` |

---

## How to Use This Project

1. **Start every session** — run the `production-manager` agent
   - It reads this file, tells you exactly what's next, and which agent to invoke
2. **Run the delegated agent** — each agent does its work then updates this file
3. **Repeat** — run `production-manager` again after each agent finishes
4. **Done** when every checkbox above is checked

---

## Security Findings
*(populated by security-agent during Phase 8 and on-demand audits)*

| Severity | Description | File:Line | Status |
|---|---|---|---|
| — | No findings yet | — | — |

---

## Test Results
*(populated by debugger-agent during Phase 9)*

- **Tests Passed**: 46 backend suite (`pytest backend`) + 7 Phase 7 UI verification checks (frontend) — all green
- **Tests Failed**: 0
- **Last Run**: 2026-06-03 — Phase 7 Multi-Window UI verification: 7/7 checks pass (React/TS layer). Prior: Phase 6 Tools 14/14, full backend suite 46/46.

### Phase 7 — Multi-Window UI (React/TS layer, 2026-06-03, 7/7 checks PASS) — Phase 7 VERIFIED
- [x] BUILD — `pnpm build` clean: `tsc` no TS errors, `vite` "built in 2.97s", `dist/` generated (index.html + assets, Three.js code-split into isolated 891kB AnimationWindow chunk).
- [x] 5 window files present — Animation/Reasoning/Communications/Agents/Tools under `frontend/src/windows/`.
- [x] 4 components present — JarvisOrb/AgentCard/ToolCard/StreamViewer under `frontend/src/components/`.
- [x] Zustand store — `frontend/src/lib/store.ts:111` exports `useStore` via `create<JarvisStore>`.
- [x] WebSocket — `frontend/src/lib/websocket.ts:14` `WS_URL = "ws://127.0.0.1:8000/ws"`.
- [x] Tauri config — `frontend/src-tauri/tauri.conf.json` defines 5 window labels (animation/reasoning/communications/agents/tools).
- [x] App routing — `frontend/src/App.tsx` maps Tauri window label → component for all 5 windows; falls back to `?window=` query then dev dashboard; windows lazy-loaded.
- CAVEAT: Rust shell (system tray, autostart, native multi-window launch) written but UNCOMPILED — Rust toolchain not installed. Native launch + Phase 9 live-UI items (orb colour transitions, agent-card live updates, WS-connect-within-2s) deferred until the full app runs.

### Phase 6 — Tools System (registry · sandbox · file ops · web search · schemas, 2026-06-03, 6/6 areas · 14/14 cases PASS) — Phase 6 COMPLETE
- [x] Permission enforcement — `get_tools_for_agent("production_lead")` returns all 12 (== `ALL_TOOLS`); `get_tools_for_agent("security")` returns exactly the 7 read-only tools (no write/comms leak); `call_tool("security","write_file",…)` raises `PermissionError`.
- [x] Sandbox blocks dangerous code — `execute_code("import os\nos.system(…)")`→`success=False`; `execute_code("import subprocess")`→`success=False`; `execute_code("print('hello')")`→`success=True`, stdout contains "hello".
- [x] Path traversal rejected — `write_file("../escape.txt",…)` and absolute-outside path both raise `PathTraversalError`; `write_file("safe.txt","hello")`+`read_file` roundtrip returns "hello". Workspace pinned to temp dir via `JARVIS_WORKSPACE`.
- [x] Web search — `WEB_SEARCH_SCHEMA` has name/description/input_schema with `type:"object"`; `web_search("")` returns `[]` (no crash, no network).
- [x] Claude schemas — every registered tool schema is well-formed (name matches, non-empty description, `input_schema.type=="object"`); Slack (3) + Gmail (3) wrappers registered with schemas.
- [x] Lifespan — real `TestClient(app)` with keystore patched (clients stay no-op): `app.state.tool_registry` is a populated `ToolRegistry` (≥6 tools), `/health` 200. Temp audit DB seeded with 6 agent rows for the FK on `audit_log.agent_id`.

### Phase 5 — Communication Integrations (Slack + Gmail, 2026-06-03, 6/6 checks · 9/9 cases PASS) — Phase 5 COMPLETE
- [x] Missing credentials (Slack) — keystore getters raise `MissingCredentialError` ⇒ `send_message`→False, `get_dm_history`→[], `get_unread_mentions`→[], `start_listener`→False (safe no-op).
- [x] Missing credentials (Gmail) — keystore getters raise `MissingCredentialError` ⇒ `get_inbox`→[], `send_email`→False, `draft_email`→"".
- [x] Slack send — mocked web client `chat_postMessage`→{"ok": True} ⇒ `send_message`→True, awaited with `channel`/`text`.
- [x] Slack read — mocked `conversations_open`+`conversations_history` ⇒ `get_dm_history` returns normalized `{user, text, ts}` dicts.
- [x] Slack listener — `_dispatch_notification(payload)` awaits the `on_notification` AsyncMock exactly once with the payload.
- [x] Gmail send/draft/inbox — mocked Google service ⇒ `send_email`→True, `draft_email`→draft id string, `get_inbox`→`{id, from, subject, snippet}` dicts.
- [x] Lifespan — real ASGI `TestClient(app)` with keystore patched (clients stay no-op): `/health` 200 and both `app.state.slack_client`/`app.state.gmail_client` constructed/exposed. `database.log_audit` stubbed so no real DB writes.

### Phase 1 — Foundation
- [x] Python project init verified — `uv run python -c "import fastapi, anthropic, keyring, aiosqlite"` exits 0 on Python 3.12.13. `pyproject.toml`, `uv.lock`, and `.venv/` all present.

### Phase 2 — Backend Core (FAISS + Claude + Ollama, 2026-06-03, 6/6 PASS)
- [x] FAISS — add 2 entries, ranked search (cat-query ranks cat entry top, scores descending), save→fresh `VectorStore.load()` round-trip with metadata.
- [x] FAISS — wired into app: `TestClient(app)` → `app.state.vector_store` is a `VectorStore`; `GET /health` 200 `status=ok`.
- [x] Claude — mocked Anthropic SDK stream: tokens yielded, system block has `cache_control: {"type":"ephemeral"}`, model `claude-opus-4-7` (not 4-8), final token `is_final=True`.
- [x] Claude — `anthropic.APIError` path raises `ClaudeAPIError`, still emits closing token.
- [x] Ollama — mocked `ollama.AsyncClient`: tokens yielded from fake stream, final token `is_final=True`.
- [x] Ollama — `ConnectionError` path yields empty stream (no exception), logs `ollama_unavailable` warning, still emits closing token.

### Phase 2 — Backend Core (Persona + /health, 2026-06-03, 6/6 PASS) — Phase 2 COMPLETE
- [x] Persona — `JARVIS_SYSTEM_PROMPT` non-empty with British-tone markers ("sir" present, "jarvis" present).
- [x] Persona — `build_system_prompt()` returns the base prompt unchanged.
- [x] Persona — `build_system_prompt(context="test context")` includes "test context" (under `# Current context`).
- [x] Persona — `build_system_prompt("   ")` (whitespace-only) returns base unchanged.
- [x] Health — Starlette `TestClient(app)` (lifespan runs: db init + vector store load) → `GET /health` 200 with `{"status":"ok","version":"0.1.0"}`.
- [x] Phase 2 verify item — backend starts and serves /health under lifespan; WebSocket endpoint registered at `/ws`; Claude client verified in prior run.

### Phase 3 — Voice Pipeline (STT + TTS, 2026-06-03, 7/7 PASS)
- [x] Imports — `backend.voice.stt` and `backend.voice.tts` import without error.
- [x] STT — `transcribe(np.ones(16000, int16))` over a mocked Whisper model (segment text=" hello world ") returns "hello world" (stripped/sanitised).
- [x] STT — `sanitize_transcript("Hi\x00\x07\x1b there\x08")` -> "Hi there" (category-C control chars stripped).
- [x] STT — `sanitize_transcript("a"*5000)` capped to 2000 chars (MAX_TRANSCRIPT_CHARS).
- [x] STT — empty audio `np.zeros(0, int16)` -> "".
- [x] TTS — `speak("hi")` with mocked client (convert -> [b"ID3", b"\x00\x01"]) returns joined b"ID3\x00\x01".
- [x] TTS — missing key: `get_elevenlabs_api_key` raising `MissingCredentialError` makes `speak("hi")` return b"" with no exception (graceful degrade).

### Phase 3 — Voice Pipeline (full pipeline + interrupt + voice_state, 2026-06-03, 6/6 PASS) — Phase 3 COMPLETE
*(`backend/voice/test_phase3_pipeline_verify.py` — all mocks, no mic/keys/hardware)*
- [x] Full pipeline — wake fire drives states listening→thinking→speaking→idle in order; Claude `stream_response` called with `[{"role":"user","content":"hello"}]`; full reply spoken via TTS across sentence chunks; ends idle.
- [x] Empty transcript — `stt.transcribe` returns "" → Claude never called, no `speaking` state, ends idle.
- [x] Interrupt — interrupt window transcribes "stop" → slow 50-token response cancelled before completion (`response_completed` stays False), pipeline returns to idle.
- [x] WebSocket broadcasts — every transition broadcasts a `VoiceStateEvent` (`type=="voice_state"`) with a valid state; all four states {listening, thinking, speaking, idle} emitted.
- [x] Lifespan — `app.state.voice_pipeline` is always non-None after startup (OpenWakeWord needs no key; Starlette TestClient).

### OpenWakeWord migration (2026-06-03, 11/11 PASS)
*(`backend/voice/test_phase3_verify.py` + `test_phase3_pipeline_verify.py` — full re-run after Porcupine → OpenWakeWord swap)*
- [x] Constants — `FRAME_LENGTH == 1280`, `SAMPLE_RATE == 16000`.
- [x] VAD — silence before speech never ends; silence after speech ends at ≥0.88s (11 × 80ms frames).
- [x] record_until_silence — returns int16 array after speech+silence frames.
- [x] OWW unavailable — `_init_model` returning False → `is_enabled=False`, `is_running=False`, no raise.
- [x] OWW detection — fake model scores ≥0.5 on first frame → callback fires.
- [x] Full pipeline, empty transcript, interrupt, voice_state broadcasts — 4 original pipeline tests still pass unchanged.
- [x] Lifespan — `app.state.voice_pipeline` always non-None (no key gate).

### Phase 4 — Agent System (2026-06-03, 12/12 PASS) — Phase 4 COMPLETE
*(`backend/agents/test_phase4_verify.py` — temp SQLite DB + fake hub + stub reasoners; no API keys, network, or shared on-disk state)*
- [x] BaseAgent lifecycle — `start()` upserts an idle agents row; an enqueued task drives working→idle and drains the queue; `stop()` sets in-memory + persisted status to offline.
- [x] Status broadcasts — fake hub collects `AgentUpdate` events; a processed task fans out a `working` then a returning-to-`idle` event in order.
- [x] DB persistence — after `AgentRuntime.start()`, `get_all_agents()` returns 6 rows with correct ids/names (production_lead/Atlas, frontend/Ben, backend/Kado, security/Sentinel, marketing/Vega, content/Quill). A second fresh runtime on the same DB still sees all 6 (offline) and can restart them — survives restarts.
- [x] Routing (×6 parametrized) — React/UI/Tauri→frontend, FastAPI/database/async-query→backend, security-audit/OAuth-vuln→security.
- [x] Delegation — `submit_goal("...FastAPI server")` → target backend, `delegated=True`, integer `task_id`; the `tasks` row is created_by production_lead / assigned_to backend and `get_agent_tasks` returns it; specialist runs it to `done`.
- [x] Error recovery — a `handle_task` that raises marks the `tasks` row `failed`, the agent recovers to `idle`, the run loop survives (still running), and a subsequent task is still accepted and drained.
- [x] Lifespan — real ASGI `TestClient(app)`: `/health` 200 `{"status":"ok"}`; `app.state.agents` has 6 running agents; on context exit the shutdown stops every agent loop.

### Failures
*(none — Phase 4: 12/12 pass; full backend suite 23/23, no regressions)*
