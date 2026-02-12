# User & Product Review: Phase-Gated /lfg with Work Discovery

**Brainstorm:** `docs/brainstorms/2026-02-12-phase-gated-lfg-brainstorm.md`
**Reviewer:** fd-user-product
**Date:** 2026-02-12

## User Context

**Primary user:** Solo developer or small team using Clavain plugin in Claude Code sessions
**Job to be done:** Return to a project after hours/days and quickly find the most important unfinished work, then execute it with confidence that quality gates won't be skipped

**Current pain (observed from beads + plans):**
- 12+ open beads with unclear state
- Plans exist but no signal about what's ready to work vs blocked
- Linear `/lfg` pipeline forces full brainstorm→ship even for bugs
- No memory of "where did I leave off" between sessions

## User Flow Review

### Discovery UX (Lines 79-111)

**Proposed flow:**
```
/lfg
═══ Work Discovery ═══

Scanned: 8 open beads, 3 orphaned artifacts

Options:
  option1: "Review plan for Clavain-abc (P1, phase:planned → needs review)" [Recommended]
  option2: "Write PRD for Clavain-def (P2, phase:brainstorm-reviewed → needs strategy)"
  option3: "Start fresh brainstorm"
  option4: "Show full backlog"
```

**Strengths:**
- Concrete, actionable options instead of abstract status
- "Recommended" default reduces decision paralysis
- Phase context ("phase:planned → needs review") shows exactly what action is needed
- Scan summary builds confidence that nothing was missed

**Risks:**
- **Ranking algorithm is untested** — score formula (lines 90-95) uses weights that have no user validation. Will P1 bugs actually surface above stale P2 features? Unknown.
- **"Recommended" might not match user intent** — if user opened `/lfg` to work on a specific bead, top-ranked item could be a distraction. No way to filter by keyword/tag.
- **Option text is dense** — "Review plan for Clavain-abc (P1, phase:planned → needs review)" packs 4 concepts (action, bead ID, priority, phase). First-time users won't parse this quickly.
- **No preview of work size** — missing estimates like "~30min to review" or "3 files changed". User can't judge time commitment.

**Missing flows:**
- User wants to work on a specific bead by ID (not top-ranked) — no `/lfg <bead-id>` syntax proposed
- User disagrees with ranking and wants manual triage — "Show full backlog" option exists but unclear what format it presents
- User wants to filter by type (only bugs, only features) — no mechanism

**Recommendation:**
Add option text format variants for scan depth:
- **Compact (default):** "Review Clavain-abc plan (P1)" + [Recommended] badge
- **Verbose (--verbose flag):** Current format with phase transitions
- **By-type groups:** "2 bugs ready, 3 plans need review, 1 new feature to brainstorm"

### Entry Points (Lines 66-77)

**Proposed entry flexibility:**

| Work type | Entry phase | Gate enforcement |
|-----------|-------------|------------------|
| Vague idea | brainstorm | Full pipeline |
| Clear feature | strategized | Skips brainstorm |
| Bug with known fix | planned | Skips brainstorm + strategy |
| Hotfix | executing | Skips all pre-work |

**Validation against real usage (from beads list):**
- **P2 task "Consolidate upstream-check.sh API calls"** — This entered as a planned task (no brainstorm needed). Entry point = `planned` ✓
- **P3 feature "Auto-inject past solutions into /lfg"** — This likely had brainstorm → PRD → plan. Entry point = `brainstorm` ✓
- **P3 task "Standardize hook invocation style"** — Could enter at `planned` (refactoring with clear scope) or `executing` (if just doing it) — **ambiguous**

**Problem: Entry point is a judgment call that users must make upfront.** Brainstorm doesn't explain:
- Who decides the entry point (user or agent)?
- What happens if wrong entry point is chosen (e.g., skip brainstorm but requirements are actually vague)?
- Can entry point be changed after creation?

**Missing flow:** User creates bead via `bd create`, doesn't set entry point, then runs `/lfg`. What's the default? Does `/lfg` prompt to classify the work type before starting?

**Recommendation:**
Make entry point **implicit from first action** rather than explicit upfront decision:
- User runs `/clavain:brainstorm` → auto-sets entry=brainstorm
- User runs `/clavain:write-plan` directly → auto-sets entry=planned
- Don't ask users to predict workflow in advance

### Gate Friction (Lines 52-64)

**Hard gates proposed:**

| Command | Blocks if... | Override |
|---------|--------------|----------|
| /strategy | brainstorm not flux-drive reviewed | --skip-gate |
| /write-plan | No PRD exists | --skip-gate |
| /work | plan not flux-drive reviewed | --skip-gate |
| /quality-gates | plan tasks not checked off | --skip-gate |
| /resolve + ship | quality gates not passed | --skip-gate |

