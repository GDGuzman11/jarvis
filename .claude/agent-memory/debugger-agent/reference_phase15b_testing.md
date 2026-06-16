---
name: phase15b-ws-wiring-testing
description: Phase 15B WebSocket event wiring (tool_call/comms/tool_permissions/shutdown) — contract-match recipe, secret scrubbing, fire-and-forget emit safety
metadata:
  type: reference
---

Phase 15B closed the WS contract drift (frontend handled 9 event types, backend emitted 6). Verified 2026-06-16, suite 154/154, `pnpm build` clean. Test file: `backend/test_phase15b_verify.py`.

**Contract-match is the whole point** — verify backend wire shape == frontend consumer field-for-field, including the `type` string. Three newly-wired events all matched:
- `tool_call`: `ToolCall` (events.py) {tool_name, agent_id, args, result, type, timestamp} == frontend `ToolCallEvent` (types.ts) → websocket.ts dispatch → store `applyToolCall` (id = `tool_name-agent_id-timestamp`).
- `comms`: `CommsEvent` {slack, gmail, type, timestamp}. Frontend `CommsEvent` has NO timestamp field — harmless (ignored). Slack snapshot keys `{id, sender, channel, text, unread, timestamp}` built in `slack_client._broadcast_comms`; Gmail `{id, sender, subject, snippet, unread, timestamp}` in `gmail_client._broadcast_comms` — both map internal `{user/from, ts/date}` → frontend names. websocket.ts uses `if(event.slack)/if(event.gmail)`; backend sends the unused side as `None`→JSON `null` (falsy) so the guard correctly skips.
- `tool_permissions`: `ToolPermissionsEvent` {permissions: dict[str,list[str]], tools: list, type, timestamp} == frontend; store `setPermissions(permissions, tools)`.

**Secret scrubbing (registry.py)**: `_scrub_args` redacts arg keys matching `_SECRET_KEY_HINTS` (token/secret/password/passwd/credential/authorization/api_key/apikey/access_key/private_key) → `***redacted***`, truncates strings to `_PREVIEW_LIMIT=200`; `_preview_result` JSON/str-renders + truncates to 200. Backed by `test_tool_call_redacts_secret_args_and_truncates` + `test_tool_call_result_preview_is_capped`. Note assertions use `<=201` (200 + 1-char ellipsis "…").

**Emit safety patterns**:
- `_broadcast_tool_call` is awaited inside `call_tool` AFTER audit, wrapped in try/except (swallowed) — broadcast failure never breaks the tool call. hub None → return.
- `grant`/`revoke` are SYNC → `_emit_permissions` schedules `loop.create_task(hub.broadcast(...))`; wraps `asyncio.get_running_loop()` in try/except RuntimeError so no-loop (unit test) = silent no-op. Test `test_grant_without_running_loop_is_safe` asserts no events when no loop. To assert grant/revoke broadcasts, `await asyncio.sleep(0)` to let the scheduled task run.
- Startup matrix push: `await hub.broadcast(tool_registry.permissions_event())` in lifespan. On-connect push: WS handler sends `serialize(registry.permissions_event())` per connection (try/except) so late-joining Tools window never sees a skeleton.

**shutdown trace**: AnimationWindow.tsx ⏻ → `fetch POST http://127.0.0.1:8000/api/shutdown` → `shutdown_endpoint` `await hub.broadcast(ShutdownEvent())` then SIGINT after 0.8s → frontend websocket.ts `case "shutdown"` disconnects + closes Tauri window. `ShutdownEvent` = `{type:"shutdown", timestamp}`, matches frontend.
