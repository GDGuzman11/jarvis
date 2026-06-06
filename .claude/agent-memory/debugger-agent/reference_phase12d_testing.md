---
name: phase12d-memory-intelligence-testing
description: How to test Phase 12D memory intelligence (detect_open_loops/extract_person/failure facts/consolidate side-effects/older_than_hours); the one-loop-per-sentence defect
metadata:
  type: reference
---

Phase 12D adds the intelligence layer on Phase 12A scoring. See also [[phase12-memory-testing]] (12B voice) and [[phase12c-agent-memory-testing]] (12C agents). Test file: `backend/memory/test_phase12d_verify.py`, 10 targeted tests.

**What changed in 12D:**
- `evaluator.py` — `detect_open_loops(text)->list[str]` (trigger phrases in `_OPEN_LOOP_TRIGGERS`, strips trigger, dedupes); `extract_person(text)->dict|None` (`{name,email,notes}`, "from <Name>" regex + email-local-part fallback); failure category now extracts `Failed approach: <approach>. Reason: <reason>.` via `_split_failure` (splits on but/because/since/as).
- `manager.py::consolidate` — fires `detect_open_loops` (→`save_open_loop`) and `extract_person` (→`save_person`) as **`asyncio.create_task` fire-and-forget**, REGARDLESS of importance score, before the score gate. Added `run_consolidation()` back-fill (re-scans last 50 conversations, dedupes by sha1 of distilled fact[:100]).
- `database.py::get_open_loops(status, older_than_hours=None, *, db_path)` — `older_than_hours` adds `created_at <= datetime('now','-Nh')`. Also a positional-`db_path` wrapper `get_open_loops_async(db_path, status, older_than_hours)` the pipeline/greeting call.
- `main.py` — `_startup_greeting(memory_manager=None)` surfaces overdue loops (`older_than_hours=12`); `_consolidation_loop(mm)` runs `run_consolidation()` every `CONSOLIDATION_INTERVAL_S=600`s in lifespan.

**Test recipes:** evaluator tests are pure-function sync (no async). consolidate test = `MemoryManager(db_path=temp, vector_store=MagicMock with __len__=0)` + poll `get_open_loops("open", db_path=...)` ≤2s (the open-loop write is create_task'd). older_than_hours test = seed a row with raw `INSERT ... datetime('now','-25 hours')` then assert 24h includes / 26h excludes. Test 10 = import `backend.main`, `inspect.iscoroutinefunction(_consolidation_loop)` + `"memory_manager" in signature(_startup_greeting).parameters`.

**THE 12D DEFECT (test_detect_open_loops_multiple FAILS):** `detect_open_loops` records **at most ONE loop per sentence** — it `break`s (evaluator.py ~line 271) after the first matching trigger in a sentence. `_SENTENCE_SPLIT_RE` only splits on `.!?;\n`, NOT on "and". So "I need to update the readme and don't forget to check the logs" is one sentence → returns only `['check the logs']` (first trigger by `_OPEN_LOOP_TRIGGERS` list order wins; "don't forget to" precedes "i need to"). Same text with a period between clauses correctly yields both. Brief's test 3 expects 2 → genuine bug, NOT a test artifact. Fix: re-scan the remainder of the sentence after stripping a matched trigger instead of breaking (keep the `seen` dedupe).

**Baseline 2026-06-05 (Phase 12D):** full `pytest backend/` = **125 passed / 2 failed (127 total)**. The 2 fails: (1) the NEW Phase 12D `test_detect_open_loops_multiple` defect above; (2) the SAME pre-existing `test_no_secrets_committed_in_source_files` (Google OAuth *client id*, public, `get_gmail_token.py:9` + quoted copy in `docs/TEST_HISTORY.md`, line drifts). 12C was 116/117; +10 new 12D tests, +1 new fail → 127 total. No previously-passing test regressed. asyncio_mode=auto. Run: `.venv/Scripts/python.exe -m pytest backend/ -q`.
