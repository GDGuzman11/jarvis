"""Speech-to-text via faster-whisper (Phase 3).

This module is the *transcription* stage of the Jarvis voice pipeline. It takes
the raw int16 PCM utterance captured by ``backend.voice.wake_word`` (after the
wake word fires and ``record_until_silence`` returns) and turns it into clean,
sanitised text ready to hand to Claude.

Design notes
------------
* **Model**: ``base.en`` — the English-only base Whisper model. It is small
  enough to run comfortably alongside everything else on a 4 GB-VRAM RTX 3050 Ti
  (and on CPU as a fallback) while giving good accuracy for short command-style
  utterances.

* **Lazy loading**: the model is *not* loaded at import time. Loading Whisper
  pulls a few hundred MB into memory and can take a couple of seconds, so we
  defer it until the first :func:`transcribe` call. This keeps backend startup
  fast and avoids paying the cost at all if voice is never used in a session.

* **Thread executor**: faster-whisper is synchronous and CPU/GPU-bound. Running
  it inline would block the asyncio event loop (stalling the WebSocket hub, the
  agents, everything). So every transcription runs in the default thread-pool
  executor via :func:`asyncio.loop.run_in_executor`.

* **Security (Rule 3)**: the transcript is *untrusted user input* on its way to
  the Claude API. Before returning we strip control characters and cap the
  length at :data:`MAX_TRANSCRIPT_CHARS` (2000) so a malformed or adversarial
  utterance cannot inject control sequences or blow up the prompt.

Audio format expected (matches the capture stage exactly):

* dtype       : ``int16`` (16-bit signed PCM)
* sample rate : 16 kHz (``SAMPLE_RATE``)
* channels    : 1 (mono), as a 1-D ``numpy`` array
"""

from __future__ import annotations

import asyncio
import time
import unicodedata
from threading import Lock
from typing import TYPE_CHECKING

import numpy as np

from backend.logging_config import get_logger

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

log = get_logger(__name__)

# --- Model configuration -----------------------------------------------------

# English-only base model: a good accuracy/size trade-off for short commands on
# a 4 GB-VRAM laptop GPU.
MODEL_SIZE: str = "base.en"

# Device + compute type. "auto" lets faster-whisper pick CUDA when available and
# fall back to CPU otherwise. int8 keeps the memory footprint small on both.
DEVICE: str = "auto"
COMPUTE_TYPE: str = "int8"

# Audio format the transcriber expects — must match the capture stage.
SAMPLE_RATE: int = 16000

# int16 full-scale, used to normalise PCM samples to the float32 [-1, 1] range
# Whisper wants.
_INT16_FULL_SCALE: float = 32768.0

# --- Security (Rule 3) -------------------------------------------------------

# Hard cap on transcript length before it reaches Claude. Per CLAUDE.md security
# rule 3 ("cap at 2000 chars").
MAX_TRANSCRIPT_CHARS: int = 2000


# Module-level singletons guarding the lazily-loaded model. The lock makes the
# first concurrent transcribe() calls cooperate so we only ever build one model.
_model: WhisperModel | None = None
_model_lock: Lock = Lock()


def sanitize_transcript(text: str) -> str:
    """Sanitise a raw transcript before it is sent anywhere (Security Rule 3).

    Two protections, in order:

    1. **Strip control characters** — anything in Unicode category ``C``
       (control/format/surrogate/private-use/unassigned) is removed, except the
       ordinary space. Tabs/newlines a transcript shouldn't contain are dropped
       too; we keep the text on a single clean line.
    2. **Cap length** — truncate to :data:`MAX_TRANSCRIPT_CHARS` so an
       over-long utterance can't bloat the Claude prompt.

    Surrounding whitespace is trimmed last. The result is always a ``str`` (the
    empty string for empty/whitespace-only input).
    """
    if not text:
        return ""

    # Drop any character whose Unicode major category is "C" (Cc, Cf, Cs, Co,
    # Cn) — i.e. control and format chars — while preserving normal printable
    # text. A literal space is allowed through even though it is not category C.
    cleaned = "".join(
        ch for ch in text if ch == " " or not unicodedata.category(ch).startswith("C")
    )

    # Collapse any run of whitespace introduced by removed control chars into a
    # single space, then trim the ends.
    cleaned = " ".join(cleaned.split())

    if len(cleaned) > MAX_TRANSCRIPT_CHARS:
        cleaned = cleaned[:MAX_TRANSCRIPT_CHARS]

    return cleaned


