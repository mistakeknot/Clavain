# Architecture Review: Work Discovery Plan (M1 F1+F2)

**Date:** 2026-02-12
**Reviewer:** fd-architecture
**Target:** `/root/projects/Clavain/docs/plans/2026-02-12-work-discovery.md`
**Context:** Phase-gated /lfg epic (Clavain-tayp), M1 features 1-2 only

## Executive Summary

The plan is **structurally sound** with minor integration risks and one simplification opportunity. The shared library approach is correct, the LLM-parses-text integration is acceptable for v1, and the lfg.md modification is well-bounded. Three recommendations below reduce coupling and improve testability.

**Verdict:** APPROVE with recommendations for iteration 2.

---

## 1. Shared Library Pattern (`hooks/lib-discovery.sh`)

### Analysis

**Question:** Is the shared library pattern the right abstraction?

**Answer:** YES, with a minor caveat about premature abstraction for session-start.

#### Strengths

1. **Established precedent:** Follows existing pattern of `hooks/lib.sh` (JSON utilities) and `hooks/sprint-scan.sh` (scanner functions sourced by multiple consumers). This is not speculative — it aligns with existing codebase conventions.

2. **Known consumers:** The plan identifies three consumers:
   - `commands/lfg.md` (immediate, this milestone)
   - `hooks/session-start.sh` (F4, future milestone)
   - `hooks/sprint-scan.sh` (potential future refactor to reuse discovery logic)

3. **Separation of concerns:** Library handles data gathering/inference, command file handles UI presentation. Clean boundary.

#### Risks

1. **Premature abstraction for session-start:** F4 (session-start light scan) is in a FUTURE milestone but is used as justification for the library. If F4 changes or gets cut, the abstraction may have only one real consumer (lfg.md). The plan doesn't specify what the "light scan" will actually do differently from the full scan.

2. **sprint-scan.sh overlap:** The plan mentions sprint-scan.sh as a consumer but doesn't specify the integration point. Current sprint-scan.sh has `sprint_beads_summary()` which already calls `bd stats`. There's potential duplication risk if both libraries query beads independently.

#### Recommendation

**Accept the library pattern** because:
- It has one confirmed consumer (lfg.md) NOW
- F4 is in the same epic and PRD (high confidence it will ship)
- The functions are cohesive (all about work discovery)
- Cost is low (~80 lines)

**Mitigate premature abstraction risk:**
- Ship M1 with the library used ONLY by lfg.md
- Add session-start integration in F4 milestone, not speculatively now
- Document in lib-discovery.sh header: "Currently used by lfg.md; session-start integration in F4"

**Address sprint-scan overlap:**
- sprint-scan.sh should NOT import lib-discovery.sh in v1
- Keep them separate until there's proven duplication (YAGNI)
- If they need to share beads queries later, extract a `hooks/lib-beads.sh` with just the `bd` CLI wrappers

---

## 2. LLM-Parses-Structured-Text Approach

### Analysis

**Question:** Is structured text output (scanner→LLM→AskUserQuestion) the right integration, or should it be different?

**Answer:** ACCEPTABLE for v1, with a known limitation and a path to improvement.

#### Current Approach

The plan specifies:
```
DISCOVERY_RESULTS
bead:Clavain-abc|title:Fix auth timeout|priority:1|action:execute|stale:no
bead:Clavain-def|title:Add dark mode|priority:2|action:plan|stale:yes
END_DISCOVERY
```

The LLM in `lfg.md` reads this output and constructs the AskUserQuestion call (question text, options array, etc.).

#### Strengths

1. **Simple data format:** Pipe-delimited text is easy to parse in bash, easy to read in logs, and easy for the LLM to interpret.
2. **Handles variable-length data:** The number of beads is unknown at plan-time. Structured text scales from 0 to 50 beads without schema changes.
3. **Minimal coupling:** The scanner doesn't need to know about AskUserQuestion's exact schema. The LLM acts as an adapter layer.
4. **Testable:** Bash tests can verify the scanner output format; smoke tests can verify the LLM correctly interprets it.

#### Weaknesses

1. **Two parsing steps:** Scanner emits text → LLM parses text → LLM emits AskUserQuestion JSON. This is less direct than scanner→JSON→LLM. But the extra step has negligible cost (LLMs parse text well) and keeps bash simple.

