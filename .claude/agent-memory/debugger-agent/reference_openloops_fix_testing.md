---
name: openloops-fix-testing
description: Open-loop (reminder) resolution + randomized greeting fix — test patterns, prefilter-gating, scripted-extractor recipe
metadata:
  type: reference
---

Open-loop "reminders" bug fix verification (post Phase 16D). New suite `backend/test_openloops_fix_verify.py` (14 tests → baseline 196→210).

- **DB resolve**: `database.resolve_open_loops_async(db_path, *, ids=None, status='resolved')` — `UPDATE open_loops SET status=?, resolved_at=datetime('now')` WHERE id IN(...) (or `WHERE status='open'` when ids=None). Validates status ∈ {resolved,dismissed} (else ValueError), empty `ids=[]` → no-op return 0, returns `cursor.rowcount`.
- **LLM open-loop judge**: `LLMExtractor.extract_open_loops(user_text, reply, open_loops)` (16C extractor extended) — Haiku(`claude-haiku-4-5`)→phi3.5→[] never-raises; given existing loops WITH ids so RESOLVE references `target_id`. `OpenLoopOp(action, description, target_id, confidence)` dataclass. `_normalise_open_loops` drops CREATE w/o desc, RESOLVE w/o id, and NOOP entries.
- **Prod path gating** (`manager._process_open_loops`): if extractor has `extract_open_loops` → keyword `evaluator.open_loop_prefilter(text, has_open_loops)` gates LLM (creation trigger always True; resolution hint only when loops exist) → else `_apply_open_loop_ops`. Brittle keyword `evaluator.detect_open_loops` demoted to FALLBACK-only (no LLM judge). Whole thing in its own try/except (off hot path; called from fire-and-forget `consolidate`).
- **Greeting**: `main._GREETING_ANGLES` (8) + `_greeting_instruction()`=`random.choice(...)+" Keep it under 40 words."`; `_compose_greeting_text(mgr, client, *, context, fallback)` factored out for testing (no WS/audio/API). `_append_open_loops` surfaces only status='open' older_than_hours=12.
- **Test recipe**: `_ScriptedExtractor(mode)` fake (create/resolve_first/noop) records `loop_calls`; `_EchoClient` echoes instruction tokens; VectorStore=MagicMock(`__len__`=0) so no embedding-model load. No real Claude/Ollama instantiated → zero network. Idle "anymore" → prefilter gates (loop_calls==[]); "i need to…" fragment → reaches LLM, NOOP, nothing stored.
- Scope: backend-only (main.py, memory/{database,evaluator,extractor,manager}.py), no new pip deps.
