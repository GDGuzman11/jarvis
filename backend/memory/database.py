"""Async SQLite persistence layer for Jarvis.

This module owns the five core tables that back Jarvis's state:

* ``conversations`` — voice/text exchanges between the user and Jarvis.
* ``agents``        — the 6 background agents and their live status.
* ``tasks``         — agent-to-agent delegated work (the task queue).
* ``tools``         — the tool registry and per-tool metadata.
* ``audit_log``     — every agent action, METADATA ONLY (Security Rule 6).

All access is async via :mod:`aiosqlite`. Foreign keys are enabled on every
connection. :func:`init_db` is idempotent — it uses ``CREATE TABLE IF NOT
EXISTS`` so it is safe to call on every startup.

Per Security Rule 6, ``audit_log`` records metadata only (agent id, action,
target, timestamp) and never the content of any message, email, or voice
exchange. The ``detail`` column is reserved for non-sensitive structured
context (e.g. a tool name or status code), not message bodies.
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Default on-disk location for the Jarvis database. Resolves to
# ``<project root>/data/jarvis.db``. The directory is created on init.
DEFAULT_DB_PATH: Path = Path(__file__).resolve().parents[2] / "data" / "jarvis.db"

# --- Schema -----------------------------------------------------------------
# One CREATE TABLE statement per table. Executed in order by init_db().

_SCHEMA: tuple[str, ...] = (
    # conversations: one row per user<->Jarvis exchange (voice or text).
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        role        TEXT    NOT NULL CHECK (role IN ('user', 'jarvis')),
        channel     TEXT    NOT NULL DEFAULT 'voice'
                            CHECK (channel IN ('voice', 'text')),
        content     TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # agents: the 6 background agents, keyed by a stable string slug.
    """
    CREATE TABLE IF NOT EXISTS agents (
        id          TEXT    PRIMARY KEY,
        name        TEXT    NOT NULL,
        role        TEXT    NOT NULL,
        status      TEXT    NOT NULL DEFAULT 'idle'
                            CHECK (status IN ('idle', 'working', 'error', 'offline')),
        current_task_id INTEGER
                            REFERENCES tasks(id) ON DELETE SET NULL,
        updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # tasks: agent-to-agent delegated work — the cross-agent task queue.
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        created_by      TEXT    REFERENCES agents(id) ON DELETE SET NULL,
        assigned_to     TEXT    REFERENCES agents(id) ON DELETE SET NULL,
        description     TEXT    NOT NULL,
        status          TEXT    NOT NULL DEFAULT 'queued'
                                CHECK (status IN
                                    ('queued', 'in_progress', 'done', 'failed')),
        result          TEXT,
        created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # tools: the tool registry — one row per available tool.
    """
    CREATE TABLE IF NOT EXISTS tools (
        id          TEXT    PRIMARY KEY,
        name        TEXT    NOT NULL,
        description TEXT    NOT NULL DEFAULT '',
        enabled     INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # audit_log: every agent action — METADATA ONLY, no message content.
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id    TEXT    REFERENCES agents(id) ON DELETE SET NULL,
        action      TEXT    NOT NULL,
        target      TEXT,
        detail      TEXT,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
)

# Helpful indexes for the common access patterns (queue polling, audit reads).
_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_status "
    "ON tasks (assigned_to, status)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_agent_time "
    "ON audit_log (agent_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_created "
    "ON conversations (created_at)",
)


async def connect(db_path: Path | str = DEFAULT_DB_PATH) -> aiosqlite.Connection:
    """Open an aiosqlite connection with foreign keys enabled.

    The caller owns the returned connection and is responsible for closing it
    (e.g. via ``async with`` or in a FastAPI lifespan). The parent directory is
    created if it does not yet exist.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Create all tables and indexes if they do not already exist.

    Idempotent and safe to call on every startup. Opens its own short-lived
    connection, applies the schema, commits, and closes.
    """
    path = Path(db_path)
    logger.info("Initializing Jarvis database at %s", path)
    conn = await connect(path)
    try:
        for statement in _SCHEMA:
            await conn.execute(statement)
        for index in _INDEXES:
            await conn.execute(index)
        await conn.commit()
    finally:
        await conn.close()
    logger.info("Database schema ready (%d tables).", len(_SCHEMA))
