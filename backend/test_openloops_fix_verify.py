"""Verification — open-loop (reminder) resolution + randomized startup greeting.

Targeted checks for the open-loop bug fix and the greeting change:

1. ``database.resolve_open_loops_async`` flips an open loop's ``status`` and
   stamps ``resolved_at`` — by id, by "all open", and via the ``dismissed``
   status; an empty id list is a no-op; an out-of-CHECK status raises.
2. A "remove/forget that reminder" turn RESOLVES the matching open loop via the
   LLM-judged path and does NOT create a new one (the core bug).
3. A genuine reminder still creates one clean open loop.
4. Idle chatter never reaches the LLM (the keyword pre-filter gates it), and a
   non-genuine "need to" fragment that *does* reach the LLM is rejected (NOOP)
   so no garbage loop is stored — the over-eager-detection fix.
5. The startup greeting text varies across launches (mock the LLM) and still
   appends overdue reminders — and no longer surfaces resolved loops.

All in-memory / temp-file: the LLM clients are lightweight fakes and the vector
store is mocked, so there is no API key, no network, and no embedding model load.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend import main
from backend.memory import database
from backend.memory.evaluator import MemoryEvaluator
from backend.memory.extractor import OpenLoopOp
from backend.memory.manager import MemoryManager


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "openloops.db")
    await database.init_db(db_path)
    return db_path


def _vs() -> MagicMock:
    """VectorStore stand-in that never loads the embedding model."""
    vs = MagicMock()
    vs.__len__.return_value = 0
    return vs


async def _count_loops(db_path: str) -> int:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute("SELECT COUNT(*) AS n FROM open_loops")
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return int(row["n"])


async def _insert_overdue_loop(db_path: str, description: str) -> int:
    """Insert an open loop whose created_at is 25 h in the past (overdue > 12 h)."""
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute(
            "INSERT INTO open_loops (description, source, status, created_at) "
            "VALUES (?, 'voice', 'open', datetime('now', '-25 hours'))",
            (description,),
        )
        await conn.commit()
        return int(cursor.lastrowid)
    finally:
        await conn.close()


class _ScriptedExtractor:
    """Fake combined extractor: no facts, scripted open-loop operations.

    ``mode`` drives :meth:`extract_open_loops`:
      * ``"create"``       — return one CREATE with a clean description.
      * ``"resolve_first"`` — RESOLVE the first existing open loop by id.
      * ``"noop"``         — return nothing (the LLM judged it not a reminder).
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.loop_calls: list[tuple[str, str, list[dict]]] = []

    async def extract(self, user_text, reply):  # fact extraction — unused here
        return []

    async def extract_open_loops(self, user_text, reply, open_loops):
        self.loop_calls.append((user_text, reply, list(open_loops)))
        if self.mode == "create":
            return [OpenLoopOp("CREATE", "call the dentist on Friday", None, 0.95)]
        if self.mode == "resolve_first" and open_loops:
            return [OpenLoopOp("RESOLVE", "", int(open_loops[0]["id"]), 0.95)]
        return []


class _EchoClient:
    """Greeting client whose stream echoes the (randomized) instruction back."""

    async def stream_response(self, messages, system_prompt):
        for token in messages[0]["content"].split():
            yield token + " "


# --- 1. resolve_open_loops_async --------------------------------------------


