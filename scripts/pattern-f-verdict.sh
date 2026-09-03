#!/usr/bin/env bash
# pattern-f-verdict.sh — write ONE Pattern F verdict into the interspect
# evidence register, then read it back. "If a verdict is not in the register,
# it did not happen." The existing call sites of the interspect library swallow
# insert failures (|| true); this script must not, so every write is checked by
# a nonce read-back and a missing row is a non-zero exit.
#
# Each call inserts one evidence row:
#   event=pattern_f_verdict  source=pattern-f:<role>  source_kind=agent
#   context={"path":"pattern-f","verdict_kind":K,"verdict":V,"role":R,
#            "plan":<basename of --plan>,"commit":C,"criterion":<=100 chars,
#            "note":<=100 chars,"goal":G,"nonce":N}
#
# Verdict kinds (--kind):
#   replay      the plan's VERIFY block was re-run — by the executor right after
#               its edits, or by the validator at the executor's commit — and
#               --verdict says whether every VERIFY line passed. A FAIL replay
#               names the failing VERIFY line in --criterion.
#   independent a finding the VERIFY block did not check: the validator's second
#               channel ("BEYOND THE GAUGE"). Independent rows carry
#               --verdict FAIL and the finding text in --note, one row per
#               finding.
#
# Usage:
#   pattern-f-verdict.sh --session ID --plan PATH --commit HASH|none \
#       --role executor|validator --kind replay|independent --verdict PASS|FAIL \
#       [--criterion TEXT] [--note TEXT] [--goal ID] [--db PATH]
#   pattern-f-verdict.sh --list [--session ID] [--db PATH]
#
# Register resolution: --db, else $INTERSPECT_DB, else
# <repo root>/.clavain/interspect/interspect.db where repo root is the parent
# of this script's directory. The register is never created here.
#
# Exit codes: 0 recorded (or listed); 2 usage error; 3 register missing or
# interspect library not found; 4 the write was not visible on read-back.
#
# The context JSON is held under 480 characters: the library truncates the
# context column to 500 characters, and a truncated JSON is unreadable.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: pattern-f-verdict.sh --session ID --plan PATH --commit HASH|none
           --role executor|validator --kind replay|independent --verdict PASS|FAIL
           [--criterion TEXT] [--note TEXT] [--goal ID] [--db PATH]
       pattern-f-verdict.sh --list [--session ID] [--db PATH]
USAGE
  exit 2
}

bad() {
  echo "pattern-f-verdict: $1" >&2
  usage
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mode=record
session=""
plan=""
commit=""
role=""
kind=""
verdict=""
criterion=""
note=""
goal=""
db=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list)
      mode=list
      shift
      ;;
    --session|--plan|--commit|--role|--kind|--verdict|--criterion|--note|--goal|--db)
      [[ $# -ge 2 ]] || bad "missing value for $1"
      case "$1" in
        --session) session="$2" ;;
        --plan) plan="$2" ;;
        --commit) commit="$2" ;;
        --role) role="$2" ;;
        --kind) kind="$2" ;;
        --verdict) verdict="$2" ;;
        --criterion) criterion="$2" ;;
        --note) note="$2" ;;
        --goal) goal="$2" ;;
        --db) db="$2" ;;
      esac
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      bad "unknown argument: $1"
      ;;
  esac
done

if [[ "$mode" == record ]]; then
  [[ -n "$session" ]] || bad "--session is required"
  [[ -n "$plan" ]] || bad "--plan is required"
  [[ "$commit" == none || "$commit" =~ ^[0-9a-f]{7,40}$ ]] || bad "--commit must be a hex hash (7-40 chars) or none"
  case "$role" in
    executor|validator) ;;
    *) bad "--role must be executor or validator" ;;
  esac
  case "$kind" in
    replay|independent) ;;
    *) bad "--kind must be replay or independent" ;;
  esac
  case "$verdict" in
    PASS|FAIL) ;;
    *) bad "--verdict must be PASS or FAIL" ;;
  esac
fi

