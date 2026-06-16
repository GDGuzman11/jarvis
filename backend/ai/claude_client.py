"""Claude API client for Helix — streaming + prompt caching.

Wraps the Anthropic async SDK so the rest of the backend can stream a Helix
response token-by-token without touching SDK internals. Two design rules from
the project spec drive this module:

* **Model** — ``claude-opus-4-7`` (the Helix spec pins 4-7, not the SDK's
  newer default). Override per call only if you have a deliberate reason.
* **Prompt caching** — the system prompt is wrapped in a ``cache_control:
  ephemeral`` block so repeated turns in a conversation re-read the cached
  prefix at ~0.1x cost instead of paying full input price every time. The
  system prompt is the stable prefix; the volatile conversation ``messages``
  come after it, so the cache stays valid across turns (prefix-match rule).

The API key is read lazily from :mod:`backend.security.keystore` (Windows
Credential Manager) — never hardcoded, never from a ``.env`` file (Security
Rule 1).

Streaming + WebSocket fan-out
-----------------------------
:meth:`ClaudeClient.stream_response` is an async generator that yields plain
token strings. As a side effect, each token is also broadcast to every
connected Tauri window as a :class:`~backend.events.Token` event over the
WebSocket hub, and a final ``is_final=True`` token marks completion — this is
what drives the Reasoning window's live token stream. Callers that only want
the text can ignore the broadcast; it happens transparently.

Error handling
--------------
API failures are logged and surfaced as a :class:`ClaudeAPIError` (or, for a
missing credential, the keystore's :class:`MissingCredentialError`) rather than
crashing the voice loop or an agent task. The caller decides whether to fall
back to Ollama (see :mod:`backend.ai.ollama_client`).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

import anthropic

from backend.events import MetricsEvent, Token
from backend.logging_config import get_logger
from backend.security import keystore
from backend.websocket_hub import hub

log = get_logger(__name__)

# Model pinned by the Helix spec. The Anthropic SDK defaults to a newer model;
# the project explicitly wants 4-7, so this constant is the single source of
# truth and must not silently drift to 4-8.
DEFAULT_MODEL: str = "claude-opus-4-7"

# Default output ceiling. Streaming makes large values safe (no HTTP timeout),
# so we give the model room without risking truncation mid-thought.
DEFAULT_MAX_TOKENS: int = 4096

# Claude Opus 4.7 price card, in USD per *million* tokens. Used by
# :func:`_compute_cost` to turn the Anthropic ``usage`` counts into a dollar
# figure for the live cost display (Phase 11C).
PRICE_INPUT_PER_MTOK: float = 15.00
PRICE_OUTPUT_PER_MTOK: float = 75.00
PRICE_CACHE_WRITE_PER_MTOK: float = 3.75
PRICE_CACHE_READ_PER_MTOK: float = 1.50

_TOKENS_PER_MILLION: float = 1_000_000.0


def _compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
) -> float:
    """Return the USD cost of a turn from its token counts.

    Pure function (no I/O, no SDK) so it can be unit-tested without a live API
    key. Applies the Claude Opus 4.7 price card: input/output at full rate,
    cache writes at 0.25x input, cache reads at 0.1x input. The Anthropic
    ``input_tokens`` count already *excludes* cached tokens, so the four buckets
    sum without double-counting.
    """
    return (
        input_tokens * PRICE_INPUT_PER_MTOK
        + output_tokens * PRICE_OUTPUT_PER_MTOK
        + cache_write_tokens * PRICE_CACHE_WRITE_PER_MTOK
        + cache_read_tokens * PRICE_CACHE_READ_PER_MTOK
    ) / _TOKENS_PER_MILLION


class ClaudeAPIError(RuntimeError):
    """Raised when a Claude API call fails after logging.

    Wraps the underlying :class:`anthropic.APIError` so callers can catch a
    single Helix-specific type and decide whether to fall back to Ollama,
    without importing the SDK's exception hierarchy.
    """


def _system_blocks(system_prompt: str) -> list[dict[str, Any]]:
    """Wrap the system prompt in a cache-controlled content block.

    Returns a one-element ``system`` list with an ephemeral ``cache_control``
    marker so the system prompt (the stable prefix) is cached and re-read on
    every subsequent turn. Keeping this as the *only* cached block, ahead of the
    volatile ``messages``, satisfies the prefix-match rule that prompt caching
    depends on.
    """
    return [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]


class ClaudeClient:
    """Async Claude client with streaming, prompt caching, and WS fan-out.

    Parameters
    ----------
    model:
        Model ID. Defaults to :data:`DEFAULT_MODEL` (``claude-opus-4-7``).
    max_tokens:
        Default output cap, overridable per :meth:`stream_response` call.

    Notes
    -----
    The underlying :class:`anthropic.AsyncAnthropic` client is created lazily on
    first use so constructing a ``ClaudeClient`` is cheap and does not touch the
    keyring (important for import-time and test safety). The API key is fetched
    from the keystore when the SDK client is first built.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client: anthropic.AsyncAnthropic | None = None

    # --- Lazy SDK client ----------------------------------------------------

    def _ensure_client(self) -> anthropic.AsyncAnthropic:
        """Return the SDK client, building it (and reading the key) on first use."""
        if self._client is None:
            api_key = keystore.get_anthropic_api_key()  # raises if unset
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            log.info("claude_client_initialised", model=self.model)
        return self._client

    async def aclose(self) -> None:
        """Close the underlying HTTP client. Safe to call if never used."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    # --- Streaming ----------------------------------------------------------

    async def stream_response(
        self,
        messages: Sequence[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream a Claude response token-by-token.

        Parameters
        ----------
        messages:
            The conversation history in Anthropic message format
            (``[{"role": "user", "content": "..."}, ...]``). The volatile part
            of the prompt — placed after the cached system prompt.
        system_prompt:
            The Helix persona / instructions. Wrapped in an ephemeral
            ``cache_control`` block (see :func:`_system_blocks`).
        tools:
            Optional Claude tool definitions (``tool_use`` JSON schemas). Passed
            through untouched when provided.
        max_tokens:
            Per-call override of the instance default.

        Yields
        ------
        str
            Each text token as it streams in.

        Side effects
        ------------
        Broadcasts a :class:`~backend.events.Token` event per token over the
        WebSocket hub, then a final ``is_final=True`` token to mark completion.

        Raises
        ------
        ClaudeAPIError
            If the API call fails. A final ``is_final=True`` token is still
            broadcast so the UI doesn't hang waiting for one.
        backend.security.keystore.MissingCredentialError
            If the Anthropic API key is not set in the keyring.
        """
        client = self._ensure_client()

        # Assemble request kwargs. ``tools`` is only included when supplied so we
        # never send an empty list (which would needlessly change the cache key
        # prefix at position 0).
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": _system_blocks(system_prompt),
            "messages": list(messages),
        }
        if tools:
            request["tools"] = tools

        # Metrics assembled on a clean stream, broadcast after the final token.
        # ``None`` means the turn errored before usage was available, so no
        # MetricsEvent is sent (an error has no meaningful cost/latency).
        metrics: MetricsEvent | None = None
        started = time.perf_counter()

        try:
            async with client.messages.stream(**request) as stream:
                async for text in stream.text_stream:
                    if not text:
                        continue
                    await hub.broadcast(Token(content=text, model=self.model))
                    yield text

            # Read usage once the stream is complete. Cache buckets may be absent
            # on older API responses, so default them to 0.
            final = await stream.get_final_message()
            usage = final.usage
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
            cache_write = (
                getattr(usage, "cache_creation_input_tokens", None) or 0
            )
            latency_ms = int((time.perf_counter() - started) * 1000)

            # Log cache effectiveness so a silent invalidator (zero cache reads)
            # is visible in the logs rather than only on the bill.
            log.info(
                "claude_stream_complete",
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read=cache_read,
                cache_write=cache_write,
                stop_reason=final.stop_reason,
            )

            metrics = MetricsEvent(
                cost_usd=_compute_cost(
                    input_tokens, output_tokens, cache_write, cache_read
                ),
                latency_ms=latency_ms,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
            )
        except anthropic.APIError as exc:
            # Log with the SDK request id (when present) for traceability, then
            # re-raise as a Helix error so the caller can fall back to Ollama.
            log.error(
                "claude_api_error",
                model=self.model,
                error=str(exc),
                request_id=getattr(exc, "request_id", None),
            )
            raise ClaudeAPIError(str(exc)) from exc
        finally:
            # Always emit a closing token so the Reasoning window stops waiting,
            # whether the stream finished cleanly or errored mid-flight.
            await hub.broadcast(
                Token(content="", model=self.model, is_final=True)
            )
            # Then, on a clean turn only, broadcast metrics LAST so the frontend
            # receives cost/latency after the final token.
            if metrics is not None:
                await hub.broadcast(metrics)


__all__ = [
    "ClaudeClient",
    "ClaudeAPIError",
    "DEFAULT_MODEL",
    "DEFAULT_MAX_TOKENS",
    "_compute_cost",
]
