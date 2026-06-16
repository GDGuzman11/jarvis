"""Async SQLite persistence layer for Helix.

This module owns the five core tables that back Helix's state:

* ``conversations`` — voice/text exchanges between the user and Helix.
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

# Default on-disk location for the Helix database. Resolves to
# ``<project root>/data/jarvis.db``. The directory is created on init.
DEFAULT_DB_PATH: Path = Path(__file__).resolve().parents[2] / "data" / "jarvis.db"

# --- Schema -----------------------------------------------------------------
# One CREATE TABLE statement per table. Executed in order by init_db().

_SCHEMA: tuple[str, ...] = (
    # conversations: one row per user<->Helix exchange (voice or text).
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        role        TEXT    NOT NULL CHECK (role IN ('user', 'jarvis')),
        channel     TEXT    NOT NULL DEFAULT 'voice'
                            CHECK (channel IN ('voice', 'text')
                                   OR channel LIKE 'agent:%'),
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
    # --- Phase 12 memory tables (Layer 2/3 structured stores) ---------------
    # memory_facts: distilled, high-value semantic facts (NOT raw transcripts).
    # Each high-scoring exchange becomes one compact declarative fact here; the
    # matching text is also added to the FAISS vector store so the two stay in
    # sync (see backend.memory.manager).
    """
    CREATE TABLE IF NOT EXISTS memory_facts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        source           TEXT    NOT NULL DEFAULT 'voice',
        category         TEXT    NOT NULL DEFAULT 'general',
        content          TEXT    NOT NULL,
        importance       REAL    NOT NULL DEFAULT 0.5,
        agent_id         TEXT    REFERENCES agents(id) ON DELETE SET NULL,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
        last_recalled_at TEXT
    )
    """,
    # people: contact profiles built from Gmail/Slack events and conversation.
    """
    CREATE TABLE IF NOT EXISTS people (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT    NOT NULL,
        email            TEXT,
        slack_user_id    TEXT,
        role             TEXT,
        notes            TEXT,
        last_contact_at  TEXT,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # open_loops: promises / reminders / follow-ups Helix must surface later.
    """
    CREATE TABLE IF NOT EXISTS open_loops (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        description      TEXT    NOT NULL,
        source           TEXT    NOT NULL DEFAULT 'voice',
        status           TEXT    NOT NULL DEFAULT 'open'
                                 CHECK (status IN ('open', 'resolved', 'dismissed')),
        due_at           TEXT,
        resolved_at      TEXT,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # decisions: the WHY behind choices — full reasoning + rejected alternatives.
    """
    CREATE TABLE IF NOT EXISTS decisions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        title            TEXT    NOT NULL,
        reasoning        TEXT    NOT NULL,
        alternatives     TEXT,
        agent_id         TEXT    REFERENCES agents(id) ON DELETE SET NULL,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    # agent_performance: per-agent task outcomes for self-improvement memory.
    """
    CREATE TABLE IF NOT EXISTS agent_performance (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id         TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
        task_type        TEXT    NOT NULL,
        outcome          TEXT    NOT NULL,
        correction_count INTEGER NOT NULL DEFAULT 0,
        notes            TEXT,
        created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
)

# --- Phase 12E: FTS5 keyword search -----------------------------------------
# Full-text (keyword) search over conversations + memory_facts, complementing
# the semantic (FAISS) recall. Two FTS5 virtual tables shadow the content of the
# base tables; AFTER INSERT triggers keep each shadow row in sync, keyed on the
# base row's id (the FTS rowid). The ``porter ascii`` tokenizer gives stemmed,
# case/diacritic-insensitive matching (e.g. "meeting" matches "meet").
#
# These run as a migration step in init_db (after the base tables exist) so the
# triggers can reference real columns. All statements are IF NOT EXISTS, so the
# step is idempotent and safe on every startup.
_FTS_SCHEMA: tuple[str, ...] = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts "
    "USING fts5(content, channel, tokenize='porter ascii')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_facts_fts "
    "USING fts5(content, category, tokenize='porter ascii')",
    "CREATE TRIGGER IF NOT EXISTS conversations_fts_insert "
    "AFTER INSERT ON conversations BEGIN "
    "INSERT INTO conversations_fts(rowid, content, channel) "
    "VALUES (new.id, new.content, new.channel); END",
    "CREATE TRIGGER IF NOT EXISTS memory_facts_fts_insert "
    "AFTER INSERT ON memory_facts BEGIN "
    "INSERT INTO memory_facts_fts(rowid, content, category) "
    "VALUES (new.id, new.content, new.category); END",
    # Phase 16C: an UPDATE action overwrites a fact's content in place (the
    # supersede/dedup path). Keep the FTS shadow in sync so keyword recall does
    # not surface the stale pre-update text. Mirrors the INSERT trigger.
    "CREATE TRIGGER IF NOT EXISTS memory_facts_fts_update "
    "AFTER UPDATE OF content, category ON memory_facts BEGIN "
    "UPDATE memory_facts_fts SET content = new.content, category = new.category "
    "WHERE rowid = new.id; END",
)

# Helpful indexes for the common access patterns (queue polling, audit reads).
_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_status "
    "ON tasks (assigned_to, status)",
    "CREATE INDEX IF NOT EXISTS idx_audit_log_agent_time "
    "ON audit_log (agent_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_conversations_created "
    "ON conversations (created_at)",
    # Phase 12 memory access patterns: recall by category, status, and contact.
    "CREATE INDEX IF NOT EXISTS idx_memory_facts_category "
    "ON memory_facts (category, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_open_loops_status "
    "ON open_loops (status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_people_email ON people (email)",
    "CREATE INDEX IF NOT EXISTS idx_agent_performance_agent "
    "ON agent_performance (agent_id, created_at)",
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
    logger.info("Initializing Helix database at %s", path)
    conn = await connect(path)
    try:
        for statement in _SCHEMA:
            await conn.execute(statement)
        for index in _INDEXES:
            await conn.execute(index)
        await conn.commit()
        await _migrate_conversations_channel(conn)
        # Phase 16A: add memory-quality columns to memory_facts (idempotent,
        # check-before-alter). Run after the base tables exist.
        await _migrate_memory_facts_quality_columns(conn)
        # Phase 12E: FTS5 shadow tables + sync triggers. Created after the base
        # tables (and the channel migration) so the triggers reference the final
        # conversations table. Idempotent (all IF NOT EXISTS).
        for statement in _FTS_SCHEMA:
            await conn.execute(statement)
        await conn.commit()
    finally:
        await conn.close()
    logger.info("Database schema ready (%d tables).", len(_SCHEMA))


async def _migrate_conversations_channel(conn: aiosqlite.Connection) -> None:
    """Relax the ``conversations.channel`` CHECK to permit ``agent:%`` channels.

    Phase 12C persists each agent's context to ``conversations`` under a
    ``channel = 'agent:<id>'`` value. Databases created before that change carry
    the old ``CHECK (channel IN ('voice','text'))`` constraint, which would
    reject agent turns. ``CREATE TABLE IF NOT EXISTS`` never alters an existing
    table, so this rebuilds the table in place only when the stale constraint is
    detected. Idempotent and a no-op on a fresh DB (which already has the new
    constraint).
    """
    cursor = await conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='conversations'"
    )
    row = await cursor.fetchone()
    if row is None:
        return
    ddl = row[0] or ""
    # Already migrated (or freshly created with the new constraint).
    if "agent:%" in ddl:
        return

    logger.info("Migrating conversations.channel CHECK to allow agent channels")
    await conn.execute("PRAGMA foreign_keys = OFF")
    try:
        await conn.execute(
            """
            CREATE TABLE conversations_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                role        TEXT    NOT NULL CHECK (role IN ('user', 'jarvis')),
                channel     TEXT    NOT NULL DEFAULT 'voice'
                                    CHECK (channel IN ('voice', 'text')
                                           OR channel LIKE 'agent:%'),
                content     TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        await conn.execute(
            "INSERT INTO conversations_new (id, role, channel, content, created_at) "
            "SELECT id, role, channel, content, created_at FROM conversations"
        )
        await conn.execute("DROP TABLE conversations")
        await conn.execute(
            "ALTER TABLE conversations_new RENAME TO conversations"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_created "
            "ON conversations (created_at)"
        )
        await conn.commit()
    finally:
        await conn.execute("PRAGMA foreign_keys = ON")


# --- Phase 16A: memory_facts quality columns --------------------------------
# Columns the multi-signal recall pipeline (Phase 16B) and the LLM extraction
# pipeline (Phase 16C) depend on. ``memory_facts`` predates them, and
# ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so they are
# added here with ``ALTER TABLE ... ADD COLUMN``. In SQLite, ADD COLUMN with a
# DEFAULT backfills every existing row with that default automatically, so no
# separate backfill UPDATE is needed.
#
#   confidence FLOAT DEFAULT 0.8   — extractor's 0.0–1.0 confidence in the fact
#   created_by TEXT DEFAULT 'system' — provenance: user|agent|inference|system
#   source_turn_id INTEGER         — conversations.id the fact was distilled from
#   access_count INTEGER DEFAULT 0 — times the fact has been recalled (16B)
#
# Phase 16C adds a single ``valid_to`` column to support the LLM extractor's
# DELETE/supersede action — a minimal soft-delete so a retracted/contradicted
# fact stops surfacing in recall without being physically removed. This is the
# *minimal* validity marker; Phase 16D extends it into a full bi-temporal model
# (valid_from, strength, half_life_days, superseded_by_fact_id, …). The shared
# check-before-alter migration below is idempotent, so 16D can add the remaining
# columns later without conflicting with this one.
#   valid_to TIMESTAMP             — NULL = active; set = archived/superseded (16C)
_MEMORY_FACTS_NEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("confidence", "FLOAT DEFAULT 0.8"),
    ("created_by", "TEXT DEFAULT 'system'"),
    ("source_turn_id", "INTEGER"),
    ("access_count", "INTEGER DEFAULT 0"),
    ("valid_to", "TIMESTAMP"),
)


