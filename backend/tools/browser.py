"""Playwright browser-automation tool for Jarvis.

Fetches a URL with a real (headless Chromium) browser so JavaScript-rendered
pages resolve, then returns the page's visible text with ``<script>`` and
``<style>`` content stripped. Optionally captures a PNG screenshot.

Why Playwright (not plain HTTP): many pages render their content client-side, so
a raw ``GET`` returns an empty shell. A headless browser executes the page and
lets us read what a human would actually see.

Event-loop safety
-----------------
Playwright ships both sync and async APIs. We use the **async** API directly so
the fetch is a first-class coroutine on the FastAPI event loop — no thread
needed, and cancellation/timeouts work naturally. Each call launches and tears
down its own browser so there is no shared global state to leak between calls.

The Claude API ``tool_use`` schema is exported as :data:`BROWSE_URL_SCHEMA`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.logging_config import get_logger

log = get_logger(__name__)

# Per-call navigation timeout (ms). A page that takes longer is abandoned and
# the tool returns "" rather than hanging an agent or the voice turn.
NAV_TIMEOUT_MS = 20_000

# Only http(s) URLs are allowed. This blocks file://, javascript:, data: and
# other schemes that could read local files or execute inline payloads.
_ALLOWED_SCHEMES = ("http://", "https://")

# Collapse runs of whitespace/newlines the DOM text extraction leaves behind.
_WS_RUN = re.compile(r"[ \t ]+")
_BLANK_LINES = re.compile(r"\n\s*\n\s*\n+")


def _is_allowed_url(url: str) -> bool:
    """Return True only for absolute http(s) URLs (Security: no file:/data:)."""
    return url.lower().startswith(_ALLOWED_SCHEMES)


def _clean_text(text: str) -> str:
    """Normalise extracted page text: trim, collapse whitespace and blank runs."""
    text = _WS_RUN.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


async def browse_url(
    url: str,
    *,
    screenshot_path: str | None = None,
    max_chars: int = 8000,
) -> str:
    """Render ``url`` in headless Chromium and return its visible text.

    ``<script>`` and ``<style>`` nodes are removed before extraction so the
    result is human-readable content only. When ``screenshot_path`` is given a
    full-page PNG is written there as a side effect. The returned text is capped
    at ``max_chars`` characters.

    Only ``http``/``https`` URLs are permitted; anything else returns ``""``. On
    any failure (timeout, navigation error, Playwright not installed) this logs
    and returns ``""`` — it never raises to the caller.
    """
    target = (url or "").strip()
    if not _is_allowed_url(target):
        log.warning("browser_url_rejected", url=target[:80])
        return ""

    try:
        # Imported lazily so an environment without browsers installed does not
        # break module import for the rest of the backend.
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on install
        log.error("browser_unavailable", error=str(exc))
        return ""

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(
                    target, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded"
                )

                if screenshot_path:
                    shot = Path(screenshot_path)
                    shot.parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(shot), full_page=True)

                # Strip scripts/styles in-page, then read the body's inner text
                # (which the browser already renders without markup).
                await page.evaluate(
                    "() => { document.querySelectorAll('script,style,noscript')"
                    ".forEach(el => el.remove()); }"
                )
                raw = await page.inner_text("body")
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001 - never let a fetch crash a caller
        log.error("browser_fetch_failed", url=target[:80], error=str(exc))
        return ""

    text = _clean_text(raw)[:max_chars]
    log.info("browser_fetch", url=target[:80], chars=len(text))
    return text


# --- Claude API tool_use schema --------------------------------------------

BROWSE_URL_SCHEMA: dict[str, Any] = {
    "name": "browse_url",
    "description": (
        "Open a web page in a headless browser (JavaScript runs) and return its "
        "visible text content with scripts and styling removed. Use this to read "
        "an article, documentation page, or any URL whose content you need. Only "
        "http and https URLs are allowed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The absolute http(s) URL to open and read.",
            }
        },
        "required": ["url"],
    },
}


__all__ = ["browse_url", "BROWSE_URL_SCHEMA", "NAV_TIMEOUT_MS"]
