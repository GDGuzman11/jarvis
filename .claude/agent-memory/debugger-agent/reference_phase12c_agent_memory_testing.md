---
name: phase12c-agent-memory-testing
description: How to test Phase 12C agent-memory wiring (reason recall/store, _remember checkpoint, start restore, decisions/agent_performance writes) — fire-and-forget + FK seeding gotchas
metadata:
  type: reference
---

Phase 12C wires persistent memory into all 6 agents (`backend/agents/`). See also [[phase12-memory-testing]] (voice 12B) and [[agent-testing]] (Phase 4 patterns). Test file: `backend/agents/test_phase12c_verify.py`, 7 tests (test 8 = Phase 4 regression, not a new test).

**What changed in 12C:**
- `base_agent.py::reason()` — when `memory_manager` is set: `recall(query, n_recent=6, n_semantic=3)` BEFORE Claude; `messages = recalled.episodic_messages + self._context + [{"role":"user","content":prompt}]` (recalled FIRST, then rolling context, then prompt). AFTER: `store(prompt, role="user", channel="agent:<id>")`, `store(reply, role="jarvis", ...)` if reply, then `asyncio.create_task(consolidate(prompt, reply, source="agent", agent_id=<id>))`.
- `base_agent.py::_remember()` — appends to `self._context` AND, **only when `memory_manager is None`**, `create_task(_checkpoint_context(...))` writing to `conversations` under `channel="agent:<id>"`. With a memory_manager the checkpoint is skipped (store owns the episodic write) to avoid a duplicate row.
- `base_agent.py::start()` → `_restore_context()` loads up to `RESTORE_CONTEXT_MESSAGES=12` rows via `get_recent_conversations(limit, channel="agent:<id>")`, oldest-first, `jarvis`→`assistant`. Empty DB → `self._context == []` (no crash).
- `production_lead.py::_delegate()` → `_record_delegation_decision()` create_task's a `decisions` row (gated on memory_manager).
- specialists' `handle_task()` call `_record_performance(task, "success"|"failed")` → create_task's `agent_performance` row (gated on memory_manager).

**KEY GOTCHA — everything is fire-and-forget.** `_checkpoint_context`, `consolidate`, `_record_delegation_decision`, `_record_performance` all run via `asyncio.create_task` (never add latency to a task). Tests MUST poll for the side effect (DB row / fake-call record) after a loop yield — do NOT assert synchronously right after the method returns. Use an async-predicate poll helper (`while ...: if await pred(): return; await asyncio.sleep(0.01)`).

**KEY GOTCHA — FK seeding for delegation test.** ProductionLead `handle_task("Build a new API endpoint")` keyword-routes to `backend` and `_delegate` writes a `tasks` row with `assigned_to="backend"` (FK → agents). You must seed the `backend` agent row (`upsert_agent("backend",...)`) in addition to `lead.start()` (which only seeds `production_lead`). Otherwise: `sqlite3.IntegrityError: FOREIGN KEY constraint failed`. This is a fixture artifact (minimal single-lead roster), not a bug.

**Gating:** `decisions` and `agent_performance` writes are gated on `self.memory_manager is not None`. Tests 6 & 7 MUST inject a FakeMemoryManager or no row is written. `agent_performance.agent_id` is NOT NULL FK ON DELETE CASCADE → seed agent row via `start()` first.

**FakeMemoryManager surface agents need:** `recall(query, n_recent, n_semantic)->RecallResult`, `store(text, role, channel)`, `consolidate(user_text, reply, *, source, agent_id)`, AND `store_fact(content, **kw)` — the last is called from `_log_audit` when memory_manager is set (audit→semantic promotion). 12B's FakeMemoryManager lacks `store_fact`; agents need it.

**`decisions` has no public reader** in `database.py` — query the table directly via `await database.connect(db_path)` + raw SQL in the test.

**Baseline as of 2026-06-06 (Phase 12C):** full `pytest backend/` = **116 passed / 1 failed (117 total)**. The 1 fail is the SAME pre-existing `test_phase9_verify.py::test_no_secrets_committed_in_source_files` (Google OAuth *client id*, public, in `get_gmail_token.py:9` + a quoted copy in `docs/TEST_HISTORY.md` — line number drifts as the doc grows). Owned by security-agent, independent of memory work. Brief said "109/110"; that was the pre-12C count, +7 new tests = 116/117. asyncio_mode=auto. Run: `.venv/Scripts/python.exe -m pytest backend/ -v`.
