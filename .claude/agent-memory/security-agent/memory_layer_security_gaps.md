---
name: memory-layer-security-gaps
description: Two latent memory-subsystem security gaps in Jarvis (unsanitized recalled-prompt injection, backup auto-includes whole DB) a future audit should already know
metadata:
  type: project
---

Latent security characteristics of Jarvis's Phase 12 memory subsystem, found
during a 2026-06-14 review of a proposed "brain" memory-architecture upgrade.
These are NOT new findings to re-investigate — they are known properties.

**Gap A — recalled memory is injected into the Claude system prompt UNSANITIZED.**
`backend/memory/manager.py recall()` -> `format_context()` (~line 498) writes
`memory_facts.content` and raw `conversations.content` verbatim into the system
prompt under `## What I remember about you` / `## Recent conversation`. Voice
input is sanitized only at the STT boundary (`backend/voice/stt.py:85
sanitize_transcript`), NOT on the way back out of memory. Today writers are the
evaluator (user's own speech) + agent outcomes, so blast radius is small — but
any feature that lets tool/web/email content become a stored fact turns this
into a stored prompt-injection vector.
**Why:** the sanitize boundary is input-side only; recall trusts stored content.
**How to apply:** if any proposal widens who can write memory_facts (scrapers,
tools, Gmail/Slack ingestion, an entity knowledge graph), REQUIRE sanitization
at the format_context() injection boundary and treat recalled memory as
untrusted data. See [[project-security-posture]].

**Gap B — daily backup zip auto-includes the ENTIRE jarvis.db.**
`backend/main.py:210 _write_backup_zip()` zips the whole DB + FAISS index into
`data/backups/jarvis_<date>.zip`, plaintext, 30-day retention, local-only
(`data/` is gitignored). Any NEW content table added to jarvis.db is silently
inherited into 30 days of plaintext snapshots — no code change needed to leak
it. Relevant if raw-payload / knowledge-graph / PII tables are ever added.
**Why:** backup is whole-DB, not table-scoped, and unencrypted.
**How to apply:** when reviewing any new table holding raw/PII content, flag
backup inheritance; either exclude the table from the zip or accept documented
plaintext-at-rest with restrictive ACLs. Keep backups local-only (no cloud).

**Also reaffirmed this review:** `database.py` is fully parameterized aiosqlite
(no string-concat SQL) — this is the baseline any new memory code must not
regress.
