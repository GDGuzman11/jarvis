"""Base class for every Jarvis background agent.

Each of the 6 background agents (the Production Lead plus five specialists) is a
long-lived asyncio task that loops forever:

    pull a task off its queue -> set status ``working`` -> handle it ->
    record the result -> set status ``idle`` -> block until the next task

This module owns the machinery shared by all of them so the concrete agents only
have to provide a persona and an implementation of :meth:`handle_task`.

What :class:`BaseAgent` gives a subclass
----------------------------------------
* **A task queue** — an :class:`asyncio.Queue` fed by :meth:`enqueue_task`. The
  run loop drains it one task at a time, so a single agent never processes two
  tasks concurrently (state stays simple and predictable).
* **A tool access list** — the names of the tools this agent is permitted to
  use. The actual tool *registry* and permission enforcement land in Phase 6;
  this list is the per-agent allowlist those will consult.
* **Claude context** — a rolling conversation history (``self._context``) so an
  agent's successive tasks can build on one another. Trimmed to a bounded window
  so it never grows without limit.
* **Status** — one of ``idle | working | error | offline`` (mirrors the
  ``agents.status`` CHECK constraint in :mod:`backend.memory.database`). Every
  transition is, in one place:
    1. broadcast as an :class:`~backend.events.AgentUpdate` over the WebSocket
       hub (drives the Agents window's live cards), and
    2. persisted via :func:`~backend.memory.database.upsert_agent` (so state
       survives a backend restart — Phase 4 requirement), and
    3. written to the ``audit_log`` as metadata only (Security Rule 6).

Resilience
----------
A task that raises does not kill the agent: the exception is logged, the agent
flips to ``error`` briefly (broadcast + audit), the originating ``tasks`` row is
marked ``failed``, and the loop continues to the next task. The agent only stops
when :meth:`stop` cancels its run loop.

Reasoning model
---------------
Concrete agents reason with the shared :class:`~backend.ai.claude_client.ClaudeClient`
and degrade to the local :class:`~backend.ai.ollama_client.OllamaClient` when the
Claude API is unavailable, mirroring the rest of the backend. :meth:`reason`
implements that Claude-then-Ollama fallback once so subclasses don't repeat it.
"""

from __future__ import annotations

import abc
import asyncio
from typing import Any

from backend.ai.claude_client import ClaudeAPIError, ClaudeClient
from backend.ai.ollama_client import OllamaClient
from backend.ai.persona import build_system_prompt
from backend.events import AgentStatus, AgentUpdate
from backend.logging_config import get_logger
from backend.memory import database
from backend.memory.manager import MemoryManager
from backend.memory.vector_store import VectorStore
from backend.websocket_hub import ConnectionHub
from backend.websocket_hub import hub as default_hub

log = get_logger(__name__)

# How many of the most recent conversation turns an agent keeps in its rolling
# Claude context. Bounded so a long-running agent's prompt never grows without
# limit (and the cached system-prompt prefix keeps paying off).
DEFAULT_CONTEXT_TURNS: int = 20

# How many of the most recent persisted messages an agent reloads from the
# ``conversations`` table on startup, so its rolling context survives a restart
# (Phase 12C — context restore). Half a turn each, so 12 messages ≈ 6 exchanges.
RESTORE_CONTEXT_MESSAGES: int = 12


