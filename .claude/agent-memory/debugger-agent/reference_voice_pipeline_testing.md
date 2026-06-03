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
- Lifespan gating: `backend/main.py` gates the pipeline on `keystore.has_credential(keystore.PORCUPINE_ACCESS_KEY)`. Test via Starlette `TestClient` as a context manager (see [[lifespan-testing]]); patch `main_mod.keystore.has_credential`, and stub `init_db`/`VectorStore`/`VoicePipeline` to avoid real DB/audio side effects.
