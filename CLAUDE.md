# HELIX — Master Control Document

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

- **Phase 15A verified ✓ 2026-06-06**: Neural Intelligence Orb rewrite complete. All 7 layers present, cascade activation, red freedom pathways. `pnpm build` clean. Backend suite 143/144.
- **Active Phase**: Phases 1–15 complete and archived. Full project audit (HEALTH.md, 2026-06-16) identified 3 live issues: WebSocket contract drift (3 windows broken), secret-scan spreading to 2 files, memory recall unreliable. Phases 15B → 16 → 17 address these in order.
- **HEALTH.md audit findings (2026-06-16)**:
  - Secret-scan failure is now **2 files**: `get_gmail_token.py:9` + `docs/TEST_HISTORY.md:110` — not 1 as previously recorded
  - **Phase 7 known gap**: Frontend handles 9 WS event types; backend only emits 6. `comms`, `tool_permissions`, `tool_call` never broadcast → Communications (Win3), Tools (Win5), and Reasoning tool cards (Win2) render skeletons
  - Memory system is **~60% to goal** — infrastructure solid, recall reliability weak (similarity-only, `last_recalled_at` dead column, rule-based extraction, no contradiction handling)
- **Tier 0 COMPLETE (2026-06-16)** ✅: Item 1 (Jarvis → Helix rename, verified 5/5), Items 2–3 (OAuth client ID scrub), Item 4 (WAL-safe SQLite backup) all done. **Suite now 145/145 green.**
- **Phase 15B COMPLETE (2026-06-16)** ✅: All 3 missing WS events (`tool_call`, `comms`, `tool_permissions`) wired + `shutdown` verified; Reasoning/Communications/Tools windows now receive live data. Verified 6/6 by debugger-agent. Note: 3 of the 4 event classes didn't actually exist and were added.
- **Phase 16A COMPLETE (2026-06-16)** ✅: Recall→prompt injection boundary sanitized (`<untrusted_memory>` + control-char strip), `last_recalled_at` activated on the real recall hot path, 4 memory-quality columns added via idempotent migration. Verified 5/5 by debugger-agent. Suite 161/161.
- **Phase 16B COMPLETE (2026-06-16)** ✅: Similarity-only recall replaced with weighted composite score (0.40 semantic + 0.20 keyword/FTS5 + 0.20 recency + 0.10 importance + 0.10 frequency); `access_count` increment wired into the recall stamp. Verified 6/6 by debugger-agent. Suite 170/170.
- **Phase 16C COMPLETE (2026-06-16)** ✅: Keyword extraction replaced with LLM extraction (Haiku 4.5 primary + phi3.5 fallback, async, rule pre-filter gate) classifying facts ADD/UPDATE/DELETE/NOOP; FAISS-0.85 UPDATE dedup; `created_by`/`confidence` set; minimal `valid_to` soft-delete. Verified 8/8 by debugger-agent. Suite 183/183.
- **Phase 16D COMPLETE (2026-06-16)** ✅: Full bi-temporal columns; TOKI contradiction operators (last-write-wins/evidence-weighted/merge/await-confirmation) dispatched on stored `write_policy`; nightly Ebbinghaus decay (once/day guard, archive at strength<0.1); FAISS tombstoning on all 3 stale-vector paths (+fixed latent 16C dedup bug). Verified 8/8 by debugger-agent. Suite 196/196. **16A–16D now complete — memory intelligence core done.**
- **HUB REDESIGN COMPLETE (2026-06-16)** ✅: Frontend retheme from cyan-led HUD → **champagne-gold / near-black / white + aqua live accent** (Ultraplan cloud patch + 3 refinements). Palette `bg #08080a` / gold `#ffc247` / highlight `#ffe9a8` / white ink / aqua accent `#3fe3d0`. CSS tokens cleanly renamed `jarvis-*` → `helix-*`. New **7th window: `CommandBarWindow`** (bottom-center, always-on-top) — verbs PLAN/EXECUTE/MONITOR/LEARN/ADAPT focus windows (LEARN disabled until 16F). Orb recolored (gold neurons, **aqua freedom pathways**) + THINK·PLAN·ACT·ELEVATE tagline + HELIX label (fixed stale "JARVIS"). True red `#FF5A5A` reserved for failures only (error/offline/shutdown). Verified 8/8 by debugger-agent: `pnpm build` clean, zero leftover `jarvis-`/cyan, backend untouched 196/196. *(Visual confirmation pending user — needs `pnpm tauri dev`.)* Design north-star: memory `helix-hub-design-direction`; `References/` mockup+patch stay gitignored.
- **Next Task**: **Phase 16F** — Memory Graph Visualization / Window 6 (`/backend-agent` API + `/frontend-agent` graph UI). Build `GET /api/memory/graph`, the `MemoryWindow.tsx` force-directed graph (inherits the new gold design system + a `command`-bar LEARN target already wired), hover HUD panel, Tauri window registration, and `memory_update` WS event. (16E ColBERT/self-reflection is optional — schedule when ready.)
- **Blockers**: Dedicated microphone not yet purchased — voice E2E tests deferred to Pending.
- **Test State**: **196/196 passing** (secret-scan green; +13 Phase 16D bi-temporal tests, 2026-06-16) · `pnpm build` clean.
- **Build Started**: 2026-06-02

