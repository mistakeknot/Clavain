# Design: Sprint Awareness System (Phase 1 — Passive Awareness)

> Clavain plugin enhancement. Designed 2026-02-11.

## Problem Statement

Clavain has excellent per-phase tools (brainstorm, strategy, write-plan, execute, review, ship) but no awareness of where the user is in the workflow. Users skip phases, forget handoffs, leave beads stale, and lose context between sessions. The `/insights` report showed 27 wrong-approach friction events and session continuity as the number one pain point.

## Solution Overview

Two components that share a single scanning engine:

1. **Session-start sprint scan** (hook enhancement) — lightweight, fast, appended to `additionalContext`
2. **`/sprint-status` command** — deep scan with full details and recommendations

Both run the same signal detectors; the hook runs a subset (fast signals only), while the command runs all of them.

---

## Design Decisions

### D1: Separate scanner script, sourced by session-start.sh

**Decision:** Create `hooks/sprint-scan.sh` as a library of functions sourced by `session-start.sh` (for the brief version) and invoked directly by the `/sprint-status` command (for the full version).

**Rationale:**
- Keeps `session-start.sh` focused on its existing responsibilities (context injection, companion detection, upstream staleness).
- The command needs the same logic — sourcing a shared library avoids duplication.
- Follows the existing pattern: `lib.sh` is already sourced by `session-start.sh`.
- The sprint-scan script defines functions but produces no output when sourced (same as `lib.sh`).

**Alternative considered:** Inline everything in session-start.sh. Rejected because the command would need to duplicate all the detection logic.

### D2: Topic slug matching for brainstorm-to-plan correlation

**Decision:** Match brainstorms to plans using the topic slug extracted from the filename pattern `YYYY-MM-DD-<topic>-brainstorm.md` to `YYYY-MM-DD-<topic>.md`. Strip the `-brainstorm` suffix and check for any plan file containing the same topic slug.

**Matching algorithm:**
1. Extract `<topic>` from brainstorm filename: `YYYY-MM-DD-<topic>-brainstorm.md` => `<topic>`
2. Search `docs/plans/` for any file containing `<topic>` in its name (case-insensitive substring match)
3. Also check `docs/prds/` for strategy docs containing `<topic>`
4. A brainstorm is "orphaned" if neither a matching plan nor a matching PRD exists

**Rationale:** The date component is unreliable (brainstorm and plan might be on different days). The topic slug is the stable identifier that flows through `brainstorm -> strategy -> write-plan`. Substring matching handles variant naming (e.g., `plan-clavain-sprint-awareness` matches topic slug `sprint-awareness`).

**Edge cases:**
- Very short slugs (e.g., `auth`) might false-match. Acceptable for a diagnostic tool — false negatives are worse than false positives here.
- Brainstorms without the standard naming pattern are skipped (no slug to match).

### D3: `/sprint-status` as a command, not a skill

**Decision:** Command (`commands/sprint-status.md`).

**Rationale:**
- Commands are simpler to invoke (`/clavain:sprint-status` vs. loading a skill with the Skill tool).
- This is a one-shot diagnostic, not a process guide — it should run and report, not guide a multi-step workflow.
- Follows the pattern of `/doctor` (also a diagnostic command).
- Uses `disable-model-invocation: true` since it triggers bash operations.

### D4: Brief session-start output format

**Decision:** A compact status line appended to the existing `additionalContext`, using a condensed format with emoji-free indicators. Maximum 500 tokens (roughly 10-15 lines).

**Format (brief, session-start hook):**

```
\n\n**Sprint status:**
- HANDOFF.md: previous session left incomplete work (run `/clavain:sprint-status` for details)
- 2 orphaned brainstorms (no matching plan)
- Plan "sprint-awareness" is 3/7 complete
- Beads: 5 open, 2 stale (5+ days)
```

Only lines with findings are shown. If everything is clean, no sprint status section appears at all — this addresses the "don't be annoying" concern.

