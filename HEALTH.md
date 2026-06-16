# JARVIS — Health & Audit Reference

> Full project audit conducted by Atlas (Production Lead) with backend/frontend/security/debugger agents.
> **Audit date: 2026-06-16.** Findings tagged **[VERIFIED]** (ran it / read exact code) vs **[REPORTED]** (specialist agent finding).
> This is a reference snapshot — re-verify before acting on any item, as code changes over time.

---

## 1. Health Snapshot (verified by running it)

| Gate | CLAUDE.md claims | Reality (verified) | Verdict |
|---|---|---|---|
| Backend pytest | 143/144 passing | **143 passed, 1 failed** in ~45s | Count accurate |
| Secret-scan failure | 1 file (`get_gmail_token.py`) | **2 files** — `get_gmail_token.py:9` AND `docs/TEST_HISTORY.md:110` (also in `.claude/agent-memory/debugger-agent/`) | Doc drift — failure spreading |
| Frontend `pnpm build` | clean | **tsc 0 errors, vite built ~3.68s** | Accurate (PowerShell "node.exe NativeCommandError" is just vite's chunk-size advisory on stderr, not a failure) |

**Bottom line:** Health is good. The one red test is a false-positive on *severity* — a public OAuth client ID, not a credential — but it should be scrubbed to reach a true 144/144.

---

## 2. Memory Capabilities — Current Stage (~60% to goal)

**Goal:** persistent assistant that remembers across sessions, learns, and recalls the RIGHT thing.

### Built & ACTIVE (not stubbed) — verified in code
- 3-layer "Brain": episodic (`conversations`) + distilled (`memory_facts`) + semantic (FAISS via `VectorStore`, sentence-transformers `all-MiniLM-L6-v2`), coordinated by `MemoryManager`.
- Wired into the **voice hot path** (`backend/voice/pipeline.py:482–533`): recall before Claude call, fire-and-forget consolidate after. **Zero added speech latency** (off-loaded via `asyncio.create_task` / `asyncio.to_thread`).
- 7 memory tables incl. `people`, `open_loops`, `decisions`, `agent_performance`. FTS5 keyword search (`porter ascii`) with sync triggers.
- Periodic consolidation loop (10 min) + daily backup loop in `main.py` lifespan. Open-loop + person extraction (Phase 12D) live.
- Idempotent back-fill consolidation (`run_consolidation`) dedupes on content hash.

### Weak link (all VERIFIED)
- **Recall is similarity-ONLY** (`manager.py:403`). Top-K FAISS filtered at `MIN_SEMANTIC_SCORE=0.25`. No recency/importance/frequency weighting.
- **`last_recalled_at` is dead** (`database.py:113`): column exists, is SELECTed, but **written nowhere**. Usage-ranking hook is inert.
- **Extraction is rule-based keyword matching** (`evaluator.py` `_RULES`), not LLM-driven. Misses anything outside its phrase list; mis-scores paraphrases.
- **Append-only, no contradiction handling.** `save_memory_fact` always INSERTs. "I use Postgres" then "switched to SQLite" → both persist, both recallable. No supersede / eviction / forgetting.
- **Unsanitized injection** into system prompt (`format_context` → `build_system_prompt`, `persona.py:118`). Stored prompt-injection vector.

### Verdict
Reliably *persists* and recalls *something relevant* across sessions — hard plumbing done and battle-tested. Does NOT yet *learn* (no contradiction resolution/forgetting) or recall the *right* thing under load (similarity-only, recency hook unused). That gap = Phase 16.

---

## 3. Improvement Opportunities (ranked by impact ÷ effort)

**B**=backend, **F**=frontend, **S**=security.

| # | Area | Finding | Impact | Effort | Source |
|---|---|---|---|---|---|
| 1 | F→B | **WS contract drift.** Frontend handles 9 event types; backend emits 6. `comms`, `tool_permissions`, `shutdown` never broadcast → Comms (Win3) & Tools-permission (Win5) render skeletons. `tool_call` defined in `events.py` but `registry.py:259` only audit-logs it, never broadcasts → Reasoning (Win2) tool cards stay empty. | High | M | [VERIFIED] |
| 2 | S/B | **Backup zips LIVE `jarvis.db`** (`main.py:233`) with 3 concurrent writers, **omits `-wal`/`-shm` sidecars**. WAL-mode recent commits live in `-wal` → restored backup can be **stale/torn** post-crash. Use `conn.backup()` or `VACUUM INTO`. | Med (reliability) | S/M | [VERIFIED] |
| 3 | S | **Scrub OAuth client ID** from `get_gmail_token.py:9` + `docs/TEST_HISTORY.md:110`. Public client ID (not secret) but only thing keeping suite red; leaks GCP project number. Script is one-time bootstrap, **not imported at runtime** — delete or parameterize. | Med (→144/144) | S | [VERIFIED] fail + [REPORTED] unused |
| 4 | S/B | **Sanitize recalled memory at injection boundary.** Input sanitized at STT/goal entry but NOT when facts/turns re-injected into system prompt. Low risk today (single-user) but **latent High**: once Gmail/Slack bodies become facts, an attacker who emails you gets persistent prompt injection. Add control-char strip + "untrusted data" delimiter in `format_context`. | Low now / High latent | S | [VERIFIED] path + [REPORTED] severity |
| 5 | B | **Activate `last_recalled_at`** + multi-signal re-ranking (recency + importance + similarity). Column + FAISS scores already exist. Highest-leverage memory-quality win. | High | M | [VERIFIED] |
| 6 | B | **No contradiction/supersede logic.** Facts accumulate forever; stale recalled alongside current. Needs UPDATE/DELETE path (Mem0-style). | High | L | [VERIFIED] |
| 7 | F | AnimationWindow bundle 903 kB (244 kB gz, Three.js) — but already a **separate lazy chunk**, not in boot path. **Leave it.** | Low | — | [VERIFIED] code-split |
| 8 | F | `voice_state: "error"` + minor shape mismatches; dead/forward-declared store fields for orphaned events. | Low | S | [REPORTED] |
| 9 | B | **RestrictedPython is mitigation, not a jail.** os/sys/subprocess/`__import__` blocked (tests prove), but 10s timeout can't kill CPU-bound thread (leaks). Fine for trusted local input; only matters if exposed. | Low | M (if exposed) | [REPORTED] + tests [VERIFIED] |

### Confirmed clean (no action)
OAuth scopes least-privilege (Gmail `readonly`+`send`, metadata-only inbox reads; Slack `chat:write`/`im:read`/`channels:read`). `audit_log` metadata-only across all 11 call sites. FastAPI binds `127.0.0.1`. Keyring leaks no secrets to files/logs. Input sanitization at entry points solid. **All 6 Security Rules hold.**

---

## 4. Status vs CLAUDE.md (phase-by-phase)

- **Phases 1–6** (backend, voice, agents, integrations, tools): genuinely complete and tested.
- **Phase 7 (UI):** marked complete, **has gaps.** 5 windows render, but Comms/Tools-permission/Reasoning-tool-cards wired to events backend never sends (§3 #1). Visually done, functionally half-live.
- **Phase 8 (Security):** solid. All rules hold.
- **Phase 9 (Testing):** 143/144. "1 pre-existing failure" understates — now spans 2 files.
- **Phases 10–15:** complete and archived; orb (15A) verified.
- **Pending:** correctly deferred — Packaging (needs `tauri build`), Voice/Mic E2E (needs hardware — legit blocker), some UI polish.

### CLAUDE.md corrections needed
1. Strike stale "Future Enhancement" line *"Jarvis remembers context across sessions (FAISS semantic memory populated by conversations)"* — **already built & active (Phase 12)**.
2. Secret-scan note should say **2 files**, not 1.
3. Phase 7 should carry a known-gap note about un-emitted WS events.

---

## 5. Recommended Next Steps (resequenced)

**Phase 16 — Memory Intelligence** confirmed as next major phase: enhance (not replace) existing system. No frameworks (Mem0/Zep/Letta/OpenClaw) adopted wholesale — plumbing exists, we add the brain.

### Tier 0 — Hygiene (hours, do first)
1. Scrub OAuth client ID + delete/parameterize `get_gmail_token.py` → **144/144 green** (§3 #3).
2. Correct CLAUDE.md (3 corrections in §4).
3. Fix backup to use `conn.backup()`/`VACUUM INTO` + include WAL state (§3 #2).

### Phase 15B (slot BEFORE 16, route to Kado/backend)
4. Wire the missing WebSocket events (§3 #1) so Comms/Tools/Reasoning windows actually work. A "remembering assistant" demo falls flat with 3 empty windows.

### Phase 16A — Foundation + safety
5. Sanitize recall→prompt boundary with untrusted-data delimiter (§3 #4) — close latent injection door before adding more memory writers.
6. Activate `last_recalled_at` (write on every recall hit) — unlocks 16B.

### Phase 16B — Multi-signal re-ranking
7. Replace similarity-only recall with recency + importance + similarity (§3 #5). Biggest memory-quality jump per effort.

### Phase 16C — LLM-driven consolidation
8. Mem0-style extract → ADD/UPDATE/DELETE/NOOP with contradiction resolution on the consolidation path (keep cheap rule pass as fast pre-filter). Solves "no forgetting / no supersede" (§3 #6). Use Ollama locally for cheap per-write calls, Claude as quality path.

### Phase 16D — Bi-temporal facts + agent skill passports
9. Zep/Graphiti-style valid-from/valid-to + per-agent/per-tool success/failure passports. Most ambitious, lowest urgency.

### Leave in Pending
Packaging and Voice/Mic E2E (mic is a real hardware blocker — don't touch until purchased).

---

## Research Context (for reference)

- **2026 frontier** (web research): LLM-driven memory management (Mem0-style extract→ADD/UPDATE/DELETE/NOOP with contradiction resolution) + temporal/bi-temporal facts (Zep/Graphiti, scores 63.8% vs Mem0 49.0% on LongMemEval). Multi-signal retrieval (semantic+keyword+recency+importance) is standard production practice.
- **Decision:** adopt the *techniques*, not the cloud frameworks — local-first (4GB VRAM / 16GB RAM, 127.0.0.1-only) constraints + CORE PRINCIPLE (enhance, don't replace).
- **OpenClaw evaluated & declined** for wholesale adoption (too young — 2 renames in 3 months, published vuln taxonomy, resource-heavy). Worth borrowing patterns later: heartbeat → proactive notifications; runtime tool sandboxing; trace IDs across delegate chain.
