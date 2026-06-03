"""Phase 10 backend verification suite (debugger-agent).

Covers the four Phase 10 backend tasks delegated for verification:

1. AudioLevelEvent broadcasting from TTS playback (backend/voice/tts.py +
   backend/events.py).
2. Voice-pipeline crash recovery / error parking (backend/voice/pipeline.py).
3. Graceful degradation Claude -> Ollama (backend/voice/pipeline.py::_iter_reply).
4. First-run setup wizard API (backend/setup_wizard.py).

All tests use mocks/fakes — no audio device, no network, no real keys.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ai.claude_client import ClaudeAPIError
from backend.events import AudioLevelEvent
from backend.security.keystore import MissingCredentialError
from backend.voice import pipeline as pipeline_mod
from backend.voice import tts as tts_mod
from backend.voice.pipeline import MAX_TURN_RETRIES, VoicePipeline


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class FakeHub:
    """Captures every broadcast so a test can assert on the event stream."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    async def broadcast(self, event: Any) -> None:
        self.events.append(event)


class _StubDetector:
    """A wake-word detector that never fires and starts/stops cleanly."""

    def __init__(self) -> None:
        self._capture = object()
        self.is_enabled = False
        self.start_calls = 0

    def on_detected(self, _cb: Any) -> None:  # noqa: D401 - stub
        self._cb = _cb

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        pass


def _make_pipeline(**kwargs: Any) -> tuple[VoicePipeline, FakeHub, _StubDetector]:
    hub = FakeHub()
    detector = _StubDetector()
    pipe = VoicePipeline(hub=hub, detector=detector, **kwargs)  # type: ignore[arg-type]
    return pipe, hub, detector


# ===========================================================================
# TEST 1 — AudioLevelEvent (backend/voice/tts.py + backend/events.py)
# ===========================================================================


def test_audio_level_event_shape() -> None:
    """AudioLevelEvent has type='audio_level' and a level field, serialisable."""
    ev = AudioLevelEvent(level=0.42)
    assert ev.type == "audio_level"
    assert ev.level == 0.42
    d = ev.to_dict()
    assert d["type"] == "audio_level"
    assert d["level"] == 0.42
    # Default is rest.
    assert AudioLevelEvent().level == 0.0


def test_rms_level_silence_fullscale_empty() -> None:
    """_rms_level: silence -> 0.0, full-scale int16 -> ~1.0, empty -> 0.0."""
    silence = np.zeros(800, dtype=np.int16)
    assert tts_mod._rms_level(silence) == 0.0

    # Full-scale: constant +32767 ~ full scale; RMS / 32768 ~ 1.0 (clipped).
    full = np.full(800, 32767, dtype=np.int16)
    level = tts_mod._rms_level(full)
    assert 0.999 <= level <= 1.0

    empty = np.zeros(0, dtype=np.int16)
    assert tts_mod._rms_level(empty) == 0.0

    # A value that would exceed 1.0 before clipping still clamps to 1.0.
    hot = np.full(10, 32768, dtype=np.int64).astype(np.float64)
    assert tts_mod._rms_level(hot) == 1.0


@pytest.mark.asyncio
async def test_speak_and_play_broadcasts_audio_levels(monkeypatch: Any) -> None:
    """Every broadcast is an AudioLevelEvent in [0,1]; the LAST has level 0.0."""
    hub = FakeHub()
    monkeypatch.setattr(tts_mod, "hub", hub)

    # Known PCM: a loud block followed by silence so we get >1 level event and a
    # mix of non-zero / zero amplitudes. Sized to span several 50 ms blocks.
    block = int(tts_mod.PCM_SAMPLE_RATE * tts_mod.AUDIO_LEVEL_INTERVAL_S)
    loud = np.full(block * 2, 20000, dtype=np.int16)
    quiet = np.zeros(block * 2, dtype=np.int16)
    pcm = np.concatenate([loud, quiet]).tobytes()

    async def fake_convert(text: str, output_format: str) -> bytes:
        return pcm

    monkeypatch.setattr(tts_mod, "_convert", fake_convert)
    # No real audio device: playback is a no-op.
    monkeypatch.setattr(tts_mod, "_play_pcm_block_sync", lambda *a, **k: None)

    out = await tts_mod.speak_and_play("hi")
    assert out == pcm

    assert hub.events, "expected at least one AudioLevelEvent"
    for ev in hub.events:
        assert isinstance(ev, AudioLevelEvent)
        assert 0.0 <= ev.level <= 1.0
    # Last event always settles the orb back to rest.
    assert hub.events[-1].level == 0.0
    # Sanity: at least one loud block produced a non-zero level.
    assert any(ev.level > 0.0 for ev in hub.events)


