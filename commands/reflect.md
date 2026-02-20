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

1. **Identify the active sprint.** Use `sprint_find_active` (sourced from lib-sprint.sh) to find the current sprint and confirm it is in the `reflect` phase. (The sprint command advances `shipping → reflect` before invoking `/reflect`.)

2. **Check for existing reflect artifact.** Before invoking engineering-docs, check if a reflect artifact is already registered:
   ```bash
   artifacts=$(bd state "<sprint_id>" sprint_artifacts 2>/dev/null) || artifacts="{}"
   existing=$(echo "$artifacts" | jq -r '.reflect // empty' 2>/dev/null) || existing=""
   ```
   If `existing` is non-empty, report "Reflect artifact already registered: <existing>. Skipping to advance." and jump to step 5 (advance).

3. **Capture learnings (complexity-scaled).**

   Check sprint complexity:
   ```bash
   source hub/clavain/hooks/lib-sprint.sh
   state=$(sprint_read_state "<sprint_id>" 2>/dev/null) || state="{}"
   complexity=$(echo "$state" | jq -r '.complexity // "3"' 2>/dev/null) || complexity="3"
   ```

   **C1-C2 (lightweight path):** Write a brief memory note capturing what was learned. If the sprint was routine with no novel learnings, write a complexity calibration note instead (e.g., "Estimated C2, actual was C1 because X"). Register the note path as the reflect artifact.

   **C3+ (full path):** Use the `clavain:engineering-docs` skill to document what was learned during this sprint. The skill provides the full 7-step documentation workflow including YAML validation, category classification, and cross-referencing.

   If no context argument was provided, extract context from the recent conversation history — what was built, what went wrong, what patterns emerged.

4. **Register the artifact.** After the learning artifact is written, register it as a reflect-phase artifact:
   ```bash
   source hub/clavain/hooks/lib-sprint.sh
   sprint_set_artifact "<sprint_id>" "reflect" "<path_to_doc>"
   ```
   (`sprint_set_artifact` handles both kernel registration via `ic run artifact add` and beads fallback automatically.)

5. **Advance the sprint.** Move from `reflect` → `done`:
   ```bash
   sprint_advance "<sprint_id>" "reflect"
   ```

The reflect gate requires at least one artifact registered for the reflect phase. The learning artifact (memory note or engineering doc) satisfies this gate.
