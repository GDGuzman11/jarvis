---
name: phase16b-testing
description: Phase 16B multi-signal recall re-ranking verification — composite scoring, signal isolation, access_count write
metadata:
  type: reference
---

Phase 16B (test_phase16b_verify.py, 9 tests; baseline 170/170) — multi-signal recall re-ranking in `backend/memory/manager.py`.

- Composite = weighted sum of 5 named constants W_SEMANTIC .40 / W_KEYWORD .20 / W_RECENCY .20 / W_IMPORTANCE .10 / W_FREQUENCY .10 (sum 1.0). `_rank_candidates()` sorts by (-composite, -semantic, fact_id asc) = deterministic.
- FAISS = IndexFlatIP over normalize_embeddings=True vectors (vector_store.py:116,124) = cosine [-1,1], higher=better. `_semantic_score` clamps to [0,1]; NOT inverted (no L2-distance bug).
- Recency `1/(1+days_since)`; NULL fallback last_recalled_at→created_at→_UNKNOWN_AGE_DAYS(3650). Frequency `log(ac+1)/max_log`, max_log<=0 guard returns 0.
- MIN_SEMANTIC_SCORE (0.25) stays a PRE-filter (hits filtered before pool builds), so high-importance sub-threshold noise can't be re-ranked in.
- Signal-isolation test pattern: give both facts EQUAL FAISS score (0.80) + neutral non-matching query ("zzqueryxx") + pin all other columns equal via direct UPDATE, leave only the signal-under-test varying. Tests genuinely isolate recency/importance/frequency/keyword.
- `mark_facts_recalled()` (database.py:779) = single combined executemany UPDATE: last_recalled_at=datetime('now') AND access_count=COALESCE(access_count,0)+1, keyed by PK. Called ONLY on ranked[:n_semantic] returned ids (not whole pool), wrapped in try/except in recall() so a write failure never drops already-appended facts.
- DB cost bounded: per recall adds 2 queries (batched get_memory_facts_by_ids `IN(...)` + one FTS search_memory_facts) + the mark write. No per-candidate loop — scoring loop is pure Python over pre-fetched meta_by_id. Pool K = max(n_semantic, CANDIDATE_POOL_K=20).
- semantic_facts dicts gained additive `composite_score` key; callers (pipeline.py:484-492, base_agent.py:366-376) only read episodic_messages + formatted_context, so shape stays compatible.
