---
agent: fd-architecture
tier: plugin
reviewed: 2026-02-12
status: complete
---

# Phase-Gated /lfg Architecture Review

## Executive Summary

The proposed phase-gated /lfg evolution introduces **two architectural changes on different risk tiers**:

1. **Low-risk, high-value:** Work Discovery Mode — scan beads/artifacts, rank by maturity, present via AskUserQuestion
2. **High-risk, high-coupling:** Phase gates with beads state tracking — hard gates between 9 phases enforced via `bd set-state`

The phase-gate design has **structural integrity issues** that require addressing before implementation. Work discovery is architecturally sound and can proceed independently.

**Gate result:** CONDITIONAL PASS — Work discovery approved, phase gates require architectural revision.

---

## 1. State Machine Design

### Finding: 9-phase model has unclear state transitions and missing error states

**Severity:** P1

The proposed 9-phase linear model treats workflow as a pipeline with reversible state:

```
brainstorm → brainstorm-reviewed → strategized → planned →
plan-reviewed → executing → tested → shipping → done
```

**Issues:**

1. **No error recovery states.** What phase does a bead enter when:
   - flux-drive review finds P0 issues? Does it revert to the pre-review phase?
   - Quality gates fail? Does `shipping → executing` or stay `shipping`?
   - Tests fail during execution? Does `executing → planned` to re-plan?

2. **Phase reversion is ambiguous.** The brainstorm mentions "gate blocked" messages suggesting linear progression, but real workflows have cycles:
   - User rewrites plan after review → should phase stay `plan-reviewed` or revert to `planned`?
   - Code changes after quality gates → should phase revert to `executing`?

3. **`tested` and `executing` overlap semantically.** Both cover code-writing. The distinction between "code complete" (tested) and "writing code" (executing) is fuzzy when test failures force code rewrites.

4. **Missing terminal states.** No representation for:
   - Abandoned work (brainstorm rejected, feature deprioritized)
   - Blocked permanently (dependency cancelled, tech constraint discovered)
   - Split/merged (bead decomposed into sub-beads, or absorbed by parent)

**Recommendation:**

Replace linear 9-phase pipeline with a **3-layer state model**:

**Layer 1: Macro phase** (always moves forward, never reverts)
- `discovery` — brainstorming, exploring
- `design` — PRD/plan writing
- `implementation` — code/tests
- `validation` — review/quality-gates
- `terminal` — done/abandoned/absorbed

**Layer 2: Micro status** (can cycle within macro phase)
- `draft` — artifact being written
- `review-pending` — submitted to flux-drive
- `revision-needed` — review found issues
- `approved` — review passed, ready for next macro phase

**Layer 3: Artifact linkage** (orthogonal to phase)
- Links to brainstorm, PRD, plan, review dirs, commit ranges

**Storage:**
```bash
bd set-state <id> macro=implementation
bd set-state <id> micro=revision-needed
bd update <id> --notes "Plan: docs/plans/2026-02-12-foo.md"
```

**Benefits:**
- Macro phase never reverts → progression is always forward
- Micro status handles review cycles without confusing phase semantics
- Clear distinction between "what stage of the workflow" (macro) vs "what's the current blocker" (micro)
- Terminal states are explicit

**Cost:** More complex, requires two state dimensions instead of one. Counter-argument: simpler than trying to encode all workflow nuance into 9 phases.

---

## 2. Beads Coupling

### Finding: Design assumes beads infallibility creates brittleness

**Severity:** P1

The brainstorm states: "Beads provides cross-session persistence that in-memory TaskCreate can't" and "Every Clavain project already has `.beads/`". The design makes beads **mandatory** for workflow state, but does not handle:

1. **`bd` command failures mid-gate-check.** Example scenario:
   ```
   /clavain:strategy completes, writes PRD
   → Calls bd set-state <id> phase=strategized
   → bd command fails (dolt lock conflict, network timeout, db corruption)
   → PRD exists, but bead phase is stuck at "brainstorm-reviewed"
   → Next /clavain:write-plan run → gate check reads stale phase → blocks incorrectly
   ```

2. **Beads database unavailable during session.** If `.beads/dolt/` is corrupt and `bd doctor --fix` fails, the entire /lfg pipeline is blocked. The design has no graceful degradation.

3. **Orphaned artifacts when bead creation fails.** If `/clavain:strategy` writes the PRD but `bd create` fails, the PRD becomes an orphaned artifact. Work discovery will flag it, but the phase-gate logic has no recovery path.

4. **Concurrent phase updates.** Two Claude sessions working on the same bead (one executing, one reviewing) could race on `bd set-state` calls. Beads state changes are atomic, but the **orchestrator logic** reading phase → checking gate → advancing phase is not. This can cause:
   - Session A reads `phase=planned`, starts execution
   - Session B reads `phase=planned`, also starts execution
   - Both sessions call `bd set-state phase=executing` → last write wins
   - No detection of duplicate work

**Recommendation:**

**Option A: Make beads optional for phase tracking** (lower coupling)

Gate checks fall back to artifact-based inference when beads is unavailable:
```
phase = bd state <id> phase || infer_phase_from_artifacts(bead_id)

infer_phase_from_artifacts(id):
  if flux-drive review dir exists → "brainstorm-reviewed" or higher
  if PRD references this bead → "strategized" or higher
  if plan references this bead → "planned" or higher
  if git commits reference this bead → "executing" or higher
  if quality-gates review exists → "shipping" or higher
  if bead is closed → "done"
```

**Pros:** Resilient to beads failures. Supports recovery from incomplete state transitions.

**Cons:** Artifact-based inference is heuristic and can be wrong (e.g., user deletes PRD, phase inference regresses).

**Option B: Add phase checkpoints to artifacts** (dual persistence)

Every command that advances phase writes phase metadata to the artifact:
```markdown
# Feature Implementation Plan

**Bead:** Clavain-abc
**Phase:** planned (as of 2026-02-12T14:30Z)
**PRD:** docs/prds/2026-02-12-foo.md
```

Gate checks read from bead first, fall back to artifact:
```
phase = bd state <id> phase || extract_phase_from_artifact(bead_id)
```

**Pros:** Dual persistence. Beads failure doesn't block workflow. Artifacts become self-documenting.

**Cons:** Redundant state. Possible desync if one update succeeds and the other fails.

**Option C: Add error handling to every bd call** (current design + safety)

Wrap every `bd set-state` call:
```bash
if ! bd set-state <id> phase=strategized --reason "..."; then
  echo "⚠️  Phase update failed — proceeding anyway. Run 'bd set-state <id> phase=strategized' manually."
fi
```

**Pros:** Minimal change to current design.

**Cons:** Doesn't solve the problem — just logs it. User must manually fix desync.

**Verdict:** Recommend **Option B** (dual persistence). Artifacts already link to beads, adding phase metadata is low-cost and makes the system resilient to beads outages.

---

## 3. Integration Surface

### Finding: 7-component refactor is manageable but requires staged rollout

**Severity:** P2

The design touches:
1. `/clavain:lfg` — add work discovery mode + gate checks
2. `/clavain:strategy` — add phase advancement to `strategized`
3. `/clavain:write-plan` — add gate check for `strategized`, advance to `planned`
4. `/clavain:work` — add gate check for `plan-reviewed`, advance to `executing`
5. `/clavain:quality-gates` — add gate check for `executing`, advance to `shipping`
6. `/clavain:resolve` — add phase advancement to `done` on close
7. `hooks/session-start.sh` — integrate sprint-scan with phase-aware recommendations

**Blast radius:** All 7 components must change atomically for phase gates to work. If `/strategy` advances phase but `/write-plan` doesn't check it yet, gates are bypassed.

**Recommendation:**

**Staged rollout plan:**

**Stage 0: Add beads state tracking (no enforcement)**
- Add `bd set-state <id> phase=<value>` calls to all commands
- Do NOT check phase before proceeding (no gates yet)
- This populates phase labels on existing beads so later stages have data

**Stage 1: Add work discovery (independent feature)**
- Implement `/lfg` with no args → scan beads/artifacts, rank, present
- No dependency on phase gates
- Can ship immediately, high value

