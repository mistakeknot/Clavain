# Research: LFG and Phase-Gate Workflow Patterns in Clavain

**Date:** 2026-02-12
**Scope:** Document the current /lfg workflow, existing phase-gating mechanisms, work discovery systems, and quality gate patterns in the Clavain plugin.

---

## Executive Summary

Clavain implements a **9-step full pipeline workflow** called `/lfg` (Let's Fucking Go) that orchestrates the complete engineering lifecycle from idea to shipped code. The workflow includes **implicit phase gates** at several critical transitions (plan→execute, execute→review, review→ship) but lacks **explicit state tracking** between phases and **automated phase discovery** for already-in-progress work.

Key findings:
- **9 sequential phases** with quality checks but no persistent state management
- **Quality gates exist** at plan review (Step 4: flux-drive) and pre-ship (Step 7: quality-gates)
- **Work discovery is lightweight** — relies on filesystem artifacts (brainstorms, plans) and git history
- **Beads integration** provides cross-session task tracking but is **optional** (not mandatory in the pipeline)
- **No explicit "phase state" model** — status inferred from artifact presence and git commits
- **Missing:** automated phase detection for resuming partial work, gate failure recovery patterns, and phase-to-phase handoff state

---

## Part 1: The /lfg Workflow (9 Steps)

**File:** `/root/projects/Clavain/commands/lfg.md`
**Alias:** `/clavain:full-pipeline` (identical)

### Step 1: Brainstorm
**Command:** `/clavain:brainstorm $ARGUMENTS`
**Artifact:** `docs/brainstorms/YYYY-MM-DD-<topic>-brainstorm.md`
**Produces:** Freeform dialogue-driven design exploration via the `brainstorming` skill
- One question at a time, multiple-choice preferred
- 200-300 word design sections, incremental validation
- Captures alternatives, constraints, success criteria

### Step 2: Strategize
**Command:** `/clavain:strategy`
**Input:** Brainstorm doc or feature description
**Artifacts:**
- `docs/prds/YYYY-MM-DD-<topic>.md` (structured PRD with features, acceptance criteria)
- Beads epic + feature issues (if `.beads/` exists)

**Produces:**
- Phase 1: Extract discrete, independently-deliverable features
- Phase 2: Write PRD with Problem/Solution/Features/Non-goals/Dependencies/Open Questions
- Phase 3: Create beads epic + child feature issues with dependencies
- Phase 4: Lightweight flux-drive validation on PRD (catches scope creep, missing AC, architectural risks)
- Phase 5: Offer next steps (plan first feature, plan all, refine PRD, or done)

### Step 3: Write Plan
**Command:** `/clavain:write-plan`
**Input:** PRD or spec
**Artifact:** `docs/plans/YYYY-MM-DD-<feature-name>.md`
**Produces:**
- Bite-sized tasks (2-5 minutes each: write test → run test → implement → commit)
- Exact file paths, complete code snippets, test commands with expected output
- Sub-skill link: clavain:executing-plans (required for implementation)

**Execution Option Selection:**
When clodex mode is active, `/write-plan` auto-selects "Codex Delegation" → Codex agents execute the plan in parallel sandboxes. **In this case, skip Step 5 (execute) — the plan has already been executed by Codex.**

### Step 4: Review Plan (Quality Gate — Execution Blocker)
**Command:** `/clavain:flux-drive <plan-file-from-step-3>`
**Gate Condition:** If flux-drive finds P0/P1 issues, **stop and address before proceeding to execution**
**Agents Launched:** Based on document type (plan receives fd-architecture, fd-quality, possibly others)

**Key Insight:** Review happens **before execution** so plan-level risks (architecture, scope, missing acceptance criteria) are caught early.

### Step 5: Execute
**Command:** `/clavain:work <plan-file-from-step-3>`
**Execution Mode:**
- Serial: Single Claude subagent follows plan tasks sequentially
- Parallel (automatic when clodex mode active): Codex agents execute independent modules in parallel
- Manual override: Can manually dispatch parallel-agents skill

**Notes:**
- Assumes Step 4 (flux-drive) passed with no P0/P1 issues
- Work loop: read plan → match patterns → implement → test → commit → mark task complete
- Incremental commits after each logical unit (not `git add .`)

### Step 6: Test & Verify
**Command:** Manual — run project's test suite
**Gate Condition:** Tests must pass before moving to quality-gates
- `go test ./...`, `npm test`, `pytest`, `cargo test` — varies by project
- If test suite doesn't exist, note this but proceed
- If tests fail, **stop** — fix failures before proceeding

### Step 7: Quality Gates (Review & Validation Phase)
**Command:** `/clavain:quality-gates`
**Parallel Opportunity:** Can overlap with Step 8 (resolve) — quality-gates spawns review agents while resolve addresses known TODOs

**What it does:**
- Auto-selects reviewer agents based on what changed (fd-architecture, fd-quality, fd-safety, fd-correctness, fd-performance, fd-user-product)
- Analyzes changed files for risk domains
- Runs up to 5 agents in parallel based on file classifications
- Produces findings by severity (P1 critical, P2 important, P3 nice-to-have)

**Agents invoked (risk-based):**
- Always: fd-architecture, fd-quality
- Auth/crypto/secrets → fd-safety
- Database/schema/backfill → fd-correctness + data-migration-expert
- Perf-critical paths → fd-performance
- Concurrent/async code → fd-correctness
- User-facing flows → fd-user-product

### Step 8: Resolve Issues
**Command:** `/clavain:resolve`
**Auto-Detection:** Finds source (todo files, PR comments, code TODOs)
**Workflow:**
1. Gather findings from source
2. Create TodoWrite list with dependencies
3. Spawn pr-comment-resolver agents in parallel (respecting dependencies)
4. Commit changes + mark todos complete

### Step 9: Ship
**Command:** Use `clavain:landing-a-change` skill
**Actions:**
- Verify, document, commit completed work
- Push to main (trunk-based development)

---

## Part 2: Quality Gates & Phase Transitions

**File:** `/root/projects/Clavain/commands/quality-gates.md`

### Architecture
Quality gates = **adaptive reviewer selection** based on git diff analysis.

### Selection Logic

**Phase 1: Analyze Changes**
```bash
git diff --name-only HEAD
git diff --cached --name-only
```
Classify by language (.go, .py, .ts, .sh, .rs) and risk domain.

**Phase 2: Select Reviewers (Risk-Based)**
- **Always:** fd-architecture, fd-quality
- **Conditional:**
  - Auth/crypto/input/secrets → fd-safety
  - Migration/schema/backfill → fd-correctness + data-migration-expert
  - Perf-critical code → fd-performance
  - Concurrency/async → fd-correctness
  - User-facing flows → fd-user-product
- **Threshold:** Don't run >5 agents total

**Phase 3: Gather Context**
```bash
git diff HEAD > /tmp/qg-diff.txt
git diff --cached >> /tmp/qg-diff.txt
```

**Phase 4: Run Agents in Parallel** (Task tool, `run_in_background: true`)

**Phase 5: Synthesize Results**
Produce a Quality Gates Report with:
- X files changed across Y languages
- Risk domains detected
- Agents invoked + findings
- P1/P2/P3 counts
- Gate result: PASS / FAIL

**Phase 6: File Findings as Beads** (optional)
If >3 findings, ask user to create beads issues for tracking.

### Important Guidance
- **Don't over-review small changes** — <20 lines + single file = only run fd-quality
- **Run after tests pass** — quality gates complement testing, don't replace it
- **P1 findings block shipping** — must be fixed before committing
- **Alternative:** `/clavain:interpeer quick` for lightweight cross-AI second opinion

---

## Part 3: Work Discovery & Phase Awareness

**Files:**
- `/root/projects/Clavain/commands/sprint-status.md`
- `/root/projects/Clavain/hooks/sprint-scan.sh`
- `/root/projects/Clavain/hooks/session-start.sh` (calls sprint-scan for brief scan)

### Current Work Discovery Mechanisms

#### 1. Session-Start Hook (Lightweight, Automatic)
**Runs at:** Every new Claude session
**Source:** `/root/projects/Clavain/hooks/session-start.sh`

**Scans for:**
1. **HANDOFF.md** — session continuity signal (previous session left incomplete work)
2. **Orphaned brainstorms** — 2+ brainstorms without matching plans (using slug matching)
3. **Incomplete plans** — <50% checklist completion + older than 1 day
4. **Stale beads** — in_progress with no recent activity (via `bd stale`)
5. **Strategy gap** — brainstorms exist but no PRDs

**Output:** Injected into additionalContext for SessionStart hook, 1-2 line warnings only

#### 2. Sprint Status Command (Full Scan, On-Demand)
**Command:** `/clavain:sprint-status`
**Sections:** 7 detailed areas

| Section | What it reports |
|---------|-----------------|
| Session Continuity | HANDOFF.md presence |
| Workflow Pipeline | Brainstorm/PRD/Plan counts |
| Plan Progress | Completion % for each plan with checklists |
| Orphaned Brainstorms | Brainstorms without matching plans (with slugs) |
| Beads Health | `bd stats` + stale count |
| Skipped Phases | Recent commits not referencing plan/bead/review (20 commits) |
| Recommendations | 1-3 prioritized next actions |

#### 3. Artifact-Based Discovery
Work status inferred from filesystem:
- **Brainstorm exists** → exploration phase (docs/brainstorms/)
- **PRD exists** → strategized (docs/prds/)
- **Plan exists** → ready to execute (docs/plans/)
- **Beads issues exist** → tracked work items (.beads/)
- **Git commits reference plan** → execution in progress

#### 4. Beads Integration (Optional but Recommended)
**Not mandatory in /lfg pipeline**, but creates cross-session task tracking.

**Strategy step creates:**
- Epic: `bd create --title="<PRD title>" --type=epic`
- Features: `bd create --title="F1: <name>" --type=feature --priority=2`
- Dependencies: `bd dep add <feature> <epic>`

**Discovery commands:**
```bash
bd ready                    # Issues ready to work (no blockers)
bd list --status=open       # All open issues
bd list --status=in_progress  # Active work
bd blocked                  # Blocked issues
bd stale                    # in_progress with no recent activity (>2 days)
bd show <id>                # Detailed view with dependencies
```

**Viewer:** `bv` shows PageRank, critical path, parallel execution opportunities

### Missing Capabilities

**Gap 1: No Explicit Phase State**
- Work status inferred from artifact presence, not stored
- No persistent state machine (e.g., `phase: strategize | planning | executing | reviewing | shipping`)
- Resuming partial work requires manual artifact scanning

**Gap 2: No Automated Phase Detection**
- When user asks "where are we?", sprint-status gives breakdown but no "current phase" label
- Session-start hints at problems but doesn't suggest "resume Step X of /lfg"

**Gap 3: No Gate Failure Recovery Patterns**
- If flux-drive (Step 4) finds P1 issues, no structured path to fix → retry
- If quality-gates (Step 7) fails, no automated re-run after fixes

**Gap 4: No Phase Transition Validation**
- No check that Step 3 (plan) completed successfully before Step 4 (review plan)
- No check that tests passed before quality-gates

---

## Part 4: Brainstorm & Strategy (Artifact Creation)

**Files:**
- `/root/projects/Clavain/skills/brainstorming/SKILL.md`
- `/root/projects/Clavain/commands/strategy.md`

### Brainstorming Skill
**How it creates artifacts:**
1. **Understanding phase:** One question at a time, dialogue-driven
2. **Exploring approaches:** 2-3 options with tradeoffs
3. **Presenting design:** Sections of 200-300 words, incremental validation
4. **Documentation:** Write to `docs/brainstorms/YYYY-MM-DD-<topic>.md`
5. **Commit:** Git commit the brainstorm

**Output format:**
- Markdown document with design sections
- No structured PRD yet (that comes in Strategy step)

### Strategy Command
**Bridge between brainstorming and planning**

**Phase 1: Extract Features**
- Parse brainstorm to identify discrete, independently-deliverable features
- Ask user for feature selection (all or subset)

**Phase 2: Write PRD**
```markdown
# PRD: <Title>

## Problem
[1-2 sentences: pain point]

## Solution
[1-2 sentences: what we're building]

## Features
### F1: <Name>
**What:** [One sentence]
**Acceptance criteria:**
- [ ] Criterion 1
- [ ] Criterion 2

### F2: ...

## Non-goals
[What we're explicitly NOT doing]

## Dependencies
[External systems, libraries, prior work]

## Open Questions
[Unresolved items that could affect implementation]
```
- Saved to `docs/prds/YYYY-MM-DD-<topic>.md`

**Phase 3: Create Beads**
- Epic: `bd create --title="<PRD title>" --type=epic --priority=1`
- Per feature: `bd create --title="F1: <name>" --type=feature --priority=2`
- Establish dependencies: `bd dep add <feature-id> <epic-id>`

**Phase 4: Validate (Lightweight Flux-Drive)**
```bash
/clavain:flux-drive docs/prds/YYYY-MM-DD-<topic>.md
```
Catches scope creep, missing acceptance criteria, architectural risks before coding.

**Phase 5: Handoff**
User choices:
- Plan the first feature
- Plan all features
- Refine PRD (address flux-drive findings)
- Done for now

---

## Part 5: Flux-Drive Review Framework

**File:** `/root/projects/Clavain/skills/flux-drive/SKILL.md` (367 lines)
**Related:**
- `phases/launch.md` (338 lines) — agent dispatch
- `phases/synthesize.md` (303 lines) — findings synthesis
- `phases/shared-contracts.md` (97 lines) — agent output format contracts
- `phases/launch-codex.md` (116 lines) — parallel Codex dispatch
- `phases/cross-ai.md` (30 lines) — Oracle integration

### Flux-Drive Architecture

**Progressive Loading:** Skill split across phase files, read on-demand.

**4 Phases:**
1. **Phase 1: Analyze + Static Triage** — Understand project, profile document, select agents
2. **Phase 2: Launch** — Dispatch agents (Stage 1 immediate, Stage 2 on-demand)
3. **Phase 3: Synthesize** — Collect findings, produce report, optional beads filing
4. **Phase 4: Cross-AI (Optional)** — Oracle perspective (only if Oracle available)

### Phase 1: Input Detection & Agent Selection

**Input Types:**
- `INPUT_TYPE = file` — Document review (plan, spec, brainstorm)
- `INPUT_TYPE = directory` — Repo review (README, structure, files)
- `INPUT_TYPE = diff` — Git diff review

**Document Profiling:**
- Type, summary, languages, frameworks, domains touched, key files
- Section analysis: thin/adequate/deep for each section
- Estimated complexity, review goal

**Agent Roster (6 core + 1 cross-AI):**
| Agent | Domain |
|-------|--------|
| fd-architecture | Module boundaries, coupling, complexity |
| fd-safety | Security, credentials, trust boundaries |
| fd-correctness | Data consistency, race conditions, async |
| fd-quality | Naming, conventions, idioms |
| fd-user-product | User flows, UX, value prop, scope |
| fd-performance | Bottlenecks, resource usage, scaling |
| oracle-council (optional) | Cross-model validation, blind spots |

**Scoring Rules:**
- **2 (relevant):** Domain directly overlaps
- **1 (maybe):** Adjacent domain, include only for thin sections
- **0 (irrelevant):** Excluded, cannot be overridden by bonuses

**Bonuses:**
- Project Agent: +1 (project-specific CLAUDE.md/AGENTS.md)
- Plugin Agent with docs: +1 (codebase-aware mode)

**Selection Cap:** 8 agents maximum

**Stage Assignment:**
- **Stage 1:** Top 2-3 agents (immediate)
- **Stage 2:** Remaining selected agents (on-demand)

### Phase 2: Launch & Monitoring

**Task-Based Dispatch (default):**
```bash
Task(fd-architecture): "[profiling] [agent system prompt] [document]"
```

**Codex-Based Dispatch (when clodex mode active):**
- Dispatch to Codex CLI for parallel execution
- Agents run in sandbox, output to same format

**Monitoring Contract:**
- Poll `{OUTPUT_DIR}/` for `.md` files every 30s
- Report completion with elapsed time
- Timeout: 5min (Task), 10min (Codex)

**Output Format (Shared Contract):**
```markdown
### Findings Index
- SEVERITY | ID | "Section Name" | Title
...
Verdict: safe|needs-changes|risky

### Summary
[3-5 lines]

### Issues Found
[Numbered with severity]

### Improvements Suggested
[Numbered with rationale]

### Overall Assessment
[1-2 sentences]
```

Agent writes to `.md.partial` during work, adds `<!-- flux-drive:complete -->`, renames to `.md` when done.

### Phase 3: Synthesis

**Aggregates findings:**
- Count by severity (P0, P1, P2, P3)
- Convergence analysis (how many agents flagged same issue)
- Contradictions (agents disagreed)
- Blind spots (only one agent flagged)

**Produces report:**
```markdown
## Synthesis Report

## Summary
[1-2 sentence overview]

## Findings by Severity
### P0 Critical: [count]
[List with convergence confidence]

### P1 Important: [count]
...

## Convergence Analysis
[Which findings had 2+ agent agreement]

## Blind Spots
[Only 1 agent flagged, might be worth noting]

## Recommended Actions
[Prioritized list]

## Optional: Cross-AI Insights
[If Oracle participated — comparison and unique insights]
```

**Optional Beads Filing:**
Ask user: "File review findings as beads issues?" (recommended for >3 findings)

### Phase 4: Cross-AI Comparison (Oracle)

**Trigger:** Only if Oracle was in roster
**Invocation:** Deep mode with prompt-optimization pipeline (not raw oracle calls)

**CLI Template:**
```bash
env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait --timeout 1800 \
  --write-output {OUTPUT_DIR}/oracle-council.md.partial \
  -p "Review this {doc_type} for {goal}. Focus on: issues Claude-based reviewers might miss." \
  -f "{files}" && \
  echo '<!-- flux-drive:complete -->' >> {OUTPUT_DIR}/oracle-council.md.partial && \
  mv {OUTPUT_DIR}/oracle-council.md.partial {OUTPUT_DIR}/oracle-council.md
```

**Important:** Use `--write-output` (not `> file`) to capture clean browser output. Do NOT wrap with `timeout` — Oracle has internal `--timeout` for cleanup.

---

## Part 6: Plan Writing & Execution

**Files:**
- `/root/projects/Clavain/commands/work.md`
- `/root/projects/Clavain/skills/writing-plans/SKILL.md`
- `/root/projects/Clavain/skills/executing-plans/SKILL.md` (referenced, not fully read)

### Writing Plans

**Output:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

**Required Header:**
```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** [One sentence]
**Architecture:** [2-3 sentences about approach]
**Tech Stack:** [Key technologies]
```

**Task Structure:**
```markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**
[Complete test code]

**Step 2: Run test to verify it fails**
Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**
[Complete code]

**Step 4: Run test to verify it passes**
Run: `pytest ...`
Expected: PASS

**Step 5: Commit**
git add ...
git commit -m "feat: ..."
```

**Granularity:** Each step = one action (2-5 minutes)
- Write test
- Run it to verify failure
- Implement minimal code
- Run test to verify pass
- Commit

**Execution Handoff (Codex vs Subagent):**
After writing plan, analyze task independence:
| Signal | Recommendation |
|--------|-----------------|
| <3 tasks, or tasks share files | Subagent-Driven |
| 3+ independent tasks with clear file lists | Codex Delegation (Recommended) |
| User wants manual checkpoints | Parallel Session |
| Codex unavailable | Subagent-Driven |

When clodex mode active: Codex Delegation automatically selected → plan executed in parallel → **skip `/work` step in /lfg.**

### Work Command (Execution)

**File:** `/root/projects/Clavain/commands/work.md`

**4 Phases:**

**Phase 1: Quick Start**
1. Read plan completely
2. Clarify ambiguities
3. Get user approval
4. `git pull` to main
5. Create TodoWrite list with dependencies

**Phase 2: Execute**
Loop over each task:
1. Mark task in-progress in TodoWrite
2. Read referenced files from plan
3. Look for similar patterns in codebase
4. Implement following conventions
5. Write tests
6. Run tests after changes
7. Mark task completed
8. Update plan file: `- [ ]` → `- [x]`
9. Evaluate for incremental commit

**Commit heuristic:** "Can I write a complete, valuable commit message? If yes, commit. If 'WIP' or 'partial', wait."

**Phase 3: Quality Check**
1. Run full test suite
2. Run linting
3. Option: `/quality-gates` for risky/large changes (not by default)
4. Option: `/interpeer quick` for cross-AI second opinion

**Phase 4: Ship**
1. Stage specific files (not `git add .`)
2. Commit with conventional format
3. Push to main
4. Notify user

**Key Principles:**
- Start fast, execute faster
- Plan is your guide (follow existing patterns)
- Test as you go (don't wait until end)
- Quality is built-in (don't over-review small changes)
- Ship complete features (finish before moving on)

---

## Part 7: Beads Integration & State Tracking

**File:** `/root/projects/Clavain/skills/beads-workflow/SKILL.md`

### Beads Overview

**Purpose:** Git-native issue tracker for persistent cross-session task tracking
**Backend:** Dolt (version-controlled SQL) with JSONL sync layer
**Storage:** `.beads/` directory (JSONL + Dolt database, gitignored)
**Sync:** `bd sync` commits state to git

### Workflow Modes
| Mode | Purpose |
|------|---------|
| Stealth | Local-only, nothing committed |
| Contributor | Routes planning to `~/.beads-planning` (separate repo) |
| Maintainer | Full read-write access (auto-detected) |

### When to Use Beads vs TaskCreate
| Use Beads | Use TaskCreate |
|-----------|----------------|
| Multi-session work | Single session |
| Tasks have dependencies | Independent tasks |
| Persistent tracking needed | Ephemeral tracking OK |
| Cross-agent collaboration | Solo execution |
| Git-synced state | In-memory state OK |

### Issue Hierarchy
```bash
bd create --title="Auth overhaul" --type=feature --priority=1
# Creates bd-a3f8

bd create --title="JWT middleware" --parent=bd-a3f8 --priority=2
# Creates bd-a3f8.1

bd create --title="Token refresh" --parent=bd-a3f8.1 --priority=2
# Creates bd-a3f8.1.1
```

### Discovery Commands
```bash
bd ready                          # Issues ready (no blockers)
bd list --status=open             # All open
bd list --status=in_progress      # Active work
bd blocked                        # Blocked issues
bd show <id>                      # Details + dependencies
bd stale                          # in_progress >2 days with no activity
bd stats                          # Counts by status
bv                                # Viewer — PageRank, critical path, parallel opportunities
```

### State Transitions
```bash
bd update <id> --status=in_progress    # Claim work
bd close <id>                          # Mark complete
bd close <id> --reason="explanation"   # Close with reason
bd dep add <issue> <depends-on>        # Create dependency
```

### Post-Batch Consolidation
After creating 5+ beads (reviews, audits, planning), consolidate:
1. **Same-file edits** — merge into one bead with combined criteria
2. **Parent-child absorption** — small beads become acceptance criteria on parent
3. **Duplicate intent** — close duplicates
4. **Missing dependencies** — add explicit `bd dep add`
5. **Missing descriptions** — add concrete acceptance criteria

Typically reduces batch backlogs by 30-40%.

### Session Close Protocol
```bash
git status              # Check changes
git add <files>         # Stage code
bd sync                 # Commit beads changes
git commit -m "..."     # Commit code
bd sync                 # Commit any new beads changes
git push                # Push to remote
```

**CRITICAL:** Never say "done" without this protocol.

### Memory Compaction
Old closed tasks are semantically summarized to reduce token cost. Automatic in Beads.

### Daily Maintenance
- `bd doctor --fix --yes` — runs daily via systemd timer
- `bd admin cleanup --older-than 30 --force` — prune closed issues >30d
- `bd upgrade` — periodic binary upgrade (manual)
- Systemd timer: `clavain-beads-hygiene.service` at 6:15 AM Pacific

---

## Part 8: Session Continuity & Handoff

**File:** `/root/projects/Clavain/hooks/session-start.sh` (lines 81-88 reference sprint-scan)

### HANDOFF.md Signal

**What it is:** Marker file created when a session ends with incomplete work

**When created:** Session-handoff hook generates it
**Location:** Project root (`HANDOFF.md`)
**Contains:** Context for resuming work in next session

**Discovery:**
- Session-start hook checks for it automatically
- Included in sprint-start brief scan warnings
- `/sprint-status` reports it in "Session Continuity" section

**Action when found:**
1. Read HANDOFF.md with Read tool
2. Understand what was in progress
3. Decide whether to resume or reset

---

## Part 9: Missing Pieces & Architectural Gaps

### Gap Analysis

| Feature | Status | Impact |
|---------|--------|--------|
| **Explicit phase state** | MISSING | No persistent "current phase" label; work status inferred from artifacts |
| **Phase detection** | MISSING | Resuming /lfg mid-workflow requires manual step identification |
| **Gate failure recovery** | MISSING | If flux-drive/quality-gates finds issues, no structured "fix → retry" path |
| **Phase validation** | MISSING | No checks that prior steps completed successfully |
| **Work discovery** | PARTIAL | Sprint-status is comprehensive but manual; no auto-suggestion of next step |
| **Multi-iteration support** | PARTIAL | Strategy creates beads; workflow assumes single feature at a time |
| **Pause/Resume signaling** | PARTIAL | HANDOFF.md exists but is optional; only used if session-handoff hook runs |
| **Quality gate automation** | GOOD | Flux-drive + quality-gates auto-select agents well |
| **Cross-session tracking** | GOOD | Beads provides git-synced issue tracking |
| **Work discovery speed** | GOOD | Sprint-scan is fast (<100ms for bd doctor) |

### Specific Gaps

1. **No "current phase" metadata**
   - Session-start hook tells you problems (orphaned brainstorms, stale beads) but not "you're in the execute phase of /lfg"
   - `/sprint-status` gives detailed breakdown but no "current phase: executing" label
   - **Would require:** Explicit phase marker in plan file or beads issue

2. **No resume-from-step guidance**
   - User asks "where are we?" → sprint-status shows breakdown
   - But no automatic "you were in Step 6, run `/clavain:quality-gates` next"
   - **Would require:** Phase state tracking + step completion signals

3. **No structured gate failure recovery**
   - If Step 4 (flux-drive) finds P1 issues → document says "stop and address before proceeding"
   - But no structured path: "fix issues, save fixes to FIXES.md, re-run flux-drive, confirm pass, proceed to Step 5"
   - **Would require:** Gate failure beads + retry pattern

4. **No plan-to-beads sync**
   - Strategy creates beads, but plan tasks aren't linked to beads issues
   - Work step marks tasks `- [x]` in plan file but doesn't update beads status
   - **Would require:** Bidirectional sync between plan checklist + beads status

5. **No implicit phase validation**
   - No check that Step 3 (plan) file exists and is complete before Step 4 (review)
   - No check that tests passed (Step 6) before quality-gates (Step 7)
   - **Would require:** Pre-step validators in /lfg orchestrator

---

## Part 10: Summary & Recommendations

### What Already Exists (Strengths)

1. **Well-defined 9-step /lfg pipeline** with clear artifacts at each phase
2. **Sophisticated quality gates** (flux-drive + quality-gates) with adaptive agent selection
3. **Comprehensive work discovery** via sprint-status scanning (7 sections, 0-2 sec runtime)
4. **Cross-session task tracking** via Beads with robust dependency tracking
5. **Phase validation at key gates:**
   - Step 4: flux-drive reviews plan before execution
   - Step 6: tests must pass before Step 7
   - Step 7: quality-gates runs before ship
6. **Lightweight session continuity** via HANDOFF.md signal
7. **Parallel execution support** (Codex delegation in write-plan, quality-gates, resolve)

### What's Missing (Gaps)

1. **No explicit phase state model** — status inferred from artifacts, not stored
2. **No automated phase detection** — sprint-status gives breakdown but no "resume from Step X" suggestion
3. **No gate failure recovery patterns** — docs say "fix and retry" but no structured path
4. **No plan-to-beads sync** — tasks tracked in two places, not linked
5. **No pre-step validation** — workflow assumes user correctly followed prior steps

### Recommendations for Phase-Gate Enhancement

**Low-Hanging Fruit (can implement quickly):**
1. Add `phase: [brainstorm | strategy | planning | reviewing | executing | shipping]` metadata to plan files
2. Enhance sprint-status to suggest "next step" based on phase + artifact state
3. Add `/clavain:resume-lfg` command that detects phase and suggests next step
4. Create beads convention: link plan tasks to beads issues via comment (`<!-- beads: bd-xxx -->`)

**Medium Effort (requires coordination):**
1. Add pre-step validators to /lfg (check prior artifacts before executing each step)
2. Create gate-failure recovery pattern (beads for gate findings, retry step)
3. Sync plan checklist with beads issue status (mark beads complete when plan task checked)
4. Add phase transition logging to git commits (e.g., "phase: strategize → planning")

**Architectural (larger changes):**
1. Create a ".lfg-state.json" file tracking phase, step completion, gate results, timestamps
2. Build phase state discovery into session-start hook (auto-detect and suggest resume)
3. Implement structured gate failure handling (findings → beads → re-run → confirm)

---

## Appendix: File Structure Reference

```
/root/projects/Clavain/
├── commands/
│   ├── lfg.md                    # 9-step workflow orchestrator
│   ├── full-pipeline.md          # Alias for lfg
│   ├── strategy.md               # Brainstorm → PRD → Beads bridge
│   ├── write-plan.md             # Plan writer (not fully read)
│   ├── work.md                   # Plan executor
│   ├── quality-gates.md          # Adaptive reviewer selection
│   ├── flux-drive.md             # Phase 4 review gate
│   ├── resolve.md                # Phase 8 issue resolver
│   └── sprint-status.md          # Work discovery + health scan
│
├── skills/
│   ├── brainstorming/SKILL.md    # Dialogue-driven design
│   ├── writing-plans/SKILL.md    # Plan composition + execution handoff
│   ├── executing-plans/SKILL.md  # Referenced in plans (not fully read)
│   ├── flux-drive/SKILL.md       # Multi-phase review orchestrator
│   │   ├── phases/launch.md
│   │   ├── phases/synthesize.md
│   │   ├── phases/shared-contracts.md
│   │   ├── phases/launch-codex.md
│   │   └── phases/cross-ai.md
│   └── beads-workflow/SKILL.md   # Cross-session task tracking
│
├── hooks/
│   ├── session-start.sh          # Injects sprint awareness + companion detection
│   └── sprint-scan.sh            # Work discovery library (full + brief scans)
│
└── docs/
    ├── brainstorms/              # Freeform exploration
    ├── prds/                     # Structured requirements + acceptance criteria
    ├── plans/                    # Implementation tasks with test code
    └── research/                 # Like this file
```

---

## Document Metadata

- **Last updated:** 2026-02-12
- **Scope:** Clavain v0.4.45
- **Methodology:** Comprehensive code reading (SKILL.md, commands, hooks, shared contracts)
- **Files analyzed:** 15 primary source files
- **Code lines read:** ~1,500 lines
