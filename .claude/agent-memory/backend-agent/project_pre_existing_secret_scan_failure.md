---
name: pre-existing-secret-scan-failure
description: One backend test (secret scan) was already red before Phase 12 due to a committed Google OAuth client id
metadata:
  type: project
---

`backend/test_phase9_verify.py::test_no_secrets_committed_in_source_files` fails because `get_gmail_token.py` (committed around 2026-06-04, commit 9671338) embeds a real Google OAuth **client id** on line 9, which the regex secret-scanner flags. Confirmed pre-existing by stashing Phase 12A changes and re-running — still red.

**Why:** A helper script for the Gmail OAuth flow was committed with the client id inline rather than pulled from keyring.
**How to apply:** The suite has grown as Phase 12 lands (96 → 117 tests by Phase 12D); the constant is "all green except this one secret-scan test." As of Phase 12D the state is 116 pass / 1 fail. When verifying backend work, do not attribute this failure to your change. The proper fix (move the client id to keyring / scrub it) is a security-agent task, not part of memory-system work. A Google OAuth client id is lower-sensitivity than the client *secret*, but it still trips the scanner and violates Security Rule 1.

Related: [[environment]] (how to run the suite).
