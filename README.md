# Helix

> *"A subtle intelligence, sir. Always at your service."*

A local-first personal AI assistant for Windows 11. Say the wake phrase — it wakes, listens, thinks, and speaks back in a calm British voice. HUD windows float on your desktop like an Iron Man interface. Six background agents run 24/7 handling code, content, security, and communications.

> **Naming note:** the assistant is **Helix**. The spoken wake phrase is still **"Hey Jarvis"** — that is the pre-trained OpenWakeWord model (`hey_jarvis`), and it stays until a custom `hey_helix` model is trained. The codebase, persona, and UI were renamed Jarvis → Helix in Tier 0; a handful of internal identifiers (`jarvis.db`, the `jarvis` keyring service, `JARVIS_*` env vars, the `hey_jarvis` wake model) are intentionally left unchanged to avoid breaking persisted state and detection.

---

## Demo

> 🎬 **Helix Short** — a quick look at Helix running on the desktop.

<!--
  HOW TO EMBED THE VIDEO (one-time, done from GitHub's web UI):
    1. Open this README on github.com and click the ✏️ (Edit) pencil.
    2. Drag-and-drop your "Helix Short.mp4" file onto the line just below this comment.
    3. GitHub uploads it and auto-inserts an inline <video> player (a
       https://github.com/user-attachments/assets/... link). Then Commit changes.
  Note: References/ is gitignored, so the local .mp4 isn't in the repo — GitHub
  hosts the uploaded copy on its CDN, which is what lets it play inline.
-->

*▶️ Demo video goes here — drop **Helix Short.mp4** in via the GitHub editor (see the comment above).*

---

## What It Does

| Feature | Description |
|---|---|
| **Voice activation** | Say "Hey Jarvis" — OpenWakeWord detects it locally, no API key needed |
| **Natural conversation** | Claude Opus 4.7 streams the reply; Ollama (`phi3.5`) runs offline if Claude is unavailable |
| **Custom voice** | ElevenLabs — calm, precise British delivery with a faint digital resonance |
| **HUD windows** | Neural intelligence orb · Live reasoning stream · Communications panel · Agent dashboard · Tools grid (Memory graph window — Phase 16F — in progress) |
| **Six background agents** | Atlas (Lead) · Ben (Frontend) · Kado (Backend) · Sentinel (Security) · Vega (Marketing) · Quill (Content) |
| **Direct agent control** | Submit tasks to any agent from the Agents window — Atlas MissionControl panel + per-card task input + live task log |
| **Slack + Gmail** | Read, draft, and reply by voice — now live in the Communications window via WebSocket |
| **Intelligent memory** | Three-layer brain (SQLite episodic + FAISS semantic + agent working memory) with multi-signal recall, LLM-driven fact extraction, contradiction resolution, and natural forgetting (see Phase 16) |
| **Sandboxed tools** | Web search, browser automation, file ops, RestrictedPython code runner |
| **Startup greeting** | Helix greets you by name and reads the system status when windows open |
| **One-click shutdown** | ⏻ button on the orb window exits all windows cleanly |

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
| Memory extraction | Claude Haiku 4.5 (`claude-haiku-4-5`) primary, Ollama `phi3.5` offline fallback |
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
| Testing | pytest + pytest-asyncio (196 backend tests) |

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
git clone https://github.com/GDGuzman11/jarvis.git
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

Helix stores **all secrets in the Windows Credential Manager** — nothing in files.

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

### 4. Create your Helix voice (ElevenLabs)

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

The windows open on your desktop. First launch compiles Rust (~3–5 min). Subsequent launches are instant.

**To shut down:** click the **⏻ button** on the orb window (top-right corner). All windows close immediately.

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

**196 backend tests passing**, secret-scan green, `pnpm build` clean.

---

## Window Layout

When launched, the windows arrange around the central orb:

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
        (MEMORY graph window — Phase 16F — joins below the orb)
```

All windows are draggable by their header. The orb window has a drag grip at the bottom edge.

---

## Talking to Helix

1. Say **"Hey Jarvis, [your question]"** — say it as one sentence without pausing *(wake phrase is still `hey_jarvis` until a custom `hey_helix` model is trained)*
2. The orb turns **cyan** while listening, **gold** while thinking, **cyan** while speaking
3. Helix responds through your speakers

**Example commands:**
- *"Hey Jarvis, what's in my Slack?"*
- *"Hey Jarvis, summarise my unread emails"*
- *"Hey Jarvis, search for the latest news on X"*
- *"Hey Jarvis, what's the status of all agents?"*
- Say **"stop"** mid-response to interrupt

---

## Project Structure

```
Helix/   (folder is still named Jarvis/ on disk)
├── CLAUDE.md                     # Master build checklist (agents read this)
├── .env.example                  # Credential reference — no real values
├── pyproject.toml                # Python project (uv)
├── backend/
│   ├── main.py                   # FastAPI app + startup greeting + shutdown + background loops
│   ├── events.py                 # WebSocket event schema (token, tool_call, comms, tool_permissions, shutdown)
│   ├── websocket_hub.py          # Fan-out hub for all windows
│   ├── ai/
│   │   ├── claude_client.py      # Anthropic SDK, streaming, prompt caching, non-streaming complete()
│   │   ├── ollama_client.py      # Local fallback
│   │   └── persona.py            # Helix system prompt (recall sanitized in <untrusted_memory>)
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
│   │   ├── slack_client.py       # Slack Bolt, DM listener, send/read, comms broadcast
│   │   └── gmail_client.py       # Gmail OAuth2, inbox, draft, send, comms broadcast
│   ├── memory/
│   │   ├── database.py           # SQLite schema, FTS5, bi-temporal columns, aiosqlite helpers
│   │   ├── manager.py            # MemoryManager — multi-signal recall, TOKI operators, decay
│   │   ├── evaluator.py          # Keyword rule pre-filter (gates the LLM extractor)
│   │   ├── extractor.py          # LLMExtractor — Haiku/phi3.5 fact extraction (ADD/UPDATE/DELETE/NOOP)
│   │   └── vector_store.py       # FAISS + sentence-transformers + tombstoning
│   ├── tools/
│   │   ├── registry.py           # ToolRegistry + permission matrix + tool_call/permissions broadcast
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
│   │   │   ├── ReasoningWindow.tsx    # Live token stream, tool call cards, cost
│   │   │   ├── CommunicationsWindow.tsx  # Slack + Gmail panels
│   │   │   ├── AgentsWindow.tsx       # 6 agent cards — live status, task input, task log, MissionControl panel
│   │   │   ├── ToolsWindow.tsx        # Tool/agent permission matrix
│   │   │   └── SetupWizardWindow.tsx  # First-run credential setup
│   │   ├── components/
│   │   │   ├── HelixOrb.tsx      # R3F neural orb — 350 neuron nodes, neural pathways, red freedom pathways, symbol sprites, hologram shell
│   │   │   ├── WindowFrame.tsx   # Shared HUD chrome (angular, data-stream border)
│   │   │   └── ...
│   │   └── lib/
│   │       ├── store.ts          # Zustand — single source of truth
│   │       ├── websocket.ts      # WS client with auto-reconnect + shutdown handler
│   │       └── types.ts          # Shared TypeScript types (mirrors backend events)
│   └── src-tauri/
│       ├── tauri.conf.json       # Window definitions, positions, capabilities
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
| Recalled-memory sanitisation | Recalled facts wrapped in `<untrusted_memory>` + control chars stripped before injection into the system prompt |
| Sandboxed execution | RestrictedPython blocks `os`, `sys`, `subprocess`; filesystem scoped to `workspace/` |
| Minimal OAuth scopes | Gmail: `readonly` + `send` · Slack: `chat:write`, `im:read`, `channels:read` |
| Audit log | Every agent action in SQLite `audit_log` — metadata only, no message content |
| Secret scan | `test_no_secrets_committed_in_source_files` — suite is green (no committed secrets) |

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
| 9 — Testing | Complete |
| 10 — Polish & Packaging | Complete |
| 11 — Live Usage | In progress (mic deferred) |
| 12 — Three-Layer Memory | Complete |
| 13 — Agent Direct Interaction | Complete |
| 14 — Neural Link Animation | Complete |
| 15 — Neural Intelligence Orb | Complete |
| 15B — WebSocket Event Wiring | Complete |
| 16A — Memory Foundation + Safety | Complete |
| 16B — Multi-Signal Re-Ranking | Complete |
| 16C — LLM-Driven Extraction | Complete |
| 16D — Bi-Temporal + Ebbinghaus + TOKI | Complete |
| 16E — ColBERT + Self-Reflection | Optional (deferred) |
| 16F — Memory Graph Window | Next |
| 17 — Computer Eyes & Hands | Planned |

Also complete: **Tier 0 hygiene** — Jarvis → Helix rename, OAuth client-id scrub (suite secret-scan green), WAL-safe SQLite backup.

---

## Phase 12 — The Brain (Three-Layer Memory System)

The first major memory architecture. Helix remembers across sessions using three complementary layers that work together on every turn.

**Layer 1 — Episodic memory (SQLite).** Every conversation turn is written to a `conversations` table; the last 10 turns are prepended to the Claude call. Additional tables: `memory_facts`, `people`, `open_loops`, `decisions`, `agent_performance`.

**Layer 2 — Semantic memory (FAISS).** High-scoring facts are embedded with `sentence-transformers` and stored in a FAISS index. A vector similarity search runs alongside the episodic fetch. All FAISS operations run in `asyncio.to_thread`.

**Layer 3 — Agent working memory.** Each of the six agents persists its last 12 turns under an `agent:<id>` channel and reloads on restart.

The keyword `MemoryEvaluator` (scoring table below) is now used as a **fast pre-filter** that gates the LLM extractor added in Phase 16C — an exchange that matches no rule never reaches the LLM.

| Category | Score | Trigger words / patterns |
|---|---|---|
| `agent_outcome` | 1.0 | Tool call results, task completions |
| `failure` | 0.85 | "was too slow", "caused issues", "attempted", "conflicted with" |
| `preference` | 0.75 | "I prefer", "my name is", "I like", "I don't like" |
| `project` | 0.70 | "we're building", "the project", "deadline", "milestone" |
| `app_work` | 0.65 | "deployed", "implemented", "fixed", "shipped" |
| `general` | 0.20 | Everything else (stored episodically only) |

---

## Phase 16 — Memory Intelligence

A major upgrade that takes the memory system from "stores and recalls" to "reasons about what it knows." All local-first, no new cloud dependencies beyond the Claude API already in use.

**16A — Foundation + Safety.** Recalled facts are wrapped in an `<untrusted_memory>` delimiter and stripped of control characters before injection into the system prompt (closes a prompt-injection vector once Slack/email bodies become facts). The dormant `last_recalled_at` column is now written on every recall, and quality columns (`confidence`, `created_by`, `source_turn_id`, `access_count`) were added.

**16B — Multi-Signal Re-Ranking.** Recall is no longer similarity-only. FAISS returns a candidate pool, then each candidate is scored by a weighted composite: `0.40 × semantic + 0.20 × keyword(FTS5) + 0.20 × recency + 0.10 × importance + 0.10 × frequency`. Recently-recalled, important, and frequently-accessed facts surface above equally-similar stale ones. `access_count` increments on every recall hit.

**16C — LLM-Driven Extraction.** Brittle keyword extraction is replaced by an LLM that reads each turn and classifies facts as `ADD` / `UPDATE` / `DELETE` / `NOOP` (structured JSON). **Claude Haiku 4.5** is the primary extractor with **Ollama `phi3.5`** as an offline fallback; extraction runs asynchronously off the voice hot path, gated behind the keyword pre-filter. Paraphrases ("I moved to Boston" / "Boston is where I live now") collapse into a single fact via FAISS-similarity dedup (≥ 0.85).

**16D — Bi-Temporal Facts + Ebbinghaus Decay + TOKI Operators.** Facts gain validity windows (`valid_from`/`valid_to`), `strength`, and a `write_policy`. Contradictions are resolved by policy: `last-write-wins` (locations/status), `evidence-weighted` (preferences/allergies), `merge` (employment/relationships — non-overlapping windows), `await-confirmation` (cross-linked, surfaced to Helix at session start). A nightly Ebbinghaus decay job (`strength × exp(-days/half_life)`) archives facts below `strength < 0.1`. Superseded, deleted, and decayed facts are tombstoned in FAISS and excluded from active recall.

**16F — Memory Graph Window (next).** A 6th Tauri window rendering a force-directed graph of all facts — nodes colored by type and sized by recall frequency, edges by semantic similarity, with a hover HUD panel and live `memory_update` WebSocket events.

### How memory flows on every turn

```
User speaks or types
        ↓
recall(query)  — FAISS candidate pool → multi-signal composite re-rank → top-N
              — recalled facts stamped (last_recalled_at, access_count++)
              — formatted into <untrusted_memory> system-prompt block
        ↓
Claude API streaming call (system prompt: date/time + recalled facts + recent turns)
        ↓
TTS speaks the response
        ↓
store(user turn) + store(Helix reply)   — conversations + FTS5 synced via trigger
        ↓
consolidate()  [fire-and-forget background task, off the hot path]
  — keyword pre-filter gates →
  — LLMExtractor (Haiku → phi3.5) extracts facts, classifies ADD/UPDATE/DELETE/NOOP
  — TOKI write-policy resolves contradictions; FAISS tombstones stale vectors
        ↓
nightly: Ebbinghaus decay archives faded facts
```

---

## Known Limitations

- **Dedicated microphone recommended.** The laptop mic captures wake words but speech recognition quality improves significantly with an external mic.
- **Wake phrase is still "Hey Jarvis."** A custom `hey_helix` OpenWakeWord model has not been trained yet.
- **Gmail requires OAuth setup.** Gmail OAuth credentials need to be generated once via the Google Cloud Console (see above). Slack and other features work without it.
- **Windows only.** Tauri 2 supports cross-platform but this build targets Windows 11 and uses the Windows Credential Manager for secrets.
- **No Vitest harness.** Frontend is verified via `pnpm build` (TypeScript + Vite). A Vitest setup is planned.

---

## License

Private — all rights reserved.
