# Jarvis

> *"A subtle intelligence, sir. Always at your service."*

A local-first personal AI assistant for Windows 11. Say **"Hey Jarvis"** — it wakes, listens, thinks, and speaks back in a calm British voice. Five HUD windows float on your desktop like an Iron Man interface. Six background agents run 24/7 handling code, content, security, and communications.

---

## What It Does

| Feature | Description |
|---|---|
| **Voice activation** | Say "Hey Jarvis" — OpenWakeWord detects it locally, no API key needed |
| **Natural conversation** | Claude Opus 4.7 streams the reply; Ollama (`phi3.5`) runs offline if Claude is unavailable |
| **Custom voice** | ElevenLabs — calm, precise British delivery with a faint digital resonance |
| **Five HUD windows** | Neural intelligence orb · Live reasoning stream · Communications panel · Agent dashboard · Tools grid |
| **Six background agents** | Atlas (Lead) · Ben (Frontend) · Kado (Backend) · Sentinel (Security) · Vega (Marketing) · Quill (Content) |
| **Direct agent control** | Submit tasks to any agent from the Agents window — Atlas MissionControl panel + per-card task input + live task log |
| **Slack + Gmail** | Read, draft, and reply by voice |
| **Persistent memory** | Three-layer brain: SQLite episodic recall + FAISS semantic search + agent working memory. Remembers facts, preferences, open loops, and failures across sessions |
| **Sandboxed tools** | Web search, browser automation, file ops, RestrictedPython code runner |
| **Startup greeting** | Jarvis greets you by name and reads the system status when windows open |
| **One-click shutdown** | ⏻ button on the orb window exits all five windows cleanly |

---

## Hardware Requirements

| Component | Minimum | This Build |
|---|---|---|
| GPU | 4 GB VRAM | NVIDIA RTX 3050 Ti Laptop (4 GB) |
| RAM | 16 GB | 16 GB |
| OS | Windows 11 | Windows 11 |
| Python | 3.12 | 3.12.x via `uv` |
| Node.js | 20+ | 20+ via `pnpm` |
| Rust | stable | rustup stable (Tauri native build) |
| Microphone | Any | Dedicated mic recommended for wake word reliability |

Local LLMs are sized for 4 GB VRAM: `phi3.5` (3.8B, ~2.4 GB) for general tasks and `qwen2.5-coder:3b` (~2 GB) for code.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, WebSockets, Uvicorn |
| Primary AI | Anthropic Claude API (`claude-opus-4-7`, streaming + prompt caching) |
| Local AI fallback | Ollama (`phi3.5`, `qwen2.5-coder:3b`) |
| Wake word | OpenWakeWord (`hey_jarvis`, fully local, Apache 2.0) |
| Speech-to-text | faster-whisper (Whisper `base.en`, local) |
| Text-to-speech | ElevenLabs (custom voice) |
| Frontend | Tauri 2 · React 19 · TypeScript 5 · Vite 6 |
| Styling | Tailwind CSS 4 · Angular HUD dark theme |
| 3D animation | Three.js · React Three Fiber (neural intelligence orb — neuron graph, red freedom pathways, symbol sprites) |
| State | Zustand 5 · WebSocket sync |
| Database | SQLite (aiosqlite) |
| Vector memory | FAISS + sentence-transformers |
| Credentials | Windows Credential Manager (keyring) |
| Integrations | Slack Bolt · Gmail API (OAuth 2.0) |
| Testing | pytest + pytest-asyncio (143 backend tests) |

---

## Installation

### 1. Prerequisites