2. **Schema drift risk:** If the LLM misinterprets the format or forgets to include a field, the UI will break. Mitigation: the format is simple (5 fields, pipe-delimited), and the plan includes shell tests to verify the format.

3. **No JSON contract:** Unlike `bd list --json`, the scanner output isn't machine-parseable by downstream tools. If future features need to query discovery results programmatically, they'll need to parse the text format or refactor the scanner to emit JSON.

#### Alternative Considered (Implicit)

**Scanner emits JSON, command file passes it to AskUserQuestion:**

```bash
# In lib-discovery.sh
discovery_scan_beads() {
  bd list --status=open --json | jq -r '
    # ... jq transform to AskUserQuestion schema ...
  '
}

# In lfg.md
AskUserQuestion(options=$(source lib-discovery.sh && discovery_scan_beads))
```

**Why the plan didn't choose this:**
- Harder to test bash-generated JSON (escaping, quotes)
- Locks the scanner to AskUserQuestion's schema (breaks if schema changes)
- Harder to read in logs (JSON is verbose)

**Why this might be better:**
- No LLM parsing step
- Direct contract between scanner and UI
- Easier to extend with new fields

#### Recommendation

**Accept the structured-text approach for v1** because:
- It's simple, testable, and works
- The extra LLM parsing step is not a performance or correctness risk
- The plan includes tests to prevent schema drift

**Plan for iteration 2** (when JSON becomes necessary):
- If a second consumer (e.g., API, dashboard, Codex agent) needs discovery results, refactor `discovery_scan_beads()` to emit JSON
- Keep a `discovery_format_for_llm()` wrapper that converts JSON → text for the lfg.md LLM parsing path
- This preserves the existing integration while adding a JSON contract for programmatic consumers

**Document the tradeoff** in lib-discovery.sh:
```bash
# Output format: structured text (not JSON) for LLM parsing.
# If you need JSON for programmatic consumption, refactor to emit JSON
# and add a _format_for_llm() wrapper for the lfg.md integration.
```

---

## 3. Integration Surface (lfg.md Modification)

### Analysis

**Question:** Is the lfg.md modification well-bounded?

**Answer:** YES, with excellent backward compatibility.

#### Proposed Change

Add a "Before Starting" section at the top of lfg.md:
- If `$ARGUMENTS` is empty → run discovery, present AskUserQuestion, route to command
- If `$ARGUMENTS` is non-empty → skip discovery, proceed to Step 1 (existing pipeline)

#### Strengths

1. **Backward compatible:** Existing users who invoke `/lfg "build a feature"` see no change. The 9-step pipeline runs as before.

2. **Single responsibility:** The new section handles discovery routing. The existing steps handle the pipeline. No mixing.

3. **Clear branching:** `$ARGUMENTS` is a simple, reliable gate. No complex conditionals.

4. **Exit points defined:** Discovery either routes to another command (exit lfg.md) or falls through to Step 1 (no-op discovery). Clean control flow.

5. **Testable:** Smoke tests can verify:
   - `/lfg` with no args triggers discovery
   - `/lfg "feature"` skips discovery
   - Selecting a bead routes to the correct command

#### Risks

1. **Command routing complexity:** The discovery section must know which command to invoke for each action type:
   ```
   action:continue → /clavain:work <plan-path>
   action:execute → /clavain:work <plan-path>
   action:plan → /clavain:write-plan
   action:strategize → /clavain:strategy
   action:brainstorm → /clavain:brainstorm
   ```
   This hardcodes the mapping between action types and commands. If commands are renamed or the routing changes, lfg.md must be updated.

   **Severity:** Low. The mapping is stable (these are core workflow commands unlikely to change). If it does become a maintenance burden, extract to a library function.

2. **AskUserQuestion placement:** The command file (markdown) must construct the AskUserQuestion call inline. This means the LLM has to parse the discovery results, format them, present the UI, read the response, and route — all in one turn. If the user's selection is ambiguous or the LLM misroutes, there's no retry logic.

   **Severity:** Low. AskUserQuestion is robust, and the options are distinct (bead IDs are unique). If misrouting happens in practice, add a confirmation step.

