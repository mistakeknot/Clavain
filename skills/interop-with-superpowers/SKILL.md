---
name: interop-with-superpowers
description: If superpowers is not installed, this skill is informational only. Use when the user mentions /superpowers:* commands or asks how Clavain relates to superpowers (obra/superpowers).
---

# Interop with Superpowers

Clavain shares vocabulary with [superpowers](https://github.com/obra/superpowers) — specifically the `dispatching-parallel-agents`, `executing-plans`, `subagent-driven-development`, `code-review-discipline` (renamed from `requesting-code-review`), and `using-clavain` (renamed from `using-superpowers`) skills are vendored from upstream and continue to evolve via `/clavain:upstream-sync`.

## Vocabulary mapping

| Clavain command | superpowers command | Notes |
|---|---|---|
| `/clavain:write-plan` | `/superpowers:write-plan` | Both produce `docs/plans/<date>-<slug>.md` |
| `/clavain:brainstorm` | `/superpowers:brainstorm` | Same goal; Clavain emits beads |
| `/clavain:execute-plan` | `/superpowers:execute-plan` | Clavain integrates with sprint orchestrator |
| `clavain:dispatching-parallel-agents` skill | `superpowers:dispatching-parallel-agents` skill | Identical semantics; vendored |
| `clavain:subagent-driven-development` skill | `superpowers:subagent-driven-development` skill | Vendored; identical |

## When to reach for superpowers instead

If you prefer the original obra workflow (lighter integration, no beads requirement, no Sylveste-specific routing), invoke superpowers directly. Both rigs coexist — Clavain does not replace superpowers, and `/clavain:setup` does not disable it.

## Compound-engineering note

`compound-engineering@every-marketplace` shares this bridge skill for V1. A dedicated `interop-with-compound-engineering` skill is filed as P3 (sylveste-fj1w) if telemetry shows that coexistence pattern is heavily exercised.
