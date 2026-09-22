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

# ------------------------------------------------------------------ provenance
#
# Every run leaves a receipt saying whether a tracker actually answered. The
# Stop hook reads it to tell a tracker-ranked Next-goal block from an
# improvised one (hooks/lib-next-goal-provenance.sh).
#
# WHY A RECEIPT AND NOT A LIVE RE-QUERY: the Stop hook is capped at 5s, and
# lib-shadow-tracker.sh already documents what happens when a hook overruns it
# — the whole waterfall is silently dropped. Each root here gets up to 25s of
# bd, so re-querying from the hook would blow the cap on the first root.
#
# The receipt is keyed by session because the useful question is "did the
# helper run for THIS conversation" — a stale receipt from yesterday must not
# vouch for today's block. An ABSENT receipt is the load-bearing case: a block
# emitted without ever running this script has no tracker provenance by
# construction, which is exactly the state that needs flagging.
PROVENANCE_SCHEMA="clavain.next-goal-provenance/v1"
PROVENANCE_DIR="${CLAVAIN_PROVENANCE_DIR:-$HOME/.cache/clavain/next-goal-provenance}"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-bb.sh"
PROVENANCE_SESSION="$(_clavain_session_id)"

record_provenance() {
    # $1 = tracker_reachable (true|false), $2 = compact JSON object of extras
    local reachable="$1" extras="${2:-\{\}}"
    [[ "${CLAVAIN_PROVENANCE_DISABLE:-0}" == "1" ]] && return 0
    mkdir -p "$PROVENANCE_DIR" 2>/dev/null || return 0
    local stamp
    stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # Written via a temp file + mv so a hook reading concurrently never sees a
    # half-written object and mistakes it for a malformed receipt.
    local tmp="${PROVENANCE_DIR}/.${PROVENANCE_SESSION}.$$.tmp"
    if command -v jq >/dev/null 2>&1; then
        jq -cn --arg schema "$PROVENANCE_SCHEMA" --arg session "$PROVENANCE_SESSION" \
               --arg stamp "$stamp" --argjson reachable "$reachable" --argjson extras "$extras" \
            '{schema_version: $schema, session_id: $session, recorded_at: $stamp,
              tracker_reachable: $reachable} + $extras' >"$tmp" 2>/dev/null || return 0
    else
        printf '{"schema_version":"%s","session_id":"%s","recorded_at":"%s","tracker_reachable":%s}\n' \
            "$PROVENANCE_SCHEMA" "$PROVENANCE_SESSION" "$stamp" "$reachable" >"$tmp" 2>/dev/null || return 0
    fi
    mv -f "$tmp" "${PROVENANCE_DIR}/${PROVENANCE_SESSION}.json" 2>/dev/null || rm -f "$tmp" 2>/dev/null
    return 0
}

die_json() {
    # A run that dies here looked at nothing, so the receipt says so. Without
    # this the two failure modes diverge: the payload would report
    # available:false while the hook, seeing no receipt at all, could not tell
    # a crashed helper from a helper that was never invoked.
    record_provenance false "$(printf '{"reason":%s}' "$1")"
    printf '{"schema_version":"%s","available":false,"reason":%s,"roots":[],"candidates":[],"lookup_failures":[%s],"roadmap":{"status":"unknown"},"serving":{"status":"unknown"}}\n' \
        "$SCHEMA_VERSION" "$1" "$1"
    exit 0
}

command -v jq >/dev/null 2>&1 || die_json '"jq not installed"'

# ---------------------------------------------------------------- root discovery

