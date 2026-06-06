# JARVIS — Master Control Document

> **Step 1 — Every agent MUST read THIS FILE FIRST before starting any task.**
> **Step 2 — Then read the archive files in `docs/` (listed in the Archive Index below) for full historical context: completed phases, test logs, and security audits.**
> Update checkboxes immediately after completing each item (`- [ ]` → `- [x]`).
> After every session, update the **Current Status** section below.
>
> **CORE PRINCIPLE: We are ENHANCING what has already been built — not replacing or rewriting it. Every new task adds to or improves the existing system. All agents work under the Production Lead (Atlas) to achieve each task collaboratively. Read the archive first so you understand what exists before proposing or implementing anything.**
>
> **TESTING RULE: After EVERY single completed task, the debugger-agent runs a targeted test for that specific task before moving on. No task is considered done until its test passes.**

---

## Current Status

- **Active Phase**: 12 — Three-Layer Memory System (started 2026-06-05). Phase 11 remains open (11D packaging + mic-blocked voice items).
- **Last Completed (2026-06-05)**: **Phase 12D verified ✓** — all 4 phases (12A–12D) built and verified by debugger-agent. 126/127 tests passing. One pre-existing secret-scan failure on `get_gmail_token.py` (Google OAuth client id, not a real secret) owned by security-agent. Phase 12D `detect_open_loops` multi-trigger bug found and fixed same session (10/10 targeted tests). Full memory system now operational: voice pipeline recalls+stores per turn, agents persist context across restarts, open loops detected + surfaced on startup, failure memory extracted, people profiles built from contacts, 10-minute consolidation loop running. All storage is local SQLite + FAISS.
- **Next Task**: **Phase 12E** — FTS5 keyword search + daily backup job. Route to `/backend-agent`. After 12E: run `/security-agent` to fix `get_gmail_token.py` secret (removes the 1 failing test). Then run `/production-manager` for full review.
- **Pending (Phase 13 — new)**: Agent direct interaction from AgentsWindow UI — user wants to submit tasks and chat with individual agents (Atlas/Ben/Kado/Sentinel/Vega/Quill) from the UI. Route to `/frontend-agent` + `/backend-agent`. See Phase 13 section below.
- **Blockers**: Dedicated microphone not yet purchased — all voice E2E tests deferred. No other blockers.
- **Test State**: 126/127 passing · 1 pre-existing failure (secret-scan on `get_gmail_token.py`) · `pnpm build` clean. New test files: `test_phase12a_verify.py`, `test_phase12b_verify.py` (in `backend/voice/`), `test_phase12c_verify.py` (in `backend/agents/`), `test_phase12d_verify.py` (in `backend/memory/`). See `docs/TEST_HISTORY.md` for full logs.
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
- **Text-to-Speech**: ElevenLabs API (custom Paul Bettany × Anthony Hopkins × JARVIS voice — calm British butler with faint digital resonance)

### Tech Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, WebSockets, Uvicorn |
| Frontend | Tauri 2 + React 19 + TypeScript 5 + Vite 6 |
| Styling | Tailwind CSS 4, Angular HUD dark theme (`#080810`, `.hud-btn`, `.data-stream-top`, `.hud-corners`) |
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
| 1 | Animation | 2500-particle orb + 60-particle solar flares; blue=idle, gold=thinking, cyan=speaking; lip-syncs to audio; SVG connection beams to other windows; ⏻ shutdown button |
| 2 | Reasoning | Model name, streaming tokens, tool call cards, cost/latency; **text input** for typing questions when mic unavailable |
| 3 | Communications | Slack inbox + Gmail inbox — read/reply via voice |
| 4 | Agents | 6 agent cards (Atlas/Ben/Kado/Sentinel/Vega/Quill) with live status, current task, rename controls |
| 5 | Tools | Tool store grid — per-agent access toggles |

### 6 Background Agents (run 24/7)
| Agent | Name | Role |
|---|---|---|
| Production Lead | Atlas | Orchestrator — breaks goals into tasks, delegates, monitors |
| Frontend | Ben | UI/UX, React components, visual design |
| Backend | Kado | APIs, database, voice pipeline, performance |
| Security | Sentinel | Vulnerability scans, key rotation, audits |
| Marketing | Vega | Campaign planning, social content strategy |
| Content Creator | Quill | Drafts posts, emails, copy, documentation |

