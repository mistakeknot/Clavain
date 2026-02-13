# Correctness Review: M2 Phase Gates Implementation Plan

**Reviewer:** Julik (fd-correctness agent)
**Date:** 2026-02-13
**Plan:** docs/plans/2026-02-13-m2-phase-gates.md
**Bead:** Clavain-tayp (M2 Phase Gates)

## Executive Summary

This plan adds tiered gate enforcement and multi-factor scoring to bash shell scripts in interphase. Found **6 high-consequence correctness issues** and **3 medium-risk concerns** that must be addressed before implementation.

**Critical findings:**
1. Phase cycling gap: `shipping:planned` re-entry missing from VALID_TRANSITIONS
2. Stale review detection has 3 failure modes (renamed files, multi-artifact plans, missing findings.json)
3. Argument parsing footgun: `--skip-gate --reason "..."` after positional args
4. Race condition in priority read (low practical risk but requires defense)
5. Scoring math edge case: stale P4 can outscore fresh P2
6. bd update --append-notes exists but has no error handling specified

## High-Consequence Issues

### H1: Phase Cycling Failure (Severity: HIGH)

**Problem:** The plan's example shows Clavain-tayp going from `shipping` → `planned` to re-enter for M2 work, but `VALID_TRANSITIONS` in lib-gates.sh does NOT include `shipping:planned`.

**Evidence:**
```bash
# Current VALID_TRANSITIONS (lib-gates.sh:22-43)
VALID_TRANSITIONS=(
    ":brainstorm"
    # ... many entries ...
    "executing:shipping"
    "shipping:done"
    # MISSING: "shipping:planned"
    # ... skip paths ...
)
```

The plan metadata shows:
```
**Phase:** planned (as of 2026-02-13T22:39:48Z)
```

But the bead was previously in `shipping` phase (it was a shipped feature scope). This transition would be BLOCKED by `is_valid_transition()`.

**Failure scenario:**
1. User invokes `/clavain:plan` on Clavain-tayp (currently `shipping`)
2. `enforce_gate("Clavain-tayp", "planned", "docs/plans/m2.md")` is called
3. `check_phase_gate()` calls `is_valid_transition("shipping", "planned")`
4. Returns 1 (blocked) because `shipping:planned` not in VALID_TRANSITIONS
5. For P2 bead, this produces soft warning, but **semantic intent is violated**
6. For P0/P1 beads in same situation, would be HARD BLOCKED

**Impact:** Phase cycling (returning to earlier phase for new scope) is a legitimate workflow pattern but currently unsupported by the phase graph.

**Fix:**
Add to VALID_TRANSITIONS:
```bash
"shipping:planned"         # Re-scope after shipping
"done:brainstorm"          # New iteration after completion
"done:planned"             # Related follow-up work
```

Or establish a "re-entry" rule: any phase can transition back to `:brainstorm` or `:planned` for new scope.

**Test required:**
```bash
@test "enforce_gate: allows shipping → planned re-entry" {
    # Setup: bead at shipping phase
    phase_set "test-bead" "shipping" "shipped v1"

    # Execute: attempt transition to planned
    run enforce_gate "test-bead" "planned" "docs/plans/v2.md"

    # Verify: transition allowed (return 0)
    assert_success
}
```

---

### H2: Stale Review Detection Has 3 Failure Modes (Severity: HIGH)

**Problem:** Task 2's `check_review_staleness()` design assumes:
1. Review dir name derivation matches artifact path (it may not)
2. One review per artifact (plans can reference multiple artifacts)
3. findings.json always exists if a review happened (git log may show older reviews before findings.json format)

**Failure Mode 1: Stem derivation mismatch**

Plan says:
```
Derives review dir: docs/research/flux-drive/{stem}/findings.json
```

But "stem" derivation is undefined. Common approaches:
- basename without extension: `docs/plans/2026-02-13-m2-phase-gates.md` → `2026-02-13-m2-phase-gates`
- basename with date stripped: → `m2-phase-gates`
- bead ID: → `Clavain-tayp`

If the review dir is `docs/research/flux-drive/phase-gates-m2/` (human-chosen name), stem matching fails and review is missed.

**Failure Mode 2: Multi-artifact plans**

