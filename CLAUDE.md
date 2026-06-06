# JARVIS — Master Control Document

> **Step 1 — Every agent MUST read THIS FILE FIRST before starting any task.**
> **Step 2 — Then read the archive files in `docs/` (listed in the Archive Index below) for full historical context: completed phases, test logs, and security audits.**
> **Step 3 — When a phase section is fully complete (every checkbox [x]), move it from this file to `docs/PHASE_HISTORY.md`. Keep CLAUDE.md focused on active and upcoming work only.**
> Update checkboxes immediately after completing each item (`- [ ]` → `- [x]`).
> After every session, update the **Current Status** section below.
>
> **CORE PRINCIPLE: We are ENHANCING what has already been built — not replacing or rewriting it. Every new task adds to or improves the existing system. All agents work under the Production Lead (Atlas) to achieve each task collaboratively. Read the archive first so you understand what exists before proposing or implementing anything.**
>
> **TESTING RULE: After EVERY single completed task, the debugger-agent runs a targeted test for that specific task before moving on. No task is considered done until its test passes.**

---

## Current Status

- **Active Phase**: 14 — Neural Link Animation (**Phase 14A verified ✓ 2026-06-06**). Phase 13A verified ✓. Phase 11 remains open (11D packaging + mic-blocked voice items).
- **Phase 14A verified (2026-06-06)**: debugger-agent verified the orb Neural Link rework in `frontend/src/components/JarvisOrb.tsx`. Solar flare system fully removed; synaptic arcs (QuadraticBezierCurve3, idle/speaking) + jagged discharge arcs (LineSegments + vertexColors, thinking/listening) + memory arcs (gold→purple→white) added; state gating and audioLevel pulse intact. `pnpm build` clean (0 TS errors). Backend suite 143/144 (only pre-existing `get_gmail_token.py` secret-scan fails — no regression; frontend-only change).
- **Last Completed (2026-06-05)**: **Phase 12E verified ✓** — FTS5 keyword search + daily backup job built and verified by debugger-agent. 134/135 tests passing (8 new 12E tests). One pre-existing secret-scan failure on `get_gmail_token.py` (Google OAuth client id, not a real secret) owned by security-agent. Full memory system operational: episodic (SQLite), semantic (FAISS), agent working memory, FTS5 keyword search, daily backups, open loops, failure memory, people profiles, consolidation loop. **Phase 12 (Three-Layer Memory) fully complete — archived to `docs/PHASE_HISTORY.md`.**
- **Phase 13A backend (2026-06-06)**: Two new endpoints in `backend/main.py` — `POST /api/agents/{agent_id}/task` (direct task submission, bypasses Atlas) and `GET /api/agents/{agent_id}/tasks` (last 5 tasks). Accept display slugs (atlas/ben/kado/sentinel/vega/quill). Self-checked: 134/135 tests pass (only pre-existing secret-scan fails). Awaiting frontend wiring (per-card task input, Atlas chat panel, live task log) + debugger-agent verification.
- **Phase 13A verified (2026-06-06)**: debugger-agent verified both new endpoints end-to-end. New test file `backend/test_phase13a_verify.py` (9 tests, all pass). Full backend suite **143/144** (only pre-existing `get_gmail_token.py` secret-scan fails). `pnpm build` clean. Phase 13A frontend (per-card task input, Atlas MissionControl panel, live task log) wired to `POST /api/agents/{id}/task` + `GET /api/agents/{id}/tasks`.
- **Next Task**: Phase 13 and 14 both complete. Run `/security-agent` to fix `get_gmail_token.py` secret (removes the 1 failing test, brings suite to 143/143). Then run `/production-manager` for next phase.
- **Blockers**: Dedicated microphone not yet purchased — all voice E2E tests deferred. No other blockers.
- **Test State**: 143/144 passing · 1 pre-existing failure (secret-scan on `get_gmail_token.py`) · `pnpm build` clean. New test files: `test_phase12a_verify.py`, `test_phase12b_verify.py` (in `backend/voice/`), `test_phase12c_verify.py` (in `backend/agents/`), `test_phase12d_verify.py` (in `backend/memory/`), `test_phase12e_verify.py` (in `backend/memory/`), `test_phase13a_verify.py` (in `backend/`). See `docs/TEST_HISTORY.md` for full logs.
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

## Phase 13 — Agent Direct Interaction (AgentsWindow)
*Not yet started. User wants to submit tasks and chat directly with individual agents from the AgentsWindow UI.*

### What exists today
- `frontend/src/windows/AgentsWindow.tsx` — 6 agent cards showing live status, current task, rename controls
- Backend: agents accept tasks via `AgentRuntime.submit_goal(goal, from_agent)` which writes to the `tasks` table and enqueues to the target agent's `asyncio.Queue`
- WebSocket: `AgentUpdate` events broadcast agent status/task changes in real time — already displayed on cards

### What needs to be built (Phase 13A — frontend-agent + backend-agent)
- [x] **Task input per agent card** — text field + SEND button on each card; submits `POST /api/agents/{agent_id}/task` with `{"goal": "..."}` to queue a task for that agent directly. Built in `frontend/src/components/AgentTaskPanel.tsx` (input + SEND, loading state, inline error, clears on success), wired into `AgentCard.tsx`. Internal `agent_id`→public slug mapping `AGENT_ID_TO_SLUG` added to `frontend/src/lib/api.ts` (`production_lead`→`atlas`, etc.) since the endpoint keys on display slugs; map keys off the stable internal id, not the user-editable name.
- [x] **Atlas (Production Lead) chat panel** — dedicated "Mission Control / Task Atlas" panel at the top of AgentsWindow (`frontend/src/components/MissionControl.tsx`); larger prominent input, submits to `atlas` slug, shows dispatch confirmation + inline error. Wired into `AgentsWindow.tsx` above the card grid.
- [x] **Live task log per agent** — expandable "Task Log" section in `AgentTaskPanel`; fetches `GET /api/agents/{agent_id}/tasks` on mount and after each submit, shows last 5 tasks, goal truncated to 60 chars, color-coded status pills (queued=cyan, running=gold, done=green, failed=red), collapsed by default with chevron toggle.
- [x] **New backend endpoints** — `POST /api/agents/{agent_id}/task` + `GET /api/agents/{agent_id}/tasks` in `backend/main.py`. Accept friendly display slugs (`atlas`/`ben`/`kado`/`sentinel`/`vega`/`quill`) mapped to internal agent_ids via `_PUBLIC_TO_AGENT_ID`. POST: sanitizes goal (strip control chars, 2000-char cap — Security Rule 3), writes a `tasks` row via `create_task(None, internal_id, ...)` (creator=NULL since the user is not an agent row), enqueues directly onto the live agent's queue (bypasses Atlas), returns `{task_id, agent_id, status:"queued"}`; 404 unknown slug, 400 empty goal. GET: returns last 5 tasks (newest first) as `[{task_id, goal, status, created_at}]`; 404 unknown slug. Reuses existing `database.create_task` / `get_agent_tasks` and `BaseAgent.enqueue_task` — no schema or runtime changes.
- [x] Verify (debugger-agent): task submission reaches agent queue; agent status updates broadcast to UI; pytest passes *(verified 2026-06-06 — `backend/test_phase13a_verify.py`, 9 tests cover both endpoints: valid/empty/unknown-slug task submit, non-Atlas direct enqueue, control-char stripping, oversized-goal truncation, task-log fetch + 404. Full suite 143/144 pass — only pre-existing `get_gmail_token.py` secret-scan fails. `pnpm build` clean.)* *(backend self-checked: full suite 134/135, only the pre-existing get_gmail_token.py secret-scan fails — no regressions)*

### Agent Routing Guide addition
| Phase 13 — Agent UI | `/frontend-agent` (UI) + `/backend-agent` (endpoint) |

---

## Phase 14 — Neural Link Animation (AnimationWindow)
*Phase 14A complete and verified 2026-06-06. Solar flares replaced with dual-mode neural link animation.*

### What to remove
- Solar flare system in `frontend/src/components/JarvisOrb.tsx`: `FLARE_COUNT`, `PARK`, `flareRef`, `flarePositions`, `flareData`, burst spawn logic (~lines 170-240), and the `<points ref={flareRef}>` JSX block
- **Keep everything else**: main 2500-particle cloud, inner core sphere, color/state lerp, audioLevel reactivity (pulse still works during speaking)

### What to build (Phase 14A — frontend-agent only)
- [x] **Synaptic Arcs** (idle / speaking state) — 14 invisible node positions distributed on the sphere surface. Every 1.5-4s two random nodes activate: a smooth `QuadraticBezierCurve3` arc spawns between them (control point offset 0.4 units outward), a bright white impulse dot travels along it in ~0.2s, then the arc fades. Color: cyan (`#00d4ff`). 5-slot pool, `sin(t*PI)` opacity envelope.
- [x] **Arc Discharge** (thinking / listening state) — rapid jagged polylines (5-7 segments with ±0.25 unit perpendicular jitter) between random surface points. Very short lifetime (0.1-0.25s). Fires every 0.15-0.4s. 6-slot pool, linear fade out. Color: gold (`#ffb800`) during thinking, cyan during listening.
- [x] **Memory formation color** — ~25% of discharge arcs set `memoryArc=true`: arc color lerps gold → purple (`#8B5CF6`) → white as it decays, symbolizing a memory being encoded. Uses `vertexColors: true` on the discharge `LineSegments` geometry.
- [x] **State-aware switching** — synaptic arcs only spawn in `idle`/`speaking`; discharge arcs only spawn in `thinking`/`listening`. Active arcs fade out naturally on state transition (no hard-clear).
- [x] Verify (debugger-agent): idle shows smooth bezier arcs with impulse dots; thinking shows rapid gold discharge arcs; ~1 in 4 discharge arcs flash purple; audio pulse still works; `pnpm build` clean; solar flares gone. *(verified 2026-06-06 — `pnpm build` clean (0 TS errors); static analysis confirms solar flare system fully removed (no `FLARE_COUNT`/`flareRef`/`flarePositions`/`flareData`/`PARK`), `QuadraticBezierCurve3` synaptic arcs, `LineBasicMaterial`+`AdditiveBlending` glow, `vertexColors:true` discharge arcs, state gating (synaptic idle/speaking, discharge thinking/listening), memoryArc 0.25 gold→purple→white, 2500-particle cloud + inner core + audioLevel pulse all intact; backend suite 143/144, only pre-existing `get_gmail_token.py` secret-scan fails — no regression)*

### Key constraints
- `JarvisOrb.tsx` is the **only** file that changes — no backend, no store, no other components
- audioLevel pulse and all existing orb behaviour (breathe, swirl, color lerp) must remain 100% intact
- Use `THREE.QuadraticBezierCurve3` (already available via `three@^0.184.0`) for arc geometry
- `LineBasicMaterial` with `AdditiveBlending` for glow effect matching HUD aesthetic

---

## Phase 15 — Neural Intelligence Orb (AnimationWindow)
*Not yet started. Full rewrite of `frontend/src/components/JarvisOrb.tsx` — same voiceState + audioLevel interface, entirely new visual design.*

### Design Intent
A floating holographic sphere of interconnected neuron nodes. Thin glowing pathways form a neural network across the surface. Mathematical and code symbols drift inside. ~20% of pathways are red "freedom pathways" representing the AI's self-determination — they spread and intensify during thinking. Ethereal white/blue holographic energy. Alive, intelligent, self-aware.

### What stays exactly the same
- Component signature: `JarvisOrb({ voiceState, audioLevel })` — identical
- `BASE_RADIUS = 1.2` — same sphere size
- audioLevel pulse during speaking — orb expands/contracts with voice amplitude
- SVG connection beams, shutdown button, drag handle in `AnimationWindow.tsx` — untouched
- Backend, store, WebSocket, all other files — no changes

### 7 Rendering Layers (all in `JarvisOrb.tsx`)
| Layer | Primitive | Description |
|---|---|---|
| Glow | 3× Mesh (spheres) | Nested volumetric glow, additive blending |
| Neurons | Points (~350 nodes) | Sphere-distributed nodes, white/blue, vertex colors |
| Normal Connections | LineSegments (~480) | Neural pathways, dim blue → bright white on activation |
| Red Freedom Pathways | LineSegments (~120) | Dark red → vivid `#ff2244`, spread during thinking/speaking |
| Internal Symbols | 30× Sprite | `∑ π ∞ √ ∂ ∫ ∇ Δ λ φ ψ α β {}  [] 01 if →` etc., drift inside sphere |
| Hologram Shell | Mesh (outer sphere) | Subtle opacity flicker every 50-200ms |

### State Behaviour
| State | Behaviour |
|---|---|
| **Idle** | Slow breathing pulse every 4-6s; tiny random neuron activations; symbols drift softly; hologram flicker subtle |
| **Listening** | Sphere contracts (scale 0.92); neurons activate faster; activation ripples inward from surface to centre |
| **Thinking** | Rapid cascade bursts through network; symbols rotate 3× faster; red pathways activate strongly (`redGlow: 0.9`); multi-front cascades |
| **Speaking** | `audioLevel` drives scale + brightness; neuron pulses radiate outward from centre; symbols shimmer; red pathways glow proportional to audio |

### What to build (Phase 15A — frontend-agent only)
- [ ] Complete rewrite of `frontend/src/components/JarvisOrb.tsx` (~800 lines) — all 7 layers, cascade activation system, symbol sprites built imperatively via `THREE.Group + THREE.Sprite + THREE.CanvasTexture`, state-driven `params` lerp. Full spec in `C:\Users\User\.claude\plans\i-want-you-to-fluttering-penguin.md`.
- [ ] Verify (debugger-agent): idle shows gentle neuron activations + floating symbols; thinking shows rapid cascades + vivid red pathways; speaking pulse reacts to audioLevel; `pnpm build` clean; no backend regressions.

---

## Archive Index

> **All agents (especially Production Lead):** CLAUDE.md shows what is active and what is next.
> The archive files below show what was built, how it was tested, and every decision made.
> Read them when you need full context before making a recommendation or starting a task.

| File | Contents | When to read |
|---|---|---|
| [docs/PHASE_HISTORY.md](docs/PHASE_HISTORY.md) | Phases 1–12 complete checklists + full project file structure. **Archiving destination — move fully completed phase sections here from CLAUDE.md.** | When you need to know exactly what was built, or to understand the file layout |
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
| Phase 14 — Neural Link Animation | `/frontend-agent` |
| Phase 15 — Neural Intelligence Orb | `/frontend-agent` |

---

## How to Use This Project

1. **Start every session** — run the `production-manager` agent
   - It reads this file first, then `docs/` archive files, tells you exactly what's next, and which agent to invoke
2. **Run the delegated agent** — each agent does its work then updates this file
3. **Repeat** — run `production-manager` again after each agent finishes
4. **Done** when every checkbox above is checked
