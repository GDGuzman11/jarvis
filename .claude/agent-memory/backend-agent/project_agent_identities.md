---
name: agent-identities
description: The display names chosen for the four previously-TBD background agents (Phase 4)
metadata:
  type: project
---

The six background agents and their display names (CLAUDE.md left four as TBD; these were chosen during Phase 4 implementation):
- Production Lead = **Atlas** (agent_id `production_lead`)
- Frontend = **Ben** (agent_id `frontend`) — fixed by spec
- Backend = **Kado** (agent_id `backend`) — fixed by spec
- Security = **Sentinel** (agent_id `security`)
- Marketing = **Vega** (agent_id `marketing`)
- Content Creator = **Quill** (agent_id `content`)

**Why:** CLAUDE.md only pinned Ben and Kado; the orchestrator, security, marketing, and content names were unspecified, so I assigned thematic names to keep the Agents window readable.

**How to apply:** Reuse these exact names if a future task references an agent by name, and use them when the frontend Agents window (Phase 7) needs labels. The Production Lead's classifier routes to these `agent_id` slugs, not the display names.