**User impact analysis:**

**Small changes (the common case):**
User wants to fix a typo in docs or add a one-line validation. Under phase gates:
1. Create bead (or it blocks)
2. Run `/write-plan` → BLOCKED: "needs PRD"
3. Add `--skip-gate` → warning printed
4. Write plan → run `/flux-drive` on plan → BLOCKED: "needs review"
5. Add `--skip-gate` again
6. Finally execute

**This adds 4 friction points (2 blocks + 2 skip-gate warnings) to what should be a 30-second change.**

**Medium changes (the design target):**
User implementing a P2 feature from backlog. Gates ensure:
- Plan was reviewed before coding (catches design issues early) ✓
- Quality gates run before shipping (prevents regressions) ✓

This is the happy path. Gates add value.

**Hotfixes (the panic scenario):**
Production is broken, user needs to bypass all gates and ship immediately. Proposed flow:
1. Set entry=executing
2. Code the fix
3. Run `/resolve --skip-gate`
4. Run `/ship --skip-gate`

Still 2 skip-gate warnings + manual flag typing. In panic mode, this is friction.

**Evidence gap:** Brainstorm assumes gate enforcement is desirable, but provides no data on:
- How often users currently skip quality checks (baseline problem severity)
- Whether gate blocks will train better habits or just annoy users into always using --skip-gate
- Comparative friction: hard gates vs soft warnings vs post-hoc audit

**Recommendation:**
Tiered gate strictness by priority:
- **P0/P1:** Hard gates enforced, --skip-gate requires --reason flag
- **P2/P3:** Soft gates (warning but proceed), tracked in bead notes
- **P4:** No gates

This matches urgency to enforcement level.

### Session-Start Integration (Lines 113-123)

**Proposed light scan:**
```
Companions detected:
- beads: 5 open issues, 2 ready to advance
  → Clavain-abc (P1) needs plan review — run /lfg to continue
```

**UX evaluation:**

**Good:**
- 1-2 lines of signal, not a wall of text
- Actionable nudge (run /lfg)
- Shows highest-priority item (P1) not full list

**Risks:**
- **Becomes noise after 2nd session** — if user ignores the nudge, seeing it every session is a reminder of unfinished work (guilt) not a helper
- **No decay/dismissal** — user can't say "I know about this, stop reminding me"
- **Assumes /lfg is always the right action** — what if user is switching contexts to work on a different project?

**Missing state:** "I'm working on something else right now, remind me later"

**Recommendation:**
Add suppression mechanism:
- `bd snooze <id> --until=tomorrow` — hides from session-start scan until date
- Session-start scan shows: "2 ready to advance (3 snoozed)"
- User can un-snooze via `/lfg` backlog view

## Scope Creep Analysis

