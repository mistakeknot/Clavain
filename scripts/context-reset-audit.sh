#!/usr/bin/env bash
# context-reset-audit.sh — reconcile a session transcript against observe-mode
# context-reset telemetry (mk-42j9.40).
#
# NOT A SECURITY BOUNDARY. This re-classifies the transcript's tool calls and
# reports exposure and approval actions that the hooks did not log, for example
# on hosts or child agents where the hooks do not run. Exposure is compared per
# epoch and per accounting batch (the same batch_max_reads / batch_max_seconds
# windows the hooks use, restarted at each compaction). A surplus of logged
# batches in one epoch never offsets a shortfall in another. Batch windows use
# each call's tool_result timestamp, which is closest to the completion time
# the hooks batch by, falling back to the assistant message timestamp.
# Task/Agent and uncovered-child calls are checked separately: the hooks log
# them as exposure_unknown only when the epoch was clean, so the audit replays
# that state and reports a missing exposure_unknown row as
# missed.subagent_unknown (uncertain exposure, not a definite one). With
# --record it appends idempotent coverage_gap rows (surface=audit). It never
# blocks or resets.
#
# Usage: context-reset-audit.sh --transcript FILE [--session ID] [--store DIR] [--record] [--json]
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || script_dir="."
transcript="" session="" record=0 json=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --transcript) transcript="${2:-}"; shift 2 || shift ;;
        --session) session="${2:-}"; shift 2 || shift ;;
        --store) export CLAVAIN_CONTEXT_RESET_DIR="${2:-}"; shift 2 || shift ;;
        --record) record=1; shift ;;
        --json) json=1; shift ;;
        -h|--help)
            printf 'Usage: context-reset-audit.sh --transcript FILE [--session ID] [--store DIR] [--record] [--json]\n'
            printf 'Observe-mode telemetry only; NOT a security boundary.\n'
            exit 0 ;;
        *) printf 'context-reset-audit: unknown argument %s\n' "$1" >&2; exit 2 ;;
    esac
done

if [[ -z "$transcript" || ! -r "$transcript" ]]; then
    printf 'context-reset-audit: --transcript FILE is required and must be readable\n' >&2
    exit 2
fi
command -v jq >/dev/null 2>&1 || { printf 'context-reset-audit: jq is required\n' >&2; exit 2; }
# shellcheck source=hooks/lib-context-reset.sh
source "$script_dir/../hooks/lib-context-reset.sh" || { printf 'context-reset-audit: cannot load lib-context-reset.sh\n' >&2; exit 2; }

store=$(cr_store_dir)
events="$store/events.jsonl"
src="$events"
[[ -r "$src" ]] || src=/dev/null

if [[ -z "$session" ]]; then
    session=$(jq -Rnr '[inputs | fromjson? | objects | .sessionId? // empty | strings] | first // ""' "$transcript" 2>/dev/null) || session=""
fi
if [[ -z "$session" ]]; then
    session=$(basename "$transcript")
    session="${session%.jsonl}"
fi

max_reads=$(cr_config_int batch_max_reads 20)
max_secs=$(cr_config_int batch_max_seconds 600)

