# Quality Review: M2 Command Docs (enforce_gate Integration)

**Scope:** enforce_gate pre-checks added to commands/work.md, commands/execute-plan.md, commands/quality-gates.md, commands/lfg.md

**Date:** 2026-02-13

---

## Executive Summary

The diff adds enforce_gate calls before advance_phase to enforce phase-transition gates at 4 execution points. Overall quality is good, but there are **2 P1 issues** (variable naming inconsistency, lfg.md bead-ID routing missing validation), **3 P2 issues** (error message clarity/consistency, missing comment patterns), and **1 P3 issue** (redundant phase tracking in lfg.md Step 5).

---

## P1 Findings (Critical - Must Fix)

### 1. Variable Naming Inconsistency: BEAD_ID vs CLAVAIN_BEAD_ID

**Files affected:**
- work.md (line 55): uses `BEAD_ID=$(phase_infer_bead ...)`
- execute-plan.md (line 11): uses `BEAD_ID=$(phase_infer_bead ...)`
- quality-gates.md (line 109): uses `BEAD_ID="${CLAVAIN_BEAD_ID:-}"`
- lfg.md (lines 116, 149): uses `CLAVAIN_BEAD_ID` (from context, already set)

**Issue:** work.md and execute-plan.md locally infer and store the bead ID as `BEAD_ID`, but lfg.md and quality-gates.md expect `CLAVAIN_BEAD_ID` (session-level context). These are isolated code examples, not shared functions, but they create a mental model mismatch.

**Why it matters:** When users copy these patterns into actual commands, they will use different variable names at different callsites. Commands that delegate to /work or /execute-plan will pass a computed `BEAD_ID`, while commands that invoke /quality-gates will reference `CLAVAIN_BEAD_ID`. This inconsistency will confuse users porting patterns and make shell scripts fragile.

**Recommendation:**
- **Option A (Recommended):** Standardize all on `CLAVAIN_BEAD_ID` in the examples. If the bead ID must be inferred locally (as in work.md), use:
  ```bash
  CLAVAIN_BEAD_ID=$(phase_infer_bead "<input_document_path>")
  ```
  This aligns with lfg.md's session-level context variable, which is the "authoritative" source once set (line 37 of lfg.md: "remember the selected bead ID as `CLAVAIN_BEAD_ID`").

- **Option B:** Keep work.md/execute-plan.md using `BEAD_ID` (local to their phase), but add a comment explaining: "# Local context — use $CLAVAIN_BEAD_ID if invoked within a broader workflow"

**Best choice:** Option A. Use `CLAVAIN_BEAD_ID` consistently across all four files.

---

### 2. lfg.md: Bead-ID Direct Routing Missing Validation Loop

**File:** commands/lfg.md, lines 63-65 (new section)

**Issue:** The new bead-ID argument routing (lines 63-65) says:
```
- **If `$ARGUMENTS` matches a bead ID** (format: `[A-Za-z]+-[a-z0-9]+`): Verify it exists with `bd show <bead_id> 2>/dev/null`. If valid, set `CLAVAIN_BEAD_ID` and route directly — run the discovery scanner for just this bead to determine its phase and action, then route per step 6 above.
```

But the instructions don't provide the bash code block. Compare to line 30-34, which shows the pattern already exists in the discovery scanner (pre-flight check). **The pattern should be copied here**, with a code block that:
1. Validates the bead ID format with regex
2. Runs `bd show <bead_id>` and captures the result
3. Extracts the phase and action from the result
4. Routes per step 6 (line 39-53)

**Why it matters:** Without the code block, users can't follow the instructions. The Phase Tracking section (lines 71-77) shows code blocks for other patterns; this one should too. Also, the instructions say "run the discovery scanner for just this bead" but don't show how to filter the discovery scanner to a single bead (no API documented for that).