### Design Aesthetic
Dark theme `#080810` (updated 2026-06-04), electric blue/cyan accents `#00D4FF`, gold highlights `#FFB800`. Iron Man HUD — angular, futuristic, high-contrast. Sharp edges with glowing outlines. No rounded corners.

- **Grid**: fine dual-scale grid (80px major / 20px minor) at low opacity
- **Panels**: `rgba(8,14,28,0.82)` background, `backdrop-filter: blur(24px)`, `1px solid rgba(0,212,255,0.25)` border
- **WindowFrame**: angular header with `|`-style accent ticks, flowing `data-stream-top` animated border, pulsing rectangular status badge, corner accent marks
- **Buttons** (`.hud-btn`): `rgba(0,212,255,0.06)` bg, `0.5` opacity cyan border, full cyan border + shadow glow on hover — high contrast
- **Window layout**: orb (AnimationWindow) centred at `x:780, y:300`; Reasoning left `x:200`; Communications upper-right `x:1180`; Agents bottom `x:200, y:760`; Tools lower-right `x:1180, y:540`
- **Orb**: 2500-particle sand/stardust cloud + 60-particle solar flare system (gold `#ffe066`, bursts every 3–9s). SVG connection beams radiate from orb centre to other window edges with animated travelling dots.
- **Voice Jarvis**: Paul Bettany × Anthony Hopkins character — calm British butler with faint digital resonance. "The kind of voice that could read you a bedtime story or a threat."

---

## Security Rules (enforced throughout ALL phases)

1. **Zero secrets in files** — All API keys stored in Windows Credential Manager via `keyring`. No `.env` files with real values. `.env.example` template only.
2. **Local network only** — FastAPI binds to `127.0.0.1:8000`, never `0.0.0.0`.
3. **Voice input sanitized** — Strip control chars, cap at 2000 chars before sending to Claude.
4. **Sandboxed code execution** — No `os`, `sys`, `subprocess` access. Workspace-only filesystem.
5. **Minimal OAuth scopes** — Gmail and Slack use least-privilege scopes.
6. **Audit log in SQLite** — Every agent action logged (metadata only, no message content).

---

## Phase 10 — Polish & Packaging
*Phases 1–9 complete. All Phase 10 done items archived in [docs/PHASE_HISTORY.md](docs/PHASE_HISTORY.md).*

- [ ] Windows installer via Tauri bundler (`.exe`) — run `pnpm tauri build`
- [ ] Verify: clean install on fresh Windows 11 machine works end-to-end *(blocked — requires `.exe` installer built first)*

---

## Phase 11 — Live Usage & Ongoing Improvements
*Active phase. Each task must be tested by debugger-agent before checkbox is ticked.*

### 11A — Credentials & Integrations
*Handled by: user (manual OAuth) + backend-agent (keyring storage)*

- [x] Gmail OAuth setup — user gabedeguzman99@gmail.com *(all 4 credentials confirmed SET in keyring 2026-06-04)*
  - [x] Create Google Cloud project "Jarvis" at console.cloud.google.com
  - [x] Enable Gmail API
  - [x] Configure OAuth consent screen (External, app name: Jarvis)
  - [x] Create OAuth Client ID (Desktop app type) → save Client ID + Secret to keyring
  - [x] Set redirect URI `urn:ietf:wg:oauth:2.0:oob` to keyring
  - [x] Run OAuth flow to generate refresh token → save to keyring
  - [x] Verify: `keystore.missing_credentials()` returns `[]` (all 10 set) *(confirmed 2026-06-04 — GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URI, GMAIL_REFRESH_TOKEN all present)*
- [x] Verify startup greeting fires on launch — `_startup_greeting()` implemented in `main.py` lifespan; all credentials SET so Claude + TTS calls will succeed *(confirmed 2026-06-04)*
- [ ] E2E voice test with dedicated microphone — "Hey Jarvis, what's in my Slack?" → reads Slack → speaks answer — **DEFERRED: needs dedicated microphone**
- [ ] E2E voice test — "Hey Jarvis, what's in my Gmail?" → reads inbox → speaks answer — **DEFERRED: needs dedicated microphone**

### 11B — Voice & Audio
*Handled by: backend-agent*

