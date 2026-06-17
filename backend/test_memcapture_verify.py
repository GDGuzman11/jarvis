"""Memory Capture Overhaul — verification (backend half).

Targeted checks for the lighter capture gate, the 10-category DOMAIN, and the
confirm-when-unsure flow:

1. A birthday / explicit "remember…" turn is captured with ``domain='personal'``
   even though its signal score is only 'general' (the old hard gate dropped it).
2. Idle chatter ("ok thanks") never reaches the LLM extractor and stores nothing.
3. A backend/Kado statement is tagged ``domain='kado'``.
4. A borderline-confidence ADD is held (not stored) and emits a
   ``memory_confirm`` event.
5. ``POST /api/memory/confirm`` with ``store`` writes the held fact and emits a
   ``memory_update``; ``discard`` drops it; an unknown id is a 404.
6. An explicit "remember…" forces auto-store even at mid confidence.
7. Regression: the evaluator's signal ``category`` column is still written
   unchanged (so the 16D write-policy keeps working), separate from ``domain``.

All in-memory / temp-file: the LLM extractor and vector store are lightweight
fakes and the hub is a recorder, so there is no API key, no network, and the
embedding model never loads.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from backend import main
from backend.events import MemoryConfirmEvent, MemoryUpdateEvent
from backend.memory import database
from backend.memory.evaluator import MemoryEvaluator
from backend.memory.extractor import Extraction
from backend.memory.manager import MemoryManager
from backend.memory.vector_store import SearchResult


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "memcapture.db")
    await database.init_db(db_path)
    return db_path


async def _active_facts(db_path: str) -> list[dict]:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, content, category, domain, created_by, confidence, "
            "write_policy, valid_to FROM memory_facts "
            "WHERE valid_to IS NULL ORDER BY id"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


async def _fact_count(db_path: str) -> int:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute("SELECT COUNT(*) AS n FROM memory_facts")
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return int(row["n"])


class FakeHub:
    """Records every broadcast event in order."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def broadcast(self, event: Any) -> int:
        self.events.append(event)
        return 1

    def of_type(self, cls) -> list[Any]:
        return [e for e in self.events if isinstance(e, cls)]


class _FakeVectorStore:
    """Records adds; returns stored entries as hits at a fixed similarity."""

    def __init__(self, search_score: float = 0.9) -> None:
        self.entries: list[tuple[str, dict]] = []
        self._score = search_score

    def __len__(self) -> int:
        return len(self.entries)

    def add(self, text, metadata=None):
        self.entries.append((text, dict(metadata or {})))
        return len(self.entries) - 1

    def search(self, query, top_k: int = 5) -> list[SearchResult]:
        hits = [
            SearchResult(text=text, metadata=meta, score=self._score)
            for text, meta in reversed(self.entries)
        ]
        return hits[:top_k]


class _QueueExtractor:
    """Stand-in LLMExtractor returning canned batches and recording its calls.

    No ``extract_open_loops`` attribute on purpose, so the manager's open-loop
    path uses its conservative keyword fallback (no spurious reminders here).
    """

    def __init__(self, batches: list[list[Extraction]]) -> None:
        self._batches = list(batches)
        self.calls: list[tuple[str, str]] = []

    async def extract(self, user_text: str, reply: str) -> list[Extraction]:
        self.calls.append((user_text, reply))
        return self._batches.pop(0) if self._batches else []


def _mgr(db_path, extractor, hub=None) -> MemoryManager:
    return MemoryManager(
        db_path=db_path, vector_store=_FakeVectorStore(),
        evaluator=MemoryEvaluator(), extractor=extractor, hub=hub,
    )


# --- 1. Birthday captured as personal despite a 'general' signal score -------


