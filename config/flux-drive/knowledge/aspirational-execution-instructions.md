---
lastConfirmed: 2026-02-10
provenance: independent
---
Orchestrator instructions should not describe execution patterns that are impossible given the execution model. Pipelining or concurrent execution instructions fail when the orchestrator executes tool calls sequentially.

Evidence: skills/flux-drive/phases/launch.md Step 2.1a instructs "Start qmd queries before agent dispatch. While queries run, prepare agent prompts" but Claude Code orchestrator executes tool calls sequentially with no pipelining mechanism. This creates false expectations and could lead to skipped knowledge injection.

Verify: Review orchestrator dispatch instructions for concurrent/parallel/pipeline terminology. Check if the orchestrator actually supports the described execution model (async tool calls, deferred injection, parallel preparation).