3. **No discovery caching:** Every `/lfg` invocation runs the full beads scan. For large projects (100+ beads), this could be slow (1-2 seconds). The plan mentions a 60-second cache for F4 (session-start) but not for the on-demand lfg discovery.

   **Severity:** Low for v1. If scan time exceeds 2 seconds, add caching in iteration 2.

#### Recommendation

**Accept the lfg.md modification as-is** because:
- Clean branching on `$ARGUMENTS`
- Backward compatible
- Well-defined exit points
- Risks are low-severity and can be addressed post-launch if needed

**Optional improvement for iteration 2:**
- Extract command routing to `discovery_route_to_command()` in lib-discovery.sh (mentioned in plan but not implemented in v1):
  ```bash
  discovery_route_to_command() {
    local action="$1"
    local bead_id="$2"
    case "$action" in
      continue|execute) echo "/clavain:work <plan-path>" ;;
      plan) echo "/clavain:write-plan" ;;
      strategize) echo "/clavain:strategy" ;;
      brainstorm) echo "/clavain:brainstorm" ;;
      *) echo "/clavain:sprint-status" ;;  # fallback
    esac
  }
  ```
  This centralizes routing logic and makes it testable. But it's not necessary for v1 — the inline mapping is fine.

---

## 4. Missing Components

### Analysis

**Question:** Are there missing components or integration points?

**Answer:** Two minor gaps, neither blocking.

#### Gap 1: Plan Path Resolution

The discovery scanner infers recommended actions (continue, execute, plan, strategize, brainstorm) but doesn't resolve the PLAN FILE PATH for `action:execute` or `action:continue`.

**Where this matters:**
- `action:execute` routes to `/clavain:work <plan-path>`
- `action:continue` routes to `/clavain:work <plan-path>`

But the scanner output is:
```
bead:Clavain-abc|title:Fix auth|priority:1|action:execute|stale:no
```

Where's the plan path?

**Plan's approach (lines 77-82):**
```bash
# Fallback: check filesystem for artifacts mentioning this bead
if ! $has_plan; then
    grep -rl "Bead.*${bead_id}" docs/plans/ 2>/dev/null | head -1 | grep -q . && has_plan=true
fi
```

This detects WHETHER a plan exists, but doesn't CAPTURE the path. The LLM in lfg.md will have to run the same grep again to get the path.

**Impact:** Minor duplication. The scanner runs `grep -rl` to detect plan existence, then lfg.md runs it again to get the path.

**Fix:** Extend the scanner output to include the plan path:
```
bead:Clavain-abc|title:Fix auth|priority:1|action:execute|plan:docs/plans/2026-02-12-auth-fix.md|stale:no
```

If no plan exists, `plan:` is empty. The LLM can then pass this directly to `/clavain:work`.

#### Gap 2: Stale Beads vs Stale Plans

The plan defines staleness as "bead updated >2 days ago" (line 44). But beads have TWO timestamps:
- Bead's `updated` field (from `bd show --json`)
- Plan file's mtime (from `stat`)

Which one should determine staleness?

**Scenario:**
- Bead created 5 days ago, last `bd edit` was 5 days ago → bead updated=5d
- Plan file modified 1 day ago (you edited it yesterday) → plan mtime=1d

Is this bead stale? The bead metadata says yes (5d). The artifact says no (1d).

**Recommended behavior:**
- If the recommended action is `execute` or `continue` (work on an existing plan), use the PLAN file's mtime for staleness.
- If the recommended action is `plan`, `strategize`, or `brainstorm` (no plan exists yet), use the BEAD's updated timestamp.

This aligns staleness with "time since last work on this task" rather than "time since bead metadata was touched."

**Impact:** Low. The staleness flag is informational only in v1 (just adds a marker to the UI). If the heuristic is wrong, users ignore it. But getting it right improves ranking quality.

#### Recommendation

**Gap 1 (plan path):** Add `plan:<path>` to scanner output. Avoids duplicate grep. 5 lines of code.

**Gap 2 (staleness):** Use plan mtime when plan exists, bead updated when plan doesn't. 10 lines of code.

Both are small, low-risk additions. Include in v1 if time permits; defer to iteration 2 if not.

---

## 5. Coupling Risks

### Analysis

