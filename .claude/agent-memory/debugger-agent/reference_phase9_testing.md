---
name: phase9-testing
description: Phase 9 final-gate suite — what it adds vs per-phase suites, the Ollama fallback wiring, and deferred UI/E2E items
metadata:
  type: reference
---

Phase 9 (Testing & Verification) consolidated suite: `backend/test_phase9_verify.py` (19 cases). It does NOT duplicate Phase 3/4/5/6 suites — the full `pytest backend/` is 65 tests, all green. Phase 9 only adds the checklist gaps no earlier suite covered:

- **STT accuracy**: patch `stt._load_model` to return a fake model whose `transcribe(audio_f32, language=...)` returns `([Segment(text), ...], info)`. The pipeline hands Whisper float32 in [-1,1] — assert dtype + max_abs<=1 to prove int16→float32 normalisation ran. `language="en"` is passed.
- **TTS bytes**: patch `tts._make_client` (return a MagicMock whose `.text_to_speech.convert` returns an iterator of byte chunks) AND `tts._resolve_voice_id`. `speak()` joins chunks → non-zero bytes. Missing client → `_make_client` returns None → `b""`.
- **Claude streaming + tool_use**: set `client._client` to a fake SDK (bypass keyring). The SDK call is `client.messages.stream(**req)` returning an async-CM whose `.text_stream` is async-iterable and `.get_final_message()` returns usage + `content=[tool_use_block]`. Patch `claude_client.hub` to a MagicMock(broadcast=AsyncMock()). Assert `req["tools"]` forwarded and `req["system"][0]["cache_control"]=={"type":"ephemeral"}` (prompt caching).

**Ollama fallback (NEW WIRING).** Before Phase 9, `pipeline._iter_reply` caught `ClaudeAPIError` and yielded nothing (no fallback). Phase 9 wired it: `VoicePipeline.__init__` now takes an injectable `ollama=` kwarg (defaults to `OllamaClient()`), and `_iter_reply` falls back to `self._ollama.stream_response` ONLY when Claude fails *before yielding any token* (a `produced_any` flag). A mid-stream failure does NOT restart from Ollama (would duplicate the already-spoken prefix). Test both paths. Inject `claude=`/`ollama=` stubs and `monkeypatch.setattr(pipeline._claude, "stream_response", ...)`.

**Security tests** live here too: regex grep for `sk-ant-`/`xoxb-`/`xapp-`/Google-OAuth-client-id/`AKIA…`/PEM blocks across source (skip OpenJarvis/node_modules/.venv/dist; skip the test file itself or its own regexes match); `main.HOST=="127.0.0.1"` + no `host="0.0.0.0"` executable line; code_executor blocks os.system/subprocess/dunder.

**code_executor gotcha:** RestrictedPython `safe_builtins` does NOT expose `sum`/`range`/`sorted` — they raise NameError despite the module docstring claiming they're allowed. For a positive-control "safe code runs" test use `len(...)` + arithmetic, not `sum(range(...))`. (Logged as a minor non-blocking docstring discrepancy.)

**DEFERRED (cannot run yet):** 4 live-UI items (5 windows open, WS<2s, orb colour idle/thinking/speaking, agent-card live updates) + 2 true voice E2E — all need the native Tauri app (Rust/cargo not installed) and/or a mic + live keys. `frontend/` has NO Vitest harness (only dev/build/preview/tauri scripts) — adding one is a Phase 10 task. See [[voice-pipeline-testing]] for the pipeline mock pattern, [[uv-path]] for venv python.
