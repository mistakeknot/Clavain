#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  CANARY_SCRIPT="$REPO_ROOT/scripts/runtime-evidence-canary.sh"
}

@test "runtime evidence canary help describes isolated source and installed modes" {
  run bash "$CANARY_SCRIPT" --help

  [ "$status" -eq 0 ]
  [[ "$output" == *"--json"* ]]
  [[ "$output" == *"--keep"* ]]
  [[ "$output" == *"--ic-bin"* ]]
  [[ "$output" == *"--clavain-cli-bin"* ]]
  [[ "$output" == *"--runtime-fixture-bin"* ]]
  [[ "$output" == *"--runtime-probe-bin"* ]]
  [[ "$output" == *"isolated"* ]]
}

@test "runtime evidence canary requires workload overrides as a pair" {
  run bash "$CANARY_SCRIPT" --json --runtime-fixture-bin=/bin/true

  [ "$status" -eq 2 ]
  [[ "$output" == *"must be provided together"* ]]
}

@test "runtime evidence canary requires installed driver overrides as a pair" {
  run bash "$CANARY_SCRIPT" --json --ic-bin=/bin/true

  [ "$status" -eq 2 ]
  [[ "$output" == *"must be provided together"* ]]
}

@test "runtime evidence source canary proves missing shared and valid outcomes without live Beads" {
  for dependency in go git jq; do
    command -v "$dependency" >/dev/null 2>&1 || skip "$dependency is required"
  done
  [ -d "$REPO_ROOT/../../core/intercore/cmd/ic" ] || skip "sibling Intercore checkout is required"

  poison_bin="$BATS_TEST_TMPDIR/poison-bin"
  mkdir -p "$poison_bin"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'echo "live bd must not be called" >&2' \
    'exit 97' > "$poison_bin/bd"
  chmod +x "$poison_bin/bd"

  mkdir -p "$BATS_TEST_TMPDIR/.clavain"
  printf 'ancestor database sentinel\n' > "$BATS_TEST_TMPDIR/.clavain/intercore.db"
  ancestor_before="$(cksum "$BATS_TEST_TMPDIR/.clavain/intercore.db")"

  before_status="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)"
  before_intercore_status="$(git -C "$REPO_ROOT/../../core/intercore" status --porcelain=v1 --untracked-files=all)"
  run --separate-stderr env \
    PATH="$poison_bin:$PATH" \
    TMPDIR="$BATS_TEST_TMPDIR" \
    GOCACHE="${GOCACHE:-$BATS_TEST_TMPDIR/go-cache}" \
    bash "$CANARY_SCRIPT" --json

  if [ "$status" -ne 0 ]; then
    printf 'stdout:\n%s\nstderr:\n%s\n' "$output" "$stderr" >&3
  fi
  ancestor_after="$(cksum "$BATS_TEST_TMPDIR/.clavain/intercore.db")"
  [ "$ancestor_after" = "$ancestor_before" ]
  [ "$status" -eq 0 ]
  jq -e '
    .schema_version == 1 and
    .mode == "source" and
    .bd_backend == "isolated-shim" and
    (.platform | test("^[a-z0-9]+-[a-z0-9]+$")) and
    (.sources.intercore_head | test("^[0-9a-f]{40,64}$")) and
    (.sources.clavain_head | test("^[0-9a-f]{40,64}$")) and
    (.sources.canary_project_head | test("^[0-9a-f]{40,64}$")) and
    .outcomes.missing.advance_blocked == true and
    .outcomes.missing.verify_blocked == true and
    .outcomes.missing.close_blocked == true and
    .outcomes.missing.artifact_count == 0 and
    .outcomes.shared.collect_blocked == true and
    .outcomes.shared.advance_blocked == true and
    .outcomes.shared.artifact_count == 0 and
    .outcomes.shared.cleanup_verified == true and
    (.outcomes.shared.rejection | contains("collector-started instance")) and
    .outcomes.valid.collect_verified == true and
    .outcomes.valid.terminal_advanced == true and
    .outcomes.valid.artifact_count == 1 and
    .outcomes.valid.phase == "done" and
    .outcomes.valid.status == "completed" and
    .outcomes.valid.cleanup_verified == true and
    (.outcomes.valid.proof_hash | test("^sha256:[0-9a-f]{64}$")) and
    (.outcomes.valid.verification_summary | keys | sort) == ["git_head","host_fingerprint","proof_hash","run_id","schema_version","verified_at"] and
    .outcomes.valid.verification_summary.proof_hash == .outcomes.valid.proof_hash and
    .outcomes.valid.verification_summary.run_id == .outcomes.valid.run_id and
    .outcomes.valid.verification_summary.git_head == .sources.canary_project_head and
    (.outcomes.valid.verification_summary.host_fingerprint | test("^sha256:[0-9a-f]{64}$")) and
    .binaries.fixture_build_digest == .binaries.fixture_installed_digest and
    ([.outcomes.missing.run_id, .outcomes.shared.run_id, .outcomes.valid.run_id] | unique | length == 3)
  ' <<<"$output" >/dev/null
  [[ "$stderr" != *"live bd must not be called"* ]]

  after_status="$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)"
  [ "$after_status" = "$before_status" ]
  after_intercore_status="$(git -C "$REPO_ROOT/../../core/intercore" status --porcelain=v1 --untracked-files=all)"
  [ "$after_intercore_status" = "$before_intercore_status" ]
  [ -z "$(find "$BATS_TEST_TMPDIR" -maxdepth 1 -type d -name 'clavain-runtime-evidence-canary.*' -print -quit)" ]
}

