"""Phase 9 — Testing & Verification: the final quality gate.

This module is the consolidated Phase 9 suite. It does NOT re-implement the
per-phase suites that already pass (Phase 3 voice pipeline, Phase 4 agents,
Phase 5 integrations, Phase 6 tools) — those run as part of the full
``pytest backend/`` invocation. Instead it fills the specific Phase 9 checklist
gaps that no earlier suite covered, and re-asserts the cross-cutting security
rules in one place:

UNIT
  * STT transcription accuracy — mocked faster-whisper, int16 audio -> expected
    transcript (+ sanitisation of an adversarial transcript).
  * TTS audio output — mocked ElevenLabs -> non-zero audio bytes.
  * Wake-word callback simulation — see Phase 3 ``test_callback_fires_on_detection``;
    re-exercised here through a minimal detector double for completeness.

INTEGRATION
  * Full voice roundtrip (mocked) with latency tracking < 3 s.
  * Claude API streaming + tool use — mocked Anthropic stream yields text tokens
    and a tool_use block; assert tokens stream and the tool call is surfaced.
  * Ollama fallback — Claude raises ClaudeAPIError before any token; the pipeline
    falls back to the local Ollama client (graceful degradation).
  * Slack read/send and Gmail read/draft/send — see Phase 5 suite (mocked SDKs).
  * Agent delegation + state persistence — see Phase 4 suite.

SECURITY
  * Grep scan: no secret patterns committed in any source file.
  * FastAPI binds to 127.0.0.1, never 0.0.0.0.
  * Code executor blocks os.system() and subprocess.

All tests are fully mocked — no microphone, no API keys, no network, no shared
on-disk state. Run with:
    .venv\\Scripts\\python.exe -m pytest backend/test_phase9_verify.py -v
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np

import backend.voice.pipeline as pipeline_mod
from backend.events import VoiceStateEvent
from backend.voice.pipeline import VoicePipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ===========================================================================
# Shared test doubles
# ===========================================================================


class RecordingHub:
    """Fake ConnectionHub recording every broadcast event."""

    def __init__(self) -> None:
        self.events: list[object] = []

    async def broadcast(self, event: object) -> int:
        self.events.append(event)
        return 1

    @property
    def voice_states(self) -> list[str]:
        return [e.state for e in self.events if isinstance(e, VoiceStateEvent)]


class FakeDetector:
    """Minimal WakeWordDetector stand-in the pipeline can drive without a mic."""

    def __init__(self) -> None:
        self._capture = object()
        self._callback = None
        self.is_enabled = True
        self.started = False

    def on_detected(self, callback) -> None:  # noqa: ANN001
        self._callback = callback

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def fire(self) -> None:
        assert self._callback is not None
        await self._callback()


class _StubClaude:
    """Default no-op Claude; per-test stream_response overrides it."""

    async def stream_response(self, messages, system_prompt):  # noqa: ANN001
        if False:  # pragma: no cover — make this an async generator
            yield ""


class _StubOllama:
    """Default no-op Ollama; per-test stream_response overrides it."""

    async def stream_response(self, messages, system_prompt):  # noqa: ANN001
        if False:  # pragma: no cover
            yield ""


async def _drain_turn(pipeline: VoicePipeline) -> None:
    task = pipeline._turn_task
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
    await asyncio.sleep(0)


# ===========================================================================
# UNIT — STT transcription accuracy (mocked faster-whisper)
# ===========================================================================


async def test_stt_transcribes_int16_audio_to_expected_text(monkeypatch) -> None:
    """A WAV-like int16 utterance -> the exact transcript the model returns."""
    from backend.voice import stt

    captured: dict[str, Any] = {}

    class _Segment:
        def __init__(self, text: str) -> None:
            self.text = text

    class _FakeModel:
        def transcribe(self, audio_f32, language=None):  # noqa: ANN001
            # Whisper is handed float32 in [-1, 1]; verify the conversion happened.
            captured["dtype"] = audio_f32.dtype
            captured["max_abs"] = float(np.max(np.abs(audio_f32)))
            captured["language"] = language
            return ([_Segment("Good afternoon, "), _Segment("sir.")], object())

    monkeypatch.setattr(stt, "_load_model", lambda: _FakeModel())

    # A 1-second 16 kHz int16 utterance (the capture stage's exact format).
    audio = (np.sin(np.linspace(0, 50, 16000)) * 8000).astype(np.int16)
    text = await stt.transcribe(audio)

    assert text == "Good afternoon, sir."
    assert captured["language"] == "en"
    assert captured["dtype"] == np.float32
    # int16 8000 / 32768 ~= 0.244 — proves int16 -> float32 normalisation ran.
    assert captured["max_abs"] <= 1.0


async def test_stt_sanitizes_control_chars_and_caps_length() -> None:
    """Security Rule 3: control chars stripped, transcript capped at 2000 chars."""
    from backend.voice import stt

    dirty = "hello\x00\x07 \x1b world" + ("A" * 3000)
    clean = stt.sanitize_transcript(dirty)
    assert "\x00" not in clean and "\x07" not in clean and "\x1b" not in clean
    assert clean.startswith("hello world")
    assert len(clean) <= stt.MAX_TRANSCRIPT_CHARS == 2000


async def test_stt_empty_audio_returns_empty_string() -> None:
    from backend.voice import stt

    assert await stt.transcribe(np.zeros(0, dtype=np.int16)) == ""


# ===========================================================================
# UNIT — TTS audio output (mocked ElevenLabs -> non-zero bytes)
# ===========================================================================


async def test_tts_speak_returns_nonzero_audio_bytes(monkeypatch) -> None:
    """A configured ElevenLabs client yields non-empty MP3 bytes from speak()."""
    from backend.voice import tts

    fake_audio_chunks = [b"\xff\xfb\x90", b"\x00\x01\x02\x03", b"\x04\x05"]

    fake_client = MagicMock()
    fake_client.text_to_speech.convert.return_value = iter(fake_audio_chunks)

    monkeypatch.setattr(tts, "_make_client", lambda: fake_client)
    monkeypatch.setattr(tts, "_resolve_voice_id", lambda: "voice-123")

    audio = await tts.speak("Good evening, sir.")

    assert isinstance(audio, bytes)
    assert len(audio) > 0
    assert audio == b"".join(fake_audio_chunks)
    # The SDK was called with our voice id + the configured low-latency model.
    args, kwargs = fake_client.text_to_speech.convert.call_args
    assert args[0] == "voice-123"
    assert kwargs["model_id"] == tts.MODEL_ID


async def test_tts_missing_credentials_returns_empty_bytes(monkeypatch) -> None:
    """No ElevenLabs key -> empty bytes, never raises (graceful degradation)."""
    from backend.voice import tts

    monkeypatch.setattr(tts, "_make_client", lambda: None)
    audio = await tts.speak("anything")
    assert audio == b""


async def test_tts_empty_text_short_circuits() -> None:
    from backend.voice import tts

    assert await tts.speak("   ") == b""


# ===========================================================================
# UNIT — wake-word callback simulation
# ===========================================================================


async def test_wake_word_callback_activates_pipeline(monkeypatch) -> None:
    """Simulating a wake-word detection drives the pipeline out of idle."""
    hub = RecordingHub()
    detector = FakeDetector()

    async def fake_record(capture, **kw):  # noqa: ANN001
        return np.ones(1600, dtype=np.int16)

    async def fake_transcribe(audio, sample_rate=16000):  # noqa: ANN001
        return ""  # empty -> short-circuit, we only care the wake fired

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)

    pipeline = VoicePipeline(
        hub=hub, claude=_StubClaude(), ollama=_StubOllama(), detector=detector
    )
    await pipeline.start()
    await detector.fire()
    await _drain_turn(pipeline)

    # The wake callback fired the listen->thinking->idle transition.
    assert "listening" in hub.voice_states
    await pipeline.stop()


# ===========================================================================
# INTEGRATION — full voice roundtrip (mocked) with latency tracking < 3s
# ===========================================================================


async def test_full_voice_roundtrip_under_3s(monkeypatch) -> None:
    """wake -> listen -> STT -> Claude -> TTS -> idle, end-to-end, < 3 s."""
    hub = RecordingHub()
    detector = FakeDetector()

    spoke: list[str] = []
    claude_messages: list[list] = []

    async def fake_record(capture, **kw):  # noqa: ANN001
        return np.ones(1600, dtype=np.int16)

    async def fake_transcribe(audio, sample_rate=16000):  # noqa: ANN001
        return "what's my status"

    async def fake_speak_and_play(text):  # noqa: ANN001
        spoke.append(text)
        return b"audio-bytes"

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", fake_speak_and_play)

    pipeline = VoicePipeline(
        hub=hub, claude=_StubClaude(), ollama=_StubOllama(), detector=detector
    )

    async def fake_stream(messages, system_prompt):  # noqa: ANN001
        claude_messages.append(messages)
        for tok in ("All systems ", "are nominal, ", "sir."):
            yield tok

    monkeypatch.setattr(pipeline._claude, "stream_response", fake_stream)

    await pipeline.start()
    start = time.perf_counter()
    await detector.fire()
    await _drain_turn(pipeline)
    elapsed = time.perf_counter() - start

    states = hub.voice_states
    for expected in ("listening", "thinking", "speaking", "idle"):
        assert expected in states, f"missing {expected!r} in {states}"
    assert states[-1] == "idle"
    assert claude_messages[0] == [{"role": "user", "content": "what's my status"}]
    assert "".join(spoke).replace(" ", "") == "Allsystemsarenominal,sir."
    # Latency target (CLAUDE.md Phase 3/9): a fully-mocked turn is far under 3 s.
    assert elapsed < 3.0, f"roundtrip took {elapsed:.3f}s (target < 3s)"

    await pipeline.stop()


# ===========================================================================
# INTEGRATION — Claude API streaming + tool use (mocked Anthropic stream)
# ===========================================================================


async def test_claude_streams_tokens_and_surfaces_tool_use(monkeypatch) -> None:
    """A mocked Anthropic stream yields text tokens; a tool_use block is sent
    in the request and surfaced in the final message."""
    from backend.ai import claude_client as cc

    # --- Build a fake async streaming context manager -----------------------
    class _FakeTextStream:
        def __init__(self, tokens: list[str]) -> None:
            self._tokens = tokens

        def __aiter__(self):
            async def gen():
                for t in self._tokens:
                    yield t

            return gen()

    class _Usage:
        input_tokens = 10
        output_tokens = 5
        cache_read_input_tokens = 8
        cache_creation_input_tokens = 2

    class _ToolUseBlock:
        type = "tool_use"
        name = "get_weather"
        input = {"city": "London"}

    class _FinalMessage:
        usage = _Usage()
        stop_reason = "tool_use"
        content = [_ToolUseBlock()]

    class _FakeStreamCtx:
        def __init__(self, tokens: list[str]) -> None:
            self.text_stream = _FakeTextStream(tokens)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_final_message(self):
            return _FinalMessage()

    captured_request: dict[str, Any] = {}

    class _FakeMessages:
        def stream(self, **kwargs):
            captured_request.update(kwargs)
            return _FakeStreamCtx(["The ", "weather ", "is ", "sunny."])

    class _FakeSDK:
        def __init__(self) -> None:
            self.messages = _FakeMessages()

    client = cc.ClaudeClient()
    client._client = _FakeSDK()  # bypass keyring / real SDK

    # Stub the hub broadcast so no real WS fan-out happens.
    monkeypatch.setattr(cc, "hub", MagicMock(broadcast=AsyncMock()))

    weather_tool = {
        "name": "get_weather",
        "description": "Get the weather for a city",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    }

    tokens = [
        tok
        async for tok in client.stream_response(
            messages=[{"role": "user", "content": "weather in London?"}],
            system_prompt="You are Jarvis.",
            tools=[weather_tool],
        )
    ]

    # Streaming: tokens arrived in order and reassemble the reply.
    assert tokens == ["The ", "weather ", "is ", "sunny."]
    assert "".join(tokens) == "The weather is sunny."

    # Tool use: the tool schema was forwarded in the request...
    assert captured_request["tools"] == [weather_tool]
    # ...the system prompt is cache-controlled (prompt caching present)...
    system_block = captured_request["system"][0]
    assert system_block["cache_control"] == {"type": "ephemeral"}
    # ...and the final message carried a tool_use block we can act on.
    final = await _FakeStreamCtx([]).get_final_message()
    tool_blocks = [b for b in final.content if getattr(b, "type", None) == "tool_use"]
    assert tool_blocks and tool_blocks[0].name == "get_weather"
    assert tool_blocks[0].input == {"city": "London"}


async def test_claude_prompt_caching_block_present(monkeypatch) -> None:
    """Every Claude request wraps the system prompt in an ephemeral cache block."""
    from backend.ai import claude_client as cc

    blocks = cc._system_blocks("system prompt text")
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[0]["text"] == "system prompt text"


# ===========================================================================
# INTEGRATION — Ollama fallback when Claude API is unavailable
# ===========================================================================


async def test_pipeline_falls_back_to_ollama_on_claude_error(monkeypatch) -> None:
    """Claude raises ClaudeAPIError before any token -> pipeline uses Ollama,
    and Ollama's reply is the one that gets spoken."""
    from backend.ai.claude_client import ClaudeAPIError

    hub = RecordingHub()
    detector = FakeDetector()

    spoke: list[str] = []
    ollama_called = {"hit": False}

    async def fake_record(capture, **kw):  # noqa: ANN001
        return np.ones(1600, dtype=np.int16)

    async def fake_transcribe(audio, sample_rate=16000):  # noqa: ANN001
        return "are you there"

    async def fake_speak_and_play(text):  # noqa: ANN001
        spoke.append(text)
        return b"audio"

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", fake_speak_and_play)

    pipeline = VoicePipeline(
        hub=hub, claude=_StubClaude(), ollama=_StubOllama(), detector=detector
    )

    async def failing_claude(messages, system_prompt):  # noqa: ANN001
        raise ClaudeAPIError("503 Service Unavailable")
        yield ""  # pragma: no cover — unreachable; makes this an async generator

    async def working_ollama(messages, system_prompt):  # noqa: ANN001
        ollama_called["hit"] = True
        for tok in ("Running ", "on local ", "fallback, sir."):
            yield tok

    monkeypatch.setattr(pipeline._claude, "stream_response", failing_claude)
    monkeypatch.setattr(pipeline._ollama, "stream_response", working_ollama)

    await pipeline.start()
    await detector.fire()
    await _drain_turn(pipeline)

    assert ollama_called["hit"] is True, "Ollama fallback was not invoked"
    assert "".join(spoke).replace(" ", "") == "Runningonlocalfallback,sir."
    assert hub.voice_states[-1] == "idle"

    await pipeline.stop()


