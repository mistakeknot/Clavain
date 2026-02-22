# Architecture Review: Sprint Handover — Kernel-Driven Sprint Skill

**Date:** 2026-02-20
**Reviewer:** Flux-drive Architecture & Design Reviewer
**Plan:** `/root/projects/Interverse/docs/plans/2026-02-20-sprint-handover-kernel-driven.md`
**Brainstorm:** `/root/projects/Interverse/docs/brainstorms/2026-02-20-sprint-handover-kernel-driven-brainstorm.md`
**Source:** `/root/projects/Interverse/os/clavain/hooks/lib-sprint.sh` (1276 lines)

---

## Summary

The plan's central design decisions are sound. Removing ~600 lines of beads fallback code is architecturally correct — the dual-path branching is the primary source of complexity and bit-rot risk in lib-sprint.sh. The bead-as-identity / run-as-engine layering is clean and well-reasoned. The run ID caching strategy is the right fix for the per-call `bd state ic_run_id` overhead.

Five concrete concerns require attention before implementation. Two are blocking correctness risks. Three are structural issues that will create follow-on bugs or confusion if not addressed in this pass.

---

## 1. Boundaries and Coupling

### 1.1 [BLOCKING] lib-gates.sh sourcing in sprint.md — incomplete removal plan

The plan (Task 13) correctly identifies two `lib-gates.sh` source lines in `sprint.md` (lines 192-193 and 347-348) and instructs removing them. However, the grep evidence shows `advance_phase` is called from eight other command files that are not in scope for this plan:

- `commands/strategy.md` (3 calls: lines 107, 109, 114, 119)
- `commands/execute-plan.md` (lines 10, 16)
- `commands/write-plan.md` (lines 10, 12)
- `commands/brainstorm.md` (lines 104, 106)
- `commands/review-doc.md` (lines 64, 66)
- `commands/quality-gates.md` (lines 136, 143)
- `commands/work.md` (lines 54, 60)
- `commands/codex-sprint.md` (line 65)

None of these are touched by this plan. Task 13's verification step checks only `sprint.md` and will produce a pass signal even though `advance_phase` continues operating in eight other commands via the lib-gates shim.

This is not a problem introduced by A2 — those commands worked before and will continue to work after, because `hooks/lib-gates.sh` is retained as a no-op shim. The problem is that the plan's success criterion "Sprint skill does not source lib-gates.sh" is accurate but could be misread as a system-wide migration when it is only sprint.md-scoped. A future implementer reading the success criteria and finding `advance_phase` in `commands/work.md` will be confused about whether the migration is incomplete.

**Minimum fix:** Reword Task 13's success criteria and verification step to make the scope explicit: "sprint.md no longer sources lib-gates.sh directly — other workflow commands still call advance_phase via the shim and are unaffected." Do not attempt to remove lib-gates from other commands in this pass — that is a separate workstream.

### 1.2 [BLOCKING] sprint_finalize_init deletion order creates a broken intermediate state

The plan marks `sprint_finalize_init` for deletion in Task 2 (rewrite sprint_create). `commands/sprint.md` line 240 still calls it:

```bash
sprint_finalize_init "$SPRINT_ID"
```

Task 13, Step 1 does instruct removing this call from sprint.md, but Task 2 runs first (Tasks 2 through 12 all touch lib-sprint.sh, Task 13 touches sprint.md last). Between Task 2's commit and Task 13's commit, the sprint skill will call a function that no longer exists. If any partial test runs, syntax-check passes, or integration smoke tests happen mid-implementation, this window will produce a silent error (function not found — bash returns non-zero silently when a sourced function is missing).

The underlying flag (`sprint_initialized=true`) is read only by the now-deleted beads fallback in `sprint_find_active` (current lib-sprint.sh lines 224-225). That fallback is removed in Task 3. So by the time the system is in a fully committed state after all 15 tasks, the flag is unreachable. The deletion is architecturally correct. The ordering is the problem.

**Minimum fix:** Add a Task 2, Step 0 that edits sprint.md to remove the `sprint_finalize_init "$SPRINT_ID"` call (line 240) before the function is deleted from lib-sprint.sh. Alternatively, re-sequence: move the sprint.md cleanup from Task 13 to immediately after Task 2. The safest sequence is: edit sprint.md first, then delete the function.

### 1.3 [BLOCKING] Session-scoped run ID cache creates cross-bead contamination in multi-sprint sessions

`_SPRINT_RUN_ID` is a module-level variable with no bead ID tracking. The plan's `_sprint_resolve_run_id` implementation:

```bash
_SPRINT_RUN_ID=""  # Session-scoped cache: resolved once at claim time

_sprint_resolve_run_id() {
    local bead_id="$1"
    ...
    # Cache hit
    if [[ -n "$_SPRINT_RUN_ID" ]]; then
        echo "$_SPRINT_RUN_ID"
        return 0
    fi
    ...
}
```

Once populated from any bead, the cache serves the same run_id to all subsequent calls regardless of which bead_id is passed. This is correct for single-sprint sessions (the common case). It is incorrect when multiple sprints are rendered in the same shell session.

This is not a theoretical concern. `hooks/sprint-scan.sh` sources `lib-sprint.sh` and then calls `sprint_find_active` (which returns multiple sprints) followed by `sprint_read_state` for each sprint. Under the new plan, `sprint_read_state` calls `_sprint_resolve_run_id`. When sprint-scan renders sprint 2 in a session where sprint 1 was already resolved, it will read sprint 1's ic state and display it under sprint 2's identity.

`hooks/session-start.sh` (line 194-196) and `hooks/sprint-scan.sh` (lines 342-355, 398-401) both call `sprint_find_active` and iterate over results — both will hit this bug.

**Minimum fix:** Track which bead_id the cache belongs to:

```bash
_SPRINT_RUN_ID=""
_SPRINT_RUN_BEAD_ID=""

_sprint_resolve_run_id() {
    local bead_id="$1"
    [[ -z "$bead_id" ]] && { echo ""; return 1; }

    # Cache hit — only valid for the same bead
    if [[ -n "$_SPRINT_RUN_ID" && "$_SPRINT_RUN_BEAD_ID" == "$bead_id" ]]; then
        echo "$_SPRINT_RUN_ID"
        return 0
    fi

    local run_id
    run_id=$(bd state "$bead_id" ic_run_id 2>/dev/null) || run_id=""
    if [[ -z "$run_id" || "$run_id" == "null" ]]; then
        echo ""
        return 1
    fi

    _SPRINT_RUN_ID="$run_id"
    _SPRINT_RUN_BEAD_ID="$bead_id"
    echo "$run_id"
}
```

This preserves the performance benefit for the single-sprint (claim-time) hot path while preventing cross-bead reads in multi-sprint scans.

### 1.4 [INFORMATIONAL] GATES_PROJECT_DIR export is not dead — other commands depend on it

Current `lib-sprint.sh` line 22:

```bash
export GATES_PROJECT_DIR="$SPRINT_LIB_PROJECT_DIR"
```

The comment above it states lib-gates.sh is deprecated and no longer sourced from lib-sprint.sh. After A2, this export serves no purpose within lib-sprint.sh's own execution path. However, `commands/strategy.md`, `commands/work.md`, and others source lib-gates.sh directly (without first sourcing lib-sprint.sh). When those commands run in a session that has sourced lib-sprint.sh already, GATES_PROJECT_DIR will already be set. When they run in a fresh session without lib-sprint.sh, they set GATES_PROJECT_DIR themselves.

The export is harmless to leave. Remove it only when the lib-gates.sh migration is complete across all commands.

**No action required in A2.** Add comment: `# Retained for non-sprint commands that source lib-gates.sh directly.`

---

## 2. Pattern Analysis

### 2.1 [STRUCTURAL] sprint_create silent failure when bead creation fails but ic run succeeds

The plan makes bead creation non-fatal in sprint_create. This is the right directional change. However, the return value contract creates a silent failure mode:

When bead creation fails but ic run creation succeeds, `sprint_id` is empty and `sprint_create` returns `""`. The caller in `commands/sprint.md` line 237-243:

```bash
SPRINT_ID=$(sprint_create "<feature title>")
if [[ -n "$SPRINT_ID" ]]; then
    sprint_set_artifact "$SPRINT_ID" "brainstorm" "<brainstorm_doc_path>"
    sprint_finalize_init "$SPRINT_ID"
    sprint_record_phase_completion "$SPRINT_ID" "brainstorm"
    CLAVAIN_BEAD_ID="$SPRINT_ID"
fi
```

If bead creation fails, `SPRINT_ID` is empty, the `if` block does not execute, and `CLAVAIN_BEAD_ID` is never set. The ic run was created (with `scope_id=sprint-<epoch>`) and is active in ic's database, but it has no handle visible to the rest of the session. All subsequent sprint operations (sprint_claim, sprint_advance, sprint_read_state) will fail silently because they receive no sprint ID. The sprint is effectively orphaned in ic.

This is worse than the current behavior, which treats bead creation failure as fatal and returns early.

**Minimum fix (two options, choose one):**