@test "runtime evidence installed canary accepts a fully prebuilt workload without invoking go" {
  for dependency in go git jq; do
    command -v "$dependency" >/dev/null 2>&1 || skip "$dependency is required to prepare test binaries"
  done
  intercore_root="$REPO_ROOT/../../core/intercore"
  [ -d "$intercore_root/cmd/ic" ] || skip "sibling Intercore checkout is required"

  prebuilt="$BATS_TEST_TMPDIR/prebuilt"
  poison_bin="$BATS_TEST_TMPDIR/poison-bin"
  mkdir -p "$prebuilt" "$poison_bin"
  go build -C "$intercore_root" -mod=readonly -o "$prebuilt/ic" ./cmd/ic
  go build -C "$REPO_ROOT/cmd/clavain-cli" -mod=readonly -o "$prebuilt/clavain-cli" .
  go build -C "$REPO_ROOT/cmd/clavain-cli" -mod=readonly -o "$prebuilt/runtimefixture" ./testdata/runtimefixture
  go build -C "$REPO_ROOT/cmd/clavain-cli" -mod=readonly -o "$prebuilt/runtimeprobe" ./testdata/runtimeprobe
  printf '%s\n' '#!/usr/bin/env bash' 'echo "go must not be invoked" >&2' 'exit 98' > "$poison_bin/go"
  chmod +x "$poison_bin/go"

  run --separate-stderr env \
    PATH="$poison_bin:$PATH" \
    TMPDIR="$BATS_TEST_TMPDIR" \
    bash "$CANARY_SCRIPT" --json \
      --ic-bin="$prebuilt/ic" \
      --clavain-cli-bin="$prebuilt/clavain-cli" \
      --runtime-fixture-bin="$prebuilt/runtimefixture" \
      --runtime-probe-bin="$prebuilt/runtimeprobe"

  if [ "$status" -ne 0 ]; then
    printf 'stdout:\n%s\nstderr:\n%s\n' "$output" "$stderr" >&3
  fi
  [ "$status" -eq 0 ]
  [[ "$stderr" != *"go must not be invoked"* ]]
  jq -e --arg root "$prebuilt" '
    .mode == "installed" and
    .binaries.paths.intercore == ($root + "/ic") and
    .binaries.paths.clavain == ($root + "/clavain-cli") and
    .binaries.paths.runtime_fixture == ($root + "/runtimefixture") and
    .binaries.paths.runtime_probe == ($root + "/runtimeprobe") and
    .outcomes.missing.advance_blocked == true and
    .outcomes.missing.close_blocked == true and
    .outcomes.shared.cleanup_verified == true and
    .outcomes.valid.cleanup_verified == true and
    .outcomes.valid.status == "completed"
  ' <<<"$output" >/dev/null
}
