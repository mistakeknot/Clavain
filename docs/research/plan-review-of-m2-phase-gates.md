# Plan Review: M2 Phase Gates Implementation

**Bead:** Clavain-tayp
**Date:** 2026-02-13
**Reviewer:** fd-plan-reviewer agent
**Plan:** docs/plans/2026-02-13-m2-phase-gates.md
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md (F7, F8)

## Executive Summary

**Grade: B+ (Strong plan with minor gaps)**

The plan correctly implements F7 (Tiered Gate Enforcement) and F8 (Discovery Integration with phase awareness) with clean architecture and comprehensive test coverage. All PRD acceptance criteria are addressed with corresponding tasks. The execution order is logical and accounts for dependencies.

**Critical Gaps Identified:**
1. **Missing `/lfg` direct routing** — F8 acceptance criterion not fully implemented
2. **No cache invalidation for phase changes** — discovery cache could show stale phase data
3. **Enforcement function signature incomplete** — `--skip-gate` parsing not specified
4. **Test count underestimated** — 23 tests planned, likely need 28+ for full coverage

**Strengths:**
- Clean separation between interphase (library) and Clavain (command docs)
- Proper fail-safe design (enforcement degrades gracefully)
- Multi-factor scoring is well-designed with clear weights
- Telemetry and audit trail for skip events

## PRD Acceptance Criteria Coverage

### F7: Tiered Gate Enforcement

| AC | Covered? | Plan Task | Notes |
|----|----------|-----------|-------|
| P0/P1 hard gates with `--skip-gate` override | ✅ Yes | Task 1 | `enforce_gate()` implements tier logic |
| P2/P3 soft gates (warn + proceed) | ✅ Yes | Task 1 | Same function, tier-based |
| P4 no gates (tracking only) | ✅ Yes | Task 1 | `tier=none` returns 0 |
| Gate checks verify: (a) phase valid, (b) artifact exists, (c) flux-drive review with no P0 | ⚠️ Partial | Task 1, Task 2 | (a) yes via `check_phase_gate`, (b) implicit via artifact_path arg, (c) **stale review check only** — no P0 findings validation |
| Stale review detection via git log | ✅ Yes | Task 2 | `check_review_staleness()` |
| Stale review = soft warning (not block) for P0/P1 | ✅ Yes | Task 2 | Integration into `enforce_gate` |
| `--skip-gate` recorded in bead notes | ✅ Yes | Task 1 | `bd update --notes` |
| Log gate blocks, skips, stale warnings | ✅ Yes | Task 1 | `_gate_log_enforcement()` telemetry |