async def _migrate_memory_facts_quality_columns(conn: aiosqlite.Connection) -> None:
    """Add Phase 16A quality columns to ``memory_facts`` if they are missing.

    Check-before-alter via ``PRAGMA table_info`` so the migration is idempotent
    and safe to run on every startup — already-present columns are skipped, and
    a fresh DB (where the base CREATE already lacks them) gets them all added on
    first run. A no-op once every column exists.
    """
    cursor = await conn.execute("PRAGMA table_info(memory_facts)")
    rows = await cursor.fetchall()
    if not rows:
        # Table somehow absent (should not happen — base schema ran first).
        return
    existing = {row["name"] for row in rows}

    added: list[str] = []
    for name, decl in _MEMORY_FACTS_NEW_COLUMNS:
        if name in existing:
            continue
        await conn.execute(
            f"ALTER TABLE memory_facts ADD COLUMN {name} {decl}"
        )
        added.append(name)

    if added:
        await conn.commit()
        logger.info(
            "Added memory_facts quality columns: %s", ", ".join(added)
        )


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
    channel: str | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return the most recent conversation turns in chronological order.

    The newest ``limit`` rows are selected, then returned oldest-first so the
    result can be fed directly to the model as conversation context. When
    ``channel`` is supplied, only turns on that channel are returned — this lets
    an agent restore *its own* context (``channel='agent:<id>'``) without pulling
    in unrelated voice/text turns.
    """
    conn = await connect(db_path)
    try:
        if channel is None:
            cursor = await conn.execute(
                "SELECT id, role, channel, content, created_at "
                "FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = await conn.execute(
                "SELECT id, role, channel, content, created_at "
                "FROM conversations WHERE channel = ? ORDER BY id DESC LIMIT ?",
                (channel, limit),
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


async def rename_agent(
    agent_id: str,
    name: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> bool:
    """Update an agent's display name in place. Returns ``True`` if a row matched.

    Only the ``name`` column (and ``updated_at``) is touched — status, role, and
    the current task are left untouched. Returns ``False`` when no agent with
    ``agent_id`` exists, so callers can map a miss to a 404 without a separate
    lookup.
    """
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "UPDATE agents SET name = ?, updated_at = datetime('now') WHERE id = ?",
            (name, agent_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
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


# --- Phase 12: memory_facts (distilled semantic facts) ----------------------


async def save_memory_fact(
    source: str,
    category: str,
    content: str,
    importance: float = 0.5,
    agent_id: str | None = None,
    *,
    created_by: str | None = None,
    confidence: float | None = None,
    source_turn_id: int | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Persist a single distilled memory fact and return its row id.

    ``content`` is a compact declarative fact (e.g. "User prefers dark mode."),
    never a raw transcript. ``importance`` is the evaluator's 0.0–1.0 score.

    Phase 16C provenance columns are optional so every existing caller keeps its
    behaviour: when ``created_by`` / ``confidence`` are omitted the schema
    defaults (``'system'`` / ``0.8``) apply. The LLM extractor (Phase 16C) passes
    ``created_by='user'|'inference'`` and the model's per-fact ``confidence``.
    """
    # Only name the provenance columns when a value is supplied, so omitted
    # arguments fall through to the column DEFAULTs rather than being forced to
    # NULL (which would clobber the 'system'/0.8 defaults).
    columns = ["source", "category", "content", "importance", "agent_id"]
    values: list[object] = [
        source, category, content, float(importance), agent_id,
    ]
    if created_by is not None:
        columns.append("created_by")
        values.append(created_by)
    if confidence is not None:
        columns.append("confidence")
        values.append(float(confidence))
    if source_turn_id is not None:
        columns.append("source_turn_id")
        values.append(int(source_turn_id))

    placeholders = ", ".join("?" for _ in columns)
    col_sql = ", ".join(columns)
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            # col_sql/placeholders are built from the hardcoded `columns` list,
            # never from caller input — the values stay parameterised.
            f"INSERT INTO memory_facts ({col_sql}) VALUES ({placeholders})",  # noqa: S608
            tuple(values),
        )
        row_id = cursor.lastrowid
        await conn.commit()
    finally:
        await conn.close()
    assert row_id is not None
    return row_id