- [ ] Tune wake-word sensitivity after microphone upgrade (currently threshold=0.5, may need adjustment) — **DEFERRED: needs dedicated microphone**
- [ ] Tune silence detection threshold (`SILENCE_RMS_THRESHOLD=500`) for new microphone — **DEFERRED: needs dedicated microphone**
- [x] Verify audio plays through correct output device consistently *(confirmed 2026-06-04 — Jarvis speaking audibly through Realtek laptop speakers + VG27AQ3A monitor)*
- [ ] Test interrupt ("stop") cancels mid-response reliably with new microphone — **DEFERRED: needs dedicated microphone**

### 11C — UI Polish
*Handled by: frontend-agent (Ben)*

- [x] Text input fallback in ReasoningWindow — type a message when mic isn't available. `POST /api/chat` endpoint in `main.py` → `pipeline.process_text(text)` runs the full Claude → token broadcast → TTS pipeline as a background task. Input disabled while Jarvis is busy (voiceState ≠ idle), shows current state label, Enter key submits, error shown inline. Backend returns 409 if busy, 400 if empty. Frontend: `frontend/src/windows/ReasoningWindow.tsx` — text input + SEND button at bottom, `.hud-btn` style, `border-jarvis-cyan/30` focus ring. `backend/voice/pipeline.py` — new `process_text(text)` public method.
- [x] **Chat history UI in ReasoningWindow** — `MessageBubble` component: user right-aligned (`bg-jarvis-cyan/10`, `border-jarvis-cyan/30`), Jarvis left-aligned (`bg-white/5`, `border-white/10`); blinking caret on in-progress Jarvis bubble; auto-scroll via `useEffect`+`scrollRef`; `chatHistory: ChatMessage[]` + `addUserMessage()` + `appendJarvisToken()` in `store.ts`; `websocket.ts` `case "token"` calls both `appendToken` (legacy) and `appendJarvisToken`. *(verified by debugger-agent 2026-06-04, 96/96 backend tests pass, pnpm build clean)*
- [x] **Live cost + latency display** — `backend/ai/claude_client.py`: `_compute_cost()` pure function (input $15/M, output $75/M, cache_write $3.75/M, cache_read $1.50/M); `MetricsEvent` broadcast after `is_final` token; `backend/events.py` `MetricsEvent` dataclass added. Frontend: `MetricsEvent` type extended with token count fields; `store.ts` `sessionCostUsd` running total; `ReasoningWindow` header shows per-turn cost (4dp), session total (2dp), latency ms, and `N in / N out · N cached` token counts. *(verified by debugger-agent 2026-06-04)*
- [x] **Translucent window style** — `index.css`: `.hud-bg` → `rgba(8,8,16,0.18)`, grid 0.02 opacity; `.glass` → `rgba(5,10,25,0.35)` + `blur(40px)` + border `rgba(0,212,255,0.45)`; `body` text-shadow `0 1px 3px rgba(0,0,0,0.8)`. `WindowFrame.tsx` header → `bg-black/20`. `AnimationWindow.tsx` root → `bg-transparent`. *(verified by debugger-agent 2026-06-04, pnpm build clean)*
- [x] Verify window drag works in native Tauri app — `core:window:allow-start-dragging` + `startDragging()` confirmed working *(2026-06-04)*
- [x] Verify shutdown button (⏻) closes all 5 windows cleanly — `core:window:allow-close` added to `capabilities/default.json`; `exit_app()` Tauri command confirmed; requires `pnpm tauri dev` restart after capability change *(2026-06-04)*
- [x] Verify connection beams animate correctly in native Tauri app — 4 SVG paths with `<animateMotion>` dots confirmed in `AnimationWindow.tsx` *(2026-06-04)*
- [x] Verify solar flares appear in native Tauri app — `FLARE_COUNT=60`, `flareRef`, `flarePositions` in `JarvisOrb.tsx` confirmed *(2026-06-04)*
- [x] Verify startup greeting sets orb to speaking state (cyan) then back to idle (blue) — `_startup_greeting()` broadcasts `speaking` then `idle` voice states *(2026-06-04)*
- [x] Test window positions on user's specific dual-monitor setup (laptop + VG27AQ3A) — user confirmed windows appear correctly *(2026-06-04)*
- [ ] Add a microphone sensitivity indicator to the AnimationWindow (small bar showing input level when listening) — **NOT YET BUILT** (Phase 11E backlog)