async def test_resolve_by_ids_flips_status_and_timestamp(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    a = await database.save_open_loop("loop A", db_path=db_path)
    b = await database.save_open_loop("loop B", db_path=db_path)

    n = await database.resolve_open_loops_async(
        db_path=db_path, ids=[a], status="resolved"
    )
    assert n == 1

    resolved = {r["id"]: r for r in await database.get_open_loops(
        "resolved", db_path=db_path
    )}
    assert a in resolved
    assert resolved[a]["resolved_at"] is not None, "resolved_at must be stamped"

    still_open = [r["id"] for r in await database.get_open_loops(
        "open", db_path=db_path
    )]
    assert still_open == [b], "only the targeted loop should be closed out"


async def test_resolve_all_open_with_dismissed_status(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    for desc in ("one", "two", "three"):
        await database.save_open_loop(desc, db_path=db_path)

    n = await database.resolve_open_loops_async(
        db_path=db_path, ids=None, status="dismissed"
    )
    assert n == 3

    assert await database.get_open_loops("open", db_path=db_path) == []
    dismissed = await database.get_open_loops("dismissed", db_path=db_path)
    assert len(dismissed) == 3
    assert all(r["resolved_at"] is not None for r in dismissed)


async def test_resolve_empty_ids_is_noop(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    await database.save_open_loop("keep me open", db_path=db_path)

    n = await database.resolve_open_loops_async(
        db_path=db_path, ids=[], status="resolved"
    )
    assert n == 0
    assert len(await database.get_open_loops("open", db_path=db_path)) == 1


async def test_resolve_invalid_status_raises(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    with pytest.raises(ValueError):
        await database.resolve_open_loops_async(
            db_path=db_path, ids=[1], status="open"
        )


# --- 2. "forget that reminder" RESOLVES and does not re-create ---------------


async def test_remove_reminder_resolves_and_does_not_create(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    await database.save_open_loop(
        "call the dentist next week", db_path=db_path
    )
    ext = _ScriptedExtractor("resolve_first")
    mgr = MemoryManager(
        db_path=db_path, vector_store=_vs(),
        evaluator=MemoryEvaluator(), extractor=ext,
    )

    await mgr.consolidate(
        "actually forget that reminder about the dentist", "Done, sir."
    )

    assert ext.loop_calls, "resolution intent must reach the LLM judge"
    assert await database.get_open_loops("open", db_path=db_path) == [], (
        "the matching loop must be closed out"
    )
    resolved = await database.get_open_loops("resolved", db_path=db_path)
    assert len(resolved) == 1 and resolved[0]["resolved_at"] is not None
    assert await _count_loops(db_path) == 1, "must NOT create a new loop"


# --- 3. Genuine reminder still creates one clean loop ------------------------


async def test_genuine_reminder_creates_clean_loop(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    ext = _ScriptedExtractor("create")
    mgr = MemoryManager(
        db_path=db_path, vector_store=_vs(),
        evaluator=MemoryEvaluator(), extractor=ext,
    )

    await mgr.consolidate("remind me to call the dentist on Friday", "Will do.")

    assert ext.loop_calls, "a genuine reminder must reach the LLM judge"
    open_rows = await database.get_open_loops("open", db_path=db_path)
    assert len(open_rows) == 1
    assert open_rows[0]["description"] == "call the dentist on Friday"


# --- 4. Over-eager detection fixed: pre-filter gate + LLM rejection ----------


async def test_idle_chatter_never_reaches_llm(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    # Would CREATE if ever consulted — but the pre-filter must gate it out.
    ext = _ScriptedExtractor("create")
    mgr = MemoryManager(
        db_path=db_path, vector_store=_vs(),
        evaluator=MemoryEvaluator(), extractor=ext,
    )

    await mgr.consolidate("anymore", "I'm not sure I follow, sir.")

    assert ext.loop_calls == [], "pre-filter must gate the LLM on idle chatter"
    assert await database.get_open_loops("open", db_path=db_path) == []


async def test_non_genuine_need_to_rejected_as_noop(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    # The "i need to" trigger passes the pre-filter, so the LLM IS consulted —
    # and judges it not a genuine reminder (NOOP), so nothing is stored. The old
    # keyword path would have stored the fragment after "i need to".
    ext = _ScriptedExtractor("noop")
    mgr = MemoryManager(
        db_path=db_path, vector_store=_vs(),
        evaluator=MemoryEvaluator(), extractor=ext,
    )

    await mgr.consolidate("i need to, at some point, sort my life out", "Indeed.")

    assert ext.loop_calls, "a trigger phrase must still reach the LLM"
    assert await database.get_open_loops("open", db_path=db_path) == [], (
        "a non-genuine fragment must not be stored as a reminder"
    )


# --- 5. Randomized greeting + reminders -------------------------------------


def test_greeting_instruction_varies() -> None:
    seen = {main._greeting_instruction() for _ in range(60)}
    assert len(seen) > 1, "the greeting angle must vary across launches"
    # Persona/length cap is preserved on every angle.
    assert all(s.endswith("Keep it under 40 words.") for s in seen)


async def test_greeting_appends_overdue_reminders(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    await _insert_overdue_loop(db_path, "renew the software license")
    mgr = MemoryManager(db_path=db_path, vector_store=_vs())

    spoken = await main._compose_greeting_text(
        mgr, _EchoClient(), context="ctx", fallback="fb"
    )

    assert "open item(s) to follow up on" in spoken
    assert "renew the software license" in spoken


async def test_greeting_omits_resolved_reminders(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    await _insert_overdue_loop(db_path, "renew the software license")
    # Once resolved, the overdue loop must no longer be surfaced at startup.
    await database.resolve_open_loops_async(
        db_path=db_path, ids=None, status="resolved"
    )
    mgr = MemoryManager(db_path=db_path, vector_store=_vs())

    spoken = await main._compose_greeting_text(
        mgr, _EchoClient(), context="ctx", fallback="fb"
    )

    assert "open item(s)" not in spoken
    assert "renew the software license" not in spoken


async def test_greeting_no_reminders_when_none(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    mgr = MemoryManager(db_path=db_path, vector_store=_vs())

    spoken = await main._compose_greeting_text(
        mgr, _EchoClient(), context="ctx", fallback="fb"
    )

    assert "open item(s)" not in spoken
    assert spoken.strip(), "a base greeting is still produced"


async def test_greeting_varies_across_calls() -> None:
    spokens = set()
    for _ in range(40):
        spokens.add(
            await main._compose_greeting_text(
                None, _EchoClient(), context="ctx", fallback="fb"
            )
        )
    assert len(spokens) > 1, "spoken greeting must vary across launches"


async def test_greeting_falls_back_when_client_fails() -> None:
    class _BoomClient:
        async def stream_response(self, messages, system_prompt):
            raise RuntimeError("no api key")
            yield  # pragma: no cover — makes this an async generator

    spoken = await main._compose_greeting_text(
        None, _BoomClient(), context="ctx", fallback="FALLBACK LINE"
    )
    assert spoken == "FALLBACK LINE"
