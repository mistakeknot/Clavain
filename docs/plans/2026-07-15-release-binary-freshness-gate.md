---
artifact_type: plan
bead: sylveste-7bms
stage: design
---
# Release Binary Freshness Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Bead:** `sylveste-7bms`

**Goal:** Prevent `ic publish` from mutating plugin, marketplace, or cache state unless shipped release binaries are verified against the current plugin and Intercore revisions.

**Architecture:** Intercore's publish engine will recognize the existing `scripts/verify-release-binaries.sh` and `scripts/build-release.sh` convention. A normal version publish may rebuild stale artifacts inside the validation phase and include the resulting tracked files in the plugin commit; a sync-only publish cannot create an unversioned artifact commit and therefore fails closed when verification is stale. Every path performs a final verifier pass immediately before marketplace mutation. Clavain's PostToolUse hook delegates this responsibility exclusively to `ic publish` and no longer runs a best-effort builder or manual mutation fallback.

**Tech Stack:** Go, Git, Bash, pytest, Bats, Claude Code plugin cache.

**Prior Learnings:** `docs/solutions/integration-issues/stop-hooks-break-after-mid-session-publish-20260212.md` establishes that current-session hook paths depend on versioned caches, so the publish engine must preserve its existing compatibility-symlink lifecycle. Prior release work also established that source-only tests are insufficient: tracked platform binaries and their manifest are the completion boundary.

## Must-Haves

**Truths**
- A normal Clavain patch publish rebuilds binaries when either `cmd/clavain-cli` or the local Intercore revision has advanced.
- A release build or verification failure stops before the plugin version, marketplace entry, or cache is mutated.
- A sync-only publish with stale artifacts fails before marketplace mutation rather than creating an untracked corrective release commit.
- The plugin commit contains any artifacts produced by release preparation.
- A final verifier pass succeeds immediately before marketplace mutation.
- The PostToolUse hook cannot bypass the engine through best-effort builds or manual version/marketplace/cache edits.
- A freshly installed versioned cache passes `verify-release-binaries.sh` and contains binaries attested to the published source revisions.

**Artifacts**
- `core/intercore/internal/publish/release.go` owns the conventional release preparation and verification contract.
- `core/intercore/internal/publish/engine.go` invokes preparation during validation and verification before marketplace mutation.
- `core/intercore/internal/publish/release_test.go` reproduces stale artifact rebuild and failure behavior.
- `os/Clavain/hooks/auto-publish.sh` delegates publication without a mutation fallback.
- `os/Clavain/tests/structural/test_scripts.py` locks down the hook delegation boundary.

**Key Links**
- `ic publish` discovers a plugin, validates a clean worktree, prepares release artifacts, bumps and commits the plugin, verifies again, then updates marketplace and cache state.
- `scripts/build-release.sh` creates platform binaries transactionally and records exact Clavain and Intercore revisions in `bin/release-manifest.json`.
- `scripts/verify-release-binaries.sh` rejects source drift, Intercore revision drift, digest drift, and build-metadata drift.
- `hooks/auto-publish.sh` calls only `ic publish --auto`; Intercore owns all release mutations.

## Task 1: Intercore Release Contract Regressions

**Files:**
- Create: `core/intercore/internal/publish/release_test.go`
- Modify: `core/intercore/internal/publish/engine_test.go`

1. Add a failing test where a stale verifier causes a normal publish to invoke the builder, verify again, stage the rebuilt artifact, and finish with matching plugin and marketplace versions.
2. Add a failing sync-only regression that asserts a stale verifier stops before the marketplace file changes and does not invoke the builder.
3. Add failure cases for a missing builder, a failed builder, and a failed post-build verifier.
4. Run the focused package tests and confirm they fail because the publish engine has no release preparation gate.

<verify>
- run: `go test ./internal/publish -run 'Release|StaleArtifacts' -count=1`
  expect: exit 0
</verify>

## Task 2: Intercore Release Preparation and Final Gate

**Files:**
- Create: `core/intercore/internal/publish/release.go`
- Modify: `core/intercore/internal/publish/engine.go`
- Modify: `core/intercore/internal/publish/publish.go`

1. Add a conventional verifier/build-script discovery helper that is a no-op for plugins without release scripts.
2. Run the verifier first; rebuild only on verifier failure during a normal version publish.
3. Return every artifact changed by the builder so the engine stages it with the version commit.
4. Reject stale sync-only and dry-run paths without mutation.
5. Re-run the verifier immediately before marketplace mutation on every managed-release path.
6. Run focused and full Intercore tests, then commit and push the dependency before rebuilding the installed `ic` binary.

<verify>
- run: `go test ./internal/publish -count=1`
  expect: exit 0
- run: `go test ./...`
  expect: exit 0
</verify>

## Task 3: Clavain Hook Boundary and Published Cache Proof

**Files:**
- Modify: `os/Clavain/hooks/auto-publish.sh`
- Modify: `os/Clavain/tests/structural/test_scripts.py`
- Generated by publish: `os/Clavain/bin/*`, `os/Clavain/.claude-plugin/plugin.json`, `os/Clavain/agent-rig.json`, `os/Clavain/docs/PRD.md`

1. Add a failing structural test that forbids direct release builds and the manual publication fallback in `auto-publish.sh` while requiring delegation to `ic publish --auto`.
2. Remove the hook's direct builder invocations and mutation fallback; retain fail-open reporting for the interactive hook surface.
3. Run structural, shell syntax, ShellCheck, Go, and release-binary verification gates.
4. Publish a patch from a clean release checkout with the rebuilt `ic`, and confirm the engine rebuilds Clavain artifacts because the Intercore revision changed.
5. Install into a new versioned cache on Mac and zklw, compare manifest digests and build metadata, and run installer doctors.
6. Close `sylveste-7bms`, sync the tracker through `.beads/push.sh`, and verify all repository heads are pushed.

<verify>
- run: `pytest -q tests/structural/test_scripts.py`
  expect: exit 0
- run: `bash scripts/verify-release-binaries.sh`
  expect: exit 0
- run: `ic publish status`
  expect: exit 0
</verify>
