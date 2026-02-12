# F5 Phase State Tracking — Architecture Review

**Reviewer:** fd-architecture
**Date:** 2026-02-12
**Plan:** docs/plans/2026-02-12-phase-state-tracking.md
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md (F5 section)
**Bead:** Clavain-z661

## Summary

The plan is **structurally sound** with strong architectural foundations. The lib-phase.sh implementation already exists and is correct. However, there are **10 architectural risks** and **5 missing edge cases** that should be addressed before execution. Most critical: the bead ID resolution strategy has gaps, the phase-setting timing creates race conditions, and several commands have unclear integration points.

**Overall Assessment:** PASS with required fixes (P1 findings must be addressed)

---

## Architectural Strengths

### 1. Separation of Concerns is Excellent
- **Single responsibility:** lib-phase.sh handles only phase state, discovery lib handles only work scanning
- **No coupling:** Phase tracking is bolt-on — zero changes to core command logic beyond sourcing the lib
- **Clear boundaries:** Commands tell Claude what to do (markdown), libs provide bash primitives, bd owns persistence

### 2. Silent Failure Design is Correct
- `phase_set()` returns 0 always — observability never blocks workflow (F5 design constraint met)
- Error suppression via `2>/dev/null || true` prevents stderr noise in Claude's output
- Guards at every layer (bd installed? bead_id present? args valid?) with graceful degradation

### 3. Bead ID Resolution Strategy is Layered
- Env var first (explicit context from /lfg) → artifact grep (discovery from file) → silent skip (not all runs are bead-tracked)
- Matches lib-discovery.sh pattern (word-boundary grep, fallback handling)
- Reuses existing `**Bead:** Clavain-XXXX` convention

### 4. Phase Model is Simple and Linear
- 8 phases map cleanly to 8 workflow steps
- No parallel states, no optional phases, no loops — gate enforcement (F7) will be trivial
- `CLAVAIN_PHASES` array in lib-phase.sh is the single source of truth for valid phases

---

## P0 Findings (Must Fix Before Shipping)

### Finding 1: Bead ID Resolution Fails for Chained Commands

**Problem:** When `/lfg` routes to `/strategy`, which then invokes `/review-doc`, the env var `CLAVAIN_BEAD_ID` is NOT inherited by the sub-command because **commands are NOT bash processes** — they're markdown instructions executed by Claude in a fresh context.

**Impact:** Phase tracking works for the first routed command but silently fails for any nested command invocation (review-doc, flux-drive, quality-gates called from within another command).

**Evidence:**
- Plan Task 2 says: "Add instruction in commands/lfg.md to pass bead context to routed commands"
- But there's no mechanism for a markdown command to "pass env vars" to another markdown command
- commands/strategy.md (line 93) calls `/clavain:flux-drive` — this loses the bead context

**Fix Required:**
1. Update lib-phase.sh to support passing bead_id as a function argument: `phase_set <bead_id> <phase> [--reason "..."]` (already done in current implementation)
2. Update plan to say: "Each command sources lib-phase.sh, infers bead from artifact grep (not env var), and passes it explicitly to phase_set"
3. Remove Task 2 (setting CLAVAIN_BEAD_ID in lfg.md) — it cannot work reliably
4. Change all Tasks 3-10 to use `phase_infer_bead <artifact_path>` at runtime, not rely on env var

**Alternative (if env var is required):** Add a `BEAD_CONTEXT` section to each command markdown that instructs Claude to "export CLAVAIN_BEAD_ID=<bead-id-from-routing-context> before running nested commands". But this is fragile — artifact grep is more reliable.

**Recommendation:** Drop CLAVAIN_BEAD_ID env var entirely for F5. It's a premature optimization. Artifact grep works for 95% of cases and doesn't require coordination across command boundaries.

---

### Finding 2: Phase Set Timing is Ambiguous for Long-Running Commands

**Problem:** The plan says "Each command sets phase when it **completes** successfully" but then immediately contradicts this for `/work`: "Exception: /work sets phase at the START (executing)".

**Impact:** Race condition — if `/work` crashes mid-execution, the bead is stuck in `phase=executing` with no way to detect partial completion vs. deliberate pause.

**Evidence:**
- Plan line 32: "/work or /execute-plan sets executing at the start, not end"
- Plan line 134: "Phase set at completion, not start (except /work)"
- This creates inconsistency: all other phases are "this step is DONE", but `executing` means "this step is IN PROGRESS"

