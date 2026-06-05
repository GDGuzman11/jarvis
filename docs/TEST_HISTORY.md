# Jarvis — Test Run History

> Maintained by debugger-agent. Add new test run entries at the top. Each entry includes date, scope, pass/fail counts, and any notable findings.

---

## Current State: 96/96 backend tests passing · frontend pnpm build clean

- **Tests Passed**: **96 backend** (`pytest backend/ -v` — all green, 37s) + **frontend `pnpm build` clean** ("built in 3.11s", 467 modules transformed, dist/ generated, 0 TS errors)
- **Tests Failed**: 0
- **Deferred**: 6 Phase 9 items (4 UI + 2 true-E2E) — require native Tauri app and/or a microphone + live API keys. No Vitest harness yet; frontend verified via `pnpm build` + grep.

---

## Phase 11C — MetricsEvent + _compute_cost (2026-06-04, 11/11 PASS · suite 96/96)
*(`backend/test_phase11c_metrics_verify.py` — pure/in-memory: no key, no network, no audio)*

- [x] Price constants — `PRICE_INPUT_PER_MTOK==15.00`, `PRICE_OUTPUT_PER_MTOK==75.00`, `PRICE_CACHE_WRITE_PER_MTOK==3.75`, `PRICE_CACHE_READ_PER_MTOK==1.50`.
- [x] `_compute_cost(1000,1000,0,0)` → **$0.09** (1000 in @ $15/M + 1000 out @ $75/M). Note: the task brief said $0.00009 — that was a 1000x typo.
- [x] `_compute_cost(0,0,1000,1000)` cache-only → **$0.00525** (1000 write @ $3.75/M + 1000 read @ $1.50/M).
- [x] `_compute_cost(1_000_000,1_000_000,0,0)` → **exactly $90.00**.
- [x] `_compute_cost(1M,1M,1M,1M)` all four buckets → $95.25; `_compute_cost(0,0,0,0)` → 0.0.
- [x] `MetricsEvent.type == "metrics"`; cache fields default to 0.
- [x] `MetricsEvent.to_dict()` → all 9 keys (cost_usd, latency_ms, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, type, timestamp); values round-trip; `to_json()` parses.
- [x] `"metrics"` present in `EventType` literal (`typing.get_args`).
- Signature note: `_compute_cost(input, output, cache_write, cache_read)` — cache_write before cache_read.

---

## Phase 10 — Backend Verification (2026-06-03, 14/14 PASS · suite 79/79)
*(`backend/test_phase10_backend_verify.py` — all mocked: no audio device, no network, no real keys)*

- [x] AudioLevelEvent shape — `events.AudioLevelEvent` has `type=="audio_level"` + `level`; defaults to 0.0; `to_dict()` round-trips.
- [x] `_rms_level` — silence→0.0, full-scale int16→~1.0, empty→0.0, >full-scale clips to 1.0.
- [x] `tts.speak_and_play` — every broadcast is an AudioLevelEvent with 0.0≤level≤1.0, at least one non-zero, and the LAST event is level==0.0.
- [x] AudioLevel finally-path — `_play_pcm_block_sync` raising mid-playback still broadcasts a final level==0.0 (finally block).
- [x] Crash recovery — 3 consecutive `_run_turn` crashes → `state=="error"`, `_consecutive_crashes==3`, no further retry.
- [x] Crash-counter reset — crash twice then one clean turn → `_consecutive_crashes` back to 0, state idle.
- [x] Graceful degradation — Claude raising `MissingCredentialError` or `ClaudeAPIError` pre-token → `_iter_reply` yields the Ollama tokens (fallback used).
- [x] No mid-stream fallback — Claude yields 1 token then raises → output is just that token; Ollama NOT called.
- [x] Setup wizard — isolated minimal-app TestClient + in-memory fake keyring: GET /setup/status all-missing → complete=false + 7 missing; POST stores + never echoes value; unknown name → 400; /setup/complete flips true once all 7 present; no secret value leaks.

---

## Phase 10 — Agent Rename + README (2026-06-03, 6/6 PASS · suite 85/85)
*(`backend/test_phase10_rename_verify.py`)*

- [x] Rename success — POST /api/agents/backend/rename → 200, returns `{"agent_id":"backend","name":"Kado Prime"}`; live agent `.name` mutated; DB write called once.
- [x] Broadcast — exactly one `AgentUpdate` emitted with correct fields.
- [x] Unknown agent — POST /api/agents/nope/rename → 404.
- [x] Empty after strip — name `"   "` → 400.
- [x] Too long — name 51 chars → 400.
- [x] Boundary — name exactly 50 chars (MAX_AGENT_NAME_LEN) → 200.
- [x] README.md — present and complete.

---

## Phase 9 — Testing & Verification (2026-06-03, backend 65/65 PASS · 6 items DEFERRED)

New suite `backend/test_phase9_verify.py` (19 cases). Full `pytest backend/` (65 tests across Phases 3–6 + 9) green.

