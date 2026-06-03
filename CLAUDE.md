# JARVIS — Master Control Document

> **Every agent MUST read this file before starting any task.**
> Update checkboxes immediately after completing each item (`- [ ]` → `- [x]`).
> After every session, update the **Current Status** section below.
>
> **TESTING RULE: After EVERY single completed task, the debugger-agent runs a targeted test for that specific task before moving on. No task is considered done until its test passes.**

---

## Current Status

- **Active Phase**: 2 — Backend Core — COMPLETE
- **Last Completed**: **Phase 2 — Jarvis persona system prompt + GET /health endpoint** — VERIFIED by debugger-agent 2026-06-03 (6/6 checks). Persona (`backend/ai/persona.py`): `JARVIS_SYSTEM_PROMPT` non-empty with British-tone markers ("sir" + "jarvis" present); `build_system_prompt()` returns base unchanged; `build_system_prompt(context="test context")` includes the context under a `# Current context` heading; `build_system_prompt("   ")` (whitespace-only) returns base unchanged. Health (`backend/main.py`): via Starlette `TestClient(app)` (context-managed so lifespan runs — db init + vector store load), `GET /health` → 200 with `{"status":"ok","version":"0.1.0"}`. **This completes Phase 2.** Prior: FAISS vector store + Claude client + Ollama client; SQLite CRUD (conversations, agents, audit, tasks).
- **Next Task**: Phase 3 — Voice Pipeline. Route per the routing guide (`/backend-agent`). First task: `sounddevice` audio capture loop.
- **Blockers**: Rust/cargo toolchain NOT installed in this environment. Frontend JS/TS scaffold + build works without it, but `pnpm tauri dev` / native bundling (Phases 7 & 10) will require installing Rust via rustup first. Also note: `uv` is not on PATH in this shell — backend Python must be invoked via `.venv\Scripts\python.exe` directly. Project root is not a git repo, so `pre-commit install` is deferred.
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
- **Wake Word**: Porcupine (keyword: "Jarvis")
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

- [ ] `sounddevice` audio capture loop (continuous, non-blocking)
- [ ] Porcupine wake word detection — keyword: "Jarvis"
- [ ] Voice activity detection — detect end of speech after 0.8s silence
- [ ] faster-whisper STT integration (`backend/voice/stt.py`, base.en model)
- [ ] ElevenLabs TTS integration (`backend/voice/tts.py`)
- [ ] *(Manual step)* Create ElevenLabs voice profile in dashboard — Tom Hardy × Jarvis character. Save voice ID to keyring.
- [ ] Full pipeline: wake → listen → STT → Claude API → TTS → play audio
- [ ] Interrupt: saying "stop" cancels mid-response
- [ ] WebSocket events: emit `voice_state` (listening / thinking / speaking / idle)
- [ ] Verify: complete voice roundtrip works end-to-end, latency target <3s

## Phase 4 — Agent System
*Handled by: backend-agent*

- [ ] `BaseAgent` class — task queue, tool access list, Claude context, status (`backend/agents/base_agent.py`)
- [ ] Production Lead agent — task routing logic (`backend/agents/production_lead.py`)
- [ ] Ben (Frontend) agent (`backend/agents/frontend_agent.py`)
- [ ] Kado (Backend) agent (`backend/agents/backend_agent.py`)
- [ ] Security agent (`backend/agents/security_agent.py`)
- [ ] Marketing agent (`backend/agents/marketing_agent.py`)
- [ ] Content Creator agent (`backend/agents/content_creator.py`)
- [ ] Agent-to-agent messaging — insert tasks into SQLite `tasks` table
- [ ] All 6 agents start as asyncio background tasks in FastAPI lifespan
- [ ] Agent state persists across backend restarts
- [ ] Agent status broadcasts to WebSocket on every state change
- [ ] Verify: all 6 agents running after startup, delegation routes correctly

## Phase 5 — Communication Integrations
*Handled by: backend-agent*

- [ ] Slack OAuth app created at api.slack.com — Bot Token stored in keyring
- [ ] Slack Bolt listener — incoming DMs and @mentions trigger Jarvis notification
- [ ] Slack send message (`backend/integrations/slack_client.py`)
- [ ] Gmail OAuth 2.0 app created at console.cloud.google.com — tokens in keyring
- [ ] Gmail read inbox — last 10 unread messages
- [ ] Gmail draft and send email (`backend/integrations/gmail_client.py`)
- [ ] Both integrations registered in tool registry
- [ ] Verify: Jarvis reads Slack and Gmail on voice command, can reply

## Phase 6 — Tools System
*Handled by: backend-agent*

- [ ] `ToolRegistry` — per-agent permission matrix (`backend/tools/registry.py`)
- [ ] DuckDuckGo web search tool (`backend/tools/web_search.py`)
- [ ] Playwright browser automation tool (`backend/tools/browser.py`)
- [ ] File read/write tool — sandboxed to workspace directory only (`backend/tools/file_ops.py`)
- [ ] Sandboxed Python code executor — RestrictedPython (`backend/tools/code_executor.py`)
- [ ] Slack tool wrapper
- [ ] Gmail tool wrapper
- [ ] All tools defined as Claude API `tool_use` JSON schemas
- [ ] Verify: each tool callable, permissions matrix enforced, sandbox blocks `os.system()`

## Phase 7 — Multi-Window UI (Tauri + React)
*Handled by: frontend-agent*

- [ ] Tauri multi-window config — 5 windows, screen positions defined in `tauri.conf.json`
- [ ] Window 1 (`AnimationWindow.tsx`) — Three.js reactive orb, audio-reactive amplitude
- [ ] Window 2 (`ReasoningWindow.tsx`) — model badge, live token stream, tool call cards, cost
- [ ] Window 3 (`CommunicationsWindow.tsx`) — Slack panel + Gmail panel side by side
- [ ] Window 4 (`AgentsWindow.tsx`) — 6 agent cards, live status badge, expandable task list
- [ ] Window 5 (`ToolsWindow.tsx`) — tool/agent matrix grid with checkbox toggles
- [ ] Zustand store wired to single WebSocket (`ws://127.0.0.1:8000/ws`)
- [ ] All windows receive real-time state via WebSocket events
- [ ] Boot sequence — staggered window fade-in animation (Framer Motion)
- [ ] System tray icon — "Open Jarvis" / "Quit" menu
- [ ] Windows startup toggle (Tauri autostart plugin)
- [ ] Verify: all 5 windows open on launch, live updates visible in all windows

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
│   │   ├── wake_word.py             ← Porcupine
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

- **Tests Passed**: 13 (cumulative)
- **Tests Failed**: 0
- **Last Run**: 2026-06-03 — Phase 2: Jarvis persona + GET /health endpoint (6 checks) — Phase 2 COMPLETE

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

### Failures
*(none — all 13 cumulative checks passed)*