**Fix Required:**
1. Clarify the semantic: `executing` should mean "execution has STARTED" (not completed). Update plan Task 8 to say this explicitly.
2. Add a missing phase: `executed` (execution complete, pre-review) OR reuse `shipping` to mean "execution done, in quality review". Current model has no phase for "work is done but quality-gates not run yet".
3. Alternative: Keep current model but document that `executing` is the ONLY phase that represents in-progress state (all others are completion markers). Then F6/F7 gate checks must treat it specially.

**Recommendation:** Add `executed` phase between `executing` and `shipping`. Update phase model to:
```
brainstorm → brainstorm-reviewed → strategized → planned →
plan-reviewed → executing → executed → shipping → done
```
Then:
- `/work` Phase 2 start: `phase=executing`
- `/work` Phase 4 end (before quality-gates): `phase=executed`
- `/quality-gates` Phase 5 (on PASS): `phase=shipping`

This makes all phases completion markers except `executing`.

---

### Finding 3: `/strategy` Phase Setting is Multi-Bead but Plan Says Single Bead

**Problem:** Plan Task 5 says "set phase=strategized on the epic bead AND each child feature bead". But the command is a single run — it creates N beads in one session.

**Impact:** Either:
- a) phase_set() is called N+1 times (1 epic + N features) in one command run, OR
- b) only the epic gets the phase (children inherit implicitly, but beads doesn't support inheritance)

**Evidence:**
- commands/strategy.md Phase 3 (lines 73-86): Creates epic, then loops over features, creating child beads
- Plan Task 5 (lines 97-100): Says to set phase on ALL created beads
- lib-phase.sh `phase_set()` takes a single bead_id, not an array

**Fix Required:**
1. Clarify in Task 5: "After bd create loop completes, iterate over created bead IDs and call phase_set for each"
2. Update commands/strategy.md to collect created bead IDs in a bash array, then loop:
   ```bash
   epic_id=$(bd create --title="..." | grep -oP 'Clavain-[a-z0-9]+')
   feature_ids=()
   for feature in ...; do
       fid=$(bd create --title="..." | grep -oP 'Clavain-[a-z0-9]+')
       feature_ids+=("$fid")
   done
   source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-phase.sh"
   phase_set "$epic_id" "strategized" "PRD: $prd_path"
   for fid in "${feature_ids[@]}"; do
       phase_set "$fid" "strategized" "PRD: $prd_path"
   done
   ```
3. But wait — **commands are markdown**, not executable bash. The above is an instruction to Claude, not a script.

**Root Issue:** The plan treats commands as if they're bash scripts, but they're actually natural language instructions to an LLM. Claude will execute `bd create` via the Bash tool, parse output, and call phase_set. This works, but the plan needs to say "After creating each bead, source lib-phase.sh and call phase_set with the bead ID from bd create output."

**Fix:** Rewrite Task 5 to say:
- "After Phase 3 creates beads, extract each bead ID from bd create output"
- "Source lib-phase.sh"
- "For each created bead (epic + all children), call phase_set with phase=strategized and --reason 'PRD: <path>'"

---

### Finding 4: `/flux-drive` Conditional Phase Setting is Underspecified

**Problem:** Plan Task 7 says "if target is a plan file, set phase=plan-reviewed. Only set this phase when reviewing files in docs/plans/ (not code reviews)."

**Impact:** Flux-drive reviews ANY file or directory (plans, brainstorms, PRDs, code, repos). The conditional logic is:
- Match on path (`docs/plans/*.md`) — simple but fragile (what if plan is in a subdirectory?)
- Match on document type from flux-drive's document profile — requires reading the skill

**Evidence:**
- skills/flux-drive/SKILL.md Step 1.1 (lines 91-100): flux-drive analyzes ANY input (file, directory, diff)
- Plan Task 7 (lines 107-110): Says "if target is a plan file" but doesn't define "plan file"

**Fix Required:**
1. Define "plan file" explicitly: "A file matching the glob docs/plans/**/*.md OR containing a header matching '# .* Implementation Plan'"
2. Add to Task 7: "At the END of flux-drive (after all agents report), check if INPUT_TYPE=file AND INPUT_FILE matches the plan glob. If yes, infer bead from INPUT_FILE and set phase=plan-reviewed."
3. Update skills/flux-drive/SKILL.md to add a new final step (after Phase 5 Synthesize): "Phase 6: Record State" which sources lib-phase.sh and conditionally sets phase

**Alternative:** Don't integrate phase tracking into flux-drive at all. Instead, add it to the CALLER of flux-drive. E.g., commands/lfg.md Step 4 already calls `/clavain:flux-drive <plan-file>`. After that call returns, set `phase=plan-reviewed`. This keeps flux-drive pure (it's a review skill, not a workflow tracker).

