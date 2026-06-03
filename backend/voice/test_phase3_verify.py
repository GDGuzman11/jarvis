"""Phase 3 tasks 1-3 verification: audio capture + OpenWakeWord wake word + VAD.

Run with: .venv\\Scripts\\python.exe -m pytest backend/voice/test_phase3_verify.py -v
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.voice.wake_word import (
    FRAME_LENGTH,
    SAMPLE_RATE,
    AudioCaptureLoop,
    SilenceDetector,
    WakeWordDetector,
    record_until_silence,
)


# --- Test 1: constants -------------------------------------------------------

def test_constants():
    assert FRAME_LENGTH == 1280
    assert SAMPLE_RATE == 16000


# --- Test 2: VAD logic -------------------------------------------------------

def test_vad_silence_before_speech_never_ends():
    det = SilenceDetector()
    # >0.8s of pure silence first (26 silent frames ~ 0.83s). Must never end,
    # heard_speech must stay False.
    silent = np.zeros(FRAME_LENGTH, dtype=np.int16)
    for _ in range(40):
        assert det.update(silent) is False
        assert det.heard_speech is False


def test_vad_ends_after_silence_following_speech():
    det = SilenceDetector()
    speech = np.ones(FRAME_LENGTH, dtype=np.int16) * 5000
    silent = np.zeros(FRAME_LENGTH, dtype=np.int16)

    # One speech frame -> heard_speech True, not ended.
    assert det.update(speech) is False
    assert det.heard_speech is True

    # Each silent frame = 1280/16000 = 0.08s. Need 0.8s -> ~10 frames.
    # Run 12 frames to safely clear the 0.8s threshold (avoids fp edge cases).
    results = [det.update(silent) for _ in range(12)]
    # Must NOT end before 0.72s of silence accumulated.
    assert results[7] is False   # after 8 silent frames = 0.640s
    # Must have ended by 0.88s (11 frames) regardless of fp rounding.
    assert results[10] is True   # after 11 silent frames = 0.880s
    assert any(results)


# --- Test 3: record_until_silence returns int16 array ------------------------

@pytest.mark.asyncio
async def test_record_until_silence_returns_int16_array():
    class FakeCapture:
        sample_rate = SAMPLE_RATE

        async def frames(self):
            speech = np.ones(FRAME_LENGTH, dtype=np.int16) * 5000
            silent = np.zeros(FRAME_LENGTH, dtype=np.int16)
            for _ in range(10):
                yield speech
            for _ in range(30):
                yield silent

    result = await record_until_silence(FakeCapture())
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.int16
    assert result.size > 0


# --- Test 4: openwakeword unavailable disables gracefully --------------------

@pytest.mark.asyncio
async def test_oww_unavailable_does_not_raise(monkeypatch):
    import backend.voice.wake_word as ww

    def fake_init_model(self) -> bool:
        self._enabled = False
        return False

    monkeypatch.setattr(ww.WakeWordDetector, "_init_model", fake_init_model)

    det = WakeWordDetector()
    # Must not raise.
    await det.start()
    assert det.is_enabled is False
    assert det.is_running is False
    await det.stop()


# --- Test 5: wake-word callback fires on detection ---------------------------

@pytest.mark.asyncio
async def test_callback_fires_on_detection(monkeypatch):
    import asyncio

    import backend.voice.wake_word as ww

    call_count = {"n": 0}

    class FakeModel:
        def predict(self, frame):
            call_count["n"] += 1
            # Score above threshold on first frame only.
            return {"hey_jarvis": 0.9 if call_count["n"] == 1 else 0.0}

    def fake_init_model(self) -> bool:
        self._model = FakeModel()
        return True

    monkeypatch.setattr(ww.WakeWordDetector, "_init_model", fake_init_model)

    class FakeCapture:
        sample_rate = SAMPLE_RATE
        frame_length = FRAME_LENGTH

        async def start(self):
            pass

        async def stop(self):
            pass

        async def frames(self):
            yield np.zeros(FRAME_LENGTH, dtype=np.int16)

    fired = {"hit": False}

    async def on_wake():
        fired["hit"] = True

    det = WakeWordDetector(capture=FakeCapture())
    det.on_detected(on_wake)
    await det.start()

    # Give the background _run task a moment to consume the single frame.
    for _ in range(20):
        if fired["hit"]:
            break
        await asyncio.sleep(0.01)

    await det.stop()
    assert fired["hit"] is True