**MVP (what's actually needed to validate the hypothesis):**

Work discovery is solving: "I have multiple unfinished tasks and don't know which to work on next."

Minimum to test:
1. `bd list` with priority + phase + recency sorting (10 lines of bash)
2. `/lfg` with no args prints top 3 beads + prompts user to pick one (20 lines)
3. `/lfg <bead-id>` routes to appropriate command based on phase (30 lines)

**Total MVP:** ~60 lines of shell, no AskUserQuestion UI, no scoring algorithm, no artifact scanning.

**Proposed scope (from brainstorm):**
- Multi-source scanning (beads API, filesystem, orphaned artifacts) — 100+ lines
- Scoring algorithm with 4 factors (priority, phase, recency, staleness) — 50 lines + tuning
- AskUserQuestion UI with ranked options — 30 lines
- Gate enforcement hooks in 5 commands (strategy, write-plan, work, quality-gates, resolve) — 150 lines
- Entry point tracking (bd set-state entry=X) — 20 lines
- Orphaned artifact detection (scan docs/ for files without bead references) — 80 lines
- Session-start integration (enhance existing hook) — 40 lines

**Total proposed:** ~470 lines, 7 new subsystems.

**Scope creep evidence:**
- Lines 155-165 (Open Questions) introduce 4 more features: auto-create beads for orphans, epic/child phase tracking, time-based review invalidation, retrospective backfill
- Line 87 mentions scanning `bd ready` + `bd list --status=in_progress` + docs filesystem — 3 data sources when 1 (beads API) would suffice
- Scoring algorithm (lines 90-95) has no user research, just invented weights

**What's not needed for MVP:**
- Orphaned artifact scanning (can add later if users report missing work)
- Complex scoring algorithm (alphabetical by priority is sufficient to start)
- Session-start nudges (user can just run /lfg manually)
- AskUserQuestion UI (plain text output works)

**Recommendation:**
Ship phase gates FIRST (validates the "quality checks are being skipped" hypothesis), then add work discovery as a separate iteration once gate adoption is measured.

## Entry Point Gap Analysis

**Proposed entry points cover:**
- Vague idea → brainstorm
- Clear feature → strategized
- Bug with fix → planned
- Hotfix → executing

**Missing scenarios (from real beads):**

**Scenario 1: Refactoring/cleanup tasks (P3 "Standardize hook invocation")**
- No external requirement
- No user-facing behavior change
- Just "make code cleaner"
- **Which phase?** Could be planned (if scope is clear) or strategized (if exploring approaches). Brainstorm feels too heavyweight.

**Scenario 2: Research/investigation tasks (P3 "Define .clavain/ filesystem contract")**
- Deliverable is a design doc, not code
- Might need brainstorm-like exploration
- But "feature" and "bug" don't fit
- **Which phase?** Unclear. Is research a separate track?

**Scenario 3: Deferred work from larger PRD (P3 "Fast-follow deferred flux-drive features")**
- PRD already exists
- Features are defined
- Just needs planning
- **Entry point = strategized?** But the feature list is already in the PRD, so maybe planned?

**Pattern:** Phase model assumes **code delivery**, but Clavain work includes docs, research, tooling, and cleanup. These don't map cleanly to brainstorm→PRD→plan→code.

**Recommendation:**
Add work type dimension to phase model:
- **Feature work:** brainstorm → PRD → plan → code → ship
- **Bug fixes:** triage → plan → fix → verify → ship (skip brainstorm/PRD)
- **Cleanup/refactor:** assess → plan → execute → verify (skip brainstorm/PRD)
- **Research:** explore → document → review (no code phase)

Each type has its own phase sequence. Gates enforce the appropriate sequence for that type.

## Gate Override Sufficiency

**Proposed override:** `--skip-gate` flag prints warning, proceeds, records skip in bead notes (line 64)

**Evaluation:**

**When override is appropriate:**
- Hotfix (ship now, backfill gates later)
- Experimental spike (throw-away code, no review needed)
- Trivial change (one-line fix, gates are overkill)

**When override is misuse:**
- User doesn't understand requirement (tries to plan before brainstorm, gets blocked, skips gate without reading why)
- User is lazy (skips review to save 5 minutes, introduces bug)
- User is under time pressure (sprinting to deadline, skips quality gates)

**Problem: Single --skip-gate flag can't distinguish legitimate vs misuse cases.**

**Missing accountability:**
- No `--reason` required (just `--skip-gate` and go)
- Bead notes record the skip, but who reviews these notes?
- No visibility into skip frequency (are 80% of ships using --skip-gate?)

**Recommendation:**
Tiered override system:
- **P0/P1 work:** `--skip-gate` requires `--reason "..."` (recorded in bead), prompts "Are you sure? [y/N]"
- **P2/P3 work:** `--skip-gate` allowed, warning printed, recorded in bead
- **P4 work:** Gates are soft warnings by default, no skip needed

Add audit command: `bd audit skipped-gates` to surface beads with multiple skips (potential quality risk).

## Product Validation Gaps

**Hypothesis (implicit):** Users skip quality checks because there's no enforcement, and this causes bugs/rework.

**Evidence provided:** None. Brainstorm assumes the problem exists but doesn't cite:
- Incident post-mortems where skipped review caused bugs
- User feedback requesting stricter workflow enforcement
- Data on current review coverage (what % of PRDs/plans are flux-drive reviewed today?)

**Alternative explanations for skipped reviews:**
- Reviews are too slow (flux-drive takes 10-20 minutes, user wants to keep momentum)
- Reviews find low-signal issues (nitpicks that don't justify the time cost)
- Users don't understand review value (education problem, not enforcement problem)

**Missing validation:**
- Survey existing Clavain users: "How often do you run flux-drive before coding?" (never/sometimes/always)
- Measure current state: grep all plans for flux-drive review references (baseline coverage %)
- Ask: "Would you use /lfg more if it enforced gates, or would you switch to manual commands to avoid friction?"

**Recommendation:**
Before building gates, instrument current behavior:
1. Add telemetry to commands (if user runs /work, check if plan has flux-drive review, log true/false)
2. Collect 2 weeks of data
3. If <50% of work has prior review, gates solve a real problem
4. If >80% already have review, gates add friction without value

## Findings Summary

### Severity: P1 (blocks user success)

**F1.1: Entry point classification is a premature forcing function**
User must decide "is this a bug or a feature" before understanding the problem. Wrong choice leads to gate friction. **Fix:** Infer entry point from first action (implicit), not upfront declaration (explicit).

**F1.2: Small changes suffer 4x friction for zero value**
Typo fix or one-line validation hits the same gate gauntlet as major features. **Fix:** Tiered gates by priority (P0/P1 hard, P2/P3 soft, P4 none).

**F1.3: No product evidence that gate enforcement solves a real user problem**
Brainstorm assumes users skip quality checks, but provides no data. **Fix:** Measure current review coverage before building enforcement.

### Severity: P2 (usability issues)

**F2.1: Ranking algorithm is untested and might surface wrong work**
Score formula uses invented weights with no user validation. **Fix:** Start with priority-only sort (simple), add scoring after observing user behavior.

**F2.2: Discovery option text is dense and unparseable for new users**
"Review plan for Clavain-abc (P1, phase:planned → needs review)" packs too much. **Fix:** Compact default format, --verbose for full context.

**F2.3: No way to filter discovery results by work type or keyword**
If user wants "just bugs" or "just beads about upstream sync", no mechanism. **Fix:** Add `--type=bug`, `--tag=upstream` filters to `/lfg`.

**F2.4: Session-start nudge has no snooze/dismiss mechanism**
Becomes guilt-inducing noise after user ignores it twice. **Fix:** Add `bd snooze <id>` to suppress reminders.

**F2.5: --skip-gate override has no accountability for P0/P1 work**
No --reason required, no confirmation prompt, no audit trail. **Fix:** Require reason + confirmation for high-priority skips.

### Severity: P3 (scope/design issues)

**F3.1: Proposed scope is 8x larger than MVP needed to test hypothesis**
470 lines across 7 subsystems vs 60-line MVP. **Fix:** Ship gates first, add discovery in iteration 2.

**F3.2: Phase model assumes code delivery, doesn't fit research/cleanup work**
"Standardize hook style" and "Define filesystem contract" don't map to brainstorm→PRD→plan. **Fix:** Add work types with type-specific phase sequences.

**F3.3: Orphaned artifact scanning is a solution looking for a problem**
No evidence users lose track of brainstorm docs. **Fix:** Cut from MVP, add if user reports surface the need.

**F3.4: Multi-feature PRD phase tracking is unresolved (Open Question #2)**
If PRD has F1, F2, F3 as separate beads, which bead owns the PRD artifact? **Fix:** Treat PRD as epic-level doc, child beads reference it but don't own it.

## Recommendations

### Immediate (before any implementation)

1. **Validate the hypothesis** — Instrument current commands to measure review coverage. If >70% of work already has reviews, gates are a solution to a non-problem.

2. **User test the discovery UX** — Mock up the AskUserQuestion output, show to 3 users, ask "which option would you pick and why?" Verify ranking makes sense.

3. **Define work types** — Map beads in current backlog to types (feature/bug/cleanup/research) and verify each type has a sensible phase sequence.

### MVP Scope (ship first to test core value)

1. **Phase gates only** — 5 commands check predecessor phase before proceeding, --skip-gate override with warning
2. **Manual work selection** — User runs `/lfg <bead-id>`, router picks command based on phase
3. **Priority-based sort** — `bd list --status=open --sort=priority` is the "discovery" (no scoring, no UI)

**Validation signal:** After 2 weeks, check `bd audit skipped-gates`. If <20% of ships used --skip-gate, gates are helping. If >50%, gates are annoying.

### Iteration 2 (only if MVP validates)

1. **Work discovery UI** — AskUserQuestion with top 3 beads, [Recommended] badge
2. **Scoring algorithm** — Add recency/staleness factors, tune weights based on user feedback
3. **Session-start nudge** — 1-line "2 ready to advance" summary

### Iteration 3 (nice-to-haves)

1. **Filter/search** — `--type=bug`, `--tag=upstream`
2. **Snooze mechanism** — `bd snooze <id> --until=date`
3. **Audit tooling** — `bd audit skipped-gates`, `bd audit stale-beads`

## Decision Lens: Should This Be Built?

**Build the MVP (phase gates only):** Yes, if user research confirms review coverage is currently low (<50%).

**Build the full scope (discovery + gates + scoring):** No. This is 8x the work for unvalidated value. The work discovery problem can be solved with better `bd list` formatting, not a custom UI.

**Build session-start integration:** No. This adds noise before value is proven. Let users opt into `/lfg` manually until they report wanting auto-suggestions.

**Smallest valuable change:** Add phase tracking (`bd set-state <id> phase=X`) and teach existing commands to read it. No gates, no enforcement, just visibility. Observe whether users naturally adopt phase discipline before adding enforcement.
