# User & Product Validation: Phase-Gated /lfg PRD

**Reviewed:** 2026-02-12
**Reviewer:** fd-user-product
**Document:** docs/prds/2026-02-12-phase-gated-lfg.md

## Executive Summary

**Verdict:** READY FOR PLANNING (P0 issues resolved)

The PRD successfully incorporated all critical findings from the brainstorm reviews. The two major structural decisions — separating work discovery from phase gates, and making entry points implicit — were correctly implemented. Tiered gate enforcement by priority is present. The 3-layer state model recommendation was NOT adopted, but the PRD's simpler single-dimension phase model is acceptable for v1.

**Remaining issues:** 2 P2 usability gaps (discovery ranking validation, filter mechanisms) and 1 P3 scope question (retrospective backfill). None block planning.

---

## Review Methodology

I verified that the PRD addressed the 7 key findings from the original fd-user-product and fd-architecture reviews:

1. **Work discovery and phase gates are orthogonal** (architecture P0)
2. **Entry point should be implicit from first action** (user P1)
3. **Tiered gates by priority** (user P1)
4. **Shared gate library** (architecture P1)
5. **Dual persistence** (architecture P1)
6. **Session-start scan with TTL cache** (architecture P2)
7. **Merged `tested` phase into `executing`** (architecture P3)

---

## Finding 1: Work Discovery + Phase Gates Split (INCORPORATED ✓)

**Original finding (architecture P0):** "Work discovery and phase gates are orthogonal — can ship separately"

**PRD implementation:**
- Lines 9-11: "Two milestones shipped independently: (1) Work Discovery scans beads... (2) Phase Gates track workflow state"
- Lines 103-114: Rollout plan shows M1 (Work Discovery) and M2 (Phase Gates) as separate milestones
- Non-goals (lines 92-94): "No 3-layer state model — single phase dimension... can add micro-status later if review cycles prove painful"

**Assessment:** FULLY INCORPORATED. The PRD makes the independence explicit and acknowledges the 3-layer model as a future option if needed. This is a pragmatic v1 decision — ship simpler model first, validate hypothesis, iterate if problems emerge.

**User impact:** Positive. Work discovery delivers immediate value (faster work triage) without waiting for complex phase-gate implementation.

---

## Finding 2: Entry Point Implicit, Not Upfront Classification (INCORPORATED ✓)

**Original finding (user P1):** "Make entry point implicit from first action rather than explicit upfront decision"

**PRD implementation:**
- Lines 54-55: "Entry point inferred from first action (not upfront classification)"
- Line 55: "Missing phase labels set on first touch (inferred from command being run)"

**Contrast with brainstorm:**
- Brainstorm proposed `bd set-state <id> entry=<phase>` as upfront decision
- PRD removes explicit entry-point setting, makes it emergent from workflow

**Assessment:** FULLY INCORPORATED. The forcing function is gone. Users don't have to predict "is this a bug or feature" before starting work.

**User flow validation:**

**Scenario A:** User discovers a bug, runs `/clavain:work` directly (skipping brainstorm/PRD).
- Brainstorm design: User must set `entry=planned` upfront
- PRD design: First `/work` call auto-sets `phase=executing` (line 55)
- Result: Friction eliminated ✓

**Scenario B:** User has vague idea, starts with `/clavain:brainstorm`.
- PRD design: Sets `phase=brainstorm` on first touch
- Later commands validate phase sequence from there
- Result: Natural flow ✓

**Missing flow (minor):** What if user creates bead manually (`bd create`) but doesn't run any `/clavain:*` command? Does the bead stay phase-less indefinitely?

**Fix (already in PRD):** Line 55 says "set on first touch" — this covers the case. The bead enters the phase sequence when user runs their first workflow command.

---

## Finding 3: Tiered Gate Enforcement by Priority (INCORPORATED ✓)

**Original finding (user P1):** "Tiered gate strictness: P0/P1 hard gates, P2/P3 soft warnings, P4 no gates"