# The transcript's first epoch is the one the hooks opened at startup/clear
# (the first such session_start row for this session), else 1, as
# cr_session_start numbers a fresh session. Each compaction adds one.
base_epoch=$(jq -Rnr --arg s "$session" '[inputs | fromjson? | objects
    | select(.session == $s and (.agent // "") == "" and .event == "session_start"
        and (.source == "startup" or .source == "clear"))
    | .epoch | numbers | floor] | first // 1' "$src" 2>/dev/null) || base_epoch=1
[[ "$base_epoch" =~ ^[0-9]+$ ]] || base_epoch=1

# Replay: ep is the epoch index (0 = base_epoch); exp_b[ep] counts expected
# batches in it. state mirrors the hooks' exposure (clean at startup, carried
# over compaction) to know when an exposure_unknown row is due.
tool_uses=0 expected_exposure=0 expected_batches=0 expected_approval=0
subagent_calls=0 expected_subagent=0
ep=0 b_reads=0 b_start="" state=clean
exp_b=(0)
while IFS=$'\t' read -r kind ts tu; do
    if [[ "$kind" == B ]]; then
        # Compaction opens a new epoch, whose first read the hooks log.
        ep=$((ep + 1))
        exp_b[ep]=0
        b_reads=0
        b_start=""
        continue
    fi
    [[ "$kind" == T && -n "${tu:-}" ]] || continue
    tool_uses=$((tool_uses + 1))
    payload=$(jq -c --arg s "$session" '{session_id: $s, hook_event_name: "PostToolUse",
        tool_name: .name, tool_input: .input}' <<<"$tu" 2>/dev/null) || continue
    cr_parse_payload "$payload" || continue
    cr_classify
    case "$CR_EXPOSURE_CLASS" in
        "")
            if [[ -n "$CR_EXPOSURE_GAP" && "$state" == clean ]]; then state=unknown; fi ;;
        child-uncovered|subagent-result)
            subagent_calls=$((subagent_calls + 1))
            if [[ "$state" == clean ]]; then
                expected_subagent=$((expected_subagent + 1))
                state=unknown
            fi ;;
        *)
            state=exposed
            expected_exposure=$((expected_exposure + 1))
            [[ "$ts" =~ ^[0-9]+$ ]] || ts=""
            if (( b_reads == 0 || b_reads >= max_reads )) \
                || [[ -n "$ts" && -n "$b_start" && $((ts - b_start)) -ge $max_secs ]]; then
                expected_batches=$((expected_batches + 1))
                exp_b[ep]=$(( ${exp_b[ep]:-0} + 1 ))
                b_reads=1
                b_start="$ts"
            else
                b_reads=$((b_reads + 1))
            fi ;;
    esac
    if [[ -n "$CR_APPROVAL_FAMILY" ]]; then
        expected_approval=$((expected_approval + 1))
    fi
