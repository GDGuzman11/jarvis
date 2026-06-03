"""End-to-end voice pipeline orchestration (Phase 3).

This module ties together the individual voice stages built earlier in Phase 3
into one continuous, long-lived loop — the thing that actually *is* "talking to
Jarvis":

    wake word -> listen -> transcribe -> reason (Claude) -> speak -> idle

The front of the pipeline (continuous capture, OpenWakeWord detection,
and silence-bounded recording) lives in :mod:`backend.voice.wake_word`; the
transcription and synthesis stages live in :mod:`backend.voice.stt` and
:mod:`backend.voice.tts`. :class:`VoicePipeline` is the conductor: it owns a
:class:`~backend.voice.wake_word.WakeWordDetector`, registers a wake callback,
and on each detection drives one full turn through the stages above, broadcasting
a :class:`~backend.events.VoiceStateEvent` at every transition so the Animation
window's orb tracks the conversation in real time.

State machine
-------------
The pipeline emits exactly these states over the WebSocket hub (Task 3):

* ``idle``      — at rest, waiting for the wake word (orb blue).
* ``listening`` — wake word fired; capturing the user's utterance (orb cyan).
* ``thinking``  — utterance captured; transcribing + streaming from Claude (gold).
* ``speaking``  — synthesising and playing Jarvis's reply (cyan).

Every turn ends back at ``idle`` — whether it completed, was interrupted, found
nothing to transcribe, or errored — so the orb never gets stuck mid-state.

Streaming + low latency
-----------------------
Claude tokens are streamed and accumulated into *speakable chunks* (a sentence
or a comfortable buffer) which are sent to TTS the moment a boundary is reached,
rather than waiting for the entire reply. This overlaps synthesis/playback of the
first sentence with generation of the rest, cutting time-to-first-audio — the
metric that makes the assistant feel responsive (Phase 3 latency target <3 s).

Interrupt ("stop") — Task 2
---------------------------
While Jarvis is thinking or speaking, a secondary listener keeps capturing from
the *same* audio stream. If it transcribes the word "stop" (a plain keyword match
on a short STT window), it cancels the in-flight response coroutine, halts
playback, and returns the pipeline to ``idle``. This lets the user cut Jarvis off
mid-sentence the way you would a person.

Resilience
----------
If the openwakeword library is not installed the detector disables itself
gracefully, so :meth:`VoicePipeline.start` is always safe to call — the backend
runs fine without voice. Errors inside a turn are logged and always unwind back
to ``idle`` rather than crashing the loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import numpy as np

from backend.ai.claude_client import ClaudeAPIError, ClaudeClient
from backend.ai.ollama_client import OllamaClient
from backend.ai.persona import build_system_prompt
from backend.security.keystore import MissingCredentialError
from backend.events import VoiceState, VoiceStateEvent
from backend.logging_config import get_logger
from backend.voice import stt, tts
from backend.voice.wake_word import (
    AudioCaptureLoop,
    WakeWordDetector,
    record_until_silence,
)
from backend.websocket_hub import ConnectionHub
from backend.websocket_hub import hub as default_hub

log = get_logger(__name__)

# --- Interrupt configuration -------------------------------------------------

# The single keyword that cancels an in-flight response. A plain substring match
# on the interrupt window's transcript keeps this cheap and predictable.
INTERRUPT_KEYWORD: str = "stop"

# How long each interrupt-listening window records before we transcribe it and
# check for the keyword. Short so a "stop" is acted on quickly, but long enough
# to catch the whole word. We re-arm the window repeatedly while Jarvis is busy.
INTERRUPT_WINDOW_S: float = 1.2

# --- Crash-recovery configuration (Phase 10) ---------------------------------

# How many *consecutive* turn crashes we tolerate before giving up. After this
# many back-to-back unhandled errors the pipeline parks in the ``error`` state
# and stops re-arming the wake word, so a hard fault (e.g. a missing audio
# device) doesn't spin forever. A single clean turn resets the counter.
MAX_TURN_RETRIES: int = 3

# How long to pause after a crash before re-arming the wake word, so a fast-
# failing fault (e.g. the audio device is gone) doesn't busy-loop.
CRASH_RECOVERY_DELAY_S: float = 2.0

# --- Token-buffering (speakable-chunk) configuration -------------------------

# Sentence-ending punctuation. When a streamed buffer ends on one of these (and
# is past the soft minimum) we flush it to TTS — speaking sentence-by-sentence so
# audio starts while later sentences are still being generated.
_SENTENCE_ENDINGS: frozenset[str] = frozenset(".!?")

# Don't flush absurdly short fragments (e.g. "Mr.") — wait until the buffer has
# at least this many characters before treating punctuation as a boundary.
MIN_CHUNK_CHARS: int = 40

# Hard ceiling: flush regardless of punctuation once the buffer reaches this many
# characters, so a long unpunctuated run still starts speaking promptly.
MAX_CHUNK_CHARS: int = 240


def _split_speakable_chunks(buffer: str) -> tuple[list[str], str]:
    """Split an accumulated token buffer into ready-to-speak chunks.

    Returns ``(chunks, remainder)`` where ``chunks`` are complete fragments ready
    to hand to TTS and ``remainder`` is the trailing text not yet at a boundary
    (carried forward to the next call). A chunk boundary is either:

    * sentence-ending punctuation once the buffer is at least
      :data:`MIN_CHUNK_CHARS` long, or
    * the :data:`MAX_CHUNK_CHARS` hard cap (split on the last space before the cap
      so we don't slice a word in half).
    """
    chunks: list[str] = []
    remainder = buffer

    while True:
        # Hard cap first: if we're over the ceiling, flush up to a word boundary.
        if len(remainder) >= MAX_CHUNK_CHARS:
            cut = remainder.rfind(" ", 0, MAX_CHUNK_CHARS)
            if cut <= 0:
                cut = MAX_CHUNK_CHARS
            head, remainder = remainder[:cut], remainder[cut:].lstrip()
            if head.strip():
                chunks.append(head.strip())
            continue

        # Otherwise look for a sentence boundary past the soft minimum.
        boundary = -1
        for i, ch in enumerate(remainder):
            if ch in _SENTENCE_ENDINGS and i + 1 >= MIN_CHUNK_CHARS:
                boundary = i
                break
        if boundary == -1:
            break
        head, remainder = remainder[: boundary + 1], remainder[boundary + 1 :].lstrip()
        if head.strip():
            chunks.append(head.strip())

    return chunks, remainder


class VoicePipeline:
    """Drives the full wake -> listen -> reason -> speak voice loop.

    One pipeline owns one :class:`~backend.voice.wake_word.WakeWordDetector` and
    one :class:`~backend.ai.claude_client.ClaudeClient`, and serialises turns: a
    new wake-word detection while a turn is already in flight is ignored (a guard
    flag), so two turns never overlap.

    Parameters
    ----------
    hub:
        The WebSocket :class:`~backend.websocket_hub.ConnectionHub` to broadcast
        ``voice_state`` events on. Defaults to the process-wide singleton.
    claude:
        The Claude client used to generate replies. Defaults to a fresh
        :class:`ClaudeClient` (lazy — touches no credentials until first use).
    ollama:
        The local fallback client used when the Claude API is unavailable
        (raises :class:`ClaudeAPIError`). Defaults to a fresh
        :class:`OllamaClient` (lazy — connects nothing until first use).
    detector:
        The wake-word detector. Defaults to a fresh one owning its own capture
        loop. Injecting one lets tests drive detection without a microphone.

    Lifecycle::

        pipeline = VoicePipeline()
        await pipeline.start()   # arms the wake word; returns immediately
        ...
        await pipeline.stop()    # cancels any in-flight turn and tears down
    """

    def __init__(
        self,
        *,
        hub: ConnectionHub | None = None,
        claude: ClaudeClient | None = None,
        ollama: OllamaClient | None = None,
        detector: WakeWordDetector | None = None,
    ) -> None:
        self._hub = hub or default_hub
        self._claude = claude or ClaudeClient()
        self._ollama = ollama or OllamaClient()
        self._detector = detector or WakeWordDetector()

        # The capture loop is shared between the wake-word detector and the
        # interrupt listener so they read one microphone stream, not two.
        self._capture: AudioCaptureLoop = self._detector._capture

        self._state: VoiceState = "idle"
        self._running: bool = False

        # The task running the current turn (handle_wake). Held so stop() and the
        # interrupt listener can cancel it. ``None`` between turns.
        self._turn_task: asyncio.Task[None] | None = None

        # Set while a turn is being processed, so a second wake-word detection
        # mid-turn is ignored rather than starting an overlapping turn.
        self._busy: bool = False

        # Number of *consecutive* turns that have crashed with an unhandled
        # error. Reset to 0 on any clean turn completion. Once it reaches
        # MAX_TURN_RETRIES the pipeline parks in ``error`` and stops retrying.
        self._consecutive_crashes: int = 0

        self._detector.on_detected(self._on_wake)

    # --- Public lifecycle ---------------------------------------------------

    @property
    def state(self) -> VoiceState:
        """The pipeline's current voice state."""
        return self._state

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Arm the wake word and begin listening. Idempotent.

        Returns immediately; the loop runs in the detector's background task.
        If openwakeword is not installed the detector disables itself quietly,
        so this is always safe to call.
        """
        if self._running:
            return
        self._running = True
        await self._set_state("idle")
        await self._detector.start()
        if self._detector.is_enabled:
            log.info("voice_pipeline_started")
        else:
            log.warning("voice_pipeline_started_wake_word_disabled")

    async def stop(self) -> None:
        """Stop the pipeline, cancelling any in-flight turn. Idempotent."""
        if not self._running:
            return
        self._running = False

        await self._cancel_turn()
        await self._detector.stop()
        await self._set_state("idle")
        log.info("voice_pipeline_stopped")

    # --- Wake handling ------------------------------------------------------

    async def _on_wake(self) -> None:
        """Wake-word callback: launch one turn unless one is already running.

        Runs the turn in its own task so this callback (invoked from the
        detector's loop) returns promptly and the cancellable handle is stored
        for the interrupt listener and :meth:`stop`.
        """
        if self._busy:
            log.info("wake_ignored_turn_in_progress")
            return
        self._busy = True
        self._turn_task = asyncio.create_task(self._run_turn(), name="voice-turn")

        def _clear(_: asyncio.Task[None]) -> None:
            self._busy = False
            self._turn_task = None

        self._turn_task.add_done_callback(_clear)

    async def _run_turn(self) -> None:
        """Process exactly one wake -> listen -> reason -> speak turn.

        Always unwinds to ``idle`` — on completion, on an empty transcript, on
        interrupt cancellation, or on error — so the orb never sticks.

        Crash recovery (Phase 10): an unhandled error inside the turn does not
        kill the loop. It is logged, the consecutive-crash counter ticks up, and
        after :data:`CRASH_RECOVERY_DELAY_S` the wake word is re-armed. A clean
        turn resets the counter. After :data:`MAX_TURN_RETRIES` back-to-back
        crashes the pipeline parks in the ``error`` state and stops retrying
        (logging a critical), so a hard fault can't spin forever.
        """
        crashed = False
        try:
            # 1. LISTEN — capture the user's utterance until they fall silent.
            await self._set_state("listening")
            audio = await record_until_silence(self._capture)

            # 2. THINK — transcribe, then stream a reply from Claude.
            await self._set_state("thinking")
            transcript = await stt.transcribe(audio)
            if not transcript:
                log.info("voice_turn_empty_transcript")
                return
            log.info("voice_turn_transcript", chars=len(transcript))

            # Run the reason+speak stage under an interrupt watcher: whichever
            # finishes first wins. If "stop" is heard, the watcher cancels the
            # responder; if the responder finishes, the watcher is cancelled.
            await self._respond_with_interrupt(transcript)
        except asyncio.CancelledError:
            # stop() or an interrupt cancelled this turn — expected, not an error.
            log.info("voice_turn_cancelled")
            raise
        except Exception:  # noqa: BLE001 — a bad turn must not kill the loop
            crashed = True
            log.error("voice_turn_error", exc_info=True)
        finally:
            if crashed:
                # A crash path handles its own state (error vs idle) via recovery.
                await self._handle_turn_crash()
            else:
                # Clean turn (completed, empty, or interrupted): reset the crash
                # streak and return to rest. (Skipped if stop() cancelled us —
                # that path raised CancelledError above and never reaches here.)
                self._consecutive_crashes = 0
                if self._running:
                    await self._set_state("idle")

    async def _handle_turn_crash(self) -> None:
        """Recover from an unhandled turn error by re-arming, up to a limit.

        Increments the consecutive-crash counter. If we are at or over
        :data:`MAX_TURN_RETRIES`, parks the pipeline in the ``error`` state and
        stops retrying (the detector keeps running but the orb shows the fault).
        Otherwise it waits :data:`CRASH_RECOVERY_DELAY_S`, re-arms the wake-word
        detector if it has fallen over, and returns the pipeline to ``idle`` so
        the next wake word starts a fresh turn.
        """
        self._consecutive_crashes += 1

        if self._consecutive_crashes >= MAX_TURN_RETRIES:
            log.critical(
                "voice_pipeline_giving_up",
                consecutive_crashes=self._consecutive_crashes,
                max_retries=MAX_TURN_RETRIES,
            )
            if self._running:
                await self._set_state("error")
            return

        log.warning(
            "voice_turn_recovering",
            consecutive_crashes=self._consecutive_crashes,
            max_retries=MAX_TURN_RETRIES,
            delay_s=CRASH_RECOVERY_DELAY_S,
        )
        try:
            await asyncio.sleep(CRASH_RECOVERY_DELAY_S)
        except asyncio.CancelledError:
            # stop() cut the recovery wait short — abandon recovery quietly.
            raise

        if not self._running:
            return

        # Re-arm the wake word in case the fault tore the detector down. start()
        # is idempotent, so this is a safe no-op when it's still listening.
        try:
            await self._detector.start()
        except Exception:  # noqa: BLE001 — re-arm failure shouldn't crash recovery
            log.error("voice_pipeline_rearm_failed", exc_info=True)

        await self._set_state("idle")

    # --- Reason + speak, with interrupt -------------------------------------

    async def _respond_with_interrupt(self, transcript: str) -> None:
        """Stream Claude's reply to TTS while watching for a spoken "stop".

        Spawns two tasks against the same audio stream — the responder and the
        interrupt listener — and lets the first to finish settle the turn:

        * responder finishes first  -> cancel the listener, turn done.
        * listener hears "stop" first -> cancel the responder, turn interrupted.
        """
        responder = asyncio.create_task(
            self._stream_and_speak(transcript), name="voice-responder"
        )
        interrupt = asyncio.create_task(
            self._listen_for_interrupt(), name="voice-interrupt"
        )

        done, pending = await asyncio.wait(
            {responder, interrupt}, return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel whichever task is still pending and await it so no task leaks.
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass

        if interrupt in done and not interrupt.cancelled() and interrupt.result():
            # The listener won by hearing "stop" — the responder was just
            # cancelled above. Surface the interruption.
            log.info("voice_response_interrupted", keyword=INTERRUPT_KEYWORD)
            return

        # Otherwise the responder finished naturally; re-raise any error it hit so
        # _run_turn's handler logs it.
        if responder in done and not responder.cancelled():
            exc = responder.exception()
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                raise exc

    async def _stream_and_speak(self, transcript: str) -> None:
        """Stream a Claude reply, speaking it sentence-by-sentence as it arrives.

        Tokens are buffered into speakable chunks (see
        :func:`_split_speakable_chunks`); each completed chunk is synthesised and
        played before generation finishes, so audio starts early. Transitions to
        ``speaking`` on the first chunk that is actually spoken.
        """
        messages = [{"role": "user", "content": transcript}]
        system_prompt = build_system_prompt()

        buffer = ""
        spoke_anything = False

        async for token in self._iter_reply(messages, system_prompt):
            buffer += token
            chunks, buffer = _split_speakable_chunks(buffer)
            for chunk in chunks:
                if not spoke_anything:
                    await self._set_state("speaking")
                    spoke_anything = True
                await self._speak_chunk(chunk)

        # Flush whatever's left after the stream ends (a final partial sentence).
        tail = buffer.strip()
        if tail:
            if not spoke_anything:
                await self._set_state("speaking")
                spoke_anything = True
            await self._speak_chunk(tail)

    async def _iter_reply(
        self, messages: list[dict[str, object]], system_prompt: str
    ) -> AsyncIterator[str]:
        """Yield reply tokens from Claude, falling back to Ollama on API error.

        Tokens are also broadcast to the Reasoning window by the AI client
        itself; here we only need the text to feed TTS. The turn degrades
        gracefully to the local Ollama model — silently, with no user-facing
        error — when Claude is unavailable for either reason:

        * :class:`ClaudeAPIError` — the API call failed (network down, rate
          limited, server error), or
        * :class:`MissingCredentialError` — the Anthropic API key is not set in
          the keyring, so the SDK client can't even be built. Jarvis simply
          speaks using Ollama instead (graceful degradation — CLAUDE.md Phase 10
          / Phase 9 fallback test).

        Ollama itself never raises on a cold start; if it too is unavailable it
        simply yields nothing.

        To preserve prefix caching and avoid re-emitting tokens, the fallback is
        only attempted when Claude fails *before yielding any token*. A mid-stream
        failure (some tokens already spoken) is logged and ends the turn, since
        restarting from Ollama would duplicate the already-spoken prefix.
        """
        produced_any = False
        try:
            async for token in self._claude.stream_response(messages, system_prompt):
                produced_any = True
                yield token
            return
        except (ClaudeAPIError, MissingCredentialError):
            log.error("voice_claude_error", exc_info=True)
            if produced_any:
                # Some audio already spoke; don't restart from a different model.
                return
            log.warning("claude_fallback_to_ollama")

        # Claude failed before producing anything — fall back to the local model.
        try:
            async for token in self._ollama.stream_response(messages, system_prompt):
                yield token
        except Exception:  # noqa: BLE001 — fallback must never crash the loop
            log.error("voice_ollama_error", exc_info=True)

    async def _speak_chunk(self, text: str) -> None:
        """Synthesise and play one chunk, swallowing TTS failures.

        TTS already degrades to empty audio when unconfigured and never raises
        for that case; this extra guard catches anything unexpected so a single
        bad chunk can't abort the whole reply.
        """
        try:
            await tts.speak_and_play(text)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — one bad chunk must not end the reply
            log.warning("voice_speak_chunk_error", exc_info=True)

    # --- Interrupt listener -------------------------------------------------

    async def _listen_for_interrupt(self) -> bool:
        """Listen for the spoken interrupt keyword while a reply is in flight.

        Records short windows from the shared capture stream, transcribes each,
        and returns ``True`` the moment the :data:`INTERRUPT_KEYWORD` is heard.
        Runs until cancelled (the reply finished) or it detects "stop".

        Each window is capped at :data:`INTERRUPT_WINDOW_S` so detection latency
        stays low and the loop re-arms quickly.
        """
        while True:
            try:
                audio = await self._record_interrupt_window()
            except asyncio.CancelledError:
                raise
            if audio.size == 0:
                continue
            try:
                heard = await stt.transcribe(audio)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — a flaky window must not stop watching
                log.warning("voice_interrupt_stt_error", exc_info=True)
                continue
            if heard and INTERRUPT_KEYWORD in heard.lower():
                return True

    async def _record_interrupt_window(self) -> np.ndarray:
        """Capture a short fixed-length window of audio for interrupt detection.

        Unlike :func:`record_until_silence` (which waits for the user to stop),
        this grabs a bounded slice so the keyword check happens on a predictable
        cadence even while Jarvis's own playback may be ongoing.
        """
        frames: list[np.ndarray] = []
        captured_s = 0.0
        async for frame in self._capture.frames():
            frames.append(frame)
            captured_s += len(frame) / self._capture.sample_rate
            if captured_s >= INTERRUPT_WINDOW_S:
                break
        if not frames:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(frames)

    # --- State broadcasting (Task 3) ----------------------------------------

    async def _set_state(self, state: VoiceState) -> None:
        """Update the current state and broadcast it over the WebSocket hub.

        Every transition flows through here, so a single ``voice_state`` event is
        emitted for each change and the Animation window's orb stays in sync. A
        no-op transition (same state) is still broadcast — cheap, and it lets a
        late-joining client resync.
        """
        self._state = state
        await self._hub.broadcast(VoiceStateEvent(state=state))
        log.info("voice_state", state=state)

    # --- Internal helpers ---------------------------------------------------

    async def _cancel_turn(self) -> None:
        """Cancel the in-flight turn task (if any) and await its unwind."""
        task = self._turn_task
        self._turn_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._busy = False


__all__ = [
    "VoicePipeline",
    "INTERRUPT_KEYWORD",
    "INTERRUPT_WINDOW_S",
    "MAX_TURN_RETRIES",
    "CRASH_RECOVERY_DELAY_S",
    "MIN_CHUNK_CHARS",
    "MAX_CHUNK_CHARS",
    "_split_speakable_chunks",
]