Option A — Keep bead creation fatal for this pass. The E3 migration should have ensured all environments with ic installed also have bd available. The "bead creation non-fatal" design can be enabled in a later pass when there is a concrete ic-only-no-bd deployment target:

```bash
sprint_create() {
    ...
    if [[ -z "$sprint_id" ]]; then
        echo "sprint_create: bead creation failed" >&2
        echo ""
        return 1
    fi
    ...
}
```

Option B — Return a synthetic handle when bead creation fails, so CLAVAIN_BEAD_ID can still be set and the session can continue against the ic run:

```bash
# If bead creation failed, use a synthetic handle derived from the run_id
local effective_id="${sprint_id:-ic-${run_id:0:8}}"
_SPRINT_RUN_ID="$run_id"
_SPRINT_RUN_BEAD_ID="$effective_id"
echo "$effective_id"
```

This requires teaching `_sprint_resolve_run_id` to recognize `ic-` prefixed IDs and return the cached run_id directly without a `bd state` lookup. Option A is simpler and recommended for this pass.

### 2.2 [STRUCTURAL] sprint_next_step decouples from the phase chain but plan wording is misleading

The brainstorm success criteria state: "sprint_next_step reads chain from ic instead of hardcoded table." The Task 9 implementation is:

```bash
sprint_next_step() {
    local phase="$1"
    case "$phase" in
        brainstorm)          echo "strategy" ;;
        brainstorm-reviewed) echo "strategy" ;;
        strategized)         echo "write-plan" ;;
        ...
    esac
}
```

This does not read from ic. It is a new hardcoded mapping. The old implementation derived the mapping through `_sprint_transition_table`. The new implementation removes the intermediate function but replaces it with an equivalent inline case statement. This is simpler (correct) but not "reading from ic."

This is not a code defect — the phase-to-command mapping is inherently Clavain-specific and cannot be derived from ic's generic phase list. The implementation is correct. The documentation wording is inaccurate and should be corrected so future readers understand what is actually happening.

There is also a subtle behavioral difference to note: the old `sprint_next_step` derived `brainstorm → strategy` by mapping `brainstorm → brainstorm-reviewed` (via transition table) then `brainstorm-reviewed → strategy` (via next-phase mapping). The new implementation maps `brainstorm → strategy` directly, collapsing two steps. The `brainstorm-reviewed` phase still exists in ic's phase chain but has no unique command mapping from `sprint_next_step`. This was true in the old implementation as well (brainstorm-reviewed and strategized both mapped to strategy). No regression — just worth documenting.

**Minimum fix:** Update brainstorm success criteria to read "sprint_next_step uses a static phase-to-command map; the dynamic phase chain lives in ic." No code change required.

### 2.3 [INFORMATIONAL] sprint.md complexity section references deleted phase-skipping behavior

`commands/sprint.md` Pre-Step complexity assessment section (line 220) says:

> Phase skipping is also enforced automatically in sprint_advance() based on cached complexity.

After A2, `sprint_advance` no longer reads `force_full_chain` from beads or calls `sprint_should_skip`. This statement becomes false. For low-complexity sprints (score 1-2), the user will be asked whether to skip brainstorm+strategy, but there is no automatic enforcement in sprint_advance.

The plan's Task 13 should include updating this line. Without it, future implementers will look for non-existent phase-skipping enforcement in sprint_advance and waste time debugging.

**Minimum fix:** Add to Task 13 Step 1: update the "Phase skipping is also enforced automatically in sprint_advance()" line in sprint.md to: "Phase skipping for low-complexity sprints uses a shorter ic run --phases chain passed at sprint creation time."

---

## 3. Simplicity and YAGNI

### 3.1 CHECKPOINT_FILE removal — safe, no backward compat risk

Question 4 from context: the CHECKPOINT_FILE constant removal is safe. A grep of the full codebase confirms `$CHECKPOINT_FILE` is referenced only within `lib-sprint.sh` itself. No external script, hook, or command reads this variable. The plan correctly inlines the default path in `checkpoint_clear`:

```bash
rm -f "${CLAVAIN_CHECKPOINT_FILE:-.clavain/checkpoint.json}" 2>/dev/null || true
```

The only subtlety: the lock scope derivation in the old fallback (`echo "$CHECKPOINT_FILE" | tr '/' '-'`) is eliminated because Task 10's new `checkpoint_write` has no file-based fallback at all. The lock scope for checkpoints disappears entirely. This is correct — ic state writes are handled by ic's own concurrency primitives.

**No action required.** Removal is safe and correct.

### 3.2 Task 12 stub change — sprint_classify_complexity returns integer, not "medium"

