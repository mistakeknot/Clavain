---
name: reflect
description: Capture sprint learnings and advance from reflect to done
argument-hint: "[optional: brief context about what was learned]"
disable-model-invocation: false
---

# /reflect

Capture sprint learnings and advance `reflect → done`.

## Context

<context> #$ARGUMENTS </context>

## Steps

1. **Find active sprint.** `clavain-cli sprint-find-active` — confirm phase is `reflect`.

2. **Check existing artifact.**
   ```bash
   artifacts=$(bd state "<sprint_id>" sprint_artifacts 2>/dev/null) || artifacts="{}"
   existing=$(echo "$artifacts" | jq -r '.reflect // empty' 2>/dev/null)
   ```
   If non-empty: report it, skip to step 5.

3. **Capture learnings (complexity-scaled).**
   ```bash
   state=$(clavain-cli sprint-read-state "<sprint_id>" 2>/dev/null) || state="{}"
   complexity=$(echo "$state" | jq -r '.complexity // "3"')
   ```
   - **C1-C2:** Write brief memory note. If routine, write complexity calibration note instead.
   - **C3+:** Use `clavain:engineering-docs` skill (full 7-step workflow).
   - **Required frontmatter:**
     ```yaml
     ---
     artifact_type: reflection
     bead: <sprint_id>
     stage: reflect
     ---
     ```
   If no context arg, extract from conversation history.

4. **Register artifact.**
   ```bash
   clavain-cli set-artifact "<sprint_id>" "reflect" "<path_to_doc>"
   ```

5. **Export session transcript (non-blocking).**
   ```bash
   session_file=$(ls -t ~/.claude/projects/*/"$(cat /tmp/interstat-session-id 2>/dev/null || echo unknown)"*.jsonl 2>/dev/null | head -1)
   if [[ -n "$session_file" ]] && command -v cass &>/dev/null; then
       mkdir -p docs/sprints
       cass export "$session_file" --format markdown -o "docs/sprints/<sprint_id>-transcript.md" 2>/dev/null || true
       cass export "$session_file" --format json -o "docs/sprints/<sprint_id>-transcript.json" 2>/dev/null || true
   fi
   ```

6. **Advance sprint.**
   ```bash
   clavain-cli sprint-advance "<sprint_id>" "reflect"
   ```

7. **Drift check (non-blocking).** Run `interwatch:watch` via Skill tool. Report findings but don't block.

8. **Calibrate costs (silent).**
   ```bash
   clavain-cli calibrate-phase-costs 2>/dev/null || true
   ```

9. **Calibrate routing (silent).**
   ```bash
   if source "${CLAUDE_PLUGIN_ROOT}/hooks/lib.sh" 2>/dev/null; then
       interspect_root=$(_discover_interspect_plugin 2>/dev/null)
       if [[ -n "$interspect_root" ]]; then
           source "${interspect_root}/hooks/lib-interspect.sh"
           _interspect_write_routing_calibration 2>/dev/null || true
       fi
   fi
   ```

Reflect gate requires at least one registered artifact for the reflect phase.
