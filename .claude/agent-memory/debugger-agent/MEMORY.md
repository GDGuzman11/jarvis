# Debugger Agent Memory Index

- [uv executable path](reference_uv_path.md) — uv not on PATH; run via full path C:\Users\User\.local\bin\uv.exe in PowerShell
- [Lifespan testing](reference_lifespan_testing.md) — ASGITransport does NOT run FastAPI lifespan; use Starlette TestClient as context manager to test init_db/startup
- [Voice pipeline testing](reference_voice_pipeline_testing.md) — mock-test VoicePipeline (injectable hub/claude/detector, patch pipeline_mod fns, drive _turn_task); OpenWakeWord swap = pipeline always starts, no key gating
- [Agent system testing](reference_agent_testing.md) — Phase 4 gotchas: status-flag-vs-broadcast race (wait on idle event not agent.status); create_task enforces agents FK; FakeHub + stub reasoner pattern