**PRD implementation:**
- Lines 70-77 (F7: Tiered Gate Enforcement):
  - P0/P1: hard gates, `--skip-gate --reason` required
  - P2/P3: soft gates, warning printed but proceeds
  - P4: no gates, tracking only
- Line 76: Stale review detection (git log check)
- Line 77: Skip overrides recorded in bead notes

**Assessment:** FULLY INCORPORATED with enhancements.

**User impact analysis:**

**Small change (P3 or P4):** User fixing typo in docs
- Old friction (brainstorm design): 4 gate checks, 2 `--skip-gate` flags required
- New friction (PRD design): P4 has no gates, P3 gets soft warning → user proceeds
- Result: Friction reduced from blocking to nudging ✓

**Medium change (P2 feature):** Standard workflow
- Soft warning reminds user to review, but doesn't block momentum
- Result: Balance between discipline and velocity ✓

**Critical change (P0 hotfix):** Production emergency
- Hard gate still requires `--skip-gate --reason "production broken"`
- Records accountability in bead notes
- Result: Safety preserved, override is explicit ✓

**Missing scenario:** What if user genuinely disagrees with priority classification? Example: user thinks a bug is P2, agent classifies it P0 during `/brainstorm`.

**Current flow:** Gates enforce based on bead priority field. User can change priority via `bd update` before running gated command.

**Gap:** PRD doesn't document the "change priority to bypass gate" escape hatch. Low severity (users will discover it), but worth mentioning in docs.

---

## Finding 4: Shared Gate Library (INCORPORATED ✓)

**Original finding (architecture P1):** "Extract gate check into shared library to prevent duplication across 5 commands"

**PRD implementation:**
- Lines 59-66 (F6: Shared Gate Library):
  - `hooks/lib-gates.sh` with `check_phase_gate()` and `advance_phase()`
  - `VALID_TRANSITIONS` array defines phase graph
  - `is_valid_transition()` function for validation
- Line 65: Dual persistence (artifact phase checkpoint + beads label)
- Line 66: Fallback if `bd state` fails (read from artifact header)

**Assessment:** FULLY INCORPORATED. The design matches the architecture review recommendation exactly.

**Validation:**

Commands will call:
```bash
source hooks/lib-gates.sh
check_phase_gate <id> <required> <target> <artifact-check-fn>
```

**Benefits:**
- 5 lines per command instead of 30 (150 lines saved)
- Centralized phase graph (one place to add transitions)
- Consistent error messages

**Missing detail:** PRD doesn't specify the artifact-check-fn interface. Example for `/strategy`:
```bash
check_flux_review() {
  # Verify flux-drive review exists and has no P0 findings
}
```

**Severity:** P3. Implementation detail, not a design flaw. Planner will define interface.

---

## Finding 5: Dual Persistence (INCORPORATED ✓)

**Original finding (architecture P1):** "Write phase to artifact headers + beads labels to prevent total blockage if beads unavailable"

**PRD implementation:**
- Line 65: "Artifact phase checkpoint: commands write `**Phase:** <value>` to artifact markdown headers"
- Line 66: "Fallback: if `bd state` fails, read phase from artifact header"

**Assessment:** FULLY INCORPORATED.

**Resilience test:**

**Scenario:** User runs `/write-plan`, completes successfully, but `bd set-state` fails (dolt lock conflict).

- Plan artifact written with `**Phase:** planned` header ✓
- Beads label NOT updated (bd command failed)
- Next `/flux-drive` run reads phase from artifact header ✓
- Workflow continues despite beads failure ✓

**Gap:** What if both sources disagree? Example:
- Beads says `phase=brainstorm-reviewed`
- Artifact header says `**Phase:** planned`

**Current design (line 66):** "Fallback" implies beads is primary, artifact is secondary. If beads succeeds, artifact header is ignored even if newer.

