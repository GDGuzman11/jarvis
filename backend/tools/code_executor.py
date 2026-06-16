"""Sandboxed Python code executor for Helix (Security Rule 4).

Runs short, untrusted Python snippets inside a heavily restricted environment so
agents can do quick calculations and data shaping *without* the snippet being
able to touch the host. Built on `RestrictedPython
<https://restrictedpython.readthedocs.io/>`_, which compiles source to bytecode
that routes attribute/item access and name lookups through guard hooks, then
executes it with a tightly curated set of builtins.

What is blocked
---------------
* ``import`` of anything (no ``os``, ``sys``, ``subprocess``, ``socket``,
  ``shutil`` …). The custom ``__import__`` always raises.
* ``open`` / file I/O — not in the provided builtins.
* ``eval`` / ``exec`` / ``compile`` — not provided.
* Dunder/attribute escapes (``().__class__.__bases__`` … ) — RestrictedPython's
  ``safe_getattr`` blocks ``_``-prefixed attribute access.
* Long-running / infinite loops — execution runs in a worker thread guarded by a
  wall-clock timeout (:data:`TIMEOUT_SECONDS`).

What is allowed
---------------
A safe subset of builtins (``len``, ``range``, ``min``, ``max``, ``sum``,
``sorted``, ``abs``, ``round``, basic types, ``print`` …) plus ``math``. ``print``
output is captured and returned as ``stdout``.

The result is always a dict: ``{"stdout": str, "stderr": str, "success": bool}``.
The async wrapper :func:`execute_code` keeps the event loop responsive by running
the (blocking, timeout-guarded) execution in a thread.

The Claude API ``tool_use`` schema is exported as :data:`EXECUTE_CODE_SCHEMA`.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import math
from typing import Any

from backend.logging_config import get_logger

log = get_logger(__name__)

# Wall-clock ceiling for a single execution. A snippet that runs longer is
# abandoned and reported as a failure (caller is never blocked indefinitely).
TIMEOUT_SECONDS = 10.0


def _blocked_import(*_args: Any, **_kwargs: Any) -> Any:
    """Replacement ``__import__`` that refuses every import (Security Rule 4)."""
    raise ImportError("imports are disabled in the sandbox")


def _build_safe_globals() -> dict[str, Any]:
    """Construct the restricted global namespace for an execution.

    Combines RestrictedPython's vetted ``safe_globals`` (safe builtins + the
    guard hooks the compiled bytecode calls) with a blocked ``__import__`` and a
    couple of harmless, commonly-useful modules. No ``os``/``sys``/``open``.
    """
    from RestrictedPython import safe_builtins
    from RestrictedPython.Eval import default_guarded_getiter
    from RestrictedPython.Guards import (
        guarded_iter_unpack_sequence,
        safe_globals,
    )

    builtins = dict(safe_builtins)
    # Explicitly neuter import even though safe_builtins omits it — defence in
    # depth in case a future RestrictedPython adds it back.
    builtins["__import__"] = _blocked_import

    sandbox: dict[str, Any] = dict(safe_globals)
    sandbox["__builtins__"] = builtins
    # Guard hooks the compiled code references for safe iteration / unpacking.
    sandbox["_getiter_"] = default_guarded_getiter
    sandbox["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
    # math is pure-computation and safe to expose for calculations.
    sandbox["math"] = math
    return sandbox


def _run_restricted(code: str) -> dict[str, Any]:
    """Compile and execute ``code`` under RestrictedPython. Blocking.

    Returns ``{"stdout", "stderr", "success"}``. Compilation errors and runtime
    exceptions are captured into ``stderr`` with ``success=False`` rather than
    propagated.
    """
    from RestrictedPython import compile_restricted
    from RestrictedPython.PrintCollector import PrintCollector

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        bytecode = compile_restricted(code, filename="<helix-sandbox>", mode="exec")
    except SyntaxError as exc:
        return {"stdout": "", "stderr": f"SyntaxError: {exc}", "success": False}

    sandbox = _build_safe_globals()
    # RestrictedPython routes `print(...)` through a `_print_` collector placed in
    # the execution namespace; we read its accumulated text afterward.
    sandbox["_print_"] = PrintCollector
    local_ns: dict[str, Any] = {}

    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(
            stderr_buf
        ):
            exec(bytecode, sandbox, local_ns)  # noqa: S102 - sandboxed bytecode only
    except Exception as exc:  # noqa: BLE001 - report any sandbox error as stderr
        return {
            "stdout": stdout_buf.getvalue(),
            "stderr": f"{type(exc).__name__}: {exc}",
            "success": False,
        }

    # PrintCollector accumulates printed text into a `_print` variable in the
    # local namespace; fall back to the redirected buffer if unused.
    printed = local_ns.get("_print")
    captured = printed() if callable(printed) else stdout_buf.getvalue()
    return {"stdout": captured, "stderr": stderr_buf.getvalue(), "success": True}


async def execute_code(code: str) -> dict[str, Any]:
    """Execute a Python snippet in the sandbox. Returns a result dict.

    Result: ``{"stdout": str, "stderr": str, "success": bool}``. Runs the
    blocking, restricted execution in a worker thread with a
    :data:`TIMEOUT_SECONDS` wall-clock timeout; a timeout yields
    ``success=False`` and an explanatory ``stderr``. Never raises to the caller.
    """
    source = code or ""
    if not source.strip():
        return {"stdout": "", "stderr": "no code provided", "success": False}

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_restricted, source), timeout=TIMEOUT_SECONDS
        )
    except TimeoutError:
        log.warning("code_executor_timeout", timeout=TIMEOUT_SECONDS)
        return {
            "stdout": "",
            "stderr": f"execution timed out after {TIMEOUT_SECONDS:.0f}s",
            "success": False,
        }
    except Exception as exc:  # noqa: BLE001 - defensive: never crash a caller
        log.error("code_executor_failed", error=str(exc))
        return {"stdout": "", "stderr": f"executor error: {exc}", "success": False}

    log.info("code_executor_run", success=result["success"])
    return result


# --- Claude API tool_use schema --------------------------------------------

EXECUTE_CODE_SCHEMA: dict[str, Any] = {
    "name": "execute_code",
    "description": (
        "Run a short Python snippet in a secure sandbox and return its captured "
        "stdout, stderr, and a success flag. Use this for calculations and quick "
        "data shaping. The sandbox blocks imports, file access, and the network, "
        "so only pure-Python computation (plus the 'math' module) is available."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "The Python source to execute. Use print() to produce output."
                ),
            }
        },
        "required": ["code"],
    },
}


__all__ = ["execute_code", "EXECUTE_CODE_SCHEMA", "TIMEOUT_SECONDS"]
