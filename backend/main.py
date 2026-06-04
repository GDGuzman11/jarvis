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

import asyncio
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.runtime import AgentRuntime
from backend.events import AgentUpdate
from backend.integrations.gmail_client import GmailClient
from backend.integrations.slack_client import SlackClient
from backend.logging_config import configure_logging, get_logger
from backend.memory.database import init_db, rename_agent
from backend.memory.vector_store import VectorStore
from backend.setup_wizard import router as setup_router
from backend.tools.wiring import build_tool_registry
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

# WebSocket Origin allowlist (Security Rule 2 / Phase 8). The CORS middleware
# above only governs HTTP requests — it does NOT protect the WebSocket
# handshake, which browsers exempt from the same-origin policy. Without an
# explicit check, any local page (or a malicious site loaded in the user's
# browser) could open ``ws://127.0.0.1:8000/ws`` and read Jarvis's live event
# stream. We therefore validate the ``Origin`` header on every WS connection and
# accept only the local Tauri frontend's origins. This mirrors ALLOWED_ORIGINS
# but is enforced independently inside the /ws handler.
ALLOWED_WS_ORIGINS: frozenset[str] = frozenset(ALLOWED_ORIGINS)

log = get_logger(__name__)


async def _startup_greeting() -> None:
    """Speak a personalised greeting once the first Tauri window connects."""
    from backend.ai.claude_client import ClaudeClient, ClaudeAPIError
    from backend.ai.persona import build_system_prompt
    from backend.events import VoiceStateEvent
    from backend.security.keystore import missing_credentials
    from backend.voice import tts

    # Wait up to 15 s for at least one window to open a WebSocket connection.
    for _ in range(30):
        await asyncio.sleep(0.5)
        if hub.connection_count > 0:
            break
    else:
        return  # No window connected — skip greeting.

    # Short pause so the orb animation has a moment to render before audio starts.
    await asyncio.sleep(0.5)

    missing = missing_credentials()
    cred_status = (
        "all credentials configured"
        if not missing
        else f"{len(missing)} credential(s) still needed"
    )
    context = (
        f"User name: Gabe\n"
        f"6 agents online: Atlas (Lead), Ben (Frontend), Kado (Backend), "
        f"Sentinel (Security), Vega (Marketing), Quill (Content)\n"
        f"Voice pipeline: active and listening\n"
        f"Credentials: {cred_status}"
    )
    fallback = (
        f"Hello Gabe. All six agents are online and the voice pipeline is active. "
        f"{cred_status.capitalize()}, sir."
    )

    reply = ""
    try:
        client = ClaudeClient()
        messages = [
            {
                "role": "user",
                "content": "Greet your user and give a brief one-sentence system status. Keep it under 40 words.",
            }
        ]
        async for token in client.stream_response(
            messages, system_prompt=build_system_prompt(context=context)
        ):
            reply += token
    except (ClaudeAPIError, Exception):
        log.warning("startup_greeting_failed", exc_info=True)

    await hub.broadcast(VoiceStateEvent(state="speaking"))
    try:
        await tts.speak_and_play(reply.strip() if reply.strip() else fallback)
    except Exception:
        log.warning("startup_greeting_tts_failed", exc_info=True)
    finally:
        await hub.broadcast(VoiceStateEvent(state="idle"))


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

    # Tools system (Phase 6): one ToolRegistry holds every tool (web search,
    # browser, sandboxed file ops + code executor, and the Slack/Gmail wrappers)
    # behind the per-agent permission matrix. Built after the integration clients
    # so their tool wrappers share the same authenticated client. Exposed on
    # app.state for the agents and the Tools window (Phase 7) to consume.
    tool_registry = build_tool_registry(
        slack_client=slack_client, gmail_client=gmail_client
    )
    app.state.tool_registry = tool_registry
    log.info("Tool registry ready", tools=len(tool_registry.list_tools()))

    # Fire the startup greeting in the background — it waits for the first
    # window to connect, then has Jarvis speak a personalised hello + status.
    asyncio.create_task(_startup_greeting(), name="startup-greeting")

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

