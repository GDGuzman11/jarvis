"""Phase 16B verification — Memory Intelligence: Multi-Signal Re-Ranking.

Targeted checks for the Phase 16B deliverables:

1. The FAISS candidate pool is re-ranked by a weighted composite of five signals
   (semantic / keyword / recency / importance / frequency), not by similarity
   alone — so:
     * a recently-recalled fact outranks an equally-similar stale one,
     * a high-``importance`` fact outranks an equally-similar low-importance one,
     * a frequently-accessed fact outranks an equally-similar rarely-accessed one.
2. ``access_count`` increments (and ``last_recalled_at`` still updates) on every
   recall hit — the combined write activated here and in Phase 16A.
3. The composite ordering is deterministic for fixed inputs.
4. ``MIN_SEMANTIC_SCORE`` remains a pre-filter — sub-threshold noise never enters
   the re-ranking pool.

All in-memory / temp-file: no API key, no network, no audio device, and the
VectorStore is a lightweight fake so the heavy embedding model never loads.
"""

from __future__ import annotations

from backend.memory import database
from backend.memory.manager import (
    MemoryManager,
    _Candidate,
    _rank_candidates,
    _recency_score,
)
from backend.memory.vector_store import SearchResult


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "phase16b.db")
    await database.init_db(db_path)
    return db_path


