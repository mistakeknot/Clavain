# Route/Sprint/Work Unification Implementation Plan
**Bead:** iv-hks2

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Restructure `/route` as the universal entry point (discovery, resume, classification, bead creation), `/sprint` as a thin phase sequencer, `/work` unchanged.

**Architecture:** Route absorbs sprint's preamble (discovery, resume, complexity, argument parsing, sprint bead creation). Sprint keeps only steps 1-10 + auto-advance + checkpointing + phase tracking. Route uses confidence-scored heuristics (threshold 0.8) with haiku LLM fallback.

**Tech Stack:** Markdown command files (Claude Code plugin commands), bash CLI calls to `clavain-cli`.

**Design decisions (resolved in brainstorm):**
1. Route dispatches to sprint at Step 1 — no `--from-step`, sprint's own logic handles step-skipping
2. Empty `/route` → discovery scan (same UX as current sprint)
3. Route creates sprint beads before dispatching to `/sprint`
4. Route classifies complexity and caches on bead; sprint reads cached value
5. `/route` replaces `/sprint` as primary "Build a feature" in routing table
6. Confidence threshold = 0.8; haiku LLM fires for ambiguous cases below threshold
7. `/work` unchanged

---

### Task 1: Rewrite route.md — full entry point with discovery, resume, classification

**Files:**
- Rewrite: `commands/route.md` (currently 113 lines → ~250 lines)

**Step 1: Read the source files**

Read `commands/route.md` (current) and `commands/sprint.md` (sections to extract):
- Sprint lines 7-49: "Before Starting — Sprint Resume"
- Sprint lines 51-123: "Work Discovery (Fallback)" + argument parsing
- Sprint lines 196-217: "Pre-Step: Complexity Assessment"
- Sprint lines 224-237: "Create Sprint Bead"

**Step 2: Write the new route.md**

Replace the entire content. New structure:

```
---
name: route
description: Universal entry point — discovers work, resumes sprints, classifies tasks, and dispatches to /sprint or /work
argument-hint: "[bead ID, feature description, or empty for discovery]"
---

# Route — Adaptive Workflow Entry Point

## Step 1: Check Active Sprints (Resume)
  - sprint-find-active → claim session → checkpoint recovery
  - Route to right command based on phase
  - Confidence: 1.0 (always definitive)
  - Stop after dispatch

## Step 2: Parse Arguments
  - --lane=<name> → set DISCOVERY_LANE
  - Empty → route_mode="discovery" → Step 3
  - Bead ID match → route_mode="bead" → gather metadata, artifacts, complexity → cache complexity on bead → Step 4
  - Free text → route_mode="text" → classify complexity → Step 4

## Step 3: Discovery Scan (discovery mode only)
  - discovery_scan_beads → present via AskUserQuestion
  - Handle all action types (continue, execute, plan, strategize, brainstorm, ship, closed, verify_done, create_bead)
  - Set CLAVAIN_BEAD_ID
  - Log selection → dispatch → stop

## Step 4: Classify and Dispatch

### 4a: Fast-Path Heuristics (confidence >= 0.8)
  Table: plan exists (1.0), phase=planned (1.0), action=execute (1.0),
         complexity=1 (0.9), no description (0.9), complexity=5 (0.85),
         epic with children (0.85)

### 4b: LLM Classification (confidence < 0.8)
  Haiku subagent → JSON response → default /sprint on parse failure

### 4c: Dispatch
  - Create sprint bead if dispatching to /sprint and no bead exists
  - Cache complexity on bead
  - Display verdict with confidence
  - Auto-dispatch via Skill tool (no confirmation)
  - Stop after dispatch
```

Key differences from current route.md:
- Step 1 (sprint resume) is entirely new — from sprint.md lines 7-49
- Step 2 (argument parsing) is expanded — adds --lane from sprint.md line 113, bead ID verification from sprint.md line 116-121
- Step 3 (discovery scan) is entirely new — from sprint.md lines 51-110
- Step 4a (heuristics) expanded with more rules and confidence scores
- Step 4c adds sprint bead creation (from sprint.md lines 224-237) and complexity caching

**Step 3: Verify the rewrite**

- [ ] Frontmatter has `name: route`, updated description, argument-hint
- [ ] Step 1 covers sprint resume (sprint-find-active, sprint-claim, checkpoint-read/validate)
- [ ] Step 2 covers argument parsing (--lane, bead ID, free text, empty)
- [ ] Step 3 covers full discovery (discovery_scan_beads, AskUserQuestion, all action types)
- [ ] Step 4a has complete confidence table (7 rules)
- [ ] Step 4b has haiku LLM classification
- [ ] Step 4c creates sprint bead before dispatching to /sprint
- [ ] Step 4c caches complexity on bead

**Step 4: Commit**

```bash
git add commands/route.md
git commit -m "feat(route): absorb sprint preamble — discovery, resume, classification, bead creation"
```

---

### Task 2: Slim sprint.md — strip preamble, keep phase sequencer

**Files:**
- Modify: `commands/sprint.md` (currently 401 lines → target ~180 lines)

**Step 1: Identify sections to remove**

REMOVE (now in route.md):
- Lines 7-49: "Before Starting — Sprint Resume"
- Lines 51-123: "Work Discovery (Fallback)" + argument parsing + separator
- Lines 196-217: "Pre-Step: Complexity Assessment"
- Lines 224-237: "Create Sprint Bead" subsection inside Step 1

KEEP:
- Lines 1-5: frontmatter (update description)
- Lines 128-148: "Session Checkpointing"
- Lines 150-186: "Auto-Advance Protocol"
- Lines 187-194: "Phase Tracking"
- Lines 219-223: Step 1: Brainstorm (without "Create Sprint Bead")
- Lines 239-401: Steps 2-10 + Error Recovery

