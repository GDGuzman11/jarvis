---
name: phase13a-testing
description: How to test Phase 13A direct-agent-task endpoints (POST/GET /api/agents/{slug}/task[s]) — TestClient-without-lifespan + patched main.create_task/get_agent_tasks + fake roster
metadata:
  type: reference
---

Phase 13A adds two `backend/main.py` routes letting AgentsWindow talk to one agent directly. Test file: `backend/test_phase13a_verify.py`, 9 tests, all pass. Baseline after 13A: full `backend/` suite = **143 passed / 1 failed (144 total)**; the 1 fail is the SAME pre-existing `test_phase9_verify.py::test_no_secrets_committed_in_source_files` (Google OAuth client id in `get_gmail_token.py:9` + quoted copy in `docs/TEST_HISTORY.md`, owned by security-agent). See [[phase12c-agent-memory-testing]] for that baseline lineage (116→...→134→143 as tests accrete).

**Endpoints (main.py ~615-693):**
- `POST /api/agents/{agent_id}/task` body `{"goal": "..."}` (FastAPI `Body(..., embed=True)`). `agent_id` is a DISPLAY SLUG (atlas/ben/kado/sentinel/vega/quill), mapped via `main._PUBLIC_TO_AGENT_ID` to internal ids (production_lead/frontend/backend/security/marketing/content). 404 unknown slug, 404 if slug valid but `app.state.agents` has no live agent, 400 empty goal. Returns `{"task_id","agent_id"(slug, not internal),"status":"queued"}`. Calls `create_task(None, internal_id, title, description=clean_goal)` then `agent.enqueue_task({...})`.
- `GET /api/agents/{agent_id}/tasks` returns `{"agent_id"(slug), "tasks":[{"task_id","goal","status","created_at"}]}` — last `AGENT_TASK_LOG_LIMIT=5`. Calls `get_agent_tasks(internal_id)`; row shape from DB is `{id, created_by, assigned_to, description, status, result, created_at, updated_at}` → endpoint maps `id→task_id`, `description→goal`.

**Sanitization** (`main._sanitize_goal`): strips chars `< " "` except `\n`, `.strip()`, truncates to `MAX_GOAL_LEN=2000`. Oversized goal is TRUNCATED not rejected (200, len==2000). Control chars `\x00\x01` removed.

**TEST RECIPE (mirror `test_phase10_rename_verify.py`):** use Starlette `TestClient(main.app)` but do NOT enter it as a context manager — entering runs the full lifespan (DB init, voice pipeline, agent runtime, Slack/Gmail) which is heavy AND overwrites your seeded `app.state.agents`. Instead:
- Seed `main.app.state.agents = {internal_id: FakeAgent(...)}` where FakeAgent has `enqueue_task(self, task)` recording into a list.
- `create_task` and `get_agent_tasks` are imported INTO main's namespace (line 41-42 `from .memory import (create_task, get_agent_tasks)`), so patch `main.create_task` / `main.get_agent_tasks` with AsyncMock/async-def stubs — NO real SQLite, sidesteps the `tasks.assigned_to → agents` FK that the real endpoint would otherwise need seeded.
- Reset `main.app.state.agents = {}` on fixture teardown.

This pattern works for any main.py endpoint test that touches DB helpers + live agent registry without wanting the lifespan.