@pytest.mark.asyncio
async def test_speak_and_play_final_zero_on_playback_error(monkeypatch: Any) -> None:
    """If playback raises mid-stream, the finally block still broadcasts 0.0."""
    hub = FakeHub()
    monkeypatch.setattr(tts_mod, "hub", hub)

    block = int(tts_mod.PCM_SAMPLE_RATE * tts_mod.AUDIO_LEVEL_INTERVAL_S)
    pcm = np.full(block * 3, 15000, dtype=np.int16).tobytes()

    async def fake_convert(text: str, output_format: str) -> bytes:
        return pcm

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("audio device exploded")

    monkeypatch.setattr(tts_mod, "_convert", fake_convert)
    monkeypatch.setattr(tts_mod, "_play_pcm_block_sync", boom)

    out = await tts_mod.speak_and_play("hi")
    assert out == pcm  # PCM still returned despite playback failure
    assert hub.events, "expected a final settle event even on failure"
    assert hub.events[-1].level == 0.0
    assert all(isinstance(e, AudioLevelEvent) for e in hub.events)


# ===========================================================================
# TEST 2 — Error recovery (backend/voice/pipeline.py)
# ===========================================================================


@pytest.mark.asyncio
async def test_pipeline_parks_in_error_after_max_crashes(monkeypatch: Any) -> None:
    """3 consecutive _run_turn crashes -> state 'error', counter==3, no retry."""
    pipe, hub, detector = _make_pipeline()
    pipe._running = True

    # asyncio.sleep -> no-op so the crash-recovery delay doesn't slow the test.
    async def no_sleep(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(pipeline_mod.asyncio, "sleep", no_sleep)

    # Make the turn body always blow up.
    async def boom() -> None:
        raise RuntimeError("turn fault")

    monkeypatch.setattr(pipe, "_set_state", _record_state(pipe))
    monkeypatch.setattr(pipe, "_run_turn", _crashing_run_turn(pipe, boom))

    for _ in range(MAX_TURN_RETRIES):
        await pipe._run_turn()

    assert pipe._consecutive_crashes == MAX_TURN_RETRIES == 3
    assert pipe.state == "error"


@pytest.mark.asyncio
async def test_pipeline_crash_counter_resets_after_clean_turn(
    monkeypatch: Any,
) -> None:
    """Crash twice, then one clean turn -> _consecutive_crashes back to 0."""
    pipe, hub, detector = _make_pipeline()
    pipe._running = True

    async def no_sleep(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(pipeline_mod.asyncio, "sleep", no_sleep)

    states: list[str] = []

    async def fake_set_state(state: str) -> None:
        pipe._state = state
        states.append(state)

    monkeypatch.setattr(pipe, "_set_state", fake_set_state)

    # Drive the real _run_turn but control the inner stages it calls.
    async def fake_record(_capture: Any) -> np.ndarray:
        return np.zeros(10, dtype=np.int16)

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)

    crash_plan = iter([True, True, False])

    async def fake_transcribe(_audio: np.ndarray) -> str:
        if next(crash_plan):
            raise RuntimeError("stt fault")
        return "hello"

    async def fake_respond(_transcript: str) -> None:
        return None

    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipe, "_respond_with_interrupt", fake_respond)

    await pipe._run_turn()  # crash 1
    assert pipe._consecutive_crashes == 1
    await pipe._run_turn()  # crash 2
    assert pipe._consecutive_crashes == 2
    await pipe._run_turn()  # clean turn
    assert pipe._consecutive_crashes == 0
    assert pipe.state == "idle"


def _record_state(pipe: VoicePipeline):
    async def fake_set_state(state: str) -> None:
        pipe._state = state

    return fake_set_state


def _crashing_run_turn(pipe: VoicePipeline, boom):
    """Build a _run_turn replacement that always crashes and recovers, mirroring
    the real finally/_handle_turn_crash contract."""

    async def run_turn() -> None:
        crashed = False
        try:
            await boom()
        except Exception:  # noqa: BLE001
            crashed = True
        finally:
            if crashed:
                await pipe._handle_turn_crash()
            else:
                pipe._consecutive_crashes = 0
                if pipe._running:
                    await pipe._set_state("idle")

    return run_turn


# ===========================================================================
# TEST 3 — Graceful degradation (Claude -> Ollama)
# ===========================================================================


class _FakeClaude:
    def __init__(self, exc: Exception | None = None, tokens: list[str] | None = None):
        self._exc = exc
        self._tokens = tokens or []

    async def stream_response(self, messages, system_prompt, *a, **k):
        for t in self._tokens:
            yield t
        if self._exc is not None:
            raise self._exc


class _FakeOllama:
    def __init__(self, tokens: list[str]):
        self._tokens = tokens
        self.called = False

    async def stream_response(self, messages, system_prompt, *a, **k):
        self.called = True
        for t in self._tokens:
            yield t


