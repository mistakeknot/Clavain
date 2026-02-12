# PRD: Phase-Gated /lfg with Work Discovery

## Problem

Users returning to a Clavain project after hours or days have no way to quickly see what needs attention. The current `/lfg` pipeline assumes you know what to work on and forces a linear brainstorm-to-ship flow even for bug fixes. Quality reviews are optional and easily skipped — there's no enforcement or even tracking of whether artifacts were reviewed before advancing.

## Solution

Evolve `/lfg` into an intelligent work-finder with formal phase tracking. Two milestones shipped independently: (1) Work Discovery scans beads and artifacts to recommend prioritized next actions, (2) Phase Gates track workflow state via `bd set-state` and enforce review-before-advance discipline with tiered strictness.

## Features

### M1: Work Discovery

#### F1: Beads-Based Work Scanner
**What:** `/lfg` with no arguments scans open beads and ranks them by priority, phase maturity, and recency.
**Ranking algorithm (v1):** Priority-only sort — P0 first, then P1, P2, etc. Within same priority, most recently updated first. No weighted scoring formula in v1; add recency/staleness factors in iteration 2 if priority-only proves insufficient.
**Acceptance criteria:**
- [ ] `bd list --status=open` results sorted by priority (P0 first), then by recency within same priority
- [ ] Stale beads (>2 days same status) flagged with staleness indicator
- [ ] In-progress beads shown separately from ready-to-start beads
- [ ] Output includes bead ID, title, priority, current status, and recommended next action
- [ ] Log which option user selects (for post-launch validation of ranking quality)

#### F2: AskUserQuestion Discovery UI
**What:** Discovery results presented via AskUserQuestion with the top-ranked item as the recommended default — user just hits Enter.
**Acceptance criteria:**
- [ ] Top 3-4 beads shown as options with compact labels (e.g., "Review Clavain-abc plan (P1)")
- [ ] First option marked as recommended
- [ ] "Start fresh brainstorm" always available as an option
- [ ] "Show full backlog" option for manual triage
- [ ] Selecting an option routes to the appropriate `/clavain:*` command for that bead's state

#### F3: Orphaned Artifact Detection
**What:** Scan `docs/brainstorms/`, `docs/prds/`, `docs/plans/` for files not linked to any bead.
**Acceptance criteria:**
- [ ] Orphaned artifacts included in discovery results with "Create bead?" action
- [ ] Artifacts linked to closed beads excluded (not orphaned)
- [ ] Linking detected via `**Bead:**` header pattern in markdown files

#### F4: Session-Start Light Scan
**What:** Session-start hook shows 1-2 line summary of work state.
**Acceptance criteria:**
- [ ] Shows count of open beads and how many are ready to advance
- [ ] Shows highest-priority item with suggested action
- [ ] Uses 60-second TTL cache to avoid repeated beads queries
- [ ] Adds no more than 200ms to session startup (cached path)

### M2: Phase Gates (Staged Rollout)

#### F5: Phase State Tracking
**What:** Every `/clavain:*` workflow command records phase transitions via `bd set-state <id> phase=<value>`.
**Acceptance criteria:**
- [ ] Phase model: `brainstorm → brainstorm-reviewed → strategized → planned → plan-reviewed → executing → shipping → done`
- [ ] `bd set-state` called with `--reason` documenting the artifact (e.g., "Plan: docs/plans/2026-02-12-foo.md")
- [ ] Missing phase labels set on first touch (inferred from command being run)
- [ ] Entry point inferred from first action (not upfront classification)
- [ ] Phase queryable via `bd state <id> phase` and `bd list --label-pattern "phase:*"`
- [ ] This stage ships with NO enforcement — tracking only

#### F6: Shared Gate Library
**What:** Centralized gate check logic in `hooks/lib-gates.sh` used by all workflow commands.
**Acceptance criteria:**
- [ ] `check_phase_gate()` function validates current phase is a valid predecessor of target phase
- [ ] `advance_phase()` function updates beads state and artifact metadata (dual persistence)
- [ ] `VALID_TRANSITIONS` array defines the phase graph in one place
- [ ] `is_valid_transition()` function used by all commands (no hardcoded phase knowledge in commands)
- [ ] Artifact phase checkpoint: commands write `**Phase:** <value>` to plan and brainstorm markdown headers. PRD artifacts do NOT get phase headers (PRDs are requirements docs shared across multiple feature beads)
- [ ] Fallback: if `bd state` fails, read phase from artifact header. Beads is authoritative; artifact header is emergency fallback only. Desync triggers warning, not block

