---
name: voice-pipeline-testing
description: How to unit-test VoicePipeline with mocks (no mic/keys/hardware) — injection points and stage-mock namespaces
metadata:
  type: reference
---

Testing `backend/voice/pipeline.py::VoicePipeline` without hardware:

- Construct with `VoicePipeline(hub=fake, claude=fake, detector=fake)`. All three are injectable kwargs.
- The pipeline reads `detector._capture` in `__init__`, calls `detector.on_detected(cb)`, and in `start()` calls `detector.start()` then reads `detector.is_enabled`. A fake detector needs those plus a `fire()` helper that `await`s the stored callback to simulate a wake-word detection.
- Mock the stage functions in the **pipeline module namespace**, not their home modules: `monkeypatch.setattr(pipeline_mod, "record_until_silence", ...)`, `pipeline_mod.stt.transcribe`, `pipeline_mod.tts.speak_and_play`. Patch Claude via `pipeline._claude.stream_response` (must be an async generator).
- `_on_wake` runs the turn in a created task stored at `pipeline._turn_task`; await it (with timeout) to drain a turn, then `await asyncio.sleep(0)` so the done-callback `_clear` runs.
- Interrupt path: `stt.transcribe` is called for BOTH the utterance and each interrupt window. Return the real prompt on call 1, then "stop" thereafter. Patch `VoicePipeline._record_interrupt_window` to return non-empty audio fast. Use a slow multi-token `stream_response` so the interrupt wins the `asyncio.wait(FIRST_COMPLETED)` race.
- Lifespan: as of 2026-06-03 the pipeline is NO LONGER gated on any API key. Porcupine was swapped for OpenWakeWord (Apache 2.0, fully local, no key); `pvporcupine` removed, `openwakeword>=0.6.0` added. `backend/main.py` ALWAYS constructs `app.state.voice_pipeline` (non-None) on startup. The old `keystore.PORCUPINE_ACCESS_KEY` and `get/set_porcupine_access_key` are gone from `keystore.py`; no `PORCUPINE_ACCESS_KEY` in `.env.example`. Test lifespan via Starlette `TestClient` as a context manager (see [[lifespan-testing]]); stub `init_db`/`VectorStore`/`VoicePipeline` to avoid real DB/audio side effects, and assert `app.state.voice_pipeline is not None` (test: `test_lifespan_always_starts_pipeline`).
- Wake-word detector now uses `from openwakeword.model import Model`. Stage-mock namespace for tests is unchanged; the detector test `test_oww_unavailable_does_not_raise` covers the missing-model case.
