#!/usr/bin/env bash
# context-reset-report.sh — summarise observe-mode context-reset telemetry (mk-42j9.40).
#
# NOT A SECURITY BOUNDARY. This reports what a context-reset rule *would* have
# done. It counts exposure epochs and research batches, would-be resets split
# exposed/unknown vs clean, and coverage gaps. It estimates the cache cost
# H x (cache-write - cache-read) for approval-triggered resets and for
# research-triggered (full-mode) resets, and breaks the totals down by role and
# mode. Nothing was blocked or reset.
#
# Usage: context-reset-report.sh [--store DIR] [--session ID] [--json] [--input-usd-per-mtok N]
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || script_dir="."
session="" json=0 usd=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --store) export CLAVAIN_CONTEXT_RESET_DIR="${2:-}"; shift 2 || shift ;;
        --session) session="${2:-}"; shift 2 || shift ;;
        --json) json=1; shift ;;
        --input-usd-per-mtok) usd="${2:-}"; shift 2 || shift ;;
        -h|--help)
            printf 'Usage: context-reset-report.sh [--store DIR] [--session ID] [--json] [--input-usd-per-mtok N]\n'
            printf 'Observe-mode telemetry only; NOT a security boundary.\n'
            exit 0 ;;
        *) printf 'context-reset-report: unknown argument %s\n' "$1" >&2; exit 2 ;;
    esac
done

command -v jq >/dev/null 2>&1 || { printf 'context-reset-report: jq is required\n' >&2; exit 2; }
# shellcheck source=hooks/lib-context-reset.sh
source "$script_dir/../hooks/lib-context-reset.sh" || { printf 'context-reset-report: cannot load lib-context-reset.sh\n' >&2; exit 2; }

mode=$(cr_mode)
case "$mode" in
    observe|off) ;;
    *) printf 'context-reset-report: configured mode %s is not implemented in this phase; hooks record nothing (observe-mode telemetry only, NOT a security boundary)\n' "$mode" >&2 ;;
esac

w=$(cr_config_float cache_write_weight 1.25)
r=$(cr_config_float cache_read_weight 0.1)
[[ -n "$usd" ]] || usd=$(cr_config_float input_usd_per_mtok 0)
[[ "$usd" =~ ^[0-9]+(\.[0-9]+)?$ ]] || usd=0

src="$(cr_store_dir)/events.jsonl"
[[ -r "$src" ]] || src=/dev/null

