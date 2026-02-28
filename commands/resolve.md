---
name: resolve
description: Resolve findings from any source — auto-detects TODOs, PR comments, or todo files, then resolves in parallel
argument-hint: "[optional: 'todos', 'pr', 'code', PR number, or specific pattern]"
---

Resolve findings from any source using parallel processing. Auto-detects the source or accepts an explicit hint.

## Source Detection

<resolve_target> #$ARGUMENTS </resolve_target>

**Auto-detect** (no arguments or ambiguous input):

```bash
# Check for todo files first (most specific)
TODO_FILES=$(ls todos/*.md 2>/dev/null | head -1)

# Check for PR context
PR_NUMBER=$(gh pr status --json number -q '.currentBranch.number' 2>/dev/null || echo "")

# Check for TODO comments in code
TODO_COMMENTS=$(grep -r "TODO" --include="*.go" --include="*.py" --include="*.ts" --include="*.sh" --include="*.rs" -l . 2>/dev/null | head -1)
```

| Priority | Condition | Source |
|----------|-----------|--------|
| 1 | Argument is a number or `pr` | PR comments via `gh pr view` |
| 2 | Argument is `todos` or `todos/*.md` exist | Todo files in `todos/` directory |
| 3 | Argument is `code` | TODO comments in codebase via grep |
| 4 | No argument, todo files exist | Todo files (default) |
| 5 | No argument, on PR branch | PR comments |
| 6 | Fallback | TODO comments in code |

### Source: Todo Files
```bash
# Read all pending todo files
ls todos/*.md
```
If any todo recommends deleting files in `docs/plans/` or `docs/solutions/`, skip it and mark as `wont_fix` — those are intentional pipeline artifacts.

### Source: PR Comments
```bash
gh pr status
gh pr view PR_NUMBER --comments
```

### Source: Code TODOs
```bash
grep -r "TODO" --include="*.go" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.sh" --include="*.rs" .
```

## Workflow

### 1. Analyze

Gather all findings from the detected source. Group by type and dependency.

### 2. Plan

Create a TodoWrite list of all items. Check for dependencies — if one fix requires another to land first, note the order. Output a brief mermaid diagram showing the parallel/sequential flow.

### 3. Implement (PARALLEL)

Spawn a `pr-comment-resolver` agent for each independent item in parallel. Wait for sequential dependencies to complete before spawning dependent items.

### 4. Commit

Commit changes. For each source type:
- **Todo files**: Mark resolved todos as complete by renaming the file status prefix
- **PR comments**: Use `gh api` to resolve PR review threads. Verify with `gh pr view --comments`. If unresolved remain, repeat from step 1
- **Code TODOs**: Verify the TODO comment was removed. Commit with conventional message

### 5. Record Trust Feedback

After resolving findings, emit trust evidence for each finding that was acted on. This feeds the agent trust scoring system (intertrust).

**Only emit when findings came from flux-drive review** (check: `.clavain/quality-gates/findings.json` exists).

```bash
FINDINGS_JSON=".clavain/quality-gates/findings.json"
if [[ -f "$FINDINGS_JSON" ]]; then
    # Try intertrust first (extracted plugin), fall back to legacy interspect location
    TRUST_PLUGIN=$(find ~/.claude/plugins/cache -path "*/intertrust/*/hooks/lib-trust.sh" 2>/dev/null | head -1)
    [[ -z "$TRUST_PLUGIN" ]] && TRUST_PLUGIN=$(find ~/.claude/plugins/cache -path "*/interspect/*/hooks/lib-trust.sh" 2>/dev/null | head -1)
    if [[ -n "$TRUST_PLUGIN" ]]; then
        source "$TRUST_PLUGIN"
        PROJECT=$(_trust_project_name)
        SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
    fi
fi
```

