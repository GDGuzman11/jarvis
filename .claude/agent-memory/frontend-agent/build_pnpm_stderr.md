---
name: build-pnpm-stderr
description: Why `pnpm build` in PowerShell prints red NativeCommandError text even when the Vite build succeeds
metadata:
  type: feedback
---

When running `pnpm build` (frontend) via the PowerShell tool, Vite writes its
chunk-size warning and progress to stderr. Windows PowerShell wraps each native
stderr line in a NativeCommandError and shows red text referencing
`pnpm.ps1:24`, which looks like a failure but is NOT.

**Why:** PowerShell 5.1 turns any native-exe stderr output into ErrorRecords;
Vite always logs to stderr. The build still produces `dist/` and exits 0.

**How to apply:** Judge success by the presence of `✓ built in <time>` and the
`dist/...` asset table, not by the red NativeCommandError block. To suppress the
noise, filter output with `Select-String -Pattern "error|dist/|built in"`. Use
the Bash tool if a truly clean stderr is needed.