# First-run setup wizard (Phase 10): GET /setup/status, POST /setup/credential,
# GET /setup/complete. Reachable on loopback only (Security Rule 2 binding).
app.include_router(setup_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe.

    Returns a small static payload so the frontend (and any monitor) can confirm
    the backend is up and report its version.
    """
    return {"status": "ok", "version": APP_VERSION}


@app.post("/api/shutdown", tags=["system"])
async def shutdown_endpoint() -> dict[str, str]:
    """Broadcast a shutdown event to all windows then exit the backend process.

    The frontend listens for the ``shutdown`` event on the WebSocket and closes
    every Tauri window. The backend itself exits via SIGINT after a short delay so
    the HTTP response is sent before the process terminates.
    """
    await hub.broadcast(
        {"type": "shutdown", "timestamp": datetime.now(timezone.utc).isoformat()}
    )

    async def _exit() -> None:
        await asyncio.sleep(0.8)
        os.kill(os.getpid(), signal.SIGINT)

    asyncio.create_task(_exit())
    log.info("shutdown_requested")
    return {"status": "shutting_down"}


# Maximum length of an agent display name. Keeps the Agents-window cards from
# overflowing and bounds what we persist; mirrored in the frontend's form.
MAX_AGENT_NAME_LEN: int = 50


@app.post("/api/agents/{agent_id}/rename", tags=["agents"])
async def rename_agent_endpoint(
    agent_id: str,
    name: str = Body(..., embed=True),
) -> dict[str, str]:
    """Rename a background agent.

    Validates that ``agent_id`` is a live agent and that ``name`` is non-empty
    and at most :data:`MAX_AGENT_NAME_LEN` characters (after trimming
    surrounding whitespace). On success the new name is persisted to the
    ``agents`` table, applied to the live in-memory agent so future status
    broadcasts carry it, and an :class:`AgentUpdate` is broadcast immediately so
    every window's card relabels in real time.

    Returns ``{"agent_id", "name"}`` with the stored (trimmed) name. Responds
    ``404`` for an unknown agent and ``400`` for an empty or over-long name.
    """
    agents = getattr(app.state, "agents", {})
    agent = agents.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")

    new_name = name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    if len(new_name) > MAX_AGENT_NAME_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"name must be at most {MAX_AGENT_NAME_LEN} characters",
        )

    # Persist first. A False return means the row vanished between the in-memory
    # check and the write (e.g. a concurrent teardown) — surface it as a 404.
    persisted = await rename_agent(agent_id, new_name)
    if not persisted:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")

    # Apply to the live agent so its own subsequent status broadcasts and DB
    # upserts carry the new name rather than reverting to the old one.
    agent.name = new_name

    # Broadcast now so every window relabels without waiting for the agent's
    # next status change. Preserve the agent's current status/task in the event.
    await hub.broadcast(
        AgentUpdate(
            agent_id=agent_id,
            agent_name=new_name,
            status=agent.status,
            current_task=getattr(agent, "_current_task_label", None),
        )
    )

    log.info("agent_renamed", agent_id=agent_id, name=new_name)
    return {"agent_id": agent_id, "name": new_name}


def _is_allowed_ws_origin(origin: str | None) -> bool:
    """Return ``True`` only for a WebSocket Origin we trust (Security Rule 2).

    A native (non-browser) client such as a test harness or a CLI may send no
    ``Origin`` header at all; we allow that case because the same-origin attack
    the check defends against only applies to browser contexts, which always
    send an Origin. Any *present* Origin must be in the local allowlist — an
    Origin from a remote web page is rejected, closing the cross-site WebSocket
    hijacking vector.
    """
    if origin is None:
        return True
    return origin in ALLOWED_WS_ORIGINS


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Single WebSocket hub endpoint.

    All 5 Tauri windows connect here and subscribe to the same broadcast event
    stream (``agent_update``, ``token``, ``tool_call``, ``voice_state`` — see
    :mod:`backend.events`). The hub pushes events *to* clients; inbound frames
    are drained but not yet acted upon (a future phase may accept client
    commands here). The loop exits on disconnect, after which the connection is
    deregistered from the hub.

    Before accepting the handshake we validate the ``Origin`` header against
    :data:`ALLOWED_WS_ORIGINS` (Security Rule 2 / Phase 8). A connection from an
    untrusted origin is closed with policy-violation code ``1008`` and never
    registered with the hub, so it receives no events.
    """
    origin = websocket.headers.get("origin")
    if not _is_allowed_ws_origin(origin):
        log.warning("websocket_origin_rejected", origin=origin)
        # 1008 = policy violation. Close before accept so no events ever flow.
        await websocket.close(code=1008)
        return

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