**Rationale:**
- Zero output when clean = zero noise.
- Each line is actionable or at least informative.
- Points to `/sprint-status` for full details rather than bloating the hook output.
- Fits within the 500-token budget (typically 3-5 lines).

### D5: Avoiding annoyance

**Decision:** Apply three noise-reduction principles:

1. **Zero output when clean.** If no signals are detected, the sprint status section is entirely omitted from `additionalContext`. The user sees no difference.

2. **Frequency capping for HANDOFF.md.** Once the session starts and HANDOFF.md is surfaced, the user knows about it. The command can re-check, but the hook does not nag repeatedly (it only fires once at session start by design).

3. **Severity filtering.** The brief version only shows signals above a threshold:
   - HANDOFF.md always shows (highest priority)
   - Orphaned brainstorms only show if count >= 2 (one might be intentionally exploratory)
   - Plan completion only shows if below 50% and plan is older than 1 day (fresh plans are expected to be incomplete)
   - Stale beads only show if stale 5+ days (the `bd stale` default)
   - Skipped phases never shown in brief (too expensive and too noisy)

---

## File-by-File Implementation Plan

### File 1: `hooks/sprint-scan.sh` (NEW)

A library of bash functions that detect sprint workflow signals. No output when sourced — all functions return results via stdout or set global variables.

```bash
#!/usr/bin/env bash
# Sprint awareness scanner — shared between session-start hook and /sprint-status command
# Source this file; call individual functions.
# All functions are project-directory-aware (use CWD or SPRINT_PROJECT_DIR).

# Detect HANDOFF.md
# Returns: 0 if exists, 1 if not. Prints brief summary (first 5 lines of each section).
sprint_check_handoff() { ... }

# Count orphaned brainstorms (brainstorms with no matching plan or PRD)
# Returns: count via stdout
# Usage: orphan_count=$(sprint_count_orphaned_brainstorms)
sprint_count_orphaned_brainstorms() { ... }

# List orphaned brainstorms with details (for full report)
# Returns: multiline "filename: topic" via stdout
sprint_list_orphaned_brainstorms() { ... }

# Find incomplete plans (plans with unchecked items)
# Returns: multiline "filename: N/M complete" via stdout
sprint_find_incomplete_plans() { ... }

# Quick beads summary (uses bd stats)
# Returns: summary line via stdout
sprint_beads_summary() { ... }

# Stale beads details (uses bd stale)
# Returns: multiline stale bead details via stdout
sprint_stale_beads() { ... }

# In-progress beads with no recent commits (uses bd list + git log)
# Returns: multiline details via stdout
sprint_stuck_beads() { ... }

# Strategy gap detection
# Returns: 0 if gap detected, 1 if no gap
sprint_check_strategy_gap() { ... }

# Skipped phases detection (git log analysis — SLOW, command-only)
# Returns: multiline details via stdout
sprint_check_skipped_phases() { ... }

# Brief scan (fast, for session-start hook)
# Returns: formatted status block via stdout (empty if clean)
sprint_brief_scan() { ... }

# Full scan (detailed, for /sprint-status command)
# Returns: formatted report via stdout
sprint_full_scan() { ... }
```

**Implementation details for key functions:**

#### `sprint_check_handoff()`
```bash
sprint_check_handoff() {
    local handoff="${SPRINT_PROJECT_DIR:-.}/HANDOFF.md"
    [[ -f "$handoff" ]] || return 1
    # Extract section headers and first line of each
    grep -E '^## ' "$handoff" 2>/dev/null | head -4
    return 0
}
```