---

## Project Overview

**Helix** is a personal AI assistant that runs locally on Windows 11. It wakes on voice command, understands natural speech, responds in a subtle British tone (Tom Hardy meets Helix from the Avengers), and manages a team of 6 background AI agents.

### Hardware
- GPU: NVIDIA RTX 3050 Ti Laptop — 4GB VRAM
- CPU: Intel i7-1180H @ 2.30GHz
- RAM: 16GB
- OS: Windows 11

### AI Stack
- **Primary AI**: Claude API — `claude-opus-4-7` (Anthropic SDK, streaming + prompt caching)
- **Local Fallback**: Ollama — `phi3.5` (3.8B, ~2.4GB VRAM) and `qwen2.5-coder:3b`
- **Wake Word**: OpenWakeWord (model: "hey_jarvis", Apache 2.0, fully local, no API key) — ⚠️ pre-trained on "hey_jarvis"; responds to "hey_helix" only after custom model is trained (see Pending)
- **Speech-to-Text**: faster-whisper (base.en model)
- **Text-to-Speech**: ElevenLabs API (custom Paul Bettany × Anthony Hopkins × HELIX voice — calm British butler with faint digital resonance)

### Tech Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, WebSockets, Uvicorn |
| Frontend | Tauri 2 + React 19 + TypeScript 5 + Vite 6 |
| Styling | Tailwind CSS 4, Angular HUD dark theme (`#080810`, `.hud-btn`, `.data-stream-top`, `.hud-corners`) |
| 3D Animation | Three.js / React Three Fiber |
| State | Zustand 5, WebSocket sync |
| Database | SQLite (aiosqlite) |
| Vector Memory | FAISS + sentence-transformers (`all-MiniLM-L6-v2`) |
| Key Storage | Windows Credential Manager (keyring library) |
| Integrations | Slack Bolt, Gmail API (OAuth2) |
| Logging | structlog |
| Testing | pytest + pytest-asyncio, Vitest |

### 6 Windows (open simultaneously on boot)
| # | Name | Contents |
|---|---|---|
| 1 | Animation | Neural intelligence orb — 350 neuron nodes, glowing pathways, red freedom pathways (~20%), 30 floating math/code symbols; cascade activation; audioLevel pulse during speaking; SVG connection beams to other windows; ⏻ shutdown button |
| 2 | Reasoning | Model name, streaming tokens, tool call cards, cost/latency; **text input** for typing questions when mic unavailable |
| 3 | Communications | Slack inbox + Gmail inbox — read/reply via voice |
| 4 | Agents | 6 agent cards (Atlas/Ben/Kado/Sentinel/Vega/Quill) with live status, current task, rename controls, task input + task log per card, Mission Control panel |
| 5 | Tools | Tool store grid — per-agent access toggles |
| 6 | Memory | Force-directed graph of all memory facts — nodes colored by type (cyan/gold/red/purple/green), sized by recall frequency, edges = semantic similarity. Click to inspect, search to filter. Live updates via WebSocket. *(Phase 16F)* |

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
**Champagne-gold / near-black / white HUD** (hub redesign 2026-06-16 — replaced the prior cyan theme). Tokens are `--color-helix-*` in `frontend/src/index.css`: bg `#08080a`, primary gold `#ffc247`, gold highlight `#ffe9a8`, white ink `#ffffff`, muted `#9a9488`, **cool aqua accent `#3fe3d0`/`#8ffaec`** (live states: online/listening/speaking/working), alert **red `#FF5A5A`** (failures only: error/offline/shutdown). Iron Man HUD — angular, futuristic, high-contrast, sharp edges, glowing outlines, no rounded corners. *(NOTE: do NOT reintroduce cyan `#00d4ff` or `jarvis-*` tokens — the rename is complete. New frontend work uses `helix-*` tokens + `.text-glow-gold`/`.text-glow-accent`.)*

- **Grid**: fine dual-scale grid (80px major / 20px minor) at low opacity, warm-gold lines
- **Panels** (`.glass`): warm-obsidian `rgba(16,14,10,0.45)` background, `backdrop-filter: blur(40px)`, `1px solid rgba(255,194,71,0.45)` gold border
- **WindowFrame**: angular header with `|`-style gold accent ticks, flowing `data-stream-top` (gold→aqua peak) animated border, pulsing status badge (ONLINE→aqua / LINKING→gold / OFFLINE→red), corner accent marks
- **Buttons** (`.hud-btn`): gold at rest (`rgba(255,194,71,0.06)` bg + gold border), **aqua glow on hover**; `.hud-btn:disabled` muted
- **Window layout**: orb (AnimationWindow) centred at `x:780, y:300`; Reasoning left `x:200`; Communications upper-right `x:1180`; Agents bottom `x:200, y:760`; Tools lower-right `x:1180, y:540`; **CommandBar bottom-centre `x:680, y:980`** (always-on-top)
- **Orb**: Neural intelligence sphere — 350 neuron `Points`, ~480 normal `LineSegments` (gold) + ~120 **aqua "freedom" `LineSegments`** (~20%, `#1f6e66`→`#8ffaec` — recolored from red; *note legacy constant names `COL_RED_*` now hold aqua values*), 30 drifting symbol `Sprite`s, glow spheres + wireframe hologram shell, cascade activation (CASCADE_DEPTH=6, NEIGHBOR_K=4). SVG beams radiate from orb centre (gold lines, aqua travelling dots). Top tagline **THINK·PLAN·ACT·ELEVATE** + **HELIX·CORE INTELLIGENCE** label.
- **Voice Helix**: Paul Bettany × Anthony Hopkins character — calm British butler with faint digital resonance. "The kind of voice that could read you a bedtime story or a threat."

