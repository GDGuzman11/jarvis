"""Phase 6 — Tools System verification (debugger-agent).

Covers, per the Phase 6 verify checklist:

* permission matrix enforcement (production_lead = all, security = read-only,
  denied call raises PermissionError);
* code-executor sandbox blocks os/subprocess and runs safe code;
* file-ops path-traversal rejection + roundtrip;
* web_search schema validity + empty-query no-crash;
* every registered Claude schema is well-formed; Slack + Gmail registered;
* lifespan wires app.state.tool_registry and /health returns 200.

Run:
    .venv\\Scripts\\python.exe -m pytest backend/tools/test_phase6_verify.py -q
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

# Point the file-ops workspace at a temp dir BEFORE importing file_ops, since
# WORKSPACE_DIR is resolved once at import time from JARVIS_WORKSPACE.
_TMP_WORKSPACE = Path(os.environ.get("PYTEST_TMP_WORKSPACE", "")) or None


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A temp workspace directory used for file-ops tests."""
    ws = tmp_path_factory.mktemp("jarvis_ws")
    return ws


@pytest.fixture(scope="module")
def file_ops_mod(workspace: Path):
    """Import file_ops with WORKSPACE_DIR pinned to the temp workspace."""
    os.environ["JARVIS_WORKSPACE"] = str(workspace)
    import importlib

    from backend.tools import file_ops

    importlib.reload(file_ops)
    assert file_ops.WORKSPACE_DIR == workspace.resolve()
    return file_ops


