---
name: reflect
description: Capture sprint learnings and advance from reflect to done
argument-hint: "[optional: brief context about what was learned]"
disable-model-invocation: false
---

# /reflect

Capture what this sprint taught you — patterns discovered, mistakes caught, decisions validated. This is the gate-enforced learning step before a sprint can be marked done.

## Context

<context> #$ARGUMENTS </context>

## Execution

1. **Identify the active sprint.** Use `sprint_find_active` (sourced from lib-sprint.sh) to find the current sprint and confirm it is in the `shipping` or `reflect` phase.

2. **Capture learnings.** Use the `clavain:engineering-docs` skill to document what was learned during this sprint. The skill provides the full 7-step documentation workflow including YAML validation, category classification, and cross-referencing.

   If no context argument was provided, extract context from the recent conversation history — what was built, what went wrong, what patterns emerged.

3. **Register the artifact.** After the engineering doc is written, register it as a reflect-phase artifact:
   ```bash
   source hub/clavain/hooks/lib-sprint.sh
   sprint_set_artifact "<sprint_id>" "reflect" "<path_to_doc>"
   ```

4. **Advance the sprint.** Move from `reflect` → `done`:
   ```bash
   sprint_advance "<sprint_id>" "reflect"
   ```

The reflect gate requires at least one artifact registered for the reflect phase. The engineering doc satisfies this gate.
