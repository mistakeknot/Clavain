# Sprint Awareness Scanner: Artifact Conventions & Scan Targets

**Date:** 2026-02-11  
**Purpose:** Map the Clavain artifact ecosystem to design a scanner that detects orphaned brainstorms, stale plans, unexecuted work, and skipped phases.

---

## 1. Brainstorm Artifacts

### Naming Convention
**Pattern:** `docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md`

**Example:** `/root/projects/Clavain/docs/brainstorms/2026-02-08-flux-drive-improvements-brainstorm.md`

### Current State
Only **1 brainstorm** exists in the codebase (as of 2026-02-11). This is a signal that brainstorms may not be captured consistently, or they are deleted after execution.

### Metadata Structure
Brainstorms contain:
- **Date:** ISO format in filename and document header
- **Status:** Explicit field showing `Implemented (commit <hash>)` or `Active` or `Planned`
- **Review feedback:** Often includes findings from flux-drive reviews with issue counts and agent consensus
- **Checkboxes:** Use `- [ ]` for action items (not completion of work, but follow-up issues)
- **Implementation reference:** Links to commit hashes (`Implemented (commit 3d02843)`)

**Example metadata from brainstorm:**
```markdown
# Flux-Drive Improvements Brainstorm

**Date:** 2026-02-08
**Status:** Implemented (commit 3d02843) — post-implementation review below

Reviewed by 4 agents (3 codebase-aware, 1 generic) on 2026-02-08.

### Issues to Address
- [ ] Remove Model column from Tier 3 table (P0, 3/4 agents)
- [ ] Fix Step 3.0.5 ordering (P0, 2/4 agents)
- [x] Issue marked as completed
```

### Linking Pattern
- **To PRDs:** Brainstorms reference downstream PRDs or are directly passed to `/strategy`
- **To beads:** Implicit — `/strategy` creates beads from brainstorm output
- **Cross-referencing:** Minimal — brainstorms reference git commits for implementation status

### Red Flags for Scanner
1. **Brainstorm with no downstream plan/PRD** — orphaned exploration
2. **Status: Active/Planned but no plan exists** — stalled work
3. **Reviewed by agents (e.g., flux-drive) but unchecked items remain** — findings not addressed
4. **Commit reference doesn't exist** — implementation claim is false

---

## 2. Plan Artifacts

### Naming Convention

**Two formats coexist:**

#### Format A: Dated Plans (Topic-Based)
- Pattern: `docs/plans/YYYY-MM-DD-<topic>.md`
- Examples: `2026-02-10-test-suite-design.md`, `2026-02-09-flux-drive-fixes.md`, `2026-02-11-upstream-integration.md`
- **Use:** Complex features or epic-level work needing structured execution

#### Format B: Bead ID Plans (Tracked in Beads)
- Pattern: `docs/plans/Clavain-<bead-id>-<description>.md`
- Examples: `Clavain-zkds-context-budget-audit.md`, `Clavain-c9gv-document-review.md`, `Clavain-fg41-swarm-patterns.md`
- **Use:** Individual tracked work items linked to beads database

#### Format C: Generic Bead Plans (Legacy)
- Pattern: `docs/plans/plan-clavain-<short-id>.md`
- Examples: `plan-clavain-690.md`, `plan-clavain-4z1.md`, `plan-clavain-1va.md`
- **Use:** Older naming convention, still active

### Current State
**23 total plans** across all three formats. Mix of completed and in-progress work.

### Metadata Structure

Plans contain:
- **Goal:** Single-sentence description of what's being accomplished
- **Context:** Background, current state, why this work matters
- **Steps/Tasks:** Numbered execution phases with specific file changes
- **Implementation checkboxes:** `- [ ]` for acceptance criteria, `- [x]` for completed items
- **Beads reference:** Link to tracking system (e.g., "Clavain-zkds (P1)", "Clavain-dbh7 (P2, DONE)")
- **Commit instructions:** Specific commit message templates included

**Example metadata from plan:**
```markdown
# Plan: Audit and apply disable-model-invocation (Clavain-zkds)

## Goal
Reduce plugin context budget usage by marking manual-invocation-only commands and skills...

## Steps

### Step 1: Add flag to 13 commands
Add `disable-model-invocation: true` to frontmatter...

### Step 4: Commit
Commit message: `perf: add disable-model-invocation to 21 manual commands/skills`

## Verification
- `grep -rl 'disable-model-invocation' commands/ | wc -l` → should be 21
```