---

## Security Rules (enforced throughout ALL phases)

1. **Zero secrets in files** — All API keys stored in Windows Credential Manager via `keyring`. No `.env` files with real values. `.env.example` template only.
2. **Local network only** — FastAPI binds to `127.0.0.1:8000`, never `0.0.0.0`.
3. **Voice input sanitized** — Strip control chars, cap at 2000 chars before sending to Claude.
4. **Sandboxed code execution** — No `os`, `sys`, `subprocess` access. Workspace-only filesystem.
5. **Minimal OAuth scopes** — Gmail and Slack use least-privilege scopes.
6. **Audit log in SQLite** — Every agent action logged (metadata only, no message content).

---

## Tier 0 — Hygiene (do before Phase 15B)
*Handled by: `/security-agent` (items 1–2) + `/backend-agent` (items 3–4) + `/frontend-agent` (item 5). Hours of work. Unblock 144/144 clean suite.*

- [x] **Rename assistant from Jarvis → Helix across entire codebase** — Helix must know his own name. *(Done 2026-06-16: backend 33 files / 94 replacements via `backend-agent`; frontend file `JarvisOrb.tsx`→`HelixOrb.tsx` + windows/config via `frontend-agent`; verified 5/5 by `debugger-agent` — backend 143/1, `pnpm build` clean, WS token path unaffected, wake-word string preserved. NOTE: persona file is at `backend/ai/persona.py`, not `backend/agents/persona.py` as listed below. Intentionally left for later: DB role enum `'jarvis'`, `SERVICE_NAME="jarvis"` keyring, `JARVIS_*` env vars, `jarvis.db`/`jarvis_*.zip` filenames, `jarvis-*` Tailwind tokens, and bundle id `com.jarvis.hud` — none user-facing / would break suite or app identity.)*
  - `backend/agents/persona.py` — update system prompt: name, personality intro, self-references ("I am Helix", not "I am Jarvis")
  - `frontend/src/components/JarvisOrb.tsx` → rename file to `HelixOrb.tsx`; update all imports
  - `frontend/src/windows/` — update any window titles, display text, or comments referencing "Jarvis"
  - `tauri.conf.json` — update app title and any window labels
  - `package.json` / `Cargo.toml` — update project name fields
  - Do NOT change `"hey_jarvis"` wake word string — that is the OpenWakeWord model filename and will break detection if changed. Add a code comment: `# wake phrase is "hey_jarvis" until custom "hey_helix" model is trained`
  - After rename: `pnpm build` clean, backend suite still passes.
