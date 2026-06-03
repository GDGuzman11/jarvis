---
name: tools-testing
description: Non-obvious gotchas when testing the Phase 6 Tools System (registry, sandbox, file ops)
metadata:
  type: reference
---

Verifying Phase 6 (`backend/tools/`). Test file: `backend/tools/test_phase6_verify.py` (14 cases, 6 areas).

**`file_ops.WORKSPACE_DIR` is resolved once at import.** It reads `JARVIS_WORKSPACE` env var (or `<root>/workspace`) at module-import time. To pin it to a temp dir, set `os.environ["JARVIS_WORKSPACE"]` BEFORE importing, then `importlib.reload(file_ops)` so the module-level `WORKSPACE_DIR` re-resolves. `_safe_path` is the single chokepoint; `../` and absolute-outside paths raise `PathTraversalError` (subclass of ValueError).

**`execute_code` is ASYNC** (`backend/tools/code_executor.py`) — `await execute_code(...)`. Returns `{"stdout","stderr","success"}`, NEVER raises. Blocked code (imports/os/subprocess/dunder) → `success=False`, not an exception. RestrictedPython emits a harmless SyntaxWarning on print-only snippets.

**`registry.PermissionError` shadows the builtin** (`backend/tools/registry.py`). Import it explicitly (`from backend.tools.registry import PermissionError as ToolPermissionError`) so `pytest.raises` matches the right class. `call_tool` is async; denied call audits then raises.

**Audit FK gotcha for temp DBs.** `audit_log.agent_id` REFERENCES `agents(id)` with `PRAGMA foreign_keys=ON`. `ToolRegistry._audit` is best-effort (swallows errors), so a missing agent row won't fail the tool call — but to test cleanly with a temp audit DB, `init_db(db_path=db)` then `upsert_agent(id, name, "idle", role=..., db_path=db)` for the 6 agents first. `upsert_agent` signature: `(agent_id, name, status, current_task=None, *, role=None, db_path=...)` — status is positional and validated.

**Registry wiring for tests:** `build_tool_registry(slack_client=, gmail_client=, db_path=)` from `backend/tools/wiring.py`. Slack/Gmail wrappers register only when a client is passed — pass MagicMock-with-AsyncMock-methods stubs to get all 12 tools. Standalone 6 (web_search, browse_url, read_file, write_file, list_files, execute_code) always register.

**Lifespan test:** same pattern as [[integrations-testing]] — patch every keystore getter the Slack/Gmail clients consult to raise `MissingCredentialError` so clients stay no-op, then `with TestClient(app)`: assert `app.state.tool_registry` populated and `/health` 200. See [[lifespan-testing]]. venv python: see [[uv-path]].
