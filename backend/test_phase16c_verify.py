"""Phase 16C verification — Memory Intelligence: LLM-Driven Extraction.

Targeted checks for the Phase 16C deliverables:

1. Paraphrased / contradicting facts dedup via the UPDATE path — a second,
   reworded statement supersedes the stored fact (FAISS similarity > 0.85)
   instead of inserting a duplicate row.
2. A deliberate ``NOOP`` from the extractor writes nothing (and is *not*
   second-guessed by the rule pass).
3. The rule pre-filter gates the LLM — an exchange that matches no rule never
   reaches the extractor.
4. The Haiku → phi3.5 fallback chain — when the Claude call raises, the local
   Ollama client is used; its parsed JSON is returned.
5. ``created_by`` provenance is persisted ('user' vs 'inference').
6. Defensive JSON parsing recovers an array from prose / code-fence wrapping and
   returns ``None`` on irrecoverable output.

All in-memory / temp-file: the LLM clients and the vector store are lightweight
fakes, so no API key, no network, and the heavy embedding model never loads.
"""

from __future__ import annotations

from backend.memory import database
from backend.memory.evaluator import MemoryEvaluator
from backend.memory.extractor import (
    Extraction,
    LLMExtractor,
    _extract_json_array,
)
from backend.memory.manager import MemoryManager
from backend.memory.vector_store import SearchResult

# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "phase16c.db")
    await database.init_db(db_path)
    return db_path


async def _fact_count(db_path: str) -> int:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute("SELECT COUNT(*) AS n FROM memory_facts")
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return int(row["n"])


async def _all_facts(db_path: str) -> list[dict]:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, content, created_by, confidence, valid_to "
            "FROM memory_facts ORDER BY id"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(r) for r in rows]


class _FakeVectorStore:
    """Records adds; returns stored entries as hits at a fixed similarity.

    The fixed score (0.9 by default) sits above ``UPDATE_SIMILARITY_THRESHOLD``
    so an UPDATE/DELETE always finds the most-recently-added stored fact — which
    is exactly the dedup behaviour under test.
    """

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


class _PromoteEvaluator(MemoryEvaluator):
    """Evaluator whose ``score`` always clears the threshold (isolates the
    extraction path from keyword-rule specifics). Open-loop / person detection
    is inherited unchanged.

    Uses the ``general`` category so stored facts carry the default
    ``last-write-wins`` write-policy (Phase 16D): an UPDATE then supersedes the
    old fact bi-temporally (archive old + insert new) rather than going through
    evidence-weighted/merge — keeping these extraction-path tests deterministic.
    """

    def score(self, user_text: str, reply: str):  # noqa: D102
        return 0.9, "general"


class _QueueExtractor:
    """Stand-in LLMExtractor returning canned batches and recording its calls."""

    def __init__(self, batches: list[list[Extraction]]) -> None:
        self._batches = list(batches)
        self.calls: list[tuple[str, str]] = []

    async def extract(self, user_text: str, reply: str) -> list[Extraction]:
        self.calls.append((user_text, reply))
        return self._batches.pop(0) if self._batches else []


# --- 1. Paraphrase → UPDATE dedups to a single fact -------------------------