**UNIT**
- [x] STT accuracy — mocked faster-whisper: int16 utterance → exact transcript; int16→float32 normalisation asserted; control-char strip + 2000-char cap; empty audio → "".
- [x] TTS output — mocked ElevenLabs `convert` → non-zero MP3 bytes; missing-key → empty bytes (graceful); empty text short-circuits.
- [x] Wake-word callback — FakeDetector `.fire()` drives pipeline out of idle (listening broadcast).

**INTEGRATION**
- [x] Full voice roundtrip — wake→listen→STT→Claude→TTS→idle, all 4 states broadcast in order; latency < 3s (mocked turn).
- [x] Claude streaming + tool use — mocked Anthropic stream; `cache_control: ephemeral` present; `tool_use` block exposed.
- [x] Ollama fallback — Claude raises `ClaudeAPIError` before any token → pipeline streams from Ollama. Mid-stream failure does NOT restart from Ollama.
- [x] Slack read/send (mocked) — Phase 5 suite: send/read/mentions normalise, missing-cred no-op.
- [x] Gmail read/draft/send (mocked) — Phase 5 suite: send/draft/inbox over deep-chained service mock, missing-cred no-op.
- [x] Agent delegation — ProductionLead keyword routing + `submit_goal` writes a `tasks` row and enqueues to the specialist.
- [x] Agent state persists across restart — 6 rows survive a fresh `AgentRuntime` against the same DB.

**SECURITY**
- [x] No secrets in source — regex scan across all `.py/.ts/.tsx/.js/.json/.toml/.md/.rs/.env*` → **0 matches**.
- [x] FastAPI bind — `main.HOST == "127.0.0.1"` and no executable `host="0.0.0.0"` line.
- [x] Code executor sandbox — `os.system`, `subprocess`, and dunder-escape all blocked.

**CONFIRMED LIVE (2026-06-04)**
- [x] UI: all 5 Tauri windows open on launch — confirmed
- [ ] UI: WebSocket connects within 2s — confirmed manually, no automated test
- [ ] UI: orb colour changes for idle/thinking/speaking — confirmed manually, no automated test
- [ ] UI: agent cards update in real-time on WS events — confirmed manually, no automated test

**DEFERRED (need dedicated mic + live credentials)**
- [ ] E2E: "Jarvis, what's in my Slack?" voice→Slack→speak
- [ ] E2E: "Jarvis, send an email…" voice→Gmail draft→send

**MINOR FINDING (non-blocking)**
- `backend/tools/code_executor.py` docstring lists "sum, range, sorted…" as allowed builtins, but RestrictedPython's `safe_builtins` does NOT expose these — they raise `NameError`. Sandbox is *more* restrictive than documented (errs safe). Recommend trimming the docstring's allowed-builtins list.

---

## Phase 7 — Multi-Window UI (2026-06-03, 7/7 checks PASS)

- [x] BUILD — `pnpm build` clean: `tsc` no TS errors, `vite` "built in 2.97s", `dist/` generated.
- [x] 5 window files present — Animation/Reasoning/Communications/Agents/Tools.
- [x] 4 components present — JarvisOrb/AgentCard/ToolCard/StreamViewer.
- [x] Zustand store — `frontend/src/lib/store.ts:111` exports `useStore` via `create<JarvisStore>`.
- [x] WebSocket — `frontend/src/lib/websocket.ts:14` `WS_URL = "ws://127.0.0.1:8000/ws"`.
- [x] Tauri config — `frontend/src-tauri/tauri.conf.json` defines 5 window labels.
- [x] App routing — `frontend/src/App.tsx` maps Tauri window label → component for all 5 windows.

---

## Phase 6 — Tools System (2026-06-03, 6/6 areas · 14/14 cases PASS)

- [x] Permission enforcement — production_lead gets all 12 tools; security agent gets exactly 7 read-only; `call_tool("security","write_file",…)` raises `PermissionError`.
- [x] Sandbox blocks dangerous code — `execute_code("import os\nos.system(…)")`→`success=False`; `execute_code("print('hello')")`→`success=True`.
- [x] Path traversal rejected — `../escape.txt` and absolute-outside paths raise `PathTraversalError`.
- [x] Web search — `WEB_SEARCH_SCHEMA` well-formed; `web_search("")` returns `[]` without crash or network call.
- [x] Claude schemas — every registered tool schema is well-formed; Slack (3) + Gmail (3) wrappers registered.
- [x] Lifespan — real `TestClient(app)`: `app.state.tool_registry` is a populated `ToolRegistry` (≥6 tools), `/health` 200.

---

## Phase 5 — Communication Integrations (2026-06-03, 6/6 checks · 9/9 cases PASS)

- [x] Missing credentials (Slack) — `MissingCredentialError` ⇒ all methods return safe no-ops.
- [x] Missing credentials (Gmail) — `MissingCredentialError` ⇒ all methods return safe no-ops.
- [x] Slack send — mocked `chat_postMessage`→{"ok": True} ⇒ `send_message`→True.
- [x] Slack read — mocked `conversations_open`+`conversations_history` ⇒ normalised `{user, text, ts}` dicts.
- [x] Slack listener — `_dispatch_notification(payload)` awaits `on_notification` AsyncMock exactly once.
- [x] Gmail send/draft/inbox — mocked Google service ⇒ `send_email`→True, `draft_email`→draft id string, `get_inbox`→`{id, from, subject, snippet}` dicts.
- [x] Lifespan — real ASGI `TestClient(app)`: `/health` 200; both slack/gmail clients constructed.

