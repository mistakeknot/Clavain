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

1. **Identify the active sprint.** Use `"${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-find-active` to find the current sprint and confirm it is in the `reflect` phase. (The sprint command advances `shipping → reflect` before invoking `/reflect`.)

2. **Check for existing reflect artifact.** Before invoking engineering-docs, check if a reflect artifact is already registered:
   ```bash
   artifacts=$(bd state "<sprint_id>" sprint_artifacts 2>/dev/null) || artifacts="{}"
   existing=$(echo "$artifacts" | jq -r '.reflect // empty' 2>/dev/null) || existing=""
   ```
   If `existing` is non-empty, report "Reflect artifact already registered: <existing>. Skipping to advance." and jump to step 5 (advance).

3. **Capture learnings (complexity-scaled).**

   Check sprint complexity:
   ```bash
   state=$("${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-read-state "<sprint_id>" 2>/dev/null) || state="{}"
   complexity=$(echo "$state" | jq -r '.complexity // "3"' 2>/dev/null) || complexity="3"
   ```

   **C1-C2 (lightweight path):** Write a brief memory note capturing what was learned. If the sprint was routine with no novel learnings, write a complexity calibration note instead (e.g., "Estimated C2, actual was C1 because X"). Register the note path as the reflect artifact.

   **C3+ (full path):** Use the `clavain:engineering-docs` skill to document what was learned during this sprint. The skill provides the full 7-step documentation workflow including YAML validation, category classification, and cross-referencing.

   If no context argument was provided, extract context from the recent conversation history — what was built, what went wrong, what patterns emerged.

4. **Register the artifact.** After the learning artifact is written, register it as a reflect-phase artifact:
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" set-artifact "<sprint_id>" "reflect" "<path_to_doc>"
   ```
   (`sprint_set_artifact` handles both kernel registration via `ic run artifact add` and beads fallback automatically.)

5. **Advance the sprint.** Move from `reflect` → `done`:
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" sprint-advance "<sprint_id>" "reflect"
   ```

6. **Calibrate cost estimates (silent).** After advancing, recalibrate phase cost estimates from interstat history so future sprints use improved estimates:
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/clavain-cli" calibrate-phase-costs 2>/dev/null || true
   ```
   This is the closed-loop feedback: actual phase costs from completed sprints improve estimates for future sprints. Silent on failure — hardcoded defaults remain active.

7. **Calibrate agent routing from evidence (silent).** After cost calibration, recalibrate agent model routing from interspect evidence so future sprints route agents to the right model tier:
   ```bash
   if source "${CLAUDE_PLUGIN_ROOT}/hooks/lib.sh" 2>/dev/null; then
       interspect_root=$(_discover_interspect_plugin 2>/dev/null) || interspect_root=""
       if [[ -n "$interspect_root" ]]; then
           source "${interspect_root}/hooks/lib-interspect.sh"
           _interspect_write_routing_calibration 2>/dev/null || true
       fi
   fi
   ```
   This is the B3 closed-loop: verdict outcomes from completed sprints calibrate agent model selection for future sprints. Shadow mode by default — logs what would change. Silent on failure.

The reflect gate requires at least one artifact registered for the reflect phase. The learning artifact (memory note or engineering doc) satisfies this gate.
