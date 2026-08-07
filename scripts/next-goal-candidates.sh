#!/usr/bin/env bash
# Collect Next-goal candidates from every bead root reachable from this session.
#
# WHY THIS IS A SCRIPT AND NOT THE INLINE BASH IT REPLACES
#
# `bd ready` resolves from the current directory and stops at the nearest git
# root. Sylveste's subprojects are nested git repos, so from
# interverse/tool-time bd reports "no beads database found" while the monorepo
# root two levels up has 30 ready issues and ~/projects has 50. The command's
# Step 1 took that error as an empty backlog:
#
#     LOCAL_READY_JSON=$(bd ready --json --limit 20 2>/dev/null) || LOCAL_READY_JSON="[]"
#
# The 2>/dev/null swallowed the diagnostic and the || turned the failure into
# the same "[]" that a genuinely clean tracker produces. Every block built from
# nothing then looked exactly like a block built from a well-stocked backlog.
#
# bead mk-fx3 closed with "goal-complete hook enriches from bd ready + open
# epics across trackers" — but the across-trackers half shipped as prose in the
# command body ("if you know of other reachable bead roots... merge results"),
# i.e. as model judgment. This file is that half as code.
#
# THE THREE OUTCOMES, WHICH MUST NEVER COLLAPSE INTO TWO
#
#   ok           root answered, candidates returned
#   empty        root answered, nothing ready      -> a real zero
#   unreachable  root could not be queried at all  -> NOT a zero
#
# `candidates: []` with `lookup_failures: []` means the backlog is genuinely
# clear. `candidates: []` with a non-empty `lookup_failures` means we could not
# look, and the caller must say so rather than improvising in silence.
#
# Read-only: never mutates a tracker, never creates a database. Fails soft —
# an unreachable root is reported in the payload, never fatal.

set -uo pipefail

SCHEMA_VERSION="clavain.next-goal-candidates/v1"

BD="${CLAVAIN_NEXT_GOAL_BD:-bd}"
LIMIT="${CLAVAIN_NEXT_GOAL_LIMIT:-20}"
PER_ROOT_TIMEOUT="${CLAVAIN_NEXT_GOAL_TIMEOUT:-25}"
MAX_ROOTS="${CLAVAIN_NEXT_GOAL_MAX_ROOTS:-6}"

# A roadmap older than this is reported as stale and NOT ranked on. Seven days
# is chosen against the regeneration cadence, not the reading cadence: once
# sync-roadmap-json.sh runs daily, a week of silence means the scheduler itself
# has been down, which is the condition worth surfacing. A looser bound would
# let a dead scheduler read as healthy — the exact failure this command is
# being repaired for.
ROADMAP_STALE_DAYS="${CLAVAIN_ROADMAP_STALE_DAYS:-7}"

SCOPE="${1:-}"
[[ "$SCOPE" == --* ]] && SCOPE=""

die_json() {
    printf '{"schema_version":"%s","available":false,"reason":%s,"roots":[],"candidates":[],"lookup_failures":[%s],"roadmap":{"status":"unknown"}}\n' \
        "$SCHEMA_VERSION" "$1" "$1"
    exit 0
}

command -v jq >/dev/null 2>&1 || die_json '"jq not installed"'

# ---------------------------------------------------------------- root discovery

discover_roots() {
    if [[ -n "${CLAVAIN_NEXT_GOAL_ROOTS:-}" ]]; then
        printf '%s\n' "${CLAVAIN_NEXT_GOAL_ROOTS}" | tr ':' '\n'
        return
    fi

    # Walk up crossing nested-git boundaries deliberately. That crossing IS the
    # fix: bd stops at the first git root, which is why a subproject checkout
    # sees no tracker at all.
    local dir="$PWD" depth=0
    while [[ -n "$dir" && "$dir" != "/" && $depth -lt 12 ]]; do
        [[ -d "$dir/.beads" ]] && printf '%s\n' "$dir"
        dir="$(dirname "$dir")"
        depth=$((depth + 1))
    done

    # The workspace tracker holds cross-project work (mk-* beads) and is not an
    # ancestor of every checkout, so walking up does not always reach it.
    [[ -d "$HOME/projects/.beads" ]] && printf '%s\n' "$HOME/projects"
}

mapfile -t ROOTS < <(discover_roots | awk 'NF && !seen[$0]++' | head -n "$MAX_ROOTS")