class BaseAgent(abc.ABC):
    """Abstract base for a single long-lived Jarvis agent.

    Parameters
    ----------
    agent_id:
        Stable slug, the primary key in the ``agents`` table (e.g.
        ``"backend"``). Used everywhere an agent must be addressed.
    name:
        Human display name shown in the Agents window (e.g. ``"Kado"``).
    role:
        One-line description of the agent's remit.
    tools:
        The names of tools this agent is allowed to use. The Phase 6 tool
        registry consults this allowlist; here it is carried and reported.
    hub:
        WebSocket hub to broadcast :class:`AgentUpdate` events on. Defaults to
        the process-wide singleton; injectable for tests.
    claude / ollama:
        Reasoning clients. Default to fresh lazy instances (no credentials are
        touched until first use), injectable for tests.
    db_path:
        Override the SQLite path (tests point this at a temp file).
    vector_store:
        Shared FAISS semantic memory (Phase 12). Carried for the upcoming memory
        integration; accepted and stored here, used in Phase 12C.
    memory_manager:
        Shared :class:`MemoryManager` coordinating episodic + semantic memory
        (Phase 12). Accepted and stored here; recall/store wiring lands in
        Phase 12C. No behaviour change yet.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        *,
        tools: list[str] | None = None,
        hub: ConnectionHub | None = None,
        claude: ClaudeClient | None = None,
        ollama: OllamaClient | None = None,
        db_path: Any | None = None,
        vector_store: VectorStore | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.tools: list[str] = list(tools or [])

        self._hub = hub or default_hub
        self._claude = claude or ClaudeClient()
        self._ollama = ollama or OllamaClient()
        self._db_path = db_path

        # Phase 12 memory components. Stored now, wired into reasoning in 12C.
        self.vector_store = vector_store
        self.memory_manager = memory_manager

        # The per-agent inbound work queue. Each item is a task ``dict`` (see
        # :meth:`enqueue_task`). Drained one at a time by the run loop.
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        # Rolling Claude conversation history for this agent (Anthropic message
        # format). Bounded to the most recent DEFAULT_CONTEXT_TURNS entries.
        self._context: list[dict[str, Any]] = []

        # Lifecycle: the background run-loop task and the current status. Status
        # starts ``offline`` until :meth:`start` brings the agent up.
        self._task: asyncio.Task[None] | None = None
        self._status: AgentStatus = "offline"
        self._current_task_label: str | None = None

    # --- Public properties --------------------------------------------------

    @property
    def status(self) -> AgentStatus:
        """The agent's current status (``idle | working | error | offline``)."""
        return self._status

    @property
    def queue_size(self) -> int:
        """Number of tasks waiting in this agent's queue (not yet started)."""
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        """``True`` while the background run loop is live."""
        return self._task is not None and not self._task.done()

    # --- Database keyword args ----------------------------------------------

    def _db_kwargs(self) -> dict[str, Any]:
        """Pass-through ``db_path`` to database helpers only when overridden.

        Keeping this conditional means production code uses the module default
        path while tests can redirect every write to a temp database by passing
        ``db_path=`` once to the constructor.
        """
        return {"db_path": self._db_path} if self._db_path is not None else {}

    # --- Lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Bring the agent online and launch its background run loop.

        Persists the agent's row (so it exists in the DB even before its first
        task) and transitions it to ``idle``. Idempotent: calling ``start`` on an
        already-running agent is a no-op.
        """
        if self.is_running:
            return
        # Ensure the agent's row exists / is current before we start serving.
        await self._set_status("idle", task_label=None)
        # Restore this agent's rolling context from the conversations table so it
        # survives a backend restart (Phase 12C). No-op on a cold/empty DB.
        await self._restore_context()
        self._task = asyncio.create_task(self._run(), name=f"agent:{self.agent_id}")
        log.info("agent_started", agent_id=self.agent_id, name=self.name)

    async def _restore_context(self) -> None:
        """Reload the agent's last persisted turns into the rolling context.

        Loads up to :data:`RESTORE_CONTEXT_MESSAGES` of *this agent's own*
        conversation turns (``channel = 'agent:<id>'``), oldest-first, and seeds
        ``self._context`` with them in Anthropic message shape. On a fresh
        install (no rows) ``self._context`` stays the empty list it started as,
        exactly as before — graceful first-boot behaviour. Best-effort: a read
        failure leaves the context empty rather than blocking startup.
        """
        try:
            rows = await database.get_recent_conversations(
                limit=RESTORE_CONTEXT_MESSAGES,
                channel=self._channel,
                **self._db_kwargs(),
            )
        except Exception:  # noqa: BLE001 — never block startup on a read error
            log.warning(
                "agent_context_restore_failed",
                agent_id=self.agent_id,
                exc_info=True,
            )
            return
        if not rows:
            return
        self._context = [
            {
                "role": "assistant" if row["role"] == "jarvis" else "user",
                "content": row["content"],
            }
            for row in rows
        ]
        log.info(
            "agent_context_restored",
            agent_id=self.agent_id,
            messages=len(self._context),
        )

    async def stop(self) -> None:
        """Cancel the run loop and mark the agent ``offline``.

        Awaits the loop's cancellation so the caller knows the agent is fully
        stopped on return. Safe to call when not running.
        """
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._set_status("offline", task_label=None)
        log.info("agent_stopped", agent_id=self.agent_id, name=self.name)

    def enqueue_task(self, task: dict[str, Any]) -> None:
        """Add a task to this agent's queue.

        A task is a ``dict`` carrying at least a ``description``; it may also
        carry a ``task_id`` (the originating ``tasks`` row, updated as the task
        progresses), a ``title``, and a ``created_by`` agent id. Non-blocking —
        the unbounded queue accepts the task immediately; the run loop picks it
        up when it next becomes free.
        """
        self._queue.put_nowait(task)
        log.info(
            "agent_task_enqueued",
            agent_id=self.agent_id,
            task_id=task.get("task_id"),
            pending=self._queue.qsize(),
        )

    # --- The run loop -------------------------------------------------------

    async def _run(self) -> None:
        """Forever: pull a task, run it, report the result, go idle.

        This is the body of the agent's asyncio task. It only exits on
        cancellation (from :meth:`stop`). Any exception from
        :meth:`handle_task` is contained so one bad task can't take the agent
        down.
        """
        while True:
            task = await self._queue.get()
            try:
                await self._process_one(task)
            finally:
                self._queue.task_done()

    async def _process_one(self, task: dict[str, Any]) -> None:
        """Execute a single task end-to-end, updating status and the DB row."""
        task_id = task.get("task_id")
        label = task.get("title") or task.get("description", "")
        label = (label or "").splitlines()[0][:120] if label else None

        await self._set_status("working", task_label=label)
        await self._log_audit("task.start", target=self._task_target(task_id))
        if task_id is not None:
            await database.update_task_status(
                task_id, "in_progress", **self._db_kwargs()
            )

        try:
            result = await self.handle_task(task)
        except Exception as exc:  # noqa: BLE001 — contain so the loop survives
            log.error(
                "agent_task_failed",
                agent_id=self.agent_id,
                task_id=task_id,
                error=str(exc),
                exc_info=True,
            )
            # Surface the error state briefly, mark the row failed, then recover.
            await self._set_status("error", task_label=label)
            await self._log_audit("task.failed", target=self._task_target(task_id))
            if task_id is not None:
                await database.update_task_status(
                    task_id, "failed", result=str(exc)[:1000], **self._db_kwargs()
                )
        else:
            await self._log_audit("task.done", target=self._task_target(task_id))
            if task_id is not None:
                await database.update_task_status(
                    task_id, "completed", result=result[:4000], **self._db_kwargs()
                )
        finally:
            # Back to idle and ready for the next task regardless of outcome.
            await self._set_status("idle", task_label=None)

    # --- Subclass contract --------------------------------------------------

    @abc.abstractmethod
    async def handle_task(self, task: dict[str, Any]) -> str:
        """Process one task and return a short result string.

        Subclasses implement their specialism here, typically by calling
        :meth:`reason` with their persona system prompt. The returned string is
        recorded as the task result (truncated) in the ``tasks`` table and is
        what a delegating agent (the Production Lead) can relay back.
        """
        raise NotImplementedError

    # --- Reasoning (Claude with Ollama fallback) ----------------------------

    async def reason(self, prompt: str, system_prompt: str | None = None) -> str:
        """Reason over ``prompt`` and return the full response text.

        Streams from Claude (tokens fan out to the Reasoning window via the
        client's own broadcast), accumulating the text to return. On a
        :class:`ClaudeAPIError` it degrades to the local Ollama model, exactly as
        the rest of the backend does. The exchange is appended to this agent's
        rolling context so successive tasks build on one another.

        Memory integration (Phase 12C)
        ------------------------------
        When a :class:`MemoryManager` is wired in, the agent recalls shared
        memory *before* the Claude call — a few recent episodic turns plus the
        most semantically-relevant facts — and injects the recalled facts into
        the system prompt's ``# Current context`` block. After the response it
        stores both sides to episodic memory and fires off (non-blocking)
        consolidation so important exchanges promote to semantic memory. Without
        a memory manager the behaviour is unchanged: the agent's in-RAM rolling
        context is the only history and the caller's ``system_prompt`` is used
        verbatim.

        Returns an empty string only if both Claude and Ollama produce nothing
        (e.g. Ollama is also cold) — never raises for a model failure.
        """
        if self.memory_manager is not None:
            recalled = await self.memory_manager.recall(
                query=prompt,
                n_recent=6,  # fewer than voice — agents have longer task context
                n_semantic=3,
            )
            messages = (
                recalled.episodic_messages
                + self._context
                + [{"role": "user", "content": prompt}]
            )
            base_context = recalled.formatted_context
            if system_prompt and base_context:
                effective_system = f"{system_prompt}\n\n{base_context}"
            elif system_prompt:
                effective_system = system_prompt
            else:
                effective_system = build_system_prompt(context=base_context)
        else:
            messages = self._context + [{"role": "user", "content": prompt}]
            effective_system = system_prompt or build_system_prompt()

        chunks: list[str] = []
        try:
            async for token in self._claude.stream_response(
                messages, effective_system
            ):
                chunks.append(token)
        except ClaudeAPIError:
            log.warning(
                "agent_claude_unavailable_fallback_ollama", agent_id=self.agent_id
            )
            chunks.clear()
            async for token in self._ollama.stream_response(
                messages, effective_system
            ):
                chunks.append(token)

        reply = "".join(chunks).strip()
        # Record both sides so the agent's context carries forward, then trim.
        self._remember(prompt, reply)

        # Promote the exchange into shared memory (Layer 2 episodic write happens
        # via _remember's checkpoint; here we additionally distil to Layer 3).
        if self.memory_manager is not None:
            try:
                await self.memory_manager.store(
                    prompt, role="user", channel=self._channel
                )
                if reply:
                    await self.memory_manager.store(
                        reply, role="jarvis", channel=self._channel
                    )
                    asyncio.create_task(
                        self.memory_manager.consolidate(
                            prompt,
                            reply,
                            source="agent",
                            agent_id=self.agent_id,
                        )
                    )
            except Exception:  # noqa: BLE001 — memory must never break a task
                log.warning(
                    "agent_memory_store_failed", agent_id=self.agent_id, exc_info=True
                )
        return reply

    def _remember(self, user_text: str, assistant_text: str) -> None:
        """Append a user/assistant exchange to context and persist a checkpoint.

        The in-RAM rolling window (``self._context``) is updated and trimmed so
        successive tasks build on one another. The exchange is *also* written to
        the ``conversations`` table under this agent's ``agent:<id>`` channel so
        the context survives a backend restart (Phase 12C — context checkpoint).

        When a :class:`MemoryManager` is wired in, the episodic write is its
        responsibility (it happens in :meth:`reason` via ``store``), so the
        checkpoint here is skipped to avoid a duplicate ``conversations`` row.
        Without a memory manager this is the only durable record, so it always
        writes. The DB write is fire-and-forget — it never blocks the task loop.
        """
        self._context.append({"role": "user", "content": user_text})
        if assistant_text:
            self._context.append({"role": "assistant", "content": assistant_text})
        # Keep only the most recent N turns (each turn is up to 2 messages).
        max_messages = DEFAULT_CONTEXT_TURNS * 2
        if len(self._context) > max_messages:
            self._context = self._context[-max_messages:]

        # Persist a checkpoint to the conversations table so the agent's context
        # survives a restart. Skipped when a memory manager already owns the
        # episodic write (avoids duplicating the row).
        if self.memory_manager is None:
            asyncio.create_task(
                self._checkpoint_context(user_text, assistant_text)
            )

    async def _checkpoint_context(
        self, user_text: str, assistant_text: str
    ) -> None:
        """Write a user/assistant exchange to ``conversations`` for restart.

        Both turns are stored under ``channel = 'agent:<id>'`` so an agent can
        later restore *only its own* history. Best-effort: a DB hiccup must never
        take down the agent's run loop.
        """
        try:
            if user_text and user_text.strip():
                await database.save_conversation(
                    "user",
                    user_text,
                    channel=self._channel,
                    **self._db_kwargs(),
                )
            if assistant_text and assistant_text.strip():
                await database.save_conversation(
                    "jarvis",
                    assistant_text,
                    channel=self._channel,
                    **self._db_kwargs(),
                )
        except Exception:  # noqa: BLE001 — checkpoint must never break the loop
            log.warning(
                "agent_context_checkpoint_failed",
                agent_id=self.agent_id,
                exc_info=True,
            )

    @property
    def _channel(self) -> str:
        """The ``conversations.channel`` value identifying this agent's turns."""
        return f"agent:{self.agent_id}"

    # --- Status transitions (broadcast + persist + audit) -------------------

    async def _set_status(
        self, status: AgentStatus, *, task_label: str | None
    ) -> None:
        """Transition status and fan the change out everywhere it must go.

        One funnel for every status change so the three side effects — broadcast,
        DB upsert, and the live ``current_task`` label — never drift apart.
        """
        self._status = status
        self._current_task_label = task_label

        # Persist so the row survives a restart (Phase 4: state persistence).
        await database.upsert_agent(
            self.agent_id,
            self.name,
            status,
            role=self.role,
            **self._db_kwargs(),
        )

        # Broadcast to the Agents window.
        await self._hub.broadcast(
            AgentUpdate(
                agent_id=self.agent_id,
                agent_name=self.name,
                status=status,
                current_task=task_label,
            )
        )

    async def _log_audit(self, action: str, *, target: str | None = None) -> None:
        """Write a metadata-only audit record for this agent (Security Rule 6).

        Phase 12C also hooks the audit stream into semantic memory: every logged
        agent action is, by definition, a high-value event (Phase 12 Rule 2), so
        when a :class:`MemoryManager` is wired in the same metadata is promoted to
        a ``memory_facts`` row (importance 1.0) and mirrored into FAISS. The
        promotion is fire-and-forget so it never adds latency to the action, and
        it carries only metadata (action verb + target) — never message content,
        preserving Security Rule 6.
        """
        await database.log_audit(
            self.agent_id, action, target=target, **self._db_kwargs()
        )
        if self.memory_manager is not None:
            fact = self._audit_fact(action, target)
            asyncio.create_task(
                self.memory_manager.store_fact(
                    fact,
                    source="agent",
                    category="agent_outcome",
                    importance=1.0,
                    agent_id=self.agent_id,
                )
            )

    def _audit_fact(self, action: str, target: str | None) -> str:
        """Render an audit action into a compact declarative fact (metadata only).

        e.g. ``"Atlas (production_lead) performed task.delegate on
        backend:task:7."`` — no message content, just the who/what/where.
        """
        where = f" on {target}" if target else ""
        return f"{self.name} ({self.agent_id}) performed {action}{where}."

    @staticmethod
    def _task_target(task_id: int | None) -> str | None:
        """Format a ``tasks`` row id as an audit ``target`` string."""
        return f"task:{task_id}" if task_id is not None else None

    # --- Self-improvement memory (agent_performance) ------------------------

    def _record_performance(
        self,
        task: dict[str, Any],
        outcome: str,
        *,
        correction_count: int = 0,
    ) -> None:
        """Write an ``agent_performance`` row for a finished specialist task.

        Called by specialists from their ``handle_task`` once they know whether
        the task succeeded or failed. Gated on a wired-in :class:`MemoryManager`
        so the no-memory test path is unchanged, and fire-and-forget so it never
        slows the task loop. ``task_type`` is derived from the task content;
        ``notes`` carries a short, non-sensitive summary.
        """
        if self.memory_manager is None:
            return
        description = (task.get("description") or task.get("title") or "").strip()
        task_type = self._derive_task_type(description)
        notes = description[:200] or None
        asyncio.create_task(
            self._save_performance_async(
                task_type=task_type,
                outcome=outcome,
                correction_count=correction_count,
                notes=notes,
            )
        )

    async def _save_performance_async(
        self,
        *,
        task_type: str,
        outcome: str,
        correction_count: int,
        notes: str | None,
    ) -> None:
        """Best-effort wrapper around :func:`database.save_agent_performance`."""
        try:
            await database.save_agent_performance(
                self.agent_id,
                task_type,
                outcome,
                correction_count=correction_count,
                notes=notes,
                **self._db_kwargs(),
            )
        except Exception:  # noqa: BLE001 — performance logging must not break a task
            log.warning(
                "agent_performance_log_failed",
                agent_id=self.agent_id,
                exc_info=True,
            )

    @staticmethod
    def _derive_task_type(description: str) -> str:
        """Classify a task into a coarse ``task_type`` bucket from its content.

        A cheap keyword heuristic — enough to group outcomes for later analysis
        without an API call. Defaults to ``"general"`` when nothing matches.
        """
        text = description.lower()
        buckets: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("bugfix", ("bug", "fix", "error", "crash", "regression", "broken")),
            ("feature", ("add", "build", "implement", "create", "feature", "new")),
            ("refactor", ("refactor", "clean", "optimis", "optimiz", "performance")),
            ("docs", ("document", "docs", "readme", "write-up", "comment")),
            ("review", ("review", "audit", "scan", "verify", "test")),
            ("design", ("design", "ui", "ux", "style", "layout", "component")),
        )
        for name, keywords in buckets:
            if any(kw in text for kw in keywords):
                return name
        return "general"


__all__ = ["BaseAgent", "DEFAULT_CONTEXT_TURNS", "RESTORE_CONTEXT_MESSAGES"]
