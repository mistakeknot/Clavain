# Architecture Review: Auto-Drift-Check Implementation Plan

**Reviewer:** Flux-drive Architecture & Design Reviewer
**Date:** 2026-02-14
**Plan:** docs/plans/2026-02-14-auto-drift-check.md
**Bead:** Clavain-iwuy

## Summary

The plan extracts signal detection from auto-compound.sh into a shared library (lib-signals.sh), refactors two existing Stop hooks to use per-hook sentinels, and introduces a new auto-drift-check.sh Stop hook. Overall architecture is sound with good separation of concerns. Three areas require attention: sentinel coupling across hooks, redundant validation logic, and potential race conditions in the Stop hook cascade.

## Findings

### 1. Boundaries & Coupling

#### 1.1 Shared Library Extraction - APPROVED

**Finding:** The extraction of signal detection into lib-signals.sh is a clean module boundary. The library:
- Exposes a single public function (`detect_signals()`)
- Uses output variables (`CLAVAIN_SIGNALS`, `CLAVAIN_SIGNAL_WEIGHT`) as a clear contract
- Contains no side effects beyond variable assignment
- Has guard against double-sourcing (`_LIB_SIGNALS_LOADED`)

**Evidence:**
- Plan lines 134-214 show the library has no external dependencies beyond bash/grep
- Both consumers (auto-compound.sh line 260-268, auto-drift-check.sh line 526-537) use identical sourcing and invocation patterns
- Tests at lines 40-122 validate the contract without coupling to hook logic

**Recommendation:** None. This is textbook library extraction.

---

#### 1.2 Per-Hook Sentinel Namespace - PARTIALLY PROBLEMATIC

**Finding:** The plan correctly identifies that the current shared sentinel (`/tmp/clavain-stop-${SESSION_ID}`) creates cross-hook coupling where the first Stop hook to fire blocks all others in the same cycle. The proposed fix uses per-hook sentinels:
- auto-compound: `/tmp/clavain-stop-compound-${SESSION_ID}` (line 243)
- auto-drift-check: `/tmp/clavain-stop-drift-${SESSION_ID}` (line 491)
- session-handoff: `/tmp/clavain-stop-handoff-${SESSION_ID}` (line 310)

**Problem:** This fixes the namespace collision but **preserves the original architectural mistake**. Look at the existing hooks:

**auto-compound.sh line 47-52:**
```bash
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
touch "$STOP_SENTINEL"
```

**session-handoff.sh line 35-40:**
```bash
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
touch "$STOP_SENTINEL"
```

Both hooks check for AND write the same sentinel. This is a **distributed mutual exclusion lock** that prevents cascading Stop hooks. The plan changes the sentinel names but keeps this pattern. The new auto-drift-check.sh (line 491-494) does the same thing.

**Architectural Question:** What is the actual requirement?

1. **If the goal is "only one Stop hook fires per cycle"**: Then the shared sentinel is CORRECT and the per-hook refactor breaks the design. The current auto-compound line 47 comment says "if another Stop hook already fired this cycle, don't cascade" — this is explicit mutual exclusion.

2. **If the goal is "each Stop hook decides independently"**: Then per-hook sentinels are correct, but the cross-hook check should be removed entirely. Each hook should only check its own sentinel.

**Current plan is incoherent:** It adds per-hook sentinels (suggesting independent decisions) but keeps the mutual exclusion guard logic (suggesting only one hook should fire). The new auto-drift-check.sh line 491 still checks for a sentinel before firing, which means if auto-compound runs first and sets its sentinel, auto-drift-check will still exit early if it checks the OLD shared sentinel logic.

**Wait — re-reading the plan:** The plan DOES update the sentinel variable names in all three hooks (Task 2 Step 2 line 243, Task 3 line 310, Task 4 Step 3 line 491). So each hook will check its OWN per-hook sentinel, not a shared one. That's correct for independent operation.

**But:** The comment at auto-compound.sh line 46-49 says "if another Stop hook already fired this cycle, don't cascade" and the guard logic is `if [[ -f "$STOP_SENTINEL" ]]; then exit 0; fi`. After the refactor, this check will only prevent **the same hook** from firing twice in one cycle (which the throttle sentinel already prevents). It will NOT prevent cascading across hooks. The comment is now misleading and the guard logic is redundant with the throttle.

**Conclusion:** The plan fixes the namespace collision but leaves behind vestigial guard logic that no longer serves its original purpose. This is accidental complexity.

