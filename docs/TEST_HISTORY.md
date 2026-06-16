# Jarvis — Test Run History

> Maintained by debugger-agent. Add new test run entries at the top. Each entry includes date, scope, pass/fail counts, and any notable findings.

---

## Current State: 125/127 backend tests passing — 1 NEW Phase 12D failure + 1 pre-existing secret-scan failure · frontend pnpm build clean

- **Tests Passed**: **125 backend** (`pytest backend/` — 36s; 116 pre-existing + 9 of 10 new Phase 12D) + **frontend `pnpm build` clean** (last verified Phase 11C)
- **Tests Failed**: **2** — (1) **NEW** `test_phase12d_verify.py::test_detect_open_loops_multiple` (genuine Phase 12D defect — see Phase 12D entry below); (2) pre-existing `test_no_secrets_committed_in_source_files` (Google OAuth client id committed in `get_gmail_token.py:9` in a prior session — NOT a memory regression, handed to security-agent).
- **Deferred**: 6 Phase 9 items (4 UI + 2 true-E2E) — require native Tauri app and/or a microphone + live API keys. No Vitest harness yet; frontend verified via `pnpm build` + grep.

---

## Phase 12D — Memory Intelligence (2026-06-05, 9/10 targeted PASS — 1 FAIL · suite 125 passed / 2 fail)
*(`backend/memory/test_phase12d_verify.py` — pure-function evaluator checks + temp SQLite + MagicMock VectorStore; no key, no network, no audio, no FAISS)*

**RESULT: FAIL** — 9 of 10 targeted tests pass; targeted test 3 (open-loop multiple) fails on a genuine Phase 12D code defect. Full suite shows no regression in any previously-passing test (the only new failure is this Phase 12D bug; the +10 new tests took the suite from 117 to 127 total).

Verifies the Phase 12D change set: open-loop detection, people extraction, failure memory, `older_than_hours` open-loop filter, `consolidate` side effects, and the lifespan consolidation loop.

- [x] **1. Open loop detection — positive** — `detect_open_loops("remind me to follow up with Maria tomorrow")` returns ≥1 entry containing "follow up with Maria". ✓
- [x] **2. Open loop detection — negative** — `detect_open_loops("what time is it?")` returns `[]`. ✓
- [ ] **3. Open loop detection — multiple** — `detect_open_loops("I need to update the readme and don't forget to check the logs")` expected 2 entries, **got 1** (`['check the logs']`). **FAIL.** ✗
- [x] **4. Person extraction — email present** — `extract_person("got an email from Sarah at sarah@example.com")` returns `name="Sarah"`, `email="sarah@example.com"`. ✓
- [x] **5. Person extraction — no person** — `extract_person("what time is it?")` returns `None`. ✓
- [x] **6. Failure scoring** — `score("we tried using Redis but it conflicted with the audio pipeline", "Understood, reverting.")` → score 0.85, category `"failure"`. ✓
- [x] **7. Failure fact extraction** — `extract_fact(user, reply, "failure")` returns a string containing "failed"/"Failed approach". ✓
- [x] **8. Open loop saved via consolidate** — `MemoryManager(in-memory).consolidate("remind me to call the client tomorrow", ...)` lands an `open_loops` row with status="open" (fire-and-forget, polled ≤2s). ✓
- [x] **9. `get_open_loops` `older_than_hours` filter** — a row created 25h ago is returned by `older_than_hours=24` and excluded by `older_than_hours=26`. ✓
- [x] **10. Consolidation loop in lifespan** — `main._consolidation_loop` is a defined coroutine fn; `main._startup_greeting` signature accepts `memory_manager`. ✓

