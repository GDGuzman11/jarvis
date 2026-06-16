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
- **Tier 0 progress (2026-06-16)**: ✅ Item 1 (Jarvis → Helix rename) complete & verified 5/5. Remaining Tier 0: scrub OAuth client ID from `get_gmail_token.py:9` + `docs/TEST_HISTORY.md:110` → 144/144 clean (items 2–3), fix SQLite WAL backup (item 4).
- **Next Task**: **Tier 0 items 2–3** — scrub OAuth client ID from 2 files → 144/144 clean (`/security-agent`). Then item 4 (WAL backup, `/backend-agent`). Then **Phase 15B** (wire missing WebSocket events). Then **Phase 16** (Memory Intelligence).
- **Blockers**: Dedicated microphone not yet purchased — voice E2E tests deferred to Pending.
- **Test State**: 143/144 passing · **2 files** failing secret-scan (`get_gmail_token.py` + `docs/TEST_HISTORY.md`) · `pnpm build` clean.
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
Dark theme `#080810` (updated 2026-06-04), electric blue/cyan accents `#00D4FF`, gold highlights `#FFB800`. Iron Man HUD — angular, futuristic, high-contrast. Sharp edges with glowing outlines. No rounded corners.

- **Grid**: fine dual-scale grid (80px major / 20px minor) at low opacity
- **Panels**: `rgba(8,14,28,0.82)` background, `backdrop-filter: blur(24px)`, `1px solid rgba(0,212,255,0.25)` border
- **WindowFrame**: angular header with `|`-style accent ticks, flowing `data-stream-top` animated border, pulsing rectangular status badge, corner accent marks
- **Buttons** (`.hud-btn`): `rgba(0,212,255,0.06)` bg, `0.5` opacity cyan border, full cyan border + shadow glow on hover — high contrast
- **Window layout**: orb (AnimationWindow) centred at `x:780, y:300`; Reasoning left `x:200`; Communications upper-right `x:1180`; Agents bottom `x:200, y:760`; Tools lower-right `x:1180, y:540`
- **Orb**: Neural intelligence sphere — 350 neuron `Points` (golden-spiral, vertexColors), ~480 normal `LineSegments` + ~120 red freedom `LineSegments` (~20% of connections, `#440011`→`#ff2244`), 30 drifting symbol `Sprite`s (∑ π ∞ λ etc.), 3 nested glow spheres + wireframe hologram shell, cascade activation (CASCADE_DEPTH=6, NEIGHBOR_K=4). SVG connection beams radiate from orb centre to other window edges with animated travelling dots.
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
- [ ] **Scrub OAuth client ID** from `get_gmail_token.py:9` — delete or parameterize the hardcoded `client_id`. Script is one-time bootstrap, not imported at runtime; safe to delete body or replace with `input()` prompt.
- [ ] **Scrub OAuth client ID** from `docs/TEST_HISTORY.md:110` (also present in `.claude/agent-memory/debugger-agent/` snapshot). Remove or redact from doc. Verify secret-scan passes on both files → **144/144 green**.
- [ ] **Fix SQLite backup** in `main.py:233` — replace raw file-copy zip with `conn.backup()` (or `VACUUM INTO`) and include `-wal`/`-shm` sidecar files. Current approach can produce stale/torn backups under WAL mode with concurrent writers.

---

## Phase 15B — WebSocket Event Wiring
*Handled by: `/backend-agent` (Kado). Must complete before Phase 16 — a broken UI demo undermines the memory work.*

### Known gap (HEALTH.md verified)
Frontend (`websocket.ts`) handles 9 event types. Backend (`events.py` + `main.py`) only broadcasts 6. Three windows are rendering skeletons:
- **Window 2 (Reasoning)** — `tool_call` defined in `events.py` but `registry.py:259` only audit-logs it, never broadcasts → tool cards stay empty
- **Window 3 (Communications)** — `comms` event never broadcast → Slack/Gmail inbox renders skeleton
- **Window 5 (Tools)** — `tool_permissions` event never broadcast → permission toggles render skeleton

