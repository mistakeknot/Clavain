# F12 Clavain Integration Plan — Research Analysis

**Date:** 2026-02-14
**Scope:** Integration shims for the interlock companion plugin into Clavain
**Output:** `/root/projects/Clavain/docs/plans/2026-02-14-interlock-f12-clavain-integration.md`

---

## Files Analyzed

### Primary integration files (Clavain)
- `/root/projects/Clavain/hooks/lib.sh` — 4 existing discovery functions (lines 7-78), `escape_for_json` utility
- `/root/projects/Clavain/hooks/session-start.sh` — 169 lines, companion detection at lines 77-93
- `/root/projects/Clavain/commands/doctor.md` — 183 lines, checks 3b-3f cover companions + agent memory
- `/root/projects/Clavain/commands/setup.md` — 190 lines, 7 interagency-marketplace installs
- `/root/projects/Clavain/CLAUDE.md` — 42 lines, Overview lists 5 companions (missing interlock)

### Test files
- `/root/projects/Clavain/tests/shell/shims.bats` — 209 lines, tests for discovery + shim delegation
- `/root/projects/Clavain/tests/shell/lib.bats` — 49 lines, tests for `escape_for_json`
- `/root/projects/Clavain/tests/shell/test_helper.bash` — 29 lines, shared test setup

### Reference files
- `/root/projects/Clavain/docs/prds/2026-02-14-interlock-multi-agent-coordination.md` — F12 acceptance criteria
- `/root/projects/Clavain/docs/research/trace-integration-points.md` — Full companion wiring analysis
- `/root/projects/Clavain/docs/plans/2026-02-14-interlock-f1-circuit-breaker.md` — Plan format reference

---

## Key Findings

### 1. Doctor check numbering conflict
The PRD specifies "Doctor check 3f" for interlock, but 3f is already taken by "Agent Memory" (lines 86-113 of doctor.md). The plan uses **3g** instead to avoid renumbering the existing check. This is a deviation from the PRD's acceptance criteria text but not from its intent.

### 2. Marker file selection
The interlock plugin does not exist yet (`/root/projects/interlock/` does not exist on disk). The plan specifies `scripts/interlock-register.sh` as the discovery marker file based on the PRD's F7/F8 specifications (registration script). This parallels interpath's `scripts/interpath.sh` and interwatch's `scripts/interwatch.sh`. If interlock's file structure differs at creation time, the discovery function's `-path` glob must be updated.

### 3. No shim delegation needed
Unlike interphase (which requires `lib-discovery.sh` and `lib-gates.sh` shims that delegate function implementations), interlock requires only **detection** — not behavioral delegation. The interlock plugin will have its own SessionStart hook via its `hooks.json` that handles agent registration. Clavain's role is limited to: discover, report in session context, health-check in doctor, and list in setup.

### 4. Session-start ordering
The interlock detection block is placed after interwatch (line 93) and before the Clodex toggle detection (line 96). This maintains alphabetical order within the companion detection section (interflux, interpath, interwatch, interlock... though interlock breaks strict alpha, it follows the chronological addition order which is the existing convention).

### 5. CLAUDE.md was already incomplete
The trace analysis (section 10.1) noted that CLAUDE.md only listed 3 companions (missing interpath and interwatch). The current file actually lists 5 companions (it was updated since that analysis). Adding interlock makes it 6.

### 6. Test coverage is minimal but sufficient
Only 2 bats tests are needed (env var override + empty cache), matching the exact coverage level of the existing `_discover_beads_plugin` tests. The discovery function is mechanically identical to the 4 existing ones — the pattern is proven. No structural Python tests are needed since no new skills/commands/agents are added to Clavain.

---

## Plan Summary

4 tasks, 6 files modified, 2 new tests:

| Task | Files | Effort |
|------|-------|--------|
| 1. Discovery function | `hooks/lib.sh` | 5 min |
| 2. SessionStart delegation | `hooks/session-start.sh` | 5 min |
| 3. Doctor + setup + CLAUDE.md | `commands/doctor.md`, `commands/setup.md`, `CLAUDE.md` | 15 min |
| 4. Tests | `tests/shell/shims.bats` | 5 min |

Total estimated time: ~30 minutes.
