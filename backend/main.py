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
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.runtime import AgentRuntime
from backend.integrations.gmail_client import GmailClient
from backend.integrations.slack_client import SlackClient
from backend.logging_config import configure_logging, get_logger
from backend.memory.database import init_db
from backend.memory.vector_store import VectorStore
from backend.voice.pipeline import VoicePipeline
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

    # Voice pipeline (Phase 3): wake -> listen -> STT -> Claude -> TTS -> play.
    # OpenWakeWord needs no API key, so the pipeline always starts. The detector
    # disables itself gracefully if the openwakeword library is not installed.
    # Start is non-blocking — detection runs in its own background task.
    voice_pipeline = VoicePipeline(hub=hub)
    await voice_pipeline.start()
    app.state.voice_pipeline = voice_pipeline
    log.info("Voice pipeline started")

    # Agent system (Phase 4): the Production Lead (Atlas) plus five specialists
    # (Ben, Kado, Sentinel, Vega, Quill). Each runs as its own asyncio task and
    # upserts its row into the agents table on start, so the roster persists
    # across restarts. The runtime shares the singleton hub for status fan-out.
    agent_runtime = AgentRuntime(hub=hub)
    await agent_runtime.start()
    app.state.agents = agent_runtime.agents
    app.state.agent_runtime = agent_runtime
    log.info("Agent runtime started", agents=len(agent_runtime.agents))

    # Communication integrations (Phase 5): Slack + Gmail. Both construct
    # cheaply and read their credentials lazily, so they are always created and
    # exposed on app.state for the tool system (Phase 6) and agents to use. When
    # a credential is missing each client degrades to a safe no-op rather than
    # crashing startup (Security Rule 1 + graceful-degradation rule).
    async def _on_slack_message(payload: dict[str, Any]) -> None:
        # Fan an inbound DM/mention out to the UI so the Communications window
        # (and, in future, the voice pipeline) can surface "new Slack message".
        # Metadata only — the text rides the same event the UI already trusts.
        log.info(
            "slack_inbound_notification",
            kind=payload.get("kind"),
            channel=payload.get("channel"),
        )
        await hub.broadcast(payload)

    slack_client = SlackClient(on_notification=_on_slack_message)
    started = await slack_client.start_listener()
    app.state.slack_client = slack_client
    log.info("Slack integration ready", listener_running=started)

    gmail_client = GmailClient()
    app.state.gmail_client = gmail_client
    log.info("Gmail integration ready")

    try:
        yield
    finally:
        # Stop the Slack listener first so no inbound event fires mid-teardown.
        await slack_client.stop()
        log.info("Slack integration stopped")
        # Shutdown / cleanup. Stop the agents and the voice pipeline (cancels any
        # in-flight turn), persist semantic memory, then close every live
        # WebSocket so clients see a clean disconnect.
        await agent_runtime.stop()
        log.info("Agent runtime stopped")
        await voice_pipeline.stop()
        log.info("Voice pipeline stopped")
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
