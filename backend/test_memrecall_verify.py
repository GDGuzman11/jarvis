"""Memory brain additions — verification (backend).

Targeted checks for three small Memory-brain additions:

1. ``MemoryRecallEvent`` shape, and that :meth:`MemoryManager.recall` fires it
   (fire-and-forget) carrying the just-recalled facts as graph node ids
   (``"fact:<n>"``) — and fires nothing when no fact was recalled.
2. The corrected legacy domain fallback: non-dev *signal* categories
   (``correction`` / ``decision`` / ``failure`` / ``repeated_topic``) fall back to
   ``general`` instead of masquerading as ``project``; ``app_work`` →
   ``project`` and the personal/people maps still hold.
3. The one-time ``backfill_domains`` pass: it classifies legacy NULL-``domain``
   facts via the (mocked) LLM classifier and writes ``memory_facts.domain``,
   leaves already-set domains untouched, and is a no-op (no classifier call)
   when nothing is NULL. Plus the extractor's ``classify_domains`` parsing.

All in-memory / temp-file: the vector store and LLM clients are lightweight
fakes and the hub is a recorder, so there is no API key, no network, and the
embedding model never loads.
"""

from __future__ import annotations

import asyncio
from typing import Any

from backend import main
from backend.events import MemoryRecallEvent, serialize
from backend.memory import database
from backend.memory.evaluator import MemoryEvaluator
from backend.memory.extractor import LLMExtractor
from backend.memory.manager import MemoryManager
from backend.memory.vector_store import SearchResult


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "memrecall.db")
    await database.init_db(db_path)
    return db_path


async def _insert_fact(
    db_path: str, content: str, *, category: str = "general",
    domain: str | None = None,
) -> int:
    return await database.save_memory_fact(
        "test", category, content, importance=0.8, domain=domain,
        db_path=db_path,
    )


async def _domain_of(db_path: str, fact_id: int) -> str | None:
    conn = await database.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT domain FROM memory_facts WHERE id = ?", (fact_id,)
        )
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return None if row is None else row["domain"]


