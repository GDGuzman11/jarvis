"""Phase 16F verification — the memory brain's data source + live grow event.

Targeted checks for the Phase 16F backend deliverables:

1. ``GET /api/memory/graph`` returns well-formed nodes for BOTH sources
   (``type:"memory"`` facts + ``type:"person"`` people) and pairwise
   cosine-similarity edges among the memory neurons.
2. Only *active* facts become nodes — a ``valid_to``-stamped (archived/
   superseded) fact is excluded.
3. The edge similarity threshold and the node/edge caps are respected.
4. A missing or empty memory backend returns an empty graph without raising
   (never a 500).
5. ``MemoryManager`` emits a ``memory_update`` event on a fact add (asserted via
   a fake hub) so the brain can grow a neuron live.

Everything is in-memory / temp-file: no API key, no network, no audio device,
and the VectorStore is a lightweight fake so the heavy embedding model never
loads.
"""

from __future__ import annotations

import numpy as np

from backend import main
from backend.events import MemoryUpdateEvent
from backend.main import (
    GRAPH_EDGE_THRESHOLD,
    _compute_similarity_edges,
    memory_graph_endpoint,
)
from backend.memory import database
from backend.memory.manager import MemoryManager


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    db_path = str(tmp_path / "phase16f.db")
    await database.init_db(db_path)
    return db_path


def _unit(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype="float32")
    norm = np.linalg.norm(arr)
    return arr / norm if norm else arr


class _FakeIndex:
    """Minimal FAISS-index stand-in: reconstruct(position) -> preset vector."""

    def __init__(self, vectors: list[np.ndarray]) -> None:
        self._vectors = vectors

    def reconstruct(self, position: int) -> np.ndarray:
        return self._vectors[position]


class _FakeVectorStore:
    """VectorStore stand-in exposing the private attrs the edge builder reads.

    Mirrors the real store's ``_metadata`` (parallel to FAISS positions),
    ``_tombstoned`` set, and ``_index.reconstruct`` — without loading any model.
    """

    def __init__(
        self,
        vectors: list[np.ndarray],
        metadata: list[dict],
        tombstoned: set[int] | None = None,
    ) -> None:
        self._index = _FakeIndex(vectors)
        self._metadata = metadata
        self._tombstoned = tombstoned or set()

    def __len__(self) -> int:
        return len(self._metadata)

    def add(self, text, metadata=None):  # pragma: no cover - unused here
        self._metadata.append(dict(metadata or {}))
        return len(self._metadata) - 1


class _FakeHub:
    """Captures broadcast events for assertions; never touches a socket."""

    def __init__(self) -> None:
        self.events: list = []

    async def broadcast(self, event) -> int:
        self.events.append(event)
        return 1


async def _set_app_state(memory_manager, vector_store) -> None:
    main.app.state.memory_manager = memory_manager
    main.app.state.vector_store = vector_store


# --- 1. Endpoint returns well-formed memory + person nodes and edges ---------