**Recommendation:**
- Add a code block showing the full validation + routing flow
- Either: (A) document a discovery filter parameter, OR (B) simplify to "verify the bead exists, set CLAVAIN_BEAD_ID, and re-invoke /clavain:lfg (discovery will auto-detect the phase)"
- Keep the regex validation to catch malformed IDs early

**Suggested code block:**
```bash
# Validate bead-ID format and existence
if [[ "$ARGUMENTS" =~ ^[A-Za-z]+-[a-z0-9]+$ ]]; then
    if bd show "$ARGUMENTS" 2>/dev/null >/dev/null; then
        CLAVAIN_BEAD_ID="$ARGUMENTS"
        # Run discovery scanner (will return 1 result for this bead)
        DISCOVERY_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-discovery.sh" && discovery_scan_beads "$CLAVAIN_BEAD_ID"
        # Then route per step 6 (lines 39-53)
    else
        echo "Bead not found: $ARGUMENTS" >&2
        # Proceed to Step 1
    fi
fi
```

---

## P2 Findings (Important - Should Fix)

### 1. Error Messages: Inconsistent Tone and Specificity

**Locations:**
- work.md (line 57): "Gate blocked: run /clavain:flux-drive on the plan first, or set CLAVAIN_SKIP_GATE='reason' to override."
- execute-plan.md (line 13): **identical** to work.md
- quality-gates.md (line 112): "Gate blocked: review findings are stale or pre-conditions not met. Re-run /clavain:quality-gates or set CLAVAIN_SKIP_GATE='reason' to override."
- lfg.md (line 117): "Gate blocked: plan must be reviewed first. Run /clavain:flux-drive or set CLAVAIN_SKIP_GATE='reason'."
- lfg.md (line 150): "Gate blocked: review findings are stale. Re-run /clavain:quality-gates or set CLAVAIN_SKIP_GATE='reason'."

**Issues:**
1. **Inconsistent second half:** Lines 57 (work/execute-plan) include "or set CLAVAIN_SKIP_GATE='reason' to override", but line 117 (lfg executing) drops the "to override" phrase. Line 150 (lfg shipping) keeps it.
2. **Inconsistent first half:** Line 112 says "review findings are stale **or** pre-conditions not met", but that's vague. Line 150 just says "review findings are stale", which is clearer.
3. **Vague in work.md/execute-plan.md:** "run /clavain:flux-drive on the plan first" — but the caller might not have a plan file path. Better to say "ensure the plan has been reviewed via /clavain:flux-drive" or "run /clavain:flux-drive <plan-file>".

**Why it matters:** Users comparing messages across commands will see mixed patterns. The lib-gates.sh source (lines 277-278 in interphase) uses:
```bash
echo "ERROR: phase gate blocked $target for $bead_id (tier=hard)" >&2
echo "  Set CLAVAIN_SKIP_GATE=\"reason\" to override, or run /clavain:flux-drive first" >&2
```

These command docs should echo that tone, not introduce their own variations.

**Recommendation:** Standardize error messages to this pattern:
```bash
echo "Gate blocked: cannot advance to <phase>. First step:" >&2
echo "  - Run /clavain:flux-drive <artifact> to review, OR" >&2
echo "  - Set CLAVAIN_SKIP_GATE='reason' to skip enforcement" >&2
```

**Specific fixes:**
- **work.md (line 57):** Change to:
  ```bash
  echo "Gate blocked: cannot execute — plan must be reviewed first." >&2
  echo "  Run /clavain:flux-drive <input_document_path> or set CLAVAIN_SKIP_GATE='reason' to override." >&2
  ```

- **execute-plan.md (line 13):** Same as work.md, using `<plan_file_path>` instead

- **quality-gates.md (line 112):** Change to:
  ```bash
  echo "Gate blocked: cannot ship — review findings are stale or gates were not passed." >&2
  echo "  Re-run /clavain:quality-gates or set CLAVAIN_SKIP_GATE='reason' to override." >&2
  ```

- **lfg.md (line 117):** Change to match work.md pattern (both are executing phase)

