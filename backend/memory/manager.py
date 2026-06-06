"""MemoryManager — the single coordinator for Jarvis's three memory layers.

Phase 12 introduces a tiered memory architecture:

* **Layer 1 — Working memory**  (per-turn, in-RAM): the live exchange. Owned by
  the caller (voice pipeline / agents); this manager *feeds* it via :meth:`recall`.
* **Layer 2 — Episodic memory** (SQLite ``conversations``): the raw diary. Every
  user utterance and Jarvis reply is written here, time-indexed.
* **Layer 3 — Semantic memory** (FAISS + ``memory_facts``): distilled, high-value
  facts searched by meaning, not time.

:class:`MemoryManager` is the *only* interface the rest of the system talks to for
memory — no component reaches into SQLite or FAISS directly. It owns the
:class:`~backend.memory.evaluator.MemoryEvaluator` and the
:class:`~backend.memory.vector_store.VectorStore`, and exposes:

* :meth:`store`       — always write to Layer 2; conditionally promote to Layer 3.
* :meth:`recall`      — blend recent episodic turns + semantically-similar facts.
* :meth:`consolidate` — evaluate an exchange and, if important, distil + persist it.
* :meth:`format_context` — render recalled memory into the system-prompt block.

This is Phase 12A: the plumbing is complete and independently usable, but it is
not yet *called* by the voice pipeline (12B) or agents (12C). Construction is
cheap — the heavy embedding model inside the vector store still loads lazily.

Threading note
--------------
FAISS / sentence-transformers calls are synchronous and CPU-bound. They are kept
off the event loop via :func:`asyncio.to_thread` so a memory write never blocks
the spoken response.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.logging_config import get_logger
from backend.memory import database
from backend.memory.evaluator import MemoryEvaluator
from backend.memory.vector_store import VectorStore

log = get_logger(__name__)

# Default blend sizes for a recall (Phase 12 Rule 6 caps: <=10 episodic, <=5
# semantic). These are the per-call defaults; callers may request fewer.
DEFAULT_N_RECENT: int = 10
DEFAULT_N_SEMANTIC: int = 3

# Minimum cosine similarity for a semantic hit to be considered relevant enough
# to inject. Below this the memory is likely noise and is dropped.
MIN_SEMANTIC_SCORE: float = 0.25


@dataclass
class RecallResult:
    """The blended memory context returned by :meth:`MemoryManager.recall`.

    Attributes
    ----------
    episodic_messages:
        Recent conversation turns formatted as Anthropic ``messages[]`` entries
        (``{"role": "user"|"assistant", "content": str}``), oldest-first — ready
        to prepend to the current turn's messages list.
    semantic_facts:
        The distilled facts recalled by semantic similarity, each a
        ``{"content": str, "category": str, "score": float}`` dict.
    formatted_context:
        A ready-to-inject string for the system prompt's ``# Current context``
        block (see :meth:`MemoryManager.format_context`).
    """

    episodic_messages: list[dict[str, Any]] = field(default_factory=list)
    semantic_facts: list[dict[str, Any]] = field(default_factory=list)
    formatted_context: str = ""


class MemoryManager:
    """Coordinates episodic (SQLite) and semantic (FAISS) memory for Jarvis.

    Parameters
    ----------
    db_path:
        Path to the SQLite database. Threaded through to every database helper
        (tests point this at a temp file).
    vector_store:
        The shared :class:`VectorStore` instance (constructed once at startup).
    evaluator:
        Optional injected :class:`MemoryEvaluator`; a default one is created when
        omitted.
    """

    def __init__(
        self,
        db_path: str | Path,
        vector_store: VectorStore,
        *,
        evaluator: MemoryEvaluator | None = None,
    ) -> None:
        self._db_path = db_path
        self._vector_store = vector_store
        self._evaluator = evaluator or MemoryEvaluator()

    # --- Database kwargs ----------------------------------------------------

    def _db_kwargs(self) -> dict[str, Any]:
        """Pass ``db_path`` to database helpers only when explicitly set."""
        return {"db_path": self._db_path} if self._db_path is not None else {}

    # --- Layer 2: always write episodic; optionally promote to semantic -----

    async def store(
        self,
        text: str,
        role: str,
        channel: str = "voice",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Write one turn to episodic memory (Layer 2). Returns the row id.

        Every utterance is persisted to ``conversations`` unconditionally — this
        is the raw diary (Phase 12 Rule 1). Promotion to semantic memory is a
        *separate* decision made by :meth:`consolidate` over a full
        user+reply exchange, so a single ``store`` never scores in isolation.

        ``role`` accepts ``'user'``, ``'jarvis'`` or ``'assistant'`` (the
        database layer normalises the alias). ``channel`` is ``'voice'`` or
        ``'text'``. ``metadata`` is accepted for forward-compatibility (Phase
        12B/12D attach source detail) and is currently advisory only.
        """
        text = (text or "").strip()
        if not text:
            return -1
        row_id = await database.save_conversation(
            role,
            text,
            channel=channel,
            **self._db_kwargs(),
        )
        log.info("memory_store", role=role, channel=channel, conv_id=row_id)
        return row_id

    # --- Layer 3: store a pre-distilled fact directly -----------------------

    async def store_fact(
        self,
        content: str,
        *,
        source: str = "agent",
        category: str = "general",
        importance: float = 1.0,
        agent_id: str | None = None,
    ) -> int | None:
        """Promote a ready-made fact straight into semantic memory (Layer 3).

        Unlike :meth:`consolidate`, this skips the evaluator — the caller has
        already decided the content is worth keeping. Used for the audit-log hook
        (Phase 12 Rule 2: every logged agent action is, by definition, a
        high-value event and auto-promotes at importance 1.0). Writes a
        ``memory_facts`` row and mirrors the text into FAISS so semantic recall
        can find it, keeping the two stores in sync.

        Returns the ``memory_facts`` row id, or ``None`` on empty content or a
        backend failure (never raises — a memory write must not break a turn).
        """
        content = (content or "").strip()
        if not content:
            return None
        try:
            fact_id = await database.save_memory_fact(
                source,
                category,
                content,
                importance=importance,
                agent_id=agent_id,
                **self._db_kwargs(),
            )
            await asyncio.to_thread(
                self._vector_store.add,
                content,
                {
                    "fact_id": fact_id,
                    "category": category,
                    "source": source,
                    "importance": importance,
                },
            )
            log.info(
                "memory_store_fact", category=category, source=source, fact_id=fact_id
            )
            return fact_id
        except Exception:  # noqa: BLE001 — fact storage must never break a turn
            log.warning("memory_store_fact_failed", exc_info=True)
            return None

    # --- Layer 3: evaluate + distil + persist a full exchange ---------------

    async def consolidate(
        self,
        user_text: str,
        reply: str,
        *,
        source: str = "voice",
        agent_id: str | None = None,
    ) -> int | None:
        """Score an exchange and, if important, distil + persist it (Layer 3).

        Runs the :class:`MemoryEvaluator` over the ``(user_text, reply)`` pair.
        When the score is at or above the promotion threshold (0.65) the exchange
        is distilled into a compact fact, written to ``memory_facts`` and added to
        the FAISS vector store (kept in sync per Phase 12). Returns the
        ``memory_facts`` row id when promoted, else ``None``.

        Safe to run as a fire-and-forget ``asyncio.create_task`` — it never
        raises into the caller and adds no latency to the spoken response.
        """
        try:
            score, category = self._evaluator.score(user_text, reply)
            if score < self._evaluator.threshold:
                log.info("memory_consolidate_skip", category=category, score=score)
                return None

            fact = self._evaluator.extract_fact(user_text, reply, category)
            if not fact.strip():
                return None

            fact_id = await database.save_memory_fact(
                source,
                category,
                fact,
                importance=score,
                agent_id=agent_id,
                **self._db_kwargs(),
            )

            # Mirror into FAISS so semantic recall can find it. The vector store
            # is synchronous + CPU-bound, so run it off the event loop.
            await asyncio.to_thread(
                self._vector_store.add,
                fact,
                {
                    "fact_id": fact_id,
                    "category": category,
                    "source": source,
                    "importance": score,
                },
            )
            log.info(
                "memory_consolidate_promote",
                category=category,
                score=score,
                fact_id=fact_id,
            )
            return fact_id
        except Exception:  # noqa: BLE001 — consolidation must never break a turn
            log.warning("memory_consolidate_failed", exc_info=True)
            return None

    # --- Recall: blend Layer 2 (recent) + Layer 3 (semantic) ----------------

    async def recall(
        self,
        query: str,
        n_recent: int = DEFAULT_N_RECENT,
        n_semantic: int = DEFAULT_N_SEMANTIC,
    ) -> RecallResult:
        """Return blended context from episodic + semantic memory.

        * Episodic: the last ``n_recent`` conversation turns, formatted as
          Anthropic ``messages[]`` entries (oldest-first) ready to prepend.
        * Semantic: the top ``n_semantic`` facts most similar to ``query`` from
          the vector store, filtered to those above :data:`MIN_SEMANTIC_SCORE`.

        The result also carries a ``formatted_context`` string for system-prompt
        injection (see :meth:`format_context`). Never raises — a memory backend
        failure degrades to an empty result so reasoning can still proceed.
        """
        episodic_messages: list[dict[str, Any]] = []
        semantic_facts: list[dict[str, Any]] = []

        # Layer 2 — recent episodic turns.
        if n_recent > 0:
            try:
                rows = await database.get_recent_conversations(
                    limit=n_recent, **self._db_kwargs()
                )
                episodic_messages = [
                    {
                        "role": "assistant" if row["role"] == "jarvis" else "user",
                        "content": row["content"],
                    }
                    for row in rows
                ]
            except Exception:  # noqa: BLE001
                log.warning("memory_recall_episodic_failed", exc_info=True)

        # Layer 3 — semantic similarity over distilled facts.
        if n_semantic > 0 and query and query.strip() and len(self._vector_store):
            try:
                hits = await asyncio.to_thread(
                    self._vector_store.search, query, n_semantic
                )
                for hit in hits:
                    if hit.score < MIN_SEMANTIC_SCORE:
                        continue
                    semantic_facts.append(
                        {
                            "content": hit.text,
                            "category": hit.metadata.get("category", "general"),
                            "score": hit.score,
                        }
                    )
            except Exception:  # noqa: BLE001
                log.warning("memory_recall_semantic_failed", exc_info=True)

        result = RecallResult(
            episodic_messages=episodic_messages,
            semantic_facts=semantic_facts,
        )
        result.formatted_context = self.format_context(result)
        return result

    # --- Context formatting for the system prompt ---------------------------

    def format_context(self, recalled: RecallResult) -> str:
        """Render recalled memory into the ``# Current context`` block.

        Produces the structured string injected into the system prompt: the
        current date/time, the distilled facts Jarvis "remembers about you", and
        a compact transcript of the recent conversation. Returns an empty string
        when there is nothing to inject (so the cached stable prefix of the
        system prompt stays byte-identical on a cold first turn).
        """
        sections: list[str] = []
        now = datetime.now().strftime("%Y-%m-%d, %H:%M")
        sections.append(f"# Current context\nDate: {now}")

        if recalled.semantic_facts:
            lines = [f"- {fact['content']}" for fact in recalled.semantic_facts]
            sections.append("## What I remember about you\n" + "\n".join(lines))

        if recalled.episodic_messages:
            turns: list[str] = []
            for msg in recalled.episodic_messages:
                speaker = "Jarvis" if msg["role"] == "assistant" else "User"
                turns.append(f"[{speaker}]: {msg['content']}")
            sections.append("## Recent conversation\n" + "\n".join(turns))

        # Only the date header present means nothing meaningful was recalled.
        if len(sections) == 1:
            return ""
        return "\n\n".join(sections)


__all__ = [
    "MemoryManager",
    "RecallResult",
    "DEFAULT_N_RECENT",
    "DEFAULT_N_SEMANTIC",
    "MIN_SEMANTIC_SCORE",
]
