---
name: phase16a-testing
description: Phase 16A memory foundation+safety verification — sanitization lives in manager.format_context (not persona), last_recalled_at + quality columns
metadata:
  type: reference
---

Phase 16A (Memory Intelligence: Foundation + Safety) verified at 161/161 (was 154 + 7 new in `backend/test_phase16a_verify.py`).

Key locations / facts (verify before relying):
- **Sanitization is in `backend/memory/manager.py`**, NOT persona.py. `_CONTROL_CHARS_RE = [\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]` (preserves \t \n \r + Unicode); `_sanitize_fact_text()`; `format_context()` wraps facts in `<untrusted_memory>…</untrusted_memory>`. This is the ONLY path semantic_facts reach the prompt — both call sites (`pipeline.py:484`, `base_agent.py:366`) consume `recalled.formatted_context` via `build_system_prompt()`. No raw bypass.
- `persona.py` is at `backend/ai/persona.py` (NOT backend/agents/). `build_system_prompt(context=...)` appends format_context output verbatim (dedups the `# Current context` header).
- **last_recalled_at**: `database.mark_facts_recalled(fact_ids)` does PK UPDATE via executemany; called from `manager.recall()` in its OWN try/except so a stamp failure never drops recalled facts. No-op on empty list.
- **Quality columns** added by `_migrate_memory_facts_quality_columns()` in `database.py` (called from init_db): confidence FLOAT DEFAULT 0.8, created_by TEXT DEFAULT 'system', source_turn_id INTEGER (nullable), access_count INTEGER DEFAULT 0. Check-before-ALTER via PRAGMA table_info → idempotent across restarts. SQLite ADD COLUMN w/ DEFAULT auto-backfills existing rows.
- **access_count increment correctly DEFERRED to 16B** — column exists, increment not wired (intended scope, not a bug).

**How to apply:** When verifying 16B re-ranking, expect recency (last_recalled_at) + frequency (access_count) signals to now have live data. The injection-boundary wrapper means any 16B/16C test that inspects the rendered prompt must account for the `<untrusted_memory>` fence around facts.