**Recommendation:**
- **Clarify the requirement:** Do Stop hooks need mutual exclusion (only one fires per cycle) or independent operation (all can fire)?
- **If independent:** Remove the "STOP_SENTINEL" guard entirely from all three hooks. The per-hook throttle sentinels (lines 55-62 in auto-compound, 498-505 in auto-drift-check) already prevent double-firing within a session. The STOP_SENTINEL check (lines 47-52 in current, 491-494 in new) is now redundant.
- **If mutual exclusion is needed:** Keep a shared sentinel, don't rename it. Document WHY mutual exclusion is required (I suspect it's to prevent Claude from seeing 3 separate "block" decisions in one Stop cycle, which could be confusing).

**Best guess:** The original design wanted mutual exclusion to avoid overwhelming Claude with multiple Stop prompts. If that's still the goal, the plan should KEEP the shared sentinel name and ADD per-hook throttle sentinels. If hooks should run independently, DELETE the STOP_SENTINEL logic entirely.

---

#### 1.3 Auto-Drift-Check Hook Design - GOOD WITH CAVEATS

**Finding:** The new hook follows the same pattern as auto-compound:
- Reads hook JSON from stdin
- Checks guards (stop_hook_active, opt-out file, sentinel, throttle)
- Analyzes transcript using lib-signals.sh
- Returns JSON decision
- Exits 0 always

**Differences from auto-compound:**
- Lower threshold (2 vs 3) — justified by the comment "doc drift checking is cheap and important" (line 458)
- Additional guard: interwatch discovery (line 507-513) with graceful degradation
- Different throttle window (600s vs 300s) — doc drift is less urgent than compounding

**Coupling Risk:** The hook depends on:
1. lib-signals.sh (via source, line 527) — acceptable, shared library
2. lib.sh (via source, line 509) — acceptable, already used by other hooks
3. interwatch plugin (via `_discover_interwatch_plugin()`, line 510) — acceptable, gracefully degrades if missing

**Recommendation:** None. The dependency chain is clean and progressive enhancement is correctly implemented.

---

### 2. Pattern Analysis

#### 2.1 Duplicated Guard Logic - CODE SMELL

**Finding:** All three Stop hooks (auto-compound, session-handoff, auto-drift-check) implement identical guard patterns with minor variations:

**Guard sequence (all three hooks):**
1. Check jq availability
2. Read stdin JSON
3. Check `stop_hook_active` flag
4. Check per-repo opt-out file
5. Extract session_id
6. Check STOP_SENTINEL (per-hook after refactor)
7. Write STOP_SENTINEL
8. Check throttle sentinel
9. (hook-specific logic)
10. Return JSON decision
11. Clean up stale sentinels

**Evidence:**
- auto-compound.sh lines 25-62
- session-handoff.sh lines 19-46
- auto-drift-check.sh (plan) lines 467-524

**Pattern Violation:** The plan extracts signal detection (domain logic) into a shared library but leaves guard boilerplate (cross-cutting concern) duplicated. This is inconsistent abstraction level.

**Counter-argument:** Guard logic is ~40 lines per hook and varies slightly:
- auto-compound opt-out: `.claude/clavain.no-autocompound` (line 40)
- auto-drift-check opt-out: `.claude/clavain.no-driftcheck` (line 484)
- session-handoff: no opt-out file (relies only on sentinels)
- Throttle windows: 300s (compound), 600s (drift), none (handoff)

Extracting guards into a shared function would require parameterizing opt-out file names and throttle windows, which might be more complex than duplication.

**Recommendation:** Accept duplication for now. The guard logic is simple and the variations are meaningful. If a 4th Stop hook is added, revisit and extract a `_stop_hook_guards()` function in lib.sh that takes opt-out filename and throttle seconds as parameters.

---

#### 2.2 Sentinel Cleanup Pattern - GOOD

**Finding:** All three hooks use the same cleanup pattern at the end:
```bash
find /tmp -maxdepth 1 -name 'clavain-stop-*' -mmin +60 -delete 2>/dev/null || true
```

This appears in:
- auto-compound.sh line 148 (current)
- session-handoff.sh line 117 (current)
- auto-drift-check.sh line 558 (plan)

**Problem:** After the per-hook sentinel refactor, this cleanup glob will match:
- `/tmp/clavain-stop-compound-*`
- `/tmp/clavain-stop-drift-*`
- `/tmp/clavain-stop-handoff-*`

