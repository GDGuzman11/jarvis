"""DuckDuckGo web search tool for Jarvis.

A read-only, side-effect-free tool that queries DuckDuckGo via the
``duckduckgo-search`` (``ddgs``) library and returns a small list of result
dicts. Used by agents and the voice pipeline to answer "what is…/look up…"
questions without any account, API key, or rate-limit token.

The library call is synchronous and does network I/O, so :func:`web_search` is
``async`` and dispatches the blocking call to a worker thread via
:func:`asyncio.to_thread` — the FastAPI event loop is never blocked.

The Claude API ``tool_use`` schema for this tool is exported as
:data:`WEB_SEARCH_SCHEMA`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from backend.logging_config import get_logger

log = get_logger(__name__)

# Hard ceiling on results regardless of what a caller (or the model) asks for.
# Keeps payloads small and the single DDG query cheap.
MAX_RESULTS_CAP = 10


def _search_sync(query: str, max_results: int) -> list[dict]:
    """Blocking DuckDuckGo text search. Runs inside a worker thread.

    Returns a list of ``{"title", "url", "snippet"}`` dicts. Imports the SDK
    lazily so an unused/optional dependency never breaks module import.
    """
    # The package was renamed ``duckduckgo_search`` -> ``ddgs``; support both so
    # the tool works across installed versions.
    try:
        from ddgs import DDGS  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - depends on installed version
        from duckduckgo_search import DDGS  # type: ignore[import-not-found]

    results: list[dict] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": item.get("title", ""),
                    # ddgs uses "href" for the result URL; older builds use "url".
                    "url": item.get("href") or item.get("url", ""),
                    "snippet": item.get("body", ""),
                }
            )
    return results


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web via DuckDuckGo. Returns a list of result dicts.

    Each item is ``{"title": str, "url": str, "snippet": str}``. Read-only and
    side-effect-free. ``max_results`` is clamped to ``[1, MAX_RESULTS_CAP]``. On
    any failure (network down, library missing) this logs and returns ``[]`` so
    a caller is never crashed by search being unavailable.
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return []
    count = max(1, min(int(max_results), MAX_RESULTS_CAP))

    try:
        results = await asyncio.to_thread(_search_sync, cleaned, count)
    except Exception as exc:  # noqa: BLE001 - never let search crash a caller
        log.error("web_search_failed", error=str(exc))
        return []

    log.info("web_search", results=len(results))
    return results


# --- Claude API tool_use schema --------------------------------------------

WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "name": "web_search",
    "description": (
        "Search the public web via DuckDuckGo and return a ranked list of "
        "results, each with a title, URL, and short snippet. Use this to look "
        "up current facts, documentation, or anything not already known. "
        "Read-only — it never changes anything."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query, e.g. 'FastAPI websocket example'.",
            },
            "max_results": {
                "type": "integer",
                "description": "How many results to return (1-10). Defaults to 5.",
                "minimum": 1,
                "maximum": MAX_RESULTS_CAP,
            },
        },
        "required": ["query"],
    },
}


__all__ = ["web_search", "WEB_SEARCH_SCHEMA", "MAX_RESULTS_CAP"]