### Completion Tracking

Plans use **two mechanisms**:

1. **Task-level checkboxes:** `- [ ]` / `- [x]` marking acceptance criteria
   - Example: `- [ ] Language-specific reviewers are skipped when their language isn't in the document`
   - Example: `- [x] launch-codex.md TIER field uses numeric — fixed (2/3 agents)`

2. **Bead status markers:** Plans reference beads like `Clavain-zkds (P1)`, `Clavain-dbh7 (P2, DONE)`
   - DONE marker indicates work is complete in beads system
   - P0/P1/P2/P3 priority levels

3. **Brainstorm status links:** Plans may link back to brainstorms for context verification

### Plan-to-Brainstorm Cross-References

- **Brainstorm → Plan:** Brainstorms output is passed to `/strategy` → `/write-plan`, creating plans
- **Plan → Brainstorm:** Plans often include "Brainstormed YYYY-MM-DD" line referencing source
- **Example:** `Clavain Test Suite — Implementation Plan` includes: `> Brainstormed 2026-02-10...`

### Red Flags for Scanner

1. **Plan with no referenced brainstorm** — may be orphaned spike work
2. **Acceptance criteria all unchecked** — plan not started
3. **Bead reference marked DONE but plan has unchecked items** — desync between beads and docs
4. **No commit instructions** — plan may not have been executed
5. **Plan older than 14 days with active checkboxes** — stale/abandoned
6. **Plan references brainstorm that doesn't exist** — orphaned genealogy

---

## 3. PRD Artifacts

### Current State
**NO `docs/prds/` directory exists.** PRDs are NOT created in the current Clavain workflow.

### Expected Structure (Per `/strategy` command)
The `strategy.md` command defines the PRD format but doesn't create them:

```markdown
# PRD: <Title>

## Problem
[1-2 sentences: what pain point this solves]

## Solution
[1-2 sentences: what we're building]

## Features

### F1: <Feature Name>
**What:** [One sentence]
**Acceptance criteria:**
- [ ] [Concrete, testable criterion]

### F2: <Feature Name>
...

## Non-goals
[What we're explicitly NOT doing this iteration]

## Dependencies
[External systems, libraries, or prior work needed]

## Open Questions
[Anything unresolved that could affect implementation]
```

### Implication for Scanner
- **No PRDs currently written** means `/strategy` command is not in active use, OR it's writing directly to beads without markdown artifacts
- Plans skip the PRD entirely and go brainstorm → plan → execution
- The LFG pipeline (Step 2: Strategize) *should* produce a PRD but isn't being captured as an artifact
- **Scanner target:** Track whether plans skip strategy phase or whether strategy outputs aren't persisted

---

## 4. HANDOFF.md Format

### Current State
**NO HANDOFF.md files exist** in the Clavain codebase.

### Implication
Handoffs between sessions are not documented in markdown. Work continuity depends on:
- Git commit messages
- Beads tracking system
- Plan checkboxes in `docs/plans/`
- Memory files (`.claude/projects/.../memory/`)

### Scanner Opportunity
Detect plans that are marked in-progress but have no git activity in the past N days — potential sign of stalled work needing handoff.

---

## 5. Git Log Patterns: Commit Messages & Bead ID Convention

### Commit Message Format

**Observed convention:**
- `<type>(<scope>): <subject>` (e.g., `fix(flux-drive): move output format to top of prompt`)
- Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `chore`, `research`, `ci`, `sync`
- Scopes: skill/command names or high-level areas (e.g., `flux-drive`, `hooks`, `tests`)
- Often include bead closure: `Closes Clavain-<id>`

### Bead ID Pattern

**Pattern:** `Clavain-<4-char-alphanumeric>`

**Examples from codebase:**
- `Clavain-zkds` (context-budget-audit)
- `Clavain-dbh7` (async-sessionstart)
- `Clavain-w219` (triage-prs)
- `Clavain-c9gv` (document-review)
- `Clavain-gvu` (validation-comparison)
- `Clavain-nta` (parallel-dispatch)
- `Clavain-8xs` (atomic-rename)

**Frequency:** ~1 bead ID per commit in recent history (highly consistent).

### Git Log Scanning

**Searching for bead IDs:**
```bash
git log --all --oneline | grep 'Clavain-'
```

**Result:** Only 1 bead reference found in git history directly (`Clavain-gvu`), but plans reference many bead IDs.