# ---------------------------------------------------------------- roadmap state

roadmap_state() {
    local root="$1"
    local slug cache_dir repo_copy cache_copy
    slug="$(basename "$root" | tr '[:upper:]' '[:lower:]')"
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/clavain"
    repo_copy="$root/docs/roadmap.json"
    cache_copy="${CLAVAIN_ROADMAP_CACHE:-$cache_dir/$slug-roadmap.json}"

    [[ -r "$repo_copy" || -r "$cache_copy" ]] || { echo 'null'; return; }

    # Two copies, deliberately. The repo copy is a committed snapshot; the cache
    # copy is what the scheduler regenerates. Regenerating in place was
    # rejected: docs/roadmap.json and docs/backlog.md are tracked, a single
    # regeneration produces an ~8,000-line diff, and Sylveste's main is
    # protected — so a daily in-repo job would dirty the tree every morning for
    # changes nobody can land without a PR. Whichever copy carries the newer
    # generated_at wins, and the payload names which one it was.
    ROADMAP_REPO="$repo_copy" ROADMAP_CACHE="$cache_copy" ROADMAP_STALE_DAYS="$ROADMAP_STALE_DAYS" \
    python3 - <<'PY' 2>/dev/null || echo 'null'
import json, os, sys
from datetime import datetime, timezone

limit = int(os.environ["ROADMAP_STALE_DAYS"])
now = datetime.now(timezone.utc)


def parse(stamp):
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def load(path, source):
    if not path or not os.access(path, os.R_OK):
        return None
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except Exception as exc:
        return {"status": "unreadable", "path": path, "source": source,
                "reason": str(exc)[:200], "_when": None}
    stamp = doc.get("generated_at")
    when = parse(stamp)
    if when is None:
        # No usable provenance stamp means freshness is unknowable. That is its
        # own state, never "fresh" — reporting unknown as healthy is the bug
        # this whole helper exists to stop.
        out = {"status": "undated", "path": path, "source": source, "_when": None}
        if stamp:
            out["generated_at"] = stamp
        return out
    age = (now - when).total_seconds() / 86400.0
    return {
        "status": "stale" if age > limit else "fresh",
        "path": path,
        "source": source,
        "generated_at": stamp,
        "age_days": round(age, 1),
        "stale_after_days": limit,
        "open_beads": doc.get("open_beads"),
        "blocked": doc.get("blocked"),
        "module_count": doc.get("module_count"),
        "_when": when,
    }


candidates = [c for c in (load(os.environ.get("ROADMAP_CACHE"), "cache"),
                          load(os.environ.get("ROADMAP_REPO"), "repo")) if c]
if not candidates:
    print("null")
    sys.exit(0)

dated = [c for c in candidates if c["_when"] is not None]
best = max(dated, key=lambda c: c["_when"]) if dated else candidates[0]
best.pop("_when", None)
json.dump(best, sys.stdout)
PY
}

# ---------------------------------------------------------------- tracker query

ROOT_REPORTS=()
CANDIDATE_SETS=()
FAILURES=()
ROADMAP_JSON='null'
SEEN_DATABASES=()

# Deduplicate by the database bd actually resolves to, not by the directory we
# found a .beads/ in. /Users/sma/projects has a .beads/ directory but bd
# resolves past it to /Users/sma/.beads (prefix mk), so walking up from a
# Sylveste subproject yields three directories over two real trackers. Keying
# on the path would report a breadth of coverage that does not exist.
resolve_tracker() {
    local dir="$1"
    (cd "$dir" && timeout "$PER_ROOT_TIMEOUT" "$BD" where 2>/dev/null) | awk '
        NR == 1 { beads = $0 }
        /^[[:space:]]*prefix:/   { prefix = $2 }
        /^[[:space:]]*database:/ { db = $2 }
        END { if (beads != "") printf "%s\t%s\t%s\n", beads, prefix, db }
    '
}