async def test_graph_endpoint_returns_memory_and_person_nodes_with_edges(
    tmp_path,
) -> None:
    db_path = await _make_db(tmp_path)

    # Two near-identical facts (edge expected) + one orthogonal fact (no edge).
    a = await database.save_memory_fact(
        "voice", "general", "Gabe drinks oolong tea each morning",
        importance=0.6, db_path=db_path,
    )
    b = await database.save_memory_fact(
        "voice", "general", "Gabe enjoys oolong tea in the mornings",
        importance=0.4, db_path=db_path,
    )
    c = await database.save_memory_fact(
        "voice", "general", "The RTX 3050 has 4GB of VRAM",
        importance=0.5, db_path=db_path,
    )
    await database.save_person("Ada Lovelace", email="ada@example.com", db_path=db_path)

    # a and b point nearly the same direction (cosine ~0.999 > 0.5); c is
    # orthogonal to both (cosine 0).
    vectors = [
        _unit([1.0, 0.05, 0.0]),
        _unit([1.0, 0.04, 0.0]),
        _unit([0.0, 0.0, 1.0]),
    ]
    metadata = [{"fact_id": a}, {"fact_id": b}, {"fact_id": c}]
    vs = _FakeVectorStore(vectors, metadata)
    mm = MemoryManager(db_path=db_path, vector_store=vs)
    await _set_app_state(mm, vs)

    graph = await memory_graph_endpoint()
    nodes = graph["nodes"]
    edges = graph["edges"]

    by_type: dict[str, list] = {"memory": [], "person": []}
    for node in nodes:
        by_type.setdefault(node["type"], []).append(node)

    # Both sources present.
    assert len(by_type["memory"]) == 3
    assert len(by_type["person"]) == 1

    # Memory node shape (extensible: id namespaced by type).
    mem = next(n for n in by_type["memory"] if n["id"] == f"fact:{a}")
    for key in (
        "id", "type", "text_preview", "text_full", "importance",
        "access_count", "confidence", "created_at", "last_recalled_at",
        "conflicting_fact_ids", "subject", "category",
    ):
        assert key in mem
    assert mem["text_full"].startswith("Gabe drinks oolong")

    # Person node shape.
    person = by_type["person"][0]
    assert person["id"].startswith("person:")
    assert person["name"] == "Ada Lovelace"

    # Exactly the a<->b edge survives the 0.5 threshold; c connects to nothing.
    assert len(edges) == 1
    edge = edges[0]
    assert {edge["source_id"], edge["target_id"]} == {f"fact:{a}", f"fact:{b}"}
    assert edge["similarity"] > GRAPH_EDGE_THRESHOLD
    assert not any(f"fact:{c}" in (e["source_id"], e["target_id"]) for e in edges)


# --- 2. Only active facts become nodes --------------------------------------


async def test_graph_excludes_archived_facts(tmp_path) -> None:
    db_path = await _make_db(tmp_path)

    active = await database.save_memory_fact(
        "voice", "general", "Active fact stays a neuron", db_path=db_path,
    )
    archived = await database.save_memory_fact(
        "voice", "general", "Archived fact is gone", db_path=db_path,
    )
    # Stamp valid_to on the second fact (supersede/DELETE path).
    assert await database.invalidate_memory_fact(archived, db_path=db_path)

    vs = _FakeVectorStore([], [])
    mm = MemoryManager(db_path=db_path, vector_store=vs)
    await _set_app_state(mm, vs)

    graph = await memory_graph_endpoint()
    ids = {n["id"] for n in graph["nodes"]}
    assert f"fact:{active}" in ids
    assert f"fact:{archived}" not in ids

    # The DB helper applies the same active filter directly.
    facts = await database.get_graph_facts(db_path=db_path)
    assert {f["id"] for f in facts} == {active}


# --- 3a. Edge threshold is respected ----------------------------------------


async def test_edges_respect_similarity_threshold() -> None:
    # Three unit vectors: 0 and 1 similar (>0.5), 2 orthogonal to both.
    vectors = [_unit([1.0, 0.1, 0.0]), _unit([1.0, 0.0, 0.0]), _unit([0.0, 0.0, 1.0])]
    metadata = [{"fact_id": 10}, {"fact_id": 11}, {"fact_id": 12}]
    vs = _FakeVectorStore(vectors, metadata)
    active = {"fact:10", "fact:11", "fact:12"}

    edges = _compute_similarity_edges(vs, active, GRAPH_EDGE_THRESHOLD, 2000)
    assert len(edges) == 1
    assert {edges[0]["source_id"], edges[0]["target_id"]} == {"fact:10", "fact:11"}


# --- 3b. Tombstoned vectors are skipped -------------------------------------