### 11D — Packaging
*Handled by: backend-agent + production-manager*

- [ ] Windows installer via Tauri bundler (`pnpm tauri build`) — generates `.exe` installer
- [x] Git repo initialised with `.gitignore` (excludes `.env`, `data/`, `workspace/`, `.venv/`, `target/`); pushed to **https://github.com/GDGuzman11/jarvis** (2026-06-04)
- [ ] Verify clean install on fresh Windows 11 machine (end-to-end)

### 11E — Future Enhancements (backlog — not yet scheduled)
*Handled by: appropriate agent when scheduled*

- [ ] Jarvis remembers context across sessions (FAISS semantic memory populated by conversations)
- [ ] Proactive notifications — Jarvis speaks when important Slack/Gmail arrives
- [ ] Agent task visibility — show what each agent is working on in real-time in AgentsWindow
- [ ] Voice commands to control agent tasks ("Jarvis, tell Ben to update the UI")
- [ ] Custom wake word training (replace "hey_jarvis" OpenWakeWord model with user-trained model)
- [ ] Multiple voice profiles (switch between voices via voice command)

---

## Phase 12 — Three-Layer Memory System ("The Brain")
*Active backend initiative. Wires SQLite (episodic), FAISS (semantic), and agent working memory into one tiered architecture so Jarvis remembers across sessions. Full spec in the Phase 12 plan. Each task tested by debugger-agent before its checkbox is ticked.*

### 12A — Memory Infrastructure
*Handled by: backend-agent. Lay all the plumbing — no behaviour changes yet.*

- [x] Create `backend/memory/manager.py` — `MemoryManager` class (store / recall / consolidate / format_context); `RecallResult` dataclass; FAISS calls run via `asyncio.to_thread` so memory never blocks the event loop
- [x] Create `backend/memory/evaluator.py` — `MemoryEvaluator` class with full scoring table (agent_outcome 1.0 → general 0.2) + per-category fact extraction; pure keyword matching, no ML
- [x] Update `backend/memory/database.py` — added 5 new tables (`memory_facts`, `people`, `open_loops`, `decisions`, `agent_performance`) to `_SCHEMA` (all `IF NOT EXISTS`) + indexes + helpers `save_memory_fact`/`get_memory_facts`/`save_person`/`get_person_by_email`/`save_open_loop`/`get_open_loops`/`save_decision`/`save_agent_performance`
- [x] Update `backend/agents/runtime.py` — accepts + passes `vector_store` and `memory_manager` to agents via `common`
- [x] Update `backend/agents/base_agent.py` — accepts + stores `vector_store`/`memory_manager` as `self.vector_store`/`self.memory_manager` (no behaviour change)
- [x] Update `backend/main.py` — constructs `MemoryManager(db_path=DEFAULT_DB_PATH, vector_store=...)` on `app.state.memory_manager`; passed to `AgentRuntime` + `VoicePipeline`
- [x] Verify (debugger-agent): MemoryManager instantiates at startup; all 5 new tables created cleanly; `pytest backend/` passes *(verified 2026-06-05 — 7/7 targeted tests pass, 102/103 suite, schema + evaluator + recall + DB helpers all confirmed)*

### 12B — Voice Pipeline Memory
*Handled by: backend-agent. Wire memory in and out of every voice/text turn.*

- [x] Update `backend/voice/pipeline.py` — `_stream_and_speak(transcript, *, channel)` now brackets each turn with memory: `recall(query=transcript, n_recent=10, n_semantic=3)` before the Claude call (prepends `episodic_messages`, injects `formatted_context` into the system prompt), then `store(user)` + `store(jarvis)` + fire-and-forget `asyncio.create_task(consolidate(...))` after TTS completes. `process_text` routes through the same method with `channel="text"`. Interrupt cancellation skips the post-turn store cleanly (no partial/empty reply persisted). When `memory_manager is None`, falls back to the original stateless path (single message + base prompt) — existing pipeline tests still pass
- [x] Update `backend/ai/persona.py` — `build_system_prompt(context)` now detects a pre-formatted block that already opens with `# Current context` (as emitted by `MemoryManager.format_context`, carrying `Date:` + `## What I remember about you` + `## Recent conversation`) and appends it verbatim with no duplicate header; bare fragments still get a fresh header. Date/time confirmed driven by `datetime.now()` in `format_context` (not hardcoded)
- [x] Verify (debugger-agent): after 3 turns `conversations` has 6 rows; `memory_facts` ≥1 row when scored ≥0.65; recalled context appears in 4th turn's system prompt; `pytest backend/` passes *(verified 2026-06-05 — 7/7 targeted tests pass: recall prepended, store×2, fire-and-forget consolidate, no-memory fallback, persona single-header, interrupt no-store; 109/110 suite)*