**Recommendation:** Clarify precedence in planning phase. Suggested rule: "Beads is authoritative. Artifact header is emergency fallback only. Desync detection warns user but doesn't block."

**Severity:** P2. Desync handling should be defined before implementation, but current fallback behavior is safe (prefers more authoritative source).

---

## Finding 6: Session-Start Scan with TTL Cache (INCORPORATED ✓)

**Original finding (architecture P2):** "Cache session-start scan with 60-second TTL to avoid beads query latency"

**PRD implementation:**
- Lines 43-45 (F4: Session-Start Light Scan):
  - "Uses 60-second TTL cache to avoid repeated beads queries"
  - "Adds no more than 200ms to session startup (cached path)"

**Assessment:** FULLY INCORPORATED.

**Performance validation:**

First session start in 60s window:
- Runs `bd list --status=open --label-pattern "phase:*"` (50-100ms)
- Caches result to `/tmp/clavain-sprint-status-<hash>.txt`
- Total latency: ~200ms including cache write ✓

Subsequent starts within 60s:
- Reads cache file (1-5ms)
- Total latency: negligible ✓

**Missing edge case:** What if user runs `/lfg` and creates a bead, then starts a new session within 60s? Cache is stale.

**Impact:** Session-start will show outdated count ("4 open beads" when there are actually 5). User runs `/lfg` manually and sees correct count.

**Severity:** P3. Cache staleness is acceptable trade-off for startup speed. 60s TTL is short enough.

---

## Finding 7: Merge `tested` Phase into `executing` (INCORPORATED ✓)

**Original finding (architecture P3):** "Merge `tested` into `executing` — distinction between 'code complete' and 'writing code' is fuzzy"

**PRD implementation:**
- Lines 52-53: Phase model lists `executing` with NO `tested` phase:
  ```
  brainstorm → brainstorm-reviewed → strategized → planned →
  plan-reviewed → executing → shipping → done
  ```

**Contrast with brainstorm:**
- Brainstorm had 9 phases including `tested` (line 38 of brainstorm)
- PRD reduced to 8 phases, eliminating `tested`

**Assessment:** FULLY INCORPORATED.

**Validation:** Phase transition in F7 (line 73) confirms this:
- "Quality gates check: (a) phase is valid predecessor..."
- Valid predecessor for `shipping` is `executing` (not `tested`)

**User impact:** Simplified state model. "Code complete" is now represented by `executing` phase + quality-gates passing (orthogonal check).

---

## Scope Creep Analysis

**Original concern (user P3):** "Proposed scope is 8x larger than MVP needed to test hypothesis"

**PRD response:**
- Lines 103-113: Staged rollout plan breaks implementation into 5 stages
- Each stage is independently valuable
- M1 (Work Discovery) can ship first without M2 (Phase Gates)

**Assessment:** Scope is CONTROLLED. The rollout plan validates the architecture review's recommendation for staged delivery.

**MVP validation:**

**M1 deliverables (work discovery only):**
1. Beads scanner with priority-based sorting
2. AskUserQuestion UI with top 3-4 recommendations
3. Orphaned artifact detection
4. Session-start light scan

**Validation signal:** Does work discovery surface the right next action? Measurable via: "How often does user select the [Recommended] option vs manual pick?"

**M2 deliverables (phase gates):**
1. Phase state tracking (Stage 0)
2. Dual persistence (Stage 2)
3. Soft gates (Stage 3)
4. Hard gates with tiered enforcement (Stage 4)

**Validation signal:** After Stage 4, check skip-gate frequency. If <20% of ships use `--skip-gate`, gates are helping. If >50%, gates are annoying.

**Missing scope:** No instrumentation plan for measuring these signals.

**Recommendation:** Add to planning phase: "Instrumentation acceptance criteria — log gate blocks, skips, and discovery selections to validate hypothesis."

**Severity:** P2. Without telemetry, v1 ships blind. Can't measure success.

---

