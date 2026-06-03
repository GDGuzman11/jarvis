"""structlog logging configuration for the Jarvis backend (Phase 1).

This module centralises log setup so every part of the backend — the FastAPI
app, the voice pipeline, the agent runtime — emits structured logs through a
single, consistently formatted pipeline.

Two output modes are supported, selected at configuration time:

* **development** (default) — pretty, colourised, human-readable console output
  via ``structlog.dev.ConsoleRenderer``. Easy to scan while building.
* **production** — single-line JSON per event via ``structlog.processors.JSONRenderer``.
  Machine-parseable for shipping to a log aggregator.

The active mode and log level are resolved from the environment so behaviour can
be changed without touching code:

* ``JARVIS_ENV``       — ``development`` (default) or ``production``.
* ``JARVIS_LOG_LEVEL`` — standard level name, e.g. ``DEBUG``/``INFO``/``WARNING``
  (default ``INFO``). Case-insensitive.

Both can also be passed explicitly to :func:`configure_logging`, which always
wins over the environment (handy for tests).

Every emitted event carries, at minimum: an ISO-8601 UTC ``timestamp``, the
``level``, the bound ``logger`` name, and the ``event`` message.

Typical usage::

    from backend.logging_config import configure_logging, get_logger

    configure_logging()                 # once, at process startup
    log = get_logger(__name__)
    log.info("backend_started", port=8000)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

# Environment variable names (kept as constants so callers/tests can reference
# them without hard-coding strings).
ENV_VAR: str = "JARVIS_ENV"
LOG_LEVEL_VAR: str = "JARVIS_LOG_LEVEL"

# Defaults applied when the corresponding environment variable is unset.
DEFAULT_ENV: str = "development"
DEFAULT_LOG_LEVEL: str = "INFO"

# Tracks whether configure_logging() has already run, so repeated calls (e.g. in
# tests or multiple imports) are cheap no-ops unless explicitly forced.
_configured: bool = False


def _resolve_level(level: str | int | None) -> int:
    """Return a numeric ``logging`` level from a name, number, or ``None``.

    Falls back to :data:`DEFAULT_LOG_LEVEL` when the value is missing or
    unrecognised, rather than raising — logging setup should never crash the app.
    """
    if level is None:
        level = os.environ.get(LOG_LEVEL_VAR, DEFAULT_LOG_LEVEL)

    if isinstance(level, int):
        return level

    resolved = logging.getLevelName(str(level).strip().upper())
    # getLevelName returns the string "Level X" for unknown names; guard against it.
    if not isinstance(resolved, int):
        return logging.getLevelName(DEFAULT_LOG_LEVEL)
    return resolved


def _is_production(env: str | None) -> bool:
    """Return True when the resolved environment is production."""
    if env is None:
        env = os.environ.get(ENV_VAR, DEFAULT_ENV)
    return env.strip().lower() == "production"


def configure_logging(
    *,
    env: str | None = None,
    level: str | int | None = None,
    force: bool = False,
) -> None:
    """Configure structlog (and the stdlib root logger) for the whole process.

    Safe to call more than once; subsequent calls are no-ops unless ``force`` is
    set. Call this exactly once during application startup, before any logger is
    used, so that all events share the same pipeline.

    Parameters
    ----------
    env:
        ``"development"`` or ``"production"``. When ``None`` (default) the value
        is read from the ``JARVIS_ENV`` environment variable, defaulting to
        development.
    level:
        Log level as a name (``"DEBUG"``), a numeric ``logging`` constant, or
        ``None`` to read ``JARVIS_LOG_LEVEL`` (defaulting to ``INFO``).
    force:
        Reconfigure even if logging was already configured. Mainly useful in
        tests that switch between modes.
    """
    global _configured
    if _configured and not force:
        return

    numeric_level = _resolve_level(level)
    production = _is_production(env)

    # Shared processors run for every event regardless of output mode. Order
    # matters: context/level/name/timestamp are added before the final renderer.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if production:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Keep the stdlib root logger in step so any library that logs via the
    # standard ``logging`` module honours the same threshold.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=numeric_level,
        force=True,
    )

    _configured = True


def get_logger(name: str | None = None, **initial_values: Any) -> Any:
    """Return a bound structlog logger, configuring logging on first use.

    Parameters
    ----------
    name:
        Logger name, conventionally ``__name__`` of the calling module. Appears
        as the ``logger`` field on every event.
    **initial_values:
        Optional key/value pairs permanently bound to the returned logger, so
        they appear on every event it emits (e.g. ``agent="kado"``).
    """
    if not _configured:
        configure_logging()
    # PrintLoggerFactory's logger has no ``.name`` attribute, so the stdlib
    # ``add_logger_name`` processor cannot populate it. Bind the name directly
    # into the event context instead, so every event carries a ``logger`` field.
    bound = structlog.get_logger(**initial_values)
    if name is not None:
        bound = bound.bind(logger=name)
    return bound


__all__ = [
    "ENV_VAR",
    "LOG_LEVEL_VAR",
    "DEFAULT_ENV",
    "DEFAULT_LOG_LEVEL",
    "configure_logging",
    "get_logger",
]