**Gap Detail (AC #4):** The PRD says gates should verify "flux-drive review exists with no P0 findings". The plan only checks if the review is stale (artifact modified after review). There's no validation that the review actually passed or checking findings.json for P0 issues. This is likely intentional (stale review check is sufficient to prompt re-review), but it deviates from the PRD's literal wording.

### F8: Work Discovery + Phase Integration

| AC | Covered? | Plan Task | Notes |
|----|----------|-----------|-------|
| Discovery scoring includes phase advancement bonus | ✅ Yes | Task 3 | `phase_score`: executing=30, brainstorm=4 |
| "Ready to advance" beads prioritized | ✅ Yes | Task 3 | Higher phase scores + staleness penalty |
| Phase state shown in AskUserQuestion option text | ✅ Yes | Task 4 | `phase` field added to JSON output |
| `/lfg <bead-id>` routes to correct command based on phase | ❌ **Missing** | Not in plan | F8 last AC not implemented |

**Critical Gap:** Task 4 says "Add `/lfg <bead-id>` direct routing" but doesn't specify the implementation. The plan needs a Task 5 (or Task 4 subtask) to update `commands/lfg.md` to:
1. Parse `$ARGUMENTS` for bead ID pattern
2. Call `phase_get()` to read current phase
3. Route based on phase: `brainstorm` → `/brainstorm`, `planned` → `/write-plan`, `plan-reviewed` → `/work`, `executing` → `/work`, etc.

This is a **required feature** per F8 AC and not just "nice to have" documentation.

## Architecture Review

### Enforcement Tier Logic (Task 1)

**Good:**
- Clean 3-tier model: hard/soft/none
- Priority-based mapping is deterministic (P0/P1=hard, P2/P3=soft, P4=none)
- Fail-safe on missing bead ID (returns 0, allows workflow to proceed)
- Wraps existing `check_phase_gate()` without modifying it (backward compatible)

**Gaps:**
1. **`--skip-gate` parsing not specified:** How does `enforce_gate()` parse the `--reason` argument? Is it:
   - Via bash getopts in the function?
   - Via env var `CLAVAIN_SKIP_GATE_REASON`?
   - Via extra positional args: `enforce_gate <bead> <phase> <artifact> --skip-gate --reason "..."`?

   The function signature in the plan shows the `--skip-gate --reason` pattern but doesn't specify the parsing implementation. This needs a code example or explicit design decision.

2. **No validation that `bd update --notes` succeeded:** If `bd` is unavailable or the bead was deleted mid-execution, the skip note won't be recorded. The plan should note this as a known limitation (fail-safe means audit trail is best-effort, not guaranteed).

3. **P0 findings validation missing:** As noted above, the PRD says gates should check for P0 findings in `findings.json`. The plan only checks staleness. If this is intentional (simpler, sufficient), document it as a design decision.

### Stale Review Detection (Task 2)

**Good:**
- Clean git log approach: `git log --since=<review_date> -- <artifact_path>`
- Correctly derives review dir from artifact path
- Returns `fresh|stale|none` (clear sentinel values)

**Gaps:**
1. **No error handling for missing findings.json:** If `findings.json` exists but is malformed JSON, `jq` fails. The function should return `none` (not crash) if jq fails.
2. **No handling of multi-file reviews:** flux-drive can review multiple files as a batch. If the plan was part of a multi-file review, the `findings.json` path derivation might be wrong. This is a known limitation from the existing flux-drive convention — document it.
3. **Git submodule edge case:** If the artifact is in a submodule, `git log` must run in the submodule's directory. The function doesn't account for this. Mark as "not supported for submodules" or add `--git-dir` handling.

### Multi-Factor Scoring (Task 3)

**Good:**
- Well-designed weights: priority dominates (40 points), phase is secondary (30), recency is tertiary (20)
- Staleness penalty (−10) is appropriate — noticeable but not overwhelming
- Deterministic tiebreaker (sort by id ASC after score DESC)

**Potential Issues:**
1. **Phase score for `executing` vs `shipping` is the same (30):** Is this intentional? A bead at `shipping` is closer to done than one at `executing`. Consider: executing=28, shipping=30.
2. **Recency score is coarse (4 buckets):** <24h=20, 24-48h=15, 48h-7d=10, >7d=5. This means a bead updated 25 hours ago scores the same as one updated 47 hours ago. Fine for v1, but document as "coarse-grained recency" so future iterations can refine if needed.
3. **No bonus for in-progress beads:** The PRD talks about "in-progress beads shown separately from ready-to-start beads" (F1 AC). The phase scoring doesn't distinguish `executing` (in-progress) from `plan-reviewed` (ready-to-start). This is handled by status field in JSON, but the scoring doesn't reflect it. Consider: add +5 bonus for status=in_progress if phase scoring alone isn't enough.

### Phase Display in Discovery (Task 4)

**Good:**
- Adds `phase` field to JSON output (required for F8)
- Updates `infer_bead_action()` to be phase-aware (smarter routing)

**Gaps:**
1. **Direct bead-id routing not implemented:** As noted above, this is a PRD acceptance criterion but not in the plan.
2. **Action verb mapping incomplete:** The plan says "if phase is set, use it to determine action more precisely" but doesn't give the full mapping. Should be:
   - phase=brainstorm → action=`strategize` (not `brainstorm`)
   - phase=brainstorm-reviewed → action=`strategize`
   - phase=strategized → action=`plan`
   - phase=planned → action=`execute`
   - phase=plan-reviewed → action=`execute` (not `continue`)
   - phase=executing → action=`continue`
   - phase=shipping → action=`ship` or `resolve`
   - phase=done → skip (bead is closed)

   The plan's example gives two mappings but doesn't cover the full phase model. This needs to be complete or the `infer_bead_action` logic will have gaps.

3. **Cache invalidation missing:** `discovery_brief_scan()` uses a 60-second TTL cache. If a phase changes (via `advance_phase()`), the cache won't reflect it until TTL expires. This can cause the statusline or brief scan to show stale phase data. Task 4 should note: invalidate cache on phase change, or document the 60s lag as acceptable.

## Command Integration (Task 5)

**Good:**
- Correctly identifies the 4 commands that need enforcement: `lfg.md`, `quality-gates.md`, `work.md`, `execute-plan.md`
- Provides a clear pattern for enforcement call before `advance_phase()`

**Gaps:**
1. **No diff showing exact placement:** The task says "add enforcement gate calls before `advance_phase()`" but doesn't show where in each command's markdown the code should go. For example:
   - In `work.md`, enforcement should happen in **Phase 1b** (before execution starts), not Phase 4 (after shipping).
   - In `quality-gates.md`, enforcement should happen in **Phase 5b** (only on PASS), not Phase 1.

   The task needs line number references or a "before this heading" marker for each command.

2. **Error message incomplete:** The pattern shows:
   ```bash
   echo "Gate blocked: run /clavain:flux-drive first or use --skip-gate --reason '...'"
   ```
   This assumes the user knows how to pass `--skip-gate` to the command. But the commands are invoked via slash syntax (`/clavain:work <plan>`). How does the user pass `--skip-gate`? Options:
   - Add a new command arg: `/clavain:work <plan> --skip-gate --reason "urgent fix"`
   - Set an env var: `export CLAVAIN_SKIP_GATE="reason"` before calling the command
   - Add a new command: `/clavain:force-advance <bead-id> <target-phase> --reason "..."`

   The plan must specify this. Without it, `--skip-gate` is theoretically available but practically unusable.

3. **No `lfg.md` update for direct routing:** Task 5 updates 4 commands but doesn't mention updating `lfg.md` for the `/lfg <bead-id>` direct routing feature (F8 AC). This should be a separate subtask.

## Test Coverage (Task 6)

**Good:**
- 23 tests planned (15 gates, 8 discovery) — comprehensive scenarios
- Covers happy paths, edge cases, and fail-safes
- Includes telemetry validation (JSONL structure checks)

**Gaps:**
1. **Test count underestimated:** The plan lists 23 tests, but based on the number of functions and edge cases, likely need 28+:
   - **gates.bats:** add 3 tests:
     - `enforce_gate`: no artifact path provided (should succeed — artifact is optional)
     - `check_review_staleness`: findings.json is malformed JSON (should return `none`)
     - `enforce_gate`: bd show fails mid-check (bead deleted after priority read)
   - **discovery.bats:** add 2 tests:
     - `score_bead`: in-progress status bonus (if implemented)
     - `discovery_scan_beads`: phase field present in output (explicit validation)

2. **No integration test for `--skip-gate` flow:** The tests validate `enforce_gate` returns 0 when `--skip-gate` is set, but there's no test for the full command flow:
   1. User calls `/clavain:work <plan> --skip-gate --reason "urgent"`
   2. Command parses args and passes to `enforce_gate`
   3. Skip is recorded in bead notes
   4. Telemetry logs the skip event

   This needs a smoke test or an interphase test that sources `lib-gates.sh` and simulates the command call.

3. **No test for cache invalidation on phase change:** If Task 4 adds cache invalidation (or documents the lag as acceptable), there should be a test: "brief_scan returns updated phase after advance_phase, ignoring cache TTL."

## Execution Order Review

The plan shows:
```
[Task 1: enforce_gate] ──┐
[Task 2: stale review]  ─┤── [Task 5: command docs] ── [Task 6: tests] ── [Task 7: publish]
[Task 3: scoring]  ──────┤
[Task 4: phase display] ─┘
```

**Correct:** Tasks 1-4 are independent and can be parallelized. Task 5 depends on Task 1 (needs `enforce_gate` signature). Task 6 depends on Tasks 1-4 (tests all new code). Task 7 is last (after tests pass).

**Issue:** Task 5 also depends on Task 4 indirectly — if `/lfg <bead-id>` routing (F8 AC) is part of Task 5, then it needs `phase_get()` from lib-phase.sh (already exists) and the phase-aware action mapping from Task 4. The dependency diagram should show Task 5 depends on both Task 1 and Task 4.

## Risk Mitigation Review

**Performance concern is correct:** `bd state <id> phase` adds one call per bead. For 40 beads, ~2s overhead. The plan correctly notes this is acceptable for on-demand discovery but may need caching in F4 brief scan.

**Mitigation recommendation:** Add a note in Task 3 or Task 4 to batch `bd state` calls if beads CLI supports it (check `bd state --batch <id1> <id2> ...`). If not, document the 2s overhead as acceptable for v1 and defer batching to F9 (performance iteration).

**Backward compatibility claim is correct:** `enforce_gate()` is new, `check_phase_gate()` unchanged. No breakage.

**Fail-safe claim is mostly correct:** All new functions inherit the pattern (return 0 on error). Exception: if `bd update --notes` fails when recording a skip, the skip isn't audited. This is acceptable (telemetry still logs it) but should be documented as a known limitation.

## Missing Considerations

### 1. Enforcement Override Mechanism

The plan defines `--skip-gate` but doesn't specify:
- How users invoke it (command syntax)
- Whether skips have a TTL (single-use or persistent?)
- Who can skip (any user or admin-only?)

This needs a design decision: is `--skip-gate` a per-command flag, or a per-bead persistent state? If persistent, add a `bd clear-skip <bead-id>` command to reset it after re-review.

### 2. Discovery Ranking Validation

The PRD says: "Log which option user selects (for post-launch validation)." The plan implements `discovery_log_selection()` telemetry, but there's no tooling to analyze the logs. Task 7 (publish) should include a follow-up note: "After 2 weeks, run `jq 'select(.event=="discovery_select")' ~/.clavain/telemetry.jsonl | jq -s 'group_by(.recommended) | map({recommended: .[0].recommended, count: length})'` to check if recommended picks >70%."

### 3. Phase Desyncs

Task 2 detects **stale reviews** (artifact newer than review). But there's another desync scenario: **phase in beads != phase in artifact header**. This is already handled by `phase_get_with_fallback()` (warns on desync, returns beads phase). Task 5 should note: if desync warnings appear frequently, run a one-time sync script to align artifact headers with beads state.

### 4. Multi-Bead Plans

Some plans reference multiple beads (e.g., PRD with child feature beads). When `phase_infer_bead()` finds multiple bead IDs in an artifact, it warns and returns the first match. The plan doesn't address this scenario for enforcement:
- If a plan has 3 bead IDs, which one's phase is checked?
- Should enforcement require ALL beads to be plan-reviewed, or just the first one?

This is edge-case but worth noting: "For multi-bead plans, enforcement checks only the CLAVAIN_BEAD_ID (set by discovery routing). If no env var is set, enforcement is skipped (no bead context)."

## Specific Implementation Recommendations

### Task 1: `enforce_gate()` Signature

Add this to the plan:
```bash
# Parse --skip-gate via getopts-style suffix check
enforce_gate() {
    local bead_id="$1" target="$2" artifact_path="${3:-}" skip_reason=""
    shift 3 2>/dev/null || true

    # Parse remaining args for --skip-gate
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-gate) shift; skip_reason="${1:-}" ;;
            --reason) shift; skip_reason="${1:-}" ;;
        esac
        shift
    done

    # ... tier logic ...
}
```

Or use env var approach (simpler, no arg parsing):
```bash
# Commands set CLAVAIN_SKIP_GATE="reason" before calling enforce_gate
enforce_gate() {
    local skip_reason="${CLAVAIN_SKIP_GATE:-}"
    # ... tier logic ...
    if [[ -n "$skip_reason" ]]; then
        # record skip, return 0
    fi
}
```

Recommend env var approach for simpler command integration.

### Task 3: Phase Score Table

Add this table to the plan for clarity:
| Phase | Score | Rationale |
|-------|-------|-----------|
| executing | 30 | Highest — work in progress, should be top priority |
| shipping | 30 | Same as executing — ready to ship, equally urgent |
| plan-reviewed | 24 | Ready to start, next in line |
| planned | 18 | Has plan, needs review |
| strategized | 12 | Has PRD, needs plan |
| brainstorm-reviewed | 8 | Initial review done, needs strategy |
| brainstorm | 4 | Fresh idea, needs review |
| none | 0 | No phase set (first touch) |

If `shipping` should rank higher than `executing`, use 32 for shipping.

### Task 4: Action Verb Mapping

Add this to the plan:
```bash
infer_bead_action() {
    # ... existing filesystem scan ...
    local phase=""
    if command -v phase_get &>/dev/null && [[ -n "$bead_id" ]]; then
        phase=$(phase_get "$bead_id" 2>/dev/null) || phase=""
    fi

    # Phase-aware action inference (overrides filesystem-based logic)
    case "$phase" in
        brainstorm) echo "strategize|$brainstorm_path"; return 0 ;;
        brainstorm-reviewed) echo "strategize|$brainstorm_path"; return 0 ;;
        strategized) echo "plan|$prd_path"; return 0 ;;
        planned) echo "execute|$plan_path"; return 0 ;;
        plan-reviewed) echo "execute|$plan_path"; return 0 ;;
        executing) echo "continue|$plan_path"; return 0 ;;
        shipping) echo "ship|"; return 0 ;;
        done) echo "closed|"; return 0 ;;
    esac

    # Fallback to filesystem-based inference if no phase
    # ... existing priority logic ...
}
```

### Task 5: Enforcement Placement

Add line references:
- **lfg.md line 73:** After `advance_phase` call for each step, before executing the next step
- **quality-gates.md line 107:** In Phase 5b, before `advance_phase "shipping"`
- **work.md line 52:** In Phase 1b, before `advance_phase "executing"`
- **execute-plan.md line 8:** Before the first `advance_phase "executing"` call

## Recommended Changes

### High Priority (Required for PRD Compliance)

1. **Add F8 direct routing implementation:**
   - Update Task 5 to include `/lfg <bead-id>` routing logic
   - Pattern: parse `$ARGUMENTS` for bead ID, call `phase_get`, route based on phase
   - Add 2 tests: valid bead ID routes correctly, invalid bead ID shows error

2. **Specify `--skip-gate` invocation mechanism:**
   - Choose: env var (`CLAVAIN_SKIP_GATE`) or args parsing
   - Update Task 5 to show how users pass the flag to commands
   - Add 1 integration test for full skip flow

3. **Complete action verb mapping:**
   - Add full phase-to-action table to Task 4
   - Ensure all 8 phases have a defined action

### Medium Priority (Quality Improvements)

4. **Add cache invalidation on phase change:**
   - Update Task 4: invalidate `/tmp/clavain-discovery-brief-*.cache` after `advance_phase()`
   - Or document 60s lag as acceptable
   - Add 1 test if implemented

5. **Add 5 missing tests:**
   - enforce_gate with no artifact path
   - check_review_staleness with malformed findings.json
   - discovery phase field validation
   - full skip flow integration
   - cache invalidation (if implemented)

6. **Document multi-bead plan enforcement:**
   - Add note in Task 1: "For multi-bead plans, enforcement checks CLAVAIN_BEAD_ID only. Set explicitly via env var before calling enforce_gate."

### Low Priority (Nice to Have)

7. **Add telemetry analysis tooling:**
   - Task 7: include post-launch validation query in publish checklist
   - `jq 'select(.event=="discovery_select")' ~/.clavain/telemetry.jsonl | jq -s ...`

8. **Add P0 findings validation:**
   - If this is intended, update Task 2 to check `findings.json` for `.findings[] | select(.severity == "P0") | length == 0`
   - If not intended, document as design decision: "Stale review check is sufficient; P0 validation deferred to user re-running flux-drive"

9. **Refine phase scoring:**
   - Consider: executing=28, shipping=30 (shipping is closer to done)
   - Or add in-progress status bonus: +5 if status=in_progress

## Summary of Findings

### Critical (Must Fix)
- **F8 direct routing missing** — Task 5 must implement `/lfg <bead-id>` routing
- **`--skip-gate` invocation not specified** — Choose env var or args parsing, update Task 5
- **Action verb mapping incomplete** — Task 4 needs full phase-to-action table

### Important (Should Fix)
- **Test count underestimated** — Add 5 missing tests (28 total, not 23)
- **Enforcement placement not specified** — Task 5 needs line references for where to insert code
- **Cache invalidation missing** — Task 4 should invalidate on phase change or document lag

### Suggestions (Nice to Have)
- Document multi-bead plan enforcement behavior
- Add telemetry analysis tooling for post-launch validation
- Clarify P0 findings validation intent (is stale-review-only intentional?)
- Refine phase scoring (shipping vs executing)

## Final Grade Justification

**B+ (85/100)**

**Why not A:**
- F8 direct routing is a PRD requirement but not fully implemented in the plan (−5 points)
- `--skip-gate` invocation mechanism is undefined, making the feature theoretically complete but practically incomplete (−5 points)
- Test coverage gaps and missing line references reduce implementation confidence (−5 points)

**Why not C:**
- All core logic is sound and architecturally clean
- Fail-safe design is correct and well-thought-out
- Most PRD acceptance criteria are covered with clear tasks
- Multi-factor scoring is well-designed

**To reach A grade:** Fix the 3 critical gaps (direct routing, skip invocation, action mapping) and add the 5 missing tests. The plan would then be fully PRD-compliant with high implementation confidence.