- **lfg.md (line 150):** Change to match quality-gates.md pattern (both are shipping phase)

---

### 2. Missing Explicit "Do NOT proceed" Comment Pattern

**Locations:**
- work.md (line 58): Has comment "# Stop and tell user — do NOT proceed to execution"
- execute-plan.md (line 14): Has comment "# Stop and tell user — do NOT proceed to execution"
- quality-gates.md (line 113): Has comment "# Do NOT advance phase — stop and tell user"
- lfg.md (line 118): Has comment "# Stop — do NOT proceed to execution" (shorter form)
- lfg.md (line 151): Has comment "# Do NOT advance to shipping — stop and tell user"

**Issue:** Comments vary slightly in style (some say "Stop and tell user", others say "do NOT advance phase"). Compare to work.md/execute-plan.md which have the most explicit pattern. Standardize across all four files.

**Recommendation:** Use the most explicit pattern: "# Stop — do NOT proceed (no fallthrough to next step)". This makes it clear the script should exit here, not continue to advance_phase.

---

### 3. Code Block Structure Inconsistency: guard vs if-without-else

**Locations:**
- work.md (lines 56-60): guard pattern (if ! ... then echo/fi, then advance_phase outside the block)
- execute-plan.md (lines 12-16): guard pattern (same as work.md)
- quality-gates.md (lines 111-117): **if/else pattern** (enforce_gate is inside an if, with else containing advance_phase)
- lfg.md (lines 116-119): guard pattern (if ! ... then echo/fi, then advance_phase outside the block)
- lfg.md (lines 149-154): **if/else pattern** (same as quality-gates.md)

**Issue:** Two structural patterns are mixed:

**Pattern A (Guard)** — work.md, execute-plan.md, lfg line 116:
```bash
if ! enforce_gate ...; then
    echo "Gate blocked: ..." >&2
    # Stop comment
fi
advance_phase ...  # Always executed if gate passes
```

**Pattern B (If/else)** — quality-gates.md, lfg lines 149-154:
```bash
if ! enforce_gate ...; then
    echo "Gate blocked: ..." >&2
    # Comment
else
    advance_phase ...
fi
```

**Problem:** Pattern A is cleaner and matches the guard idiom in Bash (fail fast). Pattern B is more explicit about the branch. Neither is wrong, but mixing them in the same file (lfg.md has both at lines 116 and 149) is confusing.

**Why it matters:** Users copying patterns will see inconsistent control flow. Pattern A is more idiomatic for early exits (fail fast); Pattern B is more explicit for conditionally executing the next step. In these cases, advance_phase should **always** be called if the gate passes (no other side effects in the else branch), so Pattern A is better.

**Recommendation:** Use Pattern A (guard) consistently across all four files. It's clearer and more idiomatic.

**Specific change:** quality-gates.md (lines 111-117) should be:
```bash
if ! enforce_gate "$BEAD_ID" "shipping" ""; then
    echo "Gate blocked: review findings are stale or pre-conditions not met. Re-run /clavain:quality-gates or set CLAVAIN_SKIP_GATE='reason' to override." >&2
    # Stop — do NOT proceed (no fallthrough to advance_phase)
else
    advance_phase "$BEAD_ID" "shipping" "Quality gates passed" ""
fi
```

Wait, that's still the if/else pattern. Actually, the guard pattern would not check for errors — it would just call enforce_gate and fail if it returns 1. Let me reconsider: the **correct** guard pattern for this case is:

```bash
if ! enforce_gate "$BEAD_ID" "shipping" ""; then
    echo "Gate blocked: ..." >&2
    # Stop and tell user
    # (implicit: no fallthrough)
fi
advance_phase "$BEAD_ID" "shipping" "Quality gates passed" ""
```