class FakeHub:
    """Records every broadcast event in order."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def broadcast(self, event: Any) -> int:
        self.events.append(event)
        return 1

    def of_type(self, cls) -> list[Any]:
        return [e for e in self.events if isinstance(e, cls)]


class _RecallVectorStore:
    """Returns a fixed list of hits from ``search``; len = number of hits."""

    def __init__(self, hits: list[SearchResult]) -> None:
        self._hits = hits

    def __len__(self) -> int:
        return len(self._hits)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return list(self._hits)[:top_k]

    def add(self, text, metadata=None):  # pragma: no cover - unused here
        return 0


class _EmptyVectorStore:
    def __len__(self) -> int:
        return 0

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return []

    def add(self, text, metadata=None):  # pragma: no cover - unused here
        return 0


class _FakeClassifierExtractor:
    """Stand-in extractor exposing only ``classify_domains`` (text -> domain)."""

    def __init__(self, mapping: dict[str, str | None]) -> None:
        self._mapping = mapping
        self.calls: list[list[str]] = []

    async def classify_domains(self, fact_texts: list[str]) -> list[str | None]:
        self.calls.append(list(fact_texts))
        return [self._mapping.get(t) for t in fact_texts]


class _FakeClaude:
    """Returns a canned raw string from ``complete`` (records each call)."""

    def __init__(self, raw: str | None) -> None:
        self._raw = raw
        self.calls: list[Any] = []

    async def complete(
        self, messages, system_prompt, *, model=None, max_tokens=None
    ) -> str:
        self.calls.append((messages, system_prompt, model, max_tokens))
        if self._raw is None:
            raise RuntimeError("no claude")
        return self._raw


class _FakeOllama:
    async def complete(self, messages, system_prompt, *, fmt=None) -> str:
        raise AssertionError("ollama fallback should not be reached")


async def _drain() -> None:
    """Let scheduled fire-and-forget tasks (the recall flash) run."""
    for _ in range(5):
        await asyncio.sleep(0)


# --- 1. MemoryRecallEvent shape ---------------------------------------------


def test_memory_recall_event_shape() -> None:
    evt = MemoryRecallEvent(fact_ids=["fact:1", "fact:7"])
    d = evt.to_dict()
    assert d["type"] == "memory_recall"
    assert d["fact_ids"] == ["fact:1", "fact:7"]
    assert isinstance(d["timestamp"], str) and d["timestamp"]
    # Round-trips through the hub serializer like every other event.
    assert '"type":"memory_recall"' in serialize(evt)


# --- 1b. recall emits the flash with fact:<n> ids ---------------------------


async def test_recall_emits_flash_with_node_ids(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    fid1 = await _insert_fact(db_path, "User lives in Boston.", category="personal")
    fid2 = await _insert_fact(db_path, "User prefers tea.", category="preference")

    hits = [
        SearchResult(
            text="User lives in Boston.",
            metadata={"fact_id": fid1, "category": "personal", "importance": 0.8},
            score=0.9,
        ),
        SearchResult(
            text="User prefers tea.",
            metadata={"fact_id": fid2, "category": "preference", "importance": 0.8},
            score=0.85,
        ),
    ]
    hub = FakeHub()
    mgr = MemoryManager(
        db_path=db_path, vector_store=_RecallVectorStore(hits),
        evaluator=MemoryEvaluator(), hub=hub,
    )

    result = await mgr.recall("where do I live?", n_recent=0)
    await _drain()

    assert result.semantic_facts, "the fake hits should have been recalled"
    flashes = hub.of_type(MemoryRecallEvent)
    assert len(flashes) == 1, "recall should emit exactly one flash"
    ids = set(flashes[0].fact_ids)
    assert ids == {f"fact:{fid1}", f"fact:{fid2}"}
    assert all(s.startswith("fact:") for s in flashes[0].fact_ids)


async def test_recall_no_flash_when_nothing_recalled(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = FakeHub()
    mgr = MemoryManager(
        db_path=db_path, vector_store=_EmptyVectorStore(),
        evaluator=MemoryEvaluator(), hub=hub,
    )

    result = await mgr.recall("anything?", n_recent=0)
    await _drain()

    assert result.semantic_facts == []
    assert hub.of_type(MemoryRecallEvent) == [], "no recall ⇒ no flash"


# --- 2. corrected legacy domain fallback ------------------------------------


def test_fallback_domain_non_dev_signals_are_general() -> None:
    # The bug: these signal categories used to masquerade as 'project'.
    assert main._fallback_domain("correction") == "general"
    assert main._fallback_domain("decision") == "general"
    assert main._fallback_domain("failure") == "general"
    assert main._fallback_domain("repeated_topic") == "general"
    # Dev/app work still maps to project; personal + people maps intact.
    assert main._fallback_domain("app_work") == "project"
    assert main._fallback_domain("agent_outcome") == "project"
    assert main._fallback_domain("preference") == "personal"
    assert main._fallback_domain("instruction") == "personal"
    assert main._fallback_domain("open_loop") == "personal"
    assert main._fallback_domain("external_comm") == "people"
    # Unknown / NULL → general (colour of last resort).
    assert main._fallback_domain(None) == "general"
    assert main._fallback_domain("nonsense") == "general"


# --- 3. backfill_domains -----------------------------------------------------


async def test_backfill_sets_domain_on_null_facts(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    # A legacy personal fact whose *signal* category is a 'correction' — exactly
    # the case the old fallback mislabelled as project. domain is NULL.
    mom = await _insert_fact(
        db_path, "User's mother is named Ramona.", category="correction",
    )
    # A second NULL-domain fact the classifier can't label → stays NULL.
    misc = await _insert_fact(db_path, "Some vague note.", category="general")
    # An already-classified fact must be left untouched (and never reclassified).
    kado = await _insert_fact(
        db_path, "Backend voice pipeline refactored.", category="app_work",
        domain="kado",
    )

    classifier = _FakeClassifierExtractor(
        {"User's mother is named Ramona.": "personal", "Some vague note.": None}
    )
    mgr = MemoryManager(
        db_path=db_path, vector_store=_EmptyVectorStore(),
        evaluator=MemoryEvaluator(), extractor=classifier,
    )

    n = await mgr.backfill_domains()

    assert n == 1, "only the one labellable NULL-domain fact is backfilled"
    assert await _domain_of(db_path, mom) == "personal"
    assert await _domain_of(db_path, misc) is None, "unparseable ⇒ left NULL"
    assert await _domain_of(db_path, kado) == "kado", "set domains untouched"
    # The already-set fact was never handed to the classifier.
    assert classifier.calls == [
        ["User's mother is named Ramona.", "Some vague note."]
    ]


async def test_backfill_noop_when_no_null_domains(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    await _insert_fact(db_path, "All set.", category="general", domain="general")

    classifier = _FakeClassifierExtractor({"All set.": "personal"})
    mgr = MemoryManager(
        db_path=db_path, vector_store=_EmptyVectorStore(),
        evaluator=MemoryEvaluator(), extractor=classifier,
    )

    n = await mgr.backfill_domains()

    assert n == 0
    assert classifier.calls == [], "no NULL domains ⇒ classifier never called"


async def test_backfill_noop_without_extractor(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    await _insert_fact(db_path, "Legacy fact.", category="general")
    mgr = MemoryManager(
        db_path=db_path, vector_store=_EmptyVectorStore(),
        evaluator=MemoryEvaluator(), extractor=None,
    )
    assert await mgr.backfill_domains() == 0
    assert await _domain_of(db_path, 1) is None


# --- 3b. extractor.classify_domains parsing ---------------------------------


async def test_classify_domains_parses_indexed_categories() -> None:
    claude = _FakeClaude(
        '[{"index": 0, "category": "kado"}, {"index": 1, "category": "people"}]'
    )
    ext = LLMExtractor(claude_client=claude, ollama_client=_FakeOllama())
    out = await ext.classify_domains(
        ["Backend refactor.", "Maria is the user's colleague."]
    )
    assert out == ["kado", "people"]
    assert claude.calls, "the Haiku path should have been used"


async def test_classify_domains_drops_unknown_and_missing() -> None:
    # index 0 → invalid domain (dropped → None); index 1 absent (→ None).
    claude = _FakeClaude('[{"index": 0, "category": "banana"}]')
    ext = LLMExtractor(claude_client=claude, ollama_client=_FakeOllama())
    out = await ext.classify_domains(["one", "two"])
    assert out == [None, None]


async def test_classify_domains_empty_input_skips_llm() -> None:
    claude = _FakeClaude("[]")
    ext = LLMExtractor(claude_client=claude, ollama_client=_FakeOllama())
    assert await ext.classify_domains([]) == []
    assert claude.calls == [], "empty input must not call the model"