A plan might reference:
- `docs/plans/m2-phase-gates.md` (plan itself)
- `docs/prds/phase-gated-lfg.md` (PRD)
- Existing code in `interphase/hooks/lib-gates.sh`

Git log check only looks at ONE artifact path. If the review was triggered by the PRD but the plan was edited later, staleness check looks at the wrong file.

**Failure Mode 3: Missing findings.json**

Plan says:
```
Reads "reviewed" date from findings.json via jq
```

But what if:
- Old review used a different format (before findings.json existed)
- Review is still running (findings.json not written yet)
- Review dir exists but findings.json was deleted/corrupted

The plan says "Returns: `none` if no review found" — this is WRONG semantic. Missing findings.json should return `unknown` or `error`, not `none`. `none` implies "definitely no review exists" when the truth is "cannot determine review state".

**Failure scenario:**
```bash
# Timeline:
# 2026-02-12 10:00 - flux-drive reviews docs/plans/foo.md
#                    creates docs/research/flux-drive/plan-foo/findings.json
# 2026-02-13 14:00 - User renames docs/plans/foo.md → docs/plans/bar.md
# 2026-02-13 15:00 - User edits docs/plans/bar.md
# 2026-02-13 16:00 - enforce_gate called with artifact=docs/plans/bar.md

# Step 1: check_review_staleness("docs/plans/bar.md")
# Step 2: Derive stem → "bar"
# Step 3: Look for docs/research/flux-drive/bar/findings.json
# Step 4: Not found (actual review is in plan-foo/)
# Step 5: Return "none"
# Step 6: No staleness warning issued
# Step 7: Gate passes even though review is stale
```

**Impact:** False negatives — stale reviews not detected, soft warnings not issued, users ship unreviewed changes.

**Fix:**

Replace stem-based matching with **content-based matching**:
1. Scan `docs/research/flux-drive/*/findings.json` for `"artifact"` field matching the target path
2. If not found, scan for `"bead_id"` field matching the current bead
3. Read `"reviewed"` timestamp
4. Git log check: `git log --since="$reviewed_date" -- "$artifact_path"`
5. If commits exist after review → `stale`
6. If no review metadata found → `unknown` (not `none`)
7. Return BOTH staleness and review path so enforce_gate can log which review was used

**Error handling:**
- Missing findings.json but dir exists → `unknown` + warning to stderr
- No review dir at all → `none`
- jq parse failure → `error` + fail-safe to no-gate (return 0)
- git log failure → `error` + fail-safe to no-gate

**Test required:**
```bash
@test "check_review_staleness: handles renamed artifact" {
    # Setup: create review for old path
    mkdir -p docs/research/flux-drive/test-review
    echo '{"artifact":"docs/plans/old.md","reviewed":"2026-02-12T10:00:00Z"}' \
        > docs/research/flux-drive/test-review/findings.json

    # Execute: check staleness for renamed path
    run check_review_staleness "Clavain-test" "docs/plans/new.md"

    # Verify: returns "unknown" not "none"
    assert_output --partial "unknown"
}
```

---

### H3: Argument Parsing Footgun (Severity: MEDIUM-HIGH)

**Problem:** The plan's API for `enforce_gate` is:
```bash
enforce_gate <bead_id> <target_phase> [artifact_path] [--skip-gate --reason "..."]
```

This mixes positional args with `--` flag parsing, which is error-prone in bash because:
1. `artifact_path` is optional, so parser doesn't know if arg 3 is a path or `--skip-gate`
2. `--reason` takes a quoted string which may contain spaces
3. Bash's `$@` and shift-based parsing is fragile with optional args

**Failure scenario:**
```bash
# User invokes:
enforce_gate "Clavain-xxx" "executing" --skip-gate --reason "Product decision"

# Bash sees:
# $1=Clavain-xxx
# $2=executing
# $3=--skip-gate
# $4=--reason
# $5=Product decision  # WRONG: quoted string split into separate args

# Parser logic (naive):
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-gate) skip_gate=true; shift ;;
        --reason) reason="$2"; shift 2 ;;  # Assumes next arg is full reason
        *) artifact_path="$1"; shift ;;
    esac
done

# Result:
# artifact_path="--skip-gate"  # WRONG
# skip_gate=true
# reason="Product"  # WRONG: only first word
```