- [x] **Scrub OAuth client ID** from `get_gmail_token.py:9` — *(Done 2026-06-16: rewritten to take the client-secret JSON path via `sys.argv[1]` or `GMAIL_CLIENT_SECRET_FILE` env var; literal ID removed from code & comments; still runnable as bootstrap.)*
- [x] **Scrub OAuth client ID** from `docs/TEST_HISTORY.md:110` — *(Done 2026-06-16: redacted to `<REDACTED_OAUTH_CLIENT_ID>`. Repo-wide grep confirmed only these 2 files contained the ID — the `.claude/agent-memory/` snapshot did NOT. Secret-scan now passes → **144/144 green**. Residual: ID still in git history; optional `git filter-repo` follow-up if deemed sensitive, but it's a public client id, not a secret.)*
- [x] **Fix SQLite backup** in `main.py:233` — *(Done 2026-06-16: new `_online_backup_db()` helper uses `sqlite3.Connection.backup()` for a consistent online snapshot — folds in committed WAL pages, safe under concurrent writers. Self-contained snapshot, so `-wal`/`-shm` sidecars intentionally NOT shipped. FAISS files still copied as before; `jarvis_<date>.zip` naming + `jarvis.db` arcname preserved; temp snapshot cleaned up in finally. Added regression test `test_backup_is_wal_safe` → suite now **145/145 green**.)*

---

## Phase 15B — WebSocket Event Wiring
*Handled by: `/backend-agent` (Kado). Must complete before Phase 16 — a broken UI demo undermines the memory work.*

### Known gap (HEALTH.md verified)
Frontend (`websocket.ts`) handles 9 event types. Backend (`events.py` + `main.py`) only broadcasts 6. Three windows are rendering skeletons:
- **Window 2 (Reasoning)** — `tool_call` defined in `events.py` but `registry.py:259` only audit-logs it, never broadcasts → tool cards stay empty
- **Window 3 (Communications)** — `comms` event never broadcast → Slack/Gmail inbox renders skeleton
- **Window 5 (Tools)** — `tool_permissions` event never broadcast → permission toggles render skeleton

### What to build (Phase 15B) — ✅ COMPLETE & verified 6/6 (2026-06-16)
> **Correction to the gap analysis above**: only `tool_call` actually had an event class in `events.py`. `comms`, `tool_permissions`, AND `shutdown` had NO event classes (the `EventType` literal listed only 6) — backend-agent added `CommsEvent`, `ToolPermissionsEvent`, `ShutdownEvent` with frontend-matching shapes. Hub is accessed per the existing emit pattern (async sites `await hub.broadcast`; sync sites fire-and-forget via `loop.create_task`, no-op when no loop/hub).
- [x] **Broadcast `tool_call` from registry** — emitted at `registry.py:383` after successful `call_tool()`. Secret scrubbing via `_scrub_args` (redacts token/secret/password/api_key/etc. → `***redacted***`) + `_preview_result` (≤200 chars). Shape matches frontend `ToolCallEvent`. Reasoning window tool cards populate.
- [x] **Broadcast `comms` event** — emitted after Slack fetches (`slack_client.py:188,245`) and Gmail fetch (`gmail_client.py:154`). `CommsEvent` carries `slack` OR `gmail` independently; item shapes match frontend `SlackMessage`/`GmailMessage`. (Added `Date` header to Gmail metadata for real timestamps — non-breaking, Phase 5 test asserts subset.)
- [x] **Broadcast `tool_permissions` event** — on startup (`main.py:449`), on grant/revoke (`registry.py:283`), AND pushed per-window on connect (`main.py:807`) to beat connect-order races. Shape matches frontend.
- [x] **Wire `shutdown` broadcast** — verified already working (⏻ → `POST /api/shutdown` → `hub.broadcast` → all windows); swapped raw dict for typed `ShutdownEvent()` (identical wire shape).
- [x] Verified (debugger-agent 2026-06-16): all 3 events match frontend field-for-field incl. `type` string; secrets scrubbed (code + tests); emit-safe (failures swallowed, no-loop safe); shutdown reaches all windows; `pnpm build` clean; **backend suite 154/154** (+8 new Phase 15B tests).
- **Out-of-scope observation (future)**: Slack live-listener inbound callback (`main.py` `_on_slack_message`) still broadcasts a raw payload with no `type` field (frontend ignores it). It's a push, not a fetch, so outside 15B scope — could emit a `CommsEvent` later.

---

## Phase 16 — Memory Intelligence
*Handled by: `/backend-agent` (Kado). Enhance — do not replace — the existing SQLite + FAISS memory system. Research basis: Mem0 (49% LongMemEval), Zep/Graphiti (63.8% LongMemEval), TOKI bi-temporal operators, Ebbinghaus forgetting curves, ColBERT re-ranking. Target: ~85% of Zep quality, fully local, zero new cloud dependencies.*

### Memory system current state (HEALTH.md verified)
- **What works**: 3-layer brain (episodic SQLite + distilled `memory_facts` + FAISS semantic), wired into voice hot path, 7 memory tables, FTS5 keyword search, consolidation loop, daily backup, open loops, people profiles.
- **What's broken**: recall is similarity-only (`MIN_SEMANTIC_SCORE=0.25`, no recency/importance/frequency); `last_recalled_at` column exists but is never written; extraction is keyword rule-matching (misses paraphrases); facts accumulate forever (no contradiction resolution, no eviction); recalled memories injected into system prompt without sanitization (latent injection vector).

### Phase 16A — Foundation + Safety — ✅ COMPLETE & verified 5/5 (2026-06-16)
*Close the security gap and activate the dead recall infrastructure before adding more memory writers.*
> **Path correction**: sanitization lives in `backend/memory/manager.py::format_context()` (where fact content becomes prompt text — the true trust boundary), NOT `persona.py`. `build_system_prompt()` (actual path `backend/ai/persona.py`, not `backend/agents/persona.py`) consumes the already-sanitized block. Grep confirmed NO bypass path injects raw facts.
- [x] **Sanitize recall→prompt injection boundary** — `format_context()` (`manager.py:535`) wraps recalled facts in `<untrusted_memory>`…`</untrusted_memory>` with a "treat as data" preamble; `_sanitize_fact_text()` (`manager.py:71`) strips C0/C1/DEL via `_CONTROL_CHARS_RE = [\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]` while preserving tab/newline/CR + Unicode. On-path for both voice (`pipeline.py:492`) and agents (`base_agent.py:376`).
- [x] **Activate `last_recalled_at`** — `mark_facts_recalled()` (`database.py:779`) does `UPDATE … SET last_recalled_at = datetime('now') WHERE id = ?` via executemany; called from `recall()` (`manager.py:487`) for facts it returns. On the real hot path; wrapped in its own try/except so a stamp failure never drops recalled facts.
- [x] **Add memory quality columns to `memory_facts`** — `_migrate_memory_facts_quality_columns()` (`database.py:331`) adds `confidence FLOAT DEFAULT 0.8`, `created_by TEXT DEFAULT 'system'`, `source_turn_id INTEGER`, `access_count INTEGER DEFAULT 0`. Idempotent (PRAGMA check-before-ALTER; SQLite auto-backfills defaults). `access_count` increment correctly DEFERRED to 16B (column only).
- [x] Verified (debugger-agent 2026-06-16): control chars stripped + `<untrusted_memory>` wrapper present (no bypass path); `last_recalled_at` NULL→now on recall; 4 new columns w/ defaults; idempotent across 3× `init_db`; cheap PK-update, no hot-path regression. **Suite 161/161** (+7 tests in `test_phase16a_verify.py`).

### Phase 16B — Multi-Signal Re-Ranking — ✅ COMPLETE & verified 6/6 (2026-06-16)
*Replace similarity-only FAISS recall with a weighted scoring pipeline.*
> Inserted in `recall()` Layer 3 (`manager.py:598-706`). FAISS pool `max(n_semantic, CANDIDATE_POOL_K=20)`; `MIN_SEMANTIC_SCORE=0.25` kept as pre-filter; `_rank_candidates()[:n_semantic]` selects final. FAISS confirmed `IndexFlatIP` over L2-normalized vectors = cosine similarity [0,1], higher=better (not inverted). Bounded DB cost: 2 extra queries/recall (batched `get_memory_facts_by_ids` + one FTS pass), no per-candidate loop.
- [x] **Implement multi-signal retrieval** — composite score with tunable constants `W_SEMANTIC=0.40 / W_KEYWORD=0.20 / W_RECENCY=0.20 / W_IMPORTANCE=0.10 / W_FREQUENCY=0.10` (sum 1.0). Keyword = FTS5 position-rank `(n-pos)/n`; recency = `1/(1+days)` with NULL fallback `last_recalled_at`→`created_at`→3650d; frequency = `log(access_count+1)` normalized by pool max (div-by-zero guarded); importance = existing column. Deterministic order: composite desc, tie-break semantic desc then `fact_id` asc.
- [x] **Increment `access_count`** — `mark_facts_recalled()` (`database.py:779`) now does a single combined UPDATE: `last_recalled_at = datetime('now')` AND `access_count = COALESCE(access_count,0)+1`, PK-keyed, wrapped, stamps only the returned top-N.
- [x] Verify (debugger-agent): recently accessed facts rank above equally-similar older facts; importance-weighted facts surface correctly; `pytest backend/` passes. **Verified 2026-06-16 — 170/170 passing (161 + 9 new). All 6 checks PASS.**

### Phase 16C — LLM-Driven Extraction — ✅ COMPLETE & verified 8/8 (2026-06-16)
*Replace keyword rule-matching in `evaluator.py` with an LLM-driven fact extraction pipeline (Mem0 pattern).*
> **Model strategy (user-decided)**: Claude **Haiku 4.5** (`claude-haiku-4-5`, per-call override — client default stays `claude-opus-4-7`) as primary extractor, local Ollama **phi3.5** as fallback, run **async off the voice hot path**, gated behind the existing rule pre-filter. New `backend/memory/extractor.py` (`LLMExtractor`). Haiku chosen over Opus: cheap + reliable structured JSON, no Opus needed for extraction. See memory `phase16c-extraction-model`.
- [x] **Replace `_RULES` keyword matching** — `LLMExtractor.extract()` prompts Haiku→(raise/unparseable)→phi3.5→(fail)→`[]`, never raises. Defensive JSON parse (`_extract_json_array` strips fences/prose, carves outermost `[...]`). Runs inside `MemoryManager.consolidate()`, fire-and-forget `asyncio.create_task` from `pipeline.py:531` + `base_agent.py:418` (off hot path). Rule `score()` < 0.65 returns before the LLM call (pre-filter gate). New non-streaming `ClaudeClient.complete()` + `OllamaClient.complete(fmt="json")`.
- [x] **Wire ADD/UPDATE/DELETE/NOOP** — `_apply_extractions()`: ADD inserts; UPDATE finds most-similar fact via FAISS, overwrites in place if ≥0.85 else falls through to ADD (no dup); DELETE soft-deletes via new `valid_to` column (recall excludes); NOOP skips. Empty `[]` (both LLMs down) falls back to Phase 12A rule distillation so a write is never lost.
- [x] **Set `created_by`** — 'user' for direct statements, 'inference' for LLM-derived; `confidence` persisted from LLM output.
- [x] Verified (debugger-agent 2026-06-16): paraphrase→1 fact (UPDATE dedup); contradiction→UPDATE not 2nd INSERT; NOOP no-write; pre-filter skips LLM; phi3.5 fallback exercised; provenance correct; opt-in (pre-16C tests unchanged, no LLM); `valid_to` migration idempotent; FTS trigger syncs after UPDATE. **Suite 183/183** (+13 mocked tests, no network).
- **Deferred to 16D (TODOs in code)**: FAISS not tombstoned on UPDATE/DELETE (stale vector lingers beside revised text — ranking tolerates it); full bi-temporal columns (`valid_from`/`strength`/`half_life_days`/`superseded_by_fact_id`/`write_policy`/`conflicting_fact_ids`) — 16C ships only the minimal `valid_to` marker, migration is forward-compatible.

### Phase 16D — Bi-Temporal Facts + Ebbinghaus + TOKI Operators — ✅ COMPLETE & verified 8/8 (2026-06-16)
*Contradiction resolution, temporal validity, and natural forgetting.*
> Note: 16D changed 16C's UPDATE from in-place overwrite (1 row) to archive-old + insert-new (2 rows, 1 active) — the bi-temporal model requires it. Two 16C tests updated to assert on *active* facts (still catch duplicate-fact regressions). Also fixed a latent 16C bug: `_find_similar_fact_id` searches FAISS directly (bypassing the `valid_to` row filter), so without tombstoning it could return a superseded vector as a dedup target — now tombstoned.
- [x] **Add bi-temporal columns to `memory_facts`** — added `valid_from`, `strength FLOAT DEFAULT 1.0`, `half_life_days INTEGER DEFAULT 14`, `superseded_by_fact_id`, `write_policy TEXT DEFAULT 'last-write-wins'`, `conflicting_fact_ids` (JSON-as-TEXT) via the idempotent check-before-ALTER helper (`valid_to` reused from 16C). SQLite forbids a non-constant DEFAULT on ADD COLUMN, so `valid_from` is backfilled (`= created_at`) + populated on insert by an `AFTER INSERT` trigger that touches only `valid_from` (doesn't fire the FTS sync trigger).
- [x] **Implement TOKI contradiction operators** — `_resolve_conflict()` (`manager.py:701`) dispatches on the matched (old) fact's stored `write_policy`. Policy chosen by `_choose_write_policy()` (keyword hints → category map → default): `last-write-wins` (default; locations/status) supersedes via `_supersede_fact` (old `valid_to=now` + `superseded_by_fact_id`, insert new, tombstone old vector); `evidence-weighted` (preferences/allergies) higher `confidence` wins, else NOOP; `merge` (employment/relationships) non-overlapping `[valid_from,valid_to)` windows; `await-confirmation` both stay active, cross-linked via `conflicting_fact_ids`.
- [x] **Nightly Ebbinghaus decay job** — `run_decay()` (`manager.py:960`) hooked into `_consolidation_loop` AFTER consolidation, **guarded once-per-calendar-day** (loop ticks every 10min). `strength *= exp(-days_since/half_life_days)`, days fallback `last_recalled_at`→`valid_from`→`created_at`→0. Facts crossing `strength < 0.1` get `valid_to=now` (archived, not deleted) + vector tombstoned. Batched, wrapped so failure can't crash the loop.
- [x] **FAISS tombstoning** (16C deferred TODO) — `VectorStore.tombstone_fact_id()` + `_tombstoned` set that `search()` skips (over-fetches to still return top_k live hits), persisted in `.meta.json`. Applied to all 3 stale-vector paths: supersede/UPDATE, DELETE, decay-archive.
- [x] Verified (debugger-agent 2026-06-16): supersede sets old `valid_to`+`superseded_by_fact_id`; evidence-weighted/merge/await-confirmation branches each tested; strength decays on schedule + below-floor archives; superseded/decayed/tombstoned facts excluded from recall; migration idempotent; the 2 modified 16C tests confirmed legitimate (assert active facts, still catch dup regressions). **Suite 196/196** (+13 tests).
> **Minor (non-blocker)**: `test_merge_produces_non_overlapping_windows` asserts `old.valid_to == new.valid_from` at SQLite second-resolution — theoretical flake if the two writes straddle a second boundary.

### Phase 16E — Optional: ColBERT Re-Ranking + Self-Reflection *(schedule when ready)*
- [ ] **ColBERT cross-encoder re-ranking** — after multi-signal scoring returns top-20, re-rank with `cross-encoder/ms-marco-MiniLM-L-6-v2` (~100MB, runs on CPU). Conditional: enable for high-importance queries (Slack/Gmail bodies), skip for speed on casual queries. Adds ~100ms, significant precision lift.
- [ ] **Self-reflective nightly routine** — add to consolidation loop: sample 50 random active facts; prompt Ollama `phi3.5` to evaluate consistency ("Are these still accurate? Any contradictions?"); emit ADD/UPDATE/DELETE corrections. Runs locally, zero API cost.

### Phase 16F — Memory Graph Visualization (Window 6)
*Handled by: `/backend-agent` (API endpoint) + `/frontend-agent` (graph UI). Depends on 16A + 16B being complete — needs quality columns (access_count, importance, confidence) for node sizing/coloring, and multi-signal scores for edge weights. Visual design: force-directed web, color by type.*

**Design spec (confirmed by user):**
- **Layout**: Force-directed web — nodes float and cluster naturally by semantic similarity (like Obsidian graph view). Physics-based, slow organic drift.
- **Nodes**: Small glowing orbs. Size = `access_count` (frequently recalled = bigger). Glow pulses if recalled in current session.
  - Cyan = general facts
  - Gold = high-importance facts (`importance > 0.7`)
  - Red = contradictions / conflicting facts (`conflicting_fact_ids` non-null)
  - Purple = people profiles (from `people` table)
  - Green = open loops (from `open_loops` table)
- **Edges**: Thin glowing `LineSegments`-style lines between facts with FAISS similarity > 0.5. Brightness = similarity strength.
- **Interaction**: Click node → highlights all connections, dims rest. Hover → HUD tooltip with full fact text + metadata. Search bar filters graph live.
- **Window**: 6th Tauri window — "Memory" — positioned at `x:780, y:760` (below orb, completing the layout).

**What to build:**
- [ ] **Backend `GET /api/memory/graph`** — returns `{nodes: [{id, text_preview, text_full, type, importance, access_count, confidence, created_at, last_recalled_at, conflicting_fact_ids, subject}], edges: [{source_id, target_id, similarity}]}`. Query top-500 active facts from `memory_facts`; compute pairwise FAISS similarity for pairs above 0.5 threshold. Cap at 2000 edges for performance.
- [ ] **New `frontend/src/windows/MemoryWindow.tsx`** — 6th Tauri window. Uses `react-force-graph-2d` (lightweight 2D canvas renderer, ~150KB). HUD-styled: `#080810` background, cyan/gold/red/purple/green node palette, glowing edges. Search input filters nodes live. Click-to-highlight interaction.
- [ ] **Node hover HUD panel** — on hover, render a floating HUD card anchored to the node with a thin cyan connecting line. Panel contains:
  - Full fact text (not truncated)
  - Type badge (color-matched: GENERAL / HIGH IMPORTANCE / CONTRADICTION / PERSON / OPEN LOOP)
  - Confidence: e.g. `0.87`
  - Created: absolute date
  - Last recalled: date + relative ("3 days ago") — greyed out if never recalled
  - Access count: "recalled 12 times"
  - **Connected to**: list of up to 5 most similar nodes, each showing: truncated fact preview + similarity as percentage (e.g. "87% match"). Clicking a listed node jumps focus to it in the graph.
  - Panel positions itself to avoid clipping the window edge (auto-flips left/right/up depending on node position).
- [ ] **Register MemoryWindow in Tauri config** — add to `tauri.conf.json` windows array at position `x:780, y:760`. Add navigation entry.
- [ ] **WebSocket `memory_update` event** — emit from backend whenever a fact is added/updated/recalled. Frontend redraws affected node in real time (no full refresh needed).
- [ ] Verify (debugger-agent): graph renders with real facts; node colors match types; edges connect semantically similar facts; hover panel appears anchored to node with correct metadata; clicking a connected node in the panel focuses it; search filters correctly; `pnpm build` clean; `pytest backend/` passes.

---

## Phase 17 — Computer Eyes & Hands
*Handled by: `/backend-agent` (tools + wiring) + `/frontend-agent` (UI feedback). Gives Helix desktop vision and control. Planned in detail during 2026-06-15 session — see plan file at `C:\Users\User\.claude\plans\i-want-you-to-fluttering-penguin.md`.*

### New dependencies
- `mss` — fast screenshots (pure Python, Windows 11 optimised)
- `pywinauto` — accessibility-tree-based desktop control (NOT pixel-based; reliable on Windows 11)
- `pygetwindow` — window enumeration companion
- Playwright already installed (used by `browse_url`) — no new web dependency

### Phase 17A — Desktop Vision + Tool Wiring
- [ ] **Fix critical tool-calling gap** — `base_agent.py` `reason()` never passes `tools=` to Claude and never handles `tool_use` response blocks. Add agentic loop: stream first response → if `stop_reason == "tool_use"`, execute tools via registry → append `tool_result` → continue until `end_turn`. Max 5 rounds. Expose `last_final_message` on `ClaudeClient` after each stream call.
- [ ] **Add `complete()` non-streaming method to `ClaudeClient`** — for tool-loop rounds 2+ where tokens don't need streaming to UI.
- [ ] **Inject `tool_registry` into `BaseAgent` + `VoicePipeline`** — reorder `main.py` lifespan to build registry before agent runtime; pass via `AgentRuntime` → `BaseAgent.__init__`.
- [ ] **New `backend/tools/screen_tool.py`** — `take_screenshot(save_to?)` captures primary monitor via `mss`, returns `{"is_image": True, "image_base64": str, "path": str, "width": int, "height": int}`; `get_screen_info()` returns monitor geometry. Screenshots saved to `workspace/screenshots/`. Runs via `asyncio.to_thread`.
- [ ] **`is_image` sentinel in `_execute_tool()`** — when tool result has `is_image: True`, build `{"type": "image", "source": {"type": "base64", ...}}` content block for Claude's tool_result (not text). Enables Claude Vision to analyze screenshots.
- [ ] **Update `wiring.py` + `registry.py`** — register screen tools; grant `take_screenshot`/`get_screen_info` to all agents (read-only); desktop control tools (Phase 17B) to `production_lead` + `backend` only.
- [ ] Verify (debugger-agent): voice command "take a screenshot" → Claude calls tool → PNG saved to workspace → Claude describes what it sees; `pytest backend/` passes; `pnpm build` clean.

### Phase 17B — Desktop Control
- [ ] **New `backend/tools/desktop_tool.py`** — six tools, all run via `asyncio.to_thread` (pywinauto is blocking):
  - `open_application(app_name, args?)` — launches from hardcoded allowlist only (`notepad`, `calculator`, `explorer`, `chrome`, `firefox`, `code`, `terminal`, `powershell`); rejects unknown names → `{"ok": False, "error": "not in allowlist"}`. Uses `subprocess.Popen` (valid at tool level — not in code executor sandbox).
  - `list_windows()` — `pygetwindow.getAllWindows()` → `[{title, pid, visible, minimized}]`
  - `focus_window(title_contains)` — case-insensitive partial match, brings window to foreground
  - `click_element(window_title, element_text?, element_type?, x?, y?)` — pywinauto `uia` backend accessibility-tree click; coords fallback. COM init/uninit per thread.
  - `type_text(text, window_title?)` — pywinauto `type_keys()`
  - `press_key(key, window_title?)` — pywinauto `send_keys()` (e.g. `"ctrl+c"`, `"alt+f4"`)
- [ ] **Permissions**: desktop control tools → `production_lead` + `backend` only. NOT security, marketing, content, or frontend.
- [ ] Verify (debugger-agent): "open Notepad" → Notepad opens; "click Save button" → pywinauto finds and clicks element; allowlist rejects unknown apps; `pytest backend/` passes.

### Phase 17C — Web Access Confirmation + Enhancement
- [ ] **Expose screenshot in `browse_url` schema** — add `take_screenshot: bool = False` param to `BROWSE_URL_SCHEMA`; when true, capture full-page PNG and return `{"text": ..., "is_image": True, "image_base64": ...}` — same sentinel as screen_tool. `_execute_tool()` handles multi-part (text + image) tool_result content block.
- [ ] **Confirm end-to-end**: voice command "search the web for X" → Claude calls `web_search` or `browse_url` → result returned → Helix speaks summary.
- [ ] Verify (debugger-agent): browse_url with screenshot returns image content block; web_search returns results; both tools visible in Reasoning window tool cards (from Phase 15B); `pytest backend/` passes.

---

## Pending — On Hold Until Further Notice
*Agents: **skip this entire section** when planning or starting any new phase. These items are intentionally deferred and are NOT prerequisites for upcoming work. The user will schedule them explicitly when ready.*

### Packaging
- [ ] Run `pnpm tauri build` — generates Windows `.exe` installer
- [ ] Verify clean install on fresh Windows 11 machine end-to-end *(blocked — requires installer first)*

### Voice & Microphone *(requires dedicated microphone — not yet purchased)*
- [ ] E2E voice test — "Hey Helix, what's in my Slack?" → reads Slack → speaks answer
- [ ] E2E voice test — "Hey Helix, what's in my Gmail?" → reads inbox → speaks answer
- [ ] Tune wake-word sensitivity (currently threshold=0.5, may need adjustment after mic upgrade)
- [ ] Tune silence detection threshold (`SILENCE_RMS_THRESHOLD=500`) for new microphone
- [ ] Test interrupt ("stop") cancels mid-response reliably with new microphone

### UI
- [ ] Add microphone sensitivity indicator to AnimationWindow (small input-level bar when listening)

### Future Enhancements
- [ ] Proactive notifications — Helix speaks when important Slack/Gmail arrives
- [ ] Agent task visibility — show what each agent is working on in real-time in AgentsWindow
- [ ] Voice commands to control agent tasks ("Helix, tell Ben to update the UI")
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
| [HEALTH.md](HEALTH.md) | Full project audit 2026-06-16 — verified health snapshot, memory gap analysis, WS contract drift, ranked improvement opportunities, resequenced phase plan | Before starting any new phase; before touching memory, WS events, or security |

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
| Phase 15B — WebSocket Event Wiring | `/backend-agent` |
| Phase 16 (16A–16E) — Memory Intelligence | `/backend-agent` |
| Phase 16F — Memory Graph Visualization | `/backend-agent` (API) + `/frontend-agent` (Window 6) |
| Phase 17 (17A–17C) — Computer Eyes & Hands | `/backend-agent` (tools) + `/frontend-agent` (UI feedback) |

---

## How to Use This Project

1. **Start every session** — run the `production-manager` agent
   - It reads this file first, then `docs/` archive files, tells you exactly what's next, and which agent to invoke
2. **Run the delegated agent** — each agent does its work then updates this file
3. **Repeat** — run `production-manager` again after each agent finishes
4. **Done** when every checkbox above is checked
