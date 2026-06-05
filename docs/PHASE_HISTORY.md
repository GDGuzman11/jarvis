# Jarvis — Completed Phase History

> All phases listed here are **complete**. This file is an archive — do not modify.
> Active and in-progress work lives in `CLAUDE.md`.

---

## Phase 1 — Foundation ✓
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

## Phase 2 — Backend Core ✓
*Handled by: backend-agent*

- [x] FastAPI app with lifespan context manager (`backend/main.py`)
- [x] WebSocket hub — all 5 windows subscribe to `ws://127.0.0.1:8000/ws`
- [x] WebSocket event schema: `agent_update`, `token`, `tool_call`, `voice_state`, `audio_level`, `shutdown` (plain dict)
- [x] `AudioLevelEvent` — broadcast RMS amplitude (0–1) every 50ms during TTS playback for lip-sync
- [x] SQLite CRUD: conversations, agent state, audit log (`backend/memory/database.py`)
- [x] FAISS vector store with sentence-transformers embeddings
- [x] Claude API client with streaming + prompt caching (`backend/ai/claude_client.py`)
- [x] Ollama client — phi3.5 local fallback (`backend/ai/ollama_client.py`)
- [x] Jarvis persona system prompt (`backend/ai/persona.py`) — British, Tom Hardy × Avengers Jarvis
- [x] GET `/health` endpoint
- [x] Verify: backend starts, WebSocket accepts connections, Claude API responds

## Phase 3 — Voice Pipeline ✓
*Handled by: backend-agent*

- [x] `sounddevice` audio capture loop (continuous, non-blocking)
- [x] OpenWakeWord wake word detection — model: "hey_jarvis" (replaced Porcupine 2026-06-03)
- [x] Voice activity detection — detect end of speech after 0.8s silence
- [x] faster-whisper STT integration (`backend/voice/stt.py`, base.en model)
- [x] ElevenLabs TTS integration (`backend/voice/tts.py`)
- [x] *(Manual step)* Create ElevenLabs voice profile — Paul Bettany × Anthony Hopkins × JARVIS character (calm British butler with faint digital resonance). Voice ID saved to keyring (2026-06-04).
- [x] Full pipeline: wake → listen → STT → Claude API → TTS → play audio
- [x] Interrupt: saying "stop" cancels mid-response
- [x] WebSocket events: emit `voice_state` (listening / thinking / speaking / idle / error) + `audio_level` (RMS 0–1 every ~50ms during TTS)
- [x] Verify: complete voice roundtrip works end-to-end, latency target <3s

## Phase 4 — Agent System ✓
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

## Phase 5 — Communication Integrations ✓
*Handled by: backend-agent*

- [x] Slack OAuth app created at api.slack.com — Bot Token stored in keyring
- [x] Slack Bolt listener — incoming DMs and @mentions trigger Jarvis notification
- [x] Slack send message (`backend/integrations/slack_client.py`)
- [x] Gmail OAuth 2.0 app created at console.cloud.google.com — tokens in keyring
- [x] Gmail read inbox — last 10 unread messages
- [x] Gmail draft and send email (`backend/integrations/gmail_client.py`)
- [x] Both integrations registered in tool registry
- [x] Verify: Jarvis reads Slack and Gmail on voice command, can reply

## Phase 6 — Tools System ✓
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

## Phase 7 — Multi-Window UI (Tauri + React) ✓
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
- [x] System tray icon — "Open Jarvis" / "Quit" menu (`src-tauri/src/lib.rs`; Rust 1.96.0 installed, `pnpm tauri dev` launches natively)
- [x] Windows startup toggle (Tauri autostart plugin, `Cargo.toml`/`lib.rs`)
- [x] `exit_app` Tauri command in `lib.rs` — invoked from shutdown button to close all 5 windows instantly via `app.exit(0)`
- [x] Window dragging — `core:window:allow-start-dragging` permission in `capabilities/default.json`; `getCurrentWebviewWindow().startDragging()` on mousedown in `WindowFrame.tsx` header and `AnimationWindow.tsx` grip
- [x] `core:window:allow-close` permission added — required for `getCurrentWebviewWindow().close()` in shutdown WS handler
- [x] Verify: all 5 windows open on launch via `pnpm tauri dev` (Rust 1.96.0 confirmed installed 2026-06-04)

