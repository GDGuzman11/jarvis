# Jarvis

> *"A subtle intelligence, sir. Always at your service."*

A local-first personal AI assistant for Windows 11. Wakes on voice command, understands natural speech, responds in a measured British tone, and runs a team of six background AI agents around the clock.

All credentials are stored in the Windows Credential Manager. No secrets ever touch the filesystem.

---

## What It Does

- **Voice-activated** -- say "hey Jarvis" and it wakes, listens, thinks, and speaks back
- **Claude Opus 4.7** as the primary brain, with Ollama (`phi3.5`) as a fully offline fallback
- **Five simultaneous windows** on boot: animated orb, live reasoning stream, communications panel, agent dashboard, and tools store
- **Six named background agents** running 24/7: Production Lead (Atlas), Ben (Frontend), Kado (Backend), Sentinel (Security), Vega (Marketing), and Quill (Content)
- **Slack and Gmail integration** -- read, draft, and send via voice
- **Persistent memory** -- conversations in SQLite, semantic recall via FAISS vector search
- **Sandboxed tool execution** -- web search, browser automation, file ops, and a RestrictedPython code runner

---

## Hardware Requirements

| Component | Minimum      | This Build                        |
|-----------|--------------|-----------------------------------|
| GPU       | 4 GB VRAM    | NVIDIA RTX 3050 Ti Laptop (4 GB)  |
| RAM       | 16 GB        | 16 GB                             |
| OS        | Windows 11   | Windows 11                        |
| Python    | 3.12         | 3.12.x (managed via uv)           |
| Node.js   | 20+          | 20+ (pnpm)                        |
| Rust      | stable       | rustup stable (for Tauri builds)  |

Local LLMs are sized for 4 GB VRAM: `phi3.5` (3.8B, ~2.4 GB) for general tasks and `qwen2.5-coder:3b` (~2 GB) for code. The Claude API handles everything that needs more capability.

---

## Tech Stack

| Layer             | Technology                                                   |
|-------------------|--------------------------------------------------------------|
| Backend           | Python 3.12, FastAPI, WebSockets, Uvicorn                    |
| Primary AI        | Anthropic Claude API (`claude-opus-4-7`, streaming + caching)|
| Local AI fallback | Ollama (`phi3.5`, `qwen2.5-coder:3b`)                        |
| Wake Word         | OpenWakeWord (`hey_jarvis` model, fully local, no API key)   |
| Speech-to-Text    | faster-whisper (Whisper base.en, local)                      |
| Text-to-Speech    | ElevenLabs (custom voice -- Tom Hardy x Avengers Jarvis)     |
| Frontend          | Tauri 2, React 19, TypeScript 5, Vite 6                      |
| Styling           | Tailwind CSS 4, glassmorphism dark theme                     |
| 3D Animation      | Three.js / React Three Fiber                                 |
| State             | Zustand 5, WebSocket sync                                    |
| Database          | SQLite (aiosqlite)                                           |
| Vector Memory     | FAISS + sentence-transformers                                |
| Credentials       | Windows Credential Manager (keyring)                         |
| Integrations      | Slack Bolt, Gmail API (OAuth2)                               |
| Logging           | structlog                                                    |
| Testing           | pytest + pytest-asyncio, Vitest                              |

---

## Installation

### 1. Clone the repository

```powershell
git clone https://github.com/gabedeguzman/jarvis.git
cd jarvis
```

### 2. Install Python dependencies