### FAILURE DETAIL — test 3 (`test_detect_open_loops_multiple`)
- **Test name**: `backend/memory/test_phase12d_verify.py::test_detect_open_loops_multiple`
- **Expected**: `detect_open_loops("I need to update the readme and don't forget to check the logs")` → list of **2** entries (one per trigger: `"i need to"` → "update the readme", `"don't forget to"` → "check the logs").
- **Actual**: returns **1** entry — `['check the logs']`. The "update the readme" loop is dropped.
- **Location**: `backend/memory/evaluator.py:252-271` (`MemoryEvaluator.detect_open_loops`), specifically the `break` at line 271.
- **Root cause**: `detect_open_loops` records **at most one loop per sentence**. It splits text only on `.!?;\n` (`_SENTENCE_SPLIT_RE`, line 171) — *not* on the conjunction "and" — so the whole input is one sentence. Within that sentence it finds the first matching trigger by list order (`"don't forget to"` precedes `"i need to"` in `_OPEN_LOOP_TRIGGERS`, lines 139-157), captures its body ("check the logs"), then `break`s — so the second commitment ("update the readme") is never captured. Confirmed: splitting the same text into two sentences with a period yields both loops (`['update the readme', 'check the logs']`).
- **Suggested fix** (two viable options):
  - *(A, minimal)* In `detect_open_loops`, after consuming a trigger, strip the matched span from the working sentence and re-scan the remainder for further triggers instead of `break`-ing — so a single sentence with N distinct triggers yields N loops. Keep the dedupe `seen` set to collapse identical descriptions.
  - *(B)* Extend `_SENTENCE_SPLIT_RE` (or add a pre-split) to also break on coordinating conjunctions (`\b and \b`, `\b then \b`) before the per-sentence scan. Lower-effort but coarser (would also split non-commitment "and" clauses).
  - Recommend (A): it targets the actual one-loop-per-sentence limitation without changing sentence semantics elsewhere.

**Test-harness notes (not product bugs):**
- *Test 8 polls the DB.* `consolidate` fires the open-loop write via `asyncio.create_task` (`manager.py:236-237`) — fire-and-forget, never awaited — so the test polls `open_loops` for up to 2s rather than asserting synchronously. This confirms the write is genuinely scheduled and lands.
- *Test 9 seeds `created_at` directly* via a raw `INSERT ... datetime('now','-25 hours')` to exercise the `older_than_hours` cutoff deterministically without waiting real time.
- *Test 10 is an import-level check* — no server start, no lifespan run.

---

## Phase 12C — Agent Memory (2026-06-06, 7/7 targeted PASS · suite 116 passed / 1 pre-existing fail)
*(`backend/agents/test_phase12c_verify.py` — mocks only: FakeMemoryManager + StubReasoner + FakeHub + temp SQLite; no key, no network, no audio, no FAISS)*

Verifies the Phase 12C change set: persistent memory wired into all 6 agents. `BaseAgent.reason()` recalls shared memory before the Claude call and stores + consolidates after; `_remember()` checkpoints each exchange to `conversations` under `channel='agent:<id>'`; `start()` restores the agent's context from the DB; `ProductionLead._delegate()` writes a `decisions` row; specialists write `agent_performance` rows on completion.

- [x] **1. Context checkpoint** — `BaseAgent` (no memory_manager) `_remember("hello","world")` persists exactly two `conversations` rows under `channel="agent:test"`: a `user` row "hello" and a `jarvis` row "world". The checkpoint is fire-and-forget (`asyncio.create_task`), so the test polls the DB until both rows land. ✓
- [x] **2. Context restore** — seed 4 conversation rows for `channel="agent:test"`; a fresh agent's `start()` rebuilds `self._context` as 4 entries in Anthropic message shape (`user`→`user`, `jarvis`→`assistant`), oldest-first, matching the seeded rows exactly. ✓
- [x] **3. Context restore empty DB** — a fresh agent on an empty DB: `start()` leaves `self._context == []`, no crash. ✓
- [x] **4. Recall in reason()** — `MemoryManager.recall` returns one episodic message; with pre-seeded rolling context, the messages list passed to Claude is **exactly** `[recalled episodic, rolling context, new prompt]` (recalled first, then `self._context`, then the new user prompt). ✓
- [x] **5. Store after reason()** — `reason("test prompt")` calls `MemoryManager.store` **exactly twice** (roles `["user","jarvis"]`, channel `agent:test`) and `consolidate` is **create_task'd not awaited** (polled after a loop yield; `agent_id="test"` propagated). ✓
- [x] **6. Production lead writes decisions** — `handle_task("Build a new API endpoint")` on a `ProductionLead` with a wired MemoryManager records a `decisions` row with `agent_id="production_lead"` (fire-and-forget, polled). ✓
- [x] **7. Specialist writes agent_performance** — `handle_task("fix a bug")` on `BackendAgent` records an `agent_performance` row with `agent_id="backend"` and `outcome` in (`success`,`failed`) (fire-and-forget, polled). ✓
- [x] **8. Phase 4 regression** — full Phase 4 agent suite (`backend/agents/test_phase4_verify.py`) still 12/12 PASS: lifecycle, status broadcasts, DB persistence across restart, keyword routing, delegation, error recovery, lifespan wiring. No regressions from the memory wiring. ✓

**Test-harness notes (not product bugs):**
- *Tests 1, 5, 6, 7 poll the DB / call records.* The Phase 12C memory writes (`_checkpoint_context`, `consolidate`, `_record_delegation_decision`, `_record_performance`) are all fire-and-forget via `asyncio.create_task` so they never add latency to a task. Tests therefore poll for the side effect rather than asserting synchronously — this confirms the writes are genuinely scheduled (not awaited inline) and still land.
- *Test 6 FK seeding.* Routing "Build a new API endpoint" classifies to `backend`, and `_delegate` writes a `tasks` row with `assigned_to="backend"` (FK into `agents`). The test seeds the `backend` agent row (via `upsert_agent`) in addition to `start()`-ing the lead, so the delegation FK is satisfied. Without it the delegation raised `FOREIGN KEY constraint failed` — an artifact of the minimal single-lead fixture, not a code defect.
- *Tests 6 & 7 require a wired MemoryManager.* The `decisions` / `agent_performance` writes are gated on `self.memory_manager is not None` (so the no-memory test path stays unchanged), hence both tests inject a `FakeMemoryManager`.

**Regression check:** All 109 previously-passing tests still pass. The 7 new Phase 12C tests bring the suite to **116 passed / 1 pre-existing fail (117 total)**. The brief anticipated "109/110" — that was the pre-12C baseline; adding the 7 new tests yields 116/117. The single failure remains the pre-existing secret scan (below), confirmed independent of Phase 12C — it scans `get_gmail_token.py` / `docs/TEST_HISTORY.md`, neither touched by the memory wiring. No Phase 12C regressions.

---

## Phase 12B — Voice Pipeline Memory (2026-06-05, 7/7 targeted PASS · suite 109 passed / 1 pre-existing fail)
*(`backend/voice/test_phase12b_verify.py` — mocks only: FakeMemoryManager + _FakeClaude + FakeDetector + RecordingHub; no key, no network, no audio, no DB/FAISS)*

Verifies the Phase 12B change: `_stream_and_speak` / `process_text` now recall memory **before** the Claude call and store + consolidate **after** TTS completes; an interrupted turn must NOT persist a partial reply; persona `build_system_prompt` accepts the memory manager's pre-formatted multi-section context without a duplicate `# Current context` header.

- [x] **1. Recall before Claude** — `recall` returns one episodic message `{"role":"user","content":"previous message"}`; after `process_text("hello")` the captured `messages` list is **exactly** `[recalled episodic, new user message]` (recalled first, then `{"role":"user","content":"hello"}`, len 2). ✓
- [x] **2. Store after turn** — `process_text("hello")` with mocked Claude+TTS calls `MemoryManager.store` **exactly twice**, roles `["user","jarvis"]`, with the user text and the full assembled reply text. ✓
- [x] **3. Consolidate is fire-and-forget** — `consolidate` stubbed with `asyncio.sleep(10)`; `process_text` returns in **< 1s** (measured ~0s) and the consolidate task is confirmed scheduled (started event set) — proving `asyncio.create_task`, not `await`. ✓
- [x] **4. No-memory fallback** — `memory_manager=None`: `process_text("hello")` completes normally, Claude called with a **single-message** list `[{"role":"user","content":"hello"}]` (no recalled context), reply spoken, ends `idle`, no AttributeError/NoneType errors. ✓
- [x] **5. Persona — no duplicate header** — `build_system_prompt(context="# Current context\n...")` contains **exactly one** `# Current context` heading and includes the injected fact. ✓
- [x] **6. Persona — backward compat** — `build_system_prompt(context="some plain text")` wraps the fragment under **exactly one** `# Current context` heading and includes "some plain text". ✓
- [x] **7. Interrupted turn does not store** — real interrupt path (slow responder + interrupt listener hears "stop", cancels mid-stream): turn ends `idle`, `recall` ran (user message reached Claude) but `store` and `consolidate` were **never called** — no partial reply persisted. ✓

**Test-harness note (test 4, not a product bug):** `process_text`'s `finally` only transitions back to `idle` when `self._running` is true (set by `start()`). The no-memory test calls `pipeline.start()` before `process_text` so the pipeline unwinds to `idle`, mirroring how the live `/api/chat` caller drives it. Initial draft omitted `start()` and observed the turn parked in `speaking`; corrected to start the pipeline. No code change — this is the pipeline's existing, correct contract.