For each finding resolved in step 3:
- If the finding was **fixed** (code changed to address it): `_trust_record_outcome "$SESSION_ID" "<agent>" "$PROJECT" "<finding_id>" "<severity>" "accepted" "<review_run_id>"`
- If the finding was **dismissed** (skipped, wont_fix, or deemed irrelevant): `_trust_record_outcome "$SESSION_ID" "<agent>" "$PROJECT" "<finding_id>" "<severity>" "discarded" "<review_run_id>"`

The `agent` comes from `findings.json` `.findings[].agents[0]` (primary attribution). The `review_run_id` comes from `.synthesis_timestamp`. The `severity` comes from `.findings[].severity`.

**Silent failures:** If lib-trust.sh is not found or any call fails, continue normally. Trust feedback is opportunistic, never blocking.

### 5b. Emit Disagreement Events

After recording trust feedback, check each resolved finding for `severity_conflict`. When the resolution changes a decision, emit a kernel event.

**Impact gate:** Only emit when:
- The finding had `severity_conflict` (agents disagreed on severity)
- AND either: (a) the finding was discarded despite having P0 or P1 severity from at least one agent, or (b) the finding was accepted with a severity different from the majority rating

```bash
if [[ -f "$FINDINGS_JSON" ]] && command -v ic &>/dev/null; then
    SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
    PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

    # Process each finding that has severity_conflict
    # Uses the same findings.json iteration as Step 5 (trust feedback)
    jq -c '.findings[] | select(.severity_conflict != null)' "$FINDINGS_JSON" 2>/dev/null | while IFS= read -r finding; do
        [[ -z "$finding" ]] && continue

        FINDING_ID=$(echo "$finding" | jq -r '.id // empty')
        SEVERITY=$(echo "$finding" | jq -r '.severity // empty')
        AGENTS_MAP=$(echo "$finding" | jq -c '.severity_conflict // {}')

        # Determine outcome from the finding's resolution field (set during Step 3)
        OUTCOME=$(echo "$finding" | jq -r '.resolution // empty')
        [[ -z "$OUTCOME" ]] && continue

        # Check if any agent rated this P0 or P1
        HAS_HIGH_SEVERITY=$(echo "$AGENTS_MAP" | jq 'to_entries | map(select(.value == "P0" or .value == "P1")) | length > 0')

        # Impact gate
        IMPACT=""
        DISMISSAL_REASON=""
        if [[ "$OUTCOME" == "discarded" && "$HAS_HIGH_SEVERITY" == "true" ]]; then
            IMPACT="decision_changed"
            DISMISSAL_REASON=$(echo "$finding" | jq -r '.dismissal_reason // "agent_wrong"')
        elif [[ "$OUTCOME" == "accepted" ]]; then
            SEVERITY_MISMATCH=$(echo "$AGENTS_MAP" | jq --arg sev "$SEVERITY" 'to_entries | map(select(.value != $sev)) | length > 0')
            if [[ "$SEVERITY_MISMATCH" == "true" ]]; then
                IMPACT="severity_overridden"
            fi
        fi

        # Only emit if impact gate passed
        if [[ -n "$IMPACT" ]]; then
            CONTEXT=$(jq -n \
                --arg finding_id "$FINDING_ID" \
                --argjson agents "$AGENTS_MAP" \
                --arg resolution "$OUTCOME" \
                --arg dismissal_reason "$DISMISSAL_REASON" \
                --arg chosen_severity "$SEVERITY" \
                --arg impact "$IMPACT" \
                '{finding_id:$finding_id,agents:$agents,resolution:$resolution,dismissal_reason:$dismissal_reason,chosen_severity:$chosen_severity,impact:$impact}')

            ic events emit \
                --source=review \
                --type=disagreement_resolved \
                --session="$SESSION_ID" \
                --project="$PROJECT_ROOT" \
                --context="$CONTEXT" 2>/dev/null || true
        fi
    done
fi
```

**Silent fail-open:** The `2>/dev/null || true` ensures resolve never fails due to event emission. Same pattern as trust feedback.