## Phase 8 — Security Hardening ✓
*Handled by: security-agent*

- [x] All API keys confirmed in Windows Credential Manager (audit `keystore.py`)
- [x] Automated grep scan passes — no secret patterns found in any file
- [x] FastAPI confirmed binding to `127.0.0.1` only
- [x] WebSocket Origin header validation implemented
- [x] `sanitize_voice_input()` function in use on all voice input before Claude calls
- [x] File tool validates paths against workspace allowlist
- [x] Code executor blocks `os`, `sys`, `subprocess`, network calls
- [x] Gmail uses minimal scopes: `gmail.readonly` + `gmail.send`
- [x] Slack uses minimal scopes: `chat:write`, `im:read`, `channels:read`
- [x] OAuth token auto-refresh implemented for both Gmail and Slack
- [x] Audit log writing on every agent action (SQLite `audit_log` table)
- [x] Security findings documented in `docs/SECURITY_AUDIT.md`
- [x] Verify: security-agent audit passes with zero Critical or High findings

## Phase 9 — Testing & Verification ✓
*Handled by: debugger-agent*

- [x] Unit: STT transcription accuracy (WAV file → expected transcript)
- [x] Unit: TTS audio output (ElevenLabs → non-zero byte audio file)
- [x] Unit: wake word callback simulation activates pipeline
- [x] Integration: full voice roundtrip (<3s latency)
- [x] Integration: Claude API streaming + tool use
- [x] Integration: Ollama fallback when Claude API unavailable (mock 503)
- [x] Integration: Slack read/send (mocked API)
- [x] Integration: Gmail read/draft/send (mocked API)
- [x] Integration: agent task delegation (Production Lead → Ben, Kado, etc.)
- [x] Integration: agent state persists across backend restart
- [x] UI: all 5 Tauri windows open on launch — CONFIRMED 2026-06-04
- [x] Security: grep scan finds no secrets in files
- [x] Security: FastAPI not binding to 0.0.0.0
- [x] Security: code executor blocks `os.system()` and `subprocess`
- [x] Verify: all backend tests pass — 96/96 (see `docs/TEST_HISTORY.md`)
- [ ] UI: WebSocket connects within 2s — confirmed manually; no Vitest harness yet
- [ ] UI: orb color changes correctly — confirmed manually; no automated test yet
- [ ] UI: agent cards update in real-time — confirmed manually; no automated test yet
- [ ] E2E: "Jarvis, what's in my Slack?" — DEFERRED (needs mic + live keys)
- [ ] E2E: "Jarvis, send an email to..." — DEFERRED (needs mic + live keys)

## Phase 10 — Polish & Packaging ✓ (2 items remain)
*Handled by: frontend-agent + backend-agent*