## User Flow Gap Analysis

**Flows covered by PRD:**

1. **Discovery happy path:** User runs `/lfg`, selects [Recommended] option, routes to correct command ✓
2. **Discovery manual triage:** User picks "Show full backlog" option ✓
3. **Discovery fresh brainstorm:** User picks "Start fresh brainstorm" ✓
4. **Gate happy path:** User advances through phases, reviews pass, gates allow ✓
5. **Gate block:** User tries to skip phase, hard gate blocks (P0/P1), soft gate warns (P2/P3) ✓
6. **Gate skip:** User provides `--skip-gate --reason`, override recorded ✓

**Missing flows:**

1. **User wants to work on specific bead ID (not top-ranked):**
   - PRD mentions "selecting an option routes to appropriate command" (line 30)
   - But doesn't specify `/lfg <bead-id>` syntax
   - **Impact:** User can't bypass discovery if they know which bead to work on
   - **Fix (already in PRD):** Line 85 says "/lfg <bead-id> routes to correct command based on phase" — this covers it ✓

2. **User disagrees with ranking algorithm:**
   - PRD shows "Show full backlog" option (line 29)
   - But doesn't specify what format the full backlog presents (plain list? sorted how?)
   - **Impact:** Low. User will see full `bd list` output.
   - **Severity:** P3. Implementation detail.

3. **Orphaned artifact found — user decides to create bead:**
   - F3 (lines 33-37) detects orphaned artifacts
   - Shows "Create bead?" action
   - But doesn't specify: auto-create with confirmation, or route to `/brainstorm`, or link to existing bead?
   - **Severity:** P2. Open Question #1 (line 117) acknowledges this: "Should /lfg auto-create beads? Leaning yes with user confirmation."
   - **Status:** Deferred to planning. Acceptable.

4. **Stale review detected — what happens?**
   - F7 (line 76) mentions "stale review detection: git log check"
   - But doesn't specify: does gate block? warn? ignore?
   - **Severity:** P2. Needs clarification in planning.
   - **Recommendation:** Stale review = soft warning (not block), even for P0/P1. Rationale: user can re-run flux-drive if needed.

---

## Product Hypothesis Validation

**Original concern (user P1):** "No product evidence that gate enforcement solves a real user problem"

**PRD response:**
- Lines 4-5: "Quality reviews are optional and easily skipped — there's no enforcement or even tracking of whether artifacts were reviewed before advancing."
- This is a problem statement, not evidence.

**Evidence gap remains:** PRD does NOT include:
- Current review coverage baseline (what % of plans have flux-drive reviews today?)
- User feedback requesting stricter workflow enforcement
- Incident post-mortems where skipped review caused bugs

**Recommendation from original review:** "Instrument current commands to measure review coverage. If >70% already have reviews, gates solve a non-problem."

**PRD status:** NOT ADDRESSED.

**Is this a blocker?** No. The staged rollout plan (lines 103-113) provides validation mechanism:
- Stage 0-1 ship with NO enforcement (tracking only)
- Stage 2-3 ship with soft gates (warnings, not blocks)
- Stage 4 ships hard gates ONLY if soft gates prove valuable

**This is incremental validation**, which is safer than pre-validating via instrumentation.

**Verdict:** Evidence gap is P3, not P1, because rollout plan mitigates the risk. If gates prove annoying in Stage 3, Stage 4 can be canceled.

---

## Discoverability & Adoption Risks

**Risk 1: New users don't know `/lfg` exists**

**Mitigation (in PRD):**
- Session-start hook shows "2 ready to advance → run /lfg to continue" (line 42-43)
- This is passive discovery (user sees it on session start)

**Missing mitigation:** Active discovery when user runs another command. Example:
```
User runs: /clavain:work
Gate blocks: "Bead Clavain-abc needs plan review. Hint: Run /lfg to see all recommended next actions."
```

**Severity:** P3. Nice-to-have.

