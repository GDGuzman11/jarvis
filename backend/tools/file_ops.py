"""Sandboxed file read/write/list tool for Jarvis.

Gives agents the ability to read, write, and list files — but **only inside a
single workspace directory** (Security Rule 4: workspace-only filesystem). Every
path supplied by a caller (or the model) is resolved to an absolute path and
checked to be contained within :data:`WORKSPACE_DIR`. Anything that escapes the
workspace via ``..`` traversal, a symlink, or an absolute path elsewhere on disk
is rejected with :class:`PathTraversalError` — it is never opened.

Workspace
---------
The workspace defaults to ``<project root>/workspace`` and is created on demand.
It can be overridden for tests/embedding via the ``JARVIS_WORKSPACE`` environment
variable. All three operations accept paths *relative to the workspace root*;
absolute paths are accepted only if they already resolve inside the workspace.

The Claude API ``tool_use`` schemas are exported as :data:`READ_FILE_SCHEMA`,
:data:`WRITE_FILE_SCHEMA`, and :data:`LIST_FILES_SCHEMA`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.logging_config import get_logger

log = get_logger(__name__)


def _resolve_workspace() -> Path:
    """Resolve the workspace root, honouring the JARVIS_WORKSPACE override."""
    override = os.environ.get("JARVIS_WORKSPACE")
    if override:
        return Path(override).resolve()
    # <project root>/workspace — project root is three levels up from this file
    # (backend/tools/file_ops.py -> backend/tools -> backend -> root).
    return (Path(__file__).resolve().parents[2] / "workspace").resolve()


# The single directory all file operations are confined to. Resolved once at
# import; callers may re-read it via the env override before import for tests.
WORKSPACE_DIR: Path = _resolve_workspace()

# Largest file (bytes) read or written in one call — keeps tool payloads bounded
# and avoids loading something enormous into memory or a model context.
MAX_FILE_BYTES = 1_000_000


class PathTraversalError(ValueError):
    """Raised when a requested path escapes the workspace sandbox."""


def _safe_path(path: str) -> Path:
    """Resolve ``path`` against the workspace and verify it stays inside it.

    Returns the resolved absolute path. Raises :class:`PathTraversalError` if the
    resolved path is not contained within :data:`WORKSPACE_DIR` — this is the one
    chokepoint every read/write/list goes through, so traversal is impossible to
    bypass from a single call site.
    """
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    raw = (path or "").strip()
    if not raw:
        raise PathTraversalError("empty path")

    candidate = Path(raw)
    # An absolute path is allowed only if it already lives in the workspace;
    # otherwise join it onto the workspace root. Either way we then resolve()
    # to collapse any ".." and follow symlinks before the containment check.
    combined = candidate if candidate.is_absolute() else (WORKSPACE_DIR / candidate)
    resolved = combined.resolve()

    # The authoritative check: resolved must be the workspace itself or below it.
    if resolved != WORKSPACE_DIR and WORKSPACE_DIR not in resolved.parents:
        raise PathTraversalError(
            f"path escapes workspace sandbox: {path!r}"
        )
    return resolved


def read_file(path: str) -> str:
    """Read and return a text file's contents from inside the workspace.

    ``path`` is relative to the workspace root (absolute paths are accepted only
    if they resolve inside it). Raises :class:`PathTraversalError` on escape,
    :class:`FileNotFoundError` if missing, and :class:`ValueError` if the file
    exceeds :data:`MAX_FILE_BYTES`.
    """
    resolved = _safe_path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"no such file in workspace: {path!r}")
    size = resolved.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"file too large ({size} bytes > {MAX_FILE_BYTES})")
    content = resolved.read_text(encoding="utf-8", errors="replace")
    log.info("file_read", chars=len(content))
    return content


def write_file(path: str, content: str) -> bool:
    """Write ``content`` to a file inside the workspace. Returns ``True``.

    Creates parent directories (within the workspace) as needed and overwrites
    any existing file. Raises :class:`PathTraversalError` on escape and
    :class:`ValueError` if the content exceeds :data:`MAX_FILE_BYTES`.
    """
    resolved = _safe_path(path)
    data = content or ""
    encoded = data.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise ValueError(
            f"content too large ({len(encoded)} bytes > {MAX_FILE_BYTES})"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(data, encoding="utf-8")
    log.info("file_write", chars=len(data))
    return True


def list_files(directory: str = ".") -> list[str]:
    """List entries in a workspace directory, relative to the workspace root.

    ``directory`` defaults to the workspace root. Directories are suffixed with
    ``/`` to distinguish them from files. Raises :class:`PathTraversalError` on
    escape and :class:`NotADirectoryError` if the path is not a directory.
    """
    resolved = _safe_path(directory or ".")
    if not resolved.is_dir():
        raise NotADirectoryError(f"not a directory in workspace: {directory!r}")
    entries: list[str] = []
    for child in sorted(resolved.iterdir()):
        rel = child.relative_to(WORKSPACE_DIR).as_posix()
        entries.append(f"{rel}/" if child.is_dir() else rel)
    log.info("file_list", count=len(entries))
    return entries


# --- Claude API tool_use schemas -------------------------------------------

READ_FILE_SCHEMA: dict[str, Any] = {
    "name": "read_file",
    "description": (
        "Read a UTF-8 text file from the Jarvis workspace and return its "
        "contents. Paths are relative to the workspace root; reading outside "
        "the workspace is not permitted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative path of the file to read.",
            }
        },
        "required": ["path"],
    },
}

WRITE_FILE_SCHEMA: dict[str, Any] = {
    "name": "write_file",
    "description": (
        "Write text to a file in the Jarvis workspace, creating or overwriting "
        "it. Paths are relative to the workspace root; writing outside the "
        "workspace is not permitted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative path of the file to write.",
            },
            "content": {
                "type": "string",
                "description": "The full text content to write to the file.",
            },
        },
        "required": ["path", "content"],
    },
}

LIST_FILES_SCHEMA: dict[str, Any] = {
    "name": "list_files",
    "description": (
        "List the files and sub-directories inside a Jarvis workspace directory. "
        "Paths are relative to the workspace root; directories end with '/'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Workspace-relative directory to list. Defaults to root.",
            }
        },
        "required": [],
    },
}


__all__ = [
    "read_file",
    "write_file",
    "list_files",
    "PathTraversalError",
    "WORKSPACE_DIR",
    "MAX_FILE_BYTES",
    "READ_FILE_SCHEMA",
    "WRITE_FILE_SCHEMA",
    "LIST_FILES_SCHEMA",
]