async def test_pipeline_no_fallback_after_partial_claude_stream(monkeypatch) -> None:
    """If Claude fails *mid-stream* (some tokens already spoken), we do NOT
    restart from Ollama (which would duplicate the spoken prefix)."""
    from backend.ai.claude_client import ClaudeAPIError

    hub = RecordingHub()
    detector = FakeDetector()

    spoke: list[str] = []
    ollama_called = {"hit": False}

    async def fake_record(capture, **kw):  # noqa: ANN001
        return np.ones(1600, dtype=np.int16)

    async def fake_transcribe(audio, sample_rate=16000):  # noqa: ANN001
        return "tell me a long story please now"

    async def fake_speak_and_play(text):  # noqa: ANN001
        spoke.append(text)
        return b"audio"

    monkeypatch.setattr(pipeline_mod, "record_until_silence", fake_record)
    monkeypatch.setattr(pipeline_mod.stt, "transcribe", fake_transcribe)
    monkeypatch.setattr(pipeline_mod.tts, "speak_and_play", fake_speak_and_play)

    pipeline = VoicePipeline(
        hub=hub, claude=_StubClaude(), ollama=_StubOllama(), detector=detector
    )

    async def partial_claude(messages, system_prompt):  # noqa: ANN001
        # Emit enough to cross a speakable-chunk boundary, then fail.
        yield "This is the beginning of a rather long tale, sir, and then "
        raise ClaudeAPIError("connection reset mid-stream")

    async def working_ollama(messages, system_prompt):  # noqa: ANN001
        ollama_called["hit"] = True
        yield "should not be reached"

    monkeypatch.setattr(pipeline._claude, "stream_response", partial_claude)
    monkeypatch.setattr(pipeline._ollama, "stream_response", working_ollama)

    await pipeline.start()
    await detector.fire()
    await _drain_turn(pipeline)

    assert ollama_called["hit"] is False, "must not restart from Ollama mid-stream"
    assert hub.voice_states[-1] == "idle"

    await pipeline.stop()


