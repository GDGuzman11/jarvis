"""WebSocket event schema for the Helix backend.

Every one of the 5 Tauri windows connects to the single WebSocket hub at
``ws://127.0.0.1:8000/ws`` and receives a stream of JSON events. This module is
the *single source of truth* for the shape of those events so the backend and
frontend stay in lockstep.

Four event types flow over the hub (Phase 2 schema):

* ``agent_update`` — an agent changed status or picked up a task. Drives the
  Agents window's live cards.
* ``token``        — one streamed token of a Claude/Ollama response. Drives the
  Reasoning window's live token stream.
* ``tool_call``    — an agent invoked a tool (and, optionally, its result).
  Drives the Reasoning window's tool-call cards.
* ``voice_state``  — the voice pipeline transitioned state. Drives the Animation
  window's orb colour (idle/listening/thinking/speaking).

Design notes
------------
* Events are plain :func:`dataclasses.dataclass` instances. Each carries a
  literal ``type`` discriminator and an ISO-8601 UTC ``timestamp`` (auto-filled
  at construction when not supplied).
* :meth:`Event.to_dict` produces a JSON-serialisable ``dict``; :func:`serialize`
  produces the wire string the hub broadcasts. Keeping serialisation here means
  the hub never needs to know about individual event shapes.
* Status / state vocabularies are constrained to :data:`AgentStatus` /
  :data:`VoiceState` literals. ``AgentStatus`` mirrors the ``agents.status``
  CHECK constraint in :mod:`backend.memory.database` so an event can be written
  straight to the DB without translation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# --- Constrained vocabularies ------------------------------------------------

# Agent status — mirrors the CHECK constraint on agents.status in the DB schema
# (backend/memory/database.py) so events and rows share one vocabulary.
AgentStatus = Literal["idle", "working", "error", "offline"]

# Voice pipeline state — drives the Animation window orb colour. Per the Phase 3
# pipeline: idle -> listening -> thinking -> speaking -> idle. ``error`` is the
# parked state the pipeline enters after exhausting its crash retries (Phase 10
# crash recovery), so the orb can surface a hard fault.
VoiceState = Literal["idle", "listening", "thinking", "speaking", "error"]

# The set of valid event ``type`` discriminators.
EventType = Literal[
    "agent_update",
    "token",
    "tool_call",
    "voice_state",
    "audio_level",
    "metrics",
    "comms",
    "tool_permissions",
    "shutdown",
    "memory_update",
    "memory_confirm",
    "memory_recall",
]


def _utc_now_iso() -> str:
    """Return the current time as an ISO-8601 string in UTC with a ``Z`` suffix."""
    return datetime.now(timezone.utc).isoformat()


# --- Event dataclasses -------------------------------------------------------


@dataclass(slots=True)
class Event:
    """Base class for all WebSocket events.

    Subclasses set ``type`` to a fixed discriminator and add their own payload
    fields. ``timestamp`` is auto-filled with the current UTC time at
    construction unless explicitly provided.
    """

    # NOTE: ``type`` and ``timestamp`` are declared on each concrete subclass
    # (not here) so that subclasses may freely add non-default fields without
    # tripping the "non-default argument follows default argument" rule that
    # dataclass inheritance imposes. This base class exists for typing,
    # ``isinstance`` checks, and the shared serialisation helpers below.

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable ``dict`` of this event."""
        return asdict(self)

    def to_json(self) -> str:
        """Return the compact JSON wire string for this event."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


@dataclass(slots=True)
class AgentUpdate(Event):
    """An agent changed status and/or its current task.

    Broadcast whenever an agent transitions state so the Agents window can
    update its card in real time.
    """

    agent_id: str
    agent_name: str
    status: AgentStatus
    current_task: str | None = None
    type: Literal["agent_update"] = "agent_update"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class Token(Event):
    """A single streamed token of an AI response.

    Emitted token-by-token while Claude (or the Ollama fallback) streams, then a
    final empty/closing token with ``is_final=True`` to mark completion.
    """

    content: str
    model: str
    is_final: bool = False
    type: Literal["token"] = "token"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class ToolCall(Event):
    """An agent invoked a tool.

    ``args`` is the tool's input arguments; ``result`` is filled in on the
    follow-up event once the tool returns (``None`` while in flight).
    """

    tool_name: str
    agent_id: str
    args: dict[str, Any] = field(default_factory=dict)
    result: Any | None = None
    type: Literal["tool_call"] = "tool_call"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class VoiceStateEvent(Event):
    """The voice pipeline transitioned to a new state.

    Drives the Animation window orb: idle (blue), thinking (gold), speaking
    (cyan); ``listening`` while capturing the user's speech.
    """

    state: VoiceState
    type: Literal["voice_state"] = "voice_state"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class AudioLevelEvent(Event):
    """A sampled audio amplitude during TTS playback (Phase 2 / Phase 10).

    Broadcast every ~50 ms while Helix is speaking so the Animation window's
    orb can pulse in time with the audio. ``level`` is the RMS amplitude of the
    playback buffer normalised to the ``0.0``-``1.0`` range (clipped at ``1.0``).
    A final event with ``level=0.0`` is broadcast when playback stops so the orb
    settles back to rest.
    """

    level: float = 0.0
    type: Literal["audio_level"] = "audio_level"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class MetricsEvent(Event):
    """Cost + latency for a completed Claude turn (Phase 11C).

    Broadcast once per Claude response, immediately *after* the final
    ``is_final=True`` token, so the Reasoning window can display the running
    cost and latency of the live model. ``cost_usd`` is computed from the
    Anthropic ``usage`` token counts against the Claude Opus 4.7 price card;
    ``latency_ms`` is wall-clock from stream open to the final token.
    """

    cost_usd: float
    latency_ms: int
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    type: Literal["metrics"] = "metrics"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class CommsEvent(Event):
    """A refreshed snapshot of the Slack and/or Gmail inboxes (Phase 15B).

    Broadcast after a Slack or Gmail *read* so the Communications window can
    render live inbox data instead of a skeleton. Either list may be ``None``
    when only one source was fetched — the frontend updates each independently
    (``if (event.slack) ...; if (event.gmail) ...``).

    Each ``slack`` item is ``{id, sender, channel, text, unread, timestamp}``;
    each ``gmail`` item is ``{id, sender, subject, snippet, unread, timestamp}``.
    Shapes mirror ``SlackMessage`` / ``GmailMessage`` in the frontend
    ``types.ts``. Message bodies that originate from external senders are *data*,
    not commands — they are never injected into a model prompt by this event.
    """

    slack: list[dict[str, Any]] | None = None
    gmail: list[dict[str, Any]] | None = None
    type: Literal["comms"] = "comms"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class ToolPermissionsEvent(Event):
    """The current per-agent tool permission matrix (Phase 15B).

    Broadcast on each window connect and whenever a permission is granted or
    revoked, so the Tools window's per-agent access toggles reflect the live
    matrix. ``permissions`` maps ``agent_id`` -> sorted list of allowed tool
    names; ``tools`` is the canonical sorted list of every registered tool so
    the UI can render a complete grid even for tools no agent currently holds.
    """

    permissions: dict[str, list[str]] = field(default_factory=dict)
    tools: list[str] | None = None
    type: Literal["tool_permissions"] = "tool_permissions"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class MemoryUpdateEvent(Event):
    """A memory fact was created/updated/recalled — grow the brain live (16F).

    Broadcast from the memory write path (``MemoryManager._add_fact`` /
    ``store_fact``) whenever a new neuron should appear in the Memory window's 3D
    brain. ``action`` is ``"add"`` (a brand-new fact/neuron), ``"update"`` (an
    existing fact changed) or ``"recall"`` (a fact was just recalled, so its
    neuron can pulse). ``node`` carries the affected node in the same minimal
    shape the ``GET /api/memory/graph`` endpoint emits (``id``, ``type``,
    ``text_preview``, …) so the frontend can splice it straight into the graph
    without a full refetch; it is ``None`` when only an id-less signal is needed.

    Fact text may originate from untrusted sources (a Slack/email body that
    became a fact). It rides this event as *display data* only and is never
    re-injected into a model prompt by the frontend.
    """

    action: Literal["add", "update", "recall"]
    node: dict[str, Any] | None = None
    type: Literal["memory_update"] = "memory_update"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class MemoryConfirmEvent(Event):
    """Helix is unsure whether to remember a fact — ask the user (Memory Capture).

    Broadcast when an extracted ADD lands in the confirm band (its confidence sits
    between :data:`~backend.memory.manager.CONFIRM_LOW_CONFIDENCE` and
    :data:`~backend.memory.manager.AUTO_STORE_CONFIDENCE`). The Reasoning window
    renders a small "🧠 Remember this?" Yes/No card; the answer is sent back to
    ``POST /api/memory/confirm`` with this ``confirm_id``. The fact is NOT stored
    until the user says yes.

    ``category`` is the 10-category display DOMAIN (drives the badge colour), not
    the evaluator's signal category. ``fact`` may derive from untrusted content;
    it rides this event as display data only and is never re-injected into a
    model prompt by the frontend.
    """

    confirm_id: str
    fact: str
    category: str
    subject: str | None = None
    type: Literal["memory_confirm"] = "memory_confirm"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class MemoryRecallEvent(Event):
    """The facts Helix just reached for during a recall — flash them (Memory window).

    Broadcast from :meth:`~backend.memory.manager.MemoryManager.recall` once the
    multi-signal re-ranker has chosen the facts to inject. ``fact_ids`` carries
    those facts in the graph node-id form (``"fact:<n>"``) so the Memory window
    can match them directly against its existing node ids and pulse just the
    neurons that were recalled — no payload reshaping, no full graph refetch.

    Recall sits on the voice hot path, so this event is emitted fire-and-forget
    (scheduled, not awaited) by the manager and never carries fact *text* — only
    ids — keeping the broadcast cheap and free of any untrusted content.
    """

    fact_ids: list[str] = field(default_factory=list)
    type: Literal["memory_recall"] = "memory_recall"
    timestamp: str = field(default_factory=_utc_now_iso)


@dataclass(slots=True)
class ShutdownEvent(Event):
    """The backend is shutting down; windows should close (Phase 15B).

    Broadcast from the ``POST /api/shutdown`` handler when the ⏻ button is
    pressed. The frontend tears down its WebSocket and closes the Tauri window
    on receipt.
    """

    type: Literal["shutdown"] = "shutdown"
    timestamp: str = field(default_factory=_utc_now_iso)


# --- Serialisation helpers ---------------------------------------------------


def serialize(event: Event | dict[str, Any]) -> str:
    """Serialise an event to its JSON wire string.

    Accepts either an :class:`Event` instance or a pre-built ``dict`` (handy for
    callers that assemble events dynamically). Raises :class:`TypeError` for
    anything else so malformed broadcasts fail loudly rather than silently.
    """
    if isinstance(event, Event):
        return event.to_json()
    if isinstance(event, dict):
        return json.dumps(event, separators=(",", ":"))
    raise TypeError(
        f"serialize() expects an Event or dict, got {type(event).__name__}"
    )


__all__ = [
    "AgentStatus",
    "VoiceState",
    "EventType",
    "Event",
    "AgentUpdate",
    "Token",
    "ToolCall",
    "VoiceStateEvent",
    "AudioLevelEvent",
    "MetricsEvent",
    "CommsEvent",
    "ToolPermissionsEvent",
    "MemoryUpdateEvent",
    "MemoryConfirmEvent",
    "MemoryRecallEvent",
    "ShutdownEvent",
    "serialize",
]