All three hooks will clean up each other's sentinels. This is correct because the cleanup is scoped to **any** session older than 60 minutes. The glob pattern still works.

**But:** The throttle sentinels use different patterns:
- auto-compound: `/tmp/clavain-compound-last-*` (line 55)
- auto-drift-check: `/tmp/clavain-drift-last-*` (line 498)
- session-handoff: no throttle

These are NOT cleaned up by the current cleanup command. Stale throttle sentinels will accumulate in /tmp.

**Recommendation:** Add throttle sentinel cleanup to the cleanup block:
```bash
find /tmp -maxdepth 1 \( -name 'clavain-stop-*' -o -name 'clavain-compound-last-*' -o -name 'clavain-drift-last-*' \) -mmin +60 -delete 2>/dev/null || true
```

Or use a single pattern if sentinels are renamed consistently:
```bash
find /tmp -maxdepth 1 -name 'clavain-*-*' -mmin +60 -delete 2>/dev/null || true
```

---

#### 2.3 Signal Detection Completeness - ASYMMETRY

**Finding:** The signal detection patterns in lib-signals.sh (lines 167-210) detect 7 signals:
1. commit (weight 1)
2. resolution (weight 2)
3. investigation (weight 2)
4. bead-closed (weight 1)
5. insight (weight 1)
6. recovery (weight 2)
7. version-bump (weight 2)

**Missing from original auto-compound.sh:** The version-bump signal (lines 205-209 in lib-signals.sh) is NEW. It was not present in the original auto-compound.sh signal detection (lines 75-116).

**Impact:** After refactoring to use lib-signals.sh, auto-compound.sh will now trigger on version bumps. A version bump (weight 2) + commit (weight 1) = 3, which meets the compound threshold. This is a **behavior change**, not a pure refactor.

**Justification:** The plan Task 2 Step 3 says "verify no regression" and expects "All 10 tests PASS (identical behavior)" (line 277). But the tests at lines 337-374 don't include a version-bump fixture. The auto_compound.bats tests only cover:
- commit + bead-close (lines 370-374)
- single commit (lines 376-380)
- no signal (lines 382-386)
- recovery (lines 432-437)

There's no test that would catch the version-bump behavior change.

**Is this a bug or a feature?** The PRD (referenced line 13) might justify adding version-bump signals. Version bumps often correlate with shipped work that should trigger drift checking. But it's not documented as an intentional change in the plan.

**Recommendation:**
- Add a test case for version-bump signals to `tests/shell/auto_compound.bats`
- Document in the commit message that refactoring to lib-signals.sh adds version-bump detection to auto-compound as a side effect
- OR: Remove version-bump from lib-signals.sh if it should only apply to drift-check

---

### 3. Simplicity & YAGNI

#### 3.1 Interwatch Discovery Graceful Degradation - APPROPRIATE

**Finding:** The auto-drift-check.sh hook includes interwatch discovery (lines 507-513):
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"
INTERWATCH_ROOT=$(_discover_interwatch_plugin)
if [[ -z "$INTERWATCH_ROOT" ]]; then
    exit 0
