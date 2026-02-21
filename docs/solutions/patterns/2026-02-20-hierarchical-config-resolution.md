---
title: "Hierarchical Config Resolution with Sentinel Values"
category: patterns
tags: [routing, yaml-parsing, shell, config-resolution]
date: 2026-02-20
sprint: iv-dd9q
---

# Hierarchical Config Resolution with Sentinel Values

## Problem

Model routing policy was scattered across three independent systems (agent frontmatter, dispatch tiers.yaml, Interspect overrides) with no unified view. Needed a single config file with nested inheritance that could replace all three without breaking existing consumers.

## Solution

`config/routing.yaml` with a 4-level resolution chain parsed by `scripts/lib-routing.sh`:

```
phases[phase].categories[cat] > phases[phase].model > defaults.categories[cat] > defaults.model
```

## Key Learnings

### 1. Sentinel values need belt-and-suspenders interception

The `inherit` sentinel means "no override at this level." Every public API must intercept it before returning. The pattern:

```bash
local result=""
# Each step: try value, skip if "inherit"
result="${_CACHE[$key]:-}"
[[ "$result" == "inherit" ]] && result=""
# ... next level ...
# Final guard (catches edge cases where ALL levels say inherit)
[[ "$result" == "inherit" ]] && result="sonnet"
```

Without the final guard, `codex exec -m inherit` would produce an API error.

### 2. Phase-level model beats default-level category

In `--phase executing --category research`, the resolution finds no phase-category override, then finds `phases.executing.model: sonnet` and returns it — never reaching `defaults.categories.research: haiku`. This is correct: "I'm in the executing phase" is a stronger signal than "I'm a research agent." If you want research cheap during execution, set it explicitly in `phases.executing.categories.research`.

### 3. Check git before re-applying changes after context compaction

After compaction, the conversation summary said Tasks 2-4 were "pending." In reality, the previous session had already committed them (`35c894d`). Re-reading and re-editing already-committed files was wasted work. **Always `git diff HEAD` first** after compaction to see what's actually uncommitted.

### 4. Phase names must match code, not display strings

The first routing.yaml draft used display names (`strategy`, `plan`, `quality-gates`, `ship`). The codebase uses state machine names (`strategized`, `planned`, `executing`, `shipping`). `quality-gates` isn't even a phase — it's a display alias for `executing`. Callers pass `--phase executing`, so the config must use that key.

### 5. Don't fight linter/hook enforcement

Agent `.md` files had `model: sonnet` restored by a hook after removal. The routing.yaml overlay works regardless — frontmatter is a harmless fallback. Committing the removal is fine, but if hooks re-add it in future sessions, that's OK too.
