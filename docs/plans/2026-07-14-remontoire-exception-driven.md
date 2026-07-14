---
artifact_type: plan
bead: Sylveste-2f8
stage: design
requirements:
  - F1: Canonical read-only attention projection
  - F2: Exception-only Claude and Codex startup context
  - F3: Evidence-backed promotion candidates in next-goal ranking
  - F4: No approval or execution authority in ambient paths
---
# Remontoire Exception-Driven Integration Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Bead:** `Sylveste-2f8`

**Goal:** Surface Remontoire only when a principal or operator must act, and make its ready promotion beads ordinary leverage-ranked next-goal candidates.

**Architecture:** Remontoire adds a read-only `attention --json` projection built from its canonical Intercore cycle state and Beads ready-work query. Clavain adds one pure shell classifier over that projection; Claude Code and Codex SessionStart hooks consume its hook output, while `next-goal` consumes its compact JSON. None of these consumers can call a mutating Remontoire operation.

**Tech Stack:** Go, Bash, jq, Claude Code hooks, Codex lifecycle hooks, Bats, pytest.

**Alignment:** The design sharpens attention, keeps mechanism ownership explicit, and improves the Remontoire-to-Clavain handoff without creating another source of truth.

**Conflict/Risk:** Startup network latency and hook trust are the main risks. The hook fails silent, has a bounded timeout, and never treats absence or transport failure as authority to act.

## Must-Haves

**Truths**
- A missing, idle, no-op, completed, or declined cycle produces no startup message.
- `awaiting_approval` produces an inspect-first principal decision message.
- `approved`, `executing`, `reviewing`, and `compounding` produce an explicit resume/recovery message, never an automatic resume.
- A failed cycle produces a receipt-replay or doctor recovery message.
- Ready `remontoire-promotion` beads join ordinary `next-goal` candidates and do not automatically outrank blockers or higher-priority work.
- Every ambient invocation is read-only and passes only `attention` to the Remontoire adapter.

**Artifacts**
- `../Remontoire/internal/app/app.go` exports the `attention` CLI command.
- `../Remontoire/internal/adapters/beads.go` exports the blocker-aware ready-promotion query.
- `scripts/remontoire-attention.sh` emits compact JSON or a SessionStart hook response.
- `hooks/hooks.json` registers the Claude Code SessionStart consumer.
- `scripts/install-codex.sh` installs and validates the Codex SessionStart consumer.
- `commands/next-goal.md` merges ready promotions before leverage ranking.

**Key Links**
- Remontoire `attention` reads Intercore and Beads but never calls its cycle service.
- Clavain's classifier invokes only `remontoire-operator.sh attention`.
- Both hook registrations execute the same classifier with a surface-specific command prefix.
- `next-goal` deduplicates promotion beads by ID before ranking.

## Task 1: Canonical Remontoire Attention Projection

**Files:**
- Modify: `../Remontoire/internal/adapters/beads.go`
- Modify: `../Remontoire/internal/adapters/beads_test.go`
- Modify: `../Remontoire/internal/app/app.go`
- Modify: `../Remontoire/internal/app/build.go`
- Modify: `../Remontoire/internal/app/cli_test.go`

1. Add failing adapter tests proving the ready query invokes `bd --sandbox ready --label=remontoire-promotion --limit=0 --json` and preserves leverage fields.
2. Add failing CLI tests proving `attention --json` returns the latest cycle and ready promotions without calling the cycle service.
3. Run the focused Go tests and confirm the missing API failures.
4. Implement the minimum read-only adapter and projection.
5. Run `gofmt`, focused tests, `go test ./...`, and `go vet ./...`.

<verify>
- run: `cd ../Remontoire && go test ./internal/adapters ./internal/app`
  expect: exit 0
- run: `cd ../Remontoire && go test ./... && go vet ./...`
  expect: exit 0
</verify>

## Task 2: Shared Clavain Attention Classifier

**Files:**
- Create: `scripts/remontoire-attention.sh`
- Modify: `scripts/remontoire-operator.sh`
- Create: `tests/shell/remontoire_attention.bats`
- Modify: `tests/structural/test_remontoire_facade.py`

1. Add failing Bats fixtures for every actionable and silent stage, malformed/unavailable projections, Claude/Codex command prefixes, and promotion compaction.
2. Add a failing facade test for the read-only `attention` operation.
3. Confirm the tests fail because the operation and classifier do not exist.
4. Implement the adapter mapping and pure classifier.
5. Assert through a logging fake that every classifier path invokes exactly `attention` and never `approve`, `decline`, `resume`, `cycle`, `shadow`, or `proposal`.

<verify>
- run: `bats tests/shell/remontoire_attention.bats`
  expect: exit 0
- run: `uv run --project tests pytest tests/structural/test_remontoire_facade.py -q`
  expect: exit 0
</verify>

## Task 3: Claude Code and Codex SessionStart Consumers

**Files:**
- Modify: `hooks/hooks.json`
- Modify: `tests/shell/hooks_json.bats`
- Modify: `scripts/install-codex.sh`
- Modify: `tests/shell/test_codex_installer.bats`
- Modify: `docs/README.codex.md`

1. Add failing tests for the Claude hook registration and for Codex install, update, doctor, preservation of unrelated hooks, and uninstall.
2. Confirm the hook and installer tests fail for the missing consumers.
3. Register the classifier as an asynchronous Claude SessionStart hook.
4. Merge one bounded Clavain SessionStart entry into `~/.codex/hooks.json`, preserving unrelated entries and requiring normal Codex hook trust review.
5. Update Codex documentation to replace the obsolete no-hooks claim.

<verify>
- run: `bats tests/shell/hooks_json.bats tests/shell/test_codex_installer.bats`
  expect: exit 0
</verify>

## Task 4: Promotion-Aware Next-Goal Ranking

**Files:**
- Modify: `commands/next-goal.md`
- Modify: `tests/structural/test_commands.py`

1. Add a failing structural contract requiring the attention helper, promotion deduplication, and explicit non-forcing leverage language.
2. Confirm the structural test fails.
3. Extend `next-goal` discovery to merge the helper's ready promotions with local `bd ready` results.
4. Rank promotion provenance as evidence, not as an override of priority, blockers, or dependent count.

<verify>
- run: `uv run --project tests pytest tests/structural/test_commands.py -q`
  expect: exit 0
</verify>

## Task 5: Integration, Installation, and Live Verification

**Files:**
- Modify: `README.md`
- Modify: `skills/remontoire/SKILL.md`
- Modify: `docs/README.codex.md`

1. Run all focused tests, Clavain structural tests, and Remontoire Go gates.
2. Push and deploy Remontoire first so the new read-only command exists on zklw.
3. Run a live zklw-backed `attention` query and verify its promotion list matches canonical `bd ready --label=remontoire-promotion` output.
4. Publish Clavain, install its Claude/Codex surfaces on the Mac, and complete Codex hook trust verification.
5. Verify a live completed/no-op cycle produces no hook output; verify fixtures cover every actionable state.
6. Close `Sylveste-2f8`, back up and push Beads, and verify both repositories are up to date with origin.

<verify>
- run: `bash tests/run-tests.sh`
  expect: exit 0
- run: `bash scripts/install-codex.sh doctor --json`
  expect: contains "\"status\":\"ok\""
- run: `bash scripts/remontoire-attention.sh --format=hook`
  expect: exit 0
</verify>
