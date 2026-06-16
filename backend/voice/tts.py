"""Text-to-speech via ElevenLabs (Phase 3).

The *speaking* end of the Helix voice pipeline. It turns Claude's response text
into spoken audio in the custom "Tom Hardy x Avengers Jarvis" voice configured
in the ElevenLabs dashboard, and plays it back on the local speakers.

Two public coroutines:

* :func:`speak` — text -> MP3 audio ``bytes``. The MP3 is convenient for the
  return value: it is what gets handed back to callers (e.g. to ship over the
  WebSocket to the UI, or cache to disk). Returns empty ``bytes`` (never raises)
  when the ElevenLabs credentials are missing, so a misconfigured key degrades
  gracefully instead of crashing the voice loop.

* :func:`play_audio` — play audio ``bytes`` on the local default output device.

Why two render paths
---------------------
ElevenLabs can return several formats. We deliberately use:

* **MP3** for :func:`speak`'s return value — compact, portable, easy to stash.
* **raw 16 kHz PCM** for :func:`play_text` / :func:`speak_and_play` playback —
  ``sounddevice`` (already a project dependency) can play PCM directly with no
  external decoder. Decoding MP3 in-process would require ffmpeg/mpv, which we
  do not want to depend on.

:func:`play_audio` accepts already-rendered MP3 ``bytes`` and plays them via the
ElevenLabs helper (which shells out to a system player). For the common
"say this now" case prefer :func:`speak_and_play`, which renders PCM and plays it
through ``sounddevice`` with no external tooling.

Credentials (Security Rule 1) come from the keyring via
``backend.security.keystore`` — never from files or env values:

* API key  : ``keystore.get_elevenlabs_api_key()``
* Voice ID : ``keystore.get_elevenlabs_voice_id()``
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import numpy as np

from backend.events import AudioLevelEvent
from backend.logging_config import get_logger
from backend.security import keystore
from backend.websocket_hub import hub

if TYPE_CHECKING:
    from elevenlabs.client import ElevenLabs

log = get_logger(__name__)

# How often we sample the playback amplitude and broadcast an AudioLevelEvent.
# 50 ms gives the Animation window a smooth, responsive pulse without flooding
# the WebSocket hub.
AUDIO_LEVEL_INTERVAL_S: float = 0.05

# Full-scale value for signed 16-bit PCM, used to normalise the RMS amplitude
# into the 0.0-1.0 range the AudioLevelEvent contract specifies.
_INT16_FULL_SCALE: float = 32768.0

# --- Output format / model configuration -------------------------------------

# MP3 returned by speak(): 44.1 kHz / 128 kbps is ElevenLabs' standard quality.
MP3_OUTPUT_FORMAT: str = "mp3_44100_128"

# Raw PCM used for local playback through sounddevice. 16 kHz mono int16 — no
# external decoder required. The string is ElevenLabs' format id; the matching
# numeric rate is PCM_SAMPLE_RATE below.
PCM_OUTPUT_FORMAT: str = "pcm_16000"
PCM_SAMPLE_RATE: int = 16000

# ElevenLabs TTS model. ``eleven_turbo_v2_5`` is low-latency and well suited to
# an interactive assistant; quality is high for conversational speech.
MODEL_ID: str = "eleven_turbo_v2_5"


def _make_client() -> ElevenLabs | None:
    """Build an ElevenLabs client from the keyring, or ``None`` if unconfigured.

    A missing API key is an expected, recoverable state (the user simply hasn't
    set it up yet): we log a warning and return ``None`` so callers can degrade
    gracefully rather than crash the voice loop.
    """
    try:
        api_key = keystore.get_elevenlabs_api_key()
    except keystore.MissingCredentialError:
        log.warning(
            "tts_disabled_no_key",
            reason="ELEVENLABS_API_KEY not set in keyring",
            hint="store it via keystore.set_elevenlabs_api_key(...)",
        )
        return None

    # Imported lazily so importing this module is cheap and does not require the
    # elevenlabs package to be importable in environments that never speak.
    from elevenlabs.client import ElevenLabs

    return ElevenLabs(api_key=api_key)


def _resolve_voice_id() -> str | None:
    """Return the configured voice id, or ``None`` (with a warning) if unset."""
    try:
        return keystore.get_elevenlabs_voice_id()
    except keystore.MissingCredentialError:
        log.warning(
            "tts_disabled_no_voice_id",
            reason="ELEVENLABS_VOICE_ID not set in keyring",
            hint="create a voice in the ElevenLabs dashboard and store its id "
            "via keystore.set_elevenlabs_voice_id(...)",
        )
        return None


def _convert_sync(text: str, output_format: str) -> bytes:
    """Synchronously call ElevenLabs and return the full audio as bytes.

    Runs inside the thread executor (the SDK call is blocking network I/O).
    ``convert`` yields an iterator of byte chunks; we join them. Returns empty
    bytes when credentials are missing.
    """
    client = _make_client()
    if client is None:
        return b""
    voice_id = _resolve_voice_id()
    if voice_id is None:
        return b""

    chunks = client.text_to_speech.convert(
        voice_id,
        text=text,
        model_id=MODEL_ID,
        output_format=output_format,
    )
    return b"".join(chunks)


async def _convert(text: str, output_format: str) -> bytes:
    """Async wrapper around :func:`_convert_sync` with latency logging.

    The blocking SDK call runs in the default thread executor so the event loop
    stays responsive. Returns empty bytes (never raises for an expected
    misconfiguration) when credentials are absent.
    """
    clean = (text or "").strip()
    if not clean:
        log.info("tts_empty_text")
        return b""

    loop = asyncio.get_running_loop()
    start = time.perf_counter()
    try:
        audio = await loop.run_in_executor(None, _convert_sync, clean, output_format)
    except Exception:  # noqa: BLE001 — TTS failure must not kill the voice loop
        log.error("tts_convert_error", exc_info=True, output_format=output_format)
        return b""

    latency_ms = (time.perf_counter() - start) * 1000.0
    if audio:
        log.info(
            "tts_synthesized",
            latency_ms=round(latency_ms, 1),
            bytes=len(audio),
            output_format=output_format,
            chars=len(clean),
        )
    return audio


async def speak(text: str) -> bytes:
    """Synthesize ``text`` to MP3 audio bytes in the Helix voice.

    Returns the full MP3 as ``bytes``. Returns empty ``bytes`` (and logs a
    warning) when the ElevenLabs API key or voice id is missing — callers should
    treat empty bytes as "TTS unavailable" and skip playback rather than error.
    """
    return await _convert(text, MP3_OUTPUT_FORMAT)


def _decode_pcm16(audio_bytes: bytes) -> np.ndarray:
    """Interpret raw little-endian 16-bit mono PCM bytes as an int16 array."""
    return np.frombuffer(audio_bytes, dtype="<i2")


def _play_pcm_sync(pcm_bytes: bytes, sample_rate: int) -> None:
    """Play raw int16 PCM through sounddevice and block until finished.

    Runs inside the thread executor. ``sounddevice`` is imported lazily so this
    module imports cleanly in environments with no audio device (e.g. tests).
    """
    import sounddevice as sd

    samples = _decode_pcm16(pcm_bytes)
    if samples.size == 0:
        return
    sd.play(samples, samplerate=sample_rate)
    sd.wait()


def _rms_level(samples: np.ndarray) -> float:
    """Return the RMS amplitude of an int16 sample block, normalised to 0.0-1.0.

    The root-mean-square is computed in float space (to avoid int16 overflow),
    divided by full scale, and clipped at ``1.0`` so a hot buffer never reports
    above the contract's ceiling. An empty block is silence (``0.0``).
    """
    if samples.size == 0:
        return 0.0
    # Square in float64 so the intermediate sum can't overflow int16.
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    return min(rms / _INT16_FULL_SCALE, 1.0)


def _play_pcm_block_sync(samples: np.ndarray, sample_rate: int) -> None:
    """Play one already-decoded int16 PCM block and block until it finishes.

    Used by the chunked playback path in :func:`speak_and_play` so amplitude can
    be sampled and broadcast between blocks on the event loop. ``sounddevice`` is
    imported lazily so this module stays importable without an audio device.
    """
    if samples.size == 0:
        return
    import sounddevice as sd

    sd.play(samples, samplerate=sample_rate)
    sd.wait()


async def play_audio(audio_bytes: bytes) -> None:
    """Play already-rendered audio ``bytes`` on the default output device.

    Accepts the MP3 bytes returned by :func:`speak`. MP3 playback is delegated
    to the ElevenLabs ``play`` helper, which uses an available system player
    (ffmpeg/mpv). If no such player is installed it logs a warning and returns
    rather than raising — playback failure must never crash the voice loop.

    For the common "synthesize then immediately speak" case prefer
    :func:`speak_and_play`, which renders raw PCM and plays it through
    ``sounddevice`` with no external decoder.

    Empty input is a no-op (e.g. when TTS was unavailable).
    """
    if not audio_bytes:
        log.info("tts_play_empty")
        return

    loop = asyncio.get_running_loop()

    def _play() -> None:
        from elevenlabs import play

        play(audio_bytes)

    try:
        await loop.run_in_executor(None, _play)
    except Exception:  # noqa: BLE001 — no system player / device: degrade, don't crash
        log.warning(
            "tts_play_mp3_failed",
            hint="install ffmpeg or mpv for MP3 playback, or use speak_and_play "
            "(PCM via sounddevice)",
            exc_info=True,
        )


async def speak_and_play(text: str) -> bytes:
    """Synthesize ``text`` as PCM, play it locally, and return the PCM bytes.

    This is the low-latency local playback path: it renders raw 16 kHz mono PCM
    (no external decoder needed) and plays it straight through ``sounddevice``.
    Use this from the voice loop for "say this now". Returns the PCM bytes (empty
    when TTS is unavailable).

    While the audio plays, the buffer is sliced into ~50 ms blocks (see
    :data:`AUDIO_LEVEL_INTERVAL_S`); each block is played in the thread executor
    and its RMS amplitude is broadcast as an :class:`~backend.events.AudioLevelEvent`
    on the event loop so the Animation window's orb pulses in time with Helix's
    voice. A final ``level=0.0`` event is always broadcast when playback ends so
    the orb settles back to rest, even if playback failed midway.
    """
    pcm = await _convert(text, PCM_OUTPUT_FORMAT)
    if not pcm:
        return b""

    samples = _decode_pcm16(pcm)
    if samples.size == 0:
        return pcm

    loop = asyncio.get_running_loop()
    block_size = max(1, int(PCM_SAMPLE_RATE * AUDIO_LEVEL_INTERVAL_S))

    try:
        # Play the full audio as one stream in the executor so Windows doesn't
        # gap between micro-blocks. Amplitude events are broadcast in parallel
        # on the event loop, sleeping AUDIO_LEVEL_INTERVAL_S between each so
        # the orb pulses in sync without interrupting playback.
        play_future = loop.run_in_executor(None, _play_pcm_block_sync, samples, PCM_SAMPLE_RATE)
        for start in range(0, samples.size, block_size):
            block = samples[start : start + block_size]
            await hub.broadcast(AudioLevelEvent(level=_rms_level(block)))
            await asyncio.sleep(AUDIO_LEVEL_INTERVAL_S)
        await play_future
    except Exception:  # noqa: BLE001 — playback failure must not kill the loop
        log.warning("tts_play_pcm_failed", exc_info=True)
    finally:
        # Always settle the orb back to rest, whether playback finished or threw.
        await hub.broadcast(AudioLevelEvent(level=0.0))
    return pcm


def is_configured() -> bool:
    """Return True when both the ElevenLabs API key and voice id are present.

    A cheap pre-flight check (touches only the keyring, makes no API call) the
    voice pipeline can use to decide whether to attempt speech at all.
    """
    return keystore.has_credential(keystore.ELEVENLABS_API_KEY) and keystore.has_credential(
        keystore.ELEVENLABS_VOICE_ID
    )


__all__ = [
    "MP3_OUTPUT_FORMAT",
    "PCM_OUTPUT_FORMAT",
    "PCM_SAMPLE_RATE",
    "MODEL_ID",
    "AUDIO_LEVEL_INTERVAL_S",
    "speak",
    "play_audio",
    "speak_and_play",
    "is_configured",
]