**Impact:**
- `--skip-gate` flag may be silently ignored if parsed as artifact_path
- Audit trail gets partial reason strings
- Telemetry logs are corrupted

**Fix Option 1: Require artifact_path (no optional args)**
```bash
enforce_gate <bead_id> <target_phase> <artifact_path> [--skip-gate --reason "..."]
# If no artifact, pass empty string: enforce_gate "..." "..." "" --skip-gate
```

**Fix Option 2: Use environment variable for flags**
```bash
CLAVAIN_SKIP_GATE=true CLAVAIN_SKIP_REASON="..." enforce_gate <bead_id> <target> [artifact]
```

**Fix Option 3: Use proper getopt parsing**
```bash
# Parse flags first, then positional args
local skip_gate=false reason="" args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-gate) skip_gate=true; shift ;;
        --reason) reason="$2"; shift 2 ;;
        --) shift; args+=("$@"); break ;;  # End of flags
        -*) echo "Unknown flag: $1" >&2; return 1 ;;
        *) args+=("$1"); shift ;;
    esac
done

# Extract positional args
bead_id="${args[0]}"
target_phase="${args[1]}"
artifact_path="${args[2]:-}"  # Optional
```

**Recommendation:** Use Fix Option 3 with `--` separator support so commands can pass artifacts with dashes:
```bash
enforce_gate "Clavain-xxx" "executing" -- docs/plans/--weird-name.md --skip-gate --reason "..."
```

**Test required:**
```bash
@test "enforce_gate: parses --reason with spaces correctly" {
    run enforce_gate "test-bead" "executing" "docs/plans/test.md" \
        --skip-gate --reason "Product decision: defer review to M3"

    # Verify: full reason string captured in bd notes
    run bd show test-bead --json
    assert_output --partial "Product decision: defer review to M3"
}
```

---

### H4: Race Condition in Priority Read (Severity: LOW, Defense-in-Depth Required)

**Problem:** Task 1 says:
```
get_enforcement_tier() — reads bead priority via `bd show <id> --json | jq '.priority'`
```

Then:
```
enforce_gate():
  - Calls check_phase_gate() to validate transition
  - If invalid + tier=hard + no --skip-gate → return 1
```

Between the `bd show` call and the `return 1` decision, another process could call `bd update <id> --priority 4` to downgrade the bead to P4 (no-gate tier).

**Timing:**
```
T0: enforce_gate() starts
T1: bd show returns {priority: 0}  (P0 = hard block)
T2: get_enforcement_tier() returns "hard"
T3: check_phase_gate() returns 1 (invalid transition)
T4: <== RACE WINDOW ==> Another agent calls `bd update --priority 4`
T5: enforce_gate() returns 1 (hard block) even though bead is now P4
T6: User sees "Gate blocked" message for a P4 bead
```

**Practical risk:** LOW because:
- Human-in-the-loop workflow (unlikely two agents modifying same bead simultaneously)
- bd update is not typically automated
- Worst case is a false hard block, which user can override with `--skip-gate`

**However:** This violates the **tier semantics** — P4 should NEVER hard block. The decision to block must be based on priority at decision time, not read time.

**Fix:**

Add a second priority read just before returning 1:
```bash
enforce_gate() {
    local bead_id="$1"
    local target="$2"
    local artifact_path="${3:-}"

    # Parse flags...

    # Read priority (first read for tier)
    local tier
    tier=$(get_enforcement_tier "$bead_id") || tier="none"

    # Check phase gate
    if ! check_phase_gate "$bead_id" "$target" "$artifact_path"; then
        # Invalid transition

        # Re-read priority just before blocking (TOCTOU mitigation)
        local tier_recheck
        tier_recheck=$(get_enforcement_tier "$bead_id") || tier_recheck="none"

        if [[ "$tier_recheck" == "none" ]]; then
            # Priority changed to P4 during execution → allow
            _gate_log_enforcement "$bead_id" "4" "none" "pass-race" "$reason"
            return 0
        fi

        # Proceed with original tier logic...
        if [[ "$tier_recheck" == "hard" && "$skip_gate" != "true" ]]; then
            echo "ERROR: phase gate blocked $target (tier=$tier_recheck)" >&2
            _gate_log_enforcement "$bead_id" "?" "$tier_recheck" "block" "$reason"
            return 1
        fi
        # ... rest of logic
    fi

    # Valid transition
    return 0
}
```