- [x] Boot startup sound — subtle electronic tone on window open
- [x] Draggable windows — `getCurrentWebviewWindow().startDragging()` on mousedown in WindowFrame header + AnimationWindow grip strip; `core:window:allow-start-dragging` in capabilities *(updated 2026-06-04)*
- [x] Ethereal sand particle orb — replace icosahedron wireframe with 2500-particle noise-field system *(frontend VERIFIED 2026-06-03)*
- [x] Lip-sync amplitude broadcasting — `AudioLevelEvent` from backend pipeline; orb pulses with spoken audio *(backend + frontend VERIFIED)*
- [x] Error recovery — auto-restart voice pipeline on crash (max 3 retries)
- [x] Graceful degradation — Claude API failure silently switches to Ollama
- [x] Agent name customization UI — rename each agent from AgentsWindow *(VERIFIED 2026-06-03)*
- [x] First-run setup wizard — prompts for API keys → stores in keyring *(frontend + backend VERIFIED)*
- [x] Startup greeting — `_startup_greeting()` background task in `main.py` lifespan
- [x] Shutdown button + endpoint — `POST /api/shutdown` → `exit_app()` closes all 5 windows
- [x] Text input fallback — `POST /api/chat` → `pipeline.process_text(text)`; ReasoningWindow text field
- [x] README.md with setup steps and first-run instructions
- [x] Final `/security-agent` audit pass *(2026-06-03 — 0 Critical / 0 High)*
- [x] Final `/debugger-agent` full test suite pass *(2026-06-03 — 85/85 PASS)*
- [ ] **REMAINING**: Windows installer via Tauri bundler (`.exe`) — `pnpm tauri build`
- [ ] **REMAINING**: Verify clean install on fresh Windows 11 machine

---

## Project File Structure