**Implication:** Bead IDs are assigned and tracked in `/root/projects/Clavain/.beads` (Dolt database), not primarily in git. Plans link to beads but commit messages don't reference them consistently.

### Red Flags for Scanner

1. **Plan references bead Clavain-<id> but git search finds no related commits** — stalled, never attempted
2. **Commits referencing Clavain-<id> exist but plan has no checkboxes marked** — executed but not documented
3. **Plan's brainstorm commit hash doesn't exist** — orphaned reference
4. **Commits to related files but no plan document** — ad-hoc work, not tracked

---

## 6. The /lfg Pipeline: 9 Stages & Artifacts

### Pipeline Overview

The `/lfg` (Let's Freaking Go) command runs a structured 9-step engineering workflow. **Each step produces specific artifacts:**

| Step | Command | Artifact Produced | Scanner Target |
|------|---------|-------------------|-----------------|
| 1 | `/brainstorm $ARGS` | `docs/brainstorms/YYYY-MM-DD-*.md` | Orphaned brainstorm (no downstream) |
| 2 | `/strategy` | (Should create: `docs/prds/YYYY-MM-DD-*.md` + beads epic) | Missing PRD artifact |
| 3 | `/write-plan` | `docs/plans/YYYY-MM-DD-*.md` | Plan not written, or skipped |
| 4 | `/flux-drive <plan-file>` | `docs/research/flux-drive/<date>/*.md` | Plan not reviewed (files missing) |
| 5 | `/work <plan-file>` | Code/artifact changes + `docs/research/<topic>/*.md` | Execution skipped or blocked |
| 6 | Test suite | CI logs (not artifact) | Test failures = blocking issue |
| 7 | `/quality-gates` | `docs/research/quality-gates/*.md` | Quality review skipped or incomplete |
| 8 | `/resolve` | Code commits + issue fixes | Findings not addressed |
| 9 | `/clavain:landing-a-change` | Git commit with verified work | Change not shipped |

### Pipeline Behavior Notes

**Clodex mode:** When clodex is active, Step 5 (`/work`) auto-dispatches to Codex agents. Step 5 writes its own execution logs and auto-compounds on completion.

**Plan review gates:** Step 4 blocks progression if P0/P1 issues found. Progression requires explicit fix + re-review.

**Parallel opportunities:** Steps 5-7 can overlap (quality-gates while resolve starts).

### Artifact Chain

```
Brainstorm (Step 1)
    ↓
(Step 2: Strategy — currently skipped in practice, no PRD artifact)
    ↓
Plan (Step 3)
    ↓
Flux-drive Review (Step 4) → docs/research/flux-drive/
    ↓
Work Execution (Step 5) → code changes
    ↓
Tests (Step 6) → CI output
    ↓
Quality Gates (Step 7) → docs/research/quality-gates/
    ↓
Resolve Issues (Step 8) → git commits
    ↓
Ship (Step 9) → final commit + documentation
```

### Red Flags for Scanner

1. **Brainstorm exists but no plan** — Step 3 skipped (orphaned exploration)
2. **Plan exists but no flux-drive review** — Step 4 skipped (no quality gate)
3. **Plan exists with P0/P1 findings noted but no fixes committed** — blocked at Step 4, work stalled
4. **Research directory has flux-drive reports but no subsequent work/** changes** — execution (Step 5) skipped
5. **Multiple plans for same brainstorm** — retries or duplicate work
6. **Plan is 30+ days old, git has no related commits** — truly orphaned

---

## 7. Directory Structure

```
/root/projects/Clavain/docs/
├── brainstorms/                          # 1 file (2026-02-08-flux-drive-improvements-brainstorm.md)
├── plans/                                # 23 files (mixed formats: dated, bead-id, plan-clavain)
├── prds/                                 # DOES NOT EXIST
├── research/                             # Research reports from reviews + experiments
│   ├── flux-drive/                       # Multi-agent review reports
│   │   ├── 2026-02-09-flux-drive-fixes/  # Date-stamped report directory
│   │   │   ├── fd-code-quality.md
│   │   │   ├── fd-architecture.md
│   │   │   └── code-simplicity-reviewer.md
│   │   ├── Clavain-v2/                   # Agent-named reports
│   │   ├── strongdm-techniques/          # Topic-organized reports
│   │   └── ...
│   ├── plan-*.md                         # Research findings from planning stages
│   └── ...
├── solutions/                            # Documented solutions to integration issues
├── templates/                            # Artifact templates
├── runbooks/                             # Operational procedures
└── upstream-decisions/                   # Design rationale for upstream integration
```

---

## 8. Completion Tracking Mechanisms

### Mechanism 1: Plan Checkboxes

Plans use `- [ ]` / `- [x]` for:
- **Acceptance criteria:** Observable, testable conditions
- **Task steps:** Individual implementation actions
- **Verification points:** Post-implementation checks

**Example:**
```markdown
## Acceptance Criteria
- [ ] Language-specific reviewers are skipped when their language isn't in the document
- [x] Domain-general agents always appear in the scoring table
- [ ] Pre-filter uses document profile fields, not raw content scanning
```

**Scanner opportunity:** Count unchecked items per plan to assess completion percentage.

### Mechanism 2: Bead Status in Plans

Plans list beads like:
```
**Beads:** Clavain-zkds (P1), Clavain-dbh7 (P2, DONE), Clavain-w219 (P2), Clavain-c9gv (P3)
```

**DONE marker** = work completed in beads system (not necessarily documented in plan checkboxes).

### Mechanism 3: Brainstorm Status Field

```markdown
**Status:** Implemented (commit 3d02843)
```

This is explicit text, not structured YAML.

### Mechanism 4: Git Commit References

Plans may include notes like:
```markdown
## Implementation Status
- Step 1 completed in commit abc1234
- Step 2 pending (waiting for upstream merge)
```

---

## 9. Scanner Design Targets

### Orphaned Brainstorms
**Detection:**
- Brainstorm file exists + date is 7+ days old
- No corresponding plan file exists
- No bead references in plan-stage tracker (`.beads/`)

**Query:**
```bash
find docs/brainstorms -name "*.md" -mtime +7 | while read f; do
  topic=$(basename "$f" | sed 's/-brainstorm.md//')
  [ $(find docs/plans -name "*$topic*" | wc -l) -eq 0 ] && echo "Orphaned: $f"
done
```

### Stale Plans
**Detection:**
- Plan file exists + date is 14+ days old
- Checkboxes remain unchecked (0% completion)
- No git commits touching related files in past 14 days
- Bead status is NOT "DONE"

### Unexecuted Work
**Detection:**
- Plan exists with Step 3 (Write Plan) completed
- No `docs/research/` subdirectory matching plan topic
- Or, flux-drive reports exist but no subsequent work/ commits

### Skipped Phases
**Detection:**
- Plan exists but no flux-drive review reports (Step 4 skipped)
- Plan exists but no work/ changes (Step 5 skipped)
- Brainstorm → Plan exists but no Strategy step evidence (PRD artifact or beads)

### Blocked Work (P0/P1 Issues)
**Detection:**
- Flux-drive report exists with `verdict: needs-changes`
- Issues marked P0/P1 are documented
- No follow-up plan or fix commits

---

## 10. Summary: Mapping for Sprint Awareness Scanner

| Artifact Type | Location | Naming | Links To | Completion Signal | Scanner Targets |
|---|---|---|---|---|---|
| Brainstorm | `docs/brainstorms/YYYY-MM-DD-*-brainstorm.md` | ISO date + topic | Plan (implicit) | Status field or commit ref | Orphaned (no plan), reviewed but unfixed |
| Plan (dated) | `docs/plans/YYYY-MM-DD-*.md` | ISO date + topic | Brainstorm, beads | Checkboxes (0%-100%) + git commits | Stale (7+ days, 0% done), unexecuted |
| Plan (bead-linked) | `docs/plans/Clavain-<id>-*.md` | Bead ID + description | Brainstorm, beads | Bead status (DONE) + checkboxes | Blocked (P0/P1 unfixed), orphaned (no bead) |
| PRD | `docs/prds/YYYY-MM-DD-*.md` | ISO date + topic | Brainstorm, Plan | Not currently used | Missing (never created) |
| Flux-drive Review | `docs/research/flux-drive/<topic>/*.md` | Topic + agent name | Plan | Multiple agent reports merged | Plan not reviewed (files missing) |
| Execution Work | Code changes + `docs/research/` | Git commits | Plan, review findings | Commits in git log | Execution skipped, findings ignored |
| HANDOFF.md | Not used | N/A | Plans | N/A | Not tracking session handoffs |

---

## 11. Key Findings

1. **PRDs are not being created.** The `/strategy` command (Step 2 of `/lfg`) exists but PRD artifacts are never written. Plans go directly from brainstorm to implementation planning, skipping the structured PRD stage.

2. **Brainstorms are rare.** Only 1 brainstorm document exists in the repo. Most work appears to originate from beads or ad-hoc planning, not structured brainstorms. This may indicate that brainstorming is happening verbally/interactively and not captured.

3. **Plans use three naming conventions simultaneously:**
   - Dated (YYYY-MM-DD topic): high-level, complex epics
   - Bead-linked (Clavain-<id>): tracked work items
   - Generic (plan-clavain-<id>): legacy format
   
   **Implication:** Scanner must support all three patterns.

4. **Checkboxes are the primary completion tracker.** Plans use `- [ ]` / `- [x]` for acceptance criteria and steps. This is structured and scannable. Beads system is secondary (referenced but not inspected).

5. **Git commits are inconsistent with beads.** Most commits don't reference bead IDs; only 1 found in 50-commit history. Beads must be tracked separately via `.beads/` database.

6. **Flux-drive reviews are extensive.** Every plan gets reviewed with 3-6 agents, and reports are stored as markdown in `docs/research/flux-drive/<date>/`. These reports contain critical blockers (P0/P1) that gate progression.

7. **Parallel execution is assumed.** Steps 5-8 (execute, test, quality-gates, resolve) overlap. Blocks at Step 4 (flux-drive review) are hard stops; blocks after (P1 findings) are soft stops.

8. **HANDOFF.md is not used.** Work continuity relies on beads status + plan checkboxes + git history, not explicit handoff documents.

---

## 12. Scanner Implementation Roadmap

### Phase 1: Brainstorm Inventory
- [x] Scan `docs/brainstorms/` for orphaned artifacts (no downstream plan)
- [x] Check Status field for implementation confirmation
- [x] Verify referenced commit hashes exist
- [x] Identify orphaned issues (checkboxes unchecked, status not "Implemented")

### Phase 2: Plan Inventory & Completion
- [x] Scan `docs/plans/` for all three naming patterns
- [x] Parse plan checkboxes → completion percentage
- [x] Match plans to beads (Clavain-<id> references)
- [x] Detect stale plans (7+ days old, 0% done)
- [x] Identify plans with no git commits in 14 days

### Phase 3: Flux-Drive Review Status
- [x] Scan `docs/research/flux-drive/` for review reports matching plans
- [x] Extract verdict (safe / needs-changes / risky) per agent
- [x] Identify P0/P1 findings that block progression
- [x] Detect plans reviewed but findings not addressed

### Phase 4: Execution & Ship Status
- [x] Match plans to git commits (file changes, resolve commands)
- [x] Identify execution-skipped plans (no work/ commits after review)
- [x] Detect missing tests (Step 6)
- [x] Identify unshipped work (no final landing commit)

### Phase 5: Pipeline Phase Tracking
- [x] Trace artifact chain: Brainstorm → Plan → Review → Execution → Ship
- [x] Detect skipped phases (missing artifacts in sequence)
- [x] Identify blocked work (P0/P1 issues, not fixed)

---

## 13. Example Scan Output

```
ORPHANED BRAINSTORMS
(No downstream plan or bead created)
- None currently

STALE PLANS
(>7 days old, 0% completion, no recent commits)
- docs/plans/plan-clavain-1va.md (9 days old, 0/4 items done)
- docs/plans/plan-clavain-2yx.md (8 days old, 0/2 items done)

EXECUTION BLOCKED
(Plan reviewed with P0/P1 findings, fixes not committed)
- docs/plans/2026-02-09-flux-drive-fixes.md
  Findings: 8/8 items marked [x] (COMPLETED)
  Verdict: Needs fixes applied (but git shows fixes committed ✓)

UNEXECUTED PLANS
(Plan exists, but no work/ commits, no flux-drive review)
- docs/plans/plan-clavain-s3j.md (created 6 days ago, no git activity)

SKIPPED PIPELINE PHASES
- 2026-02-08-flux-drive-improvements-brainstorm.md → 2026-02-10-test-suite-design.md
  Missing: PRD artifact (Step 2 of /lfg never ran)

COMPLETION STATUS
- Total plans: 23
- Completed (100% checkboxes + committed): 8
- In-progress (50-99%): 5
- Blocked (P0/P1, >3 days): 2
- Stale (0%, >7 days): 4
- Unknown (no checkboxes): 4
```
