"""FastAPI application entry point for the Helix backend.

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
import sqlite3
import tempfile
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.runtime import AgentRuntime
from backend.events import AgentUpdate, ShutdownEvent, serialize
from backend.integrations.gmail_client import GmailClient
from backend.integrations.slack_client import SlackClient
from backend.logging_config import configure_logging, get_logger
from backend.memory.database import (
    create_task,
    get_agent_tasks,
    init_db,
    rename_agent,
)
from backend.memory.extractor import LLMExtractor
from backend.memory.manager import MemoryManager
from backend.memory.vector_store import DEFAULT_INDEX_PATH, VectorStore
from backend.memory.database import DEFAULT_DB_PATH
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
# browser) could open ``ws://127.0.0.1:8000/ws`` and read Helix's live event
# stream. We therefore validate the ``Origin`` header on every WS connection and
# accept only the local Tauri frontend's origins. This mirrors ALLOWED_ORIGINS
# but is enforced independently inside the /ws handler.
ALLOWED_WS_ORIGINS: frozenset[str] = frozenset(ALLOWED_ORIGINS)

log = get_logger(__name__)


async def _startup_greeting(memory_manager: MemoryManager | None = None) -> None:
    """Speak a personalised greeting once the first Tauri window connects.

    When a :class:`MemoryManager` is supplied (Phase 12D), the greeting also
    surfaces *overdue* open loops — promises/reminders created more than 12 hours
    ago that are still open — so Helix proactively reminds the user of
    unfinished follow-ups at session start. Every memory access is guarded so the
    greeting still works when ``memory_manager is None`` or the query fails.
    """
    from backend.ai.claude_client import ClaudeClient, ClaudeAPIError
    from backend.ai.persona import build_system_prompt
    from backend.events import VoiceStateEvent
    from backend.memory.database import get_open_loops_async
    from backend.security.keystore import missing_credentials
    from backend.voice import tts

    # Wait up to 60 s for at least one window to open a WebSocket connection.
    for _ in range(120):
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

    spoken = reply.strip() if reply.strip() else fallback

    # Surface overdue open loops (created > 12 hours ago, still open) so Helix
    # proactively reminds the user of unfinished follow-ups (Phase 12D). Guarded:
    # a missing manager or a query failure simply skips the reminder.
    if memory_manager is not None:
        try:
            open_loops = await get_open_loops_async(
                memory_manager.db_path, status="open", older_than_hours=12
            )
            if open_loops:
                loop_text = ", ".join(
                    loop["description"][:60] for loop in open_loops[:3]
                )
                spoken += (
                    f" Also, sir — you have {len(open_loops)} open item(s) "
                    f"to follow up on: {loop_text}."
                )
                log.info("startup_open_loops_surfaced", count=len(open_loops))
        except Exception:  # noqa: BLE001 — reminders must not break the greeting
            log.warning("startup_open_loops_failed", exc_info=True)

    await hub.broadcast(VoiceStateEvent(state="speaking"))
    try:
        await tts.speak_and_play(spoken)
    except Exception:
        log.warning("startup_greeting_tts_failed", exc_info=True)
    finally:
        await hub.broadcast(VoiceStateEvent(state="idle"))


# How often the background consolidation pass runs (Phase 12D).
CONSOLIDATION_INTERVAL_S: int = 600  # 10 minutes


async def _consolidation_loop(memory_manager: MemoryManager) -> None:
    """Run :meth:`MemoryManager.run_consolidation` every 10 minutes forever.

    Cancellable: the lifespan cancels this task on shutdown, raising
    :class:`asyncio.CancelledError` out of the ``sleep`` — which we let
    propagate so the task ends cleanly. Any other error inside a pass is
    swallowed so a single bad consolidation never kills the loop.
    """
    while True:
        try:
            await asyncio.sleep(CONSOLIDATION_INTERVAL_S)
        except asyncio.CancelledError:
            raise
        try:
            await memory_manager.run_consolidation()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — never crash the loop on a bad pass
            log.warning("consolidation_loop_pass_failed", exc_info=True)


# Daily backup cadence + retention window (Phase 12E).
BACKUP_INTERVAL_S: int = 86_400  # 24 hours
BACKUP_RETENTION_DAYS: int = 30


def _online_backup_db(src_path: Path, dst_path: Path) -> None:
    """Copy a WAL-safe, consistent online snapshot of the SQLite DB.

    Uses :meth:`sqlite3.Connection.backup`, which reads a transactionally
    consistent image of the source database — including committed pages that
    still live in the ``-wal`` sidecar — and writes a fresh, self-contained DB
    file at ``dst_path``. This is safe under WAL journal mode with concurrent
    writers (the consolidation loop, voice pipeline, and agents all write while
    a backup runs); a raw file copy of just the ``.db`` would miss un-checkpointed
    WAL pages and produce a stale or torn snapshot.

    The source is opened read-write (the standard, robust path that avoids the
    read-only-WAL ``-shm`` pitfall); ``backup()`` never mutates the source. The
    journal mode of the live DB is untouched.
    """
    src = sqlite3.connect(str(src_path))
    try:
        dst = sqlite3.connect(str(dst_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _write_backup_zip(db_path: Path, vector_store_path: Path) -> Path | None:
    """Zip the DB + FAISS index/sidecar into ``data/backups/jarvis_<date>.zip``.

    Synchronous (called via :func:`asyncio.to_thread`). Any source file that is
    missing is simply skipped — a fresh install with no FAISS index yet still
    produces a valid backup of whatever exists. Returns the zip path written, or
    ``None`` when there was nothing to back up.

    The database is captured via :func:`_online_backup_db` (a WAL-safe online
    snapshot) rather than raw-copied, so the archive always holds a consistent,
    self-contained DB even under concurrent writers. Because the snapshot already
    folds in committed WAL pages, the ``-wal``/``-shm`` sidecars are intentionally
    NOT shipped — they would be redundant. The DB is stored in the archive under
    ``db_path.name`` (``jarvis.db`` in production) so existing restore logic keeps
    working. FAISS vector files are plain on-disk blobs with no journal, so they
    are still raw-copied as before.
    """
    backups_dir = db_path.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    vector_sources = [
        vector_store_path,
        vector_store_path.with_suffix(vector_store_path.suffix + ".meta.json"),
    ]
    vector_present = [p for p in vector_sources if p.exists()]
    db_present = db_path.exists()

    if not db_present and not vector_present:
        log.info("backup_skipped_no_sources")
        return None

    stamp = datetime.now().strftime("%Y-%m-%d")
    zip_path = backups_dir / f"jarvis_{stamp}.zip"

    tmp_db: Path | None = None
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if db_present:
                tmp_fd, tmp_name = tempfile.mkstemp(
                    prefix=".backup_", suffix=".db", dir=str(backups_dir)
                )
                os.close(tmp_fd)
                tmp_db = Path(tmp_name)
                _online_backup_db(db_path, tmp_db)
                zf.write(tmp_db, arcname=db_path.name)
            for src in vector_present:
                zf.write(src, arcname=src.name)
    finally:
        if tmp_db is not None:
            try:
                tmp_db.unlink()
            except OSError:
                log.warning(
                    "backup_tmp_cleanup_failed", path=str(tmp_db), exc_info=True
                )

    file_count = (1 if db_present else 0) + len(vector_present)
    log.info("backup_written", path=str(zip_path), files=file_count)
    return zip_path


def _prune_old_backups(db_path: Path, retention_days: int = BACKUP_RETENTION_DAYS) -> int:
    """Delete ``jarvis_*.zip`` backups older than ``retention_days``.

    Synchronous (called via :func:`asyncio.to_thread`). Age is taken from each
    file's modification time. Returns the number of files pruned. Never raises on
    an individual unlink failure — it logs and moves on.
    """
    backups_dir = db_path.parent / "backups"
    if not backups_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    pruned = 0
    for zip_file in backups_dir.glob("jarvis_*.zip"):
        try:
            mtime = datetime.fromtimestamp(zip_file.stat().st_mtime)
            if mtime < cutoff:
                zip_file.unlink()
                pruned += 1
        except OSError:
            log.warning("backup_prune_failed", path=str(zip_file), exc_info=True)
    if pruned:
        log.info("backup_pruned", count=pruned)
    return pruned


async def _backup_loop(db_path: Path, vector_store_path: Path) -> None:
    """Back up the DB + FAISS index once at startup, then daily forever.

    Mirrors :func:`_consolidation_loop`: cancellable on shutdown (the
    :class:`asyncio.CancelledError` from ``sleep`` propagates so the task ends
    cleanly), and any other error inside a pass is swallowed so a single failed
    backup never kills the loop. The blocking zip/prune I/O runs via
    :func:`asyncio.to_thread` so it never stalls the event loop.
    """
    while True:
        try:
            await asyncio.to_thread(_write_backup_zip, db_path, vector_store_path)
            await asyncio.to_thread(_prune_old_backups, db_path)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — never crash the loop on a bad pass
            log.warning("backup_loop_pass_failed", exc_info=True)
        try:
            await asyncio.sleep(BACKUP_INTERVAL_S)
        except asyncio.CancelledError:
            raise


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
    log.info("Helix backend starting", host=HOST, port=PORT, version=APP_VERSION)

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

    # Memory coordinator (Phase 12): the single interface to the three memory
    # layers — episodic (SQLite conversations), semantic (FAISS facts), and the
    # per-turn working memory the pipeline/agents own. Constructed once over the
    # shared vector store so every consumer reads/writes the same memory. Wiring
    # into the voice pipeline (12B) and agents (12C) follows; here it is built
    # and shared.
    # Phase 16C: LLM-driven fact extraction (Claude Haiku 4.5 → local phi3.5
    # fallback). Runs off the voice hot path inside the fire-and-forget
    # consolidate task, gated by the rule pre-filter, so it adds no latency to
    # the spoken reply and degrades to rule distillation if both LLMs are down.
    memory_manager = MemoryManager(
        db_path=DEFAULT_DB_PATH,
        vector_store=vector_store,
        extractor=LLMExtractor(),
    )
    app.state.memory_manager = memory_manager
    log.info("Memory manager ready")

    # Voice pipeline (Phase 3): wake -> listen -> STT -> Claude -> TTS -> play.
    # OpenWakeWord needs no API key, so the pipeline always starts. The detector
    # disables itself gracefully if the openwakeword library is not installed.
    # Start is non-blocking — detection runs in its own background task. The
    # memory manager is handed in for Phase 12B (stored now, used then).
    voice_pipeline = VoicePipeline(hub=hub, memory_manager=memory_manager)
    await voice_pipeline.start()
    app.state.voice_pipeline = voice_pipeline
    log.info("Voice pipeline started")

    # Agent system (Phase 4): the Production Lead (Atlas) plus five specialists
    # (Ben, Kado, Sentinel, Vega, Quill). Each runs as its own asyncio task and
    # upserts its row into the agents table on start, so the roster persists
    # across restarts. The runtime shares the singleton hub for status fan-out.
    agent_runtime = AgentRuntime(
        hub=hub, vector_store=vector_store, memory_manager=memory_manager
    )
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

    slack_client = SlackClient(on_notification=_on_slack_message, hub=hub)
    started = await slack_client.start_listener()
    app.state.slack_client = slack_client
    log.info("Slack integration ready", listener_running=started)

    gmail_client = GmailClient(hub=hub)
    app.state.gmail_client = gmail_client
    log.info("Gmail integration ready")

    # Tools system (Phase 6): one ToolRegistry holds every tool (web search,
    # browser, sandboxed file ops + code executor, and the Slack/Gmail wrappers)
    # behind the per-agent permission matrix. Built after the integration clients
    # so their tool wrappers share the same authenticated client. Exposed on
    # app.state for the agents and the Tools window (Phase 7) to consume.
    tool_registry = build_tool_registry(
        slack_client=slack_client, gmail_client=gmail_client, hub=hub
    )
    app.state.tool_registry = tool_registry
    log.info("Tool registry ready", tools=len(tool_registry.list_tools()))

    # Broadcast the initial tool-permission matrix so any window already
    # connected populates its Tools grid (Phase 15B). Late-joining windows get
    # the same snapshot pushed on connect by the /ws handler below, so the Tools
    # window never renders a skeleton regardless of connect ordering.
    await hub.broadcast(tool_registry.permissions_event())

    # Fire the startup greeting in the background — it waits for the first
    # window to connect, then has Helix speak a personalised hello + status,
    # surfacing any overdue open loops (Phase 12D).
    asyncio.create_task(
        _startup_greeting(memory_manager), name="startup-greeting"
    )

    # Periodic memory consolidation (Phase 12D): every 10 minutes, re-scan recent
    # conversation pairs and back-fill any semantic facts that were missed (e.g.
    # a crash between episodic store and the fire-and-forget consolidate). The
    # loop never raises into the lifespan and is cancelled cleanly on shutdown.
    consolidation_task = asyncio.create_task(
        _consolidation_loop(memory_manager), name="memory-consolidation"
    )

    # Daily backup (Phase 12E): zips jarvis.db + the FAISS index/sidecar into
    # data/backups/jarvis_<date>.zip once at startup and every 24h after, pruning
    # backups older than 30 days. Runs its I/O off the event loop and is
    # cancelled cleanly on shutdown.
    backup_task = asyncio.create_task(
        _backup_loop(Path(DEFAULT_DB_PATH), Path(DEFAULT_INDEX_PATH)),
        name="daily-backup",
    )

    try:
        yield
    finally:
        # Stop the periodic loops first so they can't fire mid-teardown.
        consolidation_task.cancel()
        try:
            await consolidation_task
        except asyncio.CancelledError:
            pass
        backup_task.cancel()
        try:
            await backup_task
        except asyncio.CancelledError:
            pass
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
        log.info("Helix backend shutting down")


app = FastAPI(
    title="Helix Backend",
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


@app.post("/api/chat", tags=["voice"])
async def chat_endpoint(message: str = Body(..., embed=True)) -> dict[str, str]:
    """Accept a typed message and process it through the full Helix pipeline.

    Identical to a voice turn — Claude streams a reply, tokens are broadcast to
    the Reasoning window, and TTS speaks the response. The turn runs in the
    background so this endpoint returns immediately. Returns ``409`` when a turn
    (voice or typed) is already in progress.
    """
    text = message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message must not be empty")

    pipeline: VoicePipeline = getattr(app.state, "voice_pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="voice pipeline not ready")

    if pipeline.state != "idle":
        raise HTTPException(
            status_code=409, detail="Helix is busy — try again in a moment."
        )

    asyncio.create_task(pipeline.process_text(text))
    log.info("chat_text_input", chars=len(text))
    return {"status": "processing"}


@app.post("/api/shutdown", tags=["system"])
async def shutdown_endpoint() -> dict[str, str]:
    """Broadcast a shutdown event to all windows then exit the backend process.

    The frontend listens for the ``shutdown`` event on the WebSocket and closes
    every Tauri window. The backend itself exits via SIGINT after a short delay so
    the HTTP response is sent before the process terminates.
    """
    await hub.broadcast(ShutdownEvent())

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


# --- Direct agent task submission (Phase 13A) -------------------------------
#
# The AgentsWindow shows agents by their display name (Atlas, Ben, Kado, ...),
# so these endpoints accept those friendly slugs in the URL and map them to the
# internal ``agent_id`` keys used everywhere else (``production_lead``,
# ``frontend``, ``backend``, ...). Keeping the public API keyed on display
# slugs means the frontend never has to know the internal ids.
_PUBLIC_TO_AGENT_ID: dict[str, str] = {
    "atlas": "production_lead",
    "ben": "frontend",
    "kado": "backend",
    "sentinel": "security",
    "vega": "marketing",
    "quill": "content",
}

# Upper bound on a submitted goal (Security Rule 3: cap input before it reaches
# Claude). Mirrors the 2000-char voice-input cap.
MAX_GOAL_LEN: int = 2000

# How many recent tasks the task-log endpoint returns per agent.
AGENT_TASK_LOG_LIMIT: int = 5


def _sanitize_goal(raw: str) -> str:
    """Strip control characters and cap length (Security Rule 3).

    Removes ASCII control chars (except none — goals are single-purpose text),
    collapses surrounding whitespace, and truncates to :data:`MAX_GOAL_LEN`.
    Returns the cleaned string, which may be empty (the caller rejects empty).
    """
    cleaned = "".join(ch for ch in raw if ch >= " " or ch == "\n")
    return cleaned.strip()[:MAX_GOAL_LEN]


@app.post("/api/agents/{agent_id}/task", tags=["agents"])
async def submit_agent_task_endpoint(
    agent_id: str,
    goal: str = Body(..., embed=True),
) -> dict[str, Any]:
    """Queue a task directly on a single agent, bypassing the Production Lead.

    ``agent_id`` is a display slug (``atlas``, ``ben``, ``kado``, ``sentinel``,
    ``vega``, ``quill``). The goal is sanitized (Security Rule 3) then written to
    the ``tasks`` table and enqueued straight onto the target agent's live queue,
    so it is targeted directly rather than routed by Atlas. Targeting ``atlas``
    enqueues onto the Production Lead, which then classifies and delegates.

    Returns ``{"task_id", "agent_id", "status": "queued"}``. Responds ``404``
    for an unknown agent slug and ``400`` for an empty/missing goal.
    """
    internal_id = _PUBLIC_TO_AGENT_ID.get(agent_id.lower())
    if internal_id is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")

    clean_goal = _sanitize_goal(goal)
    if not clean_goal:
        raise HTTPException(status_code=400, detail="goal must not be empty")

    agents = getattr(app.state, "agents", {})
    agent = agents.get(internal_id)
    if agent is None:
        # The slug is valid but the runtime is not up (e.g. mid-teardown).
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")

    # Durable record first: a ``tasks`` row with no creator agent (the user is
    # not an agent row) assigned directly to the target. Then enqueue live so the
    # agent starts immediately — mirrors ProductionLead._delegate's plumbing
    # without routing through Atlas.
    title = clean_goal.splitlines()[0][:120]
    task_id = await create_task(None, internal_id, title, description=clean_goal)

    agent.enqueue_task(
        {
            "task_id": task_id,
            "title": title,
            "description": clean_goal,
            "created_by": "user",
        }
    )

    log.info(
        "agent_task_submitted_direct",
        agent_id=internal_id,
        task_id=task_id,
        chars=len(clean_goal),
    )
    return {"task_id": task_id, "agent_id": agent_id, "status": "queued"}


@app.get("/api/agents/{agent_id}/tasks", tags=["agents"])
async def list_agent_tasks_endpoint(agent_id: str) -> dict[str, Any]:
    """Return the most recent tasks assigned to a single agent, newest first.

    ``agent_id`` is a display slug (see :func:`submit_agent_task_endpoint`).
    Returns at most :data:`AGENT_TASK_LOG_LIMIT` tasks as
    ``[{"task_id", "goal", "status", "created_at"}]``. Responds ``404`` for an
    unknown agent slug.
    """
    internal_id = _PUBLIC_TO_AGENT_ID.get(agent_id.lower())
    if internal_id is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")

    rows = await get_agent_tasks(internal_id)
    tasks = [
        {
            "task_id": row["id"],
            "goal": row["description"],
            "status": row["status"],
            "created_at": row["created_at"],
        }
        for row in rows[:AGENT_TASK_LOG_LIMIT]
    ]
    return {"agent_id": agent_id, "tasks": tasks}


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

    # Push the current tool-permission matrix to this window immediately on
    # connect (Phase 15B). The startup broadcast only reaches windows already
    # connected; sending a per-connection snapshot here means the Tools window
    # populates its grid no matter when it joins. Best-effort — a send failure
    # is handled by the disconnect path below.
    registry = getattr(websocket.app.state, "tool_registry", None)
    if registry is not None:
        try:
            await websocket.send_text(serialize(registry.permissions_event()))
        except Exception:  # noqa: BLE001 — a failed initial push ends this connection
            log.warning("websocket_initial_permissions_failed", exc_info=True)

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