def _load_model() -> WhisperModel:
    """Build (once) and return the shared faster-whisper model.

    Imported and constructed lazily under a lock so the heavyweight import and
    model download/load happen at most once, on first use, and never race.
    """
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        # Double-checked: another thread may have built it while we waited.
        if _model is not None:
            return _model

        # Imported here (not at module top) so importing this module is cheap
        # and side-effect free — important for tests that stub transcription.
        from faster_whisper import WhisperModel

        load_start = time.perf_counter()
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        load_ms = (time.perf_counter() - load_start) * 1000.0
        log.info(
            "stt_model_loaded",
            model=MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
            load_ms=round(load_ms, 1),
        )
        _model = model
        return _model


def _pcm_int16_to_float32(audio: np.ndarray) -> np.ndarray:
    """Convert an int16 PCM array to the float32 [-1, 1] array Whisper expects.

    faster-whisper accepts a float32 numpy array of mono samples normalised to
    [-1, 1]. Our capture stage produces int16, so we rescale. A non-int16 input
    is coerced defensively. Returns a contiguous float32 array.
    """
    samples = np.asarray(audio)
    if samples.dtype != np.int16:
        # Be forgiving if a caller already passed float-ish data; only rescale
        # genuine int16 PCM.
        if np.issubdtype(samples.dtype, np.floating):
            return np.ascontiguousarray(samples, dtype=np.float32)
        samples = samples.astype(np.int16)
    return np.ascontiguousarray(samples.astype(np.float32) / _INT16_FULL_SCALE)


def _transcribe_sync(audio_f32: np.ndarray) -> str:
    """Run faster-whisper synchronously and join the segment texts.

    This is the body that runs *inside the thread executor*. It must not touch
    asyncio. Returns the concatenated, but not yet sanitised, transcript.
    """
    model = _load_model()
    # ``segments`` is a generator — work is done lazily as we iterate it.
    segments, _info = model.transcribe(audio_f32, language="en")
    return "".join(segment.text for segment in segments)


async def transcribe(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    """Transcribe a captured PCM utterance to clean text.

    Parameters
    ----------
    audio:
        The utterance as a 1-D ``numpy`` array of int16 PCM samples (the output
        of ``record_until_silence``). A float32 array in [-1, 1] is also
        accepted.
    sample_rate:
        Sample rate of ``audio``. Defaults to 16 kHz, the pipeline standard. A
        mismatch is logged (Whisper resamples internally, but it signals a
        capture/transcribe format drift worth knowing about).

    Returns
    -------
    str
        The sanitised transcript (control chars stripped, capped at
        :data:`MAX_TRANSCRIPT_CHARS`). Empty string for empty/silent input.

    The synchronous, CPU/GPU-bound Whisper call runs in the default thread
    executor so the event loop is never blocked. Transcription latency is
    logged.
    """
    samples = np.asarray(audio)
    if samples.size == 0:
        log.info("stt_empty_audio")
        return ""

    if sample_rate != SAMPLE_RATE:
        log.warning(
            "stt_sample_rate_mismatch",
            expected=SAMPLE_RATE,
            received=sample_rate,
        )

    audio_f32 = _pcm_int16_to_float32(samples)
    duration_s = samples.shape[0] / float(sample_rate or SAMPLE_RATE)

    loop = asyncio.get_running_loop()
    start = time.perf_counter()
    raw_text = await loop.run_in_executor(None, _transcribe_sync, audio_f32)
    latency_ms = (time.perf_counter() - start) * 1000.0

    text = sanitize_transcript(raw_text)
    log.info(
        "stt_transcribed",
        latency_ms=round(latency_ms, 1),
        audio_seconds=round(duration_s, 2),
        chars=len(text),
    )
    return text


def reset_model() -> None:
    """Drop the cached model so the next call reloads it.

    Mainly useful for tests and for freeing memory if voice is disabled at
    runtime. Safe to call when no model is loaded.
    """
    global _model
    with _model_lock:
        _model = None


__all__ = [
    "MODEL_SIZE",
    "DEVICE",
    "COMPUTE_TYPE",
    "SAMPLE_RATE",
    "MAX_TRANSCRIPT_CHARS",
    "sanitize_transcript",
    "transcribe",
    "reset_model",
]
