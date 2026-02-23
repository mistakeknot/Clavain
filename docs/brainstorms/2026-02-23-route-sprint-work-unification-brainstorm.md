# Unify /route → /sprint → /work into Adaptive Single-Entry Workflow
**Bead:** iv-hks2

## What We're Building

A three-layer command architecture where:
- `/route` is the universal entry point (discovery, resume, classification, dispatch)
- `/sprint` is a thin phase sequencer (brainstorm → strategy → plan → review → execute → ship)
- `/work` is the execution engine (unchanged — read plan → execute → quality → ship)

Currently `/sprint` has a 400-line preamble (discovery, resume, checkpoints, complexity) that runs every invocation even when it skips to `/work`. We're extracting that preamble into `/route` so sprint becomes a pure phase sequencer.

## Why This Approach

- **Separation of concerns:** Route decides WHAT to do, sprint decides HOW to sequence phases, work EXECUTES a plan
- **Reduced prompt weight:** Sprint drops from ~400 lines to ~180 lines (just steps + auto-advance + checkpointing)
- **Single entry point:** Users only need to know `/route` — it handles resume, discovery, and dispatch
- **Explicit override:** `/sprint` and `/work` remain directly invocable for users who want to force a specific path

## Architecture

```
/route (entry point, ~200 lines)
  1. Check active sprints → resume if found (confidence 1.0)
  2. Discovery scan (beads, artifacts)
  3. Heuristic classification with confidence scoring:
     confidence >= 0.8 → dispatch directly
     confidence < 0.8  → escalate to haiku LLM
  4. Dispatch: /sprint, /work <plan>, or resume at specific phase

/sprint (phase sequencer, ~150 lines)
  Steps 1-10: brainstorm → strategy → plan → review
  → execute(/work) → test → quality-gates → resolve → reflect → ship
  + auto-advance protocol
  + session checkpointing (write/clear)
  + phase tracking

/work (execution engine, ~250 lines, UNCHANGED)
  Phase 1: read plan + clarify + gate check
  Phase 2: execute tasks with incremental commits
  Phase 3: quality check
  Phase 4: ship
```

## Confidence Scoring Table

| Condition | Route | Confidence |
|-----------|-------|------------|
| Active sprint found | Resume at phase | 1.0 |
| Plan artifact exists | `/work <plan>` | 1.0 |
| Bead phase = `planned` or `plan-reviewed` | `/work <plan>` | 1.0 |
| Bead action = `execute` or `continue` | `/work <plan>` | 1.0 |
| Complexity = 1 (trivial) | `/work` | 0.9 |
| No description AND no brainstorm | `/sprint` | 0.9 |
| Complexity = 5 (research) | `/sprint` | 0.85 |
| Free text, complexity 2-3, no bead | **→ haiku LLM** | 0.5-0.7 |
| Bead with description, no plan, complexity 3 | **→ haiku LLM** | 0.6 |

## Key Decisions

1. **Route absorbs the preamble** — discovery, resume, complexity classification all move to route
2. **Route handles resume** — checks active sprints first, dispatches to the right phase
3. **Sprint stays invocable** — users can force full lifecycle with `/sprint` directly
4. **Confidence threshold = 0.8** — heuristics handle obvious cases, haiku fires for ambiguous ones
5. **Work is unchanged** — it's the stable execution engine, no modifications needed

## What Moves Where

| Currently in sprint.md | Destination |
|---|---|
| Sprint Resume (check active, claim session) | route.md |
| Work Discovery (scan beads, present options) | route.md |
| Argument parsing (bead ID, --lane, --resume, --from-step) | route.md (bead ID, free text); sprint.md keeps --from-step |
| Complexity Assessment | route.md |
| Session Checkpointing | stays in sprint.md |
| Auto-Advance Protocol | stays in sprint.md |
| Phase Tracking | stays in sprint.md |
| Steps 1-10 | stays in sprint.md (the core value) |

## What Sprint Keeps

- Steps 1-10 (phase sequencing)
- Auto-advance protocol (phase transitions between steps)
- Session checkpointing (write after each step, clear on completion)
- Phase tracking (artifact recording)
- `--from-step <n>` flag (skip to specific step)
- Sprint summary on completion

## Open Questions

- Should `/route` with no arguments show a brief help message, or default to discovery scan?
- When route dispatches to `/sprint`, should it pass `--from-step brainstorm` explicitly, or let sprint start from Step 1 by default?
- Should the `using-clavain` routing table update to show `/route` as the primary entry point instead of `/sprint`?
