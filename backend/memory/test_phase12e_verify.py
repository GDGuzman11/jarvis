"""Phase 12E verification — FTS5 keyword search + daily backup job.

Targeted checks for the keyword-search + backup work the backend-agent added in
Phase 12E:

* FTS5 virtual tables ``conversations_fts`` / ``memory_facts_fts`` created by
  :func:`backend.memory.database.init_db`.
* The two ``AFTER INSERT`` sync triggers that mirror base rows into FTS.
* :func:`backend.memory.database.search_conversations` /
  :func:`~backend.memory.database.search_memory_facts` keyword helpers.
* :meth:`backend.memory.manager.MemoryManager.search_keyword` — blended result
  shape + crash-safety on a malformed query.
* :func:`backend.main._write_backup_zip` — zip creation.
* :func:`backend.main._prune_old_backups` — retention pruning by mtime.

All in-memory / temp-file: no API key, no network, no audio device, and the
VectorStore is mocked so the heavy embedding model never loads.
"""

from __future__ import annotations

import os
import time
import zipfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import aiosqlite

from backend.memory import database
from backend.memory.manager import MemoryManager


# --- Helpers ----------------------------------------------------------------


async def _make_db(tmp_path) -> str:
    """Create a fresh, isolated SQLite db file and return its path string."""
    db_path = str(tmp_path / "phase12e.db")
    await database.init_db(db_path)
    return db_path


def _make_vector_store() -> MagicMock:
    """A VectorStore stand-in that never loads the embedding model."""
    vs = MagicMock()
    vs.__len__.return_value = 0
    return vs


async def _object_names(db_path: str, obj_type: str) -> set[str]:
    """Return the set of sqlite_master object names of ``obj_type``."""
    conn = await aiosqlite.connect(db_path)
    try:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", (obj_type,)
        )
        rows = await cursor.fetchall()
    finally:
        await conn.close()
    return {row[0] for row in rows}


# --- 1. FTS tables exist ----------------------------------------------------


async def test_fts_tables_created(tmp_path):
    """init_db creates both FTS5 virtual tables."""
    db_path = await _make_db(tmp_path)
    tables = await _object_names(db_path, "table")
    assert "conversations_fts" in tables, "conversations_fts virtual table missing"
    assert "memory_facts_fts" in tables, "memory_facts_fts virtual table missing"


# --- 2. FTS triggers exist --------------------------------------------------


async def test_fts_triggers_exist(tmp_path):
    """init_db creates the two AFTER INSERT sync triggers."""
    db_path = await _make_db(tmp_path)
    triggers = await _object_names(db_path, "trigger")
    assert "conversations_fts_insert" in triggers, "conversations sync trigger missing"
    assert "memory_facts_fts_insert" in triggers, "memory_facts sync trigger missing"


# --- 3. search_conversations returns matching rows --------------------------


async def test_search_conversations_returns_results(tmp_path):
    """A conversation row is found by keyword via the FTS shadow table."""
    db_path = await _make_db(tmp_path)
    await database.save_conversation(
        "user", "Remind me about the quarterly budget review", db_path=db_path
    )
    await database.save_conversation(
        "jarvis", "Of course, sir. I shall note the budget review.", db_path=db_path
    )

    results = await database.search_conversations(db_path=db_path, query="budget")
    assert results, "expected at least one conversation hit for 'budget'"
    assert any("budget" in r["content"].lower() for r in results)
    # FTS rowid mirrors the source conversations.id.
    assert all("rowid" in r and "channel" in r for r in results)


# --- 4. search_memory_facts returns matching rows ---------------------------


async def test_search_memory_facts_returns_results(tmp_path):
    """A memory_facts row is found by keyword via the FTS shadow table."""
    db_path = await _make_db(tmp_path)
    await database.save_memory_fact(
        "voice",
        "preference",
        "User prefers dark mode in the dashboard.",
        importance=0.9,
        db_path=db_path,
    )

    results = await database.search_memory_facts(db_path=db_path, query="dark")
    assert results, "expected at least one memory_facts hit for 'dark'"
    assert any("dark" in r["content"].lower() for r in results)
    assert all("rowid" in r and "category" in r for r in results)


# --- 5. MemoryManager.search_keyword blended result -------------------------


async def test_search_keyword_method(tmp_path):
    """search_keyword returns both keys and finds stored content."""
    db_path = await _make_db(tmp_path)
    mgr = MemoryManager(db_path=db_path, vector_store=_make_vector_store())

    await mgr.store("Schedule the deployment for Friday", role="user")
    await database.save_memory_fact(
        "voice",
        "general",
        "Deployment is scheduled for Friday.",
        importance=0.8,
        db_path=db_path,
    )

    result = await mgr.search_keyword("deployment")
    assert isinstance(result, dict)
    assert "conversations" in result and "memory_facts" in result
    # The stored conversation turn should match the keyword.
    assert any(
        "deployment" in r["content"].lower() for r in result["conversations"]
    ), "expected the stored conversation to match 'deployment'"
    assert any(
        "deployment" in r["content"].lower() for r in result["memory_facts"]
    ), "expected the stored fact to match 'deployment'"