for root in "${ROOTS[@]}"; do
    [[ -d "$root" ]] || continue

    if [[ "$ROADMAP_JSON" == "null" ]]; then
        candidate_roadmap="$(roadmap_state "$root")"
        [[ "$candidate_roadmap" != "null" ]] && ROADMAP_JSON="$candidate_roadmap"
    fi

    IFS=$'\t' read -r beads_dir prefix database < <(resolve_tracker "$root")
    dedupe_key="${database:-${beads_dir:-$root}}"
    if [[ -n "${dedupe_key}" ]]; then
        already=0
        for seen in "${SEEN_DATABASES[@]+"${SEEN_DATABASES[@]}"}"; do
            [[ "$seen" == "$dedupe_key" ]] && already=1 && break
        done
        (( already )) && continue
        SEEN_DATABASES+=("$dedupe_key")
    fi

    errfile="$(mktemp)"
    if [[ -n "$SCOPE" ]]; then
        out="$(cd "$root" && timeout "$PER_ROOT_TIMEOUT" "$BD" ready --json --limit "$LIMIT" --parent "$SCOPE" 2>"$errfile")"
        rc=$?
        if (( rc != 0 )) || [[ -z "$out" || "$out" == "[]" ]]; then
            out="$(cd "$root" && timeout "$PER_ROOT_TIMEOUT" "$BD" ready --json --limit "$LIMIT" 2>"$errfile")"
            rc=$?
        fi
    else
        out="$(cd "$root" && timeout "$PER_ROOT_TIMEOUT" "$BD" ready --json --limit "$LIMIT" 2>"$errfile")"
        rc=$?
    fi
    reason="$(head -c 300 "$errfile" | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g; s/ $//')"
    rm -f "$errfile"

    if (( rc == 124 )); then
        status="unreachable"; reason="${reason:-timed out after ${PER_ROOT_TIMEOUT}s}"
    elif (( rc != 0 )); then
        status="unreachable"; reason="${reason:-bd exited $rc}"
    elif ! jq -e . >/dev/null 2>&1 <<<"${out:-}"; then
        # bd exited 0 but produced something that is not JSON. Treating that as
        # an empty backlog is the same conflation this file exists to prevent.
        status="unreachable"; reason="${reason:-bd returned unparseable output}"
    else
        count="$(jq 'length' <<<"$out")"
        status="ok"; reason=""
        (( count == 0 )) && status="empty"
        CANDIDATE_SETS+=("$(jq -c --arg root "$root" 'map(. + {_root: $root})' <<<"$out")")
    fi

    if [[ "$status" == "unreachable" ]]; then
        FAILURES+=("$(jq -cn --arg root "$root" --arg reason "$reason" '{root: $root, reason: $reason}')")
    fi

    ROOT_REPORTS+=("$(jq -cn \
        --arg root "$root" \
        --arg prefix "${prefix:-}" \
        --arg database "${database:-}" \
        --arg status "$status" \
        --arg reason "$reason" \
        --argjson ready "$( [[ "$status" == "ok" || "$status" == "empty" ]] && jq 'length' <<<"$out" || echo 0 )" \
        '{root: $root, status: $status, ready: $ready}
         + (if $prefix   == "" then {} else {prefix: $prefix}     end)
         + (if $database == "" then {} else {database: $database} end)
         + (if $reason   == "" then {} else {reason: $reason}     end)')")
done

# ---------------------------------------------------------------- assemble

join_array() {
    local IFS=,
    printf '[%s]' "$*"
}

ROOTS_JSON="$(join_array "${ROOT_REPORTS[@]+"${ROOT_REPORTS[@]}"}")"
FAILURES_JSON="$(join_array "${FAILURES[@]+"${FAILURES[@]}"}")"
CANDIDATES_JSON="$(join_array "${CANDIDATE_SETS[@]+"${CANDIDATE_SETS[@]}"}")"
CANDIDATES_JSON="$(jq -c 'add // [] | unique_by(.id)' <<<"$CANDIDATES_JSON" 2>/dev/null || echo '[]')"

jq -cn \
    --arg schema "$SCHEMA_VERSION" \
    --argjson roots "$ROOTS_JSON" \
    --argjson candidates "$CANDIDATES_JSON" \
    --argjson failures "$FAILURES_JSON" \
    --argjson roadmap "$ROADMAP_JSON" \
    '{
       schema_version: $schema,
       available: true,
       roots: $roots,
       candidates: $candidates,
       lookup_failures: $failures,
       roadmap: (if $roadmap == null then {status: "missing"} else $roadmap end),
       tracker_reachable: ([$roots[] | select(.status == "ok" or .status == "empty")] | length > 0)
     }'
