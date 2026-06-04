---
name: phase11c-metrics-testing
description: Phase 11C MetricsEvent/_compute_cost — cost-math units, _compute_cost arg order, and the brief's 1000x cost typo
metadata:
  type: reference
---

Phase 11C added cost/latency metrics: `MetricsEvent` in `backend/events.py` (type "metrics", added to `EventType` literal + `__all__`) and `_compute_cost` in `backend/ai/claude_client.py`. Verified by `backend/test_phase11c_metrics_verify.py` (11 cases).

**Cost units (Claude Opus 4.7 price card, USD per MILLION tokens):** input $15, output $75, cache-write $3.75, cache-read $1.50. So `_compute_cost(1000,1000,0,0)` = 1000/1e6 * 15 + 1000/1e6 * 75 = 0.015 + 0.075 = **$0.09** (NOT $0.00009). The "$0.00009" in the verification brief was a 1000x typo — the implementation is correct. The `1M+1M → exactly $90.00` case is the reliable anchor for confirming scaling.

**`_compute_cost` arg order is `(input, output, cache_write, cache_read)`** — cache_write BEFORE cache_read. The claude_client call site (`stream_response` finally/clean-turn block) passes them in that order. Easy to flip when writing tests; double-check against the signature, not intuition.

**Why:** When a verification brief states an expected numeric value, derive it independently from the price card before trusting it. Here the brief's own inline arithmetic contradicted its stated result.

**How to apply:** For any future cost/pricing test, compute from per-million rates and use the $90-at-1M anchor. When testing `_compute_cost`, respect the (input, output, cache_write, cache_read) order.
