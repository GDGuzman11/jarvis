"""Phase 3 tasks 1-3 verification: audio capture + Porcupine wake word + VAD.

Run with: .venv\\Scripts\\python.exe -m pytest backend/voice/test_phase3_verify.py -v
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.security import keystore
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
    assert FRAME_LENGTH == 512
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

    # Each silent frame = 512/16000 = 0.032s. Need 0.8s -> ceil(0.8/0.032)=25.
    # So frame #25 should be the first to cross the threshold.
    results = [det.update(silent) for _ in range(26)]
    # Must NOT end before 0.8s of silence accumulated.
    assert results[23] is False  # after 24 silent frames = 0.768s
    # Must end by/after the 25th silent frame (0.8s).
    assert results[24] is True   # after 25 silent frames = 0.800s
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


# --- Test 4: missing key graceful path ---------------------------------------

@pytest.mark.asyncio
async def test_missing_key_does_not_raise(monkeypatch):
    def _raise():
        raise keystore.MissingCredentialError("PORCUPINE_ACCESS_KEY")

    monkeypatch.setattr(keystore, "get_porcupine_access_key", _raise)

    det = WakeWordDetector()
    # Must not raise.
    await det.start()
    assert det.is_enabled is False
    assert det.is_running is False
    await det.stop()


# --- Test 5: wake-word callback fires on detection ---------------------------

@pytest.mark.asyncio
async def test_callback_fires_on_detection(monkeypatch):
    monkeypatch.setattr(keystore, "get_porcupine_access_key", lambda: "fake-key")

    class FakePorcupine:
        frame_length = FRAME_LENGTH
        sample_rate = SAMPLE_RATE

        def __init__(self):
            self._calls = 0

        def process(self, frame):
            self._calls += 1
            # Detect (keyword index 0) on the first frame, then -1 thereafter.
            return 0 if self._calls == 1 else -1

        def delete(self):
            pass

    import backend.voice.wake_word as ww

    fake_pv = type("FakePvporcupine", (), {"create": staticmethod(lambda **kw: FakePorcupine())})
    monkeypatch.setitem(__import__("sys").modules, "pvporcupine", fake_pv)

    # Fake capture that yields exactly one frame then stops.
    class FakeCapture:
        sample_rate = SAMPLE_RATE
        frame_length = FRAME_LENGTH

        def __init__(self):
            self._running = True

        async def start(self):
            pass

        async def stop(self):
            self._running = False

        async def frames(self):
            yield np.zeros(FRAME_LENGTH, dtype=np.int16)

    fired = {"hit": False}

    async def on_wake():
        fired["hit"] = True

    det = WakeWordDetector(capture=FakeCapture())
    det.on_detected(on_wake)
    await det.start()

    # Give the background _run task a moment to consume the single frame.
    import asyncio
    for _ in range(20):
        if fired["hit"]:
            break
        await asyncio.sleep(0.01)

    await det.stop()
    assert fired["hit"] is True