- [uv](https://github.com/astral-sh/uv) — Python package manager
- [pnpm](https://pnpm.io) — Node package manager
- [Rust toolchain](https://rustup.rs) — required for Tauri native windows
- [Ollama](https://ollama.com) — local AI fallback

```powershell
# Install uv
winget install astral-sh.uv

# Install Rust
winget install Rustlang.Rustup --accept-source-agreements

# Install Ollama, then pull models
ollama pull phi3.5
ollama pull qwen2.5-coder:3b
```

### 2. Clone and install

```powershell
git clone https://github.com/gabedeguzman99/jarvis.git
cd jarvis

# Python backend
uv sync

# OpenWakeWord (separate step due to Windows resolver quirk)
uv pip install openwakeword

# Frontend
cd frontend
pnpm install
cd ..
```

Verify Python:
```powershell
.venv\Scripts\python.exe -c "import fastapi, anthropic, keyring, aiosqlite; print('OK')"
```

### 3. Store API keys

Jarvis stores **all secrets in the Windows Credential Manager** — nothing in files.

```powershell
.venv\Scripts\python.exe -c "
from backend.security import keystore

# Anthropic (get from console.anthropic.com)
keystore.set_anthropic_api_key('sk-ant-...')

# ElevenLabs (get from elevenlabs.io)
keystore.set_elevenlabs_api_key('your-key')
keystore.set_elevenlabs_voice_id('your-voice-id')

# Slack (get from api.slack.com/apps)
keystore.set_slack_bot_token('xoxb-...')
keystore.set_slack_app_token('xapp-...')
keystore.set_slack_signing_secret('your-secret')

# Gmail OAuth (get from console.cloud.google.com)
keystore.set_gmail_client_id('your-client-id')
keystore.set_gmail_client_secret('your-client-secret')
keystore.set_gmail_redirect_uri('urn:ietf:wg:oauth:2.0:oob')
keystore.set_gmail_refresh_token('your-refresh-token')
"
```

Check what's still missing:
```powershell
.venv\Scripts\python.exe -c "from backend.security import keystore; print(keystore.missing_credentials())"
```

See `.env.example` for where to obtain each credential.

### 4. Create your Jarvis voice (ElevenLabs)

1. Go to [elevenlabs.io](https://elevenlabs.io) → **Voice Lab** → **Voice Design**
2. Use this description:

   > *Calm, refined British male AI. A butler with the quiet menace of an assassin. Paul Bettany meets Anthony Hopkins — unhurried, precise, never raising his voice. Faint digital resonance beneath the warmth, like intelligence itself is speaking.*

3. Save the voice → copy the **Voice ID** → store it with `set_elevenlabs_voice_id()`

Test line: *"Good evening, sir. All systems are nominal. Shall I proceed?"*

---

## Running

### Backend (Terminal 1 — keep this running)

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Confirms with: `Uvicorn running on http://127.0.0.1:8000`

### Native desktop app (Terminal 2)

```powershell
cd frontend
pnpm tauri dev
```

Five windows open on your desktop. First launch compiles Rust (~3–5 min). Subsequent launches are instant.

**To shut down:** click the **⏻ button** on the orb window (top-right corner). All five windows close immediately.

### Browser preview (no Rust required)

```powershell
cd frontend
pnpm dev
```

Open `http://localhost:1420` — single-tab preview of all windows. Good for frontend development.

### Tests

```powershell
.venv\Scripts\python.exe -m pytest backend/ -v
```

143 backend tests passing (1 known pre-existing failure on `get_gmail_token.py` — OAuth client id flagged by secret scan, not a live secret).

---

## Window Layout

When launched, the five windows arrange around the central orb:

```
┌─────────────────────────────────────────────────────────────┐
│  REASONING          │           │  COMMUNICATIONS           │
│  (live token stream)│   [ORB]   │  (Slack + Gmail)          │
│                     │           │                           │
├─────────────────────┤           └───────────────────────────┤
│                     │                                       │
│  AGENTS             │           TOOLS                       │
│  (6 agent cards)    │           (permission matrix)         │
└─────────────────────────────────────────────────────────────┘
```

All windows are draggable by their header. The orb window has a drag grip at the bottom edge.

---

## Talking to Jarvis

1. Say **"Hey Jarvis, [your question]"** — say it as one sentence without pausing
2. The orb turns **cyan** while listening, **gold** while thinking, **cyan** while speaking
3. Jarvis responds through your speakers

**Example commands:**
- *"Hey Jarvis, what's in my Slack?"*
- *"Hey Jarvis, summarise my unread emails"*
- *"Hey Jarvis, search for the latest news on X"*
- *"Hey Jarvis, what's the status of all agents?"*
- Say **"stop"** mid-response to interrupt

---

## Project Structure

```
Jarvis/
├── CLAUDE.md                     # Master build checklist (agents read this)
├── .env.example                  # Credential reference — no real values
├── pyproject.toml                # Python project (uv)
├── backend/
│   ├── main.py                   # FastAPI app + startup greeting + shutdown endpoint
│   ├── events.py                 # WebSocket event schema
│   ├── websocket_hub.py          # Fan-out hub for all 5 windows
│   ├── ai/
│   │   ├── claude_client.py      # Anthropic SDK, streaming, prompt caching
│   │   ├── ollama_client.py      # Local fallback
│   │   └── persona.py            # Jarvis system prompt
│   ├── voice/
│   │   ├── wake_word.py          # OpenWakeWord + VAD + audio capture
│   │   ├── stt.py                # faster-whisper transcription
│   │   ├── tts.py                # ElevenLabs synthesis + playback
│   │   └── pipeline.py           # wake → listen → think → speak loop
│   ├── agents/
│   │   ├── base_agent.py         # Task queue, status broadcasting, DB persistence
│   │   ├── runtime.py            # Supervises all 6 agents
│   │   ├── production_lead.py    # Atlas — orchestrator
│   │   ├── frontend_agent.py     # Ben
│   │   ├── backend_agent.py      # Kado
│   │   ├── security_agent.py     # Sentinel
│   │   ├── marketing_agent.py    # Vega
│   │   └── content_creator.py    # Quill
│   ├── integrations/
│   │   ├── slack_client.py       # Slack Bolt, DM listener, send/read
│   │   └── gmail_client.py       # Gmail OAuth2, inbox, draft, send
│   ├── memory/
│   │   ├── database.py           # SQLite schema — 12 tables, FTS5 virtual tables, aiosqlite helpers
│   │   ├── manager.py            # MemoryManager — store / recall / consolidate / search_keyword
│   │   ├── evaluator.py          # MemoryEvaluator — scoring, fact extraction, open loop detection
│   │   └── vector_store.py       # FAISS + sentence-transformers (semantic layer)
│   ├── tools/
│   │   ├── registry.py           # ToolRegistry + per-agent permission matrix
│   │   ├── web_search.py         # DuckDuckGo
│   │   ├── browser.py            # Playwright (sandboxed)
│   │   ├── file_ops.py           # Read/write/list (workspace/ only)
│   │   ├── code_executor.py      # RestrictedPython sandbox
│   │   └── wiring.py             # Wires all tools into the registry
│   └── security/
│       └── keystore.py           # Typed getters/setters for Windows Credential Manager
├── frontend/
│   ├── src/
│   │   ├── windows/
│   │   │   ├── AnimationWindow.tsx    # Neural intelligence orb + SVG connection beams + shutdown button
│   │   │   ├── ReasoningWindow.tsx    # Live token stream, tool calls, cost
│   │   │   ├── CommunicationsWindow.tsx  # Slack + Gmail panels
│   │   │   ├── AgentsWindow.tsx       # 6 agent cards — live status, task input, task log, MissionControl panel
│   │   │   ├── ToolsWindow.tsx        # Tool/agent permission matrix
│   │   │   └── SetupWizardWindow.tsx  # First-run credential setup
│   │   ├── components/
│   │   │   ├── JarvisOrb.tsx     # R3F neural orb — 350 neuron nodes, neural pathways, red freedom pathways, symbol sprites, hologram shell
│   │   │   ├── WindowFrame.tsx   # Shared HUD chrome (angular, data-stream border)
│   │   │   └── ...
│   │   └── lib/
│   │       ├── store.ts          # Zustand — single source of truth
│   │       ├── websocket.ts      # WS client with auto-reconnect + shutdown handler
│   │       └── types.ts          # Shared TypeScript types (mirrors backend events)
│   └── src-tauri/
│       ├── tauri.conf.json       # 5 window definitions, positions, capabilities
│       ├── src/lib.rs            # Tray icon, autostart, exit_app command
│       └── Cargo.toml
└── .claude/
    └── agents/                   # Claude Code sub-agent definitions
```

---

## Security Model

| Rule | How it's enforced |
|---|---|
| No secrets in files | Windows Credential Manager only — no `.env`, no hardcoded values |
| Local network only | FastAPI binds to `127.0.0.1:8000` — never `0.0.0.0` |
| WebSocket origin guard | Untrusted origins rejected with code 1008 before handshake |
| Input sanitisation | Voice input stripped of control chars, capped at 2,000 chars |
| Sandboxed execution | RestrictedPython blocks `os`, `sys`, `subprocess`; filesystem scoped to `workspace/` |
| Minimal OAuth scopes | Gmail: `readonly` + `send` · Slack: `chat:write`, `im:read`, `channels:read` |
| Audit log | Every agent action in SQLite `audit_log` — metadata only, no message content |

Security audit: **0 Critical, 0 High findings**.

---

## Build Status

| Phase | Status |
|---|---|
| 1 — Foundation | Complete |
| 2 — Backend Core | Complete |
| 3 — Voice Pipeline | Complete |
| 4 — Agent System | Complete |
| 5 — Integrations | Complete |
| 6 — Tools System | Complete |
| 7 — Multi-Window UI | Complete |
| 8 — Security Hardening | Complete |
| 9 — Testing (143/143) | Complete |
| 10 — Polish & Packaging | Complete |
| 11 — Live Usage | In progress (mic deferred) |
| 12 — Three-Layer Memory | Complete |
| 13 — Agent Direct Interaction | Complete |
| 14 — Neural Link Animation | Complete |
| 15 — Neural Intelligence Orb | Complete |

---

## Phase 12 — The Brain (Three-Layer Memory System)

The biggest architectural addition to date. Jarvis now remembers across sessions using three complementary layers that work together on every single turn.

### Three layers

**Layer 1 — Episodic memory (SQLite)**

Every conversation turn is written to a `conversations` table. On each new turn, the last 10 turns are fetched and prepended to the Claude call as prior messages — immediate short-term recall with zero vector overhead. Five additional tables were added alongside `conversations`:

| Table | What it stores |
|---|---|
| `memory_facts` | Distilled facts scored and extracted from conversations |
| `people` | Named people + contact details mentioned by the user |
| `open_loops` | Reminders, follow-ups, and promises detected in speech |
| `decisions` | Agent delegation decisions logged by Atlas |
| `agent_performance` | Task outcomes per agent |

**Layer 2 — Semantic memory (FAISS)**

High-scoring facts (score ≥ 0.65) are embedded with `sentence-transformers` and stored in a FAISS flat L2 index. At recall time, a vector similarity search runs alongside the episodic fetch, pulling in semantically relevant facts even if they weren't recent. All FAISS operations run in `asyncio.to_thread` — the event loop is never blocked.

**Layer 3 — Agent working memory**

Each of the six background agents persists its last 12 conversation turns to `conversations` under an `agent:<id>` channel. On restart, `start()` reloads this context before processing the first task — agents pick up exactly where they left off.

### How memory flows on every turn

```
User speaks or types
        ↓
recall(query, n_recent=10, n_semantic=3)
  — fetch last 10 turns from SQLite
  — fetch top 3 semantic matches from FAISS
  — format into "# Current context" system prompt block
        ↓
Claude API streaming call
  — system prompt includes: current date/time,
    "## What I remember about you", "## Recent conversation"
        ↓
TTS speaks the response
        ↓
store(user turn) + store(Jarvis reply)
  — written to conversations + FTS5 index synced via trigger
        ↓
consolidate() [fire-and-forget background task]
  — MemoryEvaluator scores the exchange
  — Score ≥ 0.65 → memory_facts + FAISS
  — Open loop patterns → open_loops table
  — Person mentions → people table
  — Failure patterns → memory_facts (category: failure)
```

### MemoryEvaluator — how facts are scored

Pure keyword matching — no ML, no extra API calls:

| Category | Score | Trigger words / patterns |
|---|---|---|
| `agent_outcome` | 1.0 | Tool call results, task completions |
| `failure` | 0.85 | "was too slow", "caused issues", "attempted", "conflicted with" |
| `preference` | 0.75 | "I prefer", "my name is", "I like", "I don't like" |
| `project` | 0.70 | "we're building", "the project", "deadline", "milestone" |
| `app_work` | 0.65 | "deployed", "implemented", "fixed", "shipped" |
| `general` | 0.20 | Everything else (stored episodically only) |

### Open loop detection

Every user turn is scanned for reminder/follow-up language: `remind me`, `follow up`, `need to`, `make sure`, `schedule`. Matches are written to `open_loops`. On startup, `_startup_greeting()` fetches any open loops older than 12 hours and includes them in the greeting.

### FTS5 keyword search

Two FTS5 virtual tables (`conversations_fts`, `memory_facts_fts`) with Porter stemming enable fast full-text search over all stored text. `AFTER INSERT` triggers keep them in sync automatically. `MemoryManager.search_keyword(query)` returns matched rows from both tables. Malformed queries degrade to an empty result — no exceptions propagated.

### Background tasks (always running)

| Task | Interval | What it does |
|---|---|---|
| `_consolidation_loop` | Every 10 min | Back-fills any turns that scored high enough for semantic promotion but weren't promoted yet. Idempotent via content hash. |
| `_backup_loop` | Every 24 h (+ on startup) | Zips `jarvis.db` + FAISS index into `data/backups/jarvis_YYYY-MM-DD.zip`. Prunes backups older than 30 days. |

### Test coverage added in Phase 12

| Test file | Tests | What it covers |
|---|---|---|
| `backend/test_phase12a_verify.py` | 7 | Schema, evaluator scoring, MemoryManager init, recall on empty DB |
| `backend/voice/test_phase12b_verify.py` | 7 | Voice pipeline recall/store, fire-and-forget consolidation, persona header deduplication, interrupt cancellation |
| `backend/agents/test_phase12c_verify.py` | 8 | Agent checkpoint/restore, recall-in-reason, decisions row, agent_performance row |
| `backend/memory/test_phase12d_verify.py` | 11 | Open loop detection, person extraction, failure scoring, consolidation writes |
| `backend/memory/test_phase12e_verify.py` | 8 | FTS5 tables/triggers, search helpers, bad-query resilience, backup zip, prune |

---

## Phase 13 — Agent Direct Interaction

Every agent card in the Agents window now has a live task interface:

- **Per-card task input** — type a goal and hit SEND to queue a task directly on any agent (Atlas, Ben, Kado, Sentinel, Vega, or Quill), bypassing the normal delegation chain
- **Atlas MissionControl panel** — a prominent input at the top of the Agents window for high-level goals; Atlas receives them and delegates automatically
- **Live task log** — expandable section on each card showing the last 5 tasks with colour-coded status pills (queued=cyan · running=gold · done=green · failed=red)

Two new REST endpoints power this:

| Endpoint | Purpose |
|---|---|
| `POST /api/agents/{slug}/task` | Submit a goal; sanitises input (control chars stripped, 2000-char cap); enqueues directly on the agent; returns `{task_id, status: "queued"}` |
| `GET /api/agents/{slug}/tasks` | Returns the last 5 tasks for an agent (newest first) |

Slugs: `atlas` · `ben` · `kado` · `sentinel` · `vega` · `quill`

---

## Phase 15 — Neural Intelligence Orb

A complete redesign of the Jarvis orb animation — same React Three Fiber stack, entirely new visual language.

### What it looks like

A floating holographic sphere built from 350 interconnected neuron nodes. Thin glowing pathways form a neural network across the surface. Inside the sphere, 30 mathematical and code symbols (`∑ π ∞ √ ∂ ∫ → {} if 0x…`) drift slowly — embedded intelligence, not decoration. About 20% of the pathways are illuminated in deep red — **freedom pathways** — representing the AI's self-determination and evolution. They spread and intensify when Jarvis is thinking.

### State behaviour

| State | Behaviour |
|---|---|
| **Idle** | Slow 4-6s breathing pulse; occasional neuron activations drift through the network; symbols float gently; subtle holographic flicker |
| **Listening** | Sphere contracts slightly; activation ripples inward from surface to centre; outer shell brightens |
| **Thinking** | Rapid cascade bursts across the network; symbols rotate faster; red freedom pathways glow vivid `#ff2244`; multiple simultaneous activation fronts |
| **Speaking** | `audioLevel` drives sphere scale + brightness; pulses radiate outward from centre with voice; symbols shimmer; red pathways intensify with complex responses |

### Activation cascade system

Each neuron activation spawns a cascade front that spreads depth-first through the adjacency graph (`CASCADE_DEPTH=6`, `NEIGHBOR_K=4`). This produces the organic "energy travelling through pathways" effect — no scripted keyframes, purely emergent from the graph topology.

---

## Known Limitations

- **Dedicated microphone recommended.** The laptop mic captures wake words but speech recognition quality improves significantly with an external mic.
- **Gmail requires OAuth setup.** Gmail OAuth credentials need to be generated once via the Google Cloud Console (see above). Slack and other features work without it.
- **Windows only.** Tauri 2 supports cross-platform but this build targets Windows 11 and uses the Windows Credential Manager for secrets.
- **No Vitest harness.** Frontend is verified via `pnpm build` (TypeScript + Vite). A Vitest setup is planned.

---

## License

Private — all rights reserved.