#### `sprint_count_orphaned_brainstorms()`
```bash
sprint_count_orphaned_brainstorms() {
    local brainstorms_dir="${SPRINT_PROJECT_DIR:-.}/docs/brainstorms"
    local plans_dir="${SPRINT_PROJECT_DIR:-.}/docs/plans"
    local prds_dir="${SPRINT_PROJECT_DIR:-.}/docs/prds"
    [[ -d "$brainstorms_dir" ]] || { echo 0; return; }

    local count=0
    for f in "$brainstorms_dir"/*-brainstorm.md; do
        [[ -f "$f" ]] || continue
        local basename=$(basename "$f")
        # Extract topic: YYYY-MM-DD-<topic>-brainstorm.md -> <topic>
        local topic=$(echo "$basename" | sed 's/^[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-//;s/-brainstorm\.md$//')
        [[ -z "$topic" ]] && continue

        # Check for matching plan or PRD (case-insensitive substring)
        local found=0
        if [[ -d "$plans_dir" ]]; then
            ls "$plans_dir" 2>/dev/null | grep -qi "$topic" && found=1
        fi
        if [[ "$found" -eq 0 && -d "$prds_dir" ]]; then
            ls "$prds_dir" 2>/dev/null | grep -qi "$topic" && found=1
        fi
        [[ "$found" -eq 0 ]] && count=$((count + 1))
    done
    echo "$count"
}
```

#### `sprint_find_incomplete_plans()`
```bash
sprint_find_incomplete_plans() {
    local plans_dir="${SPRINT_PROJECT_DIR:-.}/docs/plans"
    [[ -d "$plans_dir" ]] || return

    for f in "$plans_dir"/*.md; do
        [[ -f "$f" ]] || continue
        local total=$(grep -cE '^\s*- \[[ x]\]' "$f" 2>/dev/null || echo 0)
        [[ "$total" -eq 0 ]] && continue
        local done=$(grep -cE '^\s*- \[x\]' "$f" 2>/dev/null || echo 0)
        local pct=0
        [[ "$total" -gt 0 ]] && pct=$(( done * 100 / total ))
        [[ "$pct" -lt 100 ]] && echo "$(basename "$f"): ${done}/${total} complete (${pct}%)"
    done
}
```

#### `sprint_beads_summary()`
```bash
sprint_beads_summary() {
    command -v bd &>/dev/null || return
    [[ -d "${SPRINT_PROJECT_DIR:-.}/.beads" ]] || return
    # bd stats returns a quick summary — parse the key numbers
    local stats
    stats=$(bd stats 2>/dev/null) || return
    echo "$stats" | head -3
}
```

#### `sprint_brief_scan()`
This is the orchestrator called by `session-start.sh`. It runs only the fast signals and formats a compact output.

```bash
sprint_brief_scan() {
    local output=""

    # 1. HANDOFF.md (highest priority, always show)
    if sprint_check_handoff >/dev/null 2>&1; then
        output="${output}\\n- HANDOFF.md: previous session left incomplete work (run \`/clavain:sprint-status\` for details)"
    fi

    # 2. Orphaned brainstorms (show if >= 2)
    local orphans
    orphans=$(sprint_count_orphaned_brainstorms)
    if [[ "$orphans" -ge 2 ]]; then
        output="${output}\\n- ${orphans} orphaned brainstorms (no matching plan)"
    fi

    # 3. Incomplete plans (show if any below 50% and older than 1 day)
    local incomplete
    incomplete=$(sprint_find_incomplete_plans)
    if [[ -n "$incomplete" ]]; then
        local count
        count=$(echo "$incomplete" | wc -l)
        local first_line
        first_line=$(echo "$incomplete" | head -1)
        if [[ "$count" -eq 1 ]]; then
            output="${output}\\n- Plan ${first_line}"
        else
            output="${output}\\n- ${count} incomplete plans (lowest: ${first_line})"
        fi
    fi

    # 4. Beads summary (quick)
    if command -v bd &>/dev/null && [[ -d "${SPRINT_PROJECT_DIR:-.}/.beads" ]]; then
        local stale_count
        stale_count=$(bd stale 2>/dev/null | grep -c '●' || echo 0)
        local open_count
        open_count=$(bd list --status=open 2>/dev/null | grep -c '●' || echo 0)
        if [[ "$stale_count" -gt 0 ]]; then
            output="${output}\\n- Beads: ${open_count} open, ${stale_count} stale (5+ days)"
        fi
    fi

    # 5. Strategy gap
    local brainstorms_dir="${SPRINT_PROJECT_DIR:-.}/docs/brainstorms"
    local prds_dir="${SPRINT_PROJECT_DIR:-.}/docs/prds"
    if [[ -d "$brainstorms_dir" ]] && ls "$brainstorms_dir"/*.md &>/dev/null; then
        if [[ ! -d "$prds_dir" ]] || ! ls "$prds_dir"/*.md &>/dev/null 2>&1; then
            output="${output}\\n- Strategy gap: brainstorms exist but no PRDs"
        fi
    fi

    # Only print if we have findings
    if [[ -n "$output" ]]; then
        echo "\\n\\n**Sprint status:**${output}\\nRun \`/clavain:sprint-status\` for full details."
    fi
}
```

