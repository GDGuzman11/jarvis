---
name: phase12e-search-backup-testing
description: How to test Phase 12E (FTS5 keyword search + daily backup job); helper signatures, mtime-based prune, baseline 134/135
metadata:
  type: reference
---

Phase 12E adds FTS5 keyword search + daily backup on top of Phase 12 memory. See also [[phase12d-memory-intelligence-testing]], [[phase12c-agent-memory-testing]], [[phase12-memory-testing]]. Test file: `backend/memory/test_phase12e_verify.py`, 8 targeted tests (all pass).

**What changed in 12E:**
- `database.py` — `_FTS_SCHEMA` tuple creates `conversations_fts` + `memory_facts_fts` (fts5, `tokenize='porter ascii'`) + AFTER INSERT triggers `conversations_fts_insert`/`memory_facts_fts_insert` (mirror base row into FTS keyed on `new.id` as rowid). Applied in `init_db` AFTER `_migrate_conversations_channel`. Helpers `search_conversations(db_path, query, limit)` / `search_memory_facts(db_path, query, limit)` — NOTE db_path is FIRST positional arg; both strip empty query→`[]`, catch `aiosqlite.OperationalError`→`[]` (malformed MATCH never raises). Return dicts have `rowid` + indexed cols (content+channel / content+category).
- `manager.py::search_keyword(query, limit=20)` — returns `{"conversations":[...], "memory_facts":[...]}`; wraps both helpers, never raises (broad except→two empty lists).
- `main.py` — `_write_backup_zip(db_path, vector_store_path)->Path|None` zips db + faiss index + `<index>.bin.meta.json` into `db_path.parent/"backups"/jarvis_<YYYY-MM-DD>.zip` (arcname=filename only; skips missing sources; returns None if none present; SAME-DAY re-run overwrites same file). `_prune_old_backups(db_path, retention_days=30)->int` deletes `jarvis_*.zip` by **mtime** (NOT filename date) older than cutoff. `_backup_loop(db_path, vector_store_path)` runs both via `asyncio.to_thread` at startup then every `BACKUP_INTERVAL_S=86400`s, cancellable. Constants: `BACKUP_INTERVAL_S`, `BACKUP_RETENTION_DAYS`.

**Test recipes:** sqlite_master checks via raw `aiosqlite.connect` (type='table'/'trigger'). FTS search test = `save_conversation`/`save_memory_fact` then call helper with a keyword (porter stemming: "dark" matches "dark mode"). search_keyword crash test = `'broken "quote'` (unbalanced phrase quote) → assert `== {"conversations":[],"memory_facts":[]}`. Backup tests import from `backend.main`: zip test calls `_write_backup_zip(db, missing_index_path)` (DB-only backup still valid), assert zip exists + db.name in `namelist()`. Prune test MUST backdate the old zip via `os.utime(old_zip, (epoch, epoch))` to past `BACKUP_RETENTION_DAYS+5` days (prune is mtime-based, not filename-based) — assert returns 1, old deleted, fresh kept. MemoryManager needs `vector_store=MagicMock` with `__len__.return_value=0`.

**Baseline 2026-06-05 (Phase 12E):** full `pytest backend/` = **134 passed / 1 failed (135 total)**. The 1 fail = SAME pre-existing `test_no_secrets_committed_in_source_files` (Google OAuth *client id* `105705049468...`, public, `get_gmail_token.py:9` + quoted copy `docs/TEST_HISTORY.md:110`) owned by security-agent. 12D was 125/127 (had 2 fails incl. the now-fixed detect_open_loops bug); 12E +8 new tests, all pass, no regression. asyncio_mode=auto. Run: `.venv/Scripts/python.exe -m pytest backend/ -q`.
