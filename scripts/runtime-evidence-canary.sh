#!/usr/bin/env bash
# Exercise missing, shared-runtime, and valid runtime evidence paths in isolation.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: runtime-evidence-canary.sh [--json] [--keep]
       [--ic-bin=<path> --clavain-cli-bin=<path>]
       [--runtime-fixture-bin=<path> --runtime-probe-bin=<path>]

Builds the runtime fixture and probe in an isolated temporary Git project, uses
an isolated Intercore database and private Beads shim, then exercises missing,
shared-runtime, and valid runtime-evidence outcomes.

Options:
  --json                     Emit one machine-readable result object.
  --keep                     Retain the temporary work root for inspection.
  --ic-bin=<path>            Use this installed Intercore entrypoint.
  --clavain-cli-bin=<path>   Use this installed Clavain entrypoint.
  --runtime-fixture-bin=<path>
                             Use this prebuilt canary runtime fixture.
  --runtime-probe-bin=<path> Use this prebuilt canary runtime probe.
  -h, --help                 Show this help.

Without binary overrides, both Intercore and Clavain are built from source.
Installed binary overrides must be provided together.
Prebuilt workload overrides must also be provided together; they allow exact
installed canaries on hosts whose Go toolchain cannot build the test workload.
EOF
}

usage_error() {
  echo "runtime-evidence-canary: $*" >&2
  usage >&2
  exit 2
}

die() {
  echo "runtime-evidence-canary: $*" >&2
  exit 1
}

log() {
  if [[ "$JSON_MODE" != true ]]; then
    echo "$*" >&2
  fi
}

JSON_MODE=false
KEEP_ROOT=false
IC_OVERRIDE=""
CLAVAIN_OVERRIDE=""
FIXTURE_OVERRIDE=""
PROBE_OVERRIDE=""

for arg in "$@"; do
  case "$arg" in
    --json)
      JSON_MODE=true
      ;;
    --keep)
      KEEP_ROOT=true
      ;;
    --ic-bin=*)
      IC_OVERRIDE="${arg#--ic-bin=}"
      ;;
    --clavain-cli-bin=*)
      CLAVAIN_OVERRIDE="${arg#--clavain-cli-bin=}"
      ;;
    --runtime-fixture-bin=*)
      FIXTURE_OVERRIDE="${arg#--runtime-fixture-bin=}"
      ;;
    --runtime-probe-bin=*)
      PROBE_OVERRIDE="${arg#--runtime-probe-bin=}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage_error "unknown argument: $arg"
      ;;
  esac
done

if [[ -n "$IC_OVERRIDE" && -z "$CLAVAIN_OVERRIDE" ]] ||
   [[ -z "$IC_OVERRIDE" && -n "$CLAVAIN_OVERRIDE" ]]; then
  usage_error "--ic-bin and --clavain-cli-bin must be provided together"
fi
if [[ -n "$FIXTURE_OVERRIDE" && -z "$PROBE_OVERRIDE" ]] ||
   [[ -z "$FIXTURE_OVERRIDE" && -n "$PROBE_OVERRIDE" ]]; then
  usage_error "--runtime-fixture-bin and --runtime-probe-bin must be provided together"
fi

for dependency in git jq; do
  command -v "$dependency" >/dev/null 2>&1 || die "$dependency is required"
done
if [[ -z "$IC_OVERRIDE" || -z "$FIXTURE_OVERRIDE" ]]; then
  command -v go >/dev/null 2>&1 || die "go is required when drivers or canary workloads are built from source"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAVAIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INTERCORE_ROOT="${INTERCORE_ROOT:-$CLAVAIN_ROOT/../../core/intercore}"
[[ -d "$INTERCORE_ROOT/cmd/ic" ]] || die "Intercore source not found at $INTERCORE_ROOT"
INTERCORE_ROOT="$(cd "$INTERCORE_ROOT" && pwd)"

