#!/usr/bin/env bash
# SessionEnd hook: record evidence-qualified calibration loop outcomes.
# Exit 0 always: calibration evidence must never block session shutdown.

set -uo pipefail
trap 'exit 0' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib.sh" 2>/dev/null || true

_CALIBRATION_TIMEOUT_SECONDS="${CLAVAIN_CALIBRATION_TIMEOUT_SECONDS:-10}"
if [[ ! "$_CALIBRATION_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    _CALIBRATION_TIMEOUT_SECONDS=10
fi

_run_bounded() {
    local seconds="$1"
    shift

    if command -v timeout >/dev/null 2>&1; then
        if timeout "$seconds" "$@" >/dev/null 2>&1; then
            return 0
        else
            return $?
        fi
    fi
    if command -v gtimeout >/dev/null 2>&1; then
        if gtimeout "$seconds" "$@" >/dev/null 2>&1; then
            return 0
        else
            return $?
        fi
    fi
    if command -v python3 >/dev/null 2>&1; then
        if python3 -c '
import subprocess
import sys

try:
    result = subprocess.run(
        sys.argv[2:],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=float(sys.argv[1]),
        check=False,
    )
except subprocess.TimeoutExpired:
    raise SystemExit(124)
except FileNotFoundError:
    raise SystemExit(127)
except Exception:
    raise SystemExit(125)

raise SystemExit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
' "$seconds" "$@"; then
            return 0
        else
            return $?
        fi
    fi
    return 125
}

_hash_stream() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 | awk '{print $1}'
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 | awk '{print $NF}'
    else
        cksum | awk '{print "cksum-" $1 "-" $2}'
    fi
}

_artifact_hash() {
    local path="$1"
    if [[ -f "$path" ]]; then
        _hash_stream < "$path"
    else
        printf '%s' 'clavain:missing-calibration-artifact:v1' | _hash_stream
    fi
}

_artifact_evidence_count() {
    local loop="$1" path="$2"
    if [[ ! -f "$path" ]]; then
        printf '0\n'
        return 0
    fi

    case "$loop" in
        routing)
            jq -er '
                (.agents // {}) |
                if type == "object" then length else error("agents must be an object") end
            ' "$path" 2>/dev/null
            ;;
        gate_threshold)
            jq -er '
                (.tiers // {}) |
                if type != "object" then error("tiers must be an object")
                else
                    [to_entries[].value |
                        (.weighted_n // 0) |
                        if type == "number" and . >= 0 then .
                        else error("weighted_n must be non-negative") end
                    ] | (add // 0) | floor
                end
            ' "$path" 2>/dev/null
            ;;
        phase_cost)
            jq -er '
                .run_count |
                if type == "number" and . >= 0 and floor == . then .
                else error("run_count must be a non-negative integer") end
            ' "$path" 2>/dev/null
            ;;
        *) return 1 ;;
    esac
}

_find_interspect_writer() {
    local root="" candidate=""

    if [[ -n "${INTERSPECT_ROOT:-}" ]]; then
        candidate="${INTERSPECT_ROOT}/scripts/write-routing-calibration.sh"
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi

    if declare -F _discover_interspect_plugin >/dev/null 2>&1; then
        root="$(_discover_interspect_plugin 2>/dev/null)" || root=""
        candidate="${root:+$root/}scripts/write-routing-calibration.sh"
        if [[ -n "$root" && -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi

    for candidate in \
        "${CLAVAIN_SOURCE_DIR:-}/../../interverse/interspect/scripts/write-routing-calibration.sh" \
        "$SCRIPT_DIR/../../../interverse/interspect/scripts/write-routing-calibration.sh" \
        "${HOME}/projects/Sylveste/interverse/interspect/scripts/write-routing-calibration.sh" \
        "${HOME}/projects/interverse/interspect/scripts/write-routing-calibration.sh"
    do
        [[ "$candidate" == /* && -f "$candidate" ]] || continue
        printf '%s\n' "$candidate"
        return 0
    done

    if [[ -d "${HOME}/.claude/plugins/cache" ]]; then
        candidate="$(find "${HOME}/.claude/plugins/cache" -maxdepth 6 \
            -path '*/interspect/*/scripts/write-routing-calibration.sh' \
            -type f 2>/dev/null | sort | tail -1)" || candidate=""
        if [[ -n "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    fi
    return 1
}

_classify_loop() {
    local rc="$1" before_hash="$2" after_hash="$3" contract_valid="$4"
    _LOOP_OUTCOME="failed"
    _LOOP_DETAIL="rc=$rc; contract=failed"

    if [[ "$contract_valid" != "true" ]]; then
        return 0
    fi
    case "$rc" in
        0)
            if [[ "$before_hash" == "$after_hash" ]]; then
                _LOOP_OUTCOME="valid_noop"
                _LOOP_DETAIL="rc=0; artifact=stable"
            else
                _LOOP_OUTCOME="updated"
                _LOOP_DETAIL="rc=0; artifact=updated"
            fi
            ;;
        2)
            if [[ "$before_hash" == "$after_hash" ]]; then
                _LOOP_OUTCOME="valid_noop"
                _LOOP_DETAIL="rc=2; artifact=stable"
            else
                _LOOP_OUTCOME="failed"
                _LOOP_DETAIL="rc=2; contract=artifact-drift"
            fi
            ;;
        124)
            _LOOP_OUTCOME="timeout"
            _LOOP_DETAIL="rc=124; timeout=${_CALIBRATION_TIMEOUT_SECONDS}s"
            ;;
        *)
            _LOOP_OUTCOME="failed"
            _LOOP_DETAIL="rc=$rc; producer=failed"
            ;;
    esac
}

command -v jq >/dev/null 2>&1 || exit 0
command -v ic >/dev/null 2>&1 || exit 0
command -v bd >/dev/null 2>&1 || exit 0
command -v clavain-cli >/dev/null 2>&1 || exit 0

_HOOK_INPUT="$(cat 2>/dev/null)" || _HOOK_INPUT=""
if ! jq -e 'type == "object"' >/dev/null 2>&1 <<<"$_HOOK_INPUT"; then
    exit 0
fi

_SESSION_ID="$(jq -er '.session_id | select(type == "string" and length > 0)' \
    <<<"$_HOOK_INPUT" 2>/dev/null)" || _SESSION_ID=""
_HOOK_CWD="$(jq -er '.cwd | select(type == "string" and length > 0)' \
    <<<"$_HOOK_INPUT" 2>/dev/null)" || _HOOK_CWD=""
[[ -n "$_SESSION_ID" && "$_SESSION_ID" != "unknown" ]] || exit 0
[[ "$_HOOK_CWD" == /* && -d "$_HOOK_CWD" ]] || exit 0

_PROOF_ROOT="$_HOOK_CWD"
while [[ ! -f "$_PROOF_ROOT/.beads/metadata.json" ]]; do
    _PARENT_DIR="$(dirname "$_PROOF_ROOT")"
    [[ "$_PARENT_DIR" != "$_PROOF_ROOT" ]] || exit 0
    _PROOF_ROOT="$_PARENT_DIR"
done

_CURRENT_JSON=""
if ! _CURRENT_JSON="$(ic --json session current --session="$_SESSION_ID" \
    --project="$_HOOK_CWD" 2>/dev/null)"; then
    exit 0
fi
if ! jq -e --arg session "$_SESSION_ID" --arg project "$_HOOK_CWD" '
    type == "object" and
    .session_id == $session and .project_dir == $project and .phase == "done" and
    (.bead_id | type == "string" and length > 0) and
    (.run_id | type == "string" and length > 0)
' >/dev/null 2>&1 <<<"$_CURRENT_JSON"; then
    exit 0
fi
_SPRINT_ID="$(jq -r '.bead_id' <<<"$_CURRENT_JSON")"
_RUN_ID="$(jq -r '.run_id' <<<"$_CURRENT_JSON")"

cd -- "$_PROOF_ROOT" 2>/dev/null || exit 0
_IS_SPRINT="$(bd state "$_SPRINT_ID" sprint 2>/dev/null)" || _IS_SPRINT=""
[[ "$_IS_SPRINT" == "true" ]] || exit 0
_BEAD_RUN_ID="$(bd state "$_SPRINT_ID" ic_run_id 2>/dev/null)" || _BEAD_RUN_ID=""
[[ "$_BEAD_RUN_ID" == "$_RUN_ID" ]] || exit 0

_BEAD_JSON=""
if ! _BEAD_JSON="$(bd show --json "$_SPRINT_ID" 2>/dev/null)"; then
    exit 0
fi
if ! jq -e --arg bead "$_SPRINT_ID" '
    (if type == "array" then .[0] else . end) |
    type == "object" and .id == $bead and .status == "closed"
' >/dev/null 2>&1 <<<"$_BEAD_JSON"; then
    exit 0
fi

_RUN_JSON=""
if ! _RUN_JSON="$(ic --json run status "$_RUN_ID" 2>/dev/null)"; then
    exit 0
fi
if ! jq -e --arg run "$_RUN_ID" '
    type == "object" and .id == $run and .status == "completed" and .phase == "done"
' >/dev/null 2>&1 <<<"$_RUN_JSON"; then
    exit 0
fi

# Status verifies the receipt-derived cache before any producer can mutate an
# artifact. Duplicate SessionEnd deliveries are no-ops at this boundary.
_STREAK_JSON=""
if ! _STREAK_JSON="$(clavain-cli calibration-streak status --json \
    --root="$_PROOF_ROOT" 2>/dev/null)"; then
    exit 0
fi
if ! jq -e '
    type == "object" and .schema_version == 2 and (.receipts | type == "array")
' >/dev/null 2>&1 <<<"$_STREAK_JSON"; then
    exit 0
fi
if jq -e --arg session "$_SESSION_ID" --arg sprint "$_SPRINT_ID" '
    any(.receipts[]; .session_id == $session or .sprint_id == $sprint)
' >/dev/null 2>&1 <<<"$_STREAK_JSON"; then
    exit 0
fi

# Eligibility is now proven. Session closure is administrative and best-effort;
# the already-completed sprint remains eligible even if this update fails.
ic --json session end --session="$_SESSION_ID" >/dev/null 2>&1 || true

export CLAUDE_PROJECT_DIR="$_PROOF_ROOT"
export SPRINT_LIB_PROJECT_DIR="$_PROOF_ROOT"

_ROUTING_ARTIFACT="$_PROOF_ROOT/.clavain/interspect/routing-calibration.json"
_GATE_ARTIFACT="$_PROOF_ROOT/.clavain/gate-tier-calibration.json"
_PHASE_ARTIFACT="$_PROOF_ROOT/.clavain/phase-cost-calibration.json"

_ROUTING_BEFORE="$(_artifact_hash "$_ROUTING_ARTIFACT")"
_ROUTING_WRITER="$(_find_interspect_writer 2>/dev/null)" || _ROUTING_WRITER=""
if [[ -n "$_ROUTING_WRITER" ]]; then
    if _run_bounded "$_CALIBRATION_TIMEOUT_SECONDS" env \
        CLAUDE_PROJECT_DIR="$_PROOF_ROOT" bash "$_ROUTING_WRITER"; then
        _ROUTING_RC=0
    else
        _ROUTING_RC=$?
    fi
else
    _ROUTING_RC=127
fi
_ROUTING_AFTER="$(_artifact_hash "$_ROUTING_ARTIFACT")"
if _ROUTING_EVIDENCE="$(_artifact_evidence_count routing "$_ROUTING_ARTIFACT")"; then
    _ROUTING_CONTRACT=true
else
    _ROUTING_EVIDENCE=0
    _ROUTING_CONTRACT=false
fi
_classify_loop "$_ROUTING_RC" "$_ROUTING_BEFORE" "$_ROUTING_AFTER" "$_ROUTING_CONTRACT"
_ROUTING_OUTCOME="$_LOOP_OUTCOME"
_ROUTING_DETAIL="$_LOOP_DETAIL; evidence=$_ROUTING_EVIDENCE"

_GATE_BEFORE="$(_artifact_hash "$_GATE_ARTIFACT")"
if _run_bounded "$_CALIBRATION_TIMEOUT_SECONDS" \
    clavain-cli calibrate-gate-tiers --auto; then
    _GATE_RC=0
else
    _GATE_RC=$?
fi
_GATE_AFTER="$(_artifact_hash "$_GATE_ARTIFACT")"
if _GATE_EVIDENCE="$(_artifact_evidence_count gate_threshold "$_GATE_ARTIFACT")"; then
    _GATE_CONTRACT=true
else
    _GATE_EVIDENCE=0
    _GATE_CONTRACT=false
fi
_classify_loop "$_GATE_RC" "$_GATE_BEFORE" "$_GATE_AFTER" "$_GATE_CONTRACT"
_GATE_OUTCOME="$_LOOP_OUTCOME"
_GATE_DETAIL="$_LOOP_DETAIL; evidence=$_GATE_EVIDENCE"

_PHASE_BEFORE="$(_artifact_hash "$_PHASE_ARTIFACT")"
if _run_bounded "$_CALIBRATION_TIMEOUT_SECONDS" \
    clavain-cli calibrate-phase-costs --auto --strict; then
    _PHASE_RC=0
else
    _PHASE_RC=$?
fi
_PHASE_AFTER="$(_artifact_hash "$_PHASE_ARTIFACT")"
if _PHASE_EVIDENCE="$(_artifact_evidence_count phase_cost "$_PHASE_ARTIFACT")"; then
    _PHASE_CONTRACT=true
else
    _PHASE_EVIDENCE=0
    _PHASE_CONTRACT=false
fi
_classify_loop "$_PHASE_RC" "$_PHASE_BEFORE" "$_PHASE_AFTER" "$_PHASE_CONTRACT"
_PHASE_OUTCOME="$_LOOP_OUTCOME"
_PHASE_DETAIL="$_LOOP_DETAIL; evidence=$_PHASE_EVIDENCE"

_HOST="$(hostname -s 2>/dev/null)" || _HOST=""
if [[ -z "$_HOST" ]]; then
    _HOST="$(hostname 2>/dev/null)" || _HOST="unknown-host"
fi
[[ -n "$_HOST" ]] || _HOST="unknown-host"
_TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

_RECEIPT="$(jq -n \
    --arg session_id "$_SESSION_ID" \
    --arg sprint_id "$_SPRINT_ID" \
    --arg host "$_HOST" \
    --arg timestamp "$_TIMESTAMP" \
    --arg routing_outcome "$_ROUTING_OUTCOME" \
    --arg routing_before "$_ROUTING_BEFORE" \
    --arg routing_after "$_ROUTING_AFTER" \
    --argjson routing_evidence "$_ROUTING_EVIDENCE" \
    --arg routing_detail "$_ROUTING_DETAIL" \
    --arg gate_outcome "$_GATE_OUTCOME" \
    --arg gate_before "$_GATE_BEFORE" \
    --arg gate_after "$_GATE_AFTER" \
    --argjson gate_evidence "$_GATE_EVIDENCE" \
    --arg gate_detail "$_GATE_DETAIL" \
    --arg phase_outcome "$_PHASE_OUTCOME" \
    --arg phase_before "$_PHASE_BEFORE" \
    --arg phase_after "$_PHASE_AFTER" \
    --argjson phase_evidence "$_PHASE_EVIDENCE" \
    --arg phase_detail "$_PHASE_DETAIL" '
    {
        session_id: $session_id,
        sprint_id: $sprint_id,
        host: $host,
        timestamp: $timestamp,
        loops: {
            routing: {
                outcome: $routing_outcome,
                before_hash: $routing_before,
                after_hash: $routing_after,
                evidence_count: $routing_evidence,
                detail: $routing_detail
            },
            gate_threshold: {
                outcome: $gate_outcome,
                before_hash: $gate_before,
                after_hash: $gate_after,
                evidence_count: $gate_evidence,
                detail: $gate_detail
            },
            phase_cost: {
                outcome: $phase_outcome,
                before_hash: $phase_before,
                after_hash: $phase_after,
                evidence_count: $phase_evidence,
                detail: $phase_detail
            }
        }
    }
')" || exit 0

printf '%s\n' "$_RECEIPT" | \
    clavain-cli calibration-streak record-receipt --root="$_PROOF_ROOT" \
    >/dev/null 2>&1 || true

exit 0
