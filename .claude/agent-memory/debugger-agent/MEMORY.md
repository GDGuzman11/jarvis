# Debugger Agent Memory Index

- [uv executable path](reference_uv_path.md) — uv not on PATH; run via full path C:\Users\User\.local\bin\uv.exe in PowerShell
- [Lifespan testing](reference_lifespan_testing.md) — ASGITransport does NOT run FastAPI lifespan; use Starlette TestClient as context manager to test init_db/startup
- [Voice pipeline testing](reference_voice_pipeline_testing.md) — how to mock-test VoicePipeline: injectable hub/claude/detector, patch stage fns in pipeline_mod namespace, drive _turn_task
