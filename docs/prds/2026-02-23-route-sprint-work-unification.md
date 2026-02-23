# PRD: Unify /route → /sprint → /work
**Bead:** iv-hks2

## Problem
Users must decide between `/sprint` (10-phase lifecycle) and `/work` (4-phase execution) manually. Sprint's 400-line preamble (discovery, resume, checkpoints, complexity) runs every invocation even when it skips to `/work`, wasting context window.

## Solution
Restructure into a clean three-layer architecture: `/route` (entry + classification), `/sprint` (phase sequencing), `/work` (execution). Route absorbs sprint's preamble and becomes the universal entry point with confidence-scored heuristics and haiku LLM fallback.

## Features

### F1: Expand /route — absorb sprint preamble
**What:** Rewrite `commands/route.md` to include discovery scan, sprint resume, complexity classification, and confidence-scored dispatch with haiku LLM fallback.
**Acceptance criteria:**
- [ ] Route checks for active sprints first (confidence 1.0 → resume)
- [ ] Route runs discovery scan when no arguments and no active sprint
- [ ] Route presents discovered beads via AskUserQuestion (same UX as current sprint discovery)
- [ ] Heuristics produce confidence scores per the brainstorm table
- [ ] Confidence >= 0.8 dispatches directly without LLM
- [ ] Confidence < 0.8 escalates to haiku subagent for classification
- [ ] Route handles bead ID arguments (verify bead, read state, dispatch)
- [ ] Route handles free-text arguments (classify and dispatch)
- [ ] Route handles empty arguments (discovery scan → present beads → dispatch)
- [ ] Route creates sprint bead before dispatching to `/sprint` (if no bead exists)
- [ ] Route classifies complexity and caches on bead (`bd set-state $BEAD complexity=$score`)
- [ ] `--lane=<name>` flag sets `DISCOVERY_LANE` before discovery calls
- [ ] Sets `CLAVAIN_BEAD_ID` before dispatching

### F2: Slim /sprint — pure phase sequencer
**What:** Strip sprint.md down to steps 1-10 + auto-advance + checkpointing. Remove discovery, resume, complexity assessment, and argument parsing sections.
**Acceptance criteria:**
- [ ] Sprint no longer contains "Before Starting — Sprint Resume" section
- [ ] Sprint no longer contains "Work Discovery" section
- [ ] Sprint no longer contains argument parsing section (bead ID, --lane, --resume)
- [ ] Sprint no longer contains "Pre-Step: Complexity Assessment" section (reads cached value from bead state instead)
- [ ] Sprint no longer creates sprint beads (route creates them before dispatching)
- [ ] Sprint retains Steps 1-10 (brainstorm through ship)
- [ ] Sprint retains Auto-Advance Protocol
- [ ] Sprint retains Session Checkpointing (write/clear)
- [ ] Sprint retains Phase Tracking
- [ ] Sprint retains `--from-step <n>` support
- [ ] Sprint still accepts `$ARGUMENTS` as feature description for Step 1
- [ ] Sprint still works when invoked directly (not via route)
- [ ] Sprint line count drops from ~400 to ~200 or less

### F3: Update routing table and references
**What:** Update using-clavain SKILL.md and other cross-references to position `/route` as the primary entry point.
**Acceptance criteria:**
- [ ] `using-clavain/SKILL.md` routing table shows `/route` as primary for "Build a feature end-to-end" (instead of `/sprint`)
- [ ] "Not sure where to start" row remains pointing to `/route`
- [ ] "Not sure where to start" and "Build a feature" merge into single `/route` row
- [ ] New row: "Force full lifecycle → `/clavain:sprint`"
- [ ] No other commands break due to referencing removed sprint sections

## Non-goals
- Modifying `/work` — it's the stable execution engine, unchanged
- Changing phase names or the 10-step sequence
- Removing `/sprint` as a user-facing command — it stays invocable
- Modifying sprint infrastructure (lib-sprint.sh, clavain-cli subcommands)

## Dependencies
- Existing `lib-discovery.sh` (discovery_scan_beads, infer_bead_action)
- Existing `clavain-cli` subcommands (sprint-find-active, sprint-claim, classify-complexity, etc.)
- Current `route.md` (just created — will be rewritten)

## Design Decisions (Resolved)

1. **Route dispatches to sprint at Step 1** — no `--from-step`, sprint's own complexity logic offers to skip to plan for simple tasks
2. **Empty /route → discovery scan** — same UX as current sprint with no args
3. **Route creates sprint beads** — before dispatching to sprint, so sprint never needs to create beads
4. **Route classifies, sprint reads cached** — `bd set-state $BEAD complexity=$score`, sprint reads from bead state
5. **Routing table: /route replaces /sprint** as primary "Build a feature" entry, sprint becomes "Force full lifecycle"
6. **Confidence threshold = 0.8** — heuristics handle obvious cases, haiku LLM fires for ambiguous
7. **Work unchanged** — no modifications to work.md