**Risk 2: Discovery ranking surfaces wrong work**

**Original concern (user P2):** "Ranking algorithm is untested — score formula uses invented weights"

**PRD implementation:**
- F2 (lines 24-30): AskUserQuestion shows top 3-4 beads
- No scoring formula specified (unlike brainstorm which had lines 90-95 with weights)

**Interpretation:** PRD defers scoring algorithm to planning phase. Current spec is: "top 3-4 beads shown" without defining "top."

**Recommendation:** Planning should start with SIMPLEST ranking: priority-only sort (P0 first, then P1, etc.). Add recency/staleness factors in iteration 2 if users report priority-only is insufficient.

**Severity:** P2. Ranking must be defined before M1 ships, but doesn't need to be sophisticated.

**Risk 3: Session-start nudge becomes noise**

**Original concern (user P2):** "Session-start nudge has no snooze/dismiss mechanism — becomes guilt-inducing noise"

**PRD status:** NOT ADDRESSED.

**Is this a blocker?** No. This is a "nice-to-have" for iteration 2. The 60-second cache (line 44) prevents repeated queries within one work session, which is the performance concern. Snoozing is a UX refinement.

**Verdict:** P3. Add to backlog as "Session-start snooze mechanism."

---

## Open Questions Review

PRD lists 3 open questions (lines 115-119):

1. **"Should /lfg auto-create beads for orphaned artifacts?"** — Leaning yes with confirmation
2. **"Multi-feature PRDs"** — Treat as epic, child beads track phases independently
3. **"Retrospective backfill"** — One-time migration script with user review

**Assessment:**

**Q1: Auto-create beads**
- Safe to defer to planning
- User confirmation via AskUserQuestion prevents accidents
- Verdict: Not a blocker

**Q2: Multi-feature PRDs**
- This aligns with architecture review Section 5 Edge Case 3
- Architecture recommended YAML frontmatter for multi-bead artifacts
- PRD punts on implementation ("each tracks phase independently")
- **Gap:** How does dual persistence work if 3 beads share 1 PRD? Artifact header can only list 1 phase.
- **Severity:** P2. Needs resolution in planning. Two options:
  1. PRD artifact has NO phase header (only individual plans have phases)
  2. PRD artifact has YAML list of bead phases
- **Recommendation:** Option 1 (no PRD phase header). PRD is a requirements doc, not a workflow artifact. Plans are the workflow artifacts.

**Q3: Retrospective backfill**
- Architecture review Section 13 recommended automated inference + manual review
- PRD says "one-time migration script" but doesn't specify inference logic
- **Severity:** P3. Can be a separate task after M1 ships. Existing beads can enter phase-tracking gradually (first-touch inference per line 55).

**Verdict:** All 3 open questions are safe to defer. None block planning.

---

## Findings Summary

### P0 Issues: NONE (all resolved from brainstorm reviews)

All critical findings from fd-user-product and fd-architecture reviews were incorporated:
- Work discovery + phase gates split (architecture P0) ✓
- Entry point implicit (user P1) ✓
- Tiered gates (user P1) ✓
- Shared gate library (architecture P1) ✓
- Dual persistence (architecture P1) ✓

### P1 Issues: NONE

No new P1 issues discovered during PRD review.

### P2 Issues (should address in planning)

**F2.1: Stale review detection behavior undefined**
- Line 76 mentions "git log check for commits after review date"
- But doesn't specify: block, warn, or ignore?
- **Fix:** Clarify in planning. Recommend soft warning (not block).

**F2.2: Discovery ranking algorithm not specified**
- F2 (lines 24-30) says "top 3-4 beads" but doesn't define ranking logic
- **Fix:** Planning should start with priority-only sort, iterate if insufficient.

**F2.3: Multi-bead PRD phase tracking unclear**
- Open Question #2 acknowledges issue but doesn't resolve
- PRD artifact can't have single phase header if 3 beads share it
- **Fix:** Clarify in planning. Recommend PRDs have no phase header (only plans do).