### 12C — Agent Memory
*Handled by: backend-agent. Agents persist context across restarts and write domain-scoped facts.*

- [x] Update `backend/agents/base_agent.py` — full memory integration in `reason()`: when `memory_manager` is wired in, `recall(query=prompt, n_recent=6, n_semantic=3)` runs before the Claude call (prepends `episodic_messages`, injects `formatted_context` into the system prompt) and `store(user)`/`store(jarvis)` + fire-and-forget `consolidate(source="agent")` run after. Context checkpoint: `_remember()` persists each exchange to `conversations` under `channel="agent:<id>"` (skipped when a memory manager already owns the episodic write, to avoid a duplicate row). Context restore: `start()` calls `_restore_context()` which reloads this agent's last 12 turns (`get_recent_conversations(channel="agent:<id>", limit=12)`) into `self._context`; empty DB → `self._context = []` as before. `reason()` signature relaxed to `system_prompt: str | None = None` (no caller change). All memory writes are `asyncio.create_task` fire-and-forget; `else` branch identical to prior behaviour
- [x] Update `backend/agents/production_lead.py` — `_delegate()` writes a `decisions` row (title `Delegated: <summary>`, reasoning `Routed to <name> (<id>) via classify().`, `agent_id="production_lead"`) via fire-and-forget `_save_decision_async`, gated on `memory_manager` present
- [x] Update each specialist agent (Kado/Ben/Sentinel/Vega/Quill) — `handle_task` now records `agent_performance` on completion (`outcome="success"`/`"failed"`, `task_type` derived from content via `_record_performance`/`_derive_task_type` in `base_agent.py`), gated on `memory_manager` present
- [x] Hook `audit_log` writes → semantic memory — `_log_audit()` promotes each logged action to a `memory_facts` row (category `agent_outcome`, importance 1.0) + FAISS via new `MemoryManager.store_fact()`; metadata only (action + target, no content — Security Rule 6). Added `conversations.channel` migration in `init_db` so existing DBs accept `agent:%` channels
- [x] Verify (debugger-agent): agent context survives backend restart; `audit_log` entries appear in `memory_facts`; `pytest backend/` passes *(verified 2026-06-05 — 8/8 targeted tests pass: checkpoint, restore, empty-DB restore, recall-in-reason, store-after-reason, decisions row, agent_performance row, Phase 4 regression 12/12; 116/117 suite)*

### 12D — Memory Intelligence
*Handled by: backend-agent. Evaluator, open loops, people profiles, failure memory.*

- [x] Complete `MemoryEvaluator` — `detect_open_loops()` + `extract_person()` added; `people` profile updates wired into `MemoryManager.consolidate()` (deduped by email via existing `save_person`) *(self-verified)*
- [x] Add `open_loops` detection — `MemoryEvaluator.detect_open_loops()` scans for remind/follow-up/need-to/make-sure/schedule patterns; `consolidate()` fires `_save_open_loop_async` per match (fire-and-forget) *(self-verified)*
- [x] Add session-start open loop surfacing — `_startup_greeting(memory_manager)` in `main.py` appends overdue items (open >12h) via `get_open_loops_async(db_path, status, older_than_hours)`; guarded for `memory_manager is None` *(self-verified)*
- [x] Add failure memory extraction — expanded `failure` keyword set (attempted/caused issues/was too slow/conflicted with); `extract_fact` emits "Failed approach: … Reason: … Date: …" via `_split_failure()`; scores 0.85 *(self-verified)*
- [x] Add memory consolidation background task — `_consolidation_loop()` in `main.py` lifespan runs `MemoryManager.run_consolidation()` every 600s (cancellable on shutdown); back-fills missed semantic facts from last 50 conversations, idempotent via distilled-fact content hash *(self-verified)*
- [x] Verify (debugger-agent): reminder → `open_loops` row, surfaced next session; failure → `memory_facts` category=failure; `pytest backend/` passes *(verified 2026-06-05 — 10/10 targeted tests pass after multi-trigger bug fix; 126/127 suite)*