async def test_paraphrased_facts_produce_single_fact(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    extractor = _QueueExtractor(
        [
            [Extraction("ADD", "User lives in Boston.", 0.95, "user", "user")],
            [Extraction("UPDATE", "Boston is where the user lives now.", 0.9,
                        "user", "user")],
        ]
    )
    mgr = MemoryManager(
        db_path=db_path, vector_store=vs,
        evaluator=_PromoteEvaluator(), extractor=extractor,
    )

    await mgr.consolidate("I moved to Boston", "Noted.")
    await mgr.consolidate("Boston is where I live now", "Understood.")

    # Phase 16D: an UPDATE under last-write-wins supersedes bi-temporally — the
    # old fact is archived (valid_to set) and the revised fact inserted, so
    # exactly ONE fact stays active and recall sees only the new phrasing.
    facts = await _all_facts(db_path)
    active = [f for f in facts if f["valid_to"] is None]
    assert len(active) == 1, "exactly one fact should remain active after supersede"
    assert active[0]["content"] == "Boston is where the user lives now.", (
        "the active fact should carry the UPDATE's revised text"
    )
    # The superseded original is retained (archived), not destroyed.
    archived = [f for f in facts if f["valid_to"] is not None]
    assert len(archived) == 1 and archived[0]["content"] == "User lives in Boston."


# --- 2. Explicit contradiction → UPDATE (supersede), not a 2nd INSERT -------


async def test_contradiction_triggers_update_not_insert(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    extractor = _QueueExtractor(
        [
            [Extraction("ADD", "User lives in Portland.", 0.95, "user", "user")],
            [Extraction("UPDATE", "User lives in Boston.", 0.95, "user", "user")],
        ]
    )
    mgr = MemoryManager(
        db_path=db_path, vector_store=vs,
        evaluator=_PromoteEvaluator(), extractor=extractor,
    )

    await mgr.consolidate("I live in Portland", "Noted.")
    await mgr.consolidate("No, I live in Boston now", "Understood.")

    # Phase 16D: a contradiction supersedes bi-temporally — the old fact is
    # archived and the new one inserted, leaving exactly ONE active fact (the
    # newest value). Recall therefore never surfaces the stale Portland fact.
    facts = await _all_facts(db_path)
    active = [f for f in facts if f["valid_to"] is None]
    assert len(active) == 1, "contradiction must leave exactly one active fact"
    assert active[0]["content"] == "User lives in Boston."


# --- 3. NOOP writes nothing (and does not fall back to rules) ----------------


async def test_noop_skips_write(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    extractor = _QueueExtractor(
        [[Extraction("NOOP", "", 1.0, "", "inference")]]
    )
    mgr = MemoryManager(
        db_path=db_path, vector_store=vs,
        evaluator=_PromoteEvaluator(), extractor=extractor,
    )

    result = await mgr.consolidate("what's the weather like", "It is sunny.")

    assert result is None
    assert await _fact_count(db_path) == 0, "a NOOP verdict must write no fact"
    assert vs.entries == [], "NOOP must not mirror anything into FAISS"


# --- 4. Chatter-skip gates the LLM (pure pleasantry → extractor not called) --
#
# Memory Capture Overhaul: the old hard ``score < 0.65`` gate is replaced by a
# light chatter-skip. A substantive question like "what time is it" now DOES
# reach the LLM (which NOOPs it), but a pure greeting/acknowledgement turn is
# still gated out before any LLM call — which is what this test now asserts.


async def test_chatter_skip_gates_the_llm(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    # Would store if ever consulted — but pure chatter must gate it out first.
    extractor = _QueueExtractor([[Extraction("ADD", "x", 0.9, "x", "user")]])
    mgr = MemoryManager(
        db_path=db_path, vector_store=vs,
        evaluator=MemoryEvaluator(), extractor=extractor,
    )

    result = await mgr.consolidate("ok thanks", "You're most welcome, sir.")

    assert result is None
    assert extractor.calls == [], "chatter-skip must gate the LLM extraction call"
    assert await _fact_count(db_path) == 0


# --- 5. Haiku → phi3.5 fallback when the Claude call raises ------------------


class _RaisingClaude:
    def __init__(self) -> None:
        self.called = False

    async def complete(self, messages, system_prompt, *, model=None,
                       max_tokens=None) -> str:
        self.called = True
        raise RuntimeError("claude unavailable")


class _FakeOllama:
    def __init__(self, payload: str) -> None:
        self.called = False
        self._payload = payload

    async def complete(self, messages, system_prompt, *, fmt=None) -> str:
        self.called = True
        return self._payload


async def test_phi35_fallback_when_claude_fails() -> None:
    claude = _RaisingClaude()
    ollama = _FakeOllama(
        '[{"action": "ADD", "fact": "User likes tea.", '
        '"confidence": 0.9, "subject": "user", "source": "user"}]'
    )
    extractor = LLMExtractor(claude_client=claude, ollama_client=ollama)

    result = await extractor.extract("I like tea", "Noted.")

    assert claude.called, "Claude should be attempted first"
    assert ollama.called, "phi3.5 fallback should run after Claude raises"
    assert len(result) == 1
    assert result[0].action == "ADD"
    assert result[0].fact == "User likes tea."
    assert result[0].source == "user"


async def test_unparseable_claude_falls_back_to_ollama() -> None:
    class _GarbageClaude:
        def __init__(self) -> None:
            self.called = False

        async def complete(self, *a, **k) -> str:
            self.called = True
            return "I'm afraid I can't help with that."  # no JSON array

    claude = _GarbageClaude()
    ollama = _FakeOllama('[{"action":"NOOP","fact":"","confidence":1,'
                         '"subject":"","source":"inference"}]')
    extractor = LLMExtractor(claude_client=claude, ollama_client=ollama)

    result = await extractor.extract("hi", "hello")

    assert claude.called and ollama.called, "unparseable Claude → phi3.5 fallback"
    assert len(result) == 1 and result[0].action == "NOOP"


async def test_both_llms_fail_returns_empty() -> None:
    claude = _RaisingClaude()
    ollama = _FakeOllama("")  # cold Ollama returns empty string
    extractor = LLMExtractor(claude_client=claude, ollama_client=ollama)

    result = await extractor.extract("I like tea", "Noted.")

    assert result == [], "both LLMs failing must yield [] so caller uses rules"


async def test_empty_extraction_falls_back_to_rule_distillation(tmp_path) -> None:
    """When the extractor yields nothing (both LLMs down), consolidate must
    fall back to the Phase 12A rule distillation rather than lose the write."""
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    extractor = _QueueExtractor([[]])  # empty verdict → fallback
    mgr = MemoryManager(
        db_path=db_path, vector_store=vs,
        evaluator=MemoryEvaluator(), extractor=extractor,
    )

    # "i prefer" matches the preference rule (0.75) so the pre-filter passes and
    # the extractor is consulted; its empty result triggers the rule fallback.
    fact_id = await mgr.consolidate("I prefer dark roast coffee", "Noted.")

    assert extractor.calls, "extractor should be consulted when pre-filter passes"
    assert fact_id is not None
    assert await _fact_count(db_path) == 1, "rule fallback should store one fact"


# --- 6. created_by provenance persisted ('user' vs 'inference') --------------


async def test_created_by_set_user_vs_inference(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore()
    extractor = _QueueExtractor(
        [
            [
                Extraction("ADD", "User's name is Sam.", 0.97, "user", "user"),
                # ≥0.70 so it auto-stores; mid-confidence would land in the
                # memory-capture confirm band and be held pending instead.
                Extraction("ADD", "User likely works in tech.", 0.8,
                           "user", "inference"),
            ]
        ]
    )
    mgr = MemoryManager(
        db_path=db_path, vector_store=vs,
        evaluator=_PromoteEvaluator(), extractor=extractor,
    )

    await mgr.consolidate("My name is Sam and I build software", "Hello Sam.")

    facts = await _all_facts(db_path)
    by_content = {f["content"]: f for f in facts}
    assert by_content["User's name is Sam."]["created_by"] == "user"
    assert by_content["User likely works in tech."]["created_by"] == "inference"
    # Confidence from the model is persisted too.
    assert abs(by_content["User's name is Sam."]["confidence"] - 0.97) < 1e-6


# --- 7. Defensive JSON parsing ----------------------------------------------


def test_extract_json_array_from_prose() -> None:
    raw = (
        'Sure! Here is the extraction:\n'
        '[{"action": "ADD", "fact": "User lives in Boston.", '
        '"confidence": 0.9, "subject": "user", "source": "user"}]\n'
        'Let me know if you need anything else.'
    )
    parsed = _extract_json_array(raw)
    assert isinstance(parsed, list) and len(parsed) == 1
    assert parsed[0]["fact"] == "User lives in Boston."


def test_extract_json_array_from_code_fence() -> None:
    raw = '```json\n[{"action": "NOOP", "fact": "", "confidence": 1.0}]\n```'
    parsed = _extract_json_array(raw)
    assert isinstance(parsed, list) and parsed[0]["action"] == "NOOP"


def test_extract_json_array_irrecoverable_returns_none() -> None:
    assert _extract_json_array("no json here at all") is None
    assert _extract_json_array("") is None
    assert _extract_json_array("   ") is None


async def test_invalidate_then_recall_excludes_archived_fact(tmp_path) -> None:
    """A DELETE (valid_to set) drops the fact from the recall candidate pool."""
    db_path = await _make_db(tmp_path)
    fid = await database.save_memory_fact(
        "voice", "general", "User lives in Portland.", importance=0.8,
        db_path=db_path,
    )
    assert await database.invalidate_memory_fact(fid, db_path=db_path)

    vs = _FakeVectorStore()
    vs.add("User lives in Portland.", {"fact_id": fid, "category": "general"})
    mgr = MemoryManager(db_path=db_path, vector_store=vs)
    result = await mgr.recall("where does the user live", n_recent=0, n_semantic=3)
    contents = [f["content"] for f in result.semantic_facts]
    assert contents == [], "archived (valid_to) fact must not be recalled"