async def test_birthday_captured_as_personal_domain(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    # "remember my birthday…" is an explicit request and a high-confidence ADD;
    # the LLM tags it personal. The signal score for this text is 'general'.
    ext = _QueueExtractor(
        [[Extraction("ADD", "User's birthday is June 5.", 0.95, "user",
                     "user", "personal")]]
    )
    mgr = _mgr(db_path, ext)

    fid = await mgr.consolidate("remember my birthday is June 5", "Noted, sir.")

    assert fid is not None, "an explicit birthday must be captured, not dropped"
    facts = await _active_facts(db_path)
    assert len(facts) == 1
    assert facts[0]["content"] == "User's birthday is June 5."
    assert facts[0]["domain"] == "personal"


async def test_high_confidence_personal_auto_stores(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    # Not explicit, but high confidence (>= AUTO_STORE) → silent store.
    ext = _QueueExtractor(
        [[Extraction("ADD", "User's birthday is June 5.", 0.92, "user",
                     "user", "personal")]]
    )
    mgr = _mgr(db_path, ext)

    fid = await mgr.consolidate("my birthday is June 5", "Understood.")

    assert fid is not None
    facts = await _active_facts(db_path)
    assert len(facts) == 1 and facts[0]["domain"] == "personal"


# --- 2. Idle chatter never reaches the LLM and stores nothing ----------------


async def test_idle_chatter_not_stored_and_llm_not_called(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    ext = _QueueExtractor([[Extraction("ADD", "x", 0.99, "x", "user", "general")]])
    mgr = _mgr(db_path, ext)

    result = await mgr.consolidate("ok thanks", "You're most welcome, sir.")

    assert result is None
    assert ext.calls == [], "chatter-skip must gate the LLM extractor"
    assert await _fact_count(db_path) == 0


# --- 3. A backend/Kado statement is tagged domain='kado' ---------------------


async def test_backend_statement_tagged_kado(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    ext = _QueueExtractor(
        [[Extraction("ADD", "The FAISS recall pipeline was refactored.", 0.9,
                     "backend", "user", "kado")]]
    )
    mgr = _mgr(db_path, ext)

    await mgr.consolidate(
        "I refactored the FAISS recall pipeline in manager.py", "Done."
    )

    facts = await _active_facts(db_path)
    assert len(facts) == 1 and facts[0]["domain"] == "kado"


# --- 4. Borderline confidence → pending + memory_confirm, nothing stored -----


async def test_borderline_confidence_pends_and_emits_event(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = FakeHub()
    ext = _QueueExtractor(
        [[Extraction("ADD", "User enjoys hiking.", 0.55, "user",
                     "inference", "personal")]]
    )
    mgr = _mgr(db_path, ext, hub=hub)

    result = await mgr.consolidate(
        "I think I might enjoy hiking these days", "Noted."
    )

    assert result is None, "a borderline ADD must not be stored yet"
    assert await _fact_count(db_path) == 0
    confirms = hub.of_type(MemoryConfirmEvent)
    assert len(confirms) == 1, "a memory_confirm event must be emitted"
    ev = confirms[0]
    assert ev.fact == "User enjoys hiking."
    assert ev.category == "personal", "event category is the display DOMAIN"
    assert ev.confirm_id in mgr._pending_confirms


# --- 5. The confirm endpoint stores / discards a held fact -------------------


async def test_confirm_store_writes_fact_and_emits_update(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = FakeHub()
    ext = _QueueExtractor(
        [[Extraction("ADD", "User enjoys hiking.", 0.55, "user",
                     "inference", "personal")]]
    )
    mgr = _mgr(db_path, ext, hub=hub)
    await mgr.consolidate("I might enjoy hiking", "Noted.")
    confirm_id = hub.of_type(MemoryConfirmEvent)[0].confirm_id

    result = await mgr.confirm_pending(confirm_id, "store")

    assert result == "stored"
    facts = await _active_facts(db_path)
    assert len(facts) == 1 and facts[0]["content"] == "User enjoys hiking."
    assert facts[0]["domain"] == "personal"
    assert hub.of_type(MemoryUpdateEvent), "store must emit a memory_update"
    assert confirm_id not in mgr._pending_confirms, "pending entry must be popped"


async def test_confirm_discard_drops_fact(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = FakeHub()
    ext = _QueueExtractor(
        [[Extraction("ADD", "User enjoys hiking.", 0.55, "user",
                     "inference", "personal")]]
    )
    mgr = _mgr(db_path, ext, hub=hub)
    await mgr.consolidate("I might enjoy hiking", "Noted.")
    confirm_id = hub.of_type(MemoryConfirmEvent)[0].confirm_id

    result = await mgr.confirm_pending(confirm_id, "discard")

    assert result == "discarded"
    assert await _fact_count(db_path) == 0
    assert confirm_id not in mgr._pending_confirms


async def test_confirm_unknown_id_returns_none(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    mgr = _mgr(db_path, _QueueExtractor([]))
    assert await mgr.confirm_pending("does-not-exist", "store") is None


async def test_confirm_endpoint_store_and_404(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = FakeHub()
    ext = _QueueExtractor(
        [[Extraction("ADD", "User enjoys hiking.", 0.55, "user",
                     "inference", "personal")]]
    )
    mgr = _mgr(db_path, ext, hub=hub)
    await mgr.consolidate("I might enjoy hiking", "Noted.")
    confirm_id = hub.of_type(MemoryConfirmEvent)[0].confirm_id

    prev = getattr(main.app.state, "memory_manager", None)
    main.app.state.memory_manager = mgr
    try:
        ok = await main.memory_confirm_endpoint(confirm_id=confirm_id,
                                                decision="store")
        assert ok == {"status": "stored"}
        # Unknown id → 404.
        with pytest.raises(HTTPException) as exc:
            await main.memory_confirm_endpoint(confirm_id="nope",
                                               decision="store")
        assert exc.value.status_code == 404
        # Bad decision → 400.
        with pytest.raises(HTTPException) as exc2:
            await main.memory_confirm_endpoint(confirm_id=confirm_id,
                                               decision="maybe")
        assert exc2.value.status_code == 400
    finally:
        main.app.state.memory_manager = prev

    facts = await _active_facts(db_path)
    assert len(facts) == 1 and facts[0]["content"] == "User enjoys hiking."


# --- 6. Explicit "remember…" forces auto-store at mid confidence -------------


async def test_explicit_request_forces_store_at_mid_confidence(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = FakeHub()
    # Confidence 0.50 sits in the confirm band — but the explicit request forces
    # an auto-store with no confirmation prompt.
    ext = _QueueExtractor(
        [[Extraction("ADD", "User's dentist is Dr Lee.", 0.50, "user",
                     "user", "personal")]]
    )
    mgr = _mgr(db_path, ext, hub=hub)

    fid = await mgr.consolidate(
        "remember that my dentist is Dr Lee", "Noted, sir."
    )

    assert fid is not None, "explicit request must auto-store even at mid conf"
    assert await _fact_count(db_path) == 1
    assert hub.of_type(MemoryConfirmEvent) == [], "no confirm prompt when explicit"


async def test_below_low_confidence_dropped(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = FakeHub()
    ext = _QueueExtractor(
        [[Extraction("ADD", "User maybe likes jazz.", 0.30, "user",
                     "inference", "personal")]]
    )
    mgr = _mgr(db_path, ext, hub=hub)

    result = await mgr.consolidate("perhaps some jazz sometimes who knows", "Hm.")

    assert result is None
    assert await _fact_count(db_path) == 0
    assert mgr._pending_confirms == {}, "sub-floor confidence must not pend"
    assert hub.of_type(MemoryConfirmEvent) == []


# --- 7. Signal category column unchanged (16D write-policy intact) -----------


async def test_signal_category_written_unchanged_for_16d(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    # "I prefer…" scores the signal category 'preference' (write-policy
    # evidence-weighted). The LLM tags the DISPLAY domain 'personal'. The two must
    # be stored in separate columns so 16D keeps keying off the signal category.
    ext = _QueueExtractor(
        [[Extraction("ADD", "User prefers dark roast coffee.", 0.95, "user",
                     "user", "personal")]]
    )
    mgr = _mgr(db_path, ext)

    await mgr.consolidate("I prefer dark roast coffee", "Noted.")

    facts = await _active_facts(db_path)
    assert len(facts) == 1
    assert facts[0]["category"] == "preference", "signal category must be unchanged"
    assert facts[0]["domain"] == "personal", "domain is the separate new column"
    assert facts[0]["write_policy"] == "evidence-weighted", (
        "the 16D write-policy must still derive from the signal category"
    )
