---
name: agent-testing
description: Non-obvious gotchas when testing the Phase 4 agent system (BaseAgent / AgentRuntime / ProductionLead)
metadata:
  type: reference
---

Verifying the Phase 4 agent system (`backend/agents/`). Mock-test pattern: inject a `FakeHub` with an async `broadcast` that appends `AgentUpdate`s, pass `db_path=<temp>` and `hub=` to `AgentRuntime` / each agent, and replace `agent._claude` / `agent._ollama` with a stub whose `stream_response(messages, system_prompt)` is an async generator yielding a canned reply (no network). `pytest` runs with `asyncio_mode = "auto"`, so bare `async def` tests/fixtures work and async fixtures are fine.

**Status-flag vs broadcast race (the subtle one).** `BaseAgent._set_status` sets `self._status` *first*, then awaits `database.upsert_agent` and `self._hub.broadcast`. So polling `agent.status == "idle"` can return before the idle *broadcast* lands. If a test waits on the in-memory flag and then immediately calls `stop()`, the `offline` broadcast can race ahead and the captured event list is `['working', 'offline']` with no `idle`. **Fix:** when asserting on broadcast ordering, wait on `"idle" in hub.statuses_for(agent_id)` (the event), not on `agent.status`. `queue_size` also drops to 0 at `_queue.get()` (before processing finishes), so it's not a "task done" signal either.

**`database.create_task` enforces FKs.** `tasks.created_by` and `tasks.assigned_to` REFERENCE `agents(id)` with `PRAGMA foreign_keys = ON`. Seeding a task row directly in a test fails with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` unless both agent ids already have rows (an agent's `start()` upserts its own row). In the real delegation flow this is satisfied because all 6 agents start first. In a single-agent fixture, use that one agent's id for both ends, or start the full runtime.

**6 agent ids/names:** production_lead/Atlas, frontend/Ben, backend/Kado, security/Sentinel, marketing/Vega, content/Quill. `get_all_agents` orders by id.

Lifespan test uses Starlette `TestClient(app)` as a context manager — see [[lifespan-testing]]. venv python (uv not on PATH): see [[uv-path]].

Test file: `backend/agents/test_phase4_verify.py`.