**Alternative fix:** Use `bd show --json` atomic read with combined priority + phase + updated_at in a single call, then base ALL decisions on that snapshot. This eliminates multiple bd calls and ensures consistency.

**Test (requires concurrency):**
```bash
@test "enforce_gate: re-checks priority before hard block" {
    # Setup: P0 bead at brainstorm phase
    phase_set "test-bead" "brainstorm" "initial"
    bd update test-bead --priority 0

    # Background: downgrade to P4 after 0.1s delay
    (sleep 0.1; bd update test-bead --priority 4) &

    # Execute: attempt invalid transition (takes >0.1s due to subprocess overhead)
    run enforce_gate "test-bead" "executing"

    # Verify: should NOT hard block because priority changed to P4
    assert_success
}
```

---

### H5: Scoring Math Edge Case — Stale P4 Can Outscore Fresh P2 (Severity: MEDIUM)

**Problem:** Task 3's scoring formula:
```
priority_score: P0=40, P1=32, P2=24, P3=16, P4=8
phase_score: executing=30, ..., brainstorm=4
recency_score: <24h=20, 24-48h=15, 48h-7d=10, >7d=5
staleness_penalty: stale=-10
```

**Edge case:**
- Bead A: P2 (24) + brainstorm (4) + updated 1d ago (15) + fresh (0) = **43**
- Bead B: P4 (8) + executing (30) + updated 1h ago (20) + stale (-10) = **48**

Bead B ranks HIGHER even though:
- It's low priority (P4 = "nice to have")
- It's stale (review out of date)
- Bead A is higher priority (P2 = "should have")

**Is this correct?**

Arguments FOR current formula:
- Phase advancement matters more than priority — in-progress work (executing) should surface above open work (brainstorm)
- Staleness is just a warning flag, not a blocker
- Users can sort by priority if they want priority-first ranking

