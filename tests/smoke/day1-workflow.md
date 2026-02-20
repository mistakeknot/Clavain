# Day-1 Workflow Smoke Test

> Validates the core sprint loop defined in clavain-vision.md:
> brainstorm → plan → review plan → execute → test → gates → ship
>
> **Target:** A new user completes this loop in <30 min for a simple fix.

## Prerequisites

- `ic` binary available in PATH (or built via `go build -o /tmp/ic ./cmd/ic`)
- Clavain plugin loaded (`--plugin-dir` or installed)
- `bd` available for bead tracking
- A test project with at least one Go or TypeScript file

## Automated Validation Script

Run from the Clavain repo root:

```bash
bash tests/smoke/test-day1-workflow.sh
```

## What the Script Tests

### Phase 1: Infrastructure (no Claude session needed)

1. **Sprint library loads** — `source hooks/lib-sprint.sh` without errors
2. **Complexity classification works** — `sprint_classify_complexity` returns valid labels
3. **Sprint CRUD** — create, read state, set artifact, record phase, claim/release
4. **Checkpoint round-trip** — write, read, validate, clear
5. **Gate enforcement** — `enforce_gate` returns correct pass/fail for each phase
6. **Phase advancement** — `advance_phase` records transitions correctly
7. **Auto-advance routing** — `sprint_advance` returns correct next steps

### Phase 2: Skill Presence (file checks)

8. **Required skills exist** — brainstorm, writing-plans, work, quality-gates, landing-a-change
9. **Required commands exist** — sprint, brainstorm, write-plan, work, quality-gates
10. **Sprint command references all phases** — grep for each phase name in sprint.md

### Phase 3: Integration (requires active Claude session)

11. **Sprint invocation** — `/sprint "add a version command"` produces a brainstorm
12. **Auto-advance** — sprint auto-advances through brainstorm → strategy → plan
13. **Gate enforcement** — plan review gate blocks execution until review passes
14. **Execution** — `/work` executes the plan with incremental commits
15. **Quality gates** — reviewer agents dispatch and produce findings
16. **Ship** — landing-a-change presents commit options

## Pass Criteria

- Phase 1-2: All 10 checks pass (automated, no Claude needed)
- Phase 3: Manual verification — all 6 steps complete in <30 min

## Phase 1-2 Test Script

The automated tests verify that the sprint infrastructure is correctly wired. Phase 3 requires a live Claude session and is documented as a manual checklist.
