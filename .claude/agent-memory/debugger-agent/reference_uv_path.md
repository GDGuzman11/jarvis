---
name: uv-executable-path
description: uv is not on PATH in this environment — must be invoked by full path when running Python tests
metadata:
  type: reference
---

`uv` is installed at `C:\Users\User\.local\bin\uv.exe` but is NOT on the PATH for either the Bash tool or the PowerShell tool in this environment.

**Why:** Running `uv run ...` directly fails with "command not found" / "not recognized". The Bash tool also cannot see Windows-installed uv at all.

**How to apply:** When running any `uv` command (e.g. the Phase 1 verify `uv run python -c "..."`), invoke it via the full path through PowerShell: `& "C:\Users\User\.local\bin\uv.exe" run python -c "..."`. Set-Location to the project dir first so uv resolves the right `.venv`/`pyproject.toml`.
