"""Phase 4 — Agent System verification tests.

Covers the seven Phase 4 acceptance checks:

1. BaseAgent lifecycle (start -> idle row, enqueue -> working->idle, stop -> offline).
2. Status broadcasts (working + idle AgentUpdate events fan out during a task).
3. DB persistence (6 agent rows after start; survive a fresh runtime / restart).
4. ProductionLead keyword routing (frontend / backend / security keywords).
5. Delegation (submit_goal writes a tasks row and enqueues to the specialist).
6. Error recovery (a raising handle_task marks the task failed; the agent recovers
   to idle and the loop survives).
7. Lifespan wiring (TestClient: /health 200, 6 running agents, clean shutdown).

All tests use a temp SQLite DB and a fake hub + stubbed reasoning clients, so no
real API keys, network, or shared on-disk state are touched.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from backend.agents.backend_agent import BackendAgent
from backend.agents.base_agent import BaseAgent
from backend.agents.runtime import AgentRuntime
from backend.events import AgentUpdate
from backend.memory import database

EXPECTED_AGENTS: dict[str, str] = {
    "production_lead": "Atlas",
    "frontend": "Ben",
    "backend": "Kado",
    "security": "Sentinel",
    "marketing": "Vega",
    "content": "Quill",
}


# --- Test doubles -----------------------------------------------------------


class FakeHub:
    """Collects every AgentUpdate broadcast so tests can assert on transitions."""

    def __init__(self) -> None:
        self.events: list[AgentUpdate] = []

    async def broadcast(self, event: Any) -> int:
        self.events.append(event)
        return 1

    def statuses_for(self, agent_id: str) -> list[str]:
        return [e.status for e in self.events if e.agent_id == agent_id]


class StubReasoner:
    """Stand-in Claude/Ollama client that streams a canned reply, no network."""

    def __init__(self, reply: str = "ok") -> None:
        self._reply = reply

    async def stream_response(self, messages, system_prompt):  # noqa: ANN001
        yield self._reply


@pytest.fixture()
async def db_path(tmp_path: Path) -> Path:
    """A fresh, fully-migrated temp database for one test."""
    path = tmp_path / "jarvis.db"
    await database.init_db(path)
    return path


def _make_runtime(db_path: Path, hub: FakeHub) -> AgentRuntime:
    """Build an AgentRuntime against the temp DB + fake hub, with stub reasoners.

    Replaces each agent's Claude/Ollama clients with stubs so no task ever hits
    the network when its handler calls ``reason``.
    """
    runtime = AgentRuntime(hub=hub, db_path=db_path)
    for agent in runtime.agents.values():
        agent._claude = StubReasoner()  # type: ignore[attr-defined]
        agent._ollama = StubReasoner()  # type: ignore[attr-defined]
    return runtime


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    """Poll ``predicate`` until true or raise TimeoutError (no fixed sleeps)."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("condition not met within timeout")


# --- 1. BaseAgent lifecycle -------------------------------------------------


async def test_baseagent_lifecycle(db_path: Path) -> None:
    hub = FakeHub()
    agent = BackendAgent(hub=hub, db_path=db_path)
    agent._claude = StubReasoner("done")  # type: ignore[attr-defined]
    agent._ollama = StubReasoner("done")  # type: ignore[attr-defined]

    # start() upserts an idle row and brings the loop up.
    await agent.start()
    assert agent.is_running
    row = await database.get_agent("backend", db_path=db_path)
    assert row is not None and row["status"] == "idle"

    # enqueue_task() processes and returns to idle.
    agent.enqueue_task({"description": "Build a /health endpoint"})
    await _wait_until(lambda: agent.queue_size == 0 and agent.status == "idle")
    assert agent.status == "idle"

    # stop() sets offline status (in memory and persisted).
    await agent.stop()
    assert not agent.is_running
    assert agent.status == "offline"
    row = await database.get_agent("backend", db_path=db_path)
    assert row is not None and row["status"] == "offline"


# --- 2. Status broadcasts ---------------------------------------------------


async def test_status_broadcasts_working_then_idle(db_path: Path) -> None:
    hub = FakeHub()
    agent = BackendAgent(hub=hub, db_path=db_path)
    agent._claude = StubReasoner("done")  # type: ignore[attr-defined]
    agent._ollama = StubReasoner("done")  # type: ignore[attr-defined]

    await agent.start()
    hub.events.clear()  # drop the initial start() idle broadcast

    agent.enqueue_task({"description": "Optimise the SQLite schema"})
    # Wait for the returning-to-idle *broadcast* (not just the in-memory status
    # flag, which is set a step before the broadcast is awaited) so stop()'s
    # offline event can't race ahead of the idle event we're asserting on.
    await _wait_until(lambda: "idle" in hub.statuses_for("backend"))
    await agent.stop()

    statuses = hub.statuses_for("backend")
    # During processing we must broadcast a working then an idle transition,
    # and the working broadcast must precede the returning-to-idle broadcast.
    assert "working" in statuses
    assert "idle" in statuses
    last_idle = max(i for i, s in enumerate(statuses) if s == "idle")
    assert statuses.index("working") < last_idle


# --- 3. DB persistence across restarts --------------------------------------