fi
```

**Question:** Is this premature? The hook's entire purpose is to trigger `/interwatch:watch`. If interwatch isn't installed, the hook does nothing. Why register the hook at all?

**Counter-argument:** Clavain is a standalone plugin that CAN work without interwatch. The hook provides progressive enhancement: if interwatch is present, auto-trigger drift checks; if not, no-op. This is the same pattern used elsewhere (e.g., interphase discovery in other hooks).

**Recommendation:** Accept. This is consistent with Clavain's companion plugin architecture.

---

#### 3.2 Demo Hook for Interwatch Repo - POTENTIAL OVERENGINEERING

**Finding:** Task 6 (lines 656-793) creates a standalone example hook for the interwatch repo with:
- Inline signal detection (not using lib-signals.sh)
- Configurable threshold and throttle
- 119 lines of code

**Purpose:** Show interwatch users how to auto-trigger `/interwatch:watch` from their own plugins.

**Question:** Does this example add value or create maintenance burden?

**Analysis:** The demo hook duplicates signal detection logic (lines 746-763) that already exists in lib-signals.sh. If signal patterns change (new signals added, weights adjusted), the demo will drift from the canonical implementation. Users might copy-paste outdated patterns.

**Counter-argument:** The demo is intentionally standalone so users don't need Clavain as a dependency. Inline signal detection is a feature, not a bug.

**Recommendation:**
- Keep the demo but add a comment: "This example uses simplified signal detection. For production use, consider extracting signals into a shared library like Clavain's lib-signals.sh."
- Link to lib-signals.sh in a comment so users can reference the canonical patterns
- Mark the demo as "example-only, not maintained for production use"

---

#### 3.3 STOP_SENTINEL Redundancy (Revisited)

**Finding:** As noted in section 1.2, the per-hook STOP_SENTINEL logic (lines 491-494 in auto-drift-check.sh) is redundant with the throttle sentinel logic (lines 498-505). Both prevent double-firing within a session, but the throttle has a time-based expiry while STOP_SENTINEL is per-cycle.

**Simplification Opportunity:** If the STOP_SENTINEL is truly per-hook (not cross-hook mutual exclusion), then its only purpose is to prevent multiple fires in the same Stop event cycle. But Stop hooks are called once per cycle by Claude Code, so re-entry isn't possible unless a hook calls itself recursively (which none of these do).

**The sentinel's real purpose:** Looking at auto-compound.sh line 46-52 and the comment "if another Stop hook already fired this cycle, don't cascade" — the original design was for cross-hook mutual exclusion. The plan preserves the sentinel but changes the namespace, which breaks the mutual exclusion without removing the logic.

**Recommendation (repeated from 1.2):** Decide the requirement, then simplify:
- If mutual exclusion is needed: keep shared sentinel, document why
- If independent operation: delete STOP_SENTINEL logic entirely, rely only on throttle

---

### 4. Correctness Concerns

#### 4.1 Race Condition in Sentinel Write Order

**Finding:** All three hooks write the STOP_SENTINEL BEFORE running their analysis logic:

**auto-compound.sh lines 46-52:**
```bash
STOP_SENTINEL="/tmp/clavain-stop-${SESSION_ID}"
if [[ -f "$STOP_SENTINEL" ]]; then
    exit 0