report=$(jq -Rn --arg session "$session" --argjson w "$w" --argjson r "$r" --argjson usd "$usd" '
  def cnt(f): map(select(f)) | length;
  def r2: (. * 100 | round) / 100;
  def costset($rows):
    ($rows | map(.context_tokens | select(type == "number"))) as $h
    | ($h | add // 0) as $H
    | { resets: ($rows | length),
        tokens_known: ($h | length),
        missing_h: (($rows | length) - ($h | length)),
        input_token_equivalents: (($H * ($w - $r)) | round),
        usd: (if $usd > 0 then ((($H * ($w - $r)) / 1000000 * $usd) | r2) else null end) };
  def gaps:
    map(select(.event == "coverage_gap")) as $g
    | ($g | map(select(.surface != "audit"))) as $live
    | ($g | map(select(.surface == "audit")) | group_by(.audit_ref) | map(max_by(.count // 1))) as $audit
    | ($live + $audit) as $all
    | { total: ($all | map(.count // 1) | add // 0),
        by_kind: ($all | group_by(.kind) | map({key: (.[0].kind // "unknown"), value: (map(.count // 1) | add)}) | from_entries) };
  def agg:
    . as $rows
    | ($rows | map(.session // "" | select(. != "")) | unique | length) as $sessions
    | ($rows | map(select(.event == "would_be_reset"))) as $wbr
    | ($rows | map(select(.event == "approval_clean"))) as $clean
    | ($rows | map(select(.event == "exposure"))) as $exp
    | ($rows | map(select((.event == "would_be_reset" or .event == "approval_clean") and .simulated_reset == true))) as $sim
    | ([$sessions, 1] | max) as $n
    | { sessions: $sessions,
        session_starts: cnt(.event == "session_start"),
        exposure_epochs: ($exp | cnt(.first_in_epoch == true)),
        research_batches: ($exp | length),
        unknown_transitions: cnt(.event == "exposure_unknown"),
        would_be_resets: { exposed: ($wbr | cnt(.exposure == "exposed")), unknown: ($wbr | cnt(.exposure != "exposed")) },
        simulated_approval_resets: ($sim | length),
        approval_actions_clean: ($clean | length),
        by_family: (($wbr + $clean) | group_by(.family)
          | map({key: (.[0].family // "unknown"),
                 value: {would_be_reset: cnt(.event == "would_be_reset"), clean: cnt(.event == "approval_clean")}})
          | from_entries),
        coverage_gaps: gaps,
        hook_errors: cnt(.event == "hook_error"),
        resets_per_session: {
          approval_mode: (($sim | length) / $n | r2),
          every_sensitive_action: ((($wbr | length) + ($clean | length)) / $n | r2),
          full_mode_upper_bound: ((($sim | length) + ($exp | length)) / $n | r2) },
        cost: {
          approval_mode: costset($sim),
          all_would_be_resets: costset($wbr),
          every_sensitive_action: costset($wbr + $clean),
          research_batches: costset($exp),
          full_mode_upper_bound: costset($sim + $exp) } };
  [inputs | fromjson? | objects]
  | if $session != "" then map(select(.session == $session)) else . end
  | . as $all
  | agg + {
      security_boundary: false,
      note: "observe-mode hygiene telemetry; NOT a security boundary; nothing was blocked or reset",
      weights: {cache_write: $w, cache_read: $r},
      cost_unit: (if $usd > 0 then "usd" else "input_token_equivalents" end),
      by_role: ($all | group_by(.role // "unknown") | map({key: (.[0].role // "unknown"), value: agg}) | from_entries),
      by_mode: ($all | group_by(.mode // "unknown") | map({key: (.[0].mode // "unknown"), value: agg}) | from_entries) }
' "$src" 2>/dev/null) || { printf 'context-reset-report: could not read %s\n' "$src" >&2; exit 1; }

if (( json )); then
    printf '%s\n' "$report"
    exit 0
fi

printf '%s\n' "$report" | jq -r '
  def c: (if .usd != null then "USD \(.usd)" else "\(.input_token_equivalents) input-token-equivalents" end)
         + " over \(.resets) resets (\(.missing_h) without H)";
  "Context-reset telemetry (observe mode): NOT a security boundary; nothing was blocked or reset.",
  "sessions: \(.sessions)   session starts: \(.session_starts)",
  "exposure epochs: \(.exposure_epochs)   research batches: \(.research_batches)   unknown transitions: \(.unknown_transitions)",
  "would-be resets: exposed \(.would_be_resets.exposed), unknown \(.would_be_resets.unknown)   clean approval actions: \(.approval_actions_clean)",
  "simulated approval-mode resets: \(.simulated_approval_resets)",
  "resets per session: approval \(.resets_per_session.approval_mode), every sensitive action \(.resets_per_session.every_sensitive_action), full (upper bound) \(.resets_per_session.full_mode_upper_bound)",
  "by family: \(.by_family | to_entries | map("\(.key) \(.value.would_be_reset)/\(.value.clean)") | join(", "))  (would-be/clean)",
  "coverage gaps: \(.coverage_gaps.total)  \(.coverage_gaps.by_kind | to_entries | map("\(.key)=\(.value)") | join(" "))",
  "hook errors: \(.hook_errors)",
  "cost, H x (write \(.weights.cache_write) - read \(.weights.cache_read)):",
  "  approval mode:          \(.cost.approval_mode | c)",
  "  all would-be resets:    \(.cost.all_would_be_resets | c)",
  "  every sensitive action: \(.cost.every_sensitive_action | c)",
  "  research batches:       \(.cost.research_batches | c)",
  "  full mode (upper bound): \(.cost.full_mode_upper_bound | c)",
  (.by_role | to_entries[] | "role \(.key): would-be resets \(.value.would_be_resets.exposed + .value.would_be_resets.unknown), clean \(.value.approval_actions_clean), exposure epochs \(.value.exposure_epochs), gaps \(.value.coverage_gaps.total)"),
  (.by_mode | to_entries[] | "mode \(.key): would-be resets \(.value.would_be_resets.exposed + .value.would_be_resets.unknown), clean \(.value.approval_actions_clean), exposure epochs \(.value.exposure_epochs), gaps \(.value.coverage_gaps.total)")
'
exit 0