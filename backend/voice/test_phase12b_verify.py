"""Phase 12B verification — memory wired into the voice pipeline.

Targeted tests for the Phase 12B change: ``_stream_and_speak`` / ``process_text``
now recall memory *before* the Claude call and store + consolidate *after* TTS
completes, while an interrupted (cancelled mid-stream) turn must NOT store a
partial reply. Persona ``build_system_prompt`` must accept the memory manager's
pre-formatted multi-section context without emitting a duplicate
``# Current context`` header.

All tests use mocks only — no microphone, no API keys, no real DB / FAISS.

Run with:
    .venv\\Scripts\\python.exe -m pytest backend/voice/test_phase12b_verify.py -v
"""

from __future__ import annotations

import asyncio
import time

import numpy as np
import pytest

import backend.voice.pipeline as pipeline_mod
from backend.ai.persona import build_system_prompt
from backend.events import VoiceStateEvent
from backend.memory.manager import RecallResult
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
    """Minimal stand-in for WakeWordDetector (only the surface the pipeline uses)."""

    def __init__(self) -> None:
        self._capture = object()
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


class _FakeClaude:
    """Records the messages it was streamed and yields a canned reply.

    ``stream_response`` must be an async generator. The captured ``messages`` and
    ``system_prompt`` are stored on the instance for assertions.
    """

    def __init__(self, tokens=("Acknowledged, sir.",)) -> None:
        self._tokens = tokens
        self.calls: list[dict] = []

    async def stream_response(self, messages, system_prompt):
        # Capture a *copy* of messages so later mutation can't taint the record.
        self.calls.append(
            {"messages": list(messages), "system_prompt": system_prompt}
        )
        for tok in self._tokens:
            yield tok


class FakeMemoryManager:
    """Stand-in for MemoryManager recording recall/store/consolidate activity.

    Only the three methods the pipeline calls are implemented. ``recall`` returns
    the injected :class:`RecallResult`; ``store`` and ``consolidate`` record their
    calls. ``consolidate_delay`` lets a test prove fire-and-forget by making
    consolidation slow.
    """

    def __init__(
        self,
        recall_result: RecallResult | None = None,
        consolidate_delay: float = 0.0,
    ) -> None:
        self._recall_result = recall_result or RecallResult()
        self._consolidate_delay = consolidate_delay
        self.recall_calls: list[dict] = []
        self.store_calls: list[dict] = []
        self.consolidate_calls: list[dict] = []
        self.consolidate_started = asyncio.Event()

    async def recall(self, query, n_recent=10, n_semantic=3):
        self.recall_calls.append(
            {"query": query, "n_recent": n_recent, "n_semantic": n_semantic}
        )
        return self._recall_result

    async def store(self, text, role, channel="voice", metadata=None):
        self.store_calls.append({"text": text, "role": role, "channel": channel})
        return len(self.store_calls)

    async def consolidate(self, user_text, reply, *, source="voice", agent_id=None):
        self.consolidate_started.set()
        self.consolidate_calls.append({"user_text": user_text, "reply": reply})
        if self._consolidate_delay:
            await asyncio.sleep(self._consolidate_delay)
        return None


def _make_pipeline(
    hub: RecordingHub,
    detector: FakeDetector,
    claude: _FakeClaude,
    memory_manager=None,
) -> VoicePipeline:
    return VoicePipeline(
        hub=hub, claude=claude, detector=detector, memory_manager=memory_manager
    )


def _patch_tts(monkeypatch, sink: list[str] | None = None):
    async def fake_speak_and_play(text):
        if sink is not None:
            sink.append(text)
        return b"audio"

    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", fake_speak_and_play)


# --- Test 1: memory recall before the Claude call ----------------------------


