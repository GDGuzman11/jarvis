"""Continuous audio capture + Porcupine wake-word detection + VAD (Phase 3).

This module owns the *front* of the Jarvis voice pipeline — the part that runs
forever in the background, listening for the user to say "Jarvis", and then
capturing the utterance that follows until they stop speaking.

It is built from three cooperating pieces, all living here because they share
one audio stream and one frame format:

1. :class:`AudioCaptureLoop`
   A continuous, non-blocking microphone capture loop built on
   ``sounddevice``. sounddevice delivers audio on its *own* PortAudio thread,
   so the loop bridges that thread onto the asyncio event loop via an
   :class:`asyncio.Queue`. Consumers ``await`` :meth:`AudioCaptureLoop.frames`
   to receive 16-bit PCM frames of exactly :data:`FRAME_LENGTH` samples — the
   block size Porcupine requires.

2. :class:`WakeWordDetector`
   Wraps ``pvporcupine`` with the built-in ``"jarvis"`` keyword. It consumes
   frames from the capture loop, feeds each to Porcupine, and invokes a
   registered async callback when the wake word fires. If the Porcupine access
   key is missing from the keyring it logs a warning and disables itself rather
   than crashing the backend — Jarvis can still run (text path, agents) without
   the wake word.

3. :func:`record_until_silence` + :class:`SilenceDetector`
   Voice-activity detection. After the wake word fires the pipeline switches to
   "listening" mode and buffers frames until the speaker goes quiet — RMS
   amplitude below :data:`SILENCE_RMS_THRESHOLD` for
   :data:`SILENCE_DURATION_S` consecutive seconds — at which point the buffered
   speech is returned as a single ``numpy`` array for the STT stage.

Audio format (fixed across the whole pipeline, matching Porcupine + Whisper):

* Sample rate : :data:`SAMPLE_RATE` (16 kHz)
* Channels    : 1 (mono)
* Sample dtype: ``int16`` (16-bit signed PCM)
* Frame size  : :data:`FRAME_LENGTH` (512 samples ≈ 32 ms per frame)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import numpy as np

from backend.logging_config import get_logger
from backend.security import keystore

log = get_logger(__name__)

# --- Audio format constants --------------------------------------------------

# Porcupine (and faster-whisper's base.en) both operate at 16 kHz mono.
SAMPLE_RATE: int = 16000

# Mono capture — Porcupine expects a single channel.
CHANNELS: int = 1

# Samples per frame. Porcupine's ``frame_length`` is fixed at 512 for the
# default models; we capture in exactly that block size so every captured frame
# can be passed straight to ``Porcupine.process`` with no buffering/repacking.
FRAME_LENGTH: int = 512

# Built-in Porcupine keyword. "jarvis" ships with pvporcupine, so no custom
# ``.ppn`` keyword file (or its access-key-bound download) is required.
KEYWORD: str = "jarvis"

# --- Voice-activity-detection constants --------------------------------------

# Frames whose RMS amplitude falls below this are considered "silence". int16
# samples range over [-32768, 32767]; ~500 is a low-but-non-zero floor that
# clears typical mic self-noise without clipping quiet speech. Tunable.
SILENCE_RMS_THRESHOLD: float = 500.0

# How long the speaker must stay below the threshold before we call the
# utterance finished. 0.8 s per the Phase 3 spec.
SILENCE_DURATION_S: float = 0.8

# Safety cap so a noisy room (never crossing into "silence") can't make us
# record forever. After this many seconds we stop regardless.
MAX_UTTERANCE_S: float = 15.0

# Bound the queue between the PortAudio thread and the event loop. At ~32 ms per
# frame, 100 frames ≈ 3.2 s of buffered audio — plenty of slack without letting
# a stalled consumer grow memory without limit.
_QUEUE_MAXSIZE: int = 100

# Type alias for the async callback fired on wake-word detection.
WakeCallback = Callable[[], Awaitable[None]]


def frame_rms(frame: np.ndarray) -> float:
    """Return the root-mean-square amplitude of an int16 PCM frame.

    Computed in float64 to avoid int16 overflow when squaring. An empty frame
    returns ``0.0`` (treated as silence) rather than producing a NaN.
    """
    if frame.size == 0:
        return 0.0
    samples = frame.astype(np.float64)
    return float(np.sqrt(np.mean(samples * samples)))


class AudioCaptureLoop:
    """Continuous, non-blocking microphone capture on top of ``sounddevice``.

    sounddevice runs its callback on a separate PortAudio thread. That callback
    must never block or touch asyncio objects directly, so it hands each frame
    to the event loop via :meth:`asyncio.loop.call_soon_threadsafe`, which
    enqueues it on an :class:`asyncio.Queue`. Consumers then ``await`` frames
    from the queue on the event loop as normal.

    Lifecycle::

        capture = AudioCaptureLoop()
        await capture.start()
        async for frame in capture.frames():
            ...                      # frame is an int16 ndarray, FRAME_LENGTH long
        await capture.stop()

    :meth:`start` and :meth:`stop` are idempotent.
    """

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        frame_length: int = FRAME_LENGTH,
        channels: int = CHANNELS,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_length = frame_length
        self.channels = channels
        self.device = device

        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stream: object | None = None  # sounddevice.RawInputStream
        self._running: bool = False
        self._dropped: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def _on_audio(self, indata: bytes, frames: int, time_info: object, status: object) -> None:
        """PortAudio callback — runs on sounddevice's thread, NOT the event loop.

        Keep this fast and allocation-light. We copy the raw bytes into an int16
        ndarray and schedule the enqueue on the event loop. We must not call
        ``queue.put`` directly here (the queue is not thread-safe and we're off
        the loop), hence ``call_soon_threadsafe``.
        """
        if status:
            # Over/underflows etc. Log but keep going — a dropped frame is
            # preferable to tearing down capture mid-conversation.
            log.warning("audio_capture_status", status=str(status))

        # ``indata`` is a raw bytes buffer (RawInputStream). Decode to int16.
        frame = np.frombuffer(indata, dtype=np.int16).copy()

        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._enqueue, frame)

    def _enqueue(self, frame: np.ndarray) -> None:
        """Put a frame on the queue from the event loop thread; drop if full.

        Runs via ``call_soon_threadsafe`` so it is on the loop and may touch the
        queue safely. If the consumer has fallen behind and the queue is full we
        drop the *oldest* frame to stay real-time rather than blocking capture.
        """
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            # Drop oldest to make room — staying current matters more than
            # completeness for a live wake-word stream.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(frame)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass
            self._dropped += 1
            if self._dropped % 50 == 1:
                log.warning("audio_frames_dropped", dropped=self._dropped)

    async def start(self) -> None:
        """Open the microphone stream and begin capturing. Idempotent."""
        if self._running:
            return

        # Imported lazily so importing this module (e.g. in unit tests that
        # stub the stream) doesn't require a working PortAudio / audio device.
        import sounddevice as sd

        self._loop = asyncio.get_running_loop()
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.frame_length,
            channels=self.channels,
            dtype="int16",
            device=self.device,
            callback=self._on_audio,
        )
        self._stream.start()
        self._running = True
        log.info(
            "audio_capture_started",
            sample_rate=self.sample_rate,
            frame_length=self.frame_length,
            channels=self.channels,
        )

    async def stop(self) -> None:
        """Stop and close the microphone stream. Idempotent."""
        if not self._running:
            return
        self._running = False

        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001 — best-effort teardown
                log.warning("audio_capture_stop_error", exc_info=True)

        # Drain any frames still queued so a restart begins clean.
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        log.info("audio_capture_stopped", dropped_total=self._dropped)

    async def get_frame(self) -> np.ndarray:
        """Await and return the next captured frame (int16, ``frame_length`` long)."""
        return await self._queue.get()

    async def frames(self) -> AsyncIterator[np.ndarray]:
        """Yield captured frames until :meth:`stop` is called.

        Stops cleanly once capture is no longer running and the queue drains.
        """
        while self._running or not self._queue.empty():
            try:
                # Time out periodically so a stopped loop doesn't block forever
                # waiting on an empty queue.
                frame = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                if not self._running:
                    return
                continue
            yield frame


class SilenceDetector:
    """Tracks consecutive silence to decide when an utterance has ended.

    Feed it frames in order via :meth:`update`; it returns ``True`` once the
    accumulated trailing silence reaches the configured duration. Speech resets
    the counter, so brief pauses mid-sentence don't end the capture early.
    """

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        rms_threshold: float = SILENCE_RMS_THRESHOLD,
        silence_duration_s: float = SILENCE_DURATION_S,
    ) -> None:
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold
        self.silence_duration_s = silence_duration_s
        self._silent_seconds: float = 0.0
        self._heard_speech: bool = False

    @property
    def heard_speech(self) -> bool:
        """Whether any above-threshold (speech) frame has been seen yet."""
        return self._heard_speech

    def update(self, frame: np.ndarray) -> bool:
        """Account for one frame; return ``True`` if the utterance has ended.

        Silence only counts toward ending the utterance *after* we've heard at
        least one speech frame — otherwise a slow speaker (a beat of quiet right
        after the wake word) would be cut off before they begin.
        """
        frame_seconds = len(frame) / self.sample_rate
        is_silent = frame_rms(frame) < self.rms_threshold

        if is_silent:
            if self._heard_speech:
                self._silent_seconds += frame_seconds
        else:
            self._heard_speech = True
            self._silent_seconds = 0.0

        return self._heard_speech and self._silent_seconds >= self.silence_duration_s

    def reset(self) -> None:
        """Clear state to reuse the detector for a fresh utterance."""
        self._silent_seconds = 0.0
        self._heard_speech = False


async def record_until_silence(
    capture: AudioCaptureLoop,
    *,
    rms_threshold: float = SILENCE_RMS_THRESHOLD,
    silence_duration_s: float = SILENCE_DURATION_S,
    max_seconds: float = MAX_UTTERANCE_S,
) -> np.ndarray:
    """Buffer frames from ``capture`` until the speaker falls silent.

    Called after the wake word fires (pipeline in "listening" state). Returns
    the captured utterance as a single 1-D int16 ``numpy`` array, ready to hand
    to the STT stage. An empty array is returned if nothing was captured.

    Stops on the first of:
      * :data:`silence_duration_s` of consecutive trailing silence after speech, or
      * :data:`max_seconds` elapsed (safety cap for noisy rooms).
    """
    detector = SilenceDetector(
        sample_rate=capture.sample_rate,
        rms_threshold=rms_threshold,
        silence_duration_s=silence_duration_s,
    )
    buffered: list[np.ndarray] = []
    captured_seconds = 0.0

    async for frame in capture.frames():
        buffered.append(frame)
        captured_seconds += len(frame) / capture.sample_rate

        if detector.update(frame):
            log.info("utterance_ended", reason="silence", seconds=round(captured_seconds, 2))
            break
        if captured_seconds >= max_seconds:
            log.info("utterance_ended", reason="max_length", seconds=round(captured_seconds, 2))
            break

    if not buffered:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(buffered)


class WakeWordDetector:
    """Porcupine "Jarvis" wake-word detector over a continuous audio stream.

    Owns (or shares) an :class:`AudioCaptureLoop`, runs every captured frame
    through Porcupine, and fires a registered async callback when the keyword is
    detected. Designed to run as a long-lived asyncio background task started in
    the FastAPI lifespan.

    Resilience: if the Porcupine access key is absent from the keyring, the
    detector logs a warning and stays disabled — :meth:`start` becomes a no-op —
    so a missing key degrades the wake word gracefully instead of crashing the
    whole backend.

    Usage::

        detector = WakeWordDetector()
        detector.on_detected(handle_wake)   # async callable
        await detector.start()              # runs until stop()
        ...
        await detector.stop()
    """

    def __init__(
        self,
        *,
        capture: AudioCaptureLoop | None = None,
        keyword: str = KEYWORD,
    ) -> None:
        self.keyword = keyword
        self._owns_capture = capture is None
        self._capture = capture or AudioCaptureLoop()
        self._porcupine: object | None = None  # pvporcupine.Porcupine
        self._callback: WakeCallback | None = None
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._enabled: bool = True

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_enabled(self) -> bool:
        """False once a missing access key has disabled the detector."""
        return self._enabled

    def on_detected(self, callback: WakeCallback) -> None:
        """Register the async callback fired on each wake-word detection."""
        self._callback = callback

    def _init_porcupine(self) -> bool:
        """Create the Porcupine handle. Returns False (disabled) if no key.

        A missing access key is an expected, recoverable condition (the user
        simply hasn't configured Porcupine yet), so we warn and disable rather
        than propagate. Any *other* construction error is unexpected and is
        re-raised.
        """
        try:
            access_key = keystore.get_porcupine_access_key()
        except keystore.MissingCredentialError:
            log.warning(
                "wake_word_disabled_no_key",
                reason="PORCUPINE_ACCESS_KEY not set in keyring",
                hint="store it via keystore.set_porcupine_access_key(...)",
            )
            self._enabled = False
            return False

        import pvporcupine

        self._porcupine = pvporcupine.create(
            access_key=access_key,
            keywords=[self.keyword],
        )
        # Sanity-check the audio format matches what Porcupine expects so frames
        # line up exactly with ``process``.
        expected_len = self._porcupine.frame_length
        expected_rate = self._porcupine.sample_rate
        if expected_len != self._capture.frame_length:
            log.warning(
                "wake_word_frame_length_mismatch",
                porcupine=expected_len,
                capture=self._capture.frame_length,
            )
        if expected_rate != self._capture.sample_rate:
            log.warning(
                "wake_word_sample_rate_mismatch",
                porcupine=expected_rate,
                capture=self._capture.sample_rate,
            )
        return True

    async def start(self) -> None:
        """Start capture + detection as a background task. Idempotent.

        No-op (with a warning already logged) when the access key is missing.
        """
        if self._running:
            return

        if not self._init_porcupine():
            # Disabled: leave the backend running without a wake word.
            return

        if self._owns_capture:
            await self._capture.start()

        self._running = True
        self._task = asyncio.create_task(self._run(), name="wake-word-detector")
        log.info("wake_word_started", keyword=self.keyword)

    async def _run(self) -> None:
        """Main loop: feed each captured frame to Porcupine, fire on detection."""
        porcupine = self._porcupine
        assert porcupine is not None  # guaranteed by start() gating on _init
        try:
            async for frame in self._capture.frames():
                if not self._running:
                    break
                # Porcupine wants a list/sequence of ``frame_length`` int16s.
                result = porcupine.process(frame)
                if result >= 0:
                    log.info("wake_word_detected", keyword=self.keyword)
                    await self._fire()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — never let detection crash the backend
            log.error("wake_word_loop_error", exc_info=True)

    async def _fire(self) -> None:
        """Invoke the registered callback, isolating its errors from the loop."""
        if self._callback is None:
            log.warning("wake_word_no_callback")
            return
        try:
            await self._callback()
        except Exception:  # noqa: BLE001 — a bad handler must not kill detection
            log.error("wake_word_callback_error", exc_info=True)

    async def stop(self) -> None:
        """Stop detection, cancel the task, and release resources. Idempotent."""
        if not self._running and self._task is None and self._porcupine is None:
            return
        self._running = False

        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._owns_capture:
            await self._capture.stop()

        porcupine = self._porcupine
        self._porcupine = None
        if porcupine is not None:
            try:
                porcupine.delete()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                log.warning("wake_word_porcupine_delete_error", exc_info=True)

        log.info("wake_word_stopped")


__all__ = [
    "SAMPLE_RATE",
    "CHANNELS",
    "FRAME_LENGTH",
    "KEYWORD",
    "SILENCE_RMS_THRESHOLD",
    "SILENCE_DURATION_S",
    "MAX_UTTERANCE_S",
    "WakeCallback",
    "frame_rms",
    "AudioCaptureLoop",
    "SilenceDetector",
    "record_until_silence",
    "WakeWordDetector",
]