### What to build (Phase 15B)
- [ ] **Broadcast `tool_call` from registry** — in `registry.py` after successful `call_tool()`, emit `ToolCallEvent` via the WebSocket hub (already defined in `events.py`; hub already available via `app.state.hub`). Include `tool_name`, `agent_id`, `args` preview (truncated, no secrets), `result` preview (≤200 chars). Reasoning window tool cards will populate automatically.
- [ ] **Broadcast `comms` event** — after each Slack/Gmail fetch in `backend/integrations/`, emit a `CommsEvent` with inbox snapshot (unread count, sender, subject/preview, timestamp). Communications window subscribes to this event type already.
- [ ] **Broadcast `tool_permissions` event** — on startup and on any `grant()`/`revoke()` call in `registry.py`, emit current per-agent permission matrix as `ToolPermissionsEvent`. Tools window subscribes already.
- [ ] **Wire `shutdown` broadcast** — confirm `shutdown` event fires to all connected windows when ⏻ is pressed (may already work via Tauri; verify and fix if not).
- [ ] Verify (debugger-agent): Reasoning window shows tool call cards when an agent uses a tool; Communications window shows live Slack/Gmail data; Tools window shows live permission toggles; `pnpm build` clean; backend suite still 144/144.

---

## Phase 16 — Memory Intelligence
*Handled by: `/backend-agent` (Kado). Enhance — do not replace — the existing SQLite + FAISS memory system. Research basis: Mem0 (49% LongMemEval), Zep/Graphiti (63.8% LongMemEval), TOKI bi-temporal operators, Ebbinghaus forgetting curves, ColBERT re-ranking. Target: ~85% of Zep quality, fully local, zero new cloud dependencies.*

### Memory system current state (HEALTH.md verified)
- **What works**: 3-layer brain (episodic SQLite + distilled `memory_facts` + FAISS semantic), wired into voice hot path, 7 memory tables, FTS5 keyword search, consolidation loop, daily backup, open loops, people profiles.
- **What's broken**: recall is similarity-only (`MIN_SEMANTIC_SCORE=0.25`, no recency/importance/frequency); `last_recalled_at` column exists but is never written; extraction is keyword rule-matching (misses paraphrases); facts accumulate forever (no contradiction resolution, no eviction); recalled memories injected into system prompt without sanitization (latent injection vector).

### Phase 16A — Foundation + Safety
*Close the security gap and activate the dead recall infrastructure before adding more memory writers.*

- [ ] **Sanitize recall→prompt injection boundary** — in `format_context()` / `build_system_prompt()` (`persona.py:118`): wrap recalled facts in an `<untrusted_memory>` delimiter tag and strip control characters before injection. Prevents a malicious email/Slack body (once those become facts) from injecting into the system prompt. Add to `backend/test_phase16a_verify.py`.
- [ ] **Activate `last_recalled_at`** — in `database.py`, add `UPDATE memory_facts SET last_recalled_at = ? WHERE id = ?` on every fact returned by recall. Column already exists (line 113) but is written nowhere. Unlocks recency scoring in 16B.
- [ ] **Add memory quality columns to `memory_facts`** — migrate schema to add: `confidence FLOAT DEFAULT 0.8`, `created_by TEXT DEFAULT 'system'` (values: `'user'`, `'agent'`, `'inference'`), `source_turn_id INTEGER`, `access_count INTEGER DEFAULT 0`. Backfill `access_count = 0` for existing rows. These columns are prerequisites for 16B scoring.
- [ ] Verify (debugger-agent): control chars stripped from injected facts; `last_recalled_at` updates on recall; new columns present; `pytest backend/` passes.

### Phase 16B — Multi-Signal Re-Ranking
*Replace similarity-only FAISS recall with a weighted scoring pipeline.*

