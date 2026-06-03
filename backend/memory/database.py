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


# --- CRUD: conversations ----------------------------------------------------
#
# Note on the public CRUD API below: the task spec uses a few parameter names
# that don't map 1:1 onto the on-disk schema defined above (the schema is the
# source of truth). Where they differ, we adapt:
#
#   * ``save_conversation(role, content, model=None)`` — ``role`` accepts both
#     the canonical ``'user'``/``'jarvis'`` values and the common alias
#     ``'assistant'`` (normalized to ``'jarvis'``). There is no ``model``
#     column on ``conversations``; when provided, ``model`` is recorded in the
#     ``audit_log`` as non-sensitive metadata rather than dropped silently.
#   * ``upsert_agent(..., current_task=None)`` — agents store a
#     ``current_task_id`` (FK into ``tasks``), so ``current_task`` is treated as
#     a task id when given.
#   * ``create_task(..., title, description=None)`` — ``tasks`` has a single
#     required ``description`` column; ``title`` populates it, and any extra
#     ``description`` is appended after a blank line.
#   * task ``status`` values are normalized from the spec's
#     ``pending|in_progress|completed|failed`` to the schema's
#     ``queued|in_progress|done|failed``.

# Map caller-supplied conversation roles onto the schema's CHECK constraint.
_ROLE_ALIASES: dict[str, str] = {
    "user": "user",
    "jarvis": "jarvis",
    "assistant": "jarvis",
}

# Map spec task-status names onto the schema's CHECK constraint.
_TASK_STATUS_ALIASES: dict[str, str] = {
    "pending": "queued",
    "queued": "queued",
    "in_progress": "in_progress",
    "completed": "done",
    "done": "done",
    "failed": "failed",
}


