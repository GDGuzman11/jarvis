"""Phase 10 verification — agent rename endpoint (POST /api/agents/{id}/rename).

Drives the live FastAPI route via Starlette's ``TestClient`` with the DB write
(``main.rename_agent``) and the WebSocket fan-out (``main.hub.broadcast``)
patched, so the test exercises only the endpoint's validation, persistence
call, live-agent mutation, and broadcast — no real SQLite or sockets.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.events import AgentUpdate


def _seed_agent() -> SimpleNamespace:
    """A stand-in live agent matching the attributes the endpoint reads."""
    return SimpleNamespace(
        id="backend",
        name="Kado",
        status="idle",
        _current_task_label=None,
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    """TestClient with a seeded agent and patched DB + hub.

    The ``TestClient`` is deliberately NOT used as a context manager: entering
    it would run the full app lifespan (DB init, voice pipeline, agent runtime,
    Slack/Gmail startup) which is heavy and would overwrite the seeded
    ``app.state.agents`` with the real runtime roster. Skipping the lifespan
    isolates the endpoint's own logic.

    ``rename_agent`` is patched to report a successful row update without
    touching SQLite; ``hub.broadcast`` is replaced with an AsyncMock so we can
    assert on the emitted event.
    """
    agent = _seed_agent()
    main.app.state.agents = {"backend": agent}

    rename_mock = AsyncMock(return_value=True)
    broadcast_mock = AsyncMock()
    monkeypatch.setattr(main, "rename_agent", rename_mock)
    monkeypatch.setattr(main.hub, "broadcast", broadcast_mock)

    c = TestClient(main.app)
    # Expose the mocks + live agent to the test body.
    c.rename_mock = rename_mock  # type: ignore[attr-defined]
    c.broadcast_mock = broadcast_mock  # type: ignore[attr-defined]
    c.agent = agent  # type: ignore[attr-defined]
    yield c

    main.app.state.agents = {}


def test_rename_success_returns_200_and_new_name(client) -> None:
    resp = client.post("/api/agents/backend/rename", json={"name": "Kado Prime"})

    assert resp.status_code == 200
    assert resp.json() == {"agent_id": "backend", "name": "Kado Prime"}
    # The live in-memory agent must carry the new name for later broadcasts.
    assert client.agent.name == "Kado Prime"
    # Persistence was attempted with the trimmed name.
    client.rename_mock.assert_awaited_once_with("backend", "Kado Prime")


def test_rename_success_broadcasts_agent_update(client) -> None:
    client.post("/api/agents/backend/rename", json={"name": "Kado Prime"})

    client.broadcast_mock.assert_awaited_once()
    event = client.broadcast_mock.await_args.args[0]
    assert isinstance(event, AgentUpdate)
    assert event.agent_id == "backend"
    assert event.agent_name == "Kado Prime"
    assert event.status == "idle"
    assert event.type == "agent_update"


def test_rename_unknown_agent_returns_404(client) -> None:
    resp = client.post("/api/agents/nope/rename", json={"name": "X"})

    assert resp.status_code == 404
    # No DB write and no broadcast for an unknown agent.
    client.rename_mock.assert_not_awaited()
    client.broadcast_mock.assert_not_awaited()


def test_rename_empty_after_strip_returns_400(client) -> None:
    resp = client.post("/api/agents/backend/rename", json={"name": "   "})

    assert resp.status_code == 400
    client.rename_mock.assert_not_awaited()
    client.broadcast_mock.assert_not_awaited()
    # Live agent name unchanged.
    assert client.agent.name == "Kado"


def test_rename_too_long_returns_400(client) -> None:
    resp = client.post("/api/agents/backend/rename", json={"name": "x" * 51})

    assert resp.status_code == 400
    client.rename_mock.assert_not_awaited()
    client.broadcast_mock.assert_not_awaited()
    assert client.agent.name == "Kado"


def test_rename_max_length_boundary_succeeds(client) -> None:
    """Exactly 50 chars (MAX_AGENT_NAME_LEN) is accepted — boundary check."""
    name = "x" * 50
    resp = client.post("/api/agents/backend/rename", json={"name": name})

    assert resp.status_code == 200
    assert resp.json()["name"] == name