---

## Phase 4 — Agent System (2026-06-03, 12/12 PASS)

- [x] BaseAgent lifecycle — `start()` upserts idle row; enqueued task drives working→idle; `stop()` sets offline.
- [x] Status broadcasts — `working` then `idle` event in order on task processed.
- [x] DB persistence — after `AgentRuntime.start()`, `get_all_agents()` returns 6 rows with correct ids/names. A second fresh runtime on the same DB sees all 6 (offline) and can restart them.
- [x] Routing (×6 parametrized) — React/UI/Tauri→frontend, FastAPI/database→backend, security-audit→security.
- [x] Delegation — `submit_goal("...FastAPI server")` → target backend, `delegated=True`, integer `task_id`; `tasks` row created and specialist runs it to `done`.
- [x] Error recovery — `handle_task` that raises marks row `failed`, agent recovers to `idle`, run loop survives.
- [x] Lifespan — real ASGI `TestClient(app)`: `/health` 200; `app.state.agents` has 6 running agents.

---

## Phase 3 — Voice Pipeline (2026-06-03, 7/7 STT+TTS + 6/6 pipeline + 11/11 OWW PASS)

**STT + TTS**
- [x] Imports — `backend.voice.stt` and `backend.voice.tts` import without error.
- [x] STT — `transcribe(np.ones(16000, int16))` over mocked Whisper returns "hello world" (stripped/sanitised).
- [x] STT — `sanitize_transcript("Hi\x00\x07\x1b there\x08")` → "Hi there" (category-C control chars stripped).
- [x] STT — `sanitize_transcript("a"*5000)` capped to 2000 chars.
- [x] STT — empty audio `np.zeros(0, int16)` → "".
- [x] TTS — `speak("hi")` with mocked client returns joined bytes.
- [x] TTS — missing key: `get_elevenlabs_api_key` raising `MissingCredentialError` makes `speak("hi")` return b"" with no exception.

**Full Pipeline**
- [x] Full pipeline — wake fire drives states listening→thinking→speaking→idle in order; full reply spoken via TTS; ends idle.
- [x] Empty transcript — `stt.transcribe` returns "" → Claude never called, no `speaking` state, ends idle.
- [x] Interrupt — interrupt window transcribes "stop" → slow 50-token response cancelled before completion, pipeline returns to idle.
- [x] WebSocket broadcasts — all four states {listening, thinking, speaking, idle} emitted.
- [x] Lifespan — `app.state.voice_pipeline` is always non-None after startup.

**OpenWakeWord Migration (Porcupine → OWW)**
- [x] Constants — `FRAME_LENGTH == 1280`, `SAMPLE_RATE == 16000`.
- [x] VAD — silence before speech never ends; silence after speech ends at ≥0.88s (11 × 80ms frames).
- [x] record_until_silence — returns int16 array after speech+silence frames.
- [x] OWW unavailable — `_init_model` returning False → `is_enabled=False`, no raise.
- [x] OWW detection — fake model scores ≥0.5 on first frame → callback fires.

---

## Phase 2 — Backend Core (2026-06-03, 12/12 PASS)

**FAISS + Claude + Ollama**
- [x] FAISS — add 2 entries, ranked search (cat-query ranks cat entry top, scores descending), save→load round-trip with metadata.
- [x] FAISS — wired into app: `app.state.vector_store` is a `VectorStore`; `GET /health` 200.
- [x] Claude — mocked stream: tokens yielded, system block has `cache_control: {"type":"ephemeral"}`, model `claude-opus-4-7`, final token `is_final=True`.
- [x] Claude — `anthropic.APIError` path raises `ClaudeAPIError`, still emits closing token.
- [x] Ollama — mocked `ollama.AsyncClient`: tokens yielded from fake stream, final token `is_final=True`.
- [x] Ollama — `ConnectionError` path yields empty stream (no exception), logs `ollama_unavailable` warning.

**Persona + /health**
- [x] Persona — `JARVIS_SYSTEM_PROMPT` non-empty with British-tone markers ("sir" present, "jarvis" present).
- [x] Persona — `build_system_prompt()` returns the base prompt unchanged.
- [x] Persona — `build_system_prompt(context="test context")` includes "test context".
- [x] Persona — `build_system_prompt("   ")` (whitespace-only) returns base unchanged.
- [x] Health — `GET /health` 200 with `{"status":"ok","version":"0.1.0"}`.
- [x] Phase 2 verify — backend starts and serves /health under lifespan; WebSocket endpoint registered at `/ws`.

---

## Phase 1 — Foundation (2026-06-03, 1/1 PASS)

- [x] Python project init verified — `uv run python -c "import fastapi, anthropic, keyring, aiosqlite"` exits 0 on Python 3.12.13. `pyproject.toml`, `uv.lock`, and `.venv/` all present.