**F2.4: No instrumentation plan for validation**
- Rollout plan depends on measuring skip-gate frequency and discovery selection patterns
- No acceptance criteria for logging these signals
- **Fix:** Add to M1/M2 acceptance criteria: "Log discovery selections and gate skips for post-launch analysis."

### P3 Issues (backlog for iteration 2)

**F3.1: Session-start snooze mechanism missing**
- Original user review requested this
- Not addressed in PRD
- **Fix:** Add to backlog as "beads snooze feature" for iteration 2.

**F3.2: Discovery filter mechanisms missing**
- Original user review requested `--type=bug`, `--tag=upstream` filters
- Not in PRD
- **Fix:** Add to backlog for iteration 2.

**F3.3: Retrospective backfill details unspecified**
- Open Question #3 mentions migration script but no inference logic
- **Fix:** Create separate task after M1 ships.

---

## Recommendations

### Before Planning (address P2 issues)

1. **Define stale review behavior** — Recommend soft warning for all priorities (user can re-run flux-drive if needed).
2. **Specify discovery ranking** — Start with priority-only sort (P0 first), no recency/staleness weighting in v1.
3. **Resolve multi-bead PRD phase tracking** — PRD artifacts have no phase header, only plans/brainstorms have phases.
4. **Add instrumentation acceptance criteria** — M1: log discovery selections (which option chosen), M2: log gate blocks/skips (bead ID, priority, reason).

### Planning Phase

- All 4 P2 issues above must be resolved before writing implementation plan
- Open Questions 1-3 can be deferred (not blockers)
- Discovery ranking should be simple (priority-only) to ship M1 faster

### Post-M1 Validation

- Check discovery telemetry: "Is [Recommended] option selected >70% of the time?"
- If yes, ranking works. If no, add recency/staleness scoring in M1.1

### Post-M2 Validation

- Check gate telemetry: "What % of ships use `--skip-gate`?"
- If <20%, gates are helping. If >50%, gates are too strict (consider relaxing P2/P3 to P4-level).

---

## Decision Lens

**Should this be built?**

**M1 (Work Discovery):** YES. Independent value (faster work triage), low risk (no enforcement), all P0/P1 issues resolved.

**M2 (Phase Gates):** YES, with staged rollout. The 5-stage plan (lines 103-113) validates value incrementally:
- Stage 0-1: Tracking only (no friction)
- Stage 2-3: Soft gates (warnings, not blocks)
- Stage 4: Hard gates ONLY if soft gates prove valuable

**This is a safe validation path.** If gates prove annoying in Stage 3, Stage 4 can be canceled without wasting work (tracking + discovery are still valuable).

**Smallest valuable change:** M1 (work discovery) alone delivers "return to project and know what to work on" — the core user need from line 4.

**Full value unlocked:** M2 Stage 4 (hard gates) completes the vision of "enforce review discipline" — but this is optional value, not core.

---

## Final Verdict

**PRD STATUS:** READY FOR PLANNING

All P0/P1 issues from brainstorm reviews were correctly incorporated. The 4 remaining P2 issues are clarifications, not design flaws. They can be resolved during planning.

**Key strengths:**
- Work discovery + phase gates split (independent milestones)
- Entry point inference (no upfront forcing function)
- Tiered gates (friction matches urgency)
- Staged rollout (validates incrementally, low risk)
- Dual persistence (resilient to beads failures)

**Key gaps (all P2-P3):**
- Discovery ranking algorithm not specified (priority-only is sufficient)
- Stale review behavior not specified (soft warning recommended)
- Multi-bead PRD phase tracking unresolved (no PRD phase header recommended)
- No instrumentation plan (add logging to M1/M2 acceptance criteria)

**Bottom line:** The PRD is a lightweight, well-scoped evolution of the brainstorm. Brainstorm review findings were incorporated correctly. Proceed to planning.
