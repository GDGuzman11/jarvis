# Debugger Agent Memory Index

- [uv executable path](reference_uv_path.md) — uv not on PATH; run via full path C:\Users\User\.local\bin\uv.exe in PowerShell
- [Lifespan testing](reference_lifespan_testing.md) — ASGITransport does NOT run FastAPI lifespan; use Starlette TestClient as context manager to test init_db/startup
- [Voice pipeline testing](reference_voice_pipeline_testing.md) — mock-test VoicePipeline (injectable hub/claude/detector, patch pipeline_mod fns, drive _turn_task); OpenWakeWord swap = pipeline always starts, no key gating
- [Agent system testing](reference_agent_testing.md) — Phase 4 gotchas: status-flag-vs-broadcast race (wait on idle event not agent.status); create_task enforces agents FK; FakeHub + stub reasoner pattern
- [Integrations testing](reference_integrations_testing.md) — Phase 5 Slack/Gmail: inject _web/_service mocks, patch keystore where looked up (raise MissingCredentialError), stub database.log_audit, deep-chained Gmail mock
- [Tools testing](reference_tools_testing.md) — Phase 6: file_ops WORKSPACE_DIR fixed at import (set JARVIS_WORKSPACE + reload); execute_code async never-raises; registry.PermissionError shadows builtin; audit FK needs seeded agents
- [Phase 9 testing](reference_phase9_testing.md) — final gate suite test_phase9_verify.py; Ollama fallback now wired in pipeline._iter_reply (pre-token only); STT/TTS/Claude-tool mock recipes; sandbox lacks sum/range; UI+E2E deferred (no Rust, no Vitest)