async def save_conversation(
    role: str,
    content: str,
    model: str | None = None,
    *,
    channel: str = "voice",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Persist a single conversation turn and return its row id.

    ``role`` accepts ``'user'``, ``'jarvis'`` or the alias ``'assistant'``
    (stored as ``'jarvis'``). ``model`` has no dedicated column; when supplied
    it is recorded in the audit log as non-sensitive metadata.
    """
    normalized = _ROLE_ALIASES.get(role.lower())
    if normalized is None:
        raise ValueError(
            f"invalid conversation role {role!r}; expected one of "
            f"{sorted(_ROLE_ALIASES)}"
        )

    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "INSERT INTO conversations (role, channel, content) VALUES (?, ?, ?)",
            (normalized, channel, content),
        )
        row_id = cursor.lastrowid
        if model is not None:
            # Model identity is non-sensitive metadata, not message content.
            await conn.execute(
                "INSERT INTO audit_log (agent_id, action, target, detail) "
                "VALUES (?, ?, ?, ?)",
                (None, "conversation.save", f"conversation:{row_id}", model),
            )
        await conn.commit()
    finally:
        await conn.close()
    assert row_id is not None  # AUTOINCREMENT PK always yields a rowid
    return row_id


async def get_recent_conversations(
    limit: int = 20,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return the most recent conversation turns in chronological order.

    The newest ``limit`` rows are selected, then returned oldest-first so the
    result can be fed directly to the model as conversation context.
    """
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, role, channel, content, created_at "
            "FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(row) for row in reversed(rows)]


# --- CRUD: agent state ------------------------------------------------------

# Map spec agent statuses onto the schema's CHECK constraint.
_AGENT_STATUS_ALIASES: dict[str, str] = {
    "idle": "idle",
    "working": "working",
    "busy": "working",
    "error": "error",
    "offline": "offline",
}


async def upsert_agent(
    agent_id: str,
    name: str,
    status: str,
    current_task: int | None = None,
    *,
    role: str | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """Insert a new agent row or update an existing one in place.

    Keyed on ``agent_id`` (the agents table primary key). ``current_task`` is
    interpreted as a ``tasks.id`` and stored in ``current_task_id``. ``role`` is
    required on first insert (it is ``NOT NULL``); on update it is left
    untouched when omitted.
    """
    normalized_status = _AGENT_STATUS_ALIASES.get(status.lower())
    if normalized_status is None:
        raise ValueError(
            f"invalid agent status {status!r}; expected one of "
            f"{sorted(_AGENT_STATUS_ALIASES)}"
        )

    conn = await connect(db_path)
    try:
        # role is NOT NULL: fall back to the agent name on first insert when the
        # caller did not supply one. On conflict we COALESCE so an omitted role
        # preserves the stored value rather than overwriting it.
        insert_role = role if role is not None else name
        await conn.execute(
            """
            INSERT INTO agents (id, name, role, status, current_task_id, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                name            = excluded.name,
                role            = COALESCE(?, agents.role),
                status          = excluded.status,
                current_task_id = excluded.current_task_id,
                updated_at      = datetime('now')
            """,
            (agent_id, name, insert_role, normalized_status, current_task, role),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_all_agents(*, db_path: Path | str = DEFAULT_DB_PATH) -> list[dict]:
    """Return every agent row, ordered by id for stable display."""
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, name, role, status, current_task_id, updated_at "
            "FROM agents ORDER BY id"
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(row) for row in rows]


async def get_agent(
    agent_id: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Return a single agent row by id, or ``None`` if it does not exist."""
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, name, role, status, current_task_id, updated_at "
            "FROM agents WHERE id = ?",
            (agent_id,),
        )
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return dict(row) if row is not None else None


# --- Write-only: audit log --------------------------------------------------


async def log_audit(
    agent_id: str | None,
    action: str,
    target: str | None = None,
    detail: str | None = None,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """Append a single audit record. Write-only by design (Security Rule 6).

    Records metadata only — agent id, action verb, optional target and a
    non-sensitive ``detail`` (e.g. a tool name or status code). Never pass
    message bodies, email contents, or voice transcripts here.
    """
    conn = await connect(db_path)
    try:
        await conn.execute(
            "INSERT INTO audit_log (agent_id, action, target, detail) "
            "VALUES (?, ?, ?, ?)",
            (agent_id, action, target, detail),
        )
        await conn.commit()
    finally:
        await conn.close()


# --- CRUD: tasks (agent-to-agent delegation) --------------------------------


async def create_task(
    creator_agent_id: str | None,
    assignee_agent_id: str | None,
    title: str,
    description: str | None = None,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Insert a delegated task and return its row id.

    The schema has a single ``description`` column, so ``title`` becomes its
    first line; any additional ``description`` is appended after a blank line.
    New tasks start in the ``queued`` state.
    """
    body = title if not description else f"{title}\n\n{description}"
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "INSERT INTO tasks (created_by, assigned_to, description) "
            "VALUES (?, ?, ?)",
            (creator_agent_id, assignee_agent_id, body),
        )
        row_id = cursor.lastrowid
        await conn.commit()
    finally:
        await conn.close()
    assert row_id is not None
    return row_id


async def update_task_status(
    task_id: int,
    status: str,
    *,
    result: str | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """Update a task's status (and optionally its result).

    Accepts spec status names ``pending|in_progress|completed|failed`` as well
    as the schema's native ``queued|in_progress|done|failed``; both are
    normalized to the stored value.
    """
    normalized = _TASK_STATUS_ALIASES.get(status.lower())
    if normalized is None:
        raise ValueError(
            f"invalid task status {status!r}; expected one of "
            f"{sorted(_TASK_STATUS_ALIASES)}"
        )

    conn = await connect(db_path)
    try:
        if result is None:
            await conn.execute(
                "UPDATE tasks SET status = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (normalized, task_id),
            )
        else:
            await conn.execute(
                "UPDATE tasks SET status = ?, result = ?, "
                "updated_at = datetime('now') WHERE id = ?",
                (normalized, result, task_id),
            )
        await conn.commit()
    finally:
        await conn.close()


async def get_agent_tasks(
    agent_id: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return tasks assigned to ``agent_id``, newest first."""
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, created_by, assigned_to, description, status, result, "
            "created_at, updated_at FROM tasks "
            "WHERE assigned_to = ? ORDER BY id DESC",
            (agent_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(row) for row in rows]
