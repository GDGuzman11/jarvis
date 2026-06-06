# Backend Agent Memory

- [Environment](environment.md) — run Python via `.venv\Scripts\python.exe` (no uv on PATH); no Rust/cargo.
- [Testing rule](testing-rule.md) — implement + self-verify, but leave CLAUDE.md checkboxes for debugger-agent sign-off.
- [Pre-existing secret-scan failure](project_pre_existing_secret_scan_failure.md) — backend suite is 95 pass / 1 fail; the fail predates Phase 12 (`get_gmail_token.py` client id).
- [Wake word: openWakeWord](project_wake_word_openwakeword.md) — local `hey_jarvis`, no API key, ONNX path on Windows; no porcupine key/gate.
- [Agent identities](project_agent_identities.md) — names for the 4 TBD agents: Atlas/Sentinel/Vega/Quill (+ Ben, Kado from spec).