fi
# Write sentinel NOW — before transcript analysis — to minimize TOCTOU window
touch "$STOP_SENTINEL"
```

**Purpose:** The comment says "minimize TOCTOU window" (time-of-check to time-of-use). This prevents a race where two hooks check the sentinel simultaneously, both see it missing, and both proceed to write it.

**Problem:** Claude Code calls Stop hooks in sequence (not parallel), so this race condition doesn't exist. The hooks.json Stop array (lines 49-60) is processed one at a time. The sentinel write is defensive against a non-existent threat.

**Counter-argument:** If Claude Code's hook runner is refactored in the future to run Stop hooks in parallel, this sentinel ordering would become critical. It's future-proofing.

**Recommendation:** Accept the defensive pattern but add a comment explaining it's for theoretical parallel execution, not current behavior.

---

#### 4.2 Transcript Tail Window Consistency

**Finding:** All hooks use `tail -80` to extract recent transcript context:
- auto-compound.sh line 70
- auto-drift-check.sh (plan) line 521

**Question:** Why 80 lines? Is this enough to capture all signals?

**Analysis:** The longest signal pattern is "recovery" (lines 198-202 in lib-signals.sh), which requires detecting both a failure and a subsequent pass in the same transcript window. If a test fails at line -100 and passes at line -10, the failure won't be in the tail-80 window.

**Impact:** Recovery signals might be missed if the failure->pass cycle spans more than 80 transcript lines.

**Counter-argument:** 80 lines is ~4-8 turns of conversation (10-20 lines per turn). If debugging takes more than 8 turns, the failure is probably stale and not worth compounding anyway.

**Recommendation:** Document the 80-line window assumption in lib-signals.sh comments. Add a test case with a failure->pass cycle at the boundary (line -85 to line -5) to verify behavior.

---

### 5. Missing Abstractions

#### 5.1 No Signal Weight Configuration

**Finding:** Signal weights are hardcoded in lib-signals.sh:
- commit: 1
- resolution: 2
- investigation: 2
- bead-closed: 1
- insight: 1
- recovery: 2
- version-bump: 2

**Observation:** Different hooks use different thresholds (compound: 3, drift: 2) but consume the same weights. If a project wants to adjust weights (e.g., make commits weight 2 because they're rare in that repo), they must fork lib-signals.sh.

**YAGNI Check:** Is weight configuration needed now? No evidence in the plan or PRD that users have requested this. All current hooks use the same signals with different thresholds, which works.

**Recommendation:** Accept hardcoded weights. If a 3rd consumer with different weight needs emerges, refactor to pass weights as parameters.

---

### 6. Integration Risks

#### 6.1 Hook Ordering in hooks.json

**Finding:** Task 4 Step 5 (lines 569-589) specifies the new Stop hooks order:
1. auto-compound.sh (threshold 3, throttle 5min)
2. auto-drift-check.sh (threshold 2, throttle 10min) — NEW
3. session-handoff.sh (no threshold, checks uncommitted work)

**Analysis:** If hooks run sequentially and independently (per-hook sentinels), order doesn't matter. But if the original mutual exclusion design is preserved, the first hook to fire will block the others.

**Scenario:** User commits code (weight 1) + closes bead (weight 1) = weight 2.
- auto-compound: threshold 3, does NOT fire
- auto-drift-check: threshold 2, FIRES and prompts for `/interwatch:watch`
- session-handoff: would fire (uncommitted work), but if shared sentinel is used, auto-drift-check already blocked it

**Problem:** With shared sentinel, auto-drift-check can suppress session-handoff, which is dangerous — handoff prevents lost work.

**Recommendation:**
- If mutual exclusion is kept: move session-handoff to position 1 (highest priority)
- If independent operation: document that all three hooks can fire in one cycle and Claude might see 3 separate prompts (design decision)

---

#### 6.2 Test Coverage for Multi-Hook Scenarios

**Finding:** The plan includes tests for each hook in isolation:
- lib_signals.bats (12 tests)
- auto_compound.bats (10 tests, updated for new sentinel)
- auto_drift_check.bats (10 tests)

**Missing:** Integration tests that verify:
- Hook ordering in hooks.json
- Behavior when multiple hooks should fire in the same cycle
- Sentinel isolation (per-hook sentinels don't block each other)
- Shared sentinel cleanup doesn't break per-hook sentinels

**Recommendation:** Add a shell integration test that:
1. Simulates a Stop cycle with a transcript that triggers both auto-compound (weight 3+) and auto-drift-check (weight 2+)
2. Runs both hooks in sequence
3. Verifies both produce "block" decisions
4. Verifies sentinels are namespaced correctly

---

## Summary of Recommendations

### Must-Fix (Architectural Correctness)

1. **Clarify sentinel mutual exclusion requirement** (section 1.2): Document whether Stop hooks need mutual exclusion or independent operation. If independent, remove STOP_SENTINEL logic entirely. If mutual exclusion, revert to shared sentinel and document why.

2. **Fix hook ordering if mutual exclusion is kept** (section 6.1): Move session-handoff to position 1 to prevent auto-drift-check from suppressing handoff prompts.

3. **Document version-bump behavior change** (section 2.3): The refactor adds version-bump signals to auto-compound.sh. Either add a test for this or remove version-bump from lib-signals.sh.

### Should-Fix (Reduces Complexity)

4. **Add throttle sentinel cleanup** (section 2.2): Include `clavain-*-last-*` in the cleanup glob to prevent /tmp accumulation.

5. **Add integration test for multi-hook scenarios** (section 6.2): Verify sentinel isolation and hook ordering in a single test.

### Nice-to-Have (Future-Proofing)

6. **Add boundary test for transcript tail window** (section 4.2): Verify recovery signal detection when failure is at line -85.

7. **Mark demo hook as example-only** (section 3.2): Add disclaimer that inline signal detection is simplified and link to canonical lib-signals.sh.

---

## Verdict

**Overall Assessment:** The plan is architecturally sound with good module boundaries (lib-signals.sh extraction is clean). The primary issue is ambiguity around sentinel semantics — the refactor changes sentinel namespaces without resolving whether mutual exclusion is required. This creates vestigial guard logic that no longer serves its original purpose.

**Recommended Action Before Implementation:**
1. Decide: Do Stop hooks need mutual exclusion?
2. Update the plan accordingly (keep shared sentinel OR delete cross-hook checks)
3. Add integration test for multi-hook scenarios
4. Document version-bump signal addition to auto-compound

**Risk Level:** Medium. The sentinel ambiguity could cause unexpected behavior (hooks blocking each other or all firing at once), but it's unlikely to break functionality completely. The worst case is UX degradation (Claude sees multiple Stop prompts or misses handoff).