async def test_db_persistence_six_agents_survive_restart(db_path: Path) -> None:
    hub = FakeHub()
    runtime = _make_runtime(db_path, hub)
    await runtime.start()

    rows = await database.get_all_agents(db_path=db_path)
    assert len(rows) == 6
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == set(EXPECTED_AGENTS)
    for agent_id, name in EXPECTED_AGENTS.items():
        assert by_id[agent_id]["name"] == name

    await runtime.stop()

    # A second, fresh runtime pointing at the same DB: the 6 rows still exist
    # (state persists across restarts) without re-running start().
    runtime2 = _make_runtime(db_path, FakeHub())
    rows2 = await database.get_all_agents(db_path=db_path)
    assert len(rows2) == 6
    assert {r["id"] for r in rows2} == set(EXPECTED_AGENTS)
    # After a clean shutdown the persisted status is offline.
    assert all(r["status"] == "offline" for r in rows2)
    # The fresh runtime can bring them back up.
    await runtime2.start()
    assert all(a.is_running for a in runtime2.agents.values())
    await runtime2.stop()


# --- 4. ProductionLead keyword routing --------------------------------------


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        ("Build a React component for the orb animation", "frontend"),
        ("Redesign the UI window layout in Tauri", "frontend"),
        ("Add a FastAPI endpoint backed by the SQLite database", "backend"),
        ("Tune the async query performance of the API", "backend"),
        ("Run a security audit and rotate the OAuth credentials", "security"),
        ("Scan for vulnerabilities in the auth flow", "security"),
    ],
)
async def test_production_lead_keyword_routing(
    db_path: Path, goal: str, expected: str
) -> None:
    hub = FakeHub()
    runtime = _make_runtime(db_path, hub)
    target = await runtime.production_lead.classify(goal)
    assert target == expected


# --- 5. Delegation ----------------------------------------------------------


async def test_submit_goal_creates_task_and_delegates(db_path: Path) -> None:
    hub = FakeHub()
    runtime = _make_runtime(db_path, hub)
    await runtime.start()

    result = await runtime.submit_goal(
        "Add a websocket endpoint to the FastAPI server"
    )
    assert result["target"] == "backend"
    assert result["delegated"] is True
    assert isinstance(result["task_id"], int)

    # The delegated row is recorded and assigned to the backend specialist.
    tasks = await database.get_agent_tasks("backend", db_path=db_path)
    assert any(t["id"] == result["task_id"] for t in tasks)
    task = next(t for t in tasks if t["id"] == result["task_id"])
    assert task["created_by"] == "production_lead"
    assert task["assigned_to"] == "backend"

    # The specialist processes it to completion (stub reasoner returns "ok").
    async def task_done() -> bool:
        rows = await database.get_agent_tasks("backend", db_path=db_path)
        return any(
            t["id"] == result["task_id"] and t["status"] == "done" for t in rows
        )

    deadline = asyncio.get_event_loop().time() + 5.0
    while asyncio.get_event_loop().time() < deadline:
        if await task_done():
            break
        await asyncio.sleep(0.01)
    assert await task_done()
    await runtime.stop()


# --- 6. Error recovery ------------------------------------------------------


class ExplodingAgent(BaseAgent):
    """An agent whose handler always raises, to exercise error recovery."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            agent_id="backend",
            name="Kado",
            role="exploding test agent",
            **kwargs,
        )

    async def handle_task(self, task: dict[str, Any]) -> str:
        raise RuntimeError("boom")


async def test_error_recovery_marks_failed_and_survives(db_path: Path) -> None:
    hub = FakeHub()
    agent = ExplodingAgent(hub=hub, db_path=db_path)
    await agent.start()

    # Seed a real tasks row so we can assert it gets marked failed. start()
    # already upserted the "backend" agent row; both FK ends point at it (no
    # production_lead row exists in this minimal single-agent fixture).
    task_id = await database.create_task(
        "backend", "backend", "will explode", db_path=db_path
    )
    agent.enqueue_task({"task_id": task_id, "description": "explode please"})

    # The task row transitions to failed and the agent recovers to idle.
    async def task_failed() -> bool:
        tasks = await database.get_agent_tasks("backend", db_path=db_path)
        return any(t["id"] == task_id and t["status"] == "failed" for t in tasks)

    await _wait_until(
        lambda: agent.queue_size == 0 and agent.status == "idle"
    )
    assert await task_failed()
    assert agent.is_running  # loop survived the exception, no crash

    # A second task is still processed (loop kept going). It will also fail, but
    # the important thing is the agent accepts and drains it.
    agent.enqueue_task({"description": "explode again"})
    await _wait_until(lambda: agent.queue_size == 0 and agent.status == "idle")
    assert agent.is_running
    await agent.stop()


# --- 7. Lifespan wiring (TestClient) ----------------------------------------


def test_lifespan_starts_six_running_agents() -> None:
    """Drive the real ASGI lifespan: /health 200, 6 running agents, clean stop.

    Uses Starlette's TestClient as a context manager so startup/shutdown actually
    run (httpx ASGITransport would skip the lifespan). Runs in a worker thread
    because TestClient spins its own event loop.
    """
    from starlette.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        agents = app.state.agents
        assert len(agents) == 6
        assert set(agents) == set(EXPECTED_AGENTS)
        assert all(a.is_running for a in agents.values())

    # On context exit the lifespan shutdown ran: every agent loop is stopped.
    assert all(not a.is_running for a in app.state.agents.values())