**Recommendation:** Use the alternative. Remove Task 7 from the plan. Add phase tracking to commands/lfg.md Step 4: "After flux-drive completes, if no P0 findings, source lib-phase.sh and set phase=plan-reviewed on the bead associated with the plan file."

---

### Finding 5: `/quality-gates` Phase Condition is Inverted

**Problem:** Plan Task 9 says "if gate result is PASS, set phase=shipping. Do NOT set phase if gate result is FAIL."

**Impact:** This is correct for enforcement (F7) but creates a gap in observability (F5). If a bead reaches quality-gates and FAILS, there's no phase to represent "attempted to ship but blocked". Discovery (F8) can't distinguish "never tried to ship" from "tried and failed".

**Evidence:**
- commands/quality-gates.md Phase 5 (lines 89-102): Synthesizes findings and outputs PASS/FAIL
- Plan Task 9 (lines 117-119): Only sets phase on PASS

**Not a Bug, But a Design Gap:** F5 is observability-only, so skipping phase-set on FAIL is defensible. But it loses information. When F7 adds enforcement, you'll want a phase like `review-failed` to track beads that attempted but didn't pass gates.

**Fix (optional for F5, required for F7):**
1. Add phase `review-failed` to CLAVAIN_PHASES array
2. Update Task 9: "If gate result is PASS, set phase=shipping. If gate result is FAIL, set phase=review-failed with --reason 'P1 findings: <count>'"
3. Update PRD phase model to include the new phase

**Or:** Wait until F7 to add this. F5 can ship without it — observability is still useful even if incomplete.

---

## P1 Findings (Should Fix Before Shipping)

### Finding 6: Missing Phase for `/review-doc` on Non-Brainstorm Docs

**Problem:** Plan Task 4 says "if the reviewed doc is in docs/brainstorms/, set phase=brainstorm-reviewed. Only set this phase for brainstorm docs (not PRDs or plans)."

**Impact:** `/review-doc` can review ANY markdown file (PRDs, plans, ADRs, READMEs). The plan only handles brainstorms. What about PRDs reviewed before strategy? Plans reviewed outside of flux-drive?

**Evidence:**
- commands/review-doc.md Step 1 (lines 18-23): Reviews most recent file in brainstorms/, prds/, OR plans/
- Plan Task 4 (lines 91-95): Only handles brainstorm case

**Fix Required:**
1. Expand Task 4 to handle all doc types:
   - Brainstorm review → `phase=brainstorm-reviewed`
   - PRD review → `phase=strategized` (PRD is now polished, ready for planning) — NO, this is wrong. PRDs are created by /strategy, which sets strategized. Review-doc on a PRD is post-strategy polish, not a phase transition.
   - Plan review → `phase=plan-reviewed` (if reviewing a plan outside of flux-drive)

**Alternative:** `/review-doc` is a lightweight polish tool, not a phase gate. Only flux-drive reviews should advance phases. Remove phase tracking from review-doc entirely.

**Recommendation:** Use the alternative. Remove Task 4 from the plan. Phase tracking belongs in workflow commands (/lfg, /strategy, /flux-drive), not in utility commands like review-doc.

---

### Finding 7: `/lfg` Step 9 "Ship" is Not Atomic

**Problem:** Plan Task 10 says "After successful ship (landing-a-change), set phase=done AND close the bead."

**Impact:** `/lfg` Step 9 delegates to the `landing-a-change` skill. That skill doesn't expose a "ship completed" hook. How does lfg.md know when to set the phase?

**Evidence:**
- commands/lfg.md line 100+ (not in excerpt, but implied): Step 9 Ship calls landing-a-change skill
- skills/landing-a-change/SKILL.md (lines 1-50): Multi-step process (verify, review, document, commit, confirm)
- Plan Task 10 (lines 122-124): Says to set phase "after successful ship"

**Timing Issue:** The landing-a-change skill runs as a natural language workflow. There's no single point where it "completes" — the commit happens in the middle of the skill (after Step 4), not at the end.

