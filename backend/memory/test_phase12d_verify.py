"""Phase 12D verification — Memory Intelligence.

Targeted checks for the intelligence layer the backend-agent added in Phase 12D:

* :meth:`MemoryEvaluator.detect_open_loops` — promise/reminder/follow-up
  detection (positive / negative / multiple).
* :meth:`MemoryEvaluator.extract_person` — named-contact + email extraction.
* :meth:`MemoryEvaluator.score` / :meth:`extract_fact` — failure category.
* :meth:`MemoryManager.consolidate` — fires the open-loop side effect.
* :func:`backend.memory.database.get_open_loops` — ``older_than_hours`` filter.
* :mod:`backend.main` — ``_consolidation_loop`` defined + ``_startup_greeting``
  accepts ``memory_manager``.

All in-memory / temp-file: no API key, no network, no audio device, and the
VectorStore is mocked so the heavy embedding model never loads.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from backend.memory import database
from backend.memory.evaluator import MemoryEvaluator
from backend.memory.manager import MemoryManager


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    """Create a fresh, isolated SQLite db file and return its path string."""
    db_path = str(tmp_path / "phase12d.db")
    await database.init_db(db_path)
    return db_path


def _make_vector_store() -> MagicMock:
    """A VectorStore stand-in that never loads the embedding model."""
    vs = MagicMock()
    vs.__len__.return_value = 0
    return vs


async def _poll(pred, *, timeout: float = 2.0, interval: float = 0.02):
    """Await ``pred`` (async) until it returns truthy or ``timeout`` elapses."""
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        result = await pred()
        if result:
            return result
        await asyncio.sleep(interval)
    return await pred()


# --- 1. Open loop detection — positive --------------------------------------


def test_detect_open_loops_positive() -> None:
    ev = MemoryEvaluator()
    loops = ev.detect_open_loops("remind me to follow up with Maria tomorrow")
    assert isinstance(loops, list)
    assert len(loops) >= 1
    assert any("follow up with maria" in loop.lower() for loop in loops), loops


# --- 2. Open loop detection — negative --------------------------------------


def test_detect_open_loops_negative() -> None:
    ev = MemoryEvaluator()
    assert ev.detect_open_loops("what time is it?") == []


# --- 3. Open loop detection — multiple --------------------------------------


def test_detect_open_loops_multiple() -> None:
    ev = MemoryEvaluator()
    loops = ev.detect_open_loops(
        "I need to update the readme and don't forget to check the logs"
    )
    assert isinstance(loops, list)
    assert len(loops) == 2, loops


# --- 4. Person extraction — email present -----------------------------------


def test_extract_person_with_email() -> None:
    ev = MemoryEvaluator()
    person = ev.extract_person("got an email from Sarah at sarah@example.com")
    assert person is not None
    assert person["name"] == "Sarah"
    assert person["email"] == "sarah@example.com"


# --- 5. Person extraction — no person ---------------------------------------


def test_extract_person_none() -> None:
    ev = MemoryEvaluator()
    assert ev.extract_person("what time is it?") is None


# --- 6. Failure scoring -----------------------------------------------------


def test_failure_scoring() -> None:
    ev = MemoryEvaluator()
    score, category = ev.score(
        "we tried using Redis but it conflicted with the audio pipeline",
        "Understood, reverting.",
    )
    assert score >= 0.85, (score, category)
    assert category == "failure", (score, category)


# --- 7. Failure fact extraction ---------------------------------------------


def test_failure_fact_extraction() -> None:
    ev = MemoryEvaluator()
    user = "we tried Redis but it conflicted with the audio pipeline"
    reply = "Understood, reverting."
    fact = ev.extract_fact(user, reply, "failure")
    assert "failed" in fact.lower(), fact


# --- 8. Open loop saved via consolidate -------------------------------------


async def test_consolidate_saves_open_loop(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    manager = MemoryManager(db_path=db_path, vector_store=_make_vector_store())

    await manager.consolidate(
        "remind me to call the client tomorrow", "Sure, I'll remind you."
    )

    async def _has_open_loop() -> bool:
        rows = await database.get_open_loops("open", db_path=db_path)
        return len(rows) >= 1

    assert await _poll(_has_open_loop), "no open_loops row with status='open' appeared"


# --- 9. get_open_loops older_than_hours filter ------------------------------


async def test_get_open_loops_older_than_hours(tmp_path) -> None:
    db_path = await _make_db(tmp_path)

    # Seed one open loop whose created_at is 25 hours in the past.
    conn = await database.connect(db_path)
    try:
        await conn.execute(
            "INSERT INTO open_loops (description, source, status, created_at) "
            "VALUES (?, ?, 'open', datetime('now', '-25 hours'))",
            ("call the client", "voice"),
        )
        await conn.commit()
    finally:
        await conn.close()

    # 24h threshold: the 25h-old row qualifies.
    older_24 = await database.get_open_loops(
        status="open", older_than_hours=24, db_path=db_path
    )
    assert len(older_24) == 1, older_24

    # 26h threshold: the 25h-old row is too recent -> excluded.
    older_26 = await database.get_open_loops(
        status="open", older_than_hours=26, db_path=db_path
    )
    assert older_26 == [], older_26


# --- 10. Consolidation loop in lifespan -------------------------------------


def test_main_consolidation_loop_and_greeting_signature() -> None:
    from backend import main

    assert hasattr(main, "_consolidation_loop")
    assert inspect.iscoroutinefunction(main._consolidation_loop)

    sig = inspect.signature(main._startup_greeting)
    assert "memory_manager" in sig.parameters
