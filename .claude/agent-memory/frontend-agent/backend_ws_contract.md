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

CONFIRMED (Phase 13A, 2026-06-06): the REST agent-task endpoints
`POST /api/agents/{slug}/task` (body `{goal}`) and `GET /api/agents/{slug}/tasks`
are keyed on PUBLIC DISPLAY SLUGS (atlas/ben/kado/sentinel/vega/quill), NOT the
internal agent_ids the WS store uses (production_lead/frontend/backend/security/
marketing/content). Frontend converts via `AGENT_ID_TO_SLUG` in
`frontend/src/lib/api.ts` (mirrors backend `_PUBLIC_TO_AGENT_ID` in
`backend/main.py`). Map off the stable internal id — the display NAME is
user-editable via rename. `/api/agents/{id}/rename`, by contrast, takes the
internal id directly. POST returns {task_id, agent_id, status:"queued"};
404 unknown slug, 400 empty goal.

AUDIT (2026-06-16): contract drift still present and additional gaps found:
- `tool_call` Event class exists in events.py + is exported, but is broadcast
  NOWHERE in backend (registry.py only LOGS, never `hub.broadcast`). Reasoning
  window's tool-call cards are permanently empty. Frontend dispatch + store
  result-matching are already correct — backend just needs emit sites.
- `comms` and `tool_permissions` STILL have no backend event type (EventType
  literal = agent_update/token/tool_call/voice_state/audio_level/metrics only).
  Comms + Tools windows show only hardcoded INITIAL_PERMISSIONS / empty states.
- `/ws` endpoint (main.py:~736) still only DRAINS inbound frames
  (`await websocket.receive_text()` discarded). Every `sendCommand(...)` from UI
  (Reply/Compose/permission toggles) is a silent no-op; sendCommand still
  returns true.
- voice_state mismatch: backend VoiceState includes "error" (crash-recovery
  parked state); frontend types.ts VoiceState union OMITS it and AnimationWindow
  STATE_LABEL has no "error" key — hard voice fault renders as idle.
- `shutdown` IS handled correctly: broadcast as raw dict from POST /api/shutdown.
- Bundle: AnimationWindow chunk ~882KB (Three.js) but ALREADY code-split via
  React.lazy in App.tsx; only the animation renderer downloads it. Not a cross-
  window cost — deprioritize.
- Dead frontend code: StreamViewer.tsx (imported nowhere); store streamingText/
  clearStream unread, appendToken still double-called on token path.

CONFIRMED (Phase 11C, 2026-06-04): `metrics` is now live from the backend.
Shape: { type:"metrics", cost_usd, latency_ms, model, input_tokens,
output_tokens, cache_read_tokens, cache_write_tokens } (+ timestamp). The
frontend store accumulates a `sessionCostUsd` running total from per-turn
`cost_usd`. ReasoningWindow is now a chat UI (`chatHistory` + `addUserMessage`
+ `appendJarvisToken`); the old `streamingText`/`appendToken` path is kept for
back-compat but `StreamViewer.tsx` is no longer rendered.