**Step 2: Write the slimmed sprint.md**

New structure:

```
---
name: sprint
description: Phase sequencer — brainstorm, strategize, plan, execute, review, ship. Use /route for smart dispatch.
argument-hint: "[feature description or --from-step <step>]"
---

# Sprint — Phase Sequencer

Full lifecycle from brainstorm to ship. Normally invoked via /route. Can be invoked directly.

## Arguments
- $ARGUMENTS as feature description → used by Step 1
- --from-step <n> → skip to step. Names: brainstorm, strategy, plan, plan-review, execute, test, quality-gates, resolve, reflect, ship.

If CLAVAIN_BEAD_ID is set by caller (/route), use it. Otherwise, sprint runs without bead tracking.

## Complexity (Read from Bead)

Read cached complexity (set by /route):
  complexity = bd state $CLAVAIN_BEAD_ID complexity
  label = clavain-cli complexity-label $complexity

Display: "Complexity: N/5 (label)"
- 1-2: AskUser skip to plan?
- 3: Standard workflow
- 4-5: Full workflow with Opus

---

[Session Checkpointing — kept as-is]
[Auto-Advance Protocol — kept as-is]
[Phase Tracking — kept as-is]

## Step 1: Brainstorm
/clavain:brainstorm $ARGUMENTS
(NO "Create Sprint Bead" subsection — route creates it)

## Step 2-10: kept as-is

## Error Recovery
(Update: "re-invoke /clavain:route" instead of "re-invoke /clavain:sprint")
```

**Step 3: Execute the edit**

Use the Edit tool to:
1. Replace frontmatter description
2. Remove "Before Starting — Sprint Resume" section (lines 7-49)
3. Remove "Work Discovery (Fallback)" through separator (lines 51-124)
4. Remove "Pre-Step: Complexity Assessment" (lines 196-217)
5. Remove "Create Sprint Bead" subsection from Step 1 (lines 224-237)
6. Add new header, arguments section, and "read cached complexity" section
7. Update Error Recovery to reference /route

**Step 4: Verify**

```bash
wc -l commands/sprint.md   # Expected: ~180 lines
```

Verify:
- [ ] No "Before Starting — Sprint Resume"
- [ ] No "Work Discovery"
- [ ] No argument parsing for bead ID, --lane, --resume
- [ ] No "Pre-Step: Complexity Assessment"
- [ ] No "Create Sprint Bead"
- [ ] Steps 1-10 intact
- [ ] Auto-Advance Protocol intact
- [ ] Session Checkpointing intact
- [ ] Phase Tracking intact
- [ ] --from-step documented
- [ ] "Run these steps in order" instruction present

**Step 5: Commit**

```bash
git add commands/sprint.md
git commit -m "refactor(sprint): strip preamble — now a thin phase sequencer (~180 lines)"
```

---

### Task 3: Update routing table and cross-references

**Files:**
- Modify: `skills/using-clavain/SKILL.md`
- Modify: `commands/help.md`
- Modify: `commands/setup.md`

**Step 1: Update using-clavain/SKILL.md**

Change:
```
| Build a feature end-to-end | `/clavain:sprint` |
```
to:
```
| Build a feature end-to-end | `/clavain:route` |
```

The "Not sure where to start → /route" row already exists. Merge it with "Build a feature":
- Remove the separate "Not sure where to start" row
- The merged "Build a feature end-to-end → /route" covers both use cases

Add new row after "Build a feature":
```
| Force full lifecycle | `/clavain:sprint` |
```

**Step 2: Update commands/help.md**

Line 14 — Daily Drivers table: change `/clavain:sprint` to `/clavain:route` with updated description:
```
| `/clavain:route` | Adaptive entry point — discovers work, classifies, dispatches | `/route build a caching layer` |
```

Line 41 — Execute stage: keep `/clavain:sprint` in the Execute section (it's still a valid execute command), add `/clavain:route` above it:
```
| `/clavain:route` | Adaptive entry — routes to sprint or work automatically |
```

**Step 3: Update commands/setup.md**

Line 239: change:
```
- Or run `/clavain:sprint [task]` for the full autonomous lifecycle
```
to:
```
- Or run `/clavain:route [task]` for the adaptive workflow entry point
```

**Step 4: Verify no broken references**

```bash
# These should return 0 matches in sprint.md:
grep -c "discovery_scan_beads" commands/sprint.md   # 0
grep -c "sprint-find-active" commands/sprint.md     # 0
grep -c "classify-complexity" commands/sprint.md    # 0

# These should return 1+ matches in route.md:
grep -c "discovery_scan_beads" commands/route.md    # 1
grep -c "sprint-find-active" commands/route.md      # 1
grep -c "classify-complexity" commands/route.md     # 1+
```

**Step 5: Commit**

```bash
git add skills/using-clavain/SKILL.md commands/help.md commands/setup.md
git commit -m "docs: update routing table and references — /route is primary entry point"
```

---

### Task 4: Final verification

**Step 1: Command count**

```bash
ls commands/*.md | wc -l   # Expected: 54
```

**Step 2: Plugin manifest**

```bash
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"
```

**Step 3: Line counts**

```bash
wc -l commands/sprint.md   # Expected: <200
wc -l commands/route.md    # Expected: >200
```

**Step 4: Cross-reference integrity**

```bash
grep -n "Work Discovery" commands/sprint.md         # Expected: 0 matches
grep -n "Sprint Resume" commands/sprint.md          # Expected: 0 matches
grep "Build a feature" skills/using-clavain/SKILL.md  # Expected: /clavain:route
```