```
C:\Users\User\appsbyG\Jarvis\
├── CLAUDE.md                        ← Master control document (READ THIS FIRST)
├── docs/
│   ├── PHASE_HISTORY.md             ← This file
│   ├── TEST_HISTORY.md              ← All test run logs
│   └── SECURITY_AUDIT.md            ← Security audit findings
├── README.md                        ← Setup + usage guide
├── .gitignore
├── pyproject.toml
├── .env.example                     ← Credential name reference — no real values
├── .claude/
│   ├── agents/                      ← Sub-agent definitions
│   │   ├── production-manager.md
│   │   ├── frontend-agent.md        ← Ben
│   │   ├── backend-agent.md         ← Kado
│   │   ├── security-agent.md        ← Sentinel
│   │   └── debugger-agent.md
│   └── agent-memory/                ← Persistent memory per agent
├── backend/
│   ├── main.py                      ← FastAPI entry; lifespan; endpoints: /health /api/chat /api/shutdown /api/agents/{id}/rename /ws; startup greeting task
│   ├── events.py                    ← WebSocket event schema (AgentUpdate, Token, ToolCall, VoiceStateEvent, AudioLevelEvent, MetricsEvent)
│   ├── websocket_hub.py             ← ConnectionHub — fan-out broadcast to all 5 windows
│   ├── setup_wizard.py              ← First-run wizard router: GET /setup/status, POST /setup/credential, GET /setup/complete
│   ├── logging_config.py
│   ├── voice/
│   │   ├── pipeline.py              ← Full wake→listen→STT→Claude→TTS loop; crash recovery; process_text() for typed input
│   │   ├── wake_word.py             ← OpenWakeWord + AudioCaptureLoop + SilenceDetector + VAD
│   │   ├── stt.py                   ← faster-whisper (base.en); sanitize_transcript()
│   │   └── tts.py                   ← ElevenLabs synthesis; speak_and_play() with AudioLevelEvent broadcast
│   ├── ai/
│   │   ├── claude_client.py         ← Anthropic SDK; streaming; prompt caching; _compute_cost(); MetricsEvent broadcast
│   │   ├── ollama_client.py         ← Local fallback (phi3.5 / qwen2.5-coder:3b)
│   │   └── persona.py               ← Jarvis system prompt; build_system_prompt(context=...)
│   ├── agents/
│   │   ├── base_agent.py            ← Task queue; tool access; status broadcasting; DB persistence
│   │   ├── runtime.py               ← AgentRuntime — starts + supervises all 6 agents
│   │   ├── production_lead.py       ← Atlas — orchestrator; goal routing
│   │   ├── frontend_agent.py        ← Ben
│   │   ├── backend_agent.py         ← Kado
│   │   ├── security_agent.py        ← Sentinel
│   │   ├── marketing_agent.py       ← Vega
│   │   └── content_creator.py       ← Quill
│   ├── integrations/
│   │   ├── slack_client.py          ← Slack Bolt; DM listener; send/read
│   │   └── gmail_client.py          ← Gmail OAuth2; inbox; draft; send
│   ├── memory/
│   │   ├── database.py              ← SQLite CRUD — conversations, agents, tasks, tools, audit_log
│   │   └── vector_store.py          ← FAISS + sentence-transformers
│   ├── tools/
│   │   ├── registry.py              ← ToolRegistry + per-agent permission matrix
│   │   ├── wiring.py                ← build_tool_registry() — wires all tools + integrations
│   │   ├── web_search.py            ← DuckDuckGo async search
│   │   ├── browser.py               ← Playwright browser automation (sandboxed schemes)
│   │   ├── file_ops.py              ← Read/write/list sandboxed to workspace/ only
│   │   ├── code_executor.py         ← RestrictedPython sandbox
│   │   ├── slack_tool.py            ← Slack tool wrapper (Claude tool_use schema)
│   │   └── gmail_tool.py            ← Gmail tool wrapper (Claude tool_use schema)
│   └── security/
│       └── keystore.py              ← Typed getters/setters for Windows Credential Manager
│                                       (Note: no auth.py — Gmail OAuth handled inline by google-auth)
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx                  ← Routes by Tauri window label → component; dev dashboard fallback
│   │   ├── index.css                ← Tailwind v4 @theme; .glass .hud-bg .hud-btn .data-stream-top .hud-corners
│   │   ├── windows/
│   │   │   ├── AnimationWindow.tsx  ← Particle orb + solar flares + SVG connection beams + shutdown button + drag grip
│   │   │   ├── ReasoningWindow.tsx  ← Token stream + tool calls + cost/latency + chat history + text input (POST /api/chat)
│   │   │   ├── CommunicationsWindow.tsx  ← Slack panel + Gmail panel
│   │   │   ├── AgentsWindow.tsx     ← 6 agent cards (live status + rename)
│   │   │   ├── ToolsWindow.tsx      ← Tool/agent permission matrix
│   │   │   └── SetupWizardWindow.tsx ← First-run credential form
│   │   ├── components/
│   │   │   ├── JarvisOrb.tsx        ← R3F 2500-particle orb + 60-particle solar flare system
│   │   │   ├── WindowFrame.tsx      ← HUD chrome; startDragging() on header mousedown; data-stream-top border
│   │   │   ├── AgentCard.tsx        ← Single agent card (status badge + rename)
│   │   │   ├── StatusBadge.tsx      ← Colour-coded status indicator
│   │   │   ├── StreamViewer.tsx     ← Scrollable live token stream
│   │   │   └── ToolCard.tsx         ← Tool display card
│   │   └── lib/
│   │       ├── store.ts             ← Zustand store (voiceState, audioLevel, agents, tokens, toolCalls, chatHistory, sessionCostUsd)
│   │       ├── types.ts             ← TypeScript interfaces mirroring backend events
│   │       ├── websocket.ts         ← WS singleton; auto-reconnect; dispatches events; handles shutdown close
│   │       ├── api.ts               ← fetch helpers: /api/chat, /api/shutdown, /api/agents/{id}/rename, /setup/*
│   │       └── useBootSound.ts      ← Boot chime on window open (Web Audio API)
│   └── src-tauri/
│       ├── tauri.conf.json          ← 5 windows: animation(780,300) reasoning(200,100) comms(1180,80) agents(200,760) tools(1180,540)
│       ├── capabilities/
│       │   └── default.json         ← Permissions: core:default, allow-show/hide/set-focus/start-dragging/close, opener, autostart
│       ├── Cargo.toml               ← tauri 2 + tray-icon feature + tauri-plugin-autostart + tauri-plugin-opener
│       └── src/
│           ├── lib.rs               ← show_all_windows(); exit_app() command; system tray (Open Jarvis/Quit); autostart plugin
│           └── main.rs              ← Calls lib::run()
├── data/                            ← Runtime only (gitignored): jarvis.db, faiss_index.bin
└── OpenJarvis/                      ← Reference project (read-only)
```
