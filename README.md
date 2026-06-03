# Jarvis

> *"A subtle intelligence, sir. Always at your service."*

A local-first personal AI assistant for Windows 11. Wakes on voice command, understands natural speech, responds in a measured British tone, and runs a team of six background AI agents around the clock.

Built on the Claude API with local LLM fallback — all data stays on-device, all credentials in the Windows Credential Manager. No data leaves your machine except to the APIs you explicitly configure.

---

## What Jarvis Does

- **Voice-activated** — say "Jarvis" and it wakes up, listens, thinks, and speaks back
- **Claude Opus 4.7** as the primary intelligence, with `phi3.5` (Ollama) as offline fallback
- **Five simultaneous windows** on boot: animated orb, live reasoning stream, communications panel, agent dashboard, tools store
- **Six named background agents** running 24/7: Production Lead, Ben (Frontend), Kado (Backend), Security, Marketing, Content Creator
- **Slack + Gmail integration** — read, draft, and send via voice command
- **Full memory** — conversations stored in SQLite, semantic recall via FAISS vector search

---

## Hardware Requirements

| Component | Minimum | This Build |
|---|---|---|
| GPU | 4 GB VRAM | NVIDIA RTX 3050 Ti Laptop (4 GB) |
| RAM | 16 GB | 16 GB |
| OS | Windows 11 | Windows 11 |
| Python | 3.12 | 3.12.x (via uv) |
| Node.js | 20+ | 20+ (pnpm) |

> Local LLMs are sized for 4 GB VRAM: `phi3.5` (3.8B, ~2.4 GB) for general tasks and `qwen2.5-coder:3b` (~2 GB) for code. Claude API handles everything that needs more capability.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · WebSockets · Uvicorn |
| Primary AI | Anthropic Claude API (`claude-opus-4-7`, streaming + prompt caching) |
| Local AI | Ollama (`phi3.5`, `qwen2.5-coder:3b`) |
| Wake Word | openWakeWord (local, "hey_jarvis" model — no API key) |
| Speech-to-Text | faster-whisper (local Whisper base.en) |
| Text-to-Speech | ElevenLabs (custom voice — Tom Hardy × Avengers Jarvis) |
| Frontend | Tauri 2 · React 19 · TypeScript 5 · Vite 6 |
| Styling | Tailwind CSS 4 · glassmorphism dark theme |
| 3D Animation | Three.js / React Three Fiber |
| State | Zustand 5 · WebSocket sync |
| Database | SQLite (aiosqlite) |
| Vector Memory | FAISS + sentence-transformers |
| Credentials | Windows Credential Manager (`keyring`) |
| Integrations | Slack Bolt · Gmail API (OAuth2) |
| Logging | structlog |
| Testing | pytest + pytest-asyncio · Vitest |

---

## Installation

### 1. Clone and install Python dependencies

```powershell
git clone <repo-url>
cd Jarvis
# Install uv if you don't have it
pip install uv
# Install all dependencies into an isolated .venv
uv sync
```

Verify the install:

```powershell
.venv\Scripts\python.exe -c "import fastapi, anthropic, keyring, aiosqlite"
# Should exit silently (no errors)
```

### 2. Install frontend dependencies

```powershell
cd frontend
pnpm install
```

> Tauri native bundling also requires the [Rust toolchain](https://rustup.rs/). Run `rustup default stable` if you plan to build the desktop `.exe`.

### 3. Install Ollama (local AI fallback)

Download from [ollama.com](https://ollama.com) and pull the recommended models:

```powershell
ollama pull phi3.5
ollama pull qwen2.5-coder:3b
```

---

## Storing API Keys

Jarvis uses the **Windows Credential Manager** for all secrets — nothing is stored in files. Use the helper module:

```python
# One-time setup (run once per machine, not on every start)
from backend.security import keystore

keystore.set_anthropic_api_key("sk-ant-...")
keystore.set_elevenlabs_api_key("your-elevenlabs-key")
# Note: wake word uses openWakeWord (fully local, no API key required)
keystore.set_slack_bot_token("xoxb-...")
keystore.set_slack_app_token("xapp-...")
keystore.set_slack_signing_secret("your-signing-secret")
keystore.set_gmail_client_id("your-client-id")
keystore.set_gmail_client_secret("your-client-secret")
```

Or via PowerShell directly:

```powershell
.venv\Scripts\python.exe -c "import keyring; keyring.set_password('jarvis', 'ANTHROPIC_API_KEY', 'sk-ant-...')"
```

See `.env.example` for the full list of credential names and where to obtain each key.

---

## First Run

> **Work in progress** — this section will be completed in Phase 10. For now, start the backend manually:

```powershell
# Start the FastAPI backend (Phase 2+)
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

The frontend and full boot sequence are being built in Phase 7.

---

## Project Structure

```
Jarvis/
├── CLAUDE.md              # Master build checklist — agents read this on every run
├── .env.example           # Credential name reference (no real values)
├── pyproject.toml         # Python project config (uv)
├── backend/
│   ├── main.py            # FastAPI app + WebSocket hub
│   ├── ai/                # Claude client, Ollama client, Jarvis persona
│   ├── voice/             # Wake word, STT (Whisper), TTS (ElevenLabs)
│   ├── agents/            # 6 background agents (BaseAgent + implementations)
│   ├── integrations/      # Slack Bolt, Gmail API
│   ├── memory/            # SQLite CRUD, FAISS vector store
│   ├── tools/             # Tool registry, web search, browser, file ops, code sandbox
│   └── security/          # keystore.py (Windows Credential Manager wrappers)
├── frontend/
│   ├── src/
│   │   ├── windows/       # 5 Tauri windows (Animation, Reasoning, Comms, Agents, Tools)
│   │   ├── components/    # JarvisOrb (Three.js), AgentCard, ToolCard, StreamViewer
│   │   └── lib/           # Zustand store, API client, WebSocket
│   └── src-tauri/         # Tauri 2 Rust backend + window config
└── .claude/
    └── agents/            # Claude Code sub-agents (production-manager, backend, frontend, security, debugger)
```

---

## Build Progress

See [CLAUDE.md](CLAUDE.md) for the live phase checklist. Each phase is built step-by-step with a dedicated sub-agent, and every task is verified by the debugger-agent before being marked complete.

| Phase | Status |
|---|---|
| 1 — Foundation | Complete |
| 2 — Backend Core | In Progress |
| 3 — Voice Pipeline | Pending |
| 4 — Agent System | Pending |
| 5 — Integrations | Pending |
| 6 — Tools | Pending |
| 7 — Multi-Window UI | Pending |
| 8 — Security Hardening | Pending |
| 9 — Testing | Pending |
| 10 — Polish & Packaging | Pending |

---

## Security

- All API keys live in Windows Credential Manager — never in files or environment variables
- FastAPI binds to `127.0.0.1` only — not accessible from the network
- Voice input sanitized before reaching Claude (strip control chars, 2000-char cap)
- Code execution sandbox blocks `os`, `sys`, `subprocess` — filesystem scoped to workspace only
- OAuth tokens use minimal scopes (Gmail: `readonly` + `send`; Slack: `chat:write`, `im:read`)
- Every agent action written to an audit log (metadata only, no message content)

---

## License

Private — all rights reserved.