async def update_memory_fact(
    fact_id: int,
    content: str,
    *,
    importance: float | None = None,
    confidence: float | None = None,
    created_by: str | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> bool:
    """Overwrite an existing fact's content in place (Phase 16C UPDATE action).

    The LLM extractor's ``UPDATE`` action supersedes a near-duplicate fact rather
    than inserting a second row — e.g. "I moved to Boston" overwrites a prior
    "User lives in Portland." Only the ``content`` (and any supplied quality
    fields) change; ``created_at`` is preserved so the fact's age is unchanged.
    The ``memory_facts_fts_update`` trigger keeps the keyword index in sync.

    Returns ``True`` when a row matched. The FAISS vector for the *old* text is
    left in place (the store is append-only); recall ranking tolerates the
    near-duplicate because the new text is added alongside it. A proper FAISS
    tombstone is deferred to Phase 16D's bi-temporal rework.
    """
    sets = ["content = ?"]
    params: list[object] = [content]
    if importance is not None:
        sets.append("importance = ?")
        params.append(float(importance))
    if confidence is not None:
        sets.append("confidence = ?")
        params.append(float(confidence))
    if created_by is not None:
        sets.append("created_by = ?")
        params.append(created_by)
    params.append(int(fact_id))

    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            # `sets` is assembled from hardcoded column fragments only; every
            # bound value is parameterised via `params`.
            f"UPDATE memory_facts SET {', '.join(sets)} WHERE id = ?",  # noqa: S608
            tuple(params),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def invalidate_memory_fact(
    fact_id: int,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> bool:
    """Soft-delete a fact by stamping ``valid_to`` (Phase 16C DELETE action).

    Used when the LLM extractor decides an existing fact has been retracted or
    contradicted. The row is kept (archival, not destruction) but excluded from
    active recall via the ``valid_to IS NULL`` filter the recall pipeline applies.
    Returns ``True`` when a row matched. Idempotent — re-stamping an already
    archived fact simply refreshes its ``valid_to``.

    TODO(Phase 16D): replace this minimal marker with the full bi-temporal
    write-policy machinery (last-write-wins / evidence-weighted / merge /
    await-confirmation) and a FAISS tombstone so the archived vector is dropped.
    """
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "UPDATE memory_facts SET valid_to = datetime('now') WHERE id = ?",
            (int(fact_id),),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def get_memory_facts(
    category: str | None = None,
    limit: int = 20,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return the most recent memory facts, optionally filtered by ``category``.

    Newest first. When ``category`` is ``None`` all categories are returned.
    """
    conn = await connect(db_path)
    try:
        if category is None:
            cursor = await conn.execute(
                "SELECT id, source, category, content, importance, agent_id, "
                "created_at, last_recalled_at FROM memory_facts "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = await conn.execute(
                "SELECT id, source, category, content, importance, agent_id, "
                "created_at, last_recalled_at FROM memory_facts "
                "WHERE category = ? ORDER BY id DESC LIMIT ?",
                (category, limit),
            )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(row) for row in rows]


async def mark_facts_recalled(
    fact_ids: list[int],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """Stamp recall metadata on each recalled fact (Phase 16A + 16B).

    A single combined UPDATE per fact stamps ``last_recalled_at = now`` (Phase
    16A — recency signal) and increments ``access_count`` (Phase 16B — frequency
    signal). Both feed the multi-signal re-ranking pipeline. Each row is keyed by
    primary key, so the write stays cheap even on the recall hot path. Uses
    ``datetime('now')`` to match how every other timestamp in this schema is
    stored. A no-op on an empty list. The caller passes the ids of the facts
    actually returned by a recall, so each is stamped once per recall; if the
    same id appears twice in one call it is simply bumped twice, which is fine.
    """
    if not fact_ids:
        return
    conn = await connect(db_path)
    try:
        await conn.executemany(
            "UPDATE memory_facts "
            "SET last_recalled_at = datetime('now'), "
            "    access_count = COALESCE(access_count, 0) + 1 "
            "WHERE id = ?",
            [(int(fid),) for fid in fact_ids],
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_memory_facts_by_ids(
    fact_ids: list[int],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Batch-fetch quality metadata for a set of fact ids in one query.

    Returns one dict per matching row with the columns the Phase 16B re-ranking
    pipeline scores against: ``id``, ``importance``, ``last_recalled_at``,
    ``created_at`` and ``access_count``. Used to enrich a FAISS candidate pool
    without a per-candidate round trip — a single ``WHERE id IN (...)`` keeps the
    recall hot path cheap. Order is unspecified (the caller maps by id); an empty
    input yields ``[]`` without touching the database.
    """
    if not fact_ids:
        return []
    ids = [int(fid) for fid in fact_ids]
    placeholders = ",".join("?" for _ in ids)
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, importance, last_recalled_at, created_at, access_count, "
            "valid_to "
            f"FROM memory_facts WHERE id IN ({placeholders})",
            ids,
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(row) for row in rows]


# --- Phase 12: people (contact profiles) ------------------------------------


async def save_person(
    name: str,
    email: str | None = None,
    slack_user_id: str | None = None,
    role: str | None = None,
    notes: str | None = None,
    last_contact_at: str | None = None,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Insert or update a person profile, keyed by ``email`` when provided.

    When a row with the same ``email`` already exists it is updated in place
    (non-null arguments win; omitted fields keep their stored value) and its id
    is returned. Otherwise a new row is inserted. With no ``email`` a new row is
    always inserted (we cannot dedupe an anonymous contact).
    """
    conn = await connect(db_path)
    try:
        existing = None
        if email:
            cursor = await conn.execute(
                "SELECT id FROM people WHERE email = ?", (email,)
            )
            existing = await cursor.fetchone()

        if existing is not None:
            await conn.execute(
                """
                UPDATE people SET
                    name            = COALESCE(?, name),
                    slack_user_id   = COALESCE(?, slack_user_id),
                    role            = COALESCE(?, role),
                    notes           = COALESCE(?, notes),
                    last_contact_at = COALESCE(?, last_contact_at)
                WHERE id = ?
                """,
                (name, slack_user_id, role, notes, last_contact_at, existing["id"]),
            )
            row_id = int(existing["id"])
        else:
            cursor = await conn.execute(
                "INSERT INTO people (name, email, slack_user_id, role, notes, "
                "last_contact_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, email, slack_user_id, role, notes, last_contact_at),
            )
            row_id = cursor.lastrowid
        await conn.commit()
    finally:
        await conn.close()
    assert row_id is not None
    return int(row_id)


async def get_person_by_email(
    email: str,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict | None:
    """Return a single person profile by ``email``, or ``None`` if not found."""
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT id, name, email, slack_user_id, role, notes, "
            "last_contact_at, created_at FROM people WHERE email = ?",
            (email,),
        )
        row = await cursor.fetchone()
    finally:
        await conn.close()
    return dict(row) if row is not None else None


# --- Phase 12: open_loops (promises / reminders / follow-ups) ---------------


async def save_open_loop(
    description: str,
    source: str = "voice",
    due_at: str | None = None,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Create an open loop (a tracked promise/reminder) and return its row id.

    New loops start in the ``open`` state. ``due_at`` is an optional ISO/SQLite
    datetime string used to surface overdue items at session start.
    """
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "INSERT INTO open_loops (description, source, due_at) VALUES (?, ?, ?)",
            (description, source, due_at),
        )
        row_id = cursor.lastrowid
        await conn.commit()
    finally:
        await conn.close()
    assert row_id is not None
    return row_id


async def get_open_loops(
    status: str = "open",
    older_than_hours: float | None = None,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[dict]:
    """Return open loops with the given ``status`` (default ``'open'``).

    Ordered oldest-first so the most stale promises surface first. When
    ``older_than_hours`` is given, only loops created at least that many hours
    ago are returned — used at session start to surface *overdue* items the user
    hasn't addressed, without nagging about something they said moments ago.
    """
    conn = await connect(db_path)
    try:
        if older_than_hours is None:
            cursor = await conn.execute(
                "SELECT id, description, source, status, due_at, resolved_at, "
                "created_at FROM open_loops WHERE status = ? ORDER BY id ASC",
                (status,),
            )
        else:
            # SQLite datetime arithmetic: compare created_at against a cutoff
            # computed as 'now' minus the requested age in hours.
            cutoff = f"-{float(older_than_hours)} hours"
            cursor = await conn.execute(
                "SELECT id, description, source, status, due_at, resolved_at, "
                "created_at FROM open_loops WHERE status = ? "
                "AND created_at <= datetime('now', ?) ORDER BY id ASC",
                (status, cutoff),
            )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return [dict(row) for row in rows]


async def get_open_loops_async(
    db_path: Path | str = DEFAULT_DB_PATH,
    status: str = "open",
    older_than_hours: float | None = None,
) -> list[dict]:
    """Positional-``db_path`` wrapper around :func:`get_open_loops` (Phase 12D).

    The voice pipeline surfaces overdue loops at session start and calls this
    with ``db_path`` first, so this adapts that call shape onto the keyword-only
    ``get_open_loops`` signature. Behaviour is otherwise identical.
    """
    return await get_open_loops(
        status, older_than_hours, db_path=db_path
    )


# --- Phase 12: decisions (the WHY behind choices) ---------------------------


async def save_decision(
    title: str,
    reasoning: str,
    alternatives: str | None = None,
    agent_id: str | None = None,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Persist a decision record (title + reasoning) and return its row id.

    The ``reasoning`` (the WHY) is the valuable part — it lets future reasoning
    avoid relitigating settled choices. ``alternatives`` records what was
    considered and rejected.
    """
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "INSERT INTO decisions (title, reasoning, alternatives, agent_id) "
            "VALUES (?, ?, ?, ?)",
            (title, reasoning, alternatives, agent_id),
        )
        row_id = cursor.lastrowid
        await conn.commit()
    finally:
        await conn.close()
    assert row_id is not None
    return row_id


# --- Phase 12: agent_performance (per-agent task outcomes) ------------------


async def save_agent_performance(
    agent_id: str,
    task_type: str,
    outcome: str,
    correction_count: int = 0,
    notes: str | None = None,
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    """Record one agent task outcome and return its row id.

    ``outcome`` is typically ``'success' | 'corrected' | 'failed'``;
    ``correction_count`` is how many rounds of correction the task needed.
    """
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "INSERT INTO agent_performance (agent_id, task_type, outcome, "
            "correction_count, notes) VALUES (?, ?, ?, ?, ?)",
            (agent_id, task_type, outcome, int(correction_count), notes),
        )
        row_id = cursor.lastrowid
        await conn.commit()
    finally:
        await conn.close()
    assert row_id is not None
    return row_id


# --- Phase 12E: FTS5 keyword search -----------------------------------------


async def search_conversations(
    db_path: Path | str = DEFAULT_DB_PATH,
    query: str = "",
    limit: int = 20,
) -> list[dict]:
    """Keyword-search ``conversations`` via the FTS5 shadow table.

    Returns the best-matching conversation turns (by FTS5 ``rank``) for the
    given ``query``, each as a dict with ``rowid`` (the source
    ``conversations.id``) plus the indexed ``content`` and ``channel`` columns.
    An empty/whitespace query returns ``[]`` without touching the database.
    Never raises on a malformed FTS query — it degrades to an empty result so a
    bad search term can't break the caller.
    """
    query = (query or "").strip()
    if not query:
        return []
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT rowid, content, channel FROM conversations_fts "
            "WHERE conversations_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        )
        rows = await cursor.fetchall()
    except aiosqlite.OperationalError:
        # Malformed MATCH expression (e.g. unbalanced quotes) — treat as no hits.
        logger.warning("search_conversations: bad FTS query %r", query)
        return []
    finally:
        await conn.close()
    return [dict(row) for row in rows]


async def search_memory_facts(
    db_path: Path | str = DEFAULT_DB_PATH,
    query: str = "",
    limit: int = 20,
) -> list[dict]:
    """Keyword-search ``memory_facts`` via the FTS5 shadow table.

    Returns the best-matching distilled facts (by FTS5 ``rank``) for the given
    ``query``, each as a dict with ``rowid`` (the source ``memory_facts.id``)
    plus the indexed ``content`` and ``category`` columns. An empty/whitespace
    query returns ``[]``; a malformed FTS query degrades to ``[]`` rather than
    raising.
    """
    query = (query or "").strip()
    if not query:
        return []
    conn = await connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT rowid, content, category FROM memory_facts_fts "
            "WHERE memory_facts_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        )
        rows = await cursor.fetchall()
    except aiosqlite.OperationalError:
        logger.warning("search_memory_facts: bad FTS query %r", query)
        return []
    finally:
        await conn.close()
    return [dict(row) for row in rows]