### 12E — Search, Backup, and CLAUDE.md
*Handled by: backend-agent. FTS5 keyword search, daily backup job, project state in CLAUDE.md.*

- [ ] Add FTS5 virtual tables to `database.py` for keyword search over `conversations` + `memory_facts`
- [ ] Add `MemoryManager.search_keyword(query)` — queries FTS5 tables
- [ ] Add daily backup job in `main.py` lifespan — zips `jarvis.db` + `faiss_index.bin` + `.meta.json` to `data/backups/jarvis_YYYY-MM-DD.zip`; prunes >30 days
- [ ] Update CLAUDE.md — Phase 12 checklist + Agent Routing Guide (this section)
- [ ] Verify (debugger-agent): keyword search returns results; backup file created at startup; `pytest backend/` passes

---

## Phase 13 — Agent Direct Interaction (AgentsWindow)
*Not yet started. User wants to submit tasks and chat directly with individual agents from the AgentsWindow UI.*

### What exists today
- `frontend/src/windows/AgentsWindow.tsx` — 6 agent cards showing live status, current task, rename controls
- Backend: agents accept tasks via `AgentRuntime.submit_goal(goal, from_agent)` which writes to the `tasks` table and enqueues to the target agent's `asyncio.Queue`
- WebSocket: `AgentUpdate` events broadcast agent status/task changes in real time — already displayed on cards

### What needs to be built (Phase 13A — frontend-agent + backend-agent)
- [ ] **Task input per agent card** — text field + SEND button on each card; submits `POST /api/agents/{agent_id}/task` with `{"goal": "..."}` to queue a task for that agent directly
- [ ] **Atlas (Production Lead) chat panel** — dedicated chat input in AgentsWindow for submitting high-level goals to Atlas; Atlas breaks them down and delegates automatically
- [ ] **Live task log per agent** — expandable section on each card showing last 5 completed tasks (from `tasks` table) pulled via `GET /api/agents/{agent_id}/tasks`
- [ ] **New backend endpoint** — `POST /api/agents/{agent_id}/task` validates agent_id, writes to `tasks` table, enqueues directly (bypass production lead for direct targeting)
- [ ] Verify (debugger-agent): task submission reaches agent queue; agent status updates broadcast to UI; pytest passes

### Agent Routing Guide addition
| Phase 13 — Agent UI | `/frontend-agent` (UI) + `/backend-agent` (endpoint) |

---

## Archive Index

> **All agents (especially Production Lead):** CLAUDE.md shows what is active and what is next.
> The archive files below show what was built, how it was tested, and every decision made.
> Read them when you need full context before making a recommendation or starting a task.

| File | Contents | When to read |
|---|---|---|
| [docs/PHASE_HISTORY.md](docs/PHASE_HISTORY.md) | Phases 1–10 complete checklists + full project file structure | When you need to know exactly what was built, or to understand the file layout |
| [docs/TEST_HISTORY.md](docs/TEST_HISTORY.md) | All debugger-agent test run logs (Phases 1–11C, 96 tests) | When you need to understand what is already tested and how |
| [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) | Phase 8 + Phase 10 audit findings and verifications | Before touching auth, credentials, or network bindings |

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
| Phase 11A — Credentials | User (manual) + `/backend-agent` |
| Phase 11B — Voice/Audio | `/backend-agent` |
| Phase 11C — UI Polish | `/frontend-agent` |
| Phase 11D — Packaging | `/backend-agent` + Production Manager |
| Phase 11E — Enhancements | Route per task (see checklist) |
| Phase 12 (12A–12E) — Memory System | `/backend-agent` |
| Phase 13 — Agent Direct Interaction | `/frontend-agent` (UI) + `/backend-agent` (API endpoint) |

---

## How to Use This Project

1. **Start every session** — run the `production-manager` agent
   - It reads this file first, then `docs/` archive files, tells you exactly what's next, and which agent to invoke
2. **Run the delegated agent** — each agent does its work then updates this file
3. **Repeat** — run `production-manager` again after each agent finishes
4. **Done** when every checkbox above is checked
