# Plan: M1 Work Discovery — F3 Orphaned Artifact Detection + F4 Session-Start Light Scan

**Bead:** Clavain-tayp (epic), Clavain-ur4f (F3), Clavain-89m5 (F4)
**Phase:** executing (as of 2026-02-13T19:51:30Z)
**PRD:** docs/prds/2026-02-12-phase-gated-lfg.md
**Date:** 2026-02-13

## Context

M1 Work Discovery is 5/8 features complete. F1 (beads scanner), F2 (AskUserQuestion UI), F5 (phase tracking), F6 (gate library), and A3HP are shipped. Two features remain for M1:

- **F3: Orphaned Artifact Detection** — scan docs/ for artifacts not linked to any bead
- **F4: Session-Start Light Scan** — 1-2 line work state summary in session-start hook

Both features live in **interphase** (the companion plugin at `/root/projects/interphase/`), not in Clavain directly. Clavain's `hooks/lib-discovery.sh` is a shim that delegates to interphase.

## Implementation Plan

### Task 1: F3 — Orphaned Artifact Detection in interphase

**File:** `/root/projects/interphase/hooks/lib-discovery.sh`

Add `discovery_scan_orphans()` function that:

- [ ] 1.1. Scan `docs/brainstorms/`, `docs/prds/`, `docs/plans/` for all `.md` files
- [ ] 1.2. For each file, grep for `Bead` header pattern (same regex as `infer_bead_action`)
- [ ] 1.3. If no bead ID found → artifact is **unlinked** (potential orphan)
- [ ] 1.4. If bead ID found but `bd show <id>` fails → bead was deleted (orphan)
- [ ] 1.5. If bead ID found and bead status is `closed` → **not orphan** (completed work)
- [ ] 1.6. Return JSON array: `[{path, type: "brainstorm|prd|plan", title, suggested_action: "create_bead"}]`
- [ ] 1.7. Title extracted from first `# ` heading in the file

**Integration point:** Modify `discovery_scan_beads()` to call `discovery_scan_orphans()` and append synthetic entries to the results array with `action: "create_bead"`, `id: null`, `priority: 3`.

### Task 2: F3 — Update Clavain's /lfg routing for orphans

**File:** `/root/projects/Clavain/commands/lfg.md` (the /lfg skill content loaded at session start)

- [ ] 2.1. Add handling for `action: "create_bead"` in discovery routing (step 6)
- [ ] 2.2. When user selects an orphan: prompt "Create a bead for this artifact?" via AskUserQuestion
- [ ] 2.3. If yes: `bd create --title="<artifact title>" --type=task --priority=3` then link bead to artifact by inserting `**Bead:** <new-id>` header
- [ ] 2.4. Then route to appropriate next step based on artifact type (brainstorm→strategize, prd→plan, plan→execute)

### Task 3: F4 — Session-Start Light Scan in interphase

**File:** `/root/projects/interphase/hooks/lib-discovery.sh`

Add `discovery_brief_scan()` function that:

- [ ] 3.1. Check 60-second TTL cache at `/tmp/clavain-discovery-brief-${DISCOVERY_PROJECT_DIR//\//_}.cache`
- [ ] 3.2. If cache fresh → read and return cached result
- [ ] 3.3. If cache stale → run `bd list --status=open --json 2>/dev/null` (lightweight, no filesystem scan)
- [ ] 3.4. Count open beads, count in_progress beads, find highest-priority item
- [ ] 3.5. Output 1-2 line summary: `"5 open beads (2 in-progress). Top: Execute plan for Clavain-6czs — F1 (P2)"`
- [ ] 3.6. Write to cache file with timestamp
- [ ] 3.7. If bd unavailable → output nothing (silent no-op)

### Task 4: F4 — Wire into Clavain's session-start.sh

**File:** `/root/projects/Clavain/hooks/session-start.sh`

- [ ] 4.1. After sprint_brief_scan (line ~115), source lib-discovery.sh shim and call `discovery_brief_scan`
- [ ] 4.2. Append result to sprint signals (same format: `"• <summary>\n"`)
- [ ] 4.3. Guard: if interphase not available (shim returns nothing), skip silently
- [ ] 4.4. Budget: must add <200ms to session startup (cached path is stat + cat, ~5ms)

### Task 5: Tests

- [ ] 5.1. Add bats tests for `discovery_scan_orphans()` in interphase — test with fixture files (unlinked, deleted bead, closed bead, valid bead)
- [ ] 5.2. Add bats tests for `discovery_brief_scan()` in interphase — test cache TTL, bd unavailable, empty beads
- [ ] 5.3. Add bats test in Clavain for session-start.sh integration — mock interphase available/unavailable
- [ ] 5.4. Update structural test counts if needed (verify 29/17/37 still correct — no new skills/agents/commands)

### Task 6: Version bump + publish both plugins

- [ ] 6.1. Bump interphase version, commit, push, publish
- [ ] 6.2. Bump Clavain version, commit, push, publish
- [ ] 6.3. Close Clavain-ur4f (F3) and Clavain-89m5 (F4)

## Execution Order

Tasks 1→2 (F3 complete), Tasks 3→4 (F4 complete), Task 5 (tests), Task 6 (ship).

Tasks 1+3 are independent (different functions in same file) but I'll do them sequentially to avoid merge conflicts in lib-discovery.sh.

## Risks

1. **interphase plugin cache may not be fresh** — Clavain's shim discovers interphase at runtime. If interphase is updated but cache is stale, new functions won't be found. Mitigation: bump-version.sh handles symlinks.
2. **bd list performance on large .beads** — F4 queries bd on every session start. Mitigation: 60s TTL cache, bd list is <50ms even with 100+ beads.
3. **Orphan false positives** — artifacts might reference beads in non-standard format. Mitigation: regex pattern matches `Bead.*<id>` which covers `**Bead:** <id>`, `Bead: <id>`, and `<!-- Bead: <id> -->`.
