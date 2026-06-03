"""Phase 1 verification: backend.memory.database SQLite schema.

Verifies:
1. backend.memory.database imports.
2. init_db() creates a DB at a temp path.
3. All 5 tables exist: conversations, agents, tasks, tools, audit_log.
4. init_db() is idempotent (second call raises no error).
5. audit_log has no 'content' or 'message_body' column (Security Rule 6).
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
from pathlib import Path

EXPECTED_TABLES = {"conversations", "agents", "tasks", "tools", "audit_log"}
FORBIDDEN_AUDIT_COLUMNS = {"content", "message_body"}


def main() -> int:
    # 1. import
    from backend.memory import database

    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis_test_"))
    db_path = tmp_dir / "test_jarvis.db"

    # 2. first init
    asyncio.run(database.init_db(db_path))
    assert db_path.exists(), f"DB file was not created at {db_path}"

    # 3. assert all 5 tables exist
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {r[0] for r in rows}
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables: {missing}. Found: {tables}"

        # 4. idempotency — second call must not error
        asyncio.run(database.init_db(db_path))
        rows2 = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables2 = {r[0] for r in rows2}
        assert EXPECTED_TABLES <= tables2, (
            f"Tables changed after 2nd init: {tables2}"
        )

        # 5. audit_log metadata-only: no content/message_body columns
        cols = {c[1] for c in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
        leaked = FORBIDDEN_AUDIT_COLUMNS & cols
        assert not leaked, f"audit_log leaks forbidden columns: {leaked} (cols={cols})"
    finally:
        conn.close()

    print("PASS: backend.memory.database imported")
    print(f"PASS: init_db() created DB at {db_path}")
    print(f"PASS: all 5 tables exist -> {sorted(EXPECTED_TABLES)}")
    print("PASS: init_db() idempotent (second call OK)")
    print(f"PASS: audit_log columns metadata-only -> {sorted(cols)}")
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
