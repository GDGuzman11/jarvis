---
name: phase12-memory-testing
description: How to test Phase 12 memory layer + 12B voice-pipeline memory wiring (recall/store/consolidate brackets, persona context, interrupt-no-store)
metadata:
  type: reference
---

Phase 12 memory testing for Jarvis. See also [[voice-pipeline-testing]].

**Architecture:** `backend/memory/manager.py::MemoryManager` is the sole memory interface. Three methods the voice pipeline calls: `recall(query, n_recent, n_semantic) -> RecallResult`, `store(text, role, channel) -> int`, `consolidate(user_text, reply, *, source, agent_id)`. `RecallResult` (dataclass) has `episodic_messages`, `semantic_facts`, `formatted_context`. Import from `backend.memory.manager`.

**12B wiring in `pipeline._stream_and_speak(transcript, *, channel="voice")`:**
- If `self._memory_manager is not None`: `recall(query=transcript, n_recent=10, n_semantic=3)` BEFORE Claude; `messages = recalled.episodic_messages + [{"role":"user","content":transcript}]` (recalled FIRST); `system_prompt = build_system_prompt(context=recalled.formatted_context)`.
- If None: `messages = [{"role":"user","content":transcript}]`, base prompt. No errors.
- AFTER the reply is fully streamed+spoken: `store(transcript, role="user")` then `store(response_text, role="jarvis")` (only if response non-empty), then `asyncio.create_task(consolidate(...))` — fire-and-forget, NEVER awaited.
- Interrupted turn: `_respond_with_interrupt` cancels `_stream_and_speak` mid-`async for`, so the post-stream store/consolidate block never runs → no partial reply persisted. This is the key 12B invariant.

**Test doubles (test_phase12b_verify.py):** `FakeMemoryManager` recording recall/store/consolidate calls; `consolidate_delay` (sleep 10s) + `consolidate_started` asyncio.Event proves fire-and-forget (turn returns <1s, event set). `_FakeClaude.stream_response` is an async gen that captures `list(messages)` (copy! pipeline reuses the list). Inject all four: `VoicePipeline(hub=, claude=, detector=, memory_manager=)`.

**GOTCHA (cost me a re-run):** `process_text`'s `finally` only sets state back to `idle` when `self._running` is True. `self._running` is only set by `await pipeline.start()`. If a test asserts `hub.states[-1] == "idle"` it MUST call `pipeline.start()` first (and `stop()` after), else the turn parks in `speaking`. Tests that only assert store/recall/Claude-message-content do NOT need start(). The interrupt-path test uses the real wake flow (`start()` + `detector.fire()` + drain `_turn_task`) so it's fine.

**Persona (`backend/ai/persona.py::build_system_prompt`):** context starting with `"# Current context"` is appended verbatim (no second header — for `MemoryManager.format_context` output); any other fragment gets wrapped under one `# Current context` header. `None`/blank returns base prompt unchanged (cache-stable). Test both: `.count("# Current context") == 1` in each case.

**Baseline as of 2026-06-05 (Phase 12B):** full `pytest backend/` = **109 passed / 1 failed (110 total)**. The 1 fail is the SAME pre-existing `test_phase9_verify.py::test_no_secrets_committed_in_source_files` — flags a Google OAuth *client id* (public, not a secret) in `get_gmail_token.py:9` and `docs/TEST_HISTORY.md:30`. Independent of memory work; owned by security-agent. asyncio_mode=auto (no decorators needed). Run: `.venv/Scripts/python.exe -m pytest backend/ -v`.
