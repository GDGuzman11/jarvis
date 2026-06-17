---
name: memcapture-testing
description: Memory Capture Overhaul verification — light chatter-skip gate, domain≠category, confirm-when-unsure bands, MemoryConfirmEvent
metadata:
  type: reference
---

Memory Capture Overhaul (test_memcapture_verify.py, offline: FakeHub + _FakeVectorStore + _QueueExtractor, real MemoryEvaluator, no network). Baseline 221→233.

- **Gate**: hard `score<0.65→skip` REPLACED by light chatter-skip in `manager.consolidate` — `evaluator.is_chatter(user,reply)` (all words in `_CHATTER_TOKENS` & ≤max words) + `is_explicit_memory_request` (forces auto-store, bypasses confirm). Substantive turns reach LLM extractor. Rule-fallback path STILL keeps the score gate (only fires when extractor empty).
- **domain vs category (SAFETY)**: extractor `Extraction.category` = 10-cat DISPLAY DOMAIN (personal/atlas/ben/kado/sentinel/vega/quill/project/people/general, `_normalise` coerces unknown→general). Stored in NEW `memory_facts.domain` column (idempotent ALTER in `_MEMORY_FACTS_NEW_COLUMNS`). Signal `category` UNCHANGED → still drives 16D `_choose_write_policy` + `category` column. In manager.py `domain` only touches WRITE paths, never `_rank_candidates`/recall/`_choose_write_policy`. Graph node: `domain or _fallback_domain(category)` (`_CATEGORY_TO_DOMAIN_FALLBACK` in main.py).
- **Confirm bands** (manager.py): `AUTO_STORE_CONFIDENCE=0.70`/`CONFIRM_LOW_CONFIDENCE=0.45`. ADD ≥0.70 or explicit→`_add_fact`+memory_update; 0.45–0.70→`_stash_pending_confirm` (in-RAM `_pending_confirms`, TTL 600s sweep)+MemoryConfirmEvent, NOT stored; <0.45 drop. UPDATE/DELETE auto-apply (confirm is ADD-only). `confirm_pending(id,"store"/"discard")` returns stored/discarded/None(404).
- **Endpoint**: `POST /api/memory/confirm {confirm_id,decision}` Body(embed) → 400 bad decision, 503 no mgr, 404 unknown. `MemoryConfirmEvent{confirm_id,fact,category(=domain),subject?,type,timestamp}` in events.py (+EventType +__all__).
- **16C fix (the test I finished)**: test_phase16c_verify.py::test_created_by_set_user_vs_inference 2nd extraction confidence 0.6→0.8 so it auto-stores above the new confirm band (mid-conf would now pend).
- **Frontend contract**: types.ts MemoryConfirmEvent matches field-for-field; api.confirmMemory POSTs {confirm_id,decision}; websocket memory_confirm→addPendingConfirm; memoryStyle.ts DOMAIN_HEX locked palette reused by Neurons(nodeStyle/domainColorRgb)+ReasoningWindow badge(domainColorCss)+MemoryWindow legend(DOMAIN_ORDER/LABELS). No cyan #00d4ff/jarsis- in touched files; orb untouched (additive change set).
