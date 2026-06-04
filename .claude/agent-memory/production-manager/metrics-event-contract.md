---
name: metrics-event-contract
description: The MetricsEvent WebSocket contract for Phase 11C live cost+latency — backend emits, frontend consumes
metadata:
  type: project
---

Phase 11C "Live cost + latency display" requires a backend→frontend `MetricsEvent` broadcast.

Contract (per CLAUDE.md line 401):
`{"type":"metrics","cost_usd":X,"latency_ms":Y,"model":"...","input_tokens":N,"output_tokens":N}`

- Emitted from `backend/ai/claude_client.py` after stream completes (it already logs cache_read,
  cache_write, input_tokens, output_tokens).
- Pricing (2026): Opus 4.7 input $15/M, output $75/M, cache_read $1.50/M, cache_write $3.75/M.
- Latency = time from first token request to `is_final`.
- Frontend `store.ts` already has `metrics.cost_usd` and `metrics.latency_ms` — needs backend to populate
  + websocket.ts `case "metrics"`. Show per-turn cost AND running session total.

**Why:** This is the cross-agent dependency in Phase 11C — backend MetricsEvent must exist before the
frontend display can consume it. Defines the order: backend-agent first, then frontend-agent.

**How to apply:** When delegating the cost/latency task, give backend-agent this exact event shape so the
frontend doesn't guess. The frontend store/types were forward-declared in Phase 7.