**Question:** Are there hidden coupling risks?

**Answer:** One moderate risk — beads CLI schema changes.

#### Risk 1: bd CLI Schema Dependency

The scanner depends on `bd list --status=open --json` output schema. Current schema (inferred from sprint-scan.sh and plan):
```json
{
  "id": "Clavain-abc",
  "title": "Fix auth timeout",
  "priority": 1,
  "status": "open",
  "updated": "2026-02-10T12:00:00Z",
  "notes": "Brainstorm: docs/brainstorms/...\nPRD: docs/prds/..."
}
```

**If beads changes the schema** (field renamed, removed, or nested), the scanner breaks.

**Mitigation in plan:** Lines 111-112 say "Handle `bd` unavailable gracefully (print warning, fall through to normal `/lfg` pipeline)". This handles MISSING beads, but not BROKEN schema.

**Better mitigation:**
- Wrap all `bd` calls in error handlers that catch jq parse failures
- If schema parse fails, fall back to text-based parsing or skip that bead
- Log a warning: "bd schema unexpected, update lib-discovery.sh"

**Cost:** 10 lines per `bd` call site. Worth it to prevent hard failures when beads updates.

#### Risk 2: AskUserQuestion API Changes

If Claude Code changes the AskUserQuestion tool's schema or behavior, the LLM's parsing logic in lfg.md might break.

**Severity:** LOW. AskUserQuestion is a stable Claude Code primitive. Schema changes are rare and backward-compatible.

**Mitigation:** Smoke tests catch this (test verifies AskUserQuestion is presented correctly).

#### Risk 3: Command Routing Stability

As noted in Section 3, the action→command mapping is hardcoded in lfg.md. If `/clavain:work`, `/clavain:strategy`, etc. are renamed or removed, discovery routing breaks.

**Mitigation:** These are core Clavain commands unlikely to change. If they do, a grep for "action:" in lfg.md finds the routing logic immediately.

#### Recommendation

**Add robust error handling for `bd` CLI calls:**
```bash
discovery_scan_beads() {
  if ! command -v bd &>/dev/null; then
    echo "DISCOVERY_UNAVAILABLE: bd not installed" >&2
    return 1
  fi

  local bd_output
  if ! bd_output=$(bd list --status=open --json 2>&1); then
    echo "DISCOVERY_UNAVAILABLE: bd query failed: $bd_output" >&2
    return 1
  fi

  # Validate JSON parse works
  if ! echo "$bd_output" | jq -e 'type == "array"' &>/dev/null; then
    echo "DISCOVERY_UNAVAILABLE: bd output not valid JSON" >&2
    return 1
  fi

  # ... rest of scanner logic
}
```

This ensures the scanner fails gracefully rather than crashing with cryptic jq errors.

---

## 6. Simplification Opportunities

### Analysis

**Question:** Is there unnecessary complexity?

**Answer:** One minor opportunity — over-engineered fallback logic.

#### Complexity Point: Dual-Source Artifact Detection

The plan's `infer_bead_action()` function (lines 62-96) checks BOTH:
1. Bead notes field: `[[ "$notes" == *"Plan:"* ]]`
2. Filesystem grep: `grep -rl "Bead.*${bead_id}" docs/plans/`

**Rationale (implicit):** Beads notes might be outdated, so check filesystem as fallback.

**Problem:** This creates two sources of truth and no clear priority. What if:
- Bead notes say `Plan: docs/plans/old-plan.md` (deleted file)
- Filesystem grep finds `docs/plans/new-plan.md` (new file, bead notes not updated)

Which is correct?

**YAGNI violation:** The plan doesn't show evidence that bead notes will be stale in practice. The fallback might be solving a problem that doesn't exist.

#### Recommendation

**Simplify in v1:**
- Use ONLY the filesystem grep: `grep -rl "Bead.*${bead_id}" docs/plans/`
- Delete the notes-parsing logic
- Rationale: Filesystem is the source of truth for artifacts. Beads notes are freeform text, not structured metadata.

**If notes-parsing is desired later:**
- Add it as an OPTIMIZATION in iteration 2 (faster than grep)
- But treat filesystem as authoritative — if they conflict, filesystem wins
- Document the priority explicitly

