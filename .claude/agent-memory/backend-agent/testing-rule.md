---
name: testing-rule
description: Per-task testing/sign-off workflow — backend-agent does not self-check-off CLAUDE.md
metadata:
  type: feedback
---

After completing each Phase 2+ task, do NOT check off the CLAUDE.md checkbox yourself. Implement + self-verify, then hand the specific TEST to the **debugger-agent** for official sign-off. Only after the debugger-agent confirms does the box get checked.

**Why:** CLAUDE.md's TESTING RULE: "After EVERY single completed task, the debugger-agent runs a targeted test for that specific task before moving on. No task is considered done until its test passes."
**How to apply:** Finish the work, run a quick self-test to de-risk, then in the final response explicitly state the TEST for the debugger-agent and tell the user to run `/production-manager` (which routes to debugger-agent). Leave checkboxes unticked.
