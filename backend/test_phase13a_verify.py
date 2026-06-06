"""Phase 13A verification — direct agent task endpoints.

Targeted tests for the two new ``backend/main.py`` routes that let the
AgentsWindow UI talk to a single agent directly:

* ``POST /api/agents/{agent_id}/task`` — accepts ``{"goal": "..."}``, validates
  the display slug (atlas/ben/kado/sentinel/vega/quill), sanitizes the goal
  (strip control chars, cap at ``MAX_GOAL_LEN``), persists a ``tasks`` row, and
  enqueues directly onto the target agent's live queue. Returns
  ``{"task_id", "agent_id", "status": "queued"}``; 404 for unknown slug, 400 for
  empty goal.
* ``GET /api/agents/{agent_id}/tasks`` — returns ``{"agent_id", "tasks": [...]}``
  (last ``AGENT_TASK_LOG_LIMIT`` tasks); 404 for unknown slug.

Pattern mirrors ``test_phase10_rename_verify.py``: Starlette ``TestClient``
*without* the lifespan context manager (so the heavy DB/voice/agent startup is
skipped), a seeded ``app.state.agents`` roster of fake agents, and the two DB
helpers (``main.create_task`` / ``main.get_agent_tasks``) patched so no real
SQLite is touched. This isolates the endpoints' own validation, sanitization,
persistence call, and enqueue plumbing.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.main as main


# --- Test doubles -----------------------------------------------------------


class _FakeAgent:
    """Stand-in live agent recording everything enqueued onto it."""

    def __init__(self, agent_id: str, name: str) -> None:
        self.id = agent_id
        self.name = name
        self.status = "idle"
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_task(self, task: dict[str, Any]) -> None:
        self.enqueued.append(task)


# Internal ids matching _PUBLIC_TO_AGENT_ID's values.
_ROSTER = {
    "production_lead": _FakeAgent("production_lead", "Atlas"),
    "frontend": _FakeAgent("frontend", "Ben"),
    "backend": _FakeAgent("backend", "Kado"),
    "security": _FakeAgent("security", "Sentinel"),
    "marketing": _FakeAgent("marketing", "Vega"),
    "content": _FakeAgent("content", "Quill"),
}


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    """TestClient with a seeded fake roster and patched DB helpers.

    NOT used as a context manager — entering it would run the full app lifespan
    (DB init, voice pipeline, agent runtime, Slack/Gmail) which is heavy and
    would overwrite the seeded ``app.state.agents``. Skipping the lifespan
    isolates the endpoint logic.

    ``create_task`` returns a deterministic id without touching SQLite;
    ``get_agent_tasks`` returns a canned list keyed by internal agent id so the
    GET route can be exercised without a real DB.
    """
    # Fresh agents each test so enqueue assertions don't bleed across tests.
    roster = {
        internal: _FakeAgent(internal, fake.name)
        for internal, fake in _ROSTER.items()
    }
    main.app.state.agents = roster

    created: dict[str, Any] = {"calls": []}

    async def fake_create_task(creator, assignee, title, description=None):
        created["calls"].append(
            {
                "creator": creator,
                "assignee": assignee,
                "title": title,
                "description": description,
            }
        )
        return 4242

    # Canned task rows keyed by internal id, in get_agent_tasks' row shape.
    canned = {
        "production_lead": [
            {
                "id": 7,
                "created_by": None,
                "assigned_to": "production_lead",
                "description": "Plan the launch",
                "status": "done",
                "result": None,
                "created_at": "2026-06-06 10:00:00",
                "updated_at": "2026-06-06 10:05:00",
            }
        ],
    }

    async def fake_get_agent_tasks(agent_id: str):
        return list(canned.get(agent_id, []))

    monkeypatch.setattr(main, "create_task", fake_create_task)
    monkeypatch.setattr(main, "get_agent_tasks", fake_get_agent_tasks)

    c = TestClient(main.app)
    c.roster = roster  # type: ignore[attr-defined]
    c.created = created  # type: ignore[attr-defined]
    yield c

    main.app.state.agents = {}


# --- POST /api/agents/{id}/task ---------------------------------------------


def test_submit_valid_goal_returns_queued(client) -> None:
    resp = client.post("/api/agents/atlas/task", json={"goal": "Plan the demo"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == 4242
    assert body["agent_id"] == "atlas"
    assert body["status"] == "queued"

    # The durable record was written and the live queue received the task.
    assert len(client.created["calls"]) == 1
    call = client.created["calls"][0]
    assert call["assignee"] == "production_lead"  # internal id, not the slug
    atlas = client.roster["production_lead"]
    assert len(atlas.enqueued) == 1
    assert atlas.enqueued[0]["task_id"] == 4242
    assert atlas.enqueued[0]["description"] == "Plan the demo"


def test_submit_empty_goal_returns_400(client) -> None:
    resp = client.post("/api/agents/atlas/task", json={"goal": "   "})

    assert resp.status_code == 400
    # No persistence and no enqueue for an empty goal.
    assert client.created["calls"] == []
    assert client.roster["production_lead"].enqueued == []


def test_submit_unknown_slug_returns_404(client) -> None:
    resp = client.post("/api/agents/invalid_slug/task", json={"goal": "Do a thing"})

    assert resp.status_code == 404
    assert client.created["calls"] == []


def test_submit_non_atlas_agent_succeeds(client) -> None:
    """A direct task to a specialist (Ben) enqueues onto that agent, not Atlas."""
    resp = client.post("/api/agents/ben/task", json={"goal": "Tweak the orb"})

    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "ben"

    ben = client.roster["frontend"]
    assert len(ben.enqueued) == 1
    assert ben.enqueued[0]["description"] == "Tweak the orb"
    # Atlas must NOT have received the directly-targeted task.
    assert client.roster["production_lead"].enqueued == []


def test_submit_strips_control_chars(client) -> None:
    """Goal with embedded NUL/SOH control chars is sanitized; submit succeeds."""
    resp = client.post(
        "/api/agents/atlas/task",
        json={"goal": "Build\x00 the\x01 thing"},
    )

    assert resp.status_code == 200
    atlas = client.roster["production_lead"]
    assert len(atlas.enqueued) == 1
    cleaned = atlas.enqueued[0]["description"]
    assert "\x00" not in cleaned and "\x01" not in cleaned
    assert cleaned == "Build the thing"


def test_submit_oversized_goal_is_truncated(client) -> None:
    """A goal over MAX_GOAL_LEN is truncated (not rejected) — current behavior."""
    long_goal = "x" * (main.MAX_GOAL_LEN + 500)
    resp = client.post("/api/agents/atlas/task", json={"goal": long_goal})

    # Implemented behavior is truncation in _sanitize_goal, so submit succeeds.
    assert resp.status_code == 200
    atlas = client.roster["production_lead"]
    assert len(atlas.enqueued) == 1
    assert len(atlas.enqueued[0]["description"]) == main.MAX_GOAL_LEN


# --- GET /api/agents/{id}/tasks ---------------------------------------------


def test_list_tasks_returns_agent_and_tasks(client) -> None:
    resp = client.get("/api/agents/atlas/tasks")

    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"] == "atlas"
    assert isinstance(body["tasks"], list)
    assert len(body["tasks"]) == 1
    task = body["tasks"][0]
    assert task["task_id"] == 7
    assert task["goal"] == "Plan the launch"
    assert task["status"] == "done"


def test_list_tasks_empty_agent_returns_empty_list(client) -> None:
    """An agent with no canned rows returns an empty task list, still 200."""
    resp = client.get("/api/agents/ben/tasks")

    assert resp.status_code == 200
    assert resp.json() == {"agent_id": "ben", "tasks": []}


def test_list_tasks_unknown_slug_returns_404(client) -> None:
    resp = client.get("/api/agents/invalid_slug/tasks")

    assert resp.status_code == 404
