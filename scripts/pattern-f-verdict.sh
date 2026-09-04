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
#            "note":<=300 chars,"note_enc":""|"b64","goal":G,"nonce":N}
#   The note is kept to 300 chars and shrunk (note first, then criterion)
#   only when the context would otherwise exceed 480 chars.
#   note_enc is "b64" when the register's sanitizer rejected the plain context
#   (it refuses text containing phrases such as "ignore previous" or
#   "system:"); criterion and note are then stored base64-encoded and --list
#   decodes them. A verdict is never silently blanked or dropped.
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
#   gate        the PreToolUse gauge gate refused an executor spawn. --role gate,
#               --commit none, --verdict FAIL, and --note carries the refusal
#               reason (the linter's GAUGE lines). --kind gate pairs only with
#               --role gate.
#
# Usage:
#   pattern-f-verdict.sh --session ID --plan PATH --commit HASH|none \
#       --role executor|validator|gate --kind replay|independent|gate \
#       --verdict PASS|FAIL [--criterion TEXT] [--note TEXT] [--goal ID] [--db PATH]
#   pattern-f-verdict.sh --list [--session ID] [--db PATH]
#
# Register resolution: --db, else $INTERSPECT_DB, else
# <repo root>/.clavain/interspect/interspect.db where repo root is the parent
# of this script's directory. The register is never created here.
#
# Exit codes: 0 recorded (or listed); 2 usage error; 3 register missing or
# interspect library not found; 4 the write was not visible on read-back;
# 5 context rejected by the sanitizer even after encoding, or still over
#   480 chars after encoding and shrinking (nothing written).
#
# The context JSON is held under 480 characters: the library truncates the
# context column to 500 characters, and a truncated JSON is unreadable.
set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
usage: pattern-f-verdict.sh --session ID --plan PATH --commit HASH|none
           --role executor|validator|gate --kind replay|independent|gate --verdict PASS|FAIL
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
    executor|validator|gate) ;;
    *) bad "--role must be executor, validator or gate" ;;
  esac
  case "$kind" in
    replay|independent|gate) ;;
    *) bad "--kind must be replay, independent or gate" ;;
  esac
  if [[ "$role" == gate || "$kind" == gate ]] && [[ "$role" != "$kind" ]]; then
    bad "--kind gate pairs with --role gate"
  fi
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
  # One TSV line per row, eight columns: ts, session, role, kind, verdict,
  # plan, commit, note. Encoded notes are decoded; tabs and newlines inside
  # any field become spaces so every row stays on one parseable line. The
  # fields are joined with a literal tab rather than @tsv, which would escape
  # backslashes, so a note quoting a regex or a Windows path lists verbatim.
  sqlite3 -json "$db" "select ts, session_id, context from evidence where $where order by ts;" \
    | jq -r '.[] | (.context|fromjson) as $c
             | [.ts, .session_id, $c.role, $c.verdict_kind, $c.verdict, $c.plan, $c.commit,
                (if $c.note_enc == "b64" then ($c.note|@base64d) else $c.note end)]
             | map((. // "") | tostring | gsub("[\t\r\n]"; " ")) | join("\t")'
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
lim_n=300
# enc is "" (plain) or "b64": when the register's sanitizer rejects the plain
# context, criterion and note are base64-encoded and note_enc records that.
enc=""
build_ctx() {
  jq -nc \
    --arg k "$kind" --arg v "$verdict" --arg r "$role" \
    --arg p "${plan_base:0:80}" --arg c "$commit" \
    --arg cr "${criterion:0:$lim_c}" --arg n "${note:0:$lim_n}" \
    --arg g "${goal:0:40}" --arg x "$nonce" --arg enc "$enc" \
    '{path:"pattern-f",verdict_kind:$k,verdict:$v,role:$r,plan:$p,commit:$c,criterion:(if $enc=="b64" then ($cr|@base64) else $cr end),note:(if $enc=="b64" then ($n|@base64) else $n end),note_enc:$enc,goal:$g,nonce:$x}'
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

# Pre-flight the sanitizer. _interspect_insert_evidence runs _interspect_sanitize
# on the context and, when the sanitizer rejects it (rc 1, empty output), still
# inserts context='' with rc 0: an orphan row and exit 4 here. Ask the sanitizer
# first; on rejection encode criterion and note (note_enc=b64) and re-shrink, so
# the verdict survives (note first, then criterion). Exit 5 if the encoded
# context is still over 480 chars, or is rejected even after encoding.
if ! _interspect_sanitize "$ctx" >/dev/null 2>&1; then
  enc=b64
  ctx=$(build_ctx)
  while (( ${#ctx} > 480 )) && (( lim_n > 0 )); do
    lim_n=$(( lim_n - 20 ))
    ctx=$(build_ctx)
  done
  while (( ${#ctx} > 480 )) && (( lim_c > 0 )); do
    lim_c=$(( lim_c - 20 ))
    ctx=$(build_ctx)
  done
  if (( ${#ctx} > 480 )); then
    echo "pattern-f-verdict: encoded context still exceeds 480 chars; nothing written" >&2
    exit 5
  fi
  if ! _interspect_sanitize "$ctx" >/dev/null 2>&1; then
    echo "pattern-f-verdict: context rejected by the register's sanitizer even after encoding; nothing written" >&2
    exit 5
  fi
fi

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