@pytest.fixture(scope="module")
def temp_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A temp SQLite DB initialised with the schema + the 6 agent rows.

    The audit_log.agent_id has a FK to agents(id) with PRAGMA foreign_keys=ON,
    so we seed the agent rows; otherwise audit writes would (silently) fail the
    FK and the registry's best-effort _audit would swallow it.
    """
    import asyncio

    from backend.memory import database

    db = tmp_path_factory.mktemp("jarvis_db") / "audit.db"

    async def _setup() -> None:
        await database.init_db(db_path=db)
        for agent_id in (
            "production_lead",
            "frontend",
            "backend",
            "security",
            "marketing",
            "content",
        ):
            await database.upsert_agent(
                agent_id, agent_id, "idle", role=agent_id, db_path=db
            )

    asyncio.run(_setup())
    return db


@pytest.fixture()
def registry(temp_db: Path, file_ops_mod):
    """A ToolRegistry with every standalone tool + Slack/Gmail wrappers.

    db_path points at the temp audit DB. Slack/Gmail use lightweight stub
    clients so their wrappers register (we only call sync/local tools here).
    """
    from unittest.mock import AsyncMock, MagicMock

    from backend.tools.wiring import build_tool_registry

    slack = MagicMock()
    slack.send_message = AsyncMock(return_value=True)
    slack.get_dm_history = AsyncMock(return_value=[])
    slack.get_unread_mentions = AsyncMock(return_value=[])

    gmail = MagicMock()
    gmail.get_inbox = AsyncMock(return_value=[])
    gmail.send_email = AsyncMock(return_value=True)
    gmail.draft_email = AsyncMock(return_value="")

    return build_tool_registry(
        slack_client=slack, gmail_client=gmail, db_path=temp_db
    )


# --- 1) Permission enforcement ---------------------------------------------


def test_production_lead_gets_all_tools(registry) -> None:
    from backend.tools.registry import ALL_TOOLS

    names = {s["name"] for s in registry.get_tools_for_agent("production_lead")}
    assert names == set(ALL_TOOLS)


def test_security_gets_only_read_only_tools(registry) -> None:
    from backend.tools.registry import READ_ONLY_TOOLS, WRITE_TOOLS, COMMS_TOOLS

    names = {s["name"] for s in registry.get_tools_for_agent("security")}
    assert names == set(READ_ONLY_TOOLS)
    # No mutating tools leak into the security set.
    assert not (names & (WRITE_TOOLS | COMMS_TOOLS))


@pytest.mark.asyncio
async def test_security_write_file_raises_permission_error(registry) -> None:
    from backend.tools.registry import PermissionError as ToolPermissionError

    with pytest.raises(ToolPermissionError):
        await registry.call_tool(
            "security", "write_file", {"path": "x.txt", "content": "x"}
        )


# --- 2) Sandbox blocks dangerous code --------------------------------------


@pytest.mark.asyncio
async def test_sandbox_blocks_os_system() -> None:
    from backend.tools.code_executor import execute_code

    result = await execute_code("import os\nos.system('echo pwned')")
    assert result["success"] is False


@pytest.mark.asyncio
async def test_sandbox_blocks_subprocess() -> None:
    from backend.tools.code_executor import execute_code

    result = await execute_code("import subprocess")
    assert result["success"] is False


@pytest.mark.asyncio
async def test_sandbox_allows_safe_print() -> None:
    from backend.tools.code_executor import execute_code

    result = await execute_code("print('hello')")
    assert result["success"] is True
    assert "hello" in result["stdout"]


# --- 3) Path traversal rejected --------------------------------------------


def test_write_file_rejects_dotdot_traversal(file_ops_mod) -> None:
    with pytest.raises(file_ops_mod.PathTraversalError):
        file_ops_mod.write_file("../escape.txt", "x")


def test_write_file_rejects_absolute_outside(file_ops_mod) -> None:
    # An absolute path outside the workspace (Windows-safe target).
    outside = "C:/Windows/Temp/escape.txt" if os.name == "nt" else "/etc/passwd"
    with pytest.raises(file_ops_mod.PathTraversalError):
        file_ops_mod.write_file(outside, "x")


def test_file_roundtrip(file_ops_mod) -> None:
    assert file_ops_mod.write_file("safe.txt", "hello") is True
    assert file_ops_mod.read_file("safe.txt") == "hello"


# --- 4) Web search ----------------------------------------------------------


def test_web_search_schema_is_valid() -> None:
    from backend.tools.web_search import WEB_SEARCH_SCHEMA

    for key in ("name", "description", "input_schema"):
        assert key in WEB_SEARCH_SCHEMA
    assert WEB_SEARCH_SCHEMA["input_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_web_search_empty_returns_empty_list() -> None:
    from backend.tools.web_search import web_search

    assert await web_search("") == []


# --- 5) Claude schemas ------------------------------------------------------


def test_every_registered_schema_is_well_formed(registry) -> None:
    for name in registry.list_tools():
        schema = next(
            s for s in registry.get_tools_for_agent("production_lead")
            if s["name"] == name
        )
        assert schema["name"] == name
        assert isinstance(schema.get("description"), str) and schema["description"]
        assert schema["input_schema"]["type"] == "object"


def test_slack_and_gmail_tools_registered(registry) -> None:
    names = set(registry.list_tools())
    assert {
        "slack_send_message",
        "slack_get_dm_history",
        "slack_get_unread_mentions",
    } <= names
    assert {
        "gmail_get_inbox",
        "gmail_send_email",
        "gmail_draft_email",
    } <= names


# --- 6) Lifespan ------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient that runs the real FastAPI lifespan with credentials stubbed.

    Patch every keystore getter the Slack/Gmail clients consult to raise the
    missing-credential error so the lifespan degrades gracefully (no network,
    no listener) while still building the tool registry.
    """
    from backend.security.keystore import MissingCredentialError
    from backend.integrations import slack_client as slack_mod
    from backend.integrations import gmail_client as gmail_mod

    def _raise(name: str):
        def _getter(*_a, **_k):
            raise MissingCredentialError(name)

        return _getter

    for attr in ("get_slack_bot_token", "get_slack_app_token"):
        monkeypatch.setattr(slack_mod.keystore, attr, _raise(attr), raising=False)
    for attr in (
        "get_gmail_client_id",
        "get_gmail_client_secret",
        "get_gmail_refresh_token",
    ):
        monkeypatch.setattr(gmail_mod.keystore, attr, _raise(attr), raising=False)

    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_lifespan_sets_tool_registry_and_health(client: TestClient) -> None:
    app = client.app
    assert hasattr(app.state, "tool_registry")
    registry = app.state.tool_registry
    assert registry is not None
    assert len(registry.list_tools()) >= 6

    resp = client.get("/health")
    assert resp.status_code == 200