Install [uv](https://github.com/astral-sh/uv) if you do not have it:

```powershell
winget install astral-sh.uv
```

Then sync the project:

```powershell
uv sync --extra dev
```

Verify the install:

```powershell
.venv\Scripts\python.exe -c "import fastapi, anthropic, keyring, aiosqlite; print('OK')"
```

> **Note:** OpenWakeWord has a known Python 3.12 / uv resolver conflict on Windows due to its
> `tflite-runtime` dependency. After `uv sync`, install it separately:
>
> ```powershell
> uv pip install openwakeword
> ```

### 3. Install frontend dependencies

```powershell
cd frontend
pnpm install
```

Tauri native builds also require the [Rust toolchain](https://rustup.rs/):

```powershell
winget install Rustlang.Rustup --accept-source-agreements
```

### 4. Install Ollama (local AI fallback)

Download from [ollama.com](https://ollama.com) and pull the models:

```powershell
ollama pull phi3.5
ollama pull qwen2.5-coder:3b
```

---

## Storing API Keys

Jarvis uses the **Windows Credential Manager** for all secrets. Nothing is stored in files.
Run the following once per machine:

```python
from backend.security import keystore

keystore.set_anthropic_api_key("sk-ant-...")
keystore.set_elevenlabs_api_key("your-elevenlabs-key")
keystore.set_elevenlabs_voice_id("your-voice-id")

# Slack
keystore.set_slack_bot_token("xoxb-...")
keystore.set_slack_app_token("xapp-...")
keystore.set_slack_signing_secret("your-signing-secret")

# Gmail (OAuth2)
keystore.set_gmail_client_id("your-client-id")
keystore.set_gmail_client_secret("your-client-secret")
keystore.set_gmail_redirect_uri("http://127.0.0.1:8000/oauth/gmail/callback")
```

Or use PowerShell directly:

```powershell
.venv\Scripts\python.exe -c "
from backend.security import keystore
keystore.set_anthropic_api_key('sk-ant-...')
"
```

See `.env.example` for the full list of credential names and where to obtain each one.

> OpenWakeWord runs entirely locally and requires **no API key**.

---

## Running

### Backend

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### Frontend (Tauri dev mode)

```powershell
cd frontend
pnpm tauri dev
```

This opens all five windows. Vite serves the React app on `localhost:1420`; Tauri wraps it in native windows.

### Tests

```powershell
.venv\Scripts\pytest.exe backend/ -v
```

All 46 backend tests should pass across Phases 3-6.

---

## Project Structure

```
Jarvis/
├── CLAUDE.md                    # Master build checklist (agents read this on every run)
├── .env.example                 # Credential name reference -- no real values
├── pyproject.toml               # Python project config (uv)
├── uv.lock                      # Locked dependencies (committed for reproducibility)
├── backend/
│   ├── main.py                  # FastAPI app + lifespan (DB, agents, voice, tools)
│   ├── events.py                # WebSocket event schema
│   ├── websocket_hub.py         # Fan-out hub for all 5 windows
│   ├── logging_config.py
│   ├── ai/
│   │   ├── claude_client.py     # Anthropic SDK, streaming, prompt caching
│   │   ├── ollama_client.py     # Local fallback
│   │   └── persona.py           # Jarvis system prompt
│   ├── voice/
│   │   ├── wake_word.py         # OpenWakeWord detection
│   │   ├── stt.py               # faster-whisper transcription
│   │   ├── tts.py               # ElevenLabs synthesis
│   │   └── pipeline.py          # Full wake->listen->think->speak loop
│   ├── agents/
│   │   ├── base_agent.py        # Task queue, status broadcasting, DB persistence
│   │   ├── runtime.py           # Starts and supervises all 6 agents
│   │   ├── production_lead.py   # Atlas -- orchestrator, goal routing
│   │   ├── frontend_agent.py    # Ben
│   │   ├── backend_agent.py     # Kado
│   │   ├── security_agent.py    # Sentinel
│   │   ├── marketing_agent.py   # Vega
│   │   └── content_creator.py   # Quill
│   ├── integrations/
│   │   ├── slack_client.py      # Slack Bolt, DM listener, send/read
│   │   └── gmail_client.py      # Gmail OAuth2, inbox, draft, send
│   ├── memory/
│   │   ├── database.py          # SQLite CRUD -- conversations, agents, tasks, audit log
│   │   └── vector_store.py      # FAISS + sentence-transformers
│   ├── tools/
│   │   ├── registry.py          # ToolRegistry + per-agent permission matrix
│   │   ├── web_search.py        # DuckDuckGo (async)
│   │   ├── browser.py           # Playwright automation (http/https only)
│   │   ├── file_ops.py          # Read/write/list (sandboxed to workspace/)
│   │   ├── code_executor.py     # RestrictedPython sandbox
│   │   ├── slack_tool.py
│   │   ├── gmail_tool.py
│   │   └── wiring.py            # build_tool_registry() -- wires everything together
│   └── security/
│       └── keystore.py          # Typed getters/setters for Windows Credential Manager
├── frontend/
│   ├── src/
│   │   ├── windows/             # 5 Tauri windows
│   │   │   ├── AnimationWindow.tsx   # Three.js orb (blue/gold/cyan by state)
│   │   │   ├── ReasoningWindow.tsx   # Live token stream, tool calls, cost
│   │   │   ├── CommunicationsWindow.tsx  # Slack + Gmail panels
│   │   │   ├── AgentsWindow.tsx      # 6 agent cards, live status
│   │   │   └── ToolsWindow.tsx       # Tool/agent permission matrix
│   │   ├── components/
│   │   │   ├── JarvisOrb.tsx    # React Three Fiber orb animation
│   │   │   ├── AgentCard.tsx
│   │   │   ├── ToolCard.tsx
│   │   │   ├── StreamViewer.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   └── WindowFrame.tsx
│   │   └── lib/
│   │       ├── store.ts         # Zustand -- single source of truth
│   │       ├── websocket.ts     # WS client with auto-reconnect
│   │       ├── api.ts
│   │       └── types.ts
│   └── src-tauri/
│       ├── tauri.conf.json      # 5 window definitions, positions, decorations
│       ├── Cargo.toml           # Tauri 2 Rust dependencies
│       └── Cargo.lock           # Locked Rust dependencies (committed for binary)
└── .claude/
    └── agents/                  # Claude Code sub-agent definitions
        ├── production-manager.md
        ├── backend-agent.md
        ├── frontend-agent.md
        ├── security-agent.md
        └── debugger-agent.md
```

---

## Build Progress

| Phase                    | Status   |
|--------------------------|----------|
| 1 - Foundation           | Complete |
| 2 - Backend Core         | Complete |
| 3 - Voice Pipeline       | Complete |
| 4 - Agent System         | Complete |
| 5 - Integrations         | Complete |
| 6 - Tools System         | Complete |
| 7 - Multi-Window UI      | Complete |
| 8 - Security Hardening   | Pending  |
| 9 - Testing              | Pending  |
| 10 - Polish and Packaging| Pending  |

See [CLAUDE.md](CLAUDE.md) for the detailed per-task checklist. Each phase is built by a dedicated Claude Code sub-agent and verified by a test suite before being marked complete.

---

## Security Model

| Rule | Implementation |
|------|----------------|
| No secrets in files | All credentials stored in Windows Credential Manager via `keyring` |
| Local network only | FastAPI binds to `127.0.0.1:8000` -- never `0.0.0.0` |
| Input sanitization | Voice input stripped of control chars, capped at 2,000 chars before reaching Claude |
| Sandboxed code execution | RestrictedPython blocks `os`, `sys`, `subprocess`; filesystem scoped to `workspace/` |
| Minimal OAuth scopes | Gmail: `readonly` + `send`; Slack: `chat:write`, `im:read`, `channels:read` |
| Audit logging | Every agent action written to SQLite `audit_log` (metadata only, no message content) |

---

## License

Private -- all rights reserved.