**Performance notes:**
- `stat` on HANDOFF.md: < 1ms
- `ls` + `grep` on brainstorms/plans directories: < 10ms (typically < 20 files)
- `bd stats`: < 100ms (SQLite query on local .beads database)
- `bd stale` + `bd list`: < 200ms each
- Total: well under the 2-second budget
- NO git operations in the brief scan

### File 2: `hooks/session-start.sh` (MODIFY)

Changes are minimal — source the new library and append its output.

**Current state (lines 27-78):** Reads using-clavain, detects companions, conventions, setup hint, upstream warning, outputs JSON.

**Modification:** After the upstream staleness check (line 68) and before the JSON output (line 71), add:

```bash
# Sprint awareness scan (lightweight)
source "${SCRIPT_DIR}/sprint-scan.sh"
sprint_context=$(sprint_brief_scan)
```

Then in the JSON output, append `${sprint_context}` after `${upstream_warning}`:

```bash
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "You have Clavain.\n\n**Below is the full content of your 'clavain:using-clavain' skill - your introduction to using skills. For all other skills, use the 'Skill' tool:**\n\n${using_clavain_escaped}${companion_context}${conventions}${setup_hint}${upstream_warning}${sprint_context}"
  }
}
EOF
```

**Risk:** The sprint_brief_scan output already uses `\\n` escaping (not literal newlines) so it is safe to embed directly in the JSON string context, just like the existing `companion_context`, `conventions`, etc.

**Exact diff location:** Lines 56-75 of current `session-start.sh`.

### File 3: `hooks/lib.sh` (MODIFY — minimal)

No changes needed. The `escape_for_json()` function is not needed for the sprint scan output because the scan returns pre-escaped `\\n` strings (same pattern as `companion_context` in session-start.sh). The sprint-scan functions use `echo` not `printf`, and the output flows through the same heredoc as other context strings.

If in the future we need additional utilities (e.g., date comparison), they would go here. For Phase 1, no changes.

### File 4: `commands/sprint-status.md` (NEW)

