---
name: ws-contract-drift
description: Verified mismatches between frontend WS message handlers and backend emitters (audit 2026-06-16)
metadata:
  type: project
---

The frontend WS client (`frontend/src/lib/websocket.ts`) handles 9 inbound `type`s but the backend emits fewer. Verified 2026-06-16 by reading both sides.

- Frontend handles: `agent_update, token, tool_call, voice_state, audio_level, metrics, comms, tool_permissions, shutdown`.
- Backend `backend/events.py` BROADCAST_EVENTS defines: `agent_update, token, tool_call, voice_state, audio_level, metrics` only.
- **Orphaned (handled by frontend, never broadcast by backend): `comms`, `tool_permissions`, `shutdown`.** Communications (Win 3) and Tools-permission (Win 5) windows therefore render skeletons, not live data.
- **`tool_call` is a half-wire:** the `ToolCallEvent` class exists in events.py, but the only runtime reference (`backend/tools/registry.py:259`) is a `log_audit(..., "tool_call", ...)` write — NOT a hub broadcast. So Reasoning-window (Win 2) tool-call cards never receive live data.

**Why:** These windows were UI-forward-declared in Phase 7 with store fields, but the backend broadcast side was never wired. CLAUDE.md marks the relevant phases complete, hiding the gap.

**How to apply:** When a "Phase 16" or polish task touches Comms/Tools/Reasoning live data, the fix is BACKEND work (Kado): emit `comms` on Slack/Gmail events, emit `tool_permissions` on registry change, and broadcast `tool_call` from registry.py alongside the existing audit write. Verify by reading [[build-run-commands]] gates after.
