"""WebSocket event schema for the Jarvis backend.

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
# pipeline: idle -> listening -> thinking -> speaking -> idle.
VoiceState = Literal["idle", "listening", "thinking", "speaking"]

# The set of valid event ``type`` discriminators.
EventType = Literal["agent_update", "token", "tool_call", "voice_state"]


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
    "serialize",
]
