"""FastAPI application entry point for the Jarvis backend.

This module wires together the core HTTP application: a modern
:func:`contextlib.asynccontextmanager` lifespan that initialises the SQLite
database and structured logging on startup and cleans up on shutdown, a
``GET /health`` liveness endpoint, and CORS locked down to local Tauri origins.

The WebSocket hub lives in :mod:`backend.websocket_hub`; this module exposes it
at ``ws://127.0.0.1:8000/ws``, where all 5 Tauri windows subscribe to a single
fan-out event stream (see :mod:`backend.events` for the event schema).

Security Rule 2 (local network only): the Uvicorn entry point at the bottom
binds to ``127.0.0.1`` exclusively, never ``0.0.0.0``.

Run directly for local development::

    python -m backend.main
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.logging_config import configure_logging, get_logger
from backend.memory.database import init_db
from backend.memory.vector_store import VectorStore
from backend.websocket_hub import hub

# Application metadata. Kept in one place so the /health payload and the
# OpenAPI docs report a single source of truth.
APP_VERSION: str = "0.1.0"

# Bind address — Security Rule 2: local loopback only, never 0.0.0.0.
HOST: str = "127.0.0.1"
PORT: int = 8000

# CORS allowlist — only the local Tauri/Vite dev origins may call the API.
# Tauri serves the production UI from the ``tauri://localhost`` origin; the Vite
# dev server runs on http://localhost:1420 (Tauri's default) and 5173 (Vite's
# default). No wildcard — Security Rule 2 keeps this strictly local.
ALLOWED_ORIGINS: list[str] = [
    "tauri://localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown.

    Startup: configure structured logging, initialise the SQLite schema
    (idempotent), then signal readiness. Shutdown: release resources and log a
    clean exit. Anything ``yield``-ed back is the place future background tasks
    (the agent runtime, the voice pipeline) will be started and cancelled.
    """
    # Logging first so every subsequent startup event flows through the
    # structured pipeline.
    configure_logging()
    log.info("Jarvis backend starting", host=HOST, port=PORT, version=APP_VERSION)

    # Ensure the database and its schema exist before serving any request.
    await init_db()
    log.info("Database initialised")

    # Long-term semantic memory. Construct cheaply (the embedding model loads
    # lazily on first add/search), then load any persisted index from disk so
    # memories survive restarts. A missing index on first boot is normal.
    vector_store = VectorStore()
    try:
        vector_store.load()
        log.info("Vector store loaded", entries=len(vector_store))
    except FileNotFoundError:
        log.info("Vector store starting empty (no persisted index yet)")
    # Expose on app state so routes/agents share one instance.
    app.state.vector_store = vector_store

    try:
        yield
    finally:
        # Shutdown / cleanup. Persist semantic memory, then close every live
        # WebSocket so clients see a clean disconnect; future resources (DB
        # pools, agent tasks, audio streams) get torn down here too.
        if len(vector_store):
            vector_store.save()
            log.info("Vector store saved", entries=len(vector_store))
        await hub.disconnect_all()
        log.info("Jarvis backend shutting down")


app = FastAPI(
    title="Jarvis Backend",
    version=APP_VERSION,
    summary="Local-first AI assistant backend — voice pipeline, agents, and tools.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe.

    Returns a small static payload so the frontend (and any monitor) can confirm
    the backend is up and report its version.
    """
    return {"status": "ok", "version": APP_VERSION}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Single WebSocket hub endpoint.

    All 5 Tauri windows connect here and subscribe to the same broadcast event
    stream (``agent_update``, ``token``, ``tool_call``, ``voice_state`` — see
    :mod:`backend.events`). The hub pushes events *to* clients; inbound frames
    are drained but not yet acted upon (a future phase may accept client
    commands here). The loop exits on disconnect, after which the connection is
    deregistered from the hub.
    """
    await hub.connect(websocket)
    try:
        while True:
            # Block on inbound frames purely to detect disconnects. Clients are
            # broadcast-only consumers today, so received text is discarded.
            await websocket.receive_text()
    except WebSocketDisconnect:
        # Normal client-initiated close.
        pass
    except Exception:  # noqa: BLE001 — any transport error ends this connection
        log.warning("websocket_error", exc_info=True)
    finally:
        await hub.disconnect(websocket)


def main() -> None:
    """Run the backend under Uvicorn, bound to local loopback only."""
    import uvicorn

    # Security Rule 2: host is pinned to 127.0.0.1; never expose on 0.0.0.0.
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
