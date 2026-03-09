---
name: compound
description: Document a recently solved problem to compound your team's knowledge
argument-hint: "[optional: brief context about the fix]"
disable-model-invocation: false
---

# /compound

Capture a recently solved problem as structured documentation. Each documented solution compounds institutional knowledge — the first occurrence takes research, subsequent ones take minutes.

## Context

<context> #$ARGUMENTS </context>

## Execution

### Step 1: Surface similar past sessions (non-blocking)

If cass is available, search for past sessions where similar problems may have been encountered:

```bash
if command -v cass &>/dev/null; then
    cass search "<problem description keywords>" --robot --limit 5 --mode hybrid --fields minimal 2>/dev/null
fi
```

If results are found, briefly note: "Found N past sessions touching similar topics — this documentation will help future sessions avoid re-discovery." This provides motivation but does not block the workflow. Skip if cass is not installed.

### Step 2: Capture the solution

Use the `clavain:engineering-docs` skill to capture this solution. The skill provides the full 7-step documentation workflow including YAML validation, category classification, and cross-referencing.

If no context argument was provided, the skill will extract context from the recent conversation history.
