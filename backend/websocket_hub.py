"""WebSocket connection hub for the Jarvis backend.

A single hub fans state out to every connected client. All 5 Tauri windows
(Animation, Reasoning, Communications, Agents, Tools) open one WebSocket each to
``ws://127.0.0.1:8000/ws`` and subscribe to the same event stream, so a single
:meth:`ConnectionHub.broadcast` reaches every window at once.

Responsibilities
----------------
* Track the set of live :class:`~starlette.websockets.WebSocket` connections.
* :meth:`connect` / :meth:`disconnect` register and deregister them.
* :meth:`broadcast` serialises an :class:`~backend.events.Event` (or raw dict)
  and sends it to every connection, transparently dropping any that have died.

Concurrency
-----------
The voice pipeline, the 6 background agents, and request handlers all run on the
same asyncio event loop and may broadcast concurrently. An :class:`asyncio.Lock`
guards mutations of the connection set so registration and the snapshot taken at
broadcast time never race. Sends themselves happen *outside* the lock (against a
snapshot) so a slow client can't block others or deadlock a concurrent
connect/disconnect.
"""

from __future__ import annotations

import asyncio
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

from backend.events import Event, serialize
from backend.logging_config import get_logger

log = get_logger(__name__)


class ConnectionHub:
    """Manages active WebSocket connections and broadcasts events to them all."""

    def __init__(self) -> None:
        # The live set of connections. Mutated only under ``_lock``.
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def connection_count(self) -> int:
        """Number of currently registered connections (best-effort, lock-free)."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept the handshake and register the connection.

        Must be awaited before any send. The connection is added to the live set
        under the lock so concurrent broadcasts see a consistent view.
        """
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        log.info("websocket_connected", clients=self.connection_count)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Deregister a connection. Idempotent — safe to call more than once."""
        async with self._lock:
            self._connections.discard(websocket)
        log.info("websocket_disconnected", clients=self.connection_count)

    async def broadcast(self, event: Event | dict[str, Any]) -> int:
        """Serialise ``event`` and send it to every live connection.

        Returns the number of connections the event was successfully delivered
        to. Connections that raise on send (closed mid-flight) are pruned. The
        payload is serialised once and reused for every recipient.
        """
        payload = serialize(event)

        # Snapshot under the lock, then send outside it so a slow or wedged
        # client cannot block connect/disconnect or other broadcasts.
        async with self._lock:
            targets = list(self._connections)

        if not targets:
            return 0

        dead: list[WebSocket] = []
        delivered = 0
        for ws in targets:
            if ws.application_state != WebSocketState.CONNECTED:
                dead.append(ws)
                continue
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception:  # noqa: BLE001 — any send failure means drop it
                # The socket died between snapshot and send; prune it.
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
            log.info(
                "websocket_pruned_dead",
                pruned=len(dead),
                clients=self.connection_count,
            )

        return delivered

    async def disconnect_all(self) -> None:
        """Close and deregister every connection (used on app shutdown)."""
        async with self._lock:
            targets = list(self._connections)
            self._connections.clear()
        for ws in targets:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001 — best-effort during shutdown
                pass
        if targets:
            log.info("websocket_closed_all", closed=len(targets))


# Process-wide singleton hub. Importing this gives every module (agents, voice
# pipeline, route handlers) a handle to the same fan-out point.
hub = ConnectionHub()


__all__ = ["ConnectionHub", "hub"]