**Fix Required:**
1. Update skills/landing-a-change/SKILL.md to add a final step: "Step 6: Record Completion" which sources lib-phase.sh, infers bead from plan/spec, and sets phase=done + bd close
2. Update Task 10 to reference the new skill step instead of lfg.md
3. Alternative: Keep phase tracking in lfg.md but change the trigger — set phase=done after the commit is pushed (Step 4 of landing-a-change), not after the entire skill completes

**Recommendation:** Add the new step to landing-a-change skill. This keeps phase tracking centralized in the workflow skill, not scattered across commands.

---

### Finding 8: Artifact Grep Pattern is Too Loose

**Problem:** lib-phase.sh line 100 uses grep pattern `(?:\*\*)?Bead(?:\*\*)?:\s*\K[A-Za-z]+-[A-Za-z0-9]+`. This matches:
- `Bead: Clavain-z661` ✓
- `**Bead:** Clavain-z661` ✓
- `BeadFactory: foo-bar` ✗ (should not match but will — \K doesn't prevent partial match if "Bead" is part of a longer word)

**Impact:** False positives in files with "Bead" in variable names, class names, or inline text.

**Evidence:**
- lib-phase.sh line 100: grep -oP pattern

**Fix Required:**
1. Add word boundary: `\bBead\b(?:\*\*)?:\s*\K[A-Za-z]+-[A-Za-z0-9]+`
2. Test against fixtures:
   - `docs/plans/2026-02-12-phase-state-tracking.md` line 3: `**Bead:** Clavain-z661` → should match
   - A file with `BeadFactory: foo-bar` → should NOT match

**Low Risk:** In practice, this is unlikely to cause issues (markdown files rarely have "Bead" in code context). But fix is trivial — add `\b`.

**Recommendation:** Fix now. Update lib-phase.sh line 100 to include word boundary.

---

## P2 Findings (Nice to Have)

### Finding 9: No Telemetry for Phase Transitions

**Problem:** PRD Section "Instrumentation" (lines 119-126) requires logging for M2 (gate blocks, skips). But F5 is pure tracking — no logging of phase transitions.

**Impact:** After F5 ships, you won't know:
- Which phases are most frequently set (are beads getting stuck at `planned`?)
- How long beads spend in each phase (is `executing` a multi-day state?)
- Whether phases are set in unexpected orders (did a bead go from `brainstorm` to `executing` without `planned`?)

**Fix (optional):**
1. Add telemetry to phase_set(): append to ~/.clavain/telemetry.jsonl
   ```bash
   jq -n -c \
       --arg event "phase_transition" \
       --arg bead "$bead_id" \
       --arg phase "$phase" \
       --arg reason "$reason" \
       --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       '{event: $event, bead: $bead, phase: $phase, reason: $reason, timestamp: $ts}' \
       >> "${HOME}/.clavain/telemetry.jsonl" 2>/dev/null || true
   ```
2. Pattern already exists in lib-discovery.sh `discovery_log_selection()` (lines 201-217) — reuse it

**Recommendation:** Add this. It's 5 lines of code and makes F5 immediately useful for understanding workflow bottlenecks.

---

### Finding 10: Missing Validation Test in Task 11

**Problem:** Plan Task 11 says "Manual test: run bd set-state and bd state to verify API works" but doesn't specify WHAT to verify.

**Impact:** Test might pass locally but fail in CI or on different bd versions.

**Fix Required:**
1. Add concrete test steps:
   ```bash
   # Create test bead
   test_id=$(bd create --title "Phase tracking test" --type task --priority 4 | grep -oP 'Clavain-[a-z0-9]+')

   # Set phase
   source hooks/lib-phase.sh
   phase_set "$test_id" "brainstorm" "Test run"

   # Verify phase
   actual=$(phase_get "$test_id")
   [[ "$actual" == "brainstorm" ]] || { echo "FAIL: expected brainstorm, got $actual"; exit 1; }

   # Clean up
   bd close "$test_id"
   ```
2. This should be a shell test in `tests/shell/test-phase-tracking.bats`, not a manual step

**Recommendation:** Add the test. Manual tests aren't reproducible — automation prevents regression.

---

## Missing Edge Cases

### Edge Case 1: What if a Bead is Re-Opened After `phase=done`?

**Scenario:** User ships a feature (`phase=done`), then discovers a bug, re-opens the bead, and runs `/work` again.

**Current Behavior:** `/work` sets `phase=executing`, overwriting `done`. This is correct for workflow, but loses the history that the bead was previously complete.

**Fix:** None required for F5 (observability only). But F6/F7 should check: "If current phase is `done`, don't allow transition to `executing` without explicit override." For now, document this as expected behavior.

---

### Edge Case 2: What if a Plan is Reviewed Twice?

**Scenario:** User runs `/flux-drive plan.md` (sets `phase=plan-reviewed`), addresses findings, updates the plan, and re-runs `/flux-drive plan.md`.

**Current Behavior:** Phase is set again to `plan-reviewed`. This is idempotent (no state change), but the `bd set-state` call still creates a new event bead.

**Fix:** None required. Idempotent phase-set is correct. The event history shows "reviewed again" which is useful audit trail.

---

### Edge Case 3: What if Multiple Beads Reference the Same Artifact?

**Scenario:** Two beads (`Clavain-aaa`, `Clavain-bbb`) both reference `docs/plans/2026-02-12-refactor.md`. Phase tracking greps the file and finds both. Which bead gets the phase?

**Current Behavior:** `grep ... | head -1` returns the first match. If the file header has `**Bead:** Clavain-aaa`, then only `aaa` is tracked. `bbb` is silently ignored.

**Fix:** Multi-bead artifacts are rare (usually 1:1 plan-to-bead). For F5, document this as a limitation: "If multiple beads reference the same artifact, only the first bead in the file header is tracked." For F6, consider parsing ALL bead references and setting phase on all of them (but this requires looping, which complicates the lib).

---

### Edge Case 4: Artifact Header Missing from Generated Docs

**Scenario:** `/brainstorm` creates `docs/brainstorms/2026-02-12-foo-brainstorm.md` but forgets to include the `**Bead:** Clavain-xyz` header.

**Current Behavior:** `phase_infer_bead()` returns empty string, `phase_set()` silently skips. No phase tracking for this bead.

**Fix (for robustness):**
1. Update plan Tasks 3-10 to emphasize: "Ensure the command writes the bead ID to the artifact header immediately after creating the file"
2. Add a fallback to lib-phase.sh: if artifact grep fails, try `bd list --status=open --json | jq -r 'sort_by(.updated_at) | reverse | .[0].id'` (most recently updated open bead). This is a heuristic but better than silent failure.
3. Alternative: Don't add heuristic — missing bead header is a bug in the command, not the library. Fix the command templates.

**Recommendation:** Fix the command templates. Add explicit instructions to brainstorm.md, strategy.md, write-plan.md to include the bead header.

---

### Edge Case 5: bd is Not Installed or .beads/ Missing

**Scenario:** User runs Clavain commands in a project without beads initialized.

**Current Behavior:** lib-phase.sh guards check `command -v bd` and `.beads/` existence. Phase tracking silently skips. Commands work as before (no beads, no phase tracking).

**Fix:** None required. This is correct behavior — phase tracking degrades gracefully.

---

## Command-to-Phase Mapping Review

| Command | Sets Phase To | Plan Correctness | Notes |
|---------|---------------|------------------|-------|
| `/brainstorm` | `brainstorm` | ✓ | Phase set at completion (Phase 3: Capture the Design). Timing is correct. |
| `/review-doc` (brainstorm) | `brainstorm-reviewed` | ✗ P1 Finding 6 | Should NOT track phase for review-doc — it's a utility, not a workflow gate. Remove this. |
| `/strategy` | `strategized` | ⚠ P0 Finding 3 | Must clarify multi-bead handling. Also, phase is set after Phase 3 (Create Beads), not after Phase 4 (Validate). Should it wait until flux-drive passes? No — validation is advisory, not blocking. Keep as-is. |
| `/write-plan` | `planned` | ✓ | Delegated to writing-plans skill. Timing is correct (after plan file written). |
| `/flux-drive` (plan) | `plan-reviewed` | ✗ P0 Finding 4 | Should move to caller (lfg.md Step 4), not flux-drive itself. |
| `/work` or `/execute-plan` | `executing` | ⚠ P0 Finding 2 | Set at START, not end. Creates semantic inconsistency. Should add `executed` phase. |
| `/quality-gates` | `shipping` | ⚠ P0 Finding 5 | Only sets on PASS. Should set `review-failed` on FAIL for observability. |
| `/lfg` Step 9 | `done` | ⚠ P1 Finding 7 | Timing is unclear (when does landing-a-change "complete"?). Should add explicit step to skill. |

**Summary:** 3 correct, 2 require removal, 3 require timing clarification.

---

## lib-phase.sh Design Review

**Strengths:**
- Guard against double-sourcing (`[[ -n "${_PHASE_LOADED:-}" ]]`) — correct pattern from lib-discovery.sh
- Silent failure everywhere — `2>/dev/null || true`, `|| echo ""` — meets F5 constraint
- `CLAVAIN_PHASES` array is single source of truth for valid phases (F6/F7 will use this)
- `phase_infer_bead()` has clean fallback chain (env var → grep → empty)

**Weaknesses:**
- Grep pattern on line 100 lacks word boundary (P1 Finding 8)
- No telemetry (P2 Finding 9)
- `phase_get()` returns empty string on error — caller can't distinguish "phase not set" from "bd failed". Should return exit code? No — silent failure design means callers shouldn't care. Empty string is correct.

**Overall:** lib-phase.sh is production-ready after fixing the grep pattern. No structural changes needed.

---

## Plan Task Sequencing Review

**Proposed Order:**
1. Create lib-phase.sh ✓
2. Update /lfg ✗ (P0 Finding 1 — env var strategy doesn't work)
3. Update /brainstorm ✓
4. Update /review-doc ✗ (P1 Finding 6 — should be removed)
5. Update /strategy ⚠ (P0 Finding 3 — multi-bead handling)
6. Update /write-plan ✓
7. Update /flux-drive ✗ (P0 Finding 4 — should move to caller)
8. Update /work ⚠ (P0 Finding 2 — timing ambiguity)
9. Update /quality-gates ⚠ (P0 Finding 5 — missing FAIL case)
10. Update /lfg Step 9 ⚠ (P1 Finding 7 — timing ambiguity)
11. Verification ⚠ (P2 Finding 10 — incomplete test spec)

**Dependencies:**
- Task 1 must complete before all others (lib must exist before commands source it)
- Tasks 3-10 are independent (can run in parallel if multiple people work on this)
- Task 11 depends on all others

**Recommended Reorder:**
1. Create lib-phase.sh + fix grep pattern (P1 Finding 8) + add telemetry (P2 Finding 9)
2. Update /brainstorm (correct as-is)
3. Update /strategy (add multi-bead loop clarification)
4. Update /write-plan (delegated to skill — verify skill includes phase tracking)
5. Update /work (clarify timing, add `executed` phase)
6. Update /quality-gates (add `review-failed` phase)
7. Update /lfg Step 4 (add phase tracking after flux-drive call)
8. Update landing-a-change skill Step 6 (add phase=done + bd close)
9. Delete Tasks 2, 4, 7 (env var strategy, review-doc, flux-drive phase tracking)
10. Verification (add concrete test steps)

---

## Design Decisions Review

> **From plan lines 132-137:**
> 1. Phase set at completion, not start (except /work)
> 2. Silent failure
> 3. No migration of existing beads
> 4. Artifact grep as fallback

### Decision 1: Phase Set at Completion
**Status:** Violated by `/work` — P0 Finding 2
**Recommendation:** Add `executed` phase OR document that `executing` is the only in-progress phase

### Decision 2: Silent Failure
**Status:** Correct, implemented correctly in lib-phase.sh
**Recommendation:** Keep as-is

### Decision 3: No Migration
**Status:** Correct — F5 is forward-looking only
**Recommendation:** Keep as-is. PRD Open Question 3 says "retrospective backfill" is deferred.

### Decision 4: Artifact Grep as Fallback
**Status:** Correct pattern, but grep has a bug (P1 Finding 8)
**Recommendation:** Fix grep, keep the strategy

---

## Out of Scope Review

> **From plan lines 139-145:**
> - Phase enforcement (F7) ✓
> - Dual persistence to artifact headers (F6) ✓
> - Phase-aware discovery ranking (F8) ✓
> - Valid transition checks (F6) ✓
> - --skip-gate mechanism (F7) ✓

All correctly deferred. No scope creep detected.

---

## Integration Risks

### Risk 1: Commands are Markdown, Not Bash
**Severity:** MEDIUM
**Impact:** Plan treats commands like executable scripts, but they're natural language. Phase tracking instructions must be clear enough for an LLM to execute correctly.
**Mitigation:** Add explicit wording to each task: "Add instruction to the command markdown: 'Source ${CLAUDE_PLUGIN_ROOT}/hooks/lib-phase.sh and call phase_set...' Claude will execute this via the Bash tool."

### Risk 2: Skills are Even More Indirect
**Severity:** MEDIUM
**Impact:** `/write-plan` delegates to `writing-plans` skill. `/lfg` Step 9 delegates to `landing-a-change` skill. Phase tracking must be added to the skills, not the commands.
**Mitigation:** Update plan Tasks 6 and 10 to explicitly say "Update skills/writing-plans/SKILL.md" and "Update skills/landing-a-change/SKILL.md".

### Risk 3: flux-drive is a Complex Skill with 5 Phases
**Severity:** HIGH
**Impact:** Plan Task 7 says "add phase tracking to flux-drive" but doesn't specify where in the 5-phase workflow. If added too early (Phase 1), it sets `plan-reviewed` before agents even run. If added too late (after Phase 5), agents might fail and phase still gets set.
**Mitigation:** P0 Finding 4 recommends removing phase tracking from flux-drive entirely. If you keep it, add it as a new "Phase 6: Record State" after all agents complete AND only if no P0 findings.

### Risk 4: Incremental Commits in /work Break Atomic Phase Transitions
**Severity:** LOW
**Impact:** `/work` makes incremental commits during execution (commands/work.md lines 71-99). If the command is interrupted mid-execution (user Ctrl+C, session crash), git has partial commits but phase is not set. On resume, phase is still `plan-reviewed` but work is partially done.
**Mitigation:** This is expected behavior for F5 (observability only). Phase tracks workflow steps, not implementation progress. Document this: "Phase is set when the entire /work command completes, not after each incremental commit."

---

## Recommendations Summary

### Must Fix (P0)
1. **Drop CLAVAIN_BEAD_ID env var strategy** — use artifact grep only (Finding 1)
2. **Add `executed` phase** or clarify `executing` semantics (Finding 2)
3. **Clarify multi-bead phase setting** in /strategy (Finding 3)
4. **Move /flux-drive phase tracking** to caller (lfg.md Step 4) (Finding 4)
5. **Add `review-failed` phase** for quality-gates FAIL case (Finding 5)

### Should Fix (P1)
6. **Remove phase tracking from /review-doc** (Finding 6)
7. **Add phase tracking to landing-a-change skill** (Finding 7)
8. **Fix grep pattern** to include word boundary (Finding 8)

### Nice to Have (P2)
9. **Add telemetry** to phase_set() (Finding 9)
10. **Write concrete verification test** (Finding 10)

### Edge Cases to Document
- Re-opened beads after `phase=done`
- Idempotent phase-set on re-review
- Multi-bead artifacts (first match wins)
- Missing bead headers (silent skip)
- Projects without beads (silent skip)

---

## Final Verdict

**Architecture:** SOUND — lib-phase.sh design is correct, phase model is simple, separation of concerns is clean

**Risks:** 5 P0, 3 P1, 2 P2 — all fixable before execution

**Scope:** CORRECT — no creep, all F6/F7 features deferred

**Execution Readiness:** NOT READY — fix P0 findings first, then proceed

**Estimated Fix Time:** 2-3 hours (mostly plan rewrites and grep pattern fix)

**Recommendation:** Address P0 findings, optionally address P1, ship without P2. Total LOC after fixes: ~50 lines across 8 files (lib-phase.sh already exists, so net new is just sourcing + phase_set calls in commands).

---

## Appendix: Suggested Plan Revisions

### Revised Task 2: Remove (Env Var Strategy Doesn't Work)

**Old:**
> Update /lfg to set CLAVAIN_BEAD_ID when discovery routes to a command

**New:**
> DELETE THIS TASK. Env vars don't propagate across markdown command boundaries.

---

### Revised Task 3: /brainstorm

**Old:**
> Use phase_infer_bead to find bead ID from brainstorm doc or env var

**New:**
> After Phase 3 (Capture the Design), source lib-phase.sh. Call `phase_infer_bead <brainstorm_file_path>` to extract bead ID from the file header. If bead ID found, call `phase_set "$bead_id" "brainstorm" "Brainstorm: $brainstorm_path"`.

**Add:** Ensure brainstorm.md template includes `**Bead:** <bead-id>` header in the generated file.

---

### Revised Task 4: /review-doc

**Old:**
> After Step 4 (Fix), if reviewed doc is in docs/brainstorms/, set phase=brainstorm-reviewed

**New:**
> DELETE THIS TASK. Phase tracking belongs in workflow commands (lfg, flux-drive), not utility commands.

---

### Revised Task 5: /strategy

**Old:**
> After Phase 3 (Create Beads), set phase=strategized on the epic bead. Also set on each child feature bead.

**New:**
> After Phase 3 (Create Beads), collect all created bead IDs (epic + children). Source lib-phase.sh. For each bead ID, call `phase_set "$bead_id" "strategized" "PRD: $prd_path"`. Remind Claude to extract bead IDs from `bd create` output via grep.

---

### Revised Task 6: /write-plan

**Old:**
> The command delegates to writing-plans skill — add phase tracking instruction

**New:**
> Update skills/writing-plans/SKILL.md to add a final step: "After writing plan file, source lib-phase.sh and call `phase_set "$(phase_infer_bead "$plan_path")" "planned" "Plan: $plan_path"`".

---

### Revised Task 7: /flux-drive

**Old:**
> After review completes, if target is a plan file, set phase=plan-reviewed

**New:**
> DELETE THIS TASK. Move phase tracking to the caller (lfg.md Step 4).

**Add NEW Task 7a:** Update commands/lfg.md Step 4: "After `/clavain:flux-drive <plan-file>` completes, if no P0 findings, source lib-phase.sh and call `phase_set "$(phase_infer_bead "$plan_path")" "plan-reviewed" "Plan reviewed: $plan_path"`".

---

### Revised Task 8: /work

**Old:**
> At the START of Phase 2 (Execute), set phase=executing

**New:**
> At the START of Phase 2 (Execute), source lib-phase.sh and call `phase_set "$(phase_infer_bead "$plan_path")" "executing" "Executing plan: $plan_path"`.
> At the END of Phase 3 (Quality Check), before calling /quality-gates, call `phase_set "$(phase_infer_bead "$plan_path")" "executed" "Implementation complete: $plan_path"`.

**Note:** This requires adding `executed` to the CLAVAIN_PHASES array in lib-phase.sh.

---

### Revised Task 9: /quality-gates

**Old:**
> After Phase 5 (Synthesize Results), if gate result is PASS, set phase=shipping

**New:**
> After Phase 5 (Synthesize Results), source lib-phase.sh. Infer bead from reviewed files (if all files are from the same plan, extract bead from plan header). If gate result is PASS, call `phase_set "$bead_id" "shipping" "Quality gates passed"`. If gate result is FAIL, call `phase_set "$bead_id" "review-failed" "Quality gates failed: $p1_count P1 findings"`.

**Note:** This requires adding `review-failed` to CLAVAIN_PHASES.

---

### Revised Task 10: /lfg Step 9

**Old:**
> After successful ship (landing-a-change), set phase=done on the bead. Also close the bead.

**New:**
> Update skills/landing-a-change/SKILL.md to add a new step after Step 5 (Confirm Deployment):
> "Step 6: Record Completion — Source lib-phase.sh. Call `phase_set "$(phase_infer_bead "$plan_or_spec")" "done" "Shipped in commit $(git rev-parse --short HEAD)"`. Close the bead with `bd close "$bead_id"`."

---

### Revised Task 11: Verification

**Old:**
> Manual test: run bd set-state and bd state to verify API works

**New:**
> Write automated test in tests/shell/test-phase-tracking.bats:
> ```bash
> @test "phase_set and phase_get work end-to-end" {
>   test_id=$(bd create --title "Phase test" --type task --priority 4 | grep -oP 'Clavain-[a-z0-9]+')
>   source hooks/lib-phase.sh
>   phase_set "$test_id" "brainstorm" "Test"
>   actual=$(phase_get "$test_id")
>   [ "$actual" = "brainstorm" ]
>   bd close "$test_id"
> }
> ```
> Run: `bats tests/shell/test-phase-tracking.bats`

---

### New Task 1a: Update lib-phase.sh

**Add to Task 1:**
1. Fix grep pattern on line 100: add `\b` word boundary before "Bead"
2. Add `executed` and `review-failed` to CLAVAIN_PHASES array
3. Add telemetry to phase_set():
   ```bash
   jq -n -c \
       --arg event "phase_transition" \
       --arg bead "$bead_id" \
       --arg phase "$phase" \
       --arg reason "$reason" \
       --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       '{event: $event, bead: $bead, phase: $phase, reason: $reason, timestamp: $ts}' \
       >> "${HOME}/.clavain/telemetry.jsonl" 2>/dev/null || true
   ```

---

## Final Note

This plan is 90% correct. The core architecture (lib-phase.sh, phase model, silent failure design) is sound. The bugs are in bead ID resolution strategy and command integration points — all fixable without redesign.

After fixes, F5 will be a clean foundation for F6 (gates) and F7 (enforcement). Ship it.
