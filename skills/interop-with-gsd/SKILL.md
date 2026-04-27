---
name: interop-with-gsd
description: If gsd-plugin is not installed, this skill is informational only. Use when the user mentions /gsd:* commands, references the GSD framework (Get Stuff Done), or asks how Clavain compares to spec-driven development workflows.
---

# Interop with GSD (Get Stuff Done)

[GSD](https://github.com/gsd-build/get-shit-done) (also packaged as [gsd-plugin](https://github.com/jnuyens/gsd-plugin)) is a spec-driven development framework for Claude Code. It splits complex tasks into plan/execute/review phases, each with its own clean context. Clavain's sprint orchestrator follows a similar pattern with additional review gates.

## Vocabulary mapping

| Clavain command | GSD command | Notes |
|---|---|---|
| `/clavain:write-plan` | `/gsd:plan` | Both produce a structured plan doc |
| `/clavain:execute-plan` | `/gsd:execute` | Clavain dispatches subagents per task; GSD spawns fresh Claude instances |
| `/clavain:verify` | `/gsd:verify` | Both check the implementation matches the spec |
| `/clavain:brainstorm` | (no direct GSD equivalent) | GSD jumps straight to plan; Clavain has a separate brainstorm phase |
| `/clavain:reflect` | (no direct GSD equivalent) | Clavain captures sprint learnings; GSD relies on PR review |

## When to reach for GSD instead

GSD's strength is fresh-context-per-phase isolation — useful when context rot is the dominant failure mode. If you are working on a project with extensive specs and want each phase to start clean, invoke `/gsd:*` directly. Clavain's strength is multi-agent review gates and sprint-state continuity. Pick whichever your project's workflow needs; both rigs coexist.

## Marketplace identifier

The agent-rig.json entry uses `gsd-plugin@jnuyens` as a placeholder. If a user reports the canonical marketplace differs, update `agent-rig.json` and let downstream consumers re-detect.
