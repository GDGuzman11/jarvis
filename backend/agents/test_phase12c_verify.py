"""Phase 12C verification — persistent memory wired into all 6 agents.

Targeted tests for the Phase 12C change set:

* ``BaseAgent._remember`` checkpoints each exchange to the ``conversations`` table
  under the agent's ``channel='agent:<id>'`` (only when no MemoryManager owns the
  episodic write).
* ``BaseAgent.start`` restores the agent's last persisted turns into the rolling
  ``self._context`` (and is a graceful no-op on an empty DB).
* ``BaseAgent.reason`` recalls shared memory *before* the Claude call (recalled
  episodic message first, then rolling context, then the new prompt) and stores +
  fire-and-forget consolidates *after*.
* ``ProductionLead._delegate`` writes a ``decisions`` row.
* Each specialist writes an ``agent_performance`` row on task completion.

All tests use a temp SQLite DB plus stub reasoners / a fake MemoryManager — no
real API keys, network, FAISS, or shared on-disk state.

Run with:
    .venv\\Scripts\\python.exe -m pytest backend/agents/test_phase12c_verify.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from backend.agents.backend_agent import BackendAgent
from backend.agents.base_agent import BaseAgent
from backend.agents.production_lead import ProductionLead
from backend.memory import database
from backend.memory.manager import RecallResult


# --- Test doubles -----------------------------------------------------------


class FakeHub:
    """Swallows AgentUpdate broadcasts so status transitions don't need a hub."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def broadcast(self, event: Any) -> int:
        self.events.append(event)
        return 1


class StubReasoner:
    """Stand-in Claude/Ollama client that streams a canned reply, no network."""

    def __init__(self, reply: str = "ok") -> None:
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    async def stream_response(self, messages, system_prompt):  # noqa: ANN001
        # Capture a copy — the agent reuses/extends the messages list.
        self.calls.append(
            {"messages": list(messages), "system_prompt": system_prompt}
        )
        yield self._reply


class FakeMemoryManager:
    """Records recall/store/consolidate/store_fact — the surface agents call.

    ``recall`` returns the injected :class:`RecallResult`; the rest record their
    calls so tests can assert on count and ordering without a real DB/FAISS.
    """

    def __init__(self, recall_result: RecallResult | None = None) -> None:
        self._recall_result = recall_result or RecallResult()
        self.recall_calls: list[dict[str, Any]] = []
        self.store_calls: list[dict[str, Any]] = []
        self.consolidate_calls: list[dict[str, Any]] = []
        self.store_fact_calls: list[dict[str, Any]] = []

    async def recall(self, query, n_recent=10, n_semantic=3):  # noqa: ANN001
        self.recall_calls.append(
            {"query": query, "n_recent": n_recent, "n_semantic": n_semantic}
        )
        return self._recall_result

    async def store(self, text, role, channel="voice", metadata=None):  # noqa: ANN001
        self.store_calls.append({"text": text, "role": role, "channel": channel})
        return len(self.store_calls)

    async def consolidate(self, user_text, reply, *, source="voice", agent_id=None):  # noqa: ANN001
        self.consolidate_calls.append(
            {"user_text": user_text, "reply": reply, "agent_id": agent_id}
        )
        return None

    async def store_fact(self, content, **kwargs):  # noqa: ANN001
        self.store_fact_calls.append({"content": content, **kwargs})
        return len(self.store_fact_calls)


class _MinimalAgent(BaseAgent):
    """Concrete BaseAgent with a trivial handler, for direct unit tests."""

    def __init__(self, agent_id: str = "test", **kwargs: Any) -> None:
        super().__init__(
            agent_id=agent_id,
            name=agent_id.title(),
            role="test agent",
            **kwargs,
        )

    async def handle_task(self, task: dict[str, Any]) -> str:
        return await self.reason(task.get("description", ""))