```markdown
---
name: sprint-status
description: Show sprint workflow status — handoffs, orphaned brainstorms, plan progress, bead health, and skipped phases
disable-model-invocation: true
---

# Sprint Status

Scan the current project for workflow signals and present a comprehensive sprint status report.

## Execution

Source the sprint scanner and run the full scan:

\`\`\`bash
# Source the sprint scanner from the plugin
source "${CLAUDE_PLUGIN_ROOT}/hooks/sprint-scan.sh"
export SPRINT_PROJECT_DIR="."

# Run the full scan
sprint_full_scan
\`\`\`

Present the output as a structured report with the sections below.

## Report Structure

### 1. Session Continuity

\`\`\`bash
if [ -f HANDOFF.md ]; then
    echo "=== HANDOFF.md (from previous session) ==="
    cat HANDOFF.md
    echo ""
    echo "Action: Review, then delete HANDOFF.md when addressed"
fi
\`\`\`

### 2. Workflow Pipeline

Show the brainstorm-to-ship pipeline as a table:

| Phase | Artifacts | Status |
|-------|-----------|--------|
| Brainstorm | `docs/brainstorms/*.md` | N docs (M orphaned) |
| Strategy | `docs/prds/*.md` | N PRDs |
| Plan | `docs/plans/*.md` | N plans (M incomplete) |
| Execute | Recent commits | N commits this week |
| Review | — | (tracked via beads) |
| Ship | — | (tracked via beads) |

For orphaned brainstorms (brainstorm with no matching plan or PRD), list them by name with the suggested next step:

\`\`\`
Orphaned brainstorms (brainstormed but never planned):
  - 2026-02-08-caching-layer-brainstorm.md → Run /clavain:write-plan
  - 2026-02-05-auth-redesign-brainstorm.md → Run /clavain:strategy first
\`\`\`

### 3. Plan Progress

For each plan file with checklist items, show completion:

\`\`\`bash
# Find plans with checkboxes
for f in docs/plans/*.md; do
    [ -f "$f" ] || continue
    total=$(grep -cE '^\s*- \[[ x]\]' "$f" 2>/dev/null || echo 0)
    [ "$total" -eq 0 ] && continue
    done_count=$(grep -cE '^\s*- \[x\]' "$f" 2>/dev/null || echo 0)
    pct=$(( done_count * 100 / total ))
    echo "$(basename "$f"): ${done_count}/${total} (${pct}%)"
done
\`\`\`

Present as:
\`\`\`
Plan progress:
  ████████░░ 2026-02-10-sprint-awareness.md — 8/10 (80%)
  ██░░░░░░░░ 2026-02-09-caching-layer.md   — 2/10 (20%)
\`\`\`

### 4. Beads Health

\`\`\`bash
if command -v bd &>/dev/null && [ -d .beads ]; then
    echo "=== Beads Summary ==="
    bd stats
    echo ""
    echo "=== Stale Issues (5+ days) ==="
    bd stale
    echo ""
    echo "=== In-Progress ==="
    bd list --status=in_progress
fi
\`\`\`

### 5. Skipped Phases (git analysis)

Analyze the last 7 days of commits for workflow discipline:

\`\`\`bash
# Recent commits without bead references
git log --oneline --since="7 days ago" 2>/dev/null | while read -r line; do
    if ! echo "$line" | grep -qE '#[0-9]+|[A-Z]+-[0-9]+|bead|bd-'; then
        echo "  $line"
    fi
done
\`\`\`

Present as:
\`\`\`
Untracked commits (last 7 days):
  abc1234 fix typo in readme
  def5678 add caching to API
  → 2 of 8 commits don't reference tracked work
\`\`\`

### 6. Stuck Work

Cross-reference in-progress beads with recent git activity:

\`\`\`bash
if command -v bd &>/dev/null && [ -d .beads ]; then
    bd list --status=in_progress 2>/dev/null | while read -r line; do
        bead_id=$(echo "$line" | grep -oE '^[0-9]+' || true)
        [ -z "$bead_id" ] && continue
        # Check if bead ID appears in recent commits
        recent=$(git log --oneline --since="3 days ago" --grep="$bead_id" 2>/dev/null | head -1)
        if [ -z "$recent" ]; then
            echo "  $line — no commits in 3 days"
        fi
    done
fi
\`\`\`

### 7. Recommendations

Based on findings, generate 1-3 prioritized recommendations:

**Priority order:**
1. If HANDOFF.md exists → "Review and address the handoff from your previous session"
2. If strategy gap → "Run `/clavain:strategy` to structure your brainstorms into actionable PRDs"
3. If orphaned brainstorms → "Run `/clavain:write-plan` for: [topic]"
4. If incomplete plans < 50% → "Continue executing plan: [name]"
5. If stale beads → "Run `/clavain:triage` to review stale issues"
6. If many untracked commits → "Consider creating beads for ad-hoc work with `bd create`"

Show at most 3 recommendations.

## Output Format

Present the full report using the structure above. Use horizontal rules between sections. End with the recommendations section.
```

### File 5: `tests/structural/test_commands.py` (MODIFY)

Update the command count from 32 to 33.

**Line 23:**
```python
# Before:
assert len(files) == 32, (
    f"Expected 32 commands, found {len(files)}: {[f.stem for f in files]}"
)

# After:
assert len(files) == 33, (
    f"Expected 33 commands, found {len(files)}: {[f.stem for f in files]}"
)
```

### File 6: `tests/shell/session_start.bats` (MODIFY)

Add a test that verifies the sprint scan does not break the existing hook output. The sprint scan is designed to produce empty output when no workflow signals are detected, so the existing tests should continue to pass. But we should add explicit tests:

```bash
@test "session-start: sprint scan does not add output when no signals" {
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        bd() { return 1; }
        export -f curl pgrep bd
        # Run from a temp dir with no docs/ or HANDOFF.md
        cd /tmp
        bash '$HOOKS_DIR/session-start.sh'
    "
    assert_success
    # Should still be valid JSON
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    # Should NOT contain "Sprint status" (no signals in /tmp)
    refute_output --partial "Sprint status"
}

@test "session-start: sprint scan detects HANDOFF.md" {
    local tmpdir=$(mktemp -d)
    echo "## Done" > "$tmpdir/HANDOFF.md"
    run bash -c "
        curl() { return 1; }
        pgrep() { return 1; }
        bd() { return 1; }
        export -f curl pgrep bd
        cd '$tmpdir'
        bash '$HOOKS_DIR/session-start.sh'
    "
    assert_success
    echo "$output" | jq . >/dev/null 2>&1
    assert_success
    assert_output --partial "HANDOFF.md"
    rm -rf "$tmpdir"
}
```

### File 7: `tests/shell/sprint_scan.bats` (NEW)

Dedicated tests for the sprint scanner library functions:

```bash
#!/usr/bin/env bats
# Tests for hooks/sprint-scan.sh

setup() {
    load test_helper
    source "$HOOKS_DIR/sprint-scan.sh"
    export SPRINT_TMPDIR=$(mktemp -d)
    export SPRINT_PROJECT_DIR="$SPRINT_TMPDIR"
}

teardown() {
    rm -rf "$SPRINT_TMPDIR"
}

@test "sprint_check_handoff: returns 1 when no HANDOFF.md" {
    run sprint_check_handoff
    assert_failure
}

@test "sprint_check_handoff: returns 0 when HANDOFF.md exists" {
    echo -e "## Done\n- thing" > "$SPRINT_TMPDIR/HANDOFF.md"
    run sprint_check_handoff
    assert_success
}

@test "sprint_count_orphaned_brainstorms: returns 0 when no brainstorms dir" {
    run sprint_count_orphaned_brainstorms
    assert_output "0"
}

@test "sprint_count_orphaned_brainstorms: returns 0 when brainstorm has matching plan" {
    mkdir -p "$SPRINT_TMPDIR/docs/brainstorms"
    mkdir -p "$SPRINT_TMPDIR/docs/plans"
    touch "$SPRINT_TMPDIR/docs/brainstorms/2026-02-10-caching-brainstorm.md"
    touch "$SPRINT_TMPDIR/docs/plans/2026-02-10-caching.md"
    run sprint_count_orphaned_brainstorms
    assert_output "0"
}

@test "sprint_count_orphaned_brainstorms: counts unmatched brainstorms" {
    mkdir -p "$SPRINT_TMPDIR/docs/brainstorms"
    touch "$SPRINT_TMPDIR/docs/brainstorms/2026-02-10-caching-brainstorm.md"
    touch "$SPRINT_TMPDIR/docs/brainstorms/2026-02-09-auth-brainstorm.md"
    # No plans dir at all
    run sprint_count_orphaned_brainstorms
    assert_output "2"
}

@test "sprint_count_orphaned_brainstorms: matches against PRDs too" {
    mkdir -p "$SPRINT_TMPDIR/docs/brainstorms"
    mkdir -p "$SPRINT_TMPDIR/docs/prds"
    touch "$SPRINT_TMPDIR/docs/brainstorms/2026-02-10-caching-brainstorm.md"
    touch "$SPRINT_TMPDIR/docs/prds/2026-02-11-caching.md"  # Different date, same topic
    run sprint_count_orphaned_brainstorms
    assert_output "0"
}

@test "sprint_find_incomplete_plans: empty when no plans" {
    run sprint_find_incomplete_plans
    assert_output ""
}

@test "sprint_find_incomplete_plans: shows incomplete plans" {
    mkdir -p "$SPRINT_TMPDIR/docs/plans"
    cat > "$SPRINT_TMPDIR/docs/plans/2026-02-10-test.md" <<'PLAN'
# Test Plan
- [x] Step 1
- [ ] Step 2
- [ ] Step 3
PLAN
    run sprint_find_incomplete_plans
    assert_output --partial "1/3 complete"
    assert_output --partial "33%"
}

@test "sprint_brief_scan: empty when project is clean" {
    bd() { return 1; }
    export -f bd
    run sprint_brief_scan
    assert_output ""
}

@test "sprint_brief_scan: shows HANDOFF.md signal" {
    bd() { return 1; }
    export -f bd
    echo "## Done" > "$SPRINT_TMPDIR/HANDOFF.md"
    run sprint_brief_scan
    assert_output --partial "HANDOFF.md"
}
```

### File 8: AGENTS.md and related docs (MODIFY)

Update the component counts and architecture docs:

1. **`AGENTS.md` line 12:** Change `32 commands` to `33 commands`
2. **`AGENTS.md` Architecture section:** Add `sprint-scan.sh` to the hooks listing
3. **`CLAUDE.md`:** Update validation check if it references command count
4. **`skills/using-clavain/SKILL.md`:** Add `/sprint-status` to the routing table under the "Meta" stage and the "Workflow" domain
5. **`commands/help.md`:** Add `/sprint-status` to the Meta section
6. **`plugin.json` description:** Update count from 32 to 33 commands

---

## Implementation Order

### Step 1: Create `hooks/sprint-scan.sh` (the scanner library)

This is the core new file. Implement all functions, test them manually against a real project directory.

**Verification:** `source hooks/sprint-scan.sh` should produce no output. Each function should be individually callable.

### Step 2: Create `commands/sprint-status.md` (the command)

The command that invokes the full scan. Can be tested immediately after Step 1 by running `/clavain:sprint-status` in a project.

**Verification:** Run `/clavain:sprint-status` in a project with brainstorms and beads. Verify all 7 sections render.

### Step 3: Modify `hooks/session-start.sh` (hook integration)

Add the sprint scan sourcing and brief scan call. This is the smallest change but has the highest risk (if it breaks, every session is affected).

**Verification:**
1. Run `bash hooks/session-start.sh` manually — verify valid JSON output.
2. Start a new Claude Code session — verify `additionalContext` includes sprint status (or doesn't, if project is clean).
3. Create a HANDOFF.md and restart — verify it appears.

### Step 4: Update counts and docs

- `tests/structural/test_commands.py` — 32 to 33
- `AGENTS.md` — component count
- `commands/help.md` — add sprint-status
- `skills/using-clavain/SKILL.md` — add to routing table
- `plugin.json` description — update count
- `CLAUDE.md` — update validation command expected count if applicable

**Verification:** `uv run pytest tests/structural/` should pass with the new count.

### Step 5: Create `tests/shell/sprint_scan.bats`

Add the dedicated bats tests for the scanner functions.

**Verification:** `bats tests/shell/sprint_scan.bats` — all tests pass.

### Step 6: Extend `tests/shell/session_start.bats`

Add the two new tests for sprint scan integration in the session-start hook.

**Verification:** `bats tests/shell/session_start.bats` — all tests pass (including existing ones).

---

## Risk Assessment

### Risk 1: Session-start hook becomes slow (MEDIUM)
**Mitigation:** Sprint brief scan avoids all git operations. Beads CLI calls (`bd stats`, `bd stale`) are SQLite queries and return in < 200ms. File system operations (stat, ls, grep) are < 10ms. Total budget: 500ms max, well within the 2-second constraint.

**Monitoring:** Add a timing check in the bats tests (assert completion under 2 seconds).

### Risk 2: Sprint scan output breaks JSON (LOW)
**Mitigation:** Sprint scan uses the same `\\n` escape pattern as all other injected strings in session-start.sh. No user-controlled input flows into the scan output (all strings are from filenames and counts). The `escape_for_json()` function is not needed because the output contains no special characters beyond what's already escaped.

**Testing:** Bats test parses output with `jq .` to verify valid JSON.

### Risk 3: False positives in brainstorm matching (LOW)
**Mitigation:** Substring matching on topic slugs. A brainstorm named `2026-02-10-auth-brainstorm.md` will match a plan named `plan-clavain-auth-redesign.md` because `auth` is a substring. This is by design — false positives (incorrectly showing a brainstorm as orphaned) are briefly annoying but harmless; false negatives (missing a truly orphaned brainstorm) defeat the purpose. The `/sprint-status` command shows the full list so users can evaluate.

### Risk 4: `bd` command not available (LOW)
**Mitigation:** All beads-related checks are gated behind `command -v bd` and `[[ -d .beads ]]`. If either fails, the check is silently skipped. This matches the existing pattern in session-start.sh.

### Risk 5: Adding a command changes test counts (LOW)
**Mitigation:** Explicitly planned as Step 4. The count change from 32 to 33 is a single-line edit in `test_commands.py`. The test is a regression guard, so updating it is expected.

---

## Token Budget Analysis

The using-clavain SKILL.md injected at session start is approximately 3,500 tokens. The companion context, conventions, setup hint, and upstream warning add approximately 200 tokens. Total baseline: ~3,700 tokens.

Sprint brief scan worst case (all signals fire):
```
\n\n**Sprint status:**
- HANDOFF.md: previous session left incomplete work (run `/clavain:sprint-status` for details)
- 3 orphaned brainstorms (no matching plan)
- 2 incomplete plans (lowest: 2026-02-10-caching.md: 2/10 complete (20%))
- Beads: 8 open, 3 stale (5+ days)
- Strategy gap: brainstorms exist but no PRDs
Run `/clavain:sprint-status` for full details.
```

This is approximately 80 tokens. Well within the 500-token budget even in the worst case.

---

## Future Phase 2 Considerations

This design is deliberately forward-compatible with Phase 2 (active workflow state tracking):

1. **The scanner library pattern** (`sprint-scan.sh`) can be extended with new detection functions without modifying session-start.sh.

2. **A `.sprint-state.json` file** could be written by workflow commands (brainstorm, strategy, write-plan, execute-plan) to track the current phase explicitly, rather than inferring it from file artifacts. The scanner would check this file first and fall back to heuristic detection.

3. **The `/sprint-status` command** could evolve to also show a visual pipeline indicator:
   ```
   brainstorm ──→ strategy ──→ [plan] ──→ execute ──→ review ──→ ship
                                  ▲ you are here
   ```

4. **A Stop hook integration** could check sprint state before allowing session end, similar to how session-handoff.sh works but workflow-aware ("You're mid-plan — are you sure you want to stop?").

The key Phase 2 addition would be a `sprint_set_phase()` function called by workflow commands to explicitly record transitions, creating a reliable state machine instead of the Phase 1 heuristic inference.

---

## Summary

| Deliverable | Type | Lines of Code (est.) |
|-------------|------|---------------------|
| `hooks/sprint-scan.sh` | New file | ~180 lines |
| `commands/sprint-status.md` | New file | ~120 lines |
| `hooks/session-start.sh` | Modify | +6 lines |
| `tests/shell/sprint_scan.bats` | New file | ~100 lines |
| `tests/shell/session_start.bats` | Modify | +25 lines |
| `tests/structural/test_commands.py` | Modify | 1 line (count) |
| Docs (AGENTS.md, help.md, using-clavain, plugin.json) | Modify | ~10 lines total |

**Total new code:** ~300 lines of bash + 120 lines of command markdown + 125 lines of tests.
**Total modifications:** ~42 lines across 6 existing files.