- [ ] **Implement multi-signal retrieval** in `backend/memory/manager.py` — after FAISS returns top-K candidates, score each with:
  - `0.40 × semantic_similarity` (FAISS score, already have it)
  - `0.20 × keyword_bm25` (FTS5 already built — reuse `search_memory_facts()`)
  - `0.20 × recency_score` (`1 / (1 + days_since_last_recalled)` using now-active `last_recalled_at`)
  - `0.10 × importance_score` (existing `importance` column in `memory_facts`)
  - `0.10 × frequency_score` (`log(access_count + 1)` using new column from 16A)
  - Return top-N by composite score. No new dependencies — pure Python math over existing data.
- [ ] **Increment `access_count`** on every recall hit (same DB write as `last_recalled_at` in 16A).
- [ ] Verify (debugger-agent): recently accessed facts rank above equally-similar older facts; importance-weighted facts surface correctly; `pytest backend/` passes.

### Phase 16C — LLM-Driven Extraction
*Replace keyword rule-matching in `evaluator.py` with an LLM-driven fact extraction pipeline (Mem0 pattern).*

- [ ] **Replace `_RULES` keyword matching** in `backend/memory/evaluator.py` with an LLM extraction call — prompt Claude (or Ollama `phi3.5` for speed/cost) to extract facts from each conversation turn and classify each as `ADD`, `UPDATE`, `DELETE`, or `NOOP`. Prompt template should output structured JSON: `[{"action": "ADD"|"UPDATE"|"DELETE"|"NOOP", "fact": "...", "confidence": 0.0-1.0, "subject": "..."}]`. Keep existing rule pass as a fast pre-filter (if no patterns match at all, skip LLM call).
- [ ] **Wire ADD/UPDATE/DELETE/NOOP** into `save_memory_fact()` — UPDATE finds the most similar existing fact (FAISS score > 0.85) and overwrites; DELETE marks `valid_to = now()`; NOOP skips write.
- [ ] **Set `created_by`** on every extracted fact (`'user'` for direct statements, `'inference'` for LLM-derived).
- [ ] Verify (debugger-agent): paraphrased facts ("I moved to Boston" / "Boston is where I live now") produce single fact not two; explicit contradictions trigger UPDATE not second INSERT; `pytest backend/` passes.

### Phase 16D — Bi-Temporal Facts + Ebbinghaus + TOKI Operators
*Contradiction resolution, temporal validity, and natural forgetting.*

- [ ] **Add bi-temporal columns to `memory_facts`** — `valid_from TIMESTAMP DEFAULT (datetime('now'))`, `valid_to TIMESTAMP DEFAULT NULL`, `strength FLOAT DEFAULT 1.0`, `half_life_days INTEGER DEFAULT 14`, `superseded_by_fact_id INTEGER DEFAULT NULL`, `write_policy TEXT DEFAULT 'last-write-wins'`, `conflicting_fact_ids TEXT DEFAULT NULL` (JSON array). Migrate existing rows with safe defaults.
- [ ] **Implement TOKI contradiction operators** — when an incoming fact conflicts with an existing one, apply the `write_policy` for that fact type:
  - `last-write-wins` — set `valid_to = now()` on old fact, INSERT new (default for locations, status)
  - `evidence-weighted` — compare `confidence` scores; higher wins (for preferences, allergies)
  - `merge` — both facts valid in different time windows; set `valid_to` on old, INSERT new with `valid_from` = now (for employment history, relationships)
  - `await-confirmation` — mark `conflicting_fact_ids`, surface to Helix at next session start
- [ ] **Nightly Ebbinghaus decay job** — add to `_consolidation_loop()` in `main.py`: for each fact, `strength = strength × exp(-days_since_recalled / half_life_days)`. Facts at `strength < 0.1` → mark `valid_to = now()` (archived, not deleted). Run after existing consolidation step.
- [ ] Verify (debugger-agent): old fact's `valid_to` set when superseded; strength decays on schedule; archived facts excluded from active recall; `pytest backend/` passes.

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