class _FakeVectorStore:
    """VectorStore stand-in returning canned hits; never loads the model."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results = results or []

    def __len__(self) -> int:
        return len(self._results)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return self._results[:top_k]

    def add(self, text, metadata=None):  # pragma: no cover - unused here
        return 0


async def _get_fact(db_path: str, fact_id: int) -> dict:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, importance, access_count, last_recalled_at, created_at "
            "FROM memory_facts WHERE id = ?",
            (fact_id,),
        )
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return dict(row)


def _hit(fact_id: int, text: str, score: float, category: str = "general") -> SearchResult:
    return SearchResult(
        text=text, metadata={"fact_id": fact_id, "category": category}, score=score
    )


# --- 1a. Recency: recent fact outranks an equally-similar stale fact ---------


async def test_recency_breaks_ties_between_equal_similarity_facts(tmp_path) -> None:
    db_path = await _make_db(tmp_path)

    recent = await database.save_memory_fact(
        "voice", "general", "Fact alpha recalled recently", importance=0.5, db_path=db_path
    )
    stale = await database.save_memory_fact(
        "voice", "general", "Fact beta recalled long ago", importance=0.5, db_path=db_path
    )
    # Identical except recency. Same access_count (0) and importance (0.5).
    # Use SQLite datetime expressions for the timestamps via a direct connection.
    conn = await database.connect(db_path)
    try:
        await conn.execute(
            "UPDATE memory_facts SET last_recalled_at = datetime('now') WHERE id = ?",
            (recent,),
        )
        await conn.execute(
            "UPDATE memory_facts SET last_recalled_at = datetime('now','-30 days') "
            "WHERE id = ?",
            (stale,),
        )
        await conn.commit()
    finally:
        await conn.close()

    # Equal FAISS similarity; a query that does NOT keyword-match either fact so
    # the keyword signal stays neutral (both 0) and only recency differs.
    vs = _FakeVectorStore(
        [
            _hit(recent, "Fact alpha recalled recently", 0.80),
            _hit(stale, "Fact beta recalled long ago", 0.80),
        ]
    )
    manager = MemoryManager(db_path=db_path, vector_store=vs)
    result = await manager.recall("zzqueryxx", n_semantic=2)

    contents = [f["content"] for f in result.semantic_facts]
    assert contents[0] == "Fact alpha recalled recently", (
        f"recent fact should rank first, got order: {contents}"
    )


# --- 1b. Importance: high-importance fact outranks low, all else equal -------


async def test_importance_breaks_ties_between_equal_similarity_facts(tmp_path) -> None:
    db_path = await _make_db(tmp_path)

    high = await database.save_memory_fact(
        "voice", "general", "Fact gamma is important", importance=0.95, db_path=db_path
    )
    low = await database.save_memory_fact(
        "voice", "general", "Fact delta is trivial", importance=0.05, db_path=db_path
    )
    # Pin recency equal for both so only importance differs.
    conn = await database.connect(db_path)
    try:
        await conn.execute(
            "UPDATE memory_facts SET last_recalled_at = datetime('now','-1 day') "
            "WHERE id IN (?, ?)",
            (high, low),
        )
        await conn.commit()
    finally:
        await conn.close()

    vs = _FakeVectorStore(
        [
            _hit(low, "Fact delta is trivial", 0.80),
            _hit(high, "Fact gamma is important", 0.80),
        ]
    )
    manager = MemoryManager(db_path=db_path, vector_store=vs)
    result = await manager.recall("zzqueryxx", n_semantic=2)

    contents = [f["content"] for f in result.semantic_facts]
    assert contents[0] == "Fact gamma is important", (
        f"high-importance fact should rank first, got: {contents}"
    )


# --- 1c. Frequency: frequently-accessed fact outranks rarely-accessed --------


async def test_frequency_breaks_ties_between_equal_similarity_facts(tmp_path) -> None:
    db_path = await _make_db(tmp_path)

    frequent = await database.save_memory_fact(
        "voice", "general", "Fact epsilon accessed often", importance=0.5, db_path=db_path
    )
    rare = await database.save_memory_fact(
        "voice", "general", "Fact zeta accessed rarely", importance=0.5, db_path=db_path
    )
    # Equal recency + importance; only access_count differs.
    conn = await database.connect(db_path)
    try:
        await conn.execute(
            "UPDATE memory_facts SET last_recalled_at = datetime('now','-1 day'), "
            "access_count = 50 WHERE id = ?",
            (frequent,),
        )
        await conn.execute(
            "UPDATE memory_facts SET last_recalled_at = datetime('now','-1 day'), "
            "access_count = 0 WHERE id = ?",
            (rare,),
        )
        await conn.commit()
    finally:
        await conn.close()

    vs = _FakeVectorStore(
        [
            _hit(rare, "Fact zeta accessed rarely", 0.80),
            _hit(frequent, "Fact epsilon accessed often", 0.80),
        ]
    )
    manager = MemoryManager(db_path=db_path, vector_store=vs)
    result = await manager.recall("zzqueryxx", n_semantic=2)

    contents = [f["content"] for f in result.semantic_facts]
    assert contents[0] == "Fact epsilon accessed often", (
        f"frequently-accessed fact should rank first, got: {contents}"
    )


# --- 2. access_count increments and last_recalled_at updates on recall -------


async def test_recall_increments_access_count_and_stamps_recency(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    fact_id = await database.save_memory_fact(
        "voice", "preference", "User prefers tea over coffee", importance=0.7, db_path=db_path
    )

    before = await _get_fact(db_path, fact_id)
    assert int(before["access_count"]) == 0
    assert before["last_recalled_at"] is None

    vs = _FakeVectorStore([_hit(fact_id, "User prefers tea over coffee", 0.90)])
    manager = MemoryManager(db_path=db_path, vector_store=vs)

    await manager.recall("what does the user drink", n_semantic=1)
    after_one = await _get_fact(db_path, fact_id)
    assert int(after_one["access_count"]) == 1, "access_count must increment by 1"
    assert after_one["last_recalled_at"] is not None, "last_recalled_at must be stamped"

    await manager.recall("what does the user drink", n_semantic=1)
    after_two = await _get_fact(db_path, fact_id)
    assert int(after_two["access_count"]) == 2, "access_count must increment each recall"


# --- 3. Deterministic composite ordering for fixed inputs --------------------


def _candidate(fact_id, *, semantic, importance, access_count, days_since,
               keyword_pos=None, keyword_n=0) -> _Candidate:
    return _Candidate(
        fact_id=fact_id,
        text=f"fact-{fact_id}",
        category="general",
        semantic=semantic,
        importance=importance,
        access_count=access_count,
        days_since=days_since,
        keyword_pos=keyword_pos,
        keyword_n=keyword_n,
    )


def test_rank_candidates_is_deterministic() -> None:
    pool = [
        _candidate(1, semantic=0.80, importance=0.5, access_count=2, days_since=10),
        _candidate(2, semantic=0.82, importance=0.9, access_count=0, days_since=1),
        _candidate(3, semantic=0.70, importance=0.2, access_count=40, days_since=0),
    ]
    first = [(c.fact_id, round(s, 9)) for c, s in _rank_candidates(pool)]
    second = [(c.fact_id, round(s, 9)) for c, s in _rank_candidates(list(pool))]
    assert first == second, "ranking must be reproducible for identical inputs"


def test_rank_candidates_tie_breaks_by_semantic_then_id() -> None:
    # Two fully-identical candidates except fact_id → composite ties; tie-break
    # must be deterministic (semantic desc, then fact_id asc).
    a = _candidate(7, semantic=0.80, importance=0.5, access_count=3, days_since=5)
    b = _candidate(3, semantic=0.80, importance=0.5, access_count=3, days_since=5)
    ranked = _rank_candidates([a, b])
    assert [c.fact_id for c, _ in ranked] == [3, 7], "tie should break by fact_id asc"


def test_recency_score_is_monotonic() -> None:
    # Sanity check on the recency curve used by the composite.
    assert _recency_score(0) > _recency_score(1) > _recency_score(30) > _recency_score(365)
    assert abs(_recency_score(0) - 1.0) < 1e-9


# --- 4. MIN_SEMANTIC_SCORE remains a pre-filter ------------------------------


async def test_subthreshold_candidates_are_filtered_before_reranking(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    keep = await database.save_memory_fact(
        "voice", "general", "Kept fact above threshold", importance=0.5, db_path=db_path
    )
    drop = await database.save_memory_fact(
        "voice", "general", "Dropped noise below threshold", importance=0.99, db_path=db_path
    )
    # The dropped fact has very high importance but a sub-threshold similarity,
    # so it must NOT be re-ranked in on importance alone.
    vs = _FakeVectorStore(
        [
            _hit(keep, "Kept fact above threshold", 0.60),
            _hit(drop, "Dropped noise below threshold", 0.10),
        ]
    )
    manager = MemoryManager(db_path=db_path, vector_store=vs)
    result = await manager.recall("zzqueryxx", n_semantic=5)

    contents = [f["content"] for f in result.semantic_facts]
    assert "Kept fact above threshold" in contents
    assert "Dropped noise below threshold" not in contents, (
        "sub-threshold candidate must be pre-filtered before re-ranking"
    )


# --- 5. Keyword signal lifts a keyword-matching fact -------------------------


async def test_keyword_signal_lifts_matching_fact(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    match = await database.save_memory_fact(
        "voice", "general", "The deployment pipeline runs nightly", importance=0.5,
        db_path=db_path,
    )
    nomatch = await database.save_memory_fact(
        "voice", "general", "Sandwiches are tasty at lunch", importance=0.5,
        db_path=db_path,
    )
    # Pin recency + access_count equal so only the keyword signal differs.
    conn = await database.connect(db_path)
    try:
        await conn.execute(
            "UPDATE memory_facts SET last_recalled_at = datetime('now','-1 day') "
            "WHERE id IN (?, ?)",
            (match, nomatch),
        )
        await conn.commit()
    finally:
        await conn.close()

    vs = _FakeVectorStore(
        [
            _hit(nomatch, "Sandwiches are tasty at lunch", 0.80),
            _hit(match, "The deployment pipeline runs nightly", 0.80),
        ]
    )
    manager = MemoryManager(db_path=db_path, vector_store=vs)
    # Query keyword-matches only the 'deployment pipeline' fact via FTS.
    result = await manager.recall("deployment pipeline", n_semantic=2)

    contents = [f["content"] for f in result.semantic_facts]
    assert contents[0] == "The deployment pipeline runs nightly", (
        f"keyword-matching fact should rank first, got: {contents}"
    )
