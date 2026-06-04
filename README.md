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
| **Five HUD windows** | Particle orb · Live reasoning stream · Communications panel · Agent dashboard · Tools grid |
| **Six background agents** | Atlas (Lead) · Ben (Frontend) · Kado (Backend) · Sentinel (Security) · Vega (Marketing) · Quill (Content) |
| **Slack + Gmail** | Read, draft, and reply by voice |
| **Persistent memory** | SQLite for conversation history; FAISS + sentence-transformers for semantic recall |
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
| 3D animation | Three.js · React Three Fiber (particle orb + solar flares) |
| State | Zustand 5 · WebSocket sync |
| Database | SQLite (aiosqlite) |
| Vector memory | FAISS + sentence-transformers |
| Credentials | Windows Credential Manager (keyring) |
| Integrations | Slack Bolt · Gmail API (OAuth 2.0) |
| Testing | pytest + pytest-asyncio (85 backend tests) |

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

85 backend tests, all passing.

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
│   │   ├── database.py           # SQLite — conversations, agents, tasks, audit log
│   │   └── vector_store.py       # FAISS + sentence-transformers
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
│   │   │   ├── AnimationWindow.tsx    # Particle orb + solar flares + connection beams
│   │   │   ├── ReasoningWindow.tsx    # Live token stream, tool calls, cost
│   │   │   ├── CommunicationsWindow.tsx  # Slack + Gmail panels
│   │   │   ├── AgentsWindow.tsx       # 6 agent cards, live status
│   │   │   ├── ToolsWindow.tsx        # Tool/agent permission matrix
│   │   │   └── SetupWizardWindow.tsx  # First-run credential setup
│   │   ├── components/
│   │   │   ├── JarvisOrb.tsx     # R3F orb — 2500 particles + 60-particle solar flares
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
| 9 — Testing (85/85) | Complete |
| 10 — Polish & Packaging | Complete |
| 11 — Live Usage | In progress |

---

## Known Limitations

- **Dedicated microphone recommended.** The laptop mic captures wake words but speech recognition quality improves significantly with an external mic.
- **Gmail requires OAuth setup.** Gmail OAuth credentials need to be generated once via the Google Cloud Console (see above). Slack and other features work without it.
- **Windows only.** Tauri 2 supports cross-platform but this build targets Windows 11 and uses the Windows Credential Manager for secrets.
- **No Vitest harness.** Frontend is verified via `pnpm build` (TypeScript + Vite). A Vitest setup is planned.

---

## License

Private — all rights reserved.