resolve_executable() {
  local requested="$1"
  local resolved=""
  if [[ "$requested" == */* ]]; then
    [[ -e "$requested" ]] || return 1
    resolved="$(cd "$(dirname "$requested")" && pwd)/$(basename "$requested")"
  else
    resolved="$(command -v "$requested" 2>/dev/null || true)"
  fi
  [[ -n "$resolved" && -x "$resolved" ]] || return 1
  printf '%s\n' "$resolved"
}

host_platform() {
  local os_name arch_name
  os_name="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch_name="$(uname -m)"
  case "$os_name" in
    darwin|linux) ;;
    *) die "unsupported canary host OS: $os_name" ;;
  esac
  case "$arch_name" in
    arm64|aarch64) arch_name="arm64" ;;
    amd64|x86_64) arch_name="amd64" ;;
    *) die "unsupported canary host architecture: $arch_name" ;;
  esac
  printf '%s-%s\n' "$os_name" "$arch_name"
}

hash_file() {
  local path="$1"
  local digest=""
  if command -v sha256sum >/dev/null 2>&1; then
    digest="$(sha256sum "$path" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    digest="$(shasum -a 256 "$path" | awk '{print $1}')"
  elif command -v openssl >/dev/null 2>&1; then
    digest="$(openssl dgst -sha256 "$path" | awk '{print $NF}')"
  else
    die "sha256sum, shasum, or openssl is required"
  fi
  [[ "$digest" =~ ^[0-9a-f]{64}$ ]] || die "invalid SHA-256 digest for $path"
  printf 'sha256:%s\n' "$digest"
}

ORIGINAL_PWD="$PWD"
TMP_BASE="${TMPDIR:-/tmp}"
TMP_BASE="${TMP_BASE%/}"
CANARY_ROOT="$(mktemp -d "$TMP_BASE/clavain-runtime-evidence-canary.XXXXXX")"
PROJECT="$CANARY_ROOT/project"
DRIVER_BIN="$CANARY_ROOT/driver-bin"
SHIM_BIN="$CANARY_ROOT/shim-bin"
BD_STATE="$CANARY_ROOT/bd-state"
BD_LOG="$CANARY_ROOT/bd-calls.log"
PRIVATE_HOME="$CANARY_ROOT/home"
PRIVATE_STATE="$CANARY_ROOT/state"
PRIVATE_TMP="$CANARY_ROOT/tmp"
INSTALL_DIR="$CANARY_ROOT/install"
SHARED_DIR="$CANARY_ROOT/shared"
SHARED_ENDPOINT="$SHARED_DIR/endpoint.json"
INTERCORE_DB_PATH="$PROJECT/.clavain/intercore.db"
SHARED_PID=""

runtime_process_ids() {
  local executable="$1"
  ps -ww -axo pid=,command= 2>/dev/null |
    awk -v executable="$executable" '$2 == executable {print $1}'
}

fixture_process_ids() {
  runtime_process_ids "$INSTALLED_FIXTURE"
}

assert_no_private_probe_roots() {
  local leaked=""
  if [[ -d "$PRIVATE_STATE/clavain/runtime-evidence" ]]; then
    leaked="$(find "$PRIVATE_STATE/clavain/runtime-evidence" -type d -name '.probe-*' -print -quit 2>/dev/null || true)"
  fi
  [[ -z "$leaked" ]] || die "collector private probe root leaked: $leaked"
}

assert_fixture_processes() {
  local expected="$1" observed=""
  observed="$(fixture_process_ids | awk 'NF' | paste -sd, -)"
  [[ "$observed" == "$expected" ]] ||
    die "runtime fixture process set is '$observed', want '$expected'"
}

assert_no_probe_processes() {
  local observed=""
  observed="$(runtime_process_ids "$PROJECT/tools/runtimeprobe" | awk 'NF' | paste -sd, -)"
  [[ -z "$observed" ]] || die "runtime probe process leaked: $observed"
}

stop_shared_fixture() {
  if [[ -n "$SHARED_PID" ]]; then
    kill "$SHARED_PID" >/dev/null 2>&1 || true
    for _ in $(seq 1 100); do
      kill -0 "$SHARED_PID" >/dev/null 2>&1 || break
      sleep 0.02
    done
    if kill -0 "$SHARED_PID" >/dev/null 2>&1; then
      kill -KILL "$SHARED_PID" >/dev/null 2>&1 || true
    fi
    wait "$SHARED_PID" >/dev/null 2>&1 || true
    SHARED_PID=""
  fi
}

cleanup() {
  local rc=$?
  trap - EXIT
  stop_shared_fixture
  cd "$ORIGINAL_PWD" >/dev/null 2>&1 || true
  if [[ "$KEEP_ROOT" == true ]]; then
    echo "runtime-evidence-canary: retained $CANARY_ROOT" >&2
  elif [[ -n "$CANARY_ROOT" && -d "$CANARY_ROOT" ]]; then
    rm -rf "$CANARY_ROOT"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p \
  "$PROJECT/build" "$PROJECT/tools" "$DRIVER_BIN" "$SHIM_BIN" \
  "$BD_STATE" "$PRIVATE_HOME" "$PRIVATE_STATE" "$PRIVATE_TMP" \
  "$INSTALL_DIR" "$SHARED_DIR"

INTERCORE_HEAD="$(git -C "$INTERCORE_ROOT" rev-parse HEAD)"
CLAVAIN_HEAD="$(git -C "$CLAVAIN_ROOT" rev-parse HEAD)"
[[ "$INTERCORE_HEAD" =~ ^[0-9a-f]{40,64}$ ]] || die "Intercore HEAD is invalid"
[[ "$CLAVAIN_HEAD" =~ ^[0-9a-f]{40,64}$ ]] || die "Clavain HEAD is invalid"
if ! git -C "$INTERCORE_ROOT" diff --quiet || ! git -C "$INTERCORE_ROOT" diff --cached --quiet; then
  die "Intercore has tracked changes; commit them before recording canary source identity"
fi
if ! git -C "$CLAVAIN_ROOT" diff --quiet || ! git -C "$CLAVAIN_ROOT" diff --cached --quiet; then
  die "Clavain has tracked changes; commit them before recording canary source identity"
fi
[[ -z "$(git -C "$INTERCORE_ROOT" status --porcelain=v1 --untracked-files=all)" ]] ||
  die "Intercore has untracked source inputs; clean them before recording canary source identity"
[[ -z "$(git -C "$CLAVAIN_ROOT" status --porcelain=v1 --untracked-files=all -- cmd/clavain-cli)" ]] ||
  die "Clavain's Go module has untracked source inputs; clean them before recording canary source identity"

PLATFORM="$(host_platform)"
unset GOOS GOARCH CGO_ENABLED

if [[ -n "$IC_OVERRIDE" ]]; then
  MODE="installed"
  IC_EXEC="$(resolve_executable "$IC_OVERRIDE")" || die "--ic-bin is not executable: $IC_OVERRIDE"
  CLAVAIN_EXEC="$(resolve_executable "$CLAVAIN_OVERRIDE")" || die "--clavain-cli-bin is not executable: $CLAVAIN_OVERRIDE"
  ln -s "$IC_EXEC" "$DRIVER_BIN/ic"
  ln -s "$CLAVAIN_EXEC" "$DRIVER_BIN/clavain-cli"
else
  MODE="source"
  log "Building source Intercore and Clavain drivers"
  go build -C "$INTERCORE_ROOT" -mod=readonly -o "$DRIVER_BIN/ic" ./cmd/ic
  go build -C "$CLAVAIN_ROOT/cmd/clavain-cli" -mod=readonly -o "$DRIVER_BIN/clavain-cli" .
  IC_EXEC="$DRIVER_BIN/ic"
  CLAVAIN_EXEC="$DRIVER_BIN/clavain-cli"
fi

if [[ -n "$FIXTURE_OVERRIDE" ]]; then
  log "Installing prebuilt runtime fixture and probe"
  FIXTURE_EXEC="$(resolve_executable "$FIXTURE_OVERRIDE")" || die "--runtime-fixture-bin is not executable: $FIXTURE_OVERRIDE"
  PROBE_EXEC="$(resolve_executable "$PROBE_OVERRIDE")" || die "--runtime-probe-bin is not executable: $PROBE_OVERRIDE"
  cp -f "$FIXTURE_EXEC" "$PROJECT/build/runtimefixture"
  cp -f "$PROBE_EXEC" "$PROJECT/tools/runtimeprobe"
else
  log "Building isolated runtime fixture and probe"
  go build -C "$CLAVAIN_ROOT/cmd/clavain-cli" -mod=readonly \
    -o "$PROJECT/build/runtimefixture" ./testdata/runtimefixture
  go build -C "$CLAVAIN_ROOT/cmd/clavain-cli" -mod=readonly \
    -o "$PROJECT/tools/runtimeprobe" ./testdata/runtimeprobe
fi

INSTALLED_FIXTURE="$INSTALL_DIR/runtimefixture"
cp -f "$PROJECT/build/runtimefixture" "$INSTALLED_FIXTURE"
chmod 0755 "$PROJECT/build/runtimefixture" "$PROJECT/tools/runtimeprobe" "$INSTALLED_FIXTURE"

PROBE_DIGEST="$(hash_file "$PROJECT/tools/runtimeprobe")"
BUILD_DIGEST="$(hash_file "$PROJECT/build/runtimefixture")"
INSTALL_DIGEST="$(hash_file "$INSTALLED_FIXTURE")"
[[ "$BUILD_DIGEST" == "$INSTALL_DIGEST" ]] || die "fixture build/install digests differ"

cat > "$PROJECT/.gitignore" <<'EOF'
.clavain/
EOF
cat > "$PROJECT/reflection.md" <<'EOF'
Runtime evidence canary reflection.
EOF

jq -n \
  --arg platform "$PLATFORM" \
  --arg installed "$INSTALLED_FIXTURE" \
  --arg probe_digest "$PROBE_DIGEST" \
  '{
    schema_version: 1,
    build_path: "build/runtimefixture",
    installed_paths: {($platform): $installed},
    start_argv: ["{installed_path}"],
    probe_argv: ["{project_root}/tools/runtimeprobe"],
    probe_digests: {($platform): $probe_digest},
    timeout_seconds: 10,
    required_subsystems: ["store"],
    not_applicable_failure_classes: ["dependency_injection", "projection_catchup"],
    required_assertions: ["state-delta"],
    expected_surfaces: ["diag/health", "diag/smoke-test"],
    required_resources: [{kind: "port", ownership: "ephemeral"}]
  }' > "$PROJECT/runtime-evidence-valid.json"

jq -n \
  --arg platform "$PLATFORM" \
  --arg installed "$INSTALLED_FIXTURE" \
  --arg probe_digest "$PROBE_DIGEST" \
  --arg endpoint "$SHARED_ENDPOINT" \
  '{
    schema_version: 1,
    build_path: "build/runtimefixture",
    installed_paths: {($platform): $installed},
    start_argv: ["{installed_path}"],
    probe_argv: ["{project_root}/tools/runtimeprobe", ("--endpoint-file=" + $endpoint)],
    probe_digests: {($platform): $probe_digest},
    timeout_seconds: 10,
    required_subsystems: ["store"],
    not_applicable_failure_classes: ["dependency_injection", "projection_catchup"],
    required_assertions: ["state-delta"],
    expected_surfaces: ["diag/health", "diag/smoke-test"],
    required_resources: [{kind: "port", ownership: "ephemeral"}]
  }' > "$PROJECT/runtime-evidence-shared.json"

git -C "$PROJECT" init -q
git -C "$PROJECT" config user.name "Runtime Evidence Canary"
git -C "$PROJECT" config user.email "runtime-evidence-canary@example.invalid"
git -C "$PROJECT" add -- \
  .gitignore reflection.md build/runtimefixture tools/runtimeprobe \
  runtime-evidence-valid.json runtime-evidence-shared.json
git -C "$PROJECT" commit -q -m "runtime evidence canary fixture"
CANARY_PROJECT_HEAD="$(git -C "$PROJECT" rev-parse HEAD)"
[[ "$CANARY_PROJECT_HEAD" =~ ^[0-9a-f]{40,64}$ ]] || die "canary project HEAD is invalid"

cat > "$SHIM_BIN/bd" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

state_root="${CLAVAIN_CANARY_BD_STATE:?}"
if [[ -n "${CLAVAIN_CANARY_BD_LOG:-}" ]]; then
  printf '%s\n' "$*" >> "$CLAVAIN_CANARY_BD_LOG"
fi

validate_bead() {
  [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "isolated bd: unsafe bead id" >&2
    exit 90
  }
}

state_file_for() {
  validate_bead "$1"
  printf '%s/%s.json\n' "$state_root" "$1"
}

ensure_state_file() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    printf '{}\n' > "$file"
    chmod 0600 "$file"
  fi
}

case "${1:-}" in
  show)
    bead="${2:-}"
    validate_bead "$bead"
    jq -cn --arg id "$bead" '[{id:$id,labels:["close-gate:runtime-evidence"]}]'
    ;;
  state)
    bead="${2:-}"
    key="${3:-}"
    file="$(state_file_for "$bead")"
    ensure_state_file "$file"
    value="$(jq -r --arg key "$key" '.[$key] // empty' "$file")"
    if [[ -n "$value" ]]; then
      printf '%s\n' "$value"
    else
      printf '(no %s state set)\n' "$key"
    fi
    ;;
  set-state)
    bead="${2:-}"
    assignment="${3:-}"
    [[ "$assignment" == *=* ]] || {
      echo "isolated bd: set-state requires key=value" >&2
      exit 91
    }
    key="${assignment%%=*}"
    value="${assignment#*=}"
    file="$(state_file_for "$bead")"
    ensure_state_file "$file"
    temp="$(mktemp "$state_root/.state.XXXXXX")"
    jq --arg key "$key" --arg value "$value" '.[$key] = $value' "$file" > "$temp"
    chmod 0600 "$temp"
    mv -f "$temp" "$file"
    printf '%s\n' "$value"
    ;;
  *)
    echo "isolated bd: unsupported command: $*" >&2
    exit 92
    ;;
esac
EOF
chmod 0755 "$SHIM_BIN/bd"

export CLAVAIN_CANARY_BD_STATE="$BD_STATE"
export CLAVAIN_CANARY_BD_LOG="$BD_LOG"
: > "$BD_LOG"
export PATH="$SHIM_BIN:$DRIVER_BIN:$PATH"
export HOME="$PRIVATE_HOME"
export XDG_STATE_HOME="$PRIVATE_STATE"
export TMPDIR="$PRIVATE_TMP"

cd "$PROJECT"
"$IC_EXEC" --db="$INTERCORE_DB_PATH" init >/dev/null
[[ -f "$INTERCORE_DB_PATH" && ! -L "$INTERCORE_DB_PATH" ]] ||
  die "isolated Intercore database was not created as a local regular file"

create_canary_run() {
  local scenario="$1"
  local bead="canary-$scenario"
  local metadata=""
  local run_id=""
  metadata="$(jq -cn --arg bead "$bead" '{close_gate:{requirements:["runtime-evidence/v1"],bead_id:$bead}}')"
  run_id="$("$IC_EXEC" run create \
    --project="$PROJECT" \
    --goal="Runtime evidence canary: $scenario" \
    --scope-id="$bead" \
    --complexity=3 \
    --phases='["reflect","done"]' \
    --metadata="$metadata")"
  [[ -n "$run_id" ]] || die "failed to create $scenario run"
  "$IC_EXEC" run artifact add "$run_id" \
    --phase=reflect --path="$PROJECT/reflection.md" --type=reflection >/dev/null
  "$SHIM_BIN/bd" set-state "$bead" "ic_run_id=$run_id" >/dev/null
  "$SHIM_BIN/bd" set-state "$bead" "runtime_evidence_required=1" >/dev/null
  "$SHIM_BIN/bd" set-state "$bead" "phase=reflect" >/dev/null
  printf '%s\n' "$run_id"
}

runtime_artifact_count() {
  local run_id="$1"
  "$IC_EXEC" --json run artifact list "$run_id" |
    jq '[.[] | select(.type == "runtime-evidence/v1" and .status == "active")] | length'
}

LAST_BLOCK_JSON=""
LAST_BLOCK_EVENT_ID=""
assert_terminal_blocked() {
  local run_id="$1"
  local scenario="$2"
  local stderr_file="$CANARY_ROOT/$scenario-advance.stderr"
  local rc=0
  if LAST_BLOCK_JSON="$("$IC_EXEC" --json run advance "$run_id" \
      --disable-gates --priority=4 --skip-reason=canary 2>"$stderr_file")"; then
    die "$scenario terminal advance unexpectedly succeeded"
  else
    rc=$?
  fi
  [[ "$rc" -eq 1 ]] || die "$scenario terminal advance exited $rc, want 1"
  jq -e '
    .advanced == false and
    .event_type == "block" and
    .gate_result == "fail" and
    .gate_tier == "hard" and
    (.reason | contains("runtime_evidence"))
  ' <<<"$LAST_BLOCK_JSON" >/dev/null || die "$scenario terminal block JSON was invalid"
  LAST_BLOCK_EVENT_ID="$("$IC_EXEC" --json run events "$run_id" |
    jq -r '[.[] | select(.event_type == "block")][-1].id // ""')"
  [[ -n "$LAST_BLOCK_EVENT_ID" ]] || die "$scenario block event was not stored"
}

log "Checking missing-receipt hard block"
MISSING_BEAD="canary-missing"
MISSING_RUN="$(create_canary_run missing)"
assert_terminal_blocked "$MISSING_RUN" missing
MISSING_EVENT_ID="$LAST_BLOCK_EVENT_ID"
if "$CLAVAIN_EXEC" runtime-evidence verify "$MISSING_BEAD" \
    >"$CANARY_ROOT/missing-verify.stdout" 2>"$CANARY_ROOT/missing-verify.stderr"; then
  die "missing receipt unexpectedly verified"
fi
if bash "$CLAVAIN_ROOT/scripts/gates/bead-close.sh" "$MISSING_BEAD" "canary must stay open" \
    >"$CANARY_ROOT/missing-close.stdout" 2>"$CANARY_ROOT/missing-close.stderr"; then
  die "missing receipt unexpectedly passed the canonical close wrapper"
fi
grep -Fq "runtime-evidence: verification failed" "$CANARY_ROOT/missing-close.stderr" ||
  die "missing close wrapper failed for an unexpected reason"
if awk '$1 == "close" {found=1} END {exit !found}' "$BD_LOG"; then
  die "missing close wrapper reached tracker closure"
fi
if grep -Fq "runtime_evidence_summary=" "$BD_LOG"; then
  die "missing close wrapper persisted a proof summary"
fi
MISSING_CLOSE_BLOCKED=true
MISSING_ARTIFACTS="$(runtime_artifact_count "$MISSING_RUN")"
[[ "$MISSING_ARTIFACTS" -eq 0 ]] || die "missing run registered a runtime receipt"

log "Checking pre-existing shared-runtime refusal"
CLAVAIN_RUNTIME_INSTANCE_NONCE="shared-canary-instance" \
CLAVAIN_RUNTIME_ENDPOINT_FILE="$SHARED_ENDPOINT" \
  "$INSTALLED_FIXTURE" >"$CANARY_ROOT/shared-fixture.stdout" \
  2>"$CANARY_ROOT/shared-fixture.stderr" &
SHARED_PID=$!
for _ in $(seq 1 500); do
  [[ -s "$SHARED_ENDPOINT" ]] && break
  if ! kill -0 "$SHARED_PID" >/dev/null 2>&1; then
    die "shared fixture exited before endpoint publication"
  fi
  sleep 0.02
done
[[ -s "$SHARED_ENDPOINT" ]] || die "shared fixture endpoint was not published"

SHARED_BEAD="canary-shared"
SHARED_RUN="$(create_canary_run shared)"
if "$CLAVAIN_EXEC" runtime-evidence collect "$SHARED_BEAD" \
    --config=runtime-evidence-shared.json \
    >"$CANARY_ROOT/shared-collect.stdout" 2>"$CANARY_ROOT/shared-collect.stderr"; then
  die "shared runtime unexpectedly produced evidence"
fi
SHARED_REJECTION="$(grep -F "collector-started instance" \
  "$CANARY_ROOT/shared-collect.stderr" | head -n 1 || true)"
[[ -n "$SHARED_REJECTION" ]] || {
  tail -n 20 "$CANARY_ROOT/shared-collect.stderr" >&2 || true
  die "shared runtime failed for an unexpected reason"
}
SHARED_ARTIFACTS="$(runtime_artifact_count "$SHARED_RUN")"
[[ "$SHARED_ARTIFACTS" -eq 0 ]] || die "shared run registered a runtime receipt"
assert_no_private_probe_roots
assert_fixture_processes "$SHARED_PID"
assert_no_probe_processes
SHARED_CLEANUP_VERIFIED=true
assert_terminal_blocked "$SHARED_RUN" shared
SHARED_EVENT_ID="$LAST_BLOCK_EVENT_ID"
stop_shared_fixture
assert_fixture_processes ""

log "Checking valid collector-launched runtime evidence"
VALID_BEAD="canary-valid"
VALID_RUN="$(create_canary_run valid)"
VALID_COLLECT="$("$CLAVAIN_EXEC" runtime-evidence collect "$VALID_BEAD" \
  --config=runtime-evidence-valid.json)"
VALID_VERIFY="$("$CLAVAIN_EXEC" runtime-evidence verify "$VALID_BEAD")"
for summary in "$VALID_COLLECT" "$VALID_VERIFY"; do
  jq -e '
    type == "object" and
    (keys | sort) == ["git_head","host_fingerprint","proof_hash","run_id","schema_version","verified_at"] and
    .schema_version == 1 and
    (.proof_hash | type == "string" and test("^sha256:[0-9a-f]{64}$")) and
    (.run_id | type == "string" and length > 0) and
    (.git_head | type == "string" and test("^[0-9a-f]{40,64}$")) and
    (.verified_at | type == "string" and length > 0) and
    (.host_fingerprint | type == "string" and test("^sha256:[0-9a-f]{64}$"))
  ' <<<"$summary" >/dev/null || die "collector returned a malformed sanitized verification summary"
done
[[ "$(jq -c 'del(.verified_at)' <<<"$VALID_COLLECT")" == \
   "$(jq -c 'del(.verified_at)' <<<"$VALID_VERIFY")" ]] ||
  die "collect and verify summaries disagree on stable proof identity"
VALID_PROOF_HASH="$(jq -r '.proof_hash // empty' <<<"$VALID_COLLECT")"
[[ "$VALID_PROOF_HASH" =~ ^sha256:[0-9a-f]{64}$ ]] || die "valid collector returned no proof hash"
[[ "$(jq -r '.run_id // empty' <<<"$VALID_COLLECT")" == "$VALID_RUN" ]] ||
  die "valid collector returned the wrong run ID"
[[ "$(jq -r '.proof_hash // empty' <<<"$VALID_VERIFY")" == "$VALID_PROOF_HASH" ]] ||
  die "collect and verify proof hashes differ"
VALID_ARTIFACTS="$(runtime_artifact_count "$VALID_RUN")"
[[ "$VALID_ARTIFACTS" -eq 1 ]] || die "valid run has $VALID_ARTIFACTS runtime receipts, want 1"
assert_no_private_probe_roots
assert_fixture_processes ""
assert_no_probe_processes
VALID_CLEANUP_VERIFIED=true

VALID_ADVANCE="$("$IC_EXEC" --json run advance "$VALID_RUN" --priority=4)"
jq -e '
  .advanced == true and
  .from_phase == "reflect" and
  .to_phase == "done" and
  .gate_result == "pass" and
  .gate_tier == "hard"
' <<<"$VALID_ADVANCE" >/dev/null || die "valid terminal advance did not pass the hard gate"
VALID_STATUS_JSON="$("$IC_EXEC" --json run status "$VALID_RUN")"
VALID_PHASE="$(jq -r '.phase // empty' <<<"$VALID_STATUS_JSON")"
VALID_STATUS="$(jq -r '.status // empty' <<<"$VALID_STATUS_JSON")"
[[ "$VALID_PHASE" == "done" && "$VALID_STATUS" == "completed" ]] ||
  die "valid run ended at $VALID_STATUS/$VALID_PHASE"
VALID_EVENT_ID="$("$IC_EXEC" --json run events "$VALID_RUN" |
  jq -r '[.[] | select(.event_type == "advance" and .to_phase == "done")][-1].id // ""')"
[[ -n "$VALID_EVENT_ID" ]] || die "valid terminal event was not stored"

IC_DIGEST="$(hash_file "$IC_EXEC")"
CLAVAIN_DIGEST="$(hash_file "$CLAVAIN_EXEC")"
REPORTED_IC_PATH=""
REPORTED_CLAVAIN_PATH=""
REPORTED_FIXTURE_PATH=""
REPORTED_PROBE_PATH=""
if [[ "$MODE" == "installed" || "$KEEP_ROOT" == true ]]; then
  REPORTED_IC_PATH="$IC_EXEC"
  REPORTED_CLAVAIN_PATH="$CLAVAIN_EXEC"
fi
if [[ -n "$FIXTURE_OVERRIDE" || "$KEEP_ROOT" == true ]]; then
  REPORTED_FIXTURE_PATH="${FIXTURE_EXEC:-$PROJECT/build/runtimefixture}"
  REPORTED_PROBE_PATH="${PROBE_EXEC:-$PROJECT/tools/runtimeprobe}"
fi

RESULT="$(jq -n \
  --arg mode "$MODE" \
  --arg platform "$PLATFORM" \
  --arg intercore_head "$INTERCORE_HEAD" \
  --arg clavain_head "$CLAVAIN_HEAD" \
  --arg canary_project_head "$CANARY_PROJECT_HEAD" \
  --arg ic_digest "$IC_DIGEST" \
  --arg clavain_digest "$CLAVAIN_DIGEST" \
  --arg ic_path "$REPORTED_IC_PATH" \
  --arg clavain_path "$REPORTED_CLAVAIN_PATH" \
  --arg fixture_path "$REPORTED_FIXTURE_PATH" \
  --arg probe_path "$REPORTED_PROBE_PATH" \
  --arg build_digest "$BUILD_DIGEST" \
  --arg install_digest "$INSTALL_DIGEST" \
  --arg missing_run "$MISSING_RUN" \
  --arg missing_event "$MISSING_EVENT_ID" \
  --argjson missing_artifacts "$MISSING_ARTIFACTS" \
  --argjson missing_close_blocked "$MISSING_CLOSE_BLOCKED" \
  --arg shared_run "$SHARED_RUN" \
  --arg shared_event "$SHARED_EVENT_ID" \
  --arg shared_rejection "$SHARED_REJECTION" \
  --argjson shared_artifacts "$SHARED_ARTIFACTS" \
  --argjson shared_cleanup "$SHARED_CLEANUP_VERIFIED" \
  --arg valid_run "$VALID_RUN" \
  --arg valid_event "$VALID_EVENT_ID" \
  --arg valid_proof "$VALID_PROOF_HASH" \
  --arg valid_phase "$VALID_PHASE" \
  --arg valid_status "$VALID_STATUS" \
  --argjson valid_artifacts "$VALID_ARTIFACTS" \
  --argjson valid_cleanup "$VALID_CLEANUP_VERIFIED" \
  --argjson valid_summary "$VALID_VERIFY" \
  --arg collect_verified_at "$(jq -r '.verified_at' <<<"$VALID_COLLECT")" \
  --arg work_root "$(if [[ "$KEEP_ROOT" == true ]]; then printf '%s' "$CANARY_ROOT"; fi)" \
  '{
    schema_version: 1,
    mode: $mode,
    bd_backend: "isolated-shim",
    platform: $platform,
    sources: {
      intercore_head: $intercore_head,
      clavain_head: $clavain_head,
      canary_project_head: $canary_project_head
    },
    binaries: {
      intercore_digest: $ic_digest,
      clavain_digest: $clavain_digest,
      fixture_build_digest: $build_digest,
      fixture_installed_digest: $install_digest
    }
    + (if $ic_path == "" then {} else {
        paths: {
          intercore: $ic_path,
          clavain: $clavain_path
        }
        + (if $fixture_path == "" then {} else {
            runtime_fixture: $fixture_path,
            runtime_probe: $probe_path
          } end)
      } end),
    outcomes: {
      missing: {
        run_id: $missing_run,
        gate_event_id: $missing_event,
        advance_blocked: true,
        verify_blocked: true,
        close_blocked: $missing_close_blocked,
        artifact_count: $missing_artifacts
      },
      shared: {
        run_id: $shared_run,
        gate_event_id: $shared_event,
        collect_blocked: true,
        advance_blocked: true,
        artifact_count: $shared_artifacts,
        rejection: $shared_rejection,
        cleanup_verified: $shared_cleanup
      },
      valid: {
        run_id: $valid_run,
        gate_event_id: $valid_event,
        collect_verified: true,
        terminal_advanced: true,
        artifact_count: $valid_artifacts,
        phase: $valid_phase,
        status: $valid_status,
        proof_hash: $valid_proof,
        cleanup_verified: $valid_cleanup,
        verification_summary: $valid_summary,
        collection_verified_at: $collect_verified_at
      }
    }
  } + if $work_root == "" then {} else {work_root: $work_root} end')"

if [[ "$JSON_MODE" == true ]]; then
  printf '%s\n' "$RESULT"
else
  echo "runtime-evidence canary passed ($MODE, $PLATFORM)"
  echo "  missing: blocked (event $MISSING_EVENT_ID)"
  echo "  shared: blocked (event $SHARED_EVENT_ID)"
  echo "  valid:   $VALID_PROOF_HASH (event $VALID_EVENT_ID)"
fi
