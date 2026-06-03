---
name: wake-word-openwakeword
description: Wake word detection uses openWakeWord (not Porcupine) — fully local, no API key, ONNX path on Windows
metadata:
  type: project
---

The Jarvis wake-word stage uses **openWakeWord** with the built-in `hey_jarvis` model, NOT Porcupine. Swap happened 2026-06-03.

**Why:** openWakeWord is Apache 2.0, fully local, and needs no API key — removes the Porcupine/Picovoice access-key dependency entirely. Simplifies setup (no key in keystore, no `.env` line) and security surface.

**How to apply:**
- `backend/voice/wake_word.py` loads `Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")`. On Windows the **ONNX** inference path is required — `tflite-runtime` has no Python 3.12 wheels, so `pyproject.toml` has a `[tool.uv] override-dependencies` entry restricting tflite-runtime to Linux+py<3.12.
- Frame format for `model.predict()`: 16 kHz mono int16, `FRAME_LENGTH=1280` samples (80 ms). Detection threshold constant `WAKE_THRESHOLD=0.5`.
- `keystore.py` has NO porcupine getter/setter — do not reintroduce one.
- `backend/main.py` lifespan starts the voice pipeline **unconditionally** (no credential gate) because no wake-word key is needed; the detector disables itself gracefully if the openwakeword library is absent (logs `wake_word_disabled_no_openwakeword`, sets `is_enabled=False`).
- Stale note: debugger-agent's `reference_voice_pipeline_testing.md` still claims main.py gates on `keystore.PORCUPINE_ACCESS_KEY` — that gate no longer exists; flag to debugger if it resurfaces.