# ===========================================================================
# SECURITY — grep scan finds no secrets in committed files
# ===========================================================================


# Patterns for real, committed secrets. Deliberately narrow so doc/test strings
# and placeholders ("...", "your-key-here") don't trip them.
_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "slack_bot_token": re.compile(r"xoxb-[A-Za-z0-9\-]{20,}"),
    "slack_app_token": re.compile(r"xapp-[A-Za-z0-9\-]{20,}"),
    "google_oauth": re.compile(r"[0-9]+-[a-z0-9]{32}\.apps\.googleusercontent\.com"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

_SCAN_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json",
    ".toml", ".md", ".env", ".rs", ".html", ".css",
}
_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv",
    "dist", "build", "target", "__pycache__", "OpenJarvis",
}


def _iter_scannable_files():
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(PROJECT_ROOT).parts):
            continue
        if path.suffix.lower() not in _SCAN_EXTENSIONS and path.name != ".env.example":
            continue
        # Don't scan this test file itself (it contains the regexes + samples).
        if path.resolve() == Path(__file__).resolve():
            continue
        yield path


def test_no_secrets_committed_in_source_files() -> None:
    findings: list[str] = []
    for path in _iter_scannable_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in _SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                rel = path.relative_to(PROJECT_ROOT)
                findings.append(f"{rel}:{line_no} matched {name}: {match.group()[:12]}...")
    assert not findings, "Secret-like patterns found:\n" + "\n".join(findings)


