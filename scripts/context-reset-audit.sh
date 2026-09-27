#!/usr/bin/env bash
# context-reset-audit.sh — reconcile a session transcript against observe-mode
# context-reset telemetry (mk-42j9.40).
#
# NOT A SECURITY BOUNDARY. This re-classifies the transcript's tool calls and
# reports exposure and approval actions that the hooks did not log, for example
# on hosts or child agents where the hooks do not run. Exposure is compared per
# accounting batch (the same batch_max_reads / batch_max_seconds windows the
# hooks use, restarted at each compaction), so one logged batch cannot hide a
# later missed one. With --record it appends idempotent coverage_gap rows
# (surface=audit). It never blocks or resets.
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

if [[ -z "$session" ]]; then
    session=$(jq -Rnr '[inputs | fromjson? | objects | .sessionId? // empty | strings] | first // ""' "$transcript" 2>/dev/null) || session=""
fi
if [[ -z "$session" ]]; then
    session=$(basename "$transcript")
    session="${session%.jsonl}"
fi

max_reads=$(cr_config_int batch_max_reads 20)
max_secs=$(cr_config_int batch_max_seconds 600)

tool_uses=0 expected_exposure=0 expected_batches=0 expected_approval=0
b_reads=0 b_start=""
while IFS=$'\t' read -r kind ts tu; do
    if [[ "$kind" == B ]]; then
        # Compaction opens a new epoch, whose first read the hooks log.
        b_reads=0
        continue
    fi
    [[ "$kind" == T && -n "${tu:-}" ]] || continue
    tool_uses=$((tool_uses + 1))
    payload=$(jq -c --arg s "$session" '{session_id: $s, hook_event_name: "PostToolUse",
        tool_name: .name, tool_input: .input}' <<<"$tu" 2>/dev/null) || continue
    cr_parse_payload "$payload" || continue
    cr_classify
    if [[ -n "$CR_EXPOSURE_CLASS" && "$CR_EXPOSURE_CLASS" != child-uncovered && "$CR_EXPOSURE_CLASS" != subagent-result ]]; then
        expected_exposure=$((expected_exposure + 1))
        [[ "$ts" =~ ^[0-9]+$ ]] || ts=""
        if (( b_reads == 0 || b_reads >= max_reads )) \
            || [[ -n "$ts" && -n "$b_start" && $((ts - b_start)) -ge $max_secs ]]; then
            expected_batches=$((expected_batches + 1))
            b_reads=1
            b_start="$ts"
        else
            b_reads=$((b_reads + 1))
        fi
    fi
    if [[ -n "$CR_APPROVAL_FAMILY" ]]; then
        expected_approval=$((expected_approval + 1))
    fi
done < <(jq -Rr 'fromjson? | objects
    | if (.type == "system" and .subtype == "compact_boundary") then "B"
      elif .type == "assistant" then
        ((.timestamp // "") | if type == "string" and . != ""
            then (sub("\\.[0-9]+"; "") | try (fromdateiso8601 | floor | tostring) catch "-")
            else "-" end) as $ts
        | .message.content? | arrays | .[] | objects | select(.type == "tool_use")
        | "T\t\($ts)\t\({name: (.name // ""), input: (.input // {})} | tojson)"
      else empty end' "$transcript" 2>/dev/null)

# Only this session's parent rows: a transcript holds the parent's tool calls,
# and child agents keep their own state (rows with a non-empty agent).
src="$events"
[[ -r "$src" ]] || src=/dev/null
logged=$(jq -Rnr --arg s "$session" '[inputs | fromjson? | objects | select(.session == $s and (.agent // "") == "")]
    | "\(map(select(.event == "exposure")) | length) \(map(select(.event == "would_be_reset" or .event == "approval_clean")) | length)"' \
    "$src" 2>/dev/null) || logged="0 0"
read -r logged_exposure logged_approval <<<"$logged"
[[ "${logged_exposure:-}" =~ ^[0-9]+$ ]] || logged_exposure=0
[[ "${logged_approval:-}" =~ ^[0-9]+$ ]] || logged_approval=0

# Each accounting batch is logged as one exposure row, so compare batches.
missed_exposure=$((expected_batches - logged_exposure))
if (( missed_exposure < 0 )); then missed_exposure=0; fi
missed_approval=$((expected_approval - logged_approval))
if (( missed_approval < 0 )); then missed_approval=0; fi

recorded=()
if (( record )); then
    mode=$(cr_mode)
    if [[ "$mode" != observe ]]; then
        printf 'context-reset-audit: not recording, mode is %s (observe-mode telemetry only, NOT a security boundary)\n' "$mode" >&2
    else
        CR_SID="$session" CR_AGENT="" CR_TOOL="" CR_REF="" CR_S_EPOCH=0
        for pair in "audit_missed_exposure:$missed_exposure" "audit_missed_approval:$missed_approval"; do
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
        --argjson le "$logged_exposure" --argjson la "$logged_approval" \
        --argjson me "$missed_exposure" --argjson ma "$missed_approval" \
        '{session: $session, tool_uses: $tool_uses,
          expected: {exposure: $ee, exposure_batches: $eb, approval: $ea},
          logged: {exposure: $le, approval: $la},
          missed: {exposure: $me, approval: $ma},
          recorded: $ARGS.positional,
          security_boundary: false,
          note: "observe-mode hygiene telemetry audit; NOT a security boundary"}' \
        --args ${recorded[@]+"${recorded[@]}"}
else
    printf 'Context-reset audit (observe-mode telemetry only, NOT a security boundary)\n'
    printf 'session: %s   tool uses: %s\n' "$session" "$tool_uses"
    printf 'expected: exposure %s in %s batches, approval %s\n' "$expected_exposure" "$expected_batches" "$expected_approval"
    printf 'logged:   exposure batches %s, approval %s\n' "$logged_exposure" "$logged_approval"
    printf 'missed:   exposure batches %s, approval %s\n' "$missed_exposure" "$missed_approval"
    printf 'recorded: %s\n' "${recorded[*]:-none}"
fi
exit 0