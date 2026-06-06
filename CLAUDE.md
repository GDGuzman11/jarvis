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

- **Phase 15A verified ✓ 2026-06-06**: debugger-agent verified the Neural Intelligence Orb rewrite in `frontend/src/components/JarvisOrb.tsx`. Old system fully removed (2500-particle sand cloud, synaptic bezier arcs, jagged discharge arcs — no `PARTICLE_COUNT`/`flareRef`/`QuadraticBezierCurve3`/`DischargeSlot`). All 7 layers present: 3 nested glow spheres + wireframe hologram shell, 350 neuron `Points` (vertexColors), ~480 normal `LineSegments`, red freedom `LineSegments` (20%), 30 symbol `Sprite`s, cascade activation (`CASCADE_DEPTH=6`, `NEIGHBOR_K=4`, `RED_RATIO=0.2`). `BASE_RADIUS=1.2`, prop signature, `AdditiveBlending`+`depthWrite:false` all preserved; state gating per voiceState confirmed. `pnpm build` clean (0 TS errors). Backend suite **143/144** (only pre-existing `get_gmail_token.py` secret-scan fails — no regression; frontend-only change). **Phase 15A complete.**
- **Active Phase**: Phases 13/14/15 complete and archived to `docs/PHASE_HISTORY.md`. Phase 11 remains open: mic sensitivity indicator (11C, not yet built), packaging (11D — `pnpm tauri build` not yet run), deferred voice items (need dedicated microphone). Phase 10 packaging also incomplete.
- **Phase 14A verified (2026-06-06)**: debugger-agent verified the orb Neural Link rework in `frontend/src/components/JarvisOrb.tsx`. Solar flare system fully removed; synaptic arcs (QuadraticBezierCurve3, idle/speaking) + jagged discharge arcs (LineSegments + vertexColors, thinking/listening) + memory arcs (gold→purple→white) added; state gating and audioLevel pulse intact. `pnpm build` clean (0 TS errors). Backend suite 143/144 (only pre-existing `get_gmail_token.py` secret-scan fails — no regression; frontend-only change).
- **Last Completed (2026-06-05)**: **Phase 12E verified ✓** — FTS5 keyword search + daily backup job built and verified by debugger-agent. 134/135 tests passing (8 new 12E tests). One pre-existing secret-scan failure on `get_gmail_token.py` (Google OAuth client id, not a real secret) owned by security-agent. Full memory system operational: episodic (SQLite), semantic (FAISS), agent working memory, FTS5 keyword search, daily backups, open loops, failure memory, people profiles, consolidation loop. **Phase 12 (Three-Layer Memory) fully complete — archived to `docs/PHASE_HISTORY.md`.**
- **Phase 13A verified (2026-06-06)**: debugger-agent verified both new endpoints end-to-end. New test file `backend/test_phase13a_verify.py` (9 tests, all pass). Full backend suite **143/144** (only pre-existing `get_gmail_token.py` secret-scan fails). `pnpm build` clean. Phase 13A frontend (per-card task input, Atlas MissionControl panel, live task log) wired to `POST /api/agents/{id}/task` + `GET /api/agents/{id}/tasks`. **Phase 13 complete — archived to `docs/PHASE_HISTORY.md`.**
- **Next Task**: Phase 11C mic sensitivity indicator (add small input-level bar to AnimationWindow when listening state) OR Phase 11D `pnpm tauri build` (generate `.exe` Windows installer). Security-agent still owns the pre-existing `get_gmail_token.py` secret-scan fix (would bring suite to 143/143).
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
| 1 | Animation | Neural intelligence orb — 350 neuron nodes, glowing pathways, red freedom pathways (~20%), 30 floating math/code symbols; cascade activation; audioLevel pulse during speaking; SVG connection beams to other windows; ⏻ shutdown button |
| 2 | Reasoning | Model name, streaming tokens, tool call cards, cost/latency; **text input** for typing questions when mic unavailable |
| 3 | Communications | Slack inbox + Gmail inbox — read/reply via voice |
| 4 | Agents | 6 agent cards (Atlas/Ben/Kado/Sentinel/Vega/Quill) with live status, current task, rename controls, task input + task log per card, Mission Control panel |
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
- **Orb**: Neural intelligence sphere — 350 neuron `Points` (golden-spiral, vertexColors), ~480 normal `LineSegments` + ~120 red freedom `LineSegments` (~20% of connections, `#440011`→`#ff2244`), 30 drifting symbol `Sprite`s (∑ π ∞ λ etc.), 3 nested glow spheres + wireframe hologram shell, cascade activation (CASCADE_DEPTH=6, NEIGHBOR_K=4). SVG connection beams radiate from orb centre to other window edges with animated travelling dots.
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

## Archive Index

> **All agents (especially Production Lead):** CLAUDE.md shows what is active and what is next.
> The archive files below show what was built, how it was tested, and every decision made.
> Read them when you need full context before making a recommendation or starting a task.

| File | Contents | When to read |
|---|---|---|
| [docs/PHASE_HISTORY.md](docs/PHASE_HISTORY.md) | Phases 1–15 complete checklists + full project file structure. **Archiving destination — move fully completed phase sections here from CLAUDE.md.** | When you need to know exactly what was built, or to understand the file layout |
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