# --- 6. search_keyword is crash-safe on a malformed query -------------------


async def test_search_keyword_no_crash_bad_query(tmp_path):
    """An unbalanced-quote FTS query degrades to empty lists, never raises."""
    db_path = await _make_db(tmp_path)
    mgr = MemoryManager(db_path=db_path, vector_store=_make_vector_store())
    await mgr.store("some content here", role="user")

    # An unterminated phrase quote is a malformed FTS5 MATCH expression.
    result = await mgr.search_keyword('broken "quote')
    assert result == {"conversations": [], "memory_facts": []}


# --- 7. backup zip is created -----------------------------------------------


async def test_backup_creates_zip(tmp_path):
    """_write_backup_zip zips the DB into data/backups/jarvis_<date>.zip."""
    from backend.main import _write_backup_zip

    db_path = await _make_db(tmp_path)
    db = tmp_path / "phase12e.db"
    # FAISS index/sidecar absent here — backup should still succeed with just DB.
    index_path = tmp_path / "faiss_index.bin"

    zip_path = _write_backup_zip(db, index_path)
    assert zip_path is not None, "expected a zip path to be returned"
    assert zip_path.exists(), "expected the backup zip to be written"
    assert zip_path.parent.name == "backups"
    assert zip_path.name.startswith("jarvis_") and zip_path.suffix == ".zip"

    # The DB file should be inside the archive (arcname = filename only).
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert db.name in names, f"db not found in archive: {names}"


# --- 7b. backup is WAL-safe: un-checkpointed writes survive ------------------


async def test_backup_is_wal_safe(tmp_path):
    """A WAL-mode DB with un-checkpointed writes backs up consistently.

    Regression guard for the WAL backup fix: the live ``.db`` file does not hold
    the most-recent committed pages under WAL (they sit in the ``-wal`` sidecar
    until a checkpoint). The online ``sqlite3.Connection.backup`` snapshot must
    fold those pages in, so the DB inside the zip must contain the just-written
    row and open cleanly.
    """
    import sqlite3
    import zipfile as _zipfile

    from backend.main import _write_backup_zip

    db_path = await _make_db(tmp_path)
    db = tmp_path / "phase12e.db"

    # Force WAL mode and write a row WITHOUT checkpointing, so the committed page
    # lives only in the -wal sidecar — exactly the torn/stale-backup scenario.
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "INSERT INTO conversations (role, content) VALUES ('user', ?)",
            ("uncheckpointed-wal-row",),
        )
        conn.commit()
        # NOTE: deliberately no wal_checkpoint here.
    finally:
        conn.close()

    index_path = tmp_path / "faiss_index.bin"  # absent — DB-only backup
    zip_path = _write_backup_zip(db, index_path)
    assert zip_path is not None and zip_path.exists()

    # Extract the snapshot DB and confirm the un-checkpointed row is present.
    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()
    with _zipfile.ZipFile(zip_path) as zf:
        assert db.name in zf.namelist()
        zf.extract(db.name, restore_dir)

    restored = sqlite3.connect(str(restore_dir / db.name))
    try:
        tables = {
            row[0]
            for row in restored.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "conversations" in tables, "restored DB missing core tables"
        rows = restored.execute(
            "SELECT content FROM conversations WHERE content = ?",
            ("uncheckpointed-wal-row",),
        ).fetchall()
        assert rows, "un-checkpointed WAL row was lost in the backup snapshot"
    finally:
        restored.close()

    # No stray temp snapshot files left behind in the backups dir.
    backups_dir = db.parent / "backups"
    leftovers = list(backups_dir.glob(".backup_*"))
    assert not leftovers, f"temp backup files not cleaned up: {leftovers}"


# --- 8. backup pruning by age -----------------------------------------------


async def test_backup_prune(tmp_path):
    """_prune_old_backups deletes zips older than the retention window, keeps recent."""
    from backend.main import BACKUP_RETENTION_DAYS, _prune_old_backups

    db_path = await _make_db(tmp_path)
    db = tmp_path / "phase12e.db"
    backups_dir = db.parent / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    # An old backup (mtime well past the retention window) and a fresh one.
    old_zip = backups_dir / "jarvis_2000-01-01.zip"
    new_zip = backups_dir / f"jarvis_{datetime.now():%Y-%m-%d}.zip"
    for z in (old_zip, new_zip):
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("placeholder.txt", "x")

    # Backdate the old zip's mtime past the retention cutoff.
    old_epoch = (
        datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS + 5)
    ).timestamp()
    os.utime(old_zip, (old_epoch, old_epoch))
    # Keep the new one's mtime current.
    now_epoch = time.time()
    os.utime(new_zip, (now_epoch, now_epoch))

    pruned = _prune_old_backups(db)
    assert pruned == 1, f"expected exactly 1 pruned, got {pruned}"
    assert not old_zip.exists(), "old backup should have been deleted"
    assert new_zip.exists(), "recent backup should have been kept"