#### F7: Tiered Gate Enforcement
**What:** Gate strictness varies by bead priority — high-priority work gets hard gates, low-priority gets soft warnings.
**Acceptance criteria:**
- [ ] P0/P1 beads: hard gates — command blocks if prior phase not reviewed, `--skip-gate --reason "..."` required to override
- [ ] P2/P3 beads: soft gates — warning printed but command proceeds, skip recorded in bead notes
- [ ] P4 beads: no gates — tracking only
- [ ] Gate checks verify: (a) phase is valid predecessor, (b) artifact exists, (c) flux-drive review exists with no P0 findings
- [ ] Stale review detection: git log check for commits to artifact after review date. Stale review = soft warning (not block) even for P0/P1 — user can re-run `/clavain:flux-drive` to refresh
- [ ] `--skip-gate` overrides recorded in bead notes for audit trail
- [ ] Log gate blocks, skips, and stale-review warnings (bead ID, priority, reason) for post-launch analysis

#### F8: Work Discovery + Phase Integration
**What:** Phase tracking becomes a ranking signal in work discovery, surfacing beads that are ready to advance.
**Acceptance criteria:**
- [ ] Discovery scoring includes phase_advancement_bonus (closer to shipping = higher rank)
- [ ] "Ready to advance" beads (review passed, next phase available) prioritized
- [ ] Phase state shown in AskUserQuestion option text when relevant
- [ ] `/lfg <bead-id>` routes to the correct command based on current phase

## Non-goals

- No custom UI/dashboard — beads CLI + AskUserQuestion is sufficient
- No Gantt charts or timeline estimation
- No cross-project discovery (per-project only, per `.beads/` database)
- No automatic code generation — `/lfg` orchestrates, agents write code
- No work types with separate phase sequences (single phase model, flexible entry points cover the same need)
- No 3-layer state model (macro/micro/artifact) — single phase dimension with `bd set-state` is simpler and sufficient for v1. Can add micro-status later if review cycles prove painful.

## Dependencies

- `bd` CLI (beads) installed and `.beads/` initialized in project
- `bd set-state` / `bd state` commands available (beads v0.4+)
- `bd list --label-pattern` for phase-based queries
- Existing flux-drive review infrastructure (agents, `docs/research/flux-drive/` convention)

## Rollout Plan

Phase gates ship in 5 stages (each independently valuable):

| Stage | What | Ships with M1? |
|-------|------|----------------|
| 0: Tracking | Add `bd set-state phase=X` to all commands, no enforcement | Yes |
| 1: Discovery | `/lfg` no-args mode with beads scanning + AskUserQuestion | Yes (M1 core) |
| 2: Dual persistence | Write phase to artifact headers + beads labels | M2 Stage 1 |
| 3: Soft gates | Warnings when phase is wrong, proceed anyway | M2 Stage 2 |
| 4: Hard gates | Tiered enforcement (P0/P1 hard, P2/P3 soft, P4 none) | M2 Stage 3 |

## Instrumentation

Both milestones require lightweight logging for post-launch validation:

**M1:** Log which AskUserQuestion option the user selects (recommended vs other). If recommended is picked >70% of the time, ranking works. If <50%, add recency/staleness scoring.

**M2:** Log gate blocks, skips, and stale-review warnings (bead ID, priority, reason). After 2 weeks: if <20% of ships use `--skip-gate`, gates are helping. If >50%, gates are too strict — consider relaxing P2/P3 to no-gate tier.

**Implementation:** Append to `$HOME/.clavain/telemetry.jsonl` (local only, no network). One JSON line per event.

## Open Questions

1. **Should `/lfg` auto-create beads for orphaned artifacts?** Leaning yes with user confirmation via AskUserQuestion.
2. ~~**Multi-feature PRDs:**~~ **Resolved:** PRD artifacts have no phase header. Plans/brainstorms have phase headers. PRD is shared across child beads; each child tracks its own phase independently.
3. **Retrospective backfill:** One-time migration script infers phases from artifact existence for ~10 existing beads. User reviews output before applying.