async def _collect(pipe: VoicePipeline) -> list[str]:
    msgs = [{"role": "user", "content": "hi"}]
    return [tok async for tok in pipe._iter_reply(msgs, "sys")]


@pytest.mark.asyncio
async def test_fallback_to_ollama_on_missing_credential() -> None:
    """Claude raises MissingCredentialError pre-token -> Ollama output used."""
    claude = _FakeClaude(exc=MissingCredentialError("ANTHROPIC_API_KEY"))
    ollama = _FakeOllama(["Hello ", "sir."])
    pipe, _, _ = _make_pipeline(claude=claude, ollama=ollama)

    tokens = await _collect(pipe)
    assert tokens == ["Hello ", "sir."]
    assert ollama.called is True


@pytest.mark.asyncio
async def test_fallback_to_ollama_on_claude_api_error() -> None:
    """Claude raises ClaudeAPIError pre-token -> Ollama output used."""
    claude = _FakeClaude(exc=ClaudeAPIError("503 unavailable"))
    ollama = _FakeOllama(["Hello ", "sir."])
    pipe, _, _ = _make_pipeline(claude=claude, ollama=ollama)

    tokens = await _collect(pipe)
    assert tokens == ["Hello ", "sir."]
    assert ollama.called is True


@pytest.mark.asyncio
async def test_no_fallback_after_midstream_failure() -> None:
    """Claude yields one token then raises -> Ollama NOT used (no restart)."""
    claude = _FakeClaude(exc=ClaudeAPIError("died mid-stream"), tokens=["partial "])
    ollama = _FakeOllama(["should-not-appear"])
    pipe, _, _ = _make_pipeline(claude=claude, ollama=ollama)

    tokens = await _collect(pipe)
    assert tokens == ["partial "]
    assert ollama.called is False


# ===========================================================================
# TEST 4 — Setup wizard (backend/setup_wizard.py)
# ===========================================================================


@pytest.fixture()
def wizard_client(monkeypatch: Any) -> TestClient:
    """A TestClient over a minimal app mounting only the setup router.

    The setup endpoints touch only the keystore, so we back it with an in-memory
    fake keyring rather than the Windows Credential Manager. This isolates the
    test from the full app lifespan (DB, agents, voice, etc.).
    """
    from backend import setup_wizard

    store: dict[str, str] = {}

    def fake_has(username: str) -> bool:
        return bool(store.get(username))

    def fake_set(username: str, value: str) -> None:
        if not isinstance(value, str) or value == "":
            raise ValueError("empty")
        store[username] = value

    monkeypatch.setattr(setup_wizard.keystore, "has_credential", fake_has)
    monkeypatch.setattr(setup_wizard.keystore, "_set", fake_set)

    app = FastAPI()
    app.include_router(setup_wizard.router)
    return TestClient(app)


def _no_values_in_body(body: dict, secret: str) -> bool:
    import json

    return secret not in json.dumps(body)


def test_setup_status_all_missing(wizard_client: TestClient) -> None:
    r = wizard_client.get("/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert data["complete"] is False
    assert set(data["missing"]) == set(data["required"])
    assert len(data["missing"]) == 7


def test_setup_post_credential_stores(wizard_client: TestClient) -> None:
    r = wizard_client.post(
        "/setup/credential",
        json={"name": "anthropic_api_key", "value": "sk-x"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["stored"] == "anthropic_api_key"
    assert "anthropic_api_key" not in data["missing"]
    # The secret value must never be echoed.
    assert _no_values_in_body(data, "sk-x")


def test_setup_post_unknown_name_rejected(wizard_client: TestClient) -> None:
    r = wizard_client.post(
        "/setup/credential",
        json={"name": "totally_unknown", "value": "whatever"},
    )
    assert r.status_code == 400


def test_setup_complete_flips_when_all_present(wizard_client: TestClient) -> None:
    # Missing at start.
    assert wizard_client.get("/setup/complete").json()["complete"] is False

    from backend.setup_wizard import REQUIRED_CREDENTIALS

    for name in REQUIRED_CREDENTIALS:
        r = wizard_client.post(
            "/setup/credential", json={"name": name, "value": f"val-{name}"}
        )
        assert r.status_code == 200

    final = wizard_client.get("/setup/complete").json()
    assert final["complete"] is True

    status = wizard_client.get("/setup/status").json()
    assert status["complete"] is True
    assert status["missing"] == []


def test_setup_responses_never_leak_values(wizard_client: TestClient) -> None:
    """No stored secret value appears in any setup response body."""
    secret = "super-secret-token-12345"
    post = wizard_client.post(
        "/setup/credential", json={"name": "slack_bot_token", "value": secret}
    )
    assert _no_values_in_body(post.json(), secret)
    assert _no_values_in_body(wizard_client.get("/setup/status").json(), secret)
    assert _no_values_in_body(wizard_client.get("/setup/complete").json(), secret)
