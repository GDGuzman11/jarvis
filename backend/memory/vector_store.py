"""FAISS-backed vector memory for Jarvis (Phase 1 skeleton).

This module provides Jarvis's long-term semantic memory: arbitrary text plus
attached metadata is embedded with a small sentence-transformers model and
stored in a FAISS index so it can later be recalled by semantic similarity.

Design notes
------------
* **Embedding model** — ``all-MiniLM-L6-v2`` (384-dim). Small, fast, CPU-friendly
  and comfortably fits the 16GB RAM target without touching the 4GB VRAM budget.
* **Index** — ``IndexFlatIP`` over L2-normalised vectors, which makes the inner
  product equal to cosine similarity. Scores are therefore in ``[-1, 1]`` where
  higher is more similar.
* **Persistence** — the FAISS index serialises to ``data/faiss_index.bin`` and
  the parallel text/metadata payloads to ``data/faiss_index.bin.meta.json``.
  Index position ``i`` corresponds to payload ``i`` in both structures.

This is a Phase 1 skeleton: it is importable, instantiable, and round-trips
add → search → save → load, but it is not yet wired into the agent runtime or
the voice pipeline. The embedding model is loaded lazily on first use so that
merely constructing the store (e.g. during app startup or tests) stays cheap.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default on-disk location for the FAISS index. Resolves to
# ``<project root>/data/faiss_index.bin``. The directory is created on save.
DEFAULT_INDEX_PATH: Path = (
    Path(__file__).resolve().parents[2] / "data" / "faiss_index.bin"
)

# Sentence-transformers model used to embed text. 384-dimensional output.
DEFAULT_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
EMBEDDING_DIM: int = 384


@dataclass(frozen=True)
class SearchResult:
    """A single hit returned from :meth:`VectorStore.search`.

    Iterable as ``(text, metadata, score)`` so callers can unpack it like a
    tuple while still having named attributes available.
    """

    text: str
    metadata: dict[str, Any]
    score: float

    def __iter__(self):  # noqa: D105 - allows tuple-style unpacking
        yield self.text
        yield self.metadata
        yield self.score


class VectorStore:
    """Persistent FAISS vector store backed by sentence-transformers.

    Parameters
    ----------
    index_path:
        Where the FAISS index is read from / written to. The metadata sidecar
        lives next to it with a ``.meta.json`` suffix. Defaults to
        ``data/faiss_index.bin``.
    model_name:
        Name of the sentence-transformers model. Defaults to
        ``all-MiniLM-L6-v2``.

    Notes
    -----
    The embedding model and FAISS index are created lazily on first use, so
    constructing a ``VectorStore`` is cheap and import-safe.
    """

    def __init__(
        self,
        index_path: Path | str = DEFAULT_INDEX_PATH,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self.index_path: Path = Path(index_path)
        self.model_name: str = model_name

        # Parallel payload arrays; element ``i`` matches FAISS vector ``i``.
        self._texts: list[str] = []
        self._metadata: list[dict[str, Any]] = []

        # Lazily initialised heavy objects.
        self._model: Any | None = None
        self._index: Any | None = None

    # --- Lazy resources -----------------------------------------------------

    @property
    def _embedding_model(self) -> Any:
        """Return the sentence-transformers model, loading it on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def _ensure_index(self) -> Any:
        """Return the FAISS index, creating an empty one if needed."""
        if self._index is None:
            import faiss

            # Inner-product index; with normalised vectors this is cosine sim.
            self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        return self._index

    def _embed(self, text: str) -> Any:
        """Embed a single string into a normalised float32 vector (1, dim)."""
        import numpy as np

        vector = self._embedding_model.encode(
            [text], convert_to_numpy=True, normalize_embeddings=True
        )
        return np.asarray(vector, dtype="float32")

    # --- Public API ---------------------------------------------------------

    def add(self, text: str, metadata: dict[str, Any] | None = None) -> int:
        """Embed ``text`` and store it with optional ``metadata``.

        Returns the integer id (FAISS position) of the stored entry.
        """
        if not text or not text.strip():
            raise ValueError("Cannot add empty text to the vector store.")

        index = self._ensure_index()
        index.add(self._embed(text))

        self._texts.append(text)
        self._metadata.append(dict(metadata or {}))
        return len(self._texts) - 1

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return the ``top_k`` most similar entries to ``query``.

        Each result is a :class:`SearchResult`, which unpacks as
        ``(text, metadata, score)``. Returns an empty list if the store is
        empty. Scores are cosine similarities in ``[-1, 1]`` (higher = closer).
        """
        if top_k <= 0:
            raise ValueError("top_k must be a positive integer.")
        if not self._texts:
            return []

        index = self._ensure_index()
        k = min(top_k, len(self._texts))
        scores, ids = index.search(self._embed(query), k)

        results: list[SearchResult] = []
        for position, score in zip(ids[0], scores[0]):
            if position < 0:  # FAISS pads with -1 when fewer than k results.
                continue
            results.append(
                SearchResult(
                    text=self._texts[position],
                    metadata=self._metadata[position],
                    score=float(score),
                )
            )
        return results

    def __len__(self) -> int:
        """Number of entries currently stored."""
        return len(self._texts)

    # --- Persistence --------------------------------------------------------

    @property
    def _meta_path(self) -> Path:
        """Sidecar path holding the text/metadata payloads."""
        return self.index_path.with_suffix(self.index_path.suffix + ".meta.json")

    def save(self, path: Path | str | None = None) -> None:
        """Persist the FAISS index and payloads to disk.

        Writes the index to ``path`` (default :attr:`index_path`) and the
        parallel text/metadata payloads to the ``.meta.json`` sidecar.
        """
        import faiss

        target = Path(path) if path is not None else self.index_path
        meta_target = target.with_suffix(target.suffix + ".meta.json")
        target.parent.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._ensure_index(), str(target))
        meta_target.write_text(
            json.dumps(
                {
                    "model_name": self.model_name,
                    "texts": self._texts,
                    "metadata": self._metadata,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger.info("Saved vector store (%d entries) to %s", len(self), target)

    def load(self, path: Path | str | None = None) -> None:
        """Load the FAISS index and payloads from disk.

        Reads from ``path`` (default :attr:`index_path`) and its ``.meta.json``
        sidecar. Raises :class:`FileNotFoundError` if either file is missing.
        """
        import faiss

        source = Path(path) if path is not None else self.index_path
        meta_source = source.with_suffix(source.suffix + ".meta.json")

        if not source.exists():
            raise FileNotFoundError(f"FAISS index not found: {source}")
        if not meta_source.exists():
            raise FileNotFoundError(f"Vector store metadata not found: {meta_source}")

        self._index = faiss.read_index(str(source))
        payload = json.loads(meta_source.read_text(encoding="utf-8"))
        self.model_name = payload.get("model_name", self.model_name)
        self._texts = list(payload.get("texts", []))
        self._metadata = list(payload.get("metadata", []))
        logger.info("Loaded vector store (%d entries) from %s", len(self), source)


__all__ = [
    "VectorStore",
    "SearchResult",
    "DEFAULT_INDEX_PATH",
    "DEFAULT_EMBEDDING_MODEL",
    "EMBEDDING_DIM",
]
