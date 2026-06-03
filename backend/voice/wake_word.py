"""Continuous audio capture + OpenWakeWord wake-word detection + VAD (Phase 3).

This module owns the *front* of the Jarvis voice pipeline — the part that runs
forever in the background, listening for the user to say "hey Jarvis", and then
capturing the utterance that follows until they stop speaking.

It is built from three cooperating pieces, all living here because they share
one audio stream and one frame format:

1. :class:`AudioCaptureLoop`
   A continuous, non-blocking microphone capture loop built on
   ``sounddevice``. sounddevice delivers audio on its *own* PortAudio thread,
   so the loop bridges that thread onto the asyncio event loop via an
   :class:`asyncio.Queue`. Consumers ``await`` :meth:`AudioCaptureLoop.frames`
   to receive 16-bit PCM frames of exactly :data:`FRAME_LENGTH` samples.

2. :class:`WakeWordDetector`
   Wraps ``openwakeword`` with the built-in ``"hey_jarvis"`` model. It consumes
   frames from the capture loop, feeds each to the model, and invokes a
   registered async callback when the detection score exceeds the threshold.
   No API key is required — the library is fully open-source (Apache 2.0) and
   runs entirely locally. If the library is not installed it logs a warning and
   disables itself rather than crashing the backend.

3. :func:`record_until_silence` + :class:`SilenceDetector`
   Voice-activity detection. After the wake word fires the pipeline switches to
   "listening" mode and buffers frames until the speaker goes quiet — RMS
   amplitude below :data:`SILENCE_RMS_THRESHOLD` for
   :data:`SILENCE_DURATION_S` consecutive seconds — at which point the buffered
   speech is returned as a single ``numpy`` array for the STT stage.

Audio format (fixed across the whole pipeline, matching OpenWakeWord + Whisper):

* Sample rate : :data:`SAMPLE_RATE` (16 kHz)
* Channels    : 1 (mono)
* Sample dtype: ``int16`` (16-bit signed PCM)
* Frame size  : :data:`FRAME_LENGTH` (1280 samples = 80 ms per frame)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import numpy as np

from backend.logging_config import get_logger

log = get_logger(__name__)

# --- Audio format constants --------------------------------------------------

# OpenWakeWord (and faster-whisper's base.en) both operate at 16 kHz mono.
SAMPLE_RATE: int = 16000

# Mono capture.
CHANNELS: int = 1

# Samples per frame. 1280 samples = 80 ms at 16 kHz — OpenWakeWord's optimal
# chunk size; each call to model.predict() advances its mel-spectrogram buffer
# by exactly 8 steps (10 ms each), giving fine-grained, low-latency detection.
FRAME_LENGTH: int = 1280

# Built-in OpenWakeWord model name. "hey_jarvis" ships with the library and is
# downloaded automatically on first use — no API key or custom file required.
KEYWORD: str = "hey_jarvis"

# Detection score threshold. Scores range [0, 1]; 0.5 is the recommended
# default for the "hey_jarvis" model. Raise to reduce false positives.
WAKE_THRESHOLD: float = 0.5

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
    """OpenWakeWord "hey Jarvis" detector over a continuous audio stream.

    Owns (or shares) an :class:`AudioCaptureLoop`, runs every captured frame
    through the ``openwakeword`` model, and fires a registered async callback
    when the detection score crosses :data:`WAKE_THRESHOLD`. Designed to run as
    a long-lived asyncio background task started in the FastAPI lifespan.

    No API key is required — OpenWakeWord is fully open-source (Apache 2.0) and
    runs entirely locally. If the library is not installed it logs a warning and
    stays disabled rather than crashing the backend.

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
        threshold: float = WAKE_THRESHOLD,
    ) -> None:
        self.keyword = keyword
        self.threshold = threshold
        self._owns_capture = capture is None
        self._capture = capture or AudioCaptureLoop()
        self._model: object | None = None  # openwakeword.model.Model
        self._callback: WakeCallback | None = None
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False
        self._enabled: bool = True

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_enabled(self) -> bool:
        """False if the openwakeword library failed to load at start time."""
        return self._enabled

    def on_detected(self, callback: WakeCallback) -> None:
        """Register the async callback fired on each wake-word detection."""
        self._callback = callback

    def _init_model(self) -> bool:
        """Load the OpenWakeWord model. Returns False (disabled) on ImportError.

        The library downloads its pretrained models automatically on first use
        (from a GitHub release asset). Any subsequent load is instant from the
        local cache. ImportError means the package is not installed and is the
        only expected failure mode; all other errors are re-raised.
        """
        try:
            import openwakeword
            import openwakeword.utils
            from openwakeword.model import Model
        except ImportError:
            log.warning(
                "wake_word_disabled_no_openwakeword",
                reason="openwakeword library not installed",
                hint="pip install openwakeword",
            )
            self._enabled = False
            return False

        openwakeword.utils.download_models()
        self._model = Model(
            wakeword_models=[self.keyword],
            inference_framework="onnx",
        )
        return True

    async def start(self) -> None:
        """Start capture + detection as a background task. Idempotent.

        No-op (with a warning already logged) when openwakeword is not installed.
        """
        if self._running:
            return

        if not self._init_model():
            return

        if self._owns_capture:
            await self._capture.start()

        self._running = True
        self._task = asyncio.create_task(self._run(), name="wake-word-detector")
        log.info("wake_word_started", keyword=self.keyword, threshold=self.threshold)

    async def _run(self) -> None:
        """Main loop: score each captured frame, fire on threshold crossing."""
        model = self._model
        assert model is not None  # guaranteed by start() gating on _init_model
        try:
            async for frame in self._capture.frames():
                if not self._running:
                    break
                prediction: dict[str, float] = model.predict(frame)
                score = prediction.get(self.keyword, 0.0)
                if score >= self.threshold:
                    log.info("wake_word_detected", keyword=self.keyword, score=round(score, 3))
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
        if not self._running and self._task is None and self._model is None:
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

        self._model = None
        log.info("wake_word_stopped")


__all__ = [
    "SAMPLE_RATE",
    "CHANNELS",
    "FRAME_LENGTH",
    "KEYWORD",
    "WAKE_THRESHOLD",
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