# A linked git worktree (git worktree add, bd worktree create) carries its own
# .beads copy that nothing syncs: beads created from the main checkout read as
# "no such bead" there, and its ready list is whatever was copied at creation.
# Resolve a root found inside one to the checkout the tracker actually lives
# in. Observed 2026-09-04: a session in a nested jawnomicon worktree saw zero
# ready beads and improvised every Next-goal block for two days.
tracker_home() {
    local dir="$1" gitdir common main
    command -v git >/dev/null 2>&1 || { printf '%s\n' "$dir"; return 0; }
    gitdir="$(git -C "$dir" rev-parse --git-dir 2>/dev/null)" || { printf '%s\n' "$dir"; return 0; }
    common="$(git -C "$dir" rev-parse --git-common-dir 2>/dev/null)" || { printf '%s\n' "$dir"; return 0; }
    [[ "$gitdir" = /* ]] || gitdir="$dir/$gitdir"
    [[ "$common" = /* ]] || common="$dir/$common"
    gitdir="$(cd "$gitdir" 2>/dev/null && pwd -P)"
    common="$(cd "$common" 2>/dev/null && pwd -P)"
    if [[ -n "$gitdir" && -n "$common" && "$gitdir" != "$common" ]]; then
        main="$(dirname "$common")"
        [[ -d "$main/.beads" ]] && { printf '%s\n' "$main"; return 0; }
    fi
    # Resolved, like the worktree branch above, so one tracker has one name.
    printf '%s\n' "$(cd "$dir" 2>/dev/null && pwd -P || printf '%s' "$dir")"
}

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
        [[ -d "$dir/.beads" ]] && tracker_home "$dir"
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
from collections import Counter
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


def backlog_view(doc):
    """The backlog signal, taken from the roadmap rather than from backlog.md.

    docs/backlog.md announces itself as "generated from roadmap.json" and is a
    filtered rendering of it: 435 markdown bullets over the same 499 items,
    carrying no field the JSON lacks and no timestamp of its own beyond a
    date-only "Last synced". Parsing markdown to recover data that is already
    structured one file upstream would add a parser and lose precision, so the
    signal is derived here and gated on the same freshness rule.

    `deferred` is the load-bearing part. Deferred beads are work someone
    explicitly parked, and proposing one as a next goal re-opens a decision
    that was already made. Until interpath#1 the generator had no deferred
    branch at all and all 18 of them read as ordinary open work, so this
    signal could not have been computed correctly before that fix.
    """
    roadmap = doc.get("roadmap") or {}
    items = []
    for phase in ("now", "next", "later"):
        for entry in (roadmap.get(phase) or []):
            if isinstance(entry, dict) and entry.get("id"):
                items.append(entry)

    deferred, blocked, per_module, per_priority = set(), set(), Counter(), Counter()
    for entry in items:
        status = entry.get("status")
        if status == "closed":
            continue
        if status == "deferred":
            deferred.add(entry["id"])
            continue
        if status == "blocked":
            blocked.add(entry["id"])
        per_module[entry.get("module") or "unknown"] += 1
        per_priority[entry.get("priority") or "unknown"] += 1

    # Capped: this rides in a payload the command reads inline, and a tracker
    # with thousands of parked items should not crowd out the candidates.
    return {
        "deferred": len(deferred),
        "deferred_ids": sorted(deferred)[:200],
        "blocked": len(blocked),
        "blocked_ids": sorted(blocked)[:200],
        "by_priority": dict(sorted(per_priority.items())),
        "module_load": [{"module": m, "open": n} for m, n in per_module.most_common(8)],
    }


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
        "backlog": backlog_view(doc),
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

# ---------------------------------------------------------------- serving state
#
# What the project is FOR, as against what its tracker happens to hold. Three
# optional documents, none of which most repos have:
#
#   docs/charter.md    what the thing is for, and who consumes its output
#   docs/non-goals.md  standing constraints work is expected to stay behind
#   the serving map    which consumer is receiving what, and who is blocked
#
# ABSENCE IS THE COMMON CASE, NOT AN ERROR. A root carrying none of them reports
# status "missing", and the caller then ranks exactly as it did before this
# block existed. That is the design constraint, not a concession to it: most of
# the fleet has no charter, and a signal that fails closed on a missing file is
# a signal that gets switched off. A gate that sits red gets switched off, and
# then the signal it was carrying is gone too.
#
# WHY THERE IS NO FRESHNESS GATE, unlike roadmap_state directly above. A roadmap
# is generated by a scheduler, so a stale one means the scheduler is down and
# age is exactly the signal. These are hand-written standing documents with no
# generator and no generated_at to read: a charter written once and still true
# is not stale, and an age test would report the wrong thing confidently. The
# serving map's own currency is governed by the project's own check (jawnomicon
# runs check:publish-currency over it), not from here.
#
# THE MAP CONVENTION, kept deliberately small. A YAML mapping that may carry:
#   surfaces:   what this repo's own surfaces import, keyed by artifact
#   consumers:  external repos that read the output, keyed by name
#   versions:   one row per artifact version - surface, version, status, and,
#               when status is deferred, blocked_by and reason
# A file that parses but carries none of those is reported with schema
# "unrecognized" and ranks nothing. Reported, never guessed at.

SERVING_MAP_NAMES=(docs/serving-map.yaml docs/serving-map.yml data/exports/publish-log.yaml docs/publish-log.yaml)
SERVING_REASON_CAP="${CLAVAIN_SERVING_REASON_CAP:-600}"

first_readable() {
    local root="$1"; shift
    local name path
    for name in "$@"; do
        [[ -n "$name" ]] || continue
        if [[ "$name" == /* ]]; then path="$name"; else path="$root/$name"; fi
        [[ -f "$path" && -r "$path" ]] && { printf '%s\n' "$path"; return 0; }
    done
    return 1
}

# Serving documents live at a repo root, which is not always a bead root: a
# project can carry a charter and no tracker at all. So walk up from $PWD in its
# own right rather than reusing ROOTS, and let the discovered bead roots follow
# as a fallback. Nearest hit wins, so a subproject's charter beats its
# monorepo's rather than the other way round.
serving_roots() {
    local dir="$PWD" depth=0
    while [[ -n "$dir" && "$dir" != "/" && $depth -lt 12 ]]; do
        printf '%s\n' "$dir"
        dir="$(dirname "$dir")"
        depth=$((depth + 1))
    done
}

serving_state() {
    local root="$1" charter nongoals map
    charter="$(first_readable  "$root" "${CLAVAIN_CHARTER:-}"     docs/charter.md docs/CHARTER.md CHARTER.md)"     || charter=""
    nongoals="$(first_readable "$root" "${CLAVAIN_NON_GOALS:-}"   docs/non-goals.md docs/non_goals.md NON-GOALS.md)" || nongoals=""
    map="$(first_readable      "$root" "${CLAVAIN_SERVING_MAP:-}" "${SERVING_MAP_NAMES[@]}")"                        || map=""

    [[ -n "$charter" || -n "$nongoals" || -n "$map" ]] || { echo 'null'; return; }

    SERVING_ROOT="$root" SERVING_CHARTER="$charter" SERVING_NON_GOALS="$nongoals" \
    SERVING_MAP="$map" SERVING_REASON_CAP="$SERVING_REASON_CAP" \
    python3 - <<'PY' 2>/dev/null || echo 'null'
import json, os, re, sys

cap = int(os.environ.get("SERVING_REASON_CAP") or 600)
out = {"status": "present", "root": os.environ["SERVING_ROOT"]}


def squash(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")


def charter_view(path):
    """First real paragraph, quoted rather than summarised.

    The helper detects and quotes; it does not decide what the charter means.
    Anything that needs the argument reads the file, which is what the command
    tells a C3+ /clavain:goal-form pass to do.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
    except OSError as exc:
        return {"path": path, "unreadable": str(exc)[:200]}
    para = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith(">"):
            continue
        if not stripped:
            if para:
                break
            continue
        para.append(stripped)
    return {"path": path, "headline": squash(" ".join(para), 400)}


def non_goals_view(path):
    """The section headings ARE the constraints; the prose under each argues it.

    Listing the headings is enough to tell a drafter that a line exists and what
    it is about. Deciding whether a draft crosses one needs the prose, and the
    command says to go read it.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            body = fh.read()
    except OSError as exc:
        return {"path": path, "unreadable": str(exc)[:200]}
    heads = [re.sub(r"^#+\s*(?:\d+[.)]\s*)?", "", line).strip()
             for line in body.splitlines() if re.match(r"^##\s+", line)]
    return {"path": path, "constraints": [h for h in heads if h][:20]}


def map_view(path):
    try:
        import yaml
    except ImportError:
        return {"path": path, "schema": "unparsed",
                "reason": "PyYAML not available to this interpreter"}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            doc = yaml.safe_load(fh)
    except Exception as exc:
        return {"path": path, "schema": "unparsed", "reason": str(exc)[:200]}
    if not isinstance(doc, dict):
        return {"path": path, "schema": "unrecognized"}

    surfaces = sorted(doc["surfaces"]) if isinstance(doc.get("surfaces"), dict) else []
    consumers = sorted(doc["consumers"]) if isinstance(doc.get("consumers"), dict) else []
    rows = [r for r in (doc.get("versions") or []) if isinstance(r, dict)]
    if not (surfaces or consumers or rows):
        return {"path": path, "schema": "unrecognized"}

    blocked = []
    for row in rows:
        if row.get("status") != "deferred":
            continue
        blocked.append({
            "surface": row.get("surface"),
            "version": row.get("version"),
            "blocked_by": row.get("blocked_by"),
            "is_consumer": row.get("surface") in consumers,
            "reason": squash(row.get("reason"), cap),
        })

    # Trailing deferrals per surface, in file order: the mechanical form of "N
    # releases in a row that shipped this consumer nothing it could use". One
    # deferral is a decision and reads as healthy; a run of them is a surface
    # nobody is being served on, and no single row carries that.
    streak = {}
    for surface in {r.get("surface") for r in rows}:
        run = 0
        for row in reversed([r for r in rows if r.get("surface") == surface]):
            if row.get("status") != "deferred":
                break
            run += 1
        if run:
            streak[str(surface)] = run

    return {"path": path, "schema": "recognized", "surfaces": surfaces,
            "consumers": consumers, "blocked": blocked,
            "unserved_streak": dict(sorted(streak.items()))}


if os.environ.get("SERVING_CHARTER"):
    out["charter"] = charter_view(os.environ["SERVING_CHARTER"])
if os.environ.get("SERVING_NON_GOALS"):
    out["non_goals"] = non_goals_view(os.environ["SERVING_NON_GOALS"])
if os.environ.get("SERVING_MAP"):
    out["map"] = map_view(os.environ["SERVING_MAP"])

json.dump(out, sys.stdout)
PY
}

# ---------------------------------------------------------------- tracker query

ROOT_REPORTS=()
CANDIDATE_SETS=()
FAILURES=()
ROADMAP_JSON='null'
SEEN_DATABASES=()

# Resolved once, ahead of the tracker loop, because the serving documents are a
# property of the repo rather than of any tracker that answered. First hit wins
# and the rest are not opened.
SERVING_JSON='null'
if [[ -n "${CLAVAIN_SERVING_ROOT:-}" ]]; then
    # An explicit override is EXCLUSIVE, not merely first in line. A scan that
    # fell through to the discovered roots would answer from somewhere else
    # entirely whenever the named root had nothing, which makes the variable
    # useless for pinning behaviour and silently wrong in a test.
    SERVING_SCAN=("$CLAVAIN_SERVING_ROOT")
else
    mapfile -t SERVING_SCAN < <(
        { serving_roots; printf '%s\n' "${ROOTS[@]+"${ROOTS[@]}"}"; } \
            | awk 'NF && !seen[$0]++'
    )
fi
for serving_root in "${SERVING_SCAN[@]+"${SERVING_SCAN[@]}"}"; do
    [[ "$SERVING_JSON" == "null" ]] || break
    [[ -d "$serving_root" ]] || continue
    candidate_serving="$(serving_state "$serving_root")"
    [[ "$candidate_serving" != "null" ]] && SERVING_JSON="$candidate_serving"
done

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

PAYLOAD="$(jq -cn \
    --arg schema "$SCHEMA_VERSION" \
    --argjson roots "$ROOTS_JSON" \
    --argjson candidates "$CANDIDATES_JSON" \
    --argjson failures "$FAILURES_JSON" \
    --argjson roadmap "$ROADMAP_JSON" \
    --argjson serving "$SERVING_JSON" \
    '{
       schema_version: $schema,
       available: true,
       roots: $roots,
       candidates: $candidates,
       lookup_failures: $failures,
       roadmap: (if $roadmap == null then {status: "missing"} else $roadmap end),
       serving: (if $serving == null then {status: "missing"} else $serving end),
       tracker_reachable: ([$roots[] | select(.status == "ok" or .status == "empty")] | length > 0)
     }')"

# The receipt carries the reachable roots by prefix so the hook can say WHICH
# tracker vouched for the block, not merely that one did. Same reason the
# payload keeps lookup_failures: "reachable" without a name is the kind of
# unfalsifiable claim this whole change exists to remove.
record_provenance \
    "$(jq -r '.tracker_reachable' <<<"$PAYLOAD")" \
    "$(jq -c '{
         roots_ok: [.roots[] | select(.status == "ok" or .status == "empty") | .prefix // .root],
         lookup_failures: [.lookup_failures[] | .root],
         candidate_count: (.candidates | length),
         roadmap_status: (.roadmap.status // "unknown"),
         serving_status: (.serving.status // "unknown")
       }' <<<"$PAYLOAD")"

printf '%s\n' "$PAYLOAD"
