"""Phase 16D verification — Bi-Temporal Facts + Ebbinghaus + TOKI operators.

Targeted checks for the Phase 16D deliverables:

1. Migration — the bi-temporal/decay columns are added idempotently (repeated
   ``init_db`` is safe), backfilled with safe defaults, and ``valid_from`` is
   auto-populated to ``created_at`` on insert via the trigger.
2. TOKI contradiction operators applied to an incoming UPDATE:
   * ``last-write-wins`` — old fact archived (``valid_to`` + ``superseded_by``),
     new fact inserted.
   * ``evidence-weighted`` — higher confidence supersedes; lower is a NOOP.
   * ``merge`` — old + new end up with non-overlapping valid windows.
   * ``await-confirmation`` — both stay active; ``conflicting_fact_ids`` linked.
3. Ebbinghaus decay — strength decays on schedule; a fact crossing the floor is
   archived (``valid_to`` set), not deleted.
4. Archived / superseded / decayed facts are excluded from active recall.
5. The category/keyword write-policy selection mapping.
6. FAISS tombstoning bookkeeping (mark / skip / persist), and that DELETE
   tombstones the retracted fact's vector.

All in-memory / temp-file: the LLM clients are never constructed (we drive the
manager's ``_apply_extractions`` / ``run_decay`` directly with canned
``Extraction`` objects) and the vector store is a lightweight fake, so no API
key, no network, and the heavy embedding model never loads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.memory import database
from backend.memory.extractor import Extraction
from backend.memory.manager import (
    DECAY_THRESHOLD,
    POLICY_AWAIT_CONFIRMATION,
    POLICY_EVIDENCE_WEIGHTED,
    POLICY_LAST_WRITE_WINS,
    POLICY_MERGE,
    MemoryManager,
    _choose_write_policy,
)
from backend.memory.vector_store import SearchResult, VectorStore

# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "phase16d.db")
    await database.init_db(db_path)
    return db_path


async def _row(db_path: str, fact_id: int) -> dict:
    fact = await database.get_memory_fact(fact_id, db_path=db_path)
    assert fact is not None
    return fact


async def _all_facts(db_path: str) -> list[dict]:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, content, valid_from, valid_to, strength, write_policy, "
            "superseded_by_fact_id, conflicting_fact_ids "
            "FROM memory_facts ORDER BY id"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


async def _set_last_recalled(db_path: str, fact_id: int, when: str) -> None:
    conn = await database.connect(db_path)
    try:
        await conn.execute(
            "UPDATE memory_facts SET last_recalled_at = ? WHERE id = ?",
            (when, fact_id),
        )
        await conn.commit()
    finally:
        await conn.close()


class _FakeVectorStore:
    """Fake store with Phase 16D tombstone support.

    Each entry is ``[text, metadata, alive]``. ``search`` returns live entries
    only, most-recent first, at a fixed similarity (0.9 > the 0.85 dedup floor)
    so an UPDATE/DELETE always locates the most-recently-seeded matching fact.
    ``tombstone_fact_id`` flips the ``alive`` flag for every matching entry.
    """

    def __init__(self, search_score: float = 0.9) -> None:
        self.entries: list[list] = []
        self._score = search_score
        self.tombstoned: list[int] = []

    def __len__(self) -> int:
        return len(self.entries)

    def add(self, text, metadata=None):
        self.entries.append([text, dict(metadata or {}), True])
        return len(self.entries) - 1

    def tombstone_fact_id(self, fact_id: int) -> int:
        n = 0
        for entry in self.entries:
            if entry[1].get("fact_id") == fact_id and entry[2]:
                entry[2] = False
                n += 1
        if n:
            self.tombstoned.append(fact_id)
        return n

    def search(self, query, top_k: int = 5) -> list[SearchResult]:
        hits = [
            SearchResult(text=e[0], metadata=e[1], score=self._score)
            for e in reversed(self.entries)
            if e[2]
        ]
        return hits[:top_k]


async def _seed_fact(
    db_path: str,
    vs: _FakeVectorStore,
    content: str,
    *,
    write_policy: str,
    confidence: float = 0.9,
    category: str = "general",
) -> int:
    """Insert an existing fact (DB + fake FAISS) under a chosen write-policy."""
    fact_id = await database.save_memory_fact(
        "voice", category, content, importance=0.8,
        confidence=confidence, write_policy=write_policy, db_path=db_path,
    )
    vs.add(content, {"fact_id": fact_id, "category": category})
    return fact_id


def _update(fact: str, *, confidence: float = 0.9, subject: str = "user"):
    return Extraction("UPDATE", fact, confidence, subject, "user")


# --- 1. Migration: idempotent, columns present, valid_from trigger ----------


async def test_migration_idempotent_and_columns_present(tmp_path) -> None:
    db_path = str(tmp_path / "migrate.db")
    await database.init_db(db_path)
    await database.init_db(db_path)  # second run must be a safe no-op

    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute("PRAGMA table_info(memory_facts)")
        cols = {r["name"] for r in await cursor.fetchall()}
    finally:
        await conn.close()

    for col in (
        "valid_from", "valid_to", "strength", "half_life_days",
        "superseded_by_fact_id", "write_policy", "conflicting_fact_ids",
    ):
        assert col in cols, f"Phase 16D column {col!r} missing after migration"

    # Defaults backfill + valid_from trigger populate on insert.
    fid = await database.save_memory_fact(
        "voice", "general", "User likes tea.", importance=0.5, db_path=db_path,
    )
    row = await _row(db_path, fid)
    assert abs(float(row["strength"]) - 1.0) < 1e-9
    assert int(row["half_life_days"]) == 14
    assert row["write_policy"] == POLICY_LAST_WRITE_WINS
    assert row["valid_to"] is None
    assert row["valid_from"] is not None
    assert row["valid_from"] == row["created_at"], (
        "valid_from trigger should copy created_at on insert"
    )


# --- 2a. last-write-wins supersede ------------------------------------------


async def test_last_write_wins_supersedes_old(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    old_id = await _seed_fact(
        db_path, vs, "User lives in Portland.",
        write_policy=POLICY_LAST_WRITE_WINS,
    )
    mgr = MemoryManager(db_path=db_path, vector_store=vs)

    await mgr._apply_extractions(
        [_update("User lives in Boston.")],
        category="general", score=0.9, source="voice", agent_id=None,
    )

    old = await _row(db_path, old_id)
    assert old["valid_to"] is not None, "old fact must be archived"
    new_id = old["superseded_by_fact_id"]
    assert new_id is not None, "superseded_by_fact_id must point at the new fact"
    new = await _row(db_path, new_id)
    assert new["content"] == "User lives in Boston."
    assert new["valid_to"] is None, "the replacement fact must be active"
    # The old vector is tombstoned so it cannot resurface in recall/dedup.
    assert old_id in vs.tombstoned


# --- 2b. evidence-weighted: higher wins, lower is NOOP ----------------------


async def test_evidence_weighted_higher_confidence_supersedes(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    old_id = await _seed_fact(
        db_path, vs, "User is allergic to peanuts.",
        write_policy=POLICY_EVIDENCE_WEIGHTED, confidence=0.5,
    )
    mgr = MemoryManager(db_path=db_path, vector_store=vs)

    await mgr._apply_extractions(
        [_update("User is allergic to tree nuts.", confidence=0.95)],
        category="general", score=0.9, source="voice", agent_id=None,
    )

    old = await _row(db_path, old_id)
    assert old["valid_to"] is not None, "higher-confidence incoming should win"
    assert old["superseded_by_fact_id"] is not None


async def test_evidence_weighted_lower_confidence_is_noop(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    old_id = await _seed_fact(
        db_path, vs, "User is allergic to peanuts.",
        write_policy=POLICY_EVIDENCE_WEIGHTED, confidence=0.9,
    )
    mgr = MemoryManager(db_path=db_path, vector_store=vs)

    await mgr._apply_extractions(
        [_update("User might be allergic to peanuts.", confidence=0.4)],
        category="general", score=0.9, source="voice", agent_id=None,
    )

    old = await _row(db_path, old_id)
    assert old["valid_to"] is None, "lower-confidence incoming must NOT supersede"
    facts = await _all_facts(db_path)
    assert len(facts) == 1, "a NOOP under evidence-weighted writes no new fact"


# --- 2c. merge: non-overlapping valid windows -------------------------------


async def test_merge_produces_non_overlapping_windows(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    old_id = await _seed_fact(
        db_path, vs, "User works at Acme Corp.", write_policy=POLICY_MERGE,
    )
    # Force a clearly-past valid_from so the old window is unambiguous.
    past = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = await database.connect(db_path)
    try:
        await conn.execute(
            "UPDATE memory_facts SET valid_from = ? WHERE id = ?", (past, old_id)
        )
        await conn.commit()
    finally:
        await conn.close()

    new_id = await mgr_apply_merge(db_path, vs, old_id)

    old = await _row(db_path, old_id)
    new = await _row(db_path, new_id)
    assert old["valid_to"] is not None and new["valid_to"] is None
    assert old["valid_from"] <= old["valid_to"], "old window must be well-formed"
    # Non-overlapping handoff: the old window closes exactly where the new opens.
    assert old["valid_to"] == new["valid_from"]
    assert new["valid_from"] >= old["valid_from"]


async def mgr_apply_merge(db_path, vs, old_id) -> int:
    mgr = MemoryManager(db_path=db_path, vector_store=vs)
    await mgr._apply_extractions(
        [_update("User works at Globex Inc.")],
        category="general", score=0.9, source="voice", agent_id=None,
    )
    old = await _row(db_path, old_id)
    return old["superseded_by_fact_id"]


# --- 2d. await-confirmation: both active, conflict recorded -----------------


async def test_await_confirmation_keeps_both_and_links(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    old_id = await _seed_fact(
        db_path, vs, "User's manager is Dana.",
        write_policy=POLICY_AWAIT_CONFIRMATION,
    )
    mgr = MemoryManager(db_path=db_path, vector_store=vs)

    await mgr._apply_extractions(
        [_update("User's manager is Priya.")],
        category="general", score=0.9, source="voice", agent_id=None,
    )

    facts = await _all_facts(db_path)
    active = [f for f in facts if f["valid_to"] is None]
    assert len(active) == 2, "await-confirmation must leave BOTH facts active"
    new = next(f for f in active if f["id"] != old_id)
    old = next(f for f in active if f["id"] == old_id)
    # Each fact references the other in conflicting_fact_ids.
    assert old["conflicting_fact_ids"] and str(new["id"]) in old["conflicting_fact_ids"]
    assert new["conflicting_fact_ids"] and str(old_id) in new["conflicting_fact_ids"]


# --- 3. Ebbinghaus decay ----------------------------------------------------


async def test_decay_drops_strength_and_keeps_active_when_above_floor(
    tmp_path,
) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    fid = await _seed_fact(
        db_path, vs, "User prefers dark roast.",
        write_policy=POLICY_LAST_WRITE_WINS,
    )
    # Recalled 7 days ago, half-life 14 → strength ≈ exp(-0.5) ≈ 0.61 (> floor).
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    await _set_last_recalled(db_path, fid, seven_days_ago)

    mgr = MemoryManager(db_path=db_path, vector_store=vs)
    archived = await mgr.run_decay()

    assert archived == 0, "a fact above the floor must not be archived"
    row = await _row(db_path, fid)
    assert 0.1 < float(row["strength"]) < 1.0, "strength should decay below 1.0"
    assert row["valid_to"] is None


async def test_decay_archives_fact_below_floor(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    fid = await _seed_fact(
        db_path, vs, "Stale trivia nobody revisits.",
        write_policy=POLICY_LAST_WRITE_WINS,
    )
    # Recalled long ago → strength collapses far below the 0.1 floor.
    long_ago = (datetime.now(timezone.utc) - timedelta(days=120)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    await _set_last_recalled(db_path, fid, long_ago)

    mgr = MemoryManager(db_path=db_path, vector_store=vs)
    archived = await mgr.run_decay()

    assert archived == 1, "a fact crossing the decay floor must be archived"
    row = await _row(db_path, fid)
    assert row["valid_to"] is not None, "decayed fact must be archived (valid_to)"
    assert float(row["strength"]) < DECAY_THRESHOLD
    assert fid in vs.tombstoned, "decayed fact's vector must be tombstoned"


# --- 4. Recall excludes archived / superseded / decayed ---------------------


async def test_superseded_fact_excluded_from_recall(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    old_id = await _seed_fact(
        db_path, vs, "User lives in Portland.",
        write_policy=POLICY_LAST_WRITE_WINS,
    )
    mgr = MemoryManager(db_path=db_path, vector_store=vs)
    await mgr._apply_extractions(
        [_update("User lives in Boston.")],
        category="general", score=0.9, source="voice", agent_id=None,
    )

    result = await mgr.recall("where does the user live", n_recent=0, n_semantic=5)
    contents = [f["content"] for f in result.semantic_facts]
    assert "User lives in Boston." in contents
    assert "User lives in Portland." not in contents, (
        "the superseded (archived + tombstoned) fact must not be recalled"
    )
    _ = old_id


async def test_decayed_fact_excluded_from_recall(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    fid = await _seed_fact(
        db_path, vs, "Stale trivia nobody revisits.",
        write_policy=POLICY_LAST_WRITE_WINS,
    )
    long_ago = (datetime.now(timezone.utc) - timedelta(days=120)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    await _set_last_recalled(db_path, fid, long_ago)
    mgr = MemoryManager(db_path=db_path, vector_store=vs)
    await mgr.run_decay()

    result = await mgr.recall("stale trivia", n_recent=0, n_semantic=5)
    assert result.semantic_facts == [], "decay-archived fact must not be recalled"


# --- 5. write-policy selection mapping --------------------------------------


def test_choose_write_policy_mapping() -> None:
    assert _choose_write_policy("general", "User lives in Boston.") == (
        POLICY_LAST_WRITE_WINS
    )
    assert _choose_write_policy("preference", "User prefers tea.") == (
        POLICY_EVIDENCE_WEIGHTED
    )
    # Keyword hints override the category default.
    assert _choose_write_policy("general", "User is allergic to shellfish.") == (
        POLICY_EVIDENCE_WEIGHTED
    )
    assert _choose_write_policy("general", "User works at Acme.") == POLICY_MERGE
    assert _choose_write_policy("general", "", "married to Sam") == POLICY_MERGE


# --- 6. DELETE tombstones the retracted fact's vector + recall excludes ------


async def test_delete_tombstones_and_excludes_from_recall(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    fid = await _seed_fact(
        db_path, vs, "User uses Vim.", write_policy=POLICY_LAST_WRITE_WINS,
    )
    mgr = MemoryManager(db_path=db_path, vector_store=vs)

    await mgr._apply_extractions(
        [Extraction("DELETE", "User no longer uses Vim.", 0.9, "user", "user")],
        category="general", score=0.9, source="voice", agent_id=None,
    )

    row = await _row(db_path, fid)
    assert row["valid_to"] is not None, "DELETE must archive the fact"
    assert fid in vs.tombstoned, "DELETE must tombstone the retracted vector"
    result = await mgr.recall("which editor does the user use", n_recent=0,
                              n_semantic=5)
    assert result.semantic_facts == []


# --- 7. VectorStore tombstone bookkeeping + persistence ---------------------


def test_vector_store_tombstone_bookkeeping(tmp_path) -> None:
    vs = VectorStore(index_path=tmp_path / "vs.bin")
    # Populate the payload arrays directly to avoid loading the embedding model.
    vs._texts = ["a", "b", "c"]
    vs._metadata = [
        {"fact_id": 1}, {"fact_id": 2}, {"fact_id": 1},
    ]
    assert vs.active_count == 3
    # fact_id 1 owns two vectors (e.g. a 16C in-place update added a 2nd).
    assert vs.tombstone_fact_id(1) == 2
    assert vs.active_count == 1
    assert vs.tombstone_fact_id(1) == 0, "re-tombstoning is idempotent"

    # Persist + reload: tombstones survive the round-trip.
    vs.save()
    reloaded = VectorStore(index_path=tmp_path / "vs.bin")
    reloaded.load()
    assert reloaded._tombstoned == {0, 2}
    assert reloaded.active_count == 1