Arguments AGAINST:
- P2 is 3x higher priority than P4 (24 vs 8), but that difference can be overcome by phase+recency
- Stale work should be heavily penalized — it may be based on outdated assumptions
- Discovery is for "what should I work on next", not "what's already in progress" (that's what bd list --status=in_progress is for)

**Impact:** Unexpected ranking where low-priority stale work appears above high-priority fresh work. Users may miss important P2 brainstorms because a stale P4 execution task is ranked first.

**Fix Option 1: Increase staleness penalty**
```
staleness_penalty: stale=-20 (not -10)
```
Now Bead B = 8+30+20-20 = 38 < 43 (Bead A wins)

**Fix Option 2: Add priority weighting**
```
priority_score: P0=60, P1=48, P2=36, P3=24, P4=12
# Doubles the gap so phase can't overcome a 2-tier priority difference
```
Now Bead A = 36+4+15+0 = 55 > 48 (Bead A wins)

**Fix Option 3: Separate discovery modes**
```
discovery_scan_beads --mode=priority-first  # P0-P4 sort, then phase
discovery_scan_beads --mode=progress-first  # Phase sort, then priority
```

**Recommendation:** Use Fix Option 2 (increase priority weighting). Priority is a **strategic** signal (business value), phase is a **tactical** signal (work state). Strategic should outweigh tactical in discovery ranking.

**Test required:**
```bash
@test "score_bead: P2 fresh brainstorm outscores P4 stale execution" {
    # Setup: two beads
    bd create --id test-p2 --priority 2 --status open
    bd create --id test-p4 --priority 4 --status in_progress
    phase_set test-p2 "brainstorm" "initial"
    phase_set test-p4 "executing" "in progress"

    # Mark test-p4 as stale (plan older than 2 days)
    echo "# Plan" > docs/plans/test-p4.md
    touch -t 202602110000 docs/plans/test-p4.md  # 2 days ago

    # Execute: scan and score
    local results
    results=$(discovery_scan_beads)

    # Verify: test-p2 should rank ABOVE test-p4
    local first_id
    first_id=$(echo "$results" | jq -r '.[0].id')
    assert_equal "$first_id" "test-p2"
}
```

---

### H6: bd update --append-notes Error Handling (Severity: MEDIUM)

**Problem:** Task 1 says:
```
Records --skip-gate in bead notes via bd update --notes
```

But plan line 50 uses `bd update --notes` (overwrite), not `--append-notes` (append). The bd help shows both exist:
```
--append-notes string    Append to existing notes (with newline separator)
--notes string           Additional notes
```

**Ambiguity 1: Which flag to use?**

Plan intent is to ADD skip-gate audit trail to existing notes, so `--append-notes` is correct. But the plan text says `--notes` which would OVERWRITE existing notes, losing any prior audit entries.

**Ambiguity 2: Error handling**

What if:
- bd update fails (permission denied, .beads corrupted, etc.)
- Skip-gate decision is lost
- User never sees the audit trail
- Telemetry logs it but beads doesn't

Should `enforce_gate` fail (return 1) if audit trail write fails? Or fail-safe (return 0 with warning)?

**Current pattern in lib-gates.sh:** All functions are fail-safe (return 0 on error). But audit trail write failure is different — it's a **compliance** failure, not a workflow failure.

**Fix:**

Clarify in plan:
```bash
# Record skip in audit trail (fail-safe — workflow continues even if write fails)
local audit_entry="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Gate skipped: $target (tier=$tier, reason: $reason)"
if ! bd update "$bead_id" --append-notes "$audit_entry" 2>/dev/null; then
    echo "WARNING: failed to write skip-gate audit entry for $bead_id" >&2
    _gate_log_enforcement "$bead_id" "?" "$tier" "skip-audit-fail" "$reason"
fi
# Continue with return 0 (workflow is not blocked)
```

**Alternative:** If audit trail is MANDATORY, return 1 on write failure:
```bash
if ! bd update "$bead_id" --append-notes "$audit_entry" 2>&1; then
    echo "ERROR: cannot record skip-gate audit trail for $bead_id" >&2
    echo "Enforcement blocked until audit write succeeds" >&2
    return 1  # Hard block
fi
```

**Recommendation:** Fail-safe approach with telemetry fallback. Telemetry is append-only JSONL (higher durability) and survives even if beads database is corrupted.

**Test required:**
```bash
@test "enforce_gate: skip-gate writes audit trail to notes" {
    # Setup: P0 bead at brainstorm phase
    bd create --id test-bead --priority 0 --status open
    phase_set test-bead "brainstorm" "initial"

    # Execute: skip gate with reason
    run enforce_gate test-bead executing docs/plans/test.md \
        --skip-gate --reason "Emergency hotfix"
    assert_success

    # Verify: notes field contains audit entry
    run bd show test-bead --json
    assert_output --partial "Gate skipped: executing"
    assert_output --partial "Emergency hotfix"
}

@test "enforce_gate: continues on audit write failure" {
    # Setup: make .beads read-only to force bd update failure
    chmod -R 444 .beads

    # Execute: skip gate (should succeed despite write failure)
    run enforce_gate test-bead executing "" --skip-gate --reason "test"
    assert_success

    # Verify: warning emitted
    assert_output --partial "WARNING: failed to write skip-gate audit entry"

    # Cleanup
    chmod -R 755 .beads
}
```

---

## Medium-Risk Concerns

### M1: Performance Degradation in Discovery with 40+ Beads

**Issue:** Plan Risk Mitigation section says:
```
`bd state <id> phase` adds one `bd` call per bead in discovery. For 40 beads, this is ~2s.
```

But the plan makes TWO calls per bead:
1. `bd state <id> phase` (or `phase_get` which wraps it)
2. `bd show <id> --json` for priority scoring (if scoring is done via bd, not from discovery_scan_beads initial query)

Wait — re-reading the plan: Task 3 says "Read phase for each bead: call `bd state <id> phase`" but does NOT say to re-read priority. The initial `bd list --json` already has priority. So this concern is PARTIALLY MITIGATED.

**Remaining issue:** Phase read is still O(n) subprocess calls. For 100 beads, this is 5-10s.

**Fix:** Add phase to `bd list --json` output (requires bd CLI change, out of scope for this plan). Or batch-read phases:
```bash
# Instead of:
for id in "${bead_ids[@]}"; do
    phase=$(phase_get "$id")
done

# Do:
phases=$(bd state --batch --dimension=phase "${bead_ids[@]}")  # Single bd call
# Parse multi-line output
```

But `bd state` doesn't support `--batch` yet. So this is a **future optimization** (F4 brief scan will hit this bottleneck).

**Recommendation:** Document this as a known performance limitation. Add a TODO in discovery_scan_beads:
```bash
# TODO(performance): phase_get is O(n) subprocess calls. For >50 beads,
# consider caching phase state in /tmp/clavain-phase-cache-${session_id}.json
# with 60s TTL, similar to discovery_brief_scan cache pattern.
```

---

### M2: Stale Review Detection Doesn't Check Review Quality

**Issue:** Plan says "stale review = soft warning" if artifact was edited after review. But what if:
- Review was incomplete (agent crashed mid-review)
- Review was low-confidence (agent said "insufficient context")
- Review found critical issues but they weren't fixed

Checking git log for "commits after review date" is a **necessary** condition for staleness, but not **sufficient**. A better check:
1. Read findings.json `"status"` field → if "incomplete" or "error", treat as stale
2. Read findings.json `"issues"` array → if any P0/P1 findings are still open, treat as stale
3. Check if findings.json `"reviewed"` date matches the plan's `**Phase:**` date — if desync, treat as stale

**Fix:** Add quality checks to `check_review_staleness`:
```bash
check_review_staleness() {
    local bead_id="$1"
    local artifact_path="$2"

    # ... find review dir ...

    # Check 1: findings.json exists and is valid JSON
    if ! jq empty < "$findings_file" 2>/dev/null; then
        echo "error"
        return 0
    fi

    # Check 2: review status
    local status
    status=$(jq -r '.status // "unknown"' < "$findings_file")
    if [[ "$status" == "incomplete" || "$status" == "error" ]]; then
        echo "stale-incomplete"
        return 0
    fi

    # Check 3: git log recency (existing check)
    # ...

    # Check 4: any P0/P1 findings?
    local critical_count
    critical_count=$(jq '[.findings[] | select(.priority <= 1)] | length' < "$findings_file")
    if [[ "$critical_count" -gt 0 ]]; then
        echo "stale-critical"  # Review found issues that may not be resolved
        return 0
    fi

    echo "fresh"
}
```

**Recommendation:** Start with simple git log check (as planned), add quality checks in M3 after findings.json schema is stable.

---

### M3: No Rollback Strategy for Broken Enforcement

**Issue:** What happens if `enforce_gate` has a bug and starts hard-blocking ALL transitions (even valid ones)?

Scenario:
- User publishes interphase 0.3.0 with broken `enforce_gate`
- Restarts session to pick up new version
- Now `/clavain:work`, `/clavain:ship`, `/clavain:plan` ALL fail with "Gate blocked"
- User is stuck — cannot advance any beads
- `/clavain:flux-drive` also fails because it calls `advance_phase("brainstorm-reviewed")`

**Recovery paths:**

1. **Emergency rollback:** Downgrade interphase to 0.2.0
```bash
cd /root/projects/interphase
git checkout v0.2.0
claude --plugin-dir /root/projects/interphase --install
# Restart session
```

2. **Emergency bypass:** Set env var to disable enforcement
```bash
export CLAVAIN_DISABLE_GATES=1
# All enforce_gate calls return 0 immediately
```

3. **Hotfix publish:** Fix bug, bump to 0.3.1, publish, restart

**Recommendation:** Add env var escape hatch to `enforce_gate`:
```bash
enforce_gate() {
    # Emergency bypass (never use in production)
    if [[ "${CLAVAIN_DISABLE_GATES:-false}" == "true" ]]; then
        echo "WARNING: gate enforcement DISABLED by env var" >&2
        return 0
    fi

    # Normal logic...
}
```

Document in AGENTS.md under Troubleshooting section.

---

## Test Coverage Gaps

Plan says 15 gates.bats tests + 8 discovery.bats tests = 23 new tests. But several critical scenarios are missing:

**Missing from gates.bats:**
1. `enforce_gate`: concurrent priority changes (race test)
2. `enforce_gate`: malformed --reason with shell metacharacters (`reason="'; rm -rf /"`)
3. `enforce_gate`: very long --reason (>1KB) — does bd notes have size limits?
4. `check_review_staleness`: multiple reviews in different dirs (which one wins?)
5. `check_review_staleness`: findings.json with no "reviewed" field (legacy format)
6. `enforce_gate`: bead deleted mid-execution (bd show fails)
7. `enforce_gate`: .beads directory missing (bd unavailable)

**Missing from discovery.bats:**
1. `score_bead`: phase=none (bead never advanced)
2. `score_bead`: negative priority (invalid but bd allows it)
3. `score_bead`: updated_at in the future (clock skew)
4. `discovery_scan_beads`: 0 beads (empty project)
5. `discovery_scan_beads`: 1000 beads (performance test)
6. `infer_bead_action`: artifact in docs/research (not docs/plans)

**Recommendation:** Add at least 10 more tests covering error paths and edge cases. Target: 40 total new tests.

---

## Implementation Order Dependency Risk

Plan says Tasks 1-2 (enforcement) and 3-4 (discovery) are independent and can be parallelized. This is TRUE for code changes but FALSE for testing:

**Dependency:** Task 6 (tests) needs ALL of Tasks 1-4 complete to test integration scenarios:
- Discovery returns phase field (Task 4)
- `/lfg <bead-id>` routes to correct command (Task 4)
- That command calls `enforce_gate` (Task 5 references Task 1)
- `enforce_gate` checks staleness (Task 2)
- Stale review triggers soft warning but allows proceed

This is a 5-step call chain across ALL tasks. If Task 1 is complete but Task 4 isn't, tests can't verify the full pipeline.

**Fix:** Add Task 6.5: Integration smoke test (runs AFTER all unit tests pass):
```bash
@test "INTEGRATION: /lfg with stale P2 bead issues soft warning" {
    # Setup: P2 bead at planned phase with stale plan review
    bd create --id test-int --priority 2 --status open
    echo "# Plan" > docs/plans/test-int.md
    phase_set test-int "planned" "reviewed on 2026-02-10"

    # Create stale review (reviewed 2026-02-10, plan edited 2026-02-12)
    mkdir -p docs/research/flux-drive/test-int
    echo '{"artifact":"docs/plans/test-int.md","reviewed":"2026-02-10T10:00:00Z"}' \
        > docs/research/flux-drive/test-int/findings.json
    touch -t 202602121200 docs/plans/test-int.md

    # Execute: invoke /lfg with direct bead-id routing
    run bash -c 'CLAVAIN_BEAD_ID=test-int source commands/lfg.md'

    # Verify: soft warning issued, work proceeds
    assert_success
    assert_output --partial "WARNING: review is stale"
    assert_output --partial "Routing to /clavain:work"
}
```

---

## Recommendations Summary

**MUST FIX before implementation:**
1. Add `shipping:planned` to VALID_TRANSITIONS (H1)
2. Replace stem-based review matching with content-based matching (H2)
3. Use proper getopt parsing for `--skip-gate --reason` (H3)
4. Clarify `bd update --append-notes` vs `--notes` in plan (H6)

**SHOULD FIX before implementation:**
5. Add TOCTOU mitigation to priority read (H4)
6. Increase priority weighting in scoring formula (H5)
7. Add fail-safe error handling for audit trail writes (H6)

**CAN DEFER to M3:**
8. Review quality checks in staleness detection (M2)
9. Performance optimization for phase reads (M1)
10. Emergency rollback documentation (M3)

**Test coverage:**
11. Add 10+ edge case tests to reach 40 total new tests

**Process:**
12. Add integration smoke test as Task 6.5 (runs after all unit tests)

---

## Failure Narratives

### Narrative 1: Phase Cycling Blocks Legitimate Re-Entry

**Setup:**
- Bead: Clavain-xyz (priority P1)
- Current phase: `shipping` (feature shipped in v0.5.0)
- User wants to add M2 scope, creates new plan docs/plans/m2-xyz.md
- Invokes `/clavain:plan` to transition back to `planned` phase

**Execution:**
1. `/clavain:plan` command calls `enforce_gate("Clavain-xyz", "planned", "docs/plans/m2-xyz.md")`
2. `get_enforcement_tier("Clavain-xyz")` queries `bd show` → priority=1 → tier="hard"
3. `check_phase_gate("Clavain-xyz", "planned", "docs/plans/m2-xyz.md")` called
4. `phase_get_with_fallback("Clavain-xyz")` returns "shipping"
5. `is_valid_transition("shipping", "planned")` checks VALID_TRANSITIONS array
6. "shipping:planned" NOT FOUND → returns 1
7. `check_phase_gate` returns 1 (blocked)
8. `enforce_gate` sees tier=hard + gate blocked + no --skip-gate → returns 1
9. Command stops with "ERROR: phase gate blocked planned (tier=hard)"

**Result:**
- User cannot re-enter `planned` phase for new scope
- Workaround: `--skip-gate --reason "M2 re-entry"` but this defeats the purpose of tier enforcement
- User must manually edit VALID_TRANSITIONS and restart session

**Fix:** Add phase cycling transitions to VALID_TRANSITIONS before M2 ships.

---

### Narrative 2: Renamed Plan Evades Staleness Detection

**Setup:**
- Bead: Clavain-abc (priority P0)
- Plan: docs/plans/widget-rewrite.md (created 2026-02-10)
- flux-drive review ran 2026-02-11, created docs/research/flux-drive/widget-rewrite/findings.json
- User renames docs/plans/widget-rewrite.md → docs/plans/widget-v2-rewrite.md (2026-02-12)
- User edits docs/plans/widget-v2-rewrite.md with new scope (2026-02-13)

**Execution:**
1. `/clavain:work` command calls `enforce_gate("Clavain-abc", "executing", "docs/plans/widget-v2-rewrite.md")`
2. `check_review_staleness("Clavain-abc", "docs/plans/widget-v2-rewrite.md")` called
3. Stem derivation: "widget-v2-rewrite"
4. Look for docs/research/flux-drive/widget-v2-rewrite/findings.json → NOT FOUND
5. Returns "none" (no review found)
6. `enforce_gate` sees no stale review → proceeds with normal gate check
7. Phase is `plan-reviewed` → valid transition to `executing` → gate passes
8. Work begins on plan that was NEVER REVIEWED (old review was for different scope)

**Result:**
- P0 work starts without review
- Architectural flaws, security issues, performance problems missed
- Ships to production, breaks in prod, 3am wakeup call

**Fix:** Use content-based review matching (scan findings.json for bead_id or artifact field with fuzzy path matching).

---

### Narrative 3: Scoring Inversion Hides High-Priority Fresh Work

**Setup:**
- Bead A: Clavain-p2a (priority P2, phase brainstorm, updated 18h ago)
- Bead B: Clavain-p4b (priority P4, phase executing, updated 2h ago, plan last touched 4 days ago)

**Execution:**
1. User invokes `/clavain:lfg` → calls `discovery_scan_beads()`
2. Scoring for Bead A:
   - priority: P2=24
   - phase: brainstorm=4
   - recency: 18h=20 (within 24h)
   - staleness: fresh=0
   - **Total: 48**
3. Scoring for Bead B:
   - priority: P4=8
   - phase: executing=30
   - recency: 2h=20 (within 24h)
   - staleness: plan mtime 4d ago=true → -10
   - **Total: 48**
4. Tiebreaker: id ASC → "Clavain-p2a" < "Clavain-p4b" → Bead A wins by 1 character
5. BUT if Bead B had id "Clavain-p4a" → would win tiebreaker → P4 ranks above P2

**Result:**
- High-priority fresh strategic work (P2 brainstorm) can be HIDDEN below low-priority stale tactical work (P4 execution)
- Users miss important brainstorms because they're not surfaced in discovery
- Product priorities get inverted by scoring formula

**Fix:** Increase priority weighting so P2 vs P4 gap (2 tiers = 16 points in current formula) cannot be overcome by phase+recency (max 50 points).

---

## Sign-Off

This plan can proceed to implementation AFTER addressing H1-H6 findings. The core architecture is sound (tiered enforcement + multi-factor scoring), but edge cases and error handling need hardening.

**Time estimate:**
- Original estimate: 6 tasks × 2h = 12h
- With correctness fixes: +4h (H1-H6)
- With test coverage expansion: +3h (40 tests instead of 23)
- **Total: 19h**

**Risk after fixes:** LOW. The bash script patterns match existing lib-gates.sh style (fail-safe, jq-based JSON, telemetry logging). Test coverage will be comprehensive (40 tests + integration smoke test).

**Reviewer confidence:** MEDIUM-HIGH. I have not run the code, only analyzed the plan against existing patterns. Shell script correctness requires runtime verification (bats tests will catch issues I missed).
