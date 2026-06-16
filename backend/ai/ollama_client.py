"""Ollama client for Helix — local phi3.5 fallback.

When the Claude API is unavailable (network down, rate limited, key missing),
Helix degrades gracefully to a local model served by Ollama. This module wraps
the async Ollama client so the rest of the backend can stream a fallback
response with the same token-by-token shape as
:meth:`backend.ai.claude_client.ClaudeClient.stream_response`.

Design rules
------------
* **Model** — ``phi3.5`` (3.8B, ~2.4GB VRAM — comfortably fits the project's
  4GB RTX 3050 Ti budget). Pinned as the default; overridable per instance.
* **Silent fallback** — if Ollama isn't running (connection refused) the client
  logs a *warning*, not an error, and yields nothing. The caller (the voice
  pipeline or an agent) treats an empty stream as "fallback unavailable" and
  surfaces an appropriate message, rather than the process crashing. The whole
  point of the fallback is resilience, so it must never raise on a cold Ollama.

Streaming
---------
Like the Claude client, :meth:`OllamaClient.stream_response` is an async
generator that yields plain token strings, and broadcasts each token as a
:class:`~backend.events.Token` event over the WebSocket hub (with a final
``is_final=True`` marker) so the Reasoning window updates identically whether
the active model is Claude or the local fallback.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import ollama

from backend.events import Token
from backend.logging_config import get_logger
from backend.websocket_hub import hub

log = get_logger(__name__)

# Local fallback model. Sized to fit the project's 4GB VRAM budget.
DEFAULT_MODEL: str = "phi3.5"

# Connection errors that mean "Ollama isn't running / reachable". On any of
# these we fall back silently (warn + yield nothing) rather than propagate.
_CONNECTION_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    ollama.ResponseError,
)


class OllamaClient:
    """Async Ollama client with streaming and silent-on-cold-start fallback.

    Parameters
    ----------
    model:
        Ollama model tag. Defaults to :data:`DEFAULT_MODEL` (``phi3.5``).

    Notes
    -----
    The underlying :class:`ollama.AsyncClient` is created lazily so constructing
    the wrapper is cheap and does not attempt any connection until the first
    :meth:`stream_response` call.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model
        self._client: ollama.AsyncClient | None = None

    def _ensure_client(self) -> ollama.AsyncClient:
        """Return the async Ollama client, building it on first use."""
        if self._client is None:
            self._client = ollama.AsyncClient()
        return self._client

    async def stream_response(
        self,
        messages: Sequence[dict[str, Any]],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """Stream a local phi3.5 response token-by-token.

        Parameters
        ----------
        messages:
            Conversation history in chat format
            (``[{"role": "user", "content": "..."}, ...]``). Combined with the
            system prompt into Ollama's ``chat`` message list.
        system_prompt:
            The Helix persona / instructions, prepended as a ``system`` message.

        Yields
        ------
        str
            Each text token as it streams in. Yields nothing if Ollama is not
            running (see module docstring — this is the silent-fallback path).

        Side effects
        ------------
        Broadcasts a :class:`~backend.events.Token` event per token over the
        WebSocket hub, then a final ``is_final=True`` token to mark completion
        (the closing token is emitted even when the fallback is unavailable, so
        the UI never hangs).
        """
        client = self._ensure_client()

        # Ollama takes the system prompt as the first message in the list.
        chat_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        try:
            stream = await client.chat(
                model=self.model,
                messages=chat_messages,
                stream=True,
            )
            async for chunk in stream:
                text = chunk.get("message", {}).get("content", "")
                if not text:
                    continue
                await hub.broadcast(Token(content=text, model=self.model))
                yield text
            log.info("ollama_stream_complete", model=self.model)
        except _CONNECTION_ERRORS as exc:
            # Ollama isn't running or the model isn't pulled. This is the
            # designed degraded path — warn and yield nothing, never raise.
            log.warning(
                "ollama_unavailable",
                model=self.model,
                error=str(exc),
            )
        finally:
            await hub.broadcast(
                Token(content="", model=self.model, is_final=True)
            )


    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        system_prompt: str,
        *,
        fmt: str | None = None,
    ) -> str:
        """Return a full local phi3.5 response as plain text (non-streaming).

        The fallback counterpart to
        :meth:`backend.ai.claude_client.ClaudeClient.complete`. Used by the Phase
        16C memory extractor when the Claude call is unavailable or its output
        could not be parsed. Broadcasts nothing to the WebSocket hub.

        Parameters
        ----------
        messages:
            Conversation/messages list in chat format.
        system_prompt:
            Prepended as the leading ``system`` message.
        fmt:
            Optional Ollama ``format`` hint (pass ``"json"`` to push phi3.5
            toward strict JSON output for extraction).

        Returns
        -------
        str
            The model's reply text, or ``""`` when Ollama is not running/reachable
            (the same silent-degradation contract as :meth:`stream_response` — a
            cold fallback never raises).
        """
        client = self._ensure_client()
        chat_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]
        try:
            response = await client.chat(
                model=self.model,
                messages=chat_messages,
                stream=False,
                format=fmt,
            )
            content = response.get("message", {}).get("content", "")
            log.info("ollama_complete_done", model=self.model)
            return content or ""
        except _CONNECTION_ERRORS as exc:
            log.warning("ollama_unavailable", model=self.model, error=str(exc))
            return ""


__all__ = [
    "OllamaClient",
    "DEFAULT_MODEL",
]
