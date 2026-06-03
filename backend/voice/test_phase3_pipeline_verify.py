"""Phase 3 tasks 1(full pipeline) / 2(interrupt) / 3(voice_state) verification.

Covers the three final Phase 3 voice items end-to-end with mocks only (no mic,
no API keys, no hardware):

* Full pipeline state machine: wake -> listening -> thinking -> speaking -> idle,
  Claude called with the transcript, TTS spoken.
* Empty transcript short-circuits before Claude / speaking.
* Spoken "stop" cancels an in-flight (slow) response and returns to idle.
* Every state transition broadcasts a VoiceStateEvent with the right state.
* Lifespan gating: voice_pipeline only starts when the Porcupine key exists.

Run with:
    .venv\\Scripts\\python.exe -m pytest backend/voice/test_phase3_pipeline_verify.py -v
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

import backend.voice.pipeline as pipeline_mod
from backend.events import VoiceStateEvent
from backend.voice.pipeline import VoicePipeline


# --- Test doubles ------------------------------------------------------------


class RecordingHub:
    """Fake ConnectionHub that records every broadcast event."""

    def __init__(self) -> None:
        self.events: list[object] = []

    async def broadcast(self, event: object) -> None:
        self.events.append(event)

    @property
    def states(self) -> list[str]:
        return [e.state for e in self.events if isinstance(e, VoiceStateEvent)]


class FakeDetector:
    """Minimal stand-in for WakeWordDetector.

    Exposes the surface VoicePipeline touches: ``_capture`` attribute,
    ``on_detected`` registration, idempotent ``start``/``stop`` and
    ``is_enabled``. ``fire()`` invokes the registered wake callback to simulate
    a detection.
    """

    def __init__(self) -> None:
        self._capture = object()  # pipeline only passes this to record_until_silence
        self._callback = None
        self.is_enabled = True
        self.started = False

    def on_detected(self, callback) -> None:
        self._callback = callback

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def fire(self) -> None:
        assert self._callback is not None
        await self._callback()


def _make_pipeline(hub: RecordingHub, detector: FakeDetector) -> VoicePipeline:
    # Inject a dummy claude; individual tests patch stream_response on the class
    # via the pipeline module's ClaudeClient, so the instance just needs to exist.
    return VoicePipeline(hub=hub, claude=_FakeClaude(), detector=detector)


class _FakeClaude:
    """Default no-op Claude; tests override stream_response per-case."""

    async def stream_response(self, messages, system_prompt):  # pragma: no cover
        if False:
            yield ""  # make this an async generator


async def _drain_turn(pipeline: VoicePipeline) -> None:
    """Await the in-flight turn task started by a wake fire (with a timeout)."""
    task = pipeline._turn_task
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
    # Let the done-callback (_clear) run.
    await asyncio.sleep(0)


# --- Test 1: full pipeline state transitions ---------------------------------


async def test_full_pipeline_state_transitions(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()

    record_calls: list[object] = []
    claude_calls: list[list] = []
    tts_calls: list[str] = []

    async def fake_record(capture, **kw):
        record_calls.append(capture)
        return np.ones(1600, dtype=np.int16)

    async def fake_transcribe(audio, sample_rate=16000):
        return "hello"

    async def fake_speak_and_play(text):
        tts_calls.append(text)
        return b"audio"

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", fake_speak_and_play)

    pipeline = _make_pipeline(hub, detector)

    async def fake_stream(messages, system_prompt):
        claude_calls.append(messages)
        for tok in ("Good ", "afternoon, ", "sir. ", "All systems nominal."):
            yield tok

    monkeypatch.setattr(pipeline._claude, "stream_response", fake_stream)

    await pipeline.start()
    await detector.fire()
    await _drain_turn(pipeline)

    states = hub.states
    # Sequence must include listening -> thinking -> speaking -> idle in order.
    for expected in ("listening", "thinking", "speaking", "idle"):
        assert expected in states, f"missing {expected!r} in {states}"
    assert states.index("listening") < states.index("thinking") < states.index(
        "speaking"
    ) < (len(states) - 1 - states[::-1].index("idle"))
    # Ends idle.
    assert states[-1] == "idle"

    # Claude was called with the transcript.
    assert claude_calls, "Claude stream_response never called"
    assert claude_calls[0] == [{"role": "user", "content": "hello"}]

    # TTS was called (whole reply spoken across chunks).
    assert tts_calls, "TTS never called"
    assert "".join(tts_calls).replace(" ", "") == "Goodafternoon,sir.Allsystemsnominal."

    await pipeline.stop()


# --- Test 2: empty transcript short-circuits ---------------------------------


async def test_empty_transcript_skips_claude_and_speaking(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()

    claude_called = {"hit": False}
    tts_called = {"hit": False}

    async def fake_record(capture, **kw):
        return np.ones(1600, dtype=np.int16)

    async def fake_transcribe(audio, sample_rate=16000):
        return ""

    async def fake_speak_and_play(text):
        tts_called["hit"] = True
        return b""

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", fake_speak_and_play)

    pipeline = _make_pipeline(hub, detector)

    async def fake_stream(messages, system_prompt):
        claude_called["hit"] = True
        yield "should not happen"

    monkeypatch.setattr(pipeline._claude, "stream_response", fake_stream)

    await pipeline.start()
    await detector.fire()
    await _drain_turn(pipeline)

    states = hub.states
    assert claude_called["hit"] is False, "Claude must not be called on empty transcript"
    assert tts_called["hit"] is False, "TTS must not be called on empty transcript"
    assert "speaking" not in states, f"unexpected speaking state in {states}"
    assert states[-1] == "idle"

    await pipeline.stop()


# --- Test 3: interrupt cancels an in-flight response -------------------------


async def test_interrupt_cancels_response(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()

    tts_chunks: list[str] = []
    response_completed = {"hit": False}

    async def fake_record(capture, **kw):
        return np.ones(1600, dtype=np.int16)

    # transcribe is used for BOTH the utterance and the interrupt windows.
    # First call (the utterance) -> a real prompt. Subsequent calls (interrupt
    # windows) -> "stop".
    call_count = {"n": 0}

    async def fake_transcribe(audio, sample_rate=16000):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "tell me a very long story"
        return "stop"

    async def slow_speak_and_play(text):
        # Slow playback so the interrupt window has time to win.
        tts_chunks.append(text)
        await asyncio.sleep(0.2)
        return b"audio"

    async def fake_record_interrupt_window(self):
        # Return non-empty audio so the interrupt listener transcribes it.
        await asyncio.sleep(0.01)
        return np.ones(1600, dtype=np.int16)

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", slow_speak_and_play)
    monkeypatch.setattr(
        VoicePipeline, "_record_interrupt_window", fake_record_interrupt_window
    )

    pipeline = _make_pipeline(hub, detector)

    async def slow_stream(messages, system_prompt):
        # Many tokens with small delays so generation outlasts the interrupt.
        for i in range(50):
            yield f"This is sentence number {i} of a long monologue. "
            await asyncio.sleep(0.05)
        response_completed["hit"] = True

    monkeypatch.setattr(pipeline._claude, "stream_response", slow_stream)

    await pipeline.start()
    await detector.fire()
    await _drain_turn(pipeline)

    states = hub.states
    # The response must have been interrupted (not run to completion).
    assert response_completed["hit"] is False, "response was not cancelled"
    # Pipeline returns to idle after interrupt.
    assert states[-1] == "idle"
    # We reached at least thinking (and likely speaking) before the interrupt.
    assert "thinking" in states

    await pipeline.stop()


# --- Test 4: every transition broadcasts a VoiceStateEvent -------------------


async def test_each_transition_broadcasts_voice_state_event(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()

    async def fake_record(capture, **kw):
        return np.ones(1600, dtype=np.int16)

    async def fake_transcribe(audio, sample_rate=16000):
        return "status report"

    async def fake_speak_and_play(text):
        return b"audio"

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", fake_speak_and_play)

    pipeline = _make_pipeline(hub, detector)

    async def fake_stream(messages, system_prompt):
        yield "All systems are functioning within normal parameters, sir."

    monkeypatch.setattr(pipeline._claude, "stream_response", fake_stream)

    await pipeline.start()
    await detector.fire()
    await _drain_turn(pipeline)

    # Every state-carrying broadcast must be a VoiceStateEvent (type == voice_state)
    # with a valid state string.
    valid = {"idle", "listening", "thinking", "speaking"}
    voice_events = [e for e in hub.events if isinstance(e, VoiceStateEvent)]
    assert voice_events, "no VoiceStateEvent broadcast"
    for ev in voice_events:
        assert ev.type == "voice_state"
        assert ev.state in valid, f"unexpected state {ev.state!r}"

    # Each of the four states was broadcast as its own event.
    broadcast_states = {e.state for e in voice_events}
    assert {"listening", "thinking", "speaking", "idle"} <= broadcast_states

    await pipeline.stop()


# --- Test 5: lifespan gating on the Porcupine credential ---------------------


def _run_lifespan_and_get_pipeline(monkeypatch, has_key: bool):
    """Drive the FastAPI app lifespan via Starlette TestClient (which actually
    runs lifespan, unlike httpx ASGITransport) and return app.state.voice_pipeline.
    """
    import backend.main as main_mod
    from starlette.testclient import TestClient

    monkeypatch.setattr(
        main_mod.keystore,
        "has_credential",
        lambda username: has_key,
    )

    # Avoid real DB / vector-store / network side effects during startup.
    async def _noop_init_db():
        return None

    monkeypatch.setattr(main_mod, "init_db", _noop_init_db)

    class _FakeVectorStore:
        def load(self):
            raise FileNotFoundError

        def save(self):  # pragma: no cover - not reached when empty
            pass

        def __len__(self):
            return 0

    monkeypatch.setattr(main_mod, "VectorStore", _FakeVectorStore)

    captured = {"pipeline": "unset"}

    if has_key:
        # Replace VoicePipeline with a fake so start()/stop() don't touch audio.
        class _FakePipeline:
            def __init__(self, *a, **k):
                pass

            async def start(self):
                pass

            async def stop(self):
                pass

        monkeypatch.setattr(main_mod, "VoicePipeline", _FakePipeline)

    with TestClient(main_mod.app) as client:
        client.get("/health")
        captured["pipeline"] = main_mod.app.state.voice_pipeline

    return captured["pipeline"]


def test_lifespan_skips_pipeline_without_key(monkeypatch):
    result = _run_lifespan_and_get_pipeline(monkeypatch, has_key=False)
    assert result is None, "voice_pipeline must be None when Porcupine key is absent"


def test_lifespan_starts_pipeline_with_key(monkeypatch):
    result = _run_lifespan_and_get_pipeline(monkeypatch, has_key=True)
    assert result is not None, "voice_pipeline must be started when Porcupine key exists"
