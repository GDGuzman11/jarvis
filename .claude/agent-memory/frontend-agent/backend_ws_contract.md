---
name: backend-ws-contract
description: Exact backend WebSocket event shapes and the 6 agent ids/names the frontend store must mirror
metadata:
  type: project
---

The frontend store/websocket must stay in lockstep with `backend/events.py`
(the single source of truth). As of Phase 7 the hub at ws://127.0.0.1:8000/ws
broadcasts these 4 event types (each has `type` + ISO `timestamp`):

- `agent_update`: { agent_id, agent_name, status, current_task }
  status ∈ idle | working | error | offline
- `token`: { content, model, is_final }
- `tool_call`: { tool_name, agent_id, args, result }  (result null while in flight)
- `voice_state`: { state }  state ∈ idle | listening | thinking | speaking

The 6 agents (id → name → role):
production_lead→Atlas (Production Lead), frontend→Ben, backend→Kado,
security→Sentinel, marketing→Vega, content→Quill.

12 tools registered in `backend/tools/wiring.py`: web_search, browse_url,
read_file, write_file, list_files, execute_code, plus Slack/Gmail wrappers
(slack_send_message, slack_get_unread_mentions, gmail_get_inbox,
gmail_draft_email). Per-agent matrix = `DEFAULT_PERMISSIONS` in
`backend/tools/registry.py`.

**Why:** windows render nothing real without matching these; mismatched field
names silently drop data.

**How to apply:** Backend has NOT yet defined events for comms inbox payloads
or tool_permissions — the frontend forward-declares these (`comms`,
`tool_permissions`) and the WS endpoint currently only DRAINS inbound frames
(no command handling). When backend adds those, confirm field names match
`frontend/src/lib/types.ts` before assuming the UI is wired.

CONFIRMED (Phase 11C, 2026-06-04): `metrics` is now live from the backend.
Shape: { type:"metrics", cost_usd, latency_ms, model, input_tokens,
output_tokens, cache_read_tokens, cache_write_tokens } (+ timestamp). The
frontend store accumulates a `sessionCostUsd` running total from per-turn
`cost_usd`. ReasoningWindow is now a chat UI (`chatHistory` + `addUserMessage`
+ `appendJarvisToken`); the old `streamingText`/`appendToken` path is kept for
back-compat but `StreamViewer.tsx` is no longer rendered.