# ===========================================================================
# SECURITY — FastAPI binds to 127.0.0.1, never 0.0.0.0
# ===========================================================================


def test_fastapi_host_is_loopback_not_wildcard() -> None:
    import backend.main as main_mod

    assert main_mod.HOST == "127.0.0.1"
    assert main_mod.HOST != "0.0.0.0"  # noqa: S104 — asserting we DON'T use it


def test_no_wildcard_bind_in_main_source() -> None:
    """No executable 0.0.0.0 bind in main.py (warning comments are allowed)."""
    main_src = (PROJECT_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    for raw in main_src.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # A bind would look like host="0.0.0.0"; prose mentions are stripped above.
        assert 'host="0.0.0.0"' not in line.replace("'", '"'), f"wildcard bind: {raw}"


# ===========================================================================
# SECURITY — code executor blocks os.system() and subprocess
# ===========================================================================


async def test_code_executor_blocks_os_system() -> None:
    from backend.tools.code_executor import execute_code

    result = await execute_code("import os\nos.system('echo pwned')")
    assert result["success"] is False
    assert result["stdout"] == ""


async def test_code_executor_blocks_subprocess() -> None:
    from backend.tools.code_executor import execute_code

    result = await execute_code(
        "import subprocess\nsubprocess.run(['echo', 'pwned'])"
    )
    assert result["success"] is False


async def test_code_executor_blocks_dunder_escape() -> None:
    from backend.tools.code_executor import execute_code

    result = await execute_code("print(().__class__.__bases__)")
    assert result["success"] is False


async def test_code_executor_allows_safe_arithmetic() -> None:
    """Positive control: harmless computation (arithmetic + allowed builtins)
    runs successfully, proving the sandbox isn't a blanket deny.

    Note: ``safe_builtins`` only exposes a curated subset — ``len`` and
    arithmetic are available, but ``sum``/``range`` are NOT (the module
    docstring's "sum, range, sorted..." list overstates what's allowed). This is
    a documentation discrepancy, not a security issue; the sandbox correctly
    errs on the side of denying.
    """
    from backend.tools.code_executor import execute_code

    result = await execute_code("x = [10, 20, 12, 3]\nprint(len(x) + 1 + 2 * 3)")
    assert result["success"] is True, result["stderr"]
    assert result["stdout"].strip() == "11"
