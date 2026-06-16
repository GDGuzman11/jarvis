---
name: phase16c-llm-extraction-testing
description: Phase 16C LLM-driven memory extraction — test recipes, fallback chain, dedup/valid_to gotchas, baseline 170→183
metadata:
  type: reference
---

Phase 16C — LLM-driven fact extraction (extractor.py + manager._apply_extractions). Baseline 170 → **183 passed** (13 new in test_phase16c_verify.py).

- **Model strategy**: EXTRACTION_MODEL = `claude-haiku-4-5` (extractor.py:46, pinned constant); Ollama DEFAULT_MODEL = `phi3.5` (ollama_client.py:43). Claude default stays `claude-opus-4-7` — extractor passes per-call `model=` override to `ClaudeClient.complete(messages, system, *, model, max_tokens)`.
- **Fallback chain** (extractor.extract): Claude Haiku → (raise OR `_extract_json_array`→None) phi3.5 (`ollama.complete(..., fmt="json")`) → (fail/unparseable) `[]`. Never raises; wrapped in broad try/except + log.warning. Tests: _RaisingClaude→ollama called; _GarbageClaude (no JSON)→ollama; both fail→`[]`.
- **Off hot path**: consolidate is fire-and-forget `asyncio.create_task` at BOTH call sites — pipeline.py:531 (after reply spoken) and base_agent.py:418. consolidate() itself wrapped in try/except → never breaks a turn.
- **Pre-filter gate**: evaluator.score < threshold (0.65) returns BEFORE `self._extractor.extract()` (manager.py:426). Test uses real MemoryEvaluator + _QueueExtractor, asserts `extractor.calls == []`.
- **Dedup**: UPDATE/DELETE call `_find_similar_fact_id` → FAISS top-1, acts only if score ≥ `UPDATE_SIMILARITY_THRESHOLD=0.85` (manager.py:90); else UPDATE falls through to ADD, DELETE is no-op. `_FakeVectorStore(search_score=0.9)` returns most-recent entry to drive UPDATE path. Paraphrase + contradiction tests → 1 fact.
- **valid_to (soft-delete)**: `invalidate_memory_fact` stamps `valid_to=datetime('now')`; recall excludes via `get_memory_facts_by_ids` returning valid_to and manager.py:831 `if meta.get("valid_to"): continue`. DELETE→recall-excluded test passes.
- **Provenance**: `_apply_extractions` passes op.source→created_by ('user'/'inference') + op.confidence into `save_memory_fact`/`update_memory_fact`. Test asserts both persisted.
- **Opt-in**: extractor defaults None → pre-16C tests use rule path, no LLM. Prod wires `LLMExtractor()` in main.py:391.
- **Migration idempotent**: `_migrate_memory_facts_quality_columns` (database.py:348, called from init_db:251) PRAGMA table_info check-before-ALTER; adds confidence/created_by/source_turn_id/access_count/valid_to.
- **FTS sync**: `memory_facts_fts_update` trigger (database.py:193) AFTER UPDATE OF content,category keeps keyword index synced after in-place UPDATE.
- **Phase 16D TODOs flagged in code (not defects)**: FAISS vector NOT tombstoned on UPDATE/DELETE — stale vector lingers (manager.py:594, database.py:809/854); full bi-temporal write-policy machinery (valid_from/strength/half_life/superseded_by/write_policy) deferred to 16D.