**Regression check:** All 102 previously-passing tests still pass. The 7 new Phase 12B tests bring the suite to 109 passed. The only failure remains the pre-existing secret scan (below) — confirmed independent of this work (it scans `get_gmail_token.py` / `docs/TEST_HISTORY.md`, neither touched by Phase 12B). No Phase 12B regressions.

> Note on counts: the brief anticipated "102/103" but the live baseline was already 102 passing from Phase 12A; adding 7 new Phase 12B tests yields **109 passed / 1 pre-existing fail (110 total)**. The contract held — exactly one failure, the same known secret-scan one, no new failures.

---

## Phase 12A — Memory Infrastructure (2026-06-05, 7/7 targeted PASS · suite 102 passed / 1 pre-existing fail)
*(`backend/test_phase12a_verify.py` — in-memory/temp-file: no key, no network, no audio; VectorStore mocked so the embedding model never loads)*

- [x] **Schema** — `init_db()` on a temp db creates all 5 new Phase 12 tables: `memory_facts`, `people`, `open_loops`, `decisions`, `agent_performance` (DB now reports 10 tables total).
- [x] **Evaluator import + preference** — `MemoryEvaluator().score("my name is Gabriel", "Nice to meet you Gabriel")` → **0.75, "preference"** (≥0.75, category contains "preference"). ✓
- [x] **Evaluator app_work** — `score("we deployed the new backend endpoint", "Done, the endpoint is live at /api/v2/chat")` → **0.90, "app_work"** (≥0.9). Matched verb "deployed" + artifact "endpoint"/"/api/v2/chat". ✓
- [x] **Evaluator general/low** — `score("what time is it?", "It's 3pm")` → **0.20, "general"** (≤0.3, below the 0.65 promotion threshold). ✓
- [x] **MemoryManager instantiation** — constructs with a mocked VectorStore + temp db_path; default `MemoryEvaluator` created when none injected. No error. ✓
- [x] **RecallResult on empty DB** — `recall("anything")` returns a `RecallResult` with `episodic_messages == []` and `semantic_facts == []`. **DEVIATION FROM BRIEF (see below):** `formatted_context == ""` on a cold/empty recall, NOT the date header. Verified separately that `format_context()` DOES emit `# Current context` + `Date:` once there is real content to inject. ✓
- [x] **save_memory_fact** — `save_memory_fact(source='voice', category='preference', content='User prefers short answers', importance=0.75, agent_id=None)` → returns **int id > 0**; round-trips back via `get_memory_facts` with content/category/importance intact. ✓

**Targeted-test deviation (test 6, intentional — not a bug):** The brief expected `formatted_context` to be a non-empty string ("at minimum the date header") on an empty DB. The actual behavior of `MemoryManager.format_context` is to return `""` when only the date header would be present — a deliberate prompt-caching optimization so the stable cached prefix of the system prompt stays byte-identical on a cold first turn (documented in `manager.py` docstring + the `if len(sections) == 1: return ""` guard at the end of `format_context`). The test was written to assert this real, intended contract (empty context on cold recall) AND to confirm the date header appears as soon as any fact/turn is present. No code change made — this is correct behavior.

**Regression check:** All 95 previously-passing tests (Phases 2–11C) still pass. The 7 new Phase 12A tests bring the suite to 102 passed. The only failure is the pre-existing secret scan (below). No Phase 12A regressions.

**Pre-existing secret in `get_gmail_token.py` (investigated, NOT Phase 12A):** Line 9 hardcoded a path containing a real Google OAuth **client id** — `<REDACTED_OAUTH_CLIENT_ID>` — as part of the `client_secret_*.json` filename passed to `from_client_secrets_file(...)`. *(Scrubbed 2026-06-16: the script now reads the client_secret path from argv/env, and this doc reference is redacted.)* The secret scanner's `google_oauth` pattern matches it. Findings for security-agent:
  - It is the OAuth **client id only** — a public OAuth identifier (it appears in OAuth consent URLs by design), NOT the client *secret* and NOT the refresh token. Lower severity than a leaked secret, but the scanner correctly flags it and it should not be committed.
  - It is a literal string inside a Windows path to a `client_secret_*.json` file on the user's Desktop (`C:\Users\User\Desktop\Jarvis\...`); the actual secret JSON file is NOT in the repo.
  - `get_gmail_token.py` is a one-shot manual helper script (run once to mint a refresh token), not imported by the app. Suggested fixes: parameterize the path via `sys.argv`/env var, or move the script out of the repo / add it to `.gitignore`. Then scrub it from git history if the client id is considered sensitive.

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