But this has a subtle issue: if enforce_gate returns 1, we echo and then... continue to advance_phase anyway (because the script doesn't exit). So Pattern B (if/else) is actually **correct** here. The issue is that work.md/execute-plan.md/lfg line 116 use Pattern A, which relies on the **calling script** to exit after the command errors. That's not guaranteed.

**Revised recommendation:** Use Pattern B (if/else) consistently. This ensures advance_phase is only called if the gate passes:

```bash
if ! enforce_gate "$BEAD_ID" "shipping" ""; then
    echo "Gate blocked: ..." >&2
    # Do NOT advance phase
else
    advance_phase "$BEAD_ID" "shipping" "Quality gates passed" ""
fi
```

Apply to all four files.

---

## P3 Findings (Nice-to-Have)

### 1. Redundant Phase Tracking in lfg.md Step 5

**File:** commands/lfg.md, lines 113-119

**Issue:** The instructions say:

> **Gate check:** Before executing, enforce the gate:
> ```bash
> GATES_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
> if ! enforce_gate "$CLAVAIN_BEAD_ID" "executing" "<plan_path>"; then
>     echo "Gate blocked: plan must be reviewed first. Run /clavain:flux-drive or set CLAVAIN_SKIP_GATE='reason'." >&2
>     # Stop — do NOT proceed to execution
> fi
> ```
>
> Run `/clavain:work <plan-file-from-step-3>`
>
> **Phase:** At the START of execution (before work begins), set `phase=executing` with reason `"Executing: <plan_path>"`.

But the /work command **also** has enforce_gate + advance_phase (lines 50-60 in work.md). So the user will:
1. Enforce gate in lfg.md (line 116)
2. Call /work (line 122)
3. /work will enforce gate again (line 56)
4. /work will advance_phase (line 60)

This is **redundant**. The gate enforcement in lfg.md (step 5) is unnecessary because /work already enforces it.

**Why it matters:** It's not a bug (enforce_gate is idempotent), but it's confusing documentation. Users wonder why the gate is checked twice. Also adds latency (2 bd calls instead of 1).

**Recommendation:** Remove the enforce_gate block from lfg.md Step 5. The instructions already say "Run `/clavain:work`", which handles the gate internally. Just document that /work will enforce the executing gate as a prerequisite.

**Suggested revision:** Delete lines 113-120, keep only:
```markdown
## Step 5: Execute

Run `/clavain:work <plan-file-from-step-3>`

The /work command enforces the executing gate as a prerequisite. If the gate blocks, follow the error message.

**Phase:** At the START of execution (before work begins), set `phase=executing` with reason `"Executing: <plan_path>"`.
```

---

### 2. lfg.md Step 6: Clarify "Already Reviewed" Assumption

**File:** commands/lfg.md, lines 128-139

**Issue:** Step 6 says:

> Run the project's test suite and linting before proceeding to review

But this assumes tests pass. If tests are failing, Step 7 (quality-gates) will run reviewer agents on a broken build, which wastes time. The instructions do say:

> **If tests fail:** Stop. Fix failures before proceeding. Do NOT continue to quality gates with a broken build.

But this is buried in a wall of text. The emphasis should be higher.

**Recommendation:** Add a gate-check-style code block before Step 7:

```bash
# Verify no test failures before running quality gates
if ! <project-test-command>; then
    echo "Tests failed. Fix failures before running quality gates." >&2
    exit 1
fi
```

This is more actionable than prose. (P3 because it's documentation clarity, not a correctness issue.)

---

### 3. lfg.md Step 7: Clarify That Gate Check Is Parallel to Resolve

**File:** commands/lfg.md, lines 141-155

**Issue:** The instructions say "Parallel opportunity: Quality gates and resolve can overlap". This is good, but the code block for the gate check + phase is long and might discourage users from starting a parallel /resolve command.

**Recommendation:** Move the "Parallel opportunity" note into the code block as a comment:

```bash
# Parallel opportunity: Start /clavain:resolve in parallel while these gates run.
# Do NOT proceed to Step 9 until both complete.

GATES_PROJECT_DIR="." source "${CLAUDE_PLUGIN_ROOT}/hooks/lib-gates.sh"
if ! enforce_gate "$CLAVAIN_BEAD_ID" "shipping" ""; then
    echo "Gate blocked: ..." >&2
else
    advance_phase "$CLAVAIN_BEAD_ID" "shipping" "Quality gates passed" ""
fi
```

(P3 because it's an improvement to user experience, not correctness.)

---

### 4. lfg.md Step 2: Inconsistent Capitalization of Phase Names

**File:** commands/lfg.md, lines 82-91

**Issue:** The strategize phase is documented as `phase=strategized` (line 91), but earlier it's called "Strategize" (line 85). Compare to other steps: "Brainstorm" (line 79) → `phase=brainstorm` (line 82). The phase name is correct, but the verb capitalization is inconsistent.

**Recommendation:** Minor — no action needed. Phase names are correct (brainstorm, strategized, planned, plan-reviewed, executing, shipping, done). The step titles are verbs (Brainstorm, Strategize), which is fine.

---

## Summary Table

| Severity | Category | File:Line | Issue | Fix |
|----------|----------|-----------|-------|-----|
| P1 | Naming | work.md:55, execute-plan.md:11 | BEAD_ID vs CLAVAIN_BEAD_ID inconsistency | Standardize on CLAVAIN_BEAD_ID |
| P1 | Missing Code | lfg.md:63-65 | Bead-ID validation loop not documented | Add code block for bead-ID format + existence check |
| P2 | Messages | work.md:57, execute-plan.md:13, quality-gates.md:112, lfg.md:117, lfg.md:150 | Inconsistent error message tone/specificity | Standardize to 2-line format (problem + solution) |
| P2 | Control Flow | work.md:56, execute-plan.md:12, quality-gates.md:111, lfg.md:116, lfg.md:149 | Mixed guard vs if/else patterns | Use if/else consistently (ensure fallthrough safety) |
| P2 | Comments | All files | Inconsistent comment styles | Standardize to "# Stop — do NOT proceed (no fallthrough)" |
| P3 | Redundancy | lfg.md:113-120 | Duplicate enforce_gate (also in /work) | Remove gate check from lfg Step 5, clarify /work handles it |
| P3 | Clarity | lfg.md:128-139 | Test failure handling buried in prose | Add code block showing test check before Step 7 |
| P3 | UX | lfg.md:141-155 | Parallel opportunity note not prominent | Add comment in code block |

---

## Recommendations Summary

**Must fix (P1):**
1. Standardize all variable names to CLAVAIN_BEAD_ID
2. Add bead-ID validation code block to lfg.md lines 63-65

**Should fix (P2):**
1. Standardize error messages to 2-line format
2. Use if/else pattern consistently across all 4 files
3. Standardize comment styles to be more explicit

**Nice-to-have (P3):**
1. Remove redundant enforce_gate from lfg.md Step 5
2. Add test-check code block before quality gates
3. Highlight parallel opportunity in code comment

---

## Patterns Verified Against Source

✓ enforce_gate signature: `enforce_gate $1=bead_id $2=target_phase $3=artifact_path` (interphase lib-gates.sh:214)
✓ enforce_gate return: 0 = pass, 1 = hard block (lines 243-295)
✓ advance_phase signature: `advance_phase $1=bead_id $2=target $3=reason $4=artifact_path` (lines 303-326)
✓ CLAVAIN_SKIP_GATE override: documented in enforce_gate (lines 259-266)
✓ VALID_TRANSITIONS: includes executing and shipping as valid targets (lines 23-49)
✓ ARTIFACT_PHASE_DIRS: docs/brainstorms and docs/plans only (line 53) — so phase tracking skips other dirs

---

## Files Ready for Revision

- /root/projects/Clavain/commands/work.md
- /root/projects/Clavain/commands/execute-plan.md
- /root/projects/Clavain/commands/quality-gates.md
- /root/projects/Clavain/commands/lfg.md
