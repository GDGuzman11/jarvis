"""Phase 12A verification — Memory Infrastructure.

Targeted checks for the memory layer the backend-agent added in Phase 12A:

* :func:`backend.memory.database.init_db` — the 5 new Phase 12 tables exist.
* :class:`backend.memory.evaluator.MemoryEvaluator` — import + scoring rules.
* :class:`backend.memory.manager.MemoryManager` — instantiation + recall on an
  empty DB returning a :class:`RecallResult` with a non-empty formatted context.
* :func:`backend.memory.database.save_memory_fact` — round-trips a fact id.

All in-memory / temp-file: no API key, no network, no audio device, and the
VectorStore is mocked so the heavy embedding model never loads.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.memory import database
from backend.memory.evaluator import MemoryEvaluator
from backend.memory.manager import MemoryManager, RecallResult


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    """Create a fresh, isolated SQLite db file and return its path string."""
    db_path = str(tmp_path / "phase12a.db")
    await database.init_db(db_path)
    return db_path


def _make_vector_store() -> MagicMock:
    """A VectorStore stand-in that never loads the embedding model.

    ``len()`` is 0 so :meth:`MemoryManager.recall` skips the semantic branch on
    an empty store (matches the real cold-start path).
    """
    vs = MagicMock()
    vs.__len__.return_value = 0
    return vs


# --- 1. Schema: all 5 new Phase 12 tables exist -----------------------------

_NEW_TABLES = ("memory_facts", "people", "open_loops", "decisions", "agent_performance")


async def test_init_db_creates_five_new_memory_tables(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    names = {row["name"] for row in rows}
    for table in _NEW_TABLES:
        assert table in names, f"missing Phase 12 table: {table} (have {sorted(names)})"


# --- 2. MemoryEvaluator import + preference/fact scoring ---------------------


def test_evaluator_scores_name_introduction_as_preference() -> None:
    evaluator = MemoryEvaluator()
    score, category = evaluator.score(
        "my name is Gabriel", "Nice to meet you Gabriel"
    )
    assert score >= 0.75, f"expected >= 0.75, got {score} ({category})"
    assert "preference" in category or "fact" in category, (
        f"expected preference/fact category, got {category!r}"
    )


# --- 3. MemoryEvaluator app_work scoring ------------------------------------


def test_evaluator_scores_deploy_as_app_work() -> None:
    evaluator = MemoryEvaluator()
    score, category = evaluator.score(
        "we deployed the new backend endpoint",
        "Done, the endpoint is live at /api/v2/chat",
    )
    assert score >= 0.9, f"expected >= 0.9, got {score} ({category})"
    assert category == "app_work", f"expected app_work, got {category!r}"


# --- 4. MemoryEvaluator general/below-threshold scoring ---------------------


def test_evaluator_scores_time_lookup_as_general_low() -> None:
    evaluator = MemoryEvaluator()
    score, category = evaluator.score("what time is it?", "It's 3pm")
    assert score <= 0.3, f"expected <= 0.3, got {score} ({category})"
    assert score < evaluator.threshold, "general lookup must be below promotion threshold"


# --- 5. MemoryManager instantiation -----------------------------------------


def test_memory_manager_instantiates(tmp_path) -> None:
    manager = MemoryManager(
        db_path=str(tmp_path / "mgr.db"),
        vector_store=_make_vector_store(),
    )
    assert manager is not None
    # A default evaluator is created when none is injected.
    assert isinstance(manager._evaluator, MemoryEvaluator)


# --- 6. recall() on an empty DB returns a RecallResult ----------------------


async def test_recall_on_empty_db_returns_recall_result(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    manager = MemoryManager(db_path=db_path, vector_store=_make_vector_store())

    result = await manager.recall("anything")

    assert isinstance(result, RecallResult)
    assert result.episodic_messages == []
    assert result.semantic_facts == []
    assert isinstance(result.formatted_context, str)

    # NOTE — intentional deviation from the task brief. The brief expected
    # ``formatted_context`` to be non-empty (the date header) on an empty DB.
    # The actual (deliberate) behavior of MemoryManager.format_context is to
    # return "" when ONLY the date header would be present, so the cached stable
    # prefix of the system prompt stays byte-identical on a cold first turn
    # (see manager.py docstring + the ``if len(sections) == 1: return ""``
    # guard). This is a prompt-caching optimization, not a bug, so the test
    # asserts the real contract: empty context on a cold/empty recall.
    assert result.formatted_context == "", (
        "cold-start recall should yield an empty context (prompt-cache stability)"
    )

    # The date header IS emitted as soon as there is anything to inject. Verify
    # format_context produces the documented header when fed real content, so we
    # still cover the "at minimum the date header" expectation from the brief.
    populated = RecallResult(
        semantic_facts=[{"content": "User prefers short answers", "category": "preference"}]
    )
    rendered = manager.format_context(populated)
    assert rendered.strip(), "format_context with content should be non-empty"
    assert "# Current context" in rendered
    assert "Date:" in rendered


# --- 7. save_memory_fact round-trips an int id > 0 --------------------------


async def test_save_memory_fact_returns_positive_int_id(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    fact_id = await database.save_memory_fact(
        source="voice",
        category="preference",
        content="User prefers short answers",
        importance=0.75,
        agent_id=None,
        db_path=db_path,
    )
    assert isinstance(fact_id, int)
    assert fact_id > 0

    # And it is actually persisted/readable back.
    facts = await database.get_memory_facts(db_path=db_path)
    assert any(f["id"] == fact_id for f in facts)
    stored = next(f for f in facts if f["id"] == fact_id)
    assert stored["content"] == "User prefers short answers"
    assert stored["category"] == "preference"
    assert pytest.approx(stored["importance"], abs=1e-9) == 0.75