Task 12 updates the jq-missing stub from `echo "medium"` to `echo "3"`. This is correct. `sprint_classify_complexity` returns integers (1-5) in all non-stub paths. The legacy string fallback in `sprint_complexity_label` (`medium → "moderate"`) will never be exercised via the integer path but remains harmless dead code.

**No action required.**

### 3.3 Double cache invalidation after sprint_advance is harmless but worth noting

After A2, the phase advance sequence is:

1. `sprint_advance` calls `intercore_run_advance` (which advances the phase in ic)
2. `sprint_advance` calls `sprint_invalidate_caches` (clears discovery cache)
3. `sprint_advance` calls `sprint_record_phase_tokens`
4. Caller in sprint.md also calls `sprint_record_phase_completion` (which calls `sprint_invalidate_caches` again)

The double cache invalidation (steps 2 and 4) is harmless — the second call is a no-op after the first. However, it creates confusion about which call is authoritative. The long-term fix is to remove `sprint_record_phase_completion` calls from sprint.md when it becomes a complete no-op. That is a separate cleanup pass.

**No action required in A2.**

---

## 4. Questions From Context — Direct Answers

**Q1: Is removing lib-gates.sh sourcing from sprint.md correct? Are there other callers that might break?**

Removing it from sprint.md is correct. The lib-gates shim (`hooks/lib-gates.sh`) is retained with no-op stubs and interphase delegation, so all other command files that source it directly (strategy, work, write-plan, brainstorm, review-doc, quality-gates, codex-sprint) will continue working without change. The risk is documentation confusion, not a runtime break (see 1.1 above).

**Q2: Is the bead-as-identity / run-as-internal layering clean?**

Yes. This is the most architecturally sound decision in the entire plan. `CLAVAIN_BEAD_ID` remaining a bead ID preserves the user-visible contract across all workflow commands. The ic run ID as a session-cached internal detail is the correct model — it is an execution context analogous to a CI pipeline run, not a ticket number. The join key (`ic_run_id` stored on the bead) is the right seam. The one structural issue is the single-variable cache creating cross-bead contamination in multi-sprint sessions (addressed in 1.3 above).

**Q3: sprint_create still does bd operations — should they be extracted?**

No, not in this pass. Extracting bead creation into a separate function would apply YAGNI unnecessarily — there is no second consumer of the bead-creation logic. The non-fatal change is architecturally correct directionally, but the return-value contract creates a silent failure mode that must be resolved first (see 2.1 above). Make bead creation fatal for this pass; revisit the non-fatal design when ic-only deployments are a concrete target.

**Q4: CHECKPOINT_FILE constant removal — any backward compat risk?**

None. The constant is used only within lib-sprint.sh. Removal is safe. See 3.1 above.

**Q5: Phase skipping functions deleted — is anything depending on them outside lib-sprint.sh?**

Confirmed safe to delete. `sprint_phase_whitelist`, `sprint_should_skip`, and `sprint_next_required_phase` are referenced only in lib-sprint.sh itself (internal use only), historical plan documents (not executable), and research docs. No active command docs, hooks, or tests call these functions except the bats test suite, which Task 14 correctly addresses.

---

## 5. Must-Fix vs. Optional

### Must fix before beginning implementation

1. **[1.2] Task ordering:** Add a Task 2 pre-step that removes the `sprint_finalize_init "$SPRINT_ID"` call from `commands/sprint.md` before the function is deleted from lib-sprint.sh. Prevents a broken intermediate state during multi-task implementation.

2. **[1.3] Cache key scope:** Add `_SPRINT_RUN_BEAD_ID` tracking to `_sprint_resolve_run_id` to prevent cross-bead state contamination in multi-sprint sessions (sprint-scan, session-start).

3. **[2.1] sprint_create return value:** Decide whether bead creation is fatal (recommended for this pass) or requires a synthetic handle strategy. The current plan leaves CLAVAIN_BEAD_ID unset on bead failure, orphaning the ic run.

### Should fix in this pass — low cost, prevents confusion

4. **[1.1] Task 13 verification scope:** Clarify success criteria so "Sprint skill does not source lib-gates.sh" is understood as sprint.md-specific, not system-wide.

5. **[2.3] sprint.md phase-skipping reference:** Update the "phase skipping is also enforced automatically in sprint_advance()" claim to reflect the new reality (ic run --phases chain set at creation time).

### Defer to a later pass

6. **[2.2] sprint_next_step documentation wording:** Correct "reads chain from ic" to "uses a static phase-to-command map." No code change needed.

7. **[1.4] GATES_PROJECT_DIR export:** Leave in place, add clarifying comment.

8. **[3.2, 3.3] Minor dead code and double invalidation:** Harmless. Clean up when sprint_record_phase_completion is fully retired.