# ── Register DB resolution (never created here) ─────────────────────────────
if [[ -z "$db" ]]; then
  db="${INTERSPECT_DB:-$repo_root/.clavain/interspect/interspect.db}"
fi
if [[ ! -f "$db" ]]; then
  echo "pattern-f-verdict: register missing: $db" >&2
  exit 3
fi

sql_quote() {
  printf '%s' "${1//\'/\'\'}"
}

# ── --list: no library needed, just the register ────────────────────────────
if [[ "$mode" == list ]]; then
  where="event='pattern_f_verdict' and json_valid(context)"
  if [[ -n "$session" ]]; then
    where="$where and session_id='$(sql_quote "$session")'"
  fi
  sqlite3 -noheader -separator $'\t' "$db" \
    "select ts, session_id, json_extract(context,'\$.role'), json_extract(context,'\$.verdict_kind'), json_extract(context,'\$.verdict'), json_extract(context,'\$.plan'), json_extract(context,'\$.commit'), json_extract(context,'\$.note') from evidence where $where order by ts;"
  exit 0
fi

# ── Locate the interspect library ───────────────────────────────────────────
lib_missing() {
  echo "pattern-f-verdict: interspect library not found" >&2
  exit 3
}
# shellcheck source=/dev/null
source "$repo_root/hooks/lib.sh" 2>/dev/null || lib_missing
iroot=$(_discover_interspect_plugin 2>/dev/null) || iroot=""
[[ -n "$iroot" && -f "$iroot/hooks/lib-interspect.sh" ]] || lib_missing
# shellcheck source=/dev/null
source "$iroot/hooks/lib-interspect.sh" 2>/dev/null || lib_missing

# The insert function reads ${_INTERSPECT_DB:-$(_interspect_db_path)}; point it
# at the resolved register. Do NOT call _interspect_ensure_db (it re-resolves).
export _INTERSPECT_DB="$db"

# ── Build the context JSON (kept under 480 chars, see header) ───────────────
nonce="$(date +%s)-$$-$RANDOM"
plan_base=$(basename "$plan")
lim_c=100
lim_n=100
build_ctx() {
  jq -nc \
    --arg k "$kind" --arg v "$verdict" --arg r "$role" \
    --arg p "${plan_base:0:80}" --arg c "$commit" \
    --arg cr "${criterion:0:$lim_c}" --arg n "${note:0:$lim_n}" \
    --arg g "${goal:0:40}" --arg x "$nonce" \
    '{path:"pattern-f",verdict_kind:$k,verdict:$v,role:$r,plan:$p,commit:$c,criterion:$cr,note:$n,goal:$g,nonce:$x}'
}
ctx=$(build_ctx)
while (( ${#ctx} > 480 )) && (( lim_n > 0 )); do
  lim_n=$(( lim_n - 20 ))
  ctx=$(build_ctx)
done
while (( ${#ctx} > 480 )) && (( lim_c > 0 )); do
  lim_c=$(( lim_c - 20 ))
  ctx=$(build_ctx)
done

# ── Insert (rc captured, never silenced) ────────────────────────────────────
insert_rc=0
_interspect_insert_evidence "$session" "pattern-f:$role" "pattern_f_verdict" "" "$ctx" "" "" "" "" "agent" || insert_rc=$?
if [[ "$insert_rc" -ne 0 ]]; then
  echo "pattern-f-verdict: register insert returned rc=$insert_rc" >&2
fi

# ── Read back, always ───────────────────────────────────────────────────────
count=$(sqlite3 "$db" "select count(*) from evidence where event='pattern_f_verdict' and json_valid(context) and json_extract(context,'\$.nonce')='$nonce';" 2>&1) || count="error: $count"
if [[ "$count" != "1" ]]; then
  echo "pattern-f-verdict: write not visible in register ($db)" >&2
  echo "pattern-f-verdict: insert rc=$insert_rc, read-back result: $count" >&2
  exit 4
fi

echo "pattern-f-verdict: recorded $role $kind $verdict -> $db"
exit 0