**Stage 2: Add artifact phase checkpoints (resilience)**
- Modify plan/PRD templates to include phase metadata
- Update commands to write phase to artifacts when updating beads
- Dual persistence layer is now active

**Stage 3: Soft gates (warnings only)**
- Add gate checks to all commands
- Print warnings when phase is wrong, but proceed anyway
- Allows testing gate logic without blocking users

**Stage 4: Hard gates (enforcement)**
- Convert warnings to blocks
- Add `--skip-gate` override flag
- Full phase-gated workflow is now active

**Stage 5: Session-start integration**
- Enhance sprint-scan to surface phase-based recommendations
- Example: "Clavain-abc (P1) is in phase 'planned' — needs flux-drive review before execution"

**Benefits:**
- Each stage delivers value independently
- Rollback risk is isolated to one stage at a time
- User adoption is gradual (no big-bang behavior change)

**Cost:** 5 stages instead of 1 atomic release. Estimate: 1-2 days per stage → 1-2 week total delivery.

---

## 4. Artifact-to-Bead Linking

### Finding: Markdown header pattern is fragile, alternatives exist

**Severity:** P2

The design uses markdown header extraction to link artifacts to beads:

```markdown
**Bead:** Clavain-abc
```

**Issues:**

1. **Typos break the link.** `**Bead:** Clavain-abc` vs `**Bead**: Clavain-abc` (missing space) vs `Bead: Clavain-abc` (missing bold) → discovery scan misses the link.

2. **No enforcement.** Nothing prevents a user or agent from writing a plan without the header. The artifact becomes orphaned.

3. **Multi-bead plans are ambiguous.** If a plan has multiple `**Bead:**` headers (one per feature), which one is the "primary" bead for phase tracking?

**Alternatives:**

**Option A: Frontmatter** (structured metadata)
```yaml
---
bead: Clavain-abc
phase: planned
prd: docs/prds/2026-02-12-foo.md
---
```

**Pros:** Parseable with `yq` or any YAML parser. Enforces structure. Can include phase checkpoint.

**Cons:** Adds tooling dependency. Not all markdown renderers show frontmatter nicely.

**Option B: Git notes** (metadata outside the file)
```bash
git notes --ref=beads add -m "bead=Clavain-abc phase=planned" <commit-sha>
```

**Pros:** Metadata is in git, not file content. No markdown pollution. Survives file renames.

**Cons:** Git notes are rare in practice, easy to lose during force-pushes. Not visible in file diffs.

**Option C: Reverse index** (beads stores artifact paths)
```bash
bd update <id> --notes "Plan: docs/plans/2026-02-12-foo.md"
bd update <id> --notes "PRD: docs/prds/2026-02-12-foo.md"
```

Work discovery queries beads, not artifacts:
```bash
bd list --notes-contains "docs/plans/"  # Find all beads with plans
```

**Pros:** Single source of truth (beads). No markdown pattern matching. Supports multiple artifacts per bead.

**Cons:** Requires beads to be the index. Doesn't work if beads is unavailable.

**Option D: Current design + linting** (enforce the pattern)

Add a pre-commit hook or test that verifies:
- All files in `docs/plans/` have `**Bead:** <id>` header
- All files in `docs/prds/` have `**Bead:** <id>` header
- Bead ID format matches `Clavain-[a-z0-9]+`

**Pros:** Simplest. No new tech. Catches 90% of errors.

**Cons:** Doesn't prevent the issue, just detects it late.

**Recommendation:**

Use **Option C** (reverse index) as the primary linkage, with **Option D** (linting) as a backup. This gives:
- Beads notes store `Plan: <path>`, queryable via `bd list --notes-contains`
- Markdown header `**Bead:** <id>` is still required for human readability
- Linter validates that header matches the bead's notes
- Work discovery queries beads first, falls back to markdown pattern matching if beads is unavailable

**Rationale:** Beads is already the authoritative workflow state. Making it the index for artifact paths is consistent with that responsibility.

---

## 5. Phase Transition Logic