async def test_recall_prepends_episodic_before_new_message(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()
    claude = _FakeClaude()
    _patch_tts(monkeypatch)

    recall = RecallResult(
        episodic_messages=[{"role": "user", "content": "previous message"}],
        formatted_context="# Current context\nDate: now",
    )
    mm = FakeMemoryManager(recall_result=recall)
    pipeline = _make_pipeline(hub, detector, claude, memory_manager=mm)

    ok = await pipeline.process_text("hello")
    assert ok is True

    # recall happened before the Claude call.
    assert mm.recall_calls, "recall was never called"
    assert claude.calls, "Claude stream_response never called"

    sent = claude.calls[0]["messages"]
    # The recalled episodic message must come first, then the new user message.
    assert sent[0] == {"role": "user", "content": "previous message"}
    assert sent[1] == {"role": "user", "content": "hello"}
    assert len(sent) == 2


# --- Test 2: store called exactly twice (user + jarvis) ----------------------


async def test_store_called_twice_after_turn(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()
    claude = _FakeClaude(tokens=("All ", "is ", "well, sir."))
    _patch_tts(monkeypatch)

    mm = FakeMemoryManager()
    pipeline = _make_pipeline(hub, detector, claude, memory_manager=mm)

    await pipeline.process_text("hello")

    assert len(mm.store_calls) == 2, f"expected 2 store calls, got {mm.store_calls}"
    roles = [c["role"] for c in mm.store_calls]
    assert roles == ["user", "jarvis"], roles
    assert mm.store_calls[0]["text"] == "hello"
    assert mm.store_calls[1]["text"] == "All is well, sir."


# --- Test 3: consolidate is fire-and-forget ----------------------------------


async def test_consolidate_is_fire_and_forget(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()
    claude = _FakeClaude(tokens=("Done.",))
    _patch_tts(monkeypatch)

    # consolidate sleeps 10s; if it were awaited the call would block ~10s.
    mm = FakeMemoryManager(consolidate_delay=10.0)
    pipeline = _make_pipeline(hub, detector, claude, memory_manager=mm)

    start = time.monotonic()
    await pipeline.process_text("hello")
    elapsed = time.monotonic() - start

    # The turn returned well before the 10s consolidation completes.
    assert elapsed < 1.0, f"process_text blocked on consolidate ({elapsed:.2f}s)"
    # consolidate was kicked off (as a task), not skipped.
    await asyncio.wait_for(mm.consolidate_started.wait(), timeout=1.0)
    assert mm.consolidate_calls, "consolidate task was never scheduled"


# --- Test 4: no-memory fallback (memory_manager=None) ------------------------


async def test_no_memory_manager_single_message(monkeypatch):
    hub = RecordingHub()
    detector = FakeDetector()
    claude = _FakeClaude(tokens=("Hello.",))
    spoke: list[str] = []
    _patch_tts(monkeypatch, sink=spoke)

    pipeline = _make_pipeline(hub, detector, claude, memory_manager=None)
    # start() so the pipeline is "running" and unwinds to idle after the turn,
    # mirroring how the live /api/chat caller drives process_text.
    await pipeline.start()

    ok = await pipeline.process_text("hello")
    assert ok is True

    # Claude was called with exactly one message — no recalled context.
    assert claude.calls, "Claude stream_response never called"
    sent = claude.calls[0]["messages"]
    assert sent == [{"role": "user", "content": "hello"}], sent

    # Turn completed and spoke, ending idle — no NoneType/Attribute errors.
    assert spoke, "TTS never spoke the reply"
    assert hub.states[-1] == "idle"

    await pipeline.stop()


# --- Test 5: persona accepts pre-formatted context without a duplicate header -


def test_persona_no_duplicate_header_for_formatted_context():
    context = (
        "# Current context\n"
        "Date: 2026-06-05\n\n"
        "## What I remember about you\n"
        "User prefers short answers."
    )
    prompt = build_system_prompt(context=context)

    assert prompt.count("# Current context") == 1, (
        "duplicate '# Current context' heading in formatted-context path"
    )
    assert "User prefers short answers." in prompt


# --- Test 6: persona backward compat for a plain fragment --------------------


def test_persona_wraps_plain_fragment():
    prompt = build_system_prompt(context="some plain text")

    assert prompt.count("# Current context") == 1, (
        "plain fragment should get exactly one '# Current context' heading"
    )
    assert "some plain text" in prompt


# --- Test 7: interrupted turn does not store ---------------------------------


async def test_interrupted_turn_does_not_store(monkeypatch):
    """A turn cancelled mid-stream must not persist a partial reply.

    Drives the real interrupt path: the responder streams slowly while the
    interrupt listener hears "stop" and cancels it. ``store`` must never run.
    """
    hub = RecordingHub()
    detector = FakeDetector()
    mm = FakeMemoryManager()

    async def fake_record(capture, **kw):
        return np.ones(1600, dtype=np.int16)

    # transcribe: first call = the utterance, subsequent = interrupt windows.
    call_count = {"n": 0}

    async def fake_transcribe(audio, sample_rate=16000):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "tell me a very long story"
        return "stop"

    async def slow_speak_and_play(text):
        await asyncio.sleep(0.2)
        return b"audio"

    async def fake_record_interrupt_window(self):
        await asyncio.sleep(0.01)
        return np.ones(1600, dtype=np.int16)

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", slow_speak_and_play)
    monkeypatch.setattr(
        VoicePipeline, "_record_interrupt_window", fake_record_interrupt_window
    )

    claude = _FakeClaude()

    async def slow_stream(messages, system_prompt):
        claude.calls.append({"messages": list(messages), "system_prompt": system_prompt})
        for i in range(50):
            yield f"This is sentence number {i} of a long monologue. "
            await asyncio.sleep(0.05)

    monkeypatch.setattr(claude, "stream_response", slow_stream)

    pipeline = _make_pipeline(hub, detector, claude, memory_manager=mm)

    await pipeline.start()
    await detector.fire()
    task = pipeline._turn_task
    assert task is not None
    await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
    await asyncio.sleep(0)

    # The turn was interrupted and ended idle.
    assert hub.states[-1] == "idle"
    # recall ran (the user message reached Claude) ...
    assert mm.recall_calls, "recall should have run before the cancelled stream"
    # ... but NO store happened — the interrupted reply must not be persisted.
    assert mm.store_calls == [], (
        f"interrupted turn must not store, got {mm.store_calls}"
    )
    assert mm.consolidate_calls == [], "interrupted turn must not consolidate"

    await pipeline.stop()