done < <(jq -Rnr '
    def tsnum: if type == "string" and . != ""
        then (sub("\\.[0-9]+"; "") | try (fromdateiso8601 | floor | tostring) catch "-")
        else "-" end;
    [inputs | fromjson? | objects] as $rows
    | ([$rows[] | select(.type == "user") | (.timestamp | tsnum) as $ts
        | .message.content? | arrays | .[] | objects | select(.type == "tool_result")
        | select((.tool_use_id | type) == "string") | {key: .tool_use_id, value: $ts}]
       | from_entries) as $done
    | $rows[]
    | if (.type == "system" and .subtype == "compact_boundary") then "B"
      elif .type == "assistant" then
        (.timestamp | tsnum) as $ts
        | .message.content? | arrays | .[] | objects | select(.type == "tool_use")
        | (if (.id | type) == "string" then ($done[.id] // "-") else "-" end) as $d
        | (if $d != "-" then $d else $ts end) as $cts
        | "T\t\($cts)\t\({name: (.name // ""), input: (.input // {})} | tojson)"
      else empty end' "$transcript" 2>/dev/null)

# Only this session's parent rows: a transcript holds the parent's tool calls,
# and child agents keep their own state (rows with a non-empty agent). The
# first line holds totals; each following line is one exposure row's epoch.
logged_rows=$(jq -Rnr --arg s "$session" '[inputs | fromjson? | objects | select(.session == $s and (.agent // "") == "")] as $r
    | "\($r | map(select(.event == "exposure")) | length) \($r | map(select(.event == "would_be_reset" or .event == "approval_clean")) | length) \($r | map(select(.event == "exposure_unknown" and (.source_class == "child-uncovered" or .source_class == "subagent-result"))) | length)",
      ($r[] | select(.event == "exposure") | .epoch | numbers | floor | tostring)' \
    "$src" 2>/dev/null) || logged_rows=""
logged_exposure=0 logged_approval=0 logged_subagent=0
log_b=()
first=1
while IFS= read -r line; do
    if (( first )); then
        read -r logged_exposure logged_approval logged_subagent <<<"$line"
        first=0
        continue
    fi
    [[ "$line" =~ ^[0-9]+$ ]] || continue
    k=$((line - base_epoch))
    if (( k < 0 || k > ep )); then continue; fi
    log_b[k]=$(( ${log_b[k]:-0} + 1 ))
done <<<"$logged_rows"
[[ "${logged_exposure:-}" =~ ^[0-9]+$ ]] || logged_exposure=0
[[ "${logged_approval:-}" =~ ^[0-9]+$ ]] || logged_approval=0
[[ "${logged_subagent:-}" =~ ^[0-9]+$ ]] || logged_subagent=0

# Each accounting batch is logged as one exposure row, so compare batches per
# epoch and sum only the shortfalls.
missed_exposure=0
for ((k = 0; k <= ep; k++)); do
    d=$(( ${exp_b[k]:-0} - ${log_b[k]:-0} ))
    if (( d > 0 )); then missed_exposure=$((missed_exposure + d)); fi
done
missed_approval=$((expected_approval - logged_approval))
if (( missed_approval < 0 )); then missed_approval=0; fi
missed_subagent=$((expected_subagent - logged_subagent))
if (( missed_subagent < 0 )); then missed_subagent=0; fi

recorded=()
if (( record )); then
    mode=$(cr_mode)
    if [[ "$mode" != observe ]]; then
        printf 'context-reset-audit: not recording, mode is %s (observe-mode telemetry only, NOT a security boundary)\n' "$mode" >&2
    else
        CR_SID="$session" CR_AGENT="" CR_TOOL="" CR_REF="" CR_S_EPOCH=0
        for pair in "audit_missed_exposure:$missed_exposure" "audit_missed_approval:$missed_approval" \
            "audit_missed_subagent_unknown:$missed_subagent"; do
            kind="${pair%%:*}"
            n="${pair##*:}"
            (( n > 0 )) || continue
            ref=$(cr_hash "$session|$kind")
            src="$events"
            [[ -r "$src" ]] || src=/dev/null
            prev=$(jq -Rn --arg r "$ref" '[inputs | fromjson? | objects
                | select(.event == "coverage_gap" and .audit_ref == $r) | (.count // 0)] | max // 0' "$src" 2>/dev/null) || prev=0
            [[ "$prev" =~ ^[0-9]+$ ]] || prev=0
            (( prev >= n )) && continue
            cr_emit coverage_gap surface=audit "kind=$kind" "count:=$n" "audit_ref=$ref"
            recorded+=("$kind")
        done
    fi
fi

if (( json )); then
    jq -n --arg session "$session" --argjson tool_uses "$tool_uses" \
        --argjson ee "$expected_exposure" --argjson eb "$expected_batches" --argjson ea "$expected_approval" \
        --argjson es "$expected_subagent" --argjson sc "$subagent_calls" \
        --argjson le "$logged_exposure" --argjson la "$logged_approval" --argjson ls "$logged_subagent" \
        --argjson me "$missed_exposure" --argjson ma "$missed_approval" --argjson ms "$missed_subagent" \
        --argjson be "$base_epoch" --argjson epochs "$((ep + 1))" \
        '{session: $session, tool_uses: $tool_uses, base_epoch: $be, epochs: $epochs,
          expected: {exposure: $ee, exposure_batches: $eb, approval: $ea,
                     subagent_calls: $sc, subagent_unknown: $es},
          logged: {exposure: $le, approval: $la, subagent_unknown: $ls},
          missed: {exposure: $me, approval: $ma, subagent_unknown: $ms},
          recorded: $ARGS.positional,
          security_boundary: false,
          note: "observe-mode hygiene telemetry audit; NOT a security boundary"}' \
        --args ${recorded[@]+"${recorded[@]}"}
else
    printf 'Context-reset audit (observe-mode telemetry only, NOT a security boundary)\n'
    printf 'session: %s   tool uses: %s   epochs: %s (from %s)\n' "$session" "$tool_uses" "$((ep + 1))" "$base_epoch"
    printf 'expected: exposure %s in %s batches, approval %s, subagent/child unknown rows %s (of %s calls)\n' \
        "$expected_exposure" "$expected_batches" "$expected_approval" "$expected_subagent" "$subagent_calls"
    printf 'logged:   exposure batches %s, approval %s, subagent/child unknown %s\n' \
        "$logged_exposure" "$logged_approval" "$logged_subagent"
    printf 'missed:   exposure batches %s (per epoch), approval %s, subagent/child unknown %s\n' \
        "$missed_exposure" "$missed_approval" "$missed_subagent"
    printf 'recorded: %s\n' "${recorded[*]:-none}"
fi
exit 0