### Finding: Multiple edge cases unhandled

**Severity:** P1

**Edge case 1: Bead has no phase label**

Scenario: User creates a bead manually (`bd create`), doesn't set phase. Later runs `/clavain:write-plan`.

Current design: Gate check reads `bd state <id> phase` → empty → blocks? allows? undefined.

**Fix:** Treat missing phase as `entry` (the bead's entry point). Commands should set phase on first touch if missing:
```bash
current_phase=$(bd state <id> phase || echo "")
if [[ -z "$current_phase" ]]; then
  bd set-state <id> phase=planned --reason "First command: write-plan"
fi
```

**Edge case 2: Bead was closed and reopened**

Scenario: Bead Clavain-abc reaches `done`, gets closed. User discovers a bug, reopens it (`bd reopen <id>`). What phase should it be?

Current design: Phase label persists after close. Reopened bead is still `phase=done`, which breaks gate logic.

**Fix:** `bd reopen` should reset phase to the last pre-done phase (stored in event history), or prompt user:
```
Reopening Clavain-abc. What phase should it enter?
  1. executing (fix code)
  2. planned (re-plan)
  3. brainstorm (rethink approach)
```

Requires enhancing `bd reopen` command (out of scope for Clavain plugin). Workaround: document that users must manually reset phase after reopen.

**Edge case 3: Multiple beads share an artifact**

Scenario: PRD describes F1, F2, F3. `/clavain:strategy` creates 3 beads (Clavain-a, Clavain-b, Clavain-c), all referencing the same PRD. Brainstorm asks: "Should the PRD bead be an epic with child feature beads?"

Current design: Artifact header can only list one `**Bead:**`. Multi-bead PRDs are ambiguous.

**Fix:** Use YAML frontmatter for multi-bead artifacts:
```yaml
---
beads:
  - Clavain-a (F1)
  - Clavain-b (F2)
  - Clavain-c (F3)
epic: Clavain-abc
---
```

Work discovery aggregates phase across all linked beads. Example: "PRD has 3 features — 1 executing, 2 planned."

**Edge case 4: Plan exists but flux-drive review is stale**

Brainstorm mentions: "Should phase gates check for flux-drive review of the *specific* artifact, or any review?" and leans toward "review must be newer than artifact modification date."

**Issue:** This requires timestamp comparison:
```bash
plan_mtime=$(stat -c %Y docs/plans/2026-02-12-foo.md)
review_mtime=$(stat -c %Y docs/research/flux-drive/2026-02-12-foo/fd-architecture.md)
if [[ $review_mtime -lt $plan_mtime ]]; then
  echo "Plan was modified after review — review is stale"
fi
```

**Problem:** If user runs `touch docs/plans/foo.md` (updates mtime without content change), the review becomes stale even though content didn't change.

**Better fix:** Check git log for commits touching the plan since the review:
```bash
review_date="2026-02-12T14:30Z"  # extracted from review file frontmatter
commits_since=$(git log --since="$review_date" --oneline -- docs/plans/foo.md)
if [[ -n "$commits_since" ]]; then
  echo "Plan has commits since review — review may be stale"
fi
```

**Recommendation:** Use git log approach. Requires review files to have `reviewed: YYYY-MM-DDTHH:MM:SSZ` in frontmatter (flux-drive agents already do this).

**Edge case 5: User runs commands out of order (bypasses gates)**

Scenario: User runs `/clavain:work` directly without prior `/clavain:strategy` or `/clavain:write-plan`. Bead has no phase label. Gate check blocks.

Current design: "Gate blocked" message tells user to run prior commands. But if user creates the plan manually (not via `/write-plan`), they're stuck.

**Fix:** Add `--bootstrap` flag to commands:
```
/clavain:work --bootstrap
→ Detects bead has no phase, no plan artifact
→ Prompts: "No plan found. Should I create one? (y/n)"
→ If yes, runs /write-plan inline
→ If no, exits
```

This supports both "happy path" (user follows pipeline) and "escape hatch" (user enters mid-pipeline).

**Summary of fixes needed:**

| Edge case | Fix | Complexity |
|-----------|-----|------------|
| No phase label | Set phase on first touch | Low |
| Closed + reopened | Document manual reset (or enhance bd) | Medium |
| Multi-bead artifacts | YAML frontmatter | Medium |
| Stale review | Git log timestamp check | Medium |
| Out-of-order commands | --bootstrap flag | High |

**Recommendation:** Implement all except "closed+reopened" (document workaround instead). Bootstrap flag is optional but highly valuable for UX.

---

## 6. Boundary Analysis

### Finding: Work discovery and phase gates are orthogonal — can ship separately

**Severity:** P0 (design clarification, not a flaw)

The brainstorm treats work discovery and phase gates as a single feature ("Phase-Gated /lfg with Work Discovery"). Architecturally, they are **independent**:

**Work discovery:**
- Input: beads state, artifact filesystem
- Output: ranked list of recommended next actions
- Dependencies: beads (for priority/status), filesystem scan (for orphaned artifacts)
- No dependency on phase gates

**Phase gates:**
- Input: bead phase label, artifact timestamps, review results
- Output: allow/block command execution
- Dependencies: beads state tracking, flux-drive review results
- No dependency on work discovery

**Recommendation:** Treat as two features with independent milestones:

**Milestone 1: Work Discovery** (can ship now)
- `/lfg` with no args scans beads + artifacts
- Ranks by priority, recency, staleness
- Presents top 3-5 options via AskUserQuestion
- No phase tracking required (uses existing status/priority)

**Milestone 2: Phase Gates** (requires staged rollout per Section 3)
- Add beads state tracking to all commands
- Add artifact phase checkpoints
- Enable gate checks with `--skip-gate` override
- Integrate with work discovery (phase becomes a ranking signal)

**Value:** Milestone 1 delivers immediate value (work triage) without the complexity/risk of phase gates. Milestone 2 can proceed after user validation of Milestone 1.

---

## 7. Coupling to External Systems

### Finding: Session-start hook integration adds startup latency

**Severity:** P3

The brainstorm proposes enhancing `session-start.sh` with:

```
Companions detected:
- beads: 5 open issues, 2 ready to advance
  → Clavain-abc (P1) needs plan review — run /lfg to continue
```

This requires querying beads at session start:
```bash
bd list --status=open --label-pattern "phase:*" | wc -l  # Count open beads
bd list --status=open --label="phase:planned" | head -1  # Find next to advance
```

**Performance impact:**
- `bd list` is typically <100ms for small repos (<100 beads)
- Can reach 500ms+ for large repos (>1000 beads) if Dolt backend is slow
- Runs on every Claude Code session start → user perceives it as "Claude is slow to start"

**Recommendation:**

**Option A: Async background scan** (no startup delay)
```bash
# session-start.sh launches scan in background
(sleep 2 && sprint_brief_scan > /tmp/clavain-sprint-status.txt) &
```

User gets immediate session start. Sprint status appears as an additionalContext update 2 seconds later (if Claude Code supports streaming context injection — unclear).

**Option B: Cache with TTL** (1-minute freshness)
```bash
CACHE_FILE="/tmp/clavain-sprint-status-$(pwd | md5sum | cut -c1-8).txt"
CACHE_AGE=$(( $(date +%s) - $(stat -c %Y "$CACHE_FILE" 2>/dev/null || echo 0) ))
if [[ $CACHE_AGE -lt 60 ]]; then
  cat "$CACHE_FILE"
else
  sprint_brief_scan | tee "$CACHE_FILE"
fi
```

First session start pays the cost. Subsequent starts within 1 minute use cached result.

**Option C: Only show HANDOFF.md warning** (minimal scan)
```bash
if [[ -f HANDOFF.md ]]; then
  echo "HANDOFF.md found — previous session left unfinished work."
fi
```

Skip beads query entirely. User runs `/sprint-status` manually when they want the full scan.

**Verdict:** Recommend **Option B** (cache with 60s TTL). Balances freshness with performance. For large repos, consider increasing TTL to 5 minutes.

---

## 8. Missing Abstractions

### Finding: Gate check logic will be duplicated across 5 commands

**Severity:** P2

Each command (`/strategy`, `/write-plan`, `/work`, `/quality-gates`, `/resolve`) must implement:

1. Read bead phase
2. Check if current phase is a valid predecessor of target phase
3. Check if artifact exists (PRD, plan, review)
4. Check if review has P0 findings
5. Advance phase if all gates pass

**Without abstraction, this is ~30 lines of bash per command × 5 commands = 150 lines of duplicated logic.**

**Recommendation:**

Extract gate check into a shared library:

**`hooks/lib-gates.sh`:**
```bash
# check_phase_gate <bead-id> <required-phase> <target-phase> <artifact-check-fn>
# Returns 0 if gate passes, 1 if blocked, prints error message on failure
check_phase_gate() {
  local bead_id="$1"
  local required_phase="$2"
  local target_phase="$3"
  local artifact_check_fn="$4"

  local current_phase
  current_phase=$(bd state "$bead_id" phase 2>/dev/null || echo "")

  if [[ -z "$current_phase" ]]; then
    bd set-state "$bead_id" phase="$target_phase" --reason "First touch"
    return 0
  fi

  if [[ "$current_phase" != "$required_phase" ]]; then
    echo "⛔ Gate blocked: $bead_id is in phase '$current_phase', needs '$required_phase'"
    return 1
  fi

  if ! "$artifact_check_fn" "$bead_id"; then
    echo "⛔ Artifact check failed"
    return 1
  fi

  return 0
}

# advance_phase <bead-id> <new-phase> <reason>
advance_phase() {
  bd set-state "$1" phase="$2" --reason "$3"
  # Also update artifact if it exists (dual persistence)
  update_artifact_phase "$1" "$2"
}
```

**Usage in `/clavain:strategy`:**
```bash
source hooks/lib-gates.sh

check_flux_review() {
  local bead_id="$1"
  # Check if flux-drive review exists for brainstorm
  [[ -d "docs/research/flux-drive/<topic>/" ]] || return 1
  # Check for P0 findings
  ! grep -r "severity: P0" "docs/research/flux-drive/<topic>/" || return 1
}

if check_phase_gate "$bead_id" "brainstorm-reviewed" "strategized" check_flux_review; then
  # Write PRD
  advance_phase "$bead_id" "strategized" "PRD: docs/prds/2026-02-12-foo.md"
fi
```

**Benefits:**
- Gate logic is centralized (one place to fix bugs)
- Commands are 5 lines instead of 30
- Consistent error messages across all commands

**Cost:** Adds another library file. Bash functions are harder to test than command-line tools.

---

## 9. Recommendations Summary

### Must-fix before implementation (P0/P1)

1. **Revise state model** (Section 1) — Replace 9-phase linear pipeline with 3-layer model (macro phase, micro status, artifact links). This fixes state reversion ambiguity and adds error recovery states.

2. **Add dual persistence** (Section 2) — Write phase metadata to artifacts (plans/PRDs) in addition to beads labels. Prevents total workflow blockage if beads is unavailable.

3. **Add gate check library** (Section 8) — Extract shared logic into `hooks/lib-gates.sh` to prevent duplication across 5 commands.

4. **Handle edge cases** (Section 5) — Implement fixes for: missing phase labels, multi-bead artifacts, stale reviews, out-of-order commands.

5. **Stage rollout** (Section 3) — Do NOT ship phase gates atomically. Use 5-stage plan: state tracking → work discovery → dual persistence → soft gates → hard gates.

### Should-fix for production quality (P2)

6. **Use reverse index for artifacts** (Section 4) — Store artifact paths in beads notes, query via `bd list --notes-contains`. Add linting to validate markdown headers match notes.

7. **Cache session-start scan** (Section 7) — Add 60-second TTL cache to avoid beads query latency on every session start.

### Consider for future iterations (P3)

8. **Ship work discovery first** (Section 6) — It's independent of phase gates and delivers immediate value. Phase gates can follow in a later release.

9. **Add --bootstrap flag** (Section 5) — Allows users to enter workflow mid-pipeline without being blocked by gates.

---

## 10. Architectural Integrity

### Boundary violations: None detected

The design respects existing boundaries:
- Beads is workflow state
- Flux-drive is review orchestration
- Commands are workflow steps
- Session-start is environment detection

No new god-modules or hidden coupling.

### Abstraction leaks: One detected

**Leak:** Commands must know the full phase transition graph to validate gates. Example: `/write-plan` must know that valid predecessors of `planned` are `strategized` and `brainstorm-reviewed`. This leaks workflow semantics into every command.

**Fix:** Centralize the phase transition graph in `hooks/lib-gates.sh`:
```bash
VALID_TRANSITIONS=(
  "brainstorm→brainstorm-reviewed"
  "brainstorm-reviewed→strategized"
  "strategized→planned"
  "planned→plan-reviewed"
  "plan-reviewed→executing"
  "executing→tested"
  "tested→shipping"
  "shipping→done"
)

is_valid_transition() {
  local from="$1"
  local to="$2"
  for transition in "${VALID_TRANSITIONS[@]}"; do
    [[ "$transition" == "$from→$to" ]] && return 0
  done
  return 1
}
```

Commands call `is_valid_transition "$current" "$target"` instead of hardcoding the graph.

### Naming consistency: Good

Proposed names align with existing Clavain conventions:
- Commands: `/clavain:lfg`, `/clavain:strategy`, `/clavain:work`
- Skills: `clavain:writing-plans`, `clavain:executing-plans`
- Hooks: `session-start.sh`, `sprint-scan.sh`
- State dimensions: `phase`, `macro`, `micro` (if 3-layer model adopted)

No naming drift detected.

---

## 11. Complexity Assessment

**Current /lfg complexity:** Low
- 9 steps, each a command invocation
- No state tracking beyond TaskCreate
- Linear execution, no branching

**Proposed /lfg complexity:** Medium-High
- Work discovery: scan 3 sources (beads, artifacts, filesystem), rank, present
- Phase gates: 5 commands × gate check logic × artifact validation × phase advancement
- Error recovery: handle 5 edge cases (Section 5)
- Dual persistence: sync beads state ↔ artifact metadata

**Complexity drivers:**
1. State synchronization (beads labels + artifact frontmatter)
2. Gate check logic duplication (mitigated by shared library)
3. Artifact-to-bead linking (pattern matching + reverse index)
4. Timestamp validation (git log queries for stale review detection)

**Justification:**

The complexity is **proportional to the problem**: workflow state tracking across sessions, multiple artifacts, and review cycles is inherently complex. The design does not introduce accidental complexity (no over-abstraction, no speculative features).

**YAGNI check:** Are all 9 phases necessary?
- `brainstorm-reviewed` — YES (flux-drive review is critical before strategy)
- `strategized` — YES (PRD is a distinct artifact from plan)
- `planned` — YES (plan exists, not yet reviewed)
- `plan-reviewed` — YES (gates execution on review passing)
- `executing` — YES (code is being written)
- `tested` — MAYBE (can merge with `executing` — "code complete" is fuzzy)
- `shipping` — YES (quality gates passed, resolving findings)
- `done` — YES (terminal state)

**Recommendation:** Merge `tested` into `executing`. Use micro status to differentiate:
- `macro=implementation, micro=draft` → writing code
- `macro=implementation, micro=tests-passing` → code complete
- `macro=validation` → quality gates

This reduces 9 phases to 7 macro phases (or 5 if using the 3-layer model from Section 1).

---

## 12. Alternatives Considered

The brainstorm does not present alternatives to the phase-gate approach. Here are three:

### Alternative A: Checklist-based gates (no beads state)

Each command checks for artifact existence and quality-gate markers:
```markdown
# PRD: Foo

**Gates:**
- [x] Brainstorm flux-drive review passed
- [ ] Strategy flux-drive review passed
- [ ] Plan flux-drive review passed
```

Commands read the markdown checklist, advance when prior step is checked.

**Pros:** No beads dependency. Simpler. Self-documenting.

**Cons:** Checklist can desync from actual state (user checks box manually). No cross-session persistence (checklist is per-artifact, not per-bead).

### Alternative B: Git tags for phase tracking

Tag commits with workflow phase:
```bash
git tag workflow/Clavain-abc/strategized <commit-sha>
git tag workflow/Clavain-abc/planned <commit-sha>
```

Commands query tags to determine current phase.

**Pros:** Uses git (no external state). Immutable audit trail. Survives force-pushes (tags can be re-pushed).

**Cons:** Git tags are global, not per-bead (pollutes tag namespace). Hard to query ("what phase is Clavain-abc in?" requires parsing all tags).

### Alternative C: No gates, just recommendations

Work discovery recommends next actions, but doesn't block:
```
/lfg
→ "Clavain-abc (P1) has a plan but no review. Recommend: /flux-drive <plan>"
→ User can still run /work directly (no enforcement)
```

**Pros:** Simplest. No state tracking. No gate logic.

**Cons:** No enforcement → users can skip reviews, leading to low-quality merges.

**Verdict:** The proposed phase-gate design is the right choice IF workflow discipline is critical (e.g., high-stakes production systems). For personal projects or prototyping, Alternative C (recommendations only) is sufficient.

---

## 13. Migration Path

Existing Clavain projects have ~10 open beads with no phase labels (per brainstorm). How to backfill?

### Option 1: Manual migration script

```bash
# For each open bead, infer phase from artifacts
for bead_id in $(bd list --status=open --json | jq -r '.[].id'); do
  phase=$(infer_phase_from_artifacts "$bead_id")
  bd set-state "$bead_id" phase="$phase" --reason "Backfill from artifacts"
done
```

**Pros:** Automated. Can run once per project.

**Cons:** Inference can be wrong. Requires careful validation.

### Option 2: Prompt user on first gate check

When a command encounters a bead with no phase:
```
Bead Clavain-abc has no phase label. What phase should it enter?
  1. brainstorm (exploring idea)
  2. strategized (PRD exists)
  3. planned (plan exists)
  4. executing (code in progress)
```

**Pros:** User validates phase. No risk of wrong inference.

**Cons:** Friction — user must answer for every bead. Doesn't scale to 10+ beads.

### Option 3: Start all beads at `brainstorm`

```bash
for bead_id in $(bd list --status=open --json | jq -r '.[].id'); do
  current_phase=$(bd state "$bead_id" phase || echo "")
  if [[ -z "$current_phase" ]]; then
    bd set-state "$bead_id" phase="brainstorm" --reason "Default for migration"
  fi
done
```

**Pros:** Safe. Beads advance through pipeline naturally as commands run.

**Cons:** Causes gate blocks for beads that are actually mid-pipeline (e.g., code already written but no plan artifact).

**Recommendation:** Use **Option 1** (automated inference) with manual review:
1. Run script to infer phases
2. Output a migration report: `<bead-id>: <inferred-phase> (artifacts: <list>)`
3. User reviews report, corrects any wrong inferences
4. Run `bd set-state` batch update

---

## 14. Final Verdict

**Architecture:** CONDITIONAL PASS

The phase-gate design is **structurally sound** but requires **4 critical fixes** before implementation:

1. Revise state model (9-phase → 3-layer)
2. Add dual persistence (beads + artifact metadata)
3. Extract gate check library (avoid duplication)
4. Handle edge cases (5 scenarios from Section 5)

**Work discovery** is architecturally independent and can ship immediately.

**Recommended approach:**
- Ship work discovery as Milestone 1 (low risk, high value)
- Refine phase-gate design based on this review
- Implement phase gates as Milestone 2 using the 5-stage rollout plan

**Estimated effort:**
- Work discovery: 1-2 days
- Phase gates (with fixes): 5-7 days (1-2 days per stage)
- Total: 6-9 days

**Risk assessment:**
- Work discovery: Low (no state tracking, no enforcement)
- Phase gates: Medium (complex state sync, edge cases, multi-component refactor)

**Bottom line:** The vision is good. The execution plan needs refinement. Address the P0/P1 findings, then proceed.