**Estimated savings:** 10 lines of code, simpler tests, one fewer coupling point.

---

## 7. Test Coverage

### Analysis

The plan includes:
- Shell tests (bats) for scanner output format, sorting, staleness
- Structural tests (pytest) for file existence
- Manual smoke tests for end-to-end discovery flow

**Strengths:**
- Covers the critical path (scanner → output format → LLM parsing → routing)
- Unit tests for sorting/staleness logic
- Graceful-fallback test (bd unavailable)

**Gaps:**
1. **No test for action inference logic** — the core `infer_bead_action()` function determines routing, but there's no test verifying it returns the correct action for each scenario (in_progress → continue, has plan → execute, etc.). This is tested indirectly via the full scanner, but a unit test would make failures easier to debug.

2. **No test for grep-based artifact detection** — if the grep pattern `"Bead.*${bead_id}"` fails to match a real bead reference (e.g., `**Bead:** Clavain-abc` with extra formatting), the scanner will misclassify the bead. A test with fixture markdown files would catch this.

3. **No telemetry test** — the plan adds `discovery_log_selection()` for telemetry but doesn't test it. If the telemetry path is unwritable or the JSON is malformed, it should fail silently (per plan line 172), but a test should verify the happy path works.

#### Recommendation

**Add to tests/shell/test_discovery.bats:**
```bash
@test "infer_bead_action returns correct action for each state" {
  # Mock bd show --json output for each scenario
  # Verify: in_progress → continue, has plan → execute, etc.
}

@test "grep pattern matches beads metadata in markdown" {
  # Create fixture files with various bead reference formats
  # Verify grep finds them all
}

@test "telemetry logging writes valid JSON" {
  # Call discovery_log_selection with mock data
  # Verify telemetry.jsonl contains valid JSON line
}
```

**Estimated cost:** 30 lines of test code. High value for debugging and preventing regressions.

---

## 8. Summary of Recommendations

| Issue | Severity | Action | When |
|-------|----------|--------|------|
| Sprint-scan overlap | Low | Keep libraries separate; extract lib-beads.sh only if duplication proven | Iteration 2 |
| LLM-parses-text limitations | Low | Accept for v1; add JSON output when 2nd consumer needs it | Iteration 2 |
| Command routing coupling | Low | Extract to lib function only if mapping becomes complex | Iteration 2 |
| Plan path missing from output | Medium | Add `plan:<path>` field to scanner output | V1 (if time permits) |
| Staleness logic ambiguity | Medium | Use plan mtime when plan exists, bead updated otherwise | V1 (if time permits) |
| bd CLI error handling | High | Add robust error handling for bd calls (fallback to unavailable) | V1 (required) |
| Dual-source artifact detection | Medium | Simplify to filesystem-only; delete notes-parsing fallback | V1 (simplification) |
| Action inference tests | Medium | Add unit tests for infer_bead_action logic | V1 (if time permits) |
| Telemetry tests | Low | Add happy-path test for discovery_log_selection | Iteration 2 |

### P0 for V1 Shipment

1. **Robust bd error handling** (prevents hard crashes)
2. **Simplify to filesystem-only artifact detection** (reduces complexity)

### P1 for V1 (Ship if Time Permits)

3. **Add plan path to scanner output** (avoids duplicate grep)
4. **Fix staleness logic** (use plan mtime when available)
5. **Add action inference tests** (improves debuggability)

### Defer to Iteration 2

6. **JSON output alternative** (when 2nd consumer needs it)
7. **Extract command routing** (if mapping becomes complex)
8. **Telemetry tests** (nice-to-have, not critical path)

---

## Final Verdict

**APPROVE** with 2 required changes for v1 (bd error handling, simplify artifact detection) and 3 recommended enhancements (plan path, staleness fix, action tests).

The plan demonstrates solid architectural thinking:
- Library pattern aligns with existing precedent
- Integration surface is well-bounded
- Backward compatibility preserved
- Test coverage is good (with minor gaps)

The LLM-parses-text approach is pragmatic and works for v1. The structured-text format is simple and testable. The lfg.md modification is clean.

**Risk level:** LOW. The main risks (bd schema changes, command routing coupling) are mitigated by error handling and clear documentation.

**Ship confidence:** HIGH after P0 changes applied.