async def test_edges_skip_tombstoned_vectors() -> None:
    vectors = [_unit([1.0, 0.1, 0.0]), _unit([1.0, 0.0, 0.0])]
    metadata = [{"fact_id": 20}, {"fact_id": 21}]
    # Tombstone position 1 → only one live vector → no pair → no edge.
    vs = _FakeVectorStore(vectors, metadata, tombstoned={1})
    edges = _compute_similarity_edges(
        vs, {"fact:20", "fact:21"}, GRAPH_EDGE_THRESHOLD, 2000
    )
    assert edges == []


# --- 3c. Edge cap is respected ----------------------------------------------


async def test_edges_respect_max_cap() -> None:
    # Five nearly-identical vectors → 10 candidate pairs all > 0.5; cap to 3.
    vectors = [_unit([1.0, 0.01 * i, 0.0]) for i in range(5)]
    metadata = [{"fact_id": 100 + i} for i in range(5)]
    active = {f"fact:{100 + i}" for i in range(5)}
    vs = _FakeVectorStore(vectors, metadata)

    edges = _compute_similarity_edges(vs, active, GRAPH_EDGE_THRESHOLD, 3)
    assert len(edges) == 3
    # Kept edges are the strongest (sorted desc before truncation).
    sims = [e["similarity"] for e in edges]
    assert sims == sorted(sims, reverse=True)


# --- 3d. Node cap is respected (DB helper) ----------------------------------


async def test_graph_facts_respect_node_limit(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    for i in range(5):
        await database.save_memory_fact(
            "voice", "general", f"Fact number {i}", importance=0.5, db_path=db_path,
        )
    facts = await database.get_graph_facts(limit=2, db_path=db_path)
    assert len(facts) == 2


# --- 4. Empty / missing backend returns an empty graph, never a 500 ---------


async def test_graph_endpoint_missing_manager_returns_empty(tmp_path) -> None:
    main.app.state.memory_manager = None
    main.app.state.vector_store = None
    graph = await memory_graph_endpoint()
    assert graph == {"nodes": [], "edges": []}


async def test_graph_endpoint_empty_store_returns_nodes_no_edges(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    await database.save_memory_fact(
        "voice", "general", "A lone fact with no vectors", db_path=db_path,
    )
    vs = _FakeVectorStore([], [])  # empty store → no edges
    mm = MemoryManager(db_path=db_path, vector_store=vs)
    await _set_app_state(mm, vs)

    graph = await memory_graph_endpoint()
    assert len(graph["nodes"]) == 1
    assert graph["edges"] == []


def test_compute_edges_on_unreconstructable_store_returns_empty() -> None:
    # A store with no _metadata at all → defensive empty result, no raise.
    class _Bare:
        pass

    assert _compute_similarity_edges(_Bare(), {"fact:1"}, 0.5, 2000) == []


# --- 5. memory_update is emitted on a fact add ------------------------------


async def test_memory_update_emitted_on_fact_add(tmp_path) -> None:
    db_path = await _make_db(tmp_path)
    hub = _FakeHub()
    vs = _FakeVectorStore([], [])
    mm = MemoryManager(db_path=db_path, vector_store=vs, hub=hub)

    fact_id = await mm.store_fact(
        "Gabe prefers dark mode", category="preference", importance=0.9
    )
    assert fact_id is not None

    updates = [e for e in hub.events if isinstance(e, MemoryUpdateEvent)]
    assert len(updates) == 1
    event = updates[0]
    assert event.action == "add"
    assert event.node is not None
    assert event.node["id"] == f"fact:{fact_id}"
    assert event.node["type"] == "memory"
    assert event.node["text_full"] == "Gabe prefers dark mode"
    # Serialisable on the wire (the hub will json.dumps it).
    assert '"memory_update"' in event.to_json()


async def test_no_hub_means_no_emit_and_no_error(tmp_path) -> None:
    # A manager built without a hub (every pre-16F caller/test) must still work.
    db_path = await _make_db(tmp_path)
    vs = _FakeVectorStore([], [])
    mm = MemoryManager(db_path=db_path, vector_store=vs)  # no hub
    fact_id = await mm.store_fact("Hub-less fact", category="general")
    assert fact_id is not None