@pytest.fixture()
async def db_path(tmp_path: Path) -> Path:
    """A fresh, fully-migrated temp database for one test."""
    path = tmp_path / "jarvis.db"
    await database.init_db(path)
    return path


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    """Poll an async predicate until true or raise TimeoutError (no fixed sleeps)."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("condition not met within timeout")


async def _conversations(db_path: Path, channel: str) -> list[dict[str, Any]]:
    return await database.get_recent_conversations(
        limit=100, channel=channel, db_path=db_path
    )


# --- 1. Context checkpoint --------------------------------------------------


async def test_remember_checkpoints_conversation(db_path: Path) -> None:
    """``_remember`` persists user + jarvis turns under ``channel='agent:<id>'``.

    The checkpoint is fire-and-forget (``asyncio.create_task``), so we poll the
    DB until both rows land rather than asserting synchronously.
    """
    hub = FakeHub()
    # No memory_manager => _remember owns the checkpoint and writes to the DB.
    agent = _MinimalAgent(agent_id="test", hub=hub, db_path=db_path)

    agent._remember("hello", "world")

    async def both_rows() -> bool:
        return len(await _conversations(db_path, "agent:test")) == 2

    await _wait_until(both_rows)

    rows = await _conversations(db_path, "agent:test")
    by_role = {r["role"]: r for r in rows}
    assert set(by_role) == {"user", "jarvis"}
    assert by_role["user"]["content"] == "hello"
    assert by_role["jarvis"]["content"] == "world"
    # Every checkpoint row carries this agent's channel.
    assert all(r["channel"] == "agent:test" for r in rows)


# --- 2. Context restore -----------------------------------------------------


async def test_start_restores_context_from_db(db_path: Path) -> None:
    """``start`` reloads the agent's last persisted turns into ``self._context``.

    Seed four conversation rows for ``channel='agent:test'`` (oldest-first), then
    a fresh agent's ``start()`` must rebuild a 4-entry context in message shape:
    ``user`` rows -> ``user``, ``jarvis`` rows -> ``assistant``, in order.
    """
    seeded = [
        ("user", "first question"),
        ("jarvis", "first answer"),
        ("user", "second question"),
        ("jarvis", "second answer"),
    ]
    for role, content in seeded:
        await database.save_conversation(
            role, content, channel="agent:test", db_path=db_path
        )

    hub = FakeHub()
    agent = _MinimalAgent(agent_id="test", hub=hub, db_path=db_path)
    await agent.start()
    try:
        assert len(agent._context) == 4, agent._context
        expected = [
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user", "content": "second question"},
            {"role": "assistant", "content": "second answer"},
        ]
        assert agent._context == expected
    finally:
        await agent.stop()


# --- 3. Context restore on an empty DB --------------------------------------


async def test_start_empty_db_leaves_context_empty(db_path: Path) -> None:
    """A fresh agent on an empty DB restores nothing and does not crash."""
    hub = FakeHub()
    agent = _MinimalAgent(agent_id="test", hub=hub, db_path=db_path)
    await agent.start()
    try:
        assert agent._context == []
    finally:
        await agent.stop()


# --- 4. Memory recall in reason() -------------------------------------------


async def test_reason_prepends_recalled_then_context_then_prompt(
    db_path: Path,
) -> None:
    """``reason`` orders messages: recalled episodic, rolling context, new prompt."""
    hub = FakeHub()
    claude = StubReasoner("the answer")
    mm = FakeMemoryManager(
        recall_result=RecallResult(
            episodic_messages=[{"role": "user", "content": "recalled turn"}],
            formatted_context="# Current context\nDate: now",
        )
    )
    agent = _MinimalAgent(
        agent_id="test", hub=hub, db_path=db_path, memory_manager=mm
    )
    agent._claude = claude  # type: ignore[attr-defined]
    # Pre-seed some rolling context so we can prove ordering between the three.
    agent._context = [{"role": "assistant", "content": "earlier reply"}]

    await agent.reason("what did we discuss?")

    assert mm.recall_calls, "recall was never called"
    assert claude.calls, "Claude stream_response never called"
    sent = claude.calls[0]["messages"]
    assert sent == [
        {"role": "user", "content": "recalled turn"},
        {"role": "assistant", "content": "earlier reply"},
        {"role": "user", "content": "what did we discuss?"},
    ], sent


# --- 5. Store after reason() ------------------------------------------------


async def test_reason_stores_twice_and_consolidates_async(db_path: Path) -> None:
    """``reason`` stores user + jarvis and fire-and-forgets consolidation.

    ``consolidate`` is scheduled via ``asyncio.create_task`` (not awaited inline),
    so it may not have run by the time ``reason`` returns — we yield the loop and
    poll for it rather than asserting synchronously.
    """
    hub = FakeHub()
    claude = StubReasoner("a reply")
    mm = FakeMemoryManager()
    agent = _MinimalAgent(
        agent_id="test", hub=hub, db_path=db_path, memory_manager=mm
    )
    agent._claude = claude  # type: ignore[attr-defined]

    await agent.reason("test prompt")

    # store() ran twice: once for the user prompt, once for the jarvis reply.
    assert len(mm.store_calls) == 2, mm.store_calls
    assert [c["role"] for c in mm.store_calls] == ["user", "jarvis"]
    assert mm.store_calls[0]["text"] == "test prompt"
    assert mm.store_calls[1]["text"] == "a reply"
    assert all(c["channel"] == "agent:test" for c in mm.store_calls)

    # consolidate was create_task'd — let the scheduled task run, then assert.
    async def consolidated() -> bool:
        return bool(mm.consolidate_calls)

    await _wait_until(consolidated)
    assert mm.consolidate_calls[0]["user_text"] == "test prompt"
    assert mm.consolidate_calls[0]["reply"] == "a reply"
    assert mm.consolidate_calls[0]["agent_id"] == "test"


# --- 6. Production lead writes a decisions row ------------------------------


async def test_production_lead_writes_decision(db_path: Path) -> None:
    """Delegating a goal records a ``decisions`` row for ``production_lead``.

    The decision write is fire-and-forget, so poll the table. A wired-in
    MemoryManager is required (the write is gated on it). The lead's own agent row
    must exist first because ``_set_status``/audit and the decisions FK reference
    it — ``start()`` upserts it.
    """
    hub = FakeHub()
    claude = StubReasoner("backend")
    mm = FakeMemoryManager()
    lead = ProductionLead(
        agents={}, hub=hub, db_path=db_path, memory_manager=mm
    )
    lead._claude = claude  # type: ignore[attr-defined]
    await lead.start()  # seeds the production_lead agent row (FK target)
    # The goal routes to "backend"; its row must exist for the tasks FK
    # (created_by=production_lead, assigned_to=backend) to satisfy.
    await database.upsert_agent("backend", "Kado", "idle", role="backend", db_path=db_path)
    try:
        await lead.handle_task({"description": "Build a new API endpoint"})

        async def has_decision() -> bool:
            # decisions has no dedicated reader; query the table directly.
            conn = await database.connect(db_path)
            try:
                cur = await conn.execute(
                    "SELECT agent_id FROM decisions WHERE agent_id = ?",
                    ("production_lead",),
                )
                found = await cur.fetchall()
            finally:
                await conn.close()
            return len(found) >= 1

        await _wait_until(has_decision)
    finally:
        await lead.stop()


# --- 7. Specialist writes an agent_performance row --------------------------


async def test_specialist_writes_agent_performance(db_path: Path) -> None:
    """A completed specialist task records an ``agent_performance`` row.

    ``agent_performance.agent_id`` is a NOT NULL FK into ``agents``, so the
    specialist's row must exist first — ``start()`` upserts it. The write is
    fire-and-forget, so poll for it.
    """
    hub = FakeHub()
    claude = StubReasoner("backend guidance")
    mm = FakeMemoryManager()
    agent = BackendAgent(hub=hub, db_path=db_path, memory_manager=mm)
    agent._claude = claude  # type: ignore[attr-defined]
    await agent.start()  # seeds the backend agent row (FK target)
    try:
        await agent.handle_task({"description": "fix a bug"})

        async def has_performance() -> bool:
            conn = await database.connect(db_path)
            try:
                cur = await conn.execute(
                    "SELECT agent_id, outcome FROM agent_performance "
                    "WHERE agent_id = ?",
                    ("backend",),
                )
                rows = await cur.fetchall()
            finally:
                await conn.close()
            return any(
                r["outcome"] in ("success", "failed") for r in rows
            )

        await _wait_until(has_performance)
    finally:
        await agent.stop()
