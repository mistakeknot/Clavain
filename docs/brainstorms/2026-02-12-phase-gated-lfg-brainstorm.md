# Phase-Gated /lfg with Work Discovery

> Brainstorm for evolving /lfg from a linear execution pipeline into an intelligent work-finder with formal phase gates enforced by beads state tracking.

## What We're Building

Two capabilities for `/lfg`:

1. **Work Discovery Mode** (`/lfg` with no args): Scan beads, artifacts, and filesystem to discover what needs attention. Rank by priority, phase maturity, and recency. Present top recommendations via AskUserQuestion with the best option as default (user just hits Enter).

2. **Phase-Gated Pipeline** (`/lfg` with args or after selecting from discovery): Same 9-step pipeline but with hard gates between phases. Each gate checks that the prior artifact was reviewed by flux-drive before advancing. Phase state tracked via `bd set-state <id> phase=<value>`.

## Why This Approach

### Beads as Workflow Engine

Beads has first-class support for exactly what we need:

- **`bd set-state <id> phase=<value>`** — Atomic phase transitions with event-sourced audit trail
- **`bd state <id> phase`** — Query current phase
- **`bd list --label "phase:planned"`** — Find all beads in a given phase
- **`bd list --label-pattern "phase:*"`** — Find all beads with any phase tracking

State changes create event beads (audit trail), remove old dimension labels, and add new ones atomically. No convention hacking needed.

### Requiring beads is reasonable because:
- Every Clavain project already has `.beads/` (session-start hook detects it)
- `bd` is installed on all dev machines (it's a Go binary, no runtime deps)
- Beads provides cross-session persistence that in-memory TaskCreate can't
- The beads-workflow skill already recommends beads over TaskCreate for multi-session work

## Key Decisions

### Phase Model

```
brainstorm → brainstorm-reviewed → strategized → planned → plan-reviewed → executing → tested → shipping → done
```

| Phase | Meaning | Artifact |
|-------|---------|----------|
| `brainstorm` | Idea explored, brainstorm doc written | `docs/brainstorms/*.md` |
| `brainstorm-reviewed` | Flux-drive reviewed brainstorm, no P0s | `docs/research/flux-drive/<topic>/` |
| `strategized` | PRD written, features extracted, bead created | `docs/prds/*.md` |
| `planned` | Implementation plan written with tasks | `docs/plans/*.md` |
| `plan-reviewed` | Flux-drive reviewed plan, no P0s | `docs/research/flux-drive/<topic>/` |
| `executing` | Code being written against the plan | git commits |
| `tested` | Tests pass, code complete | test results |
| `shipping` | Quality gates passed, resolving findings | `docs/reviews/*.md` |
| `done` | Shipped, bead closed | `bd close <id>` |

### Gate Enforcement (Hard Gates)

Each `/clavain:*` command checks the bead's current phase before proceeding:

| Command | Required phase | Gate check |
|---------|---------------|------------|
| `/clavain:strategy` | `brainstorm-reviewed` | flux-drive review exists, no P0s |
| `/clavain:write-plan` | `strategized` | PRD exists referencing this bead |
| `/clavain:work` | `plan-reviewed` | flux-drive review of plan exists, no P0s |
| `/clavain:quality-gates` | `executing` or `tested` | plan tasks checked off |
| `/clavain:resolve` + ship | `shipping` | quality-gates passed |

**Override**: `--skip-gate` flag available but prints prominent warning and records skip in bead notes.

### Entry Points (Flexible)

Not all work starts at brainstorm. Entry point recorded on bead so gates only enforce from there forward:

| Work type | Entry phase | Example |
|-----------|-------------|---------|
| Vague idea | `brainstorm` | "Should we add dark mode?" |
| Clear feature with requirements | `strategized` | User provides acceptance criteria |
| Bug with known fix | `planned` | "Fix the off-by-one in pagination" |
| Hotfix / emergency | `executing` | P0 production issue |

Implementation: `bd set-state <id> entry=<phase>` tracks where work entered the pipeline. Gate checks skip phases before the entry point.

### Work Discovery UX

When `/lfg` is invoked with no arguments:

**Step 1: Scan sources**
- `bd list --status=open --label-pattern "phase:*"` — tracked work with phases
- `bd ready` — work with no blockers
- `bd list --status=in_progress` — active work (might be stale)
- Scan `docs/brainstorms/`, `docs/prds/`, `docs/plans/` for orphaned artifacts (no linked bead)

**Step 2: Score and rank**
```
score = (5 - priority) × 10          # P0=50, P1=40, P2=30...
      + phase_advancement_bonus       # closer to shipping = +5 per phase
      + recency_bonus                 # updated in last 24h = +5
      - staleness_penalty             # >2 days same phase = -10
```

**Step 3: Present via AskUserQuestion**
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

User hits Enter → `/lfg` runs the pipeline starting at the appropriate step for that bead's phase.

### Session-Start Integration

The existing session-start hook already scans for beads and sprint status. Enhance with:

```
Companions detected:
- beads: 5 open issues, 2 ready to advance
  → Clavain-abc (P1) needs plan review — run /lfg to continue
```

This is the "light scan" — just 1-2 lines. `/lfg` without args does the "deep triage."

### How Gates Work Mechanically

Example: user runs `/clavain:write-plan` for bead Clavain-abc.

1. Orchestrator reads: `bd state Clavain-abc phase` → `"brainstorm-reviewed"`
2. Check: is `brainstorm-reviewed` a valid predecessor of `planned`? → Yes ✓
3. Also check: does the brainstorm flux-drive review exist? → `docs/research/flux-drive/<topic>/` → Yes ✓
4. Also check: does any review file contain P0 findings? → Grep for severity → No P0s ✓
5. All gates pass → proceed with plan writing
6. After plan written: `bd set-state Clavain-abc phase=planned --reason "Plan: docs/plans/2026-02-12-foo.md"`

If gate fails:
```
⛔ Gate blocked: Clavain-abc is in phase "brainstorm" — needs flux-drive review before planning.
   Run: /clavain:flux-drive docs/brainstorms/2026-02-12-foo-brainstorm.md
```

### Artifact-to-Bead Linking

Plans and PRDs reference their bead ID in the header:

```markdown
# Feature Implementation Plan

**Bead:** Clavain-abc
**PRD:** docs/prds/2026-02-12-foo.md
```

Discovery scans for this pattern to link artifacts to beads. Orphaned artifacts (no bead reference) get flagged in work discovery.

## Open Questions

1. **Should `/lfg` auto-create beads for orphaned artifacts?** If a brainstorm exists with no bead, should discovery offer to create one? (Leaning yes — with user confirmation.)

2. **How to handle multi-feature PRDs?** A PRD with F1, F2, F3 creates 3 beads via `/clavain:strategy`. Each gets its own phase tracking. But the PRD artifact is shared. Should the PRD bead be an epic with child feature beads?

3. **Should phase gates check for flux-drive review of the *specific* artifact, or any review?** E.g., if the plan was rewritten after review, should the old review still count? (Leaning no — review must be newer than artifact modification date.)

4. **Retrospective phase tracking for existing beads?** We have ~10 open beads with no phase labels. Should we backfill based on artifact existence? (Leaning yes — one-time migration script.)

## What We're NOT Building

- No custom UI / dashboard — beads CLI + AskUserQuestion is sufficient
- No Gantt charts or timeline estimation — beads dependencies handle ordering
- No automatic code generation — `/lfg` orchestrates, humans/agents write code
- No cross-project discovery — this is per-project (per `.beads/` database)
