#!/usr/bin/env bash
#
# next-goal-verify.sh — re-read every candidate a Next-goal block is about to
# cite, at source, immediately before it is emitted.
#
# WHY THIS EXISTS, and why it is NOT the same check as the provenance receipt.
#
# next-goal-candidates.sh answers "did a tracker answer at all", and the Stop
# hook flags a block with no receipt as improvised. That closed the failure
# where a block was written from session context without consulting anything.
#
# It does not close this one. On 2026-08-14 a Next-goal block cited
# `solwend-w46q` — a real bead ID, correctly formed, from a reachable tracker,
# so every provenance signal read clean — and recommended continuing it. The
# epic had been CLOSED as "all steps complete" since 2026-07-31, and the
# deliverables it proposed building were already on disk: eight components, a
# 337-line token sheet, a /plan page. The recommendation was to build what
# existed.
#
# The gap is exact: provenance asks WHETHER YOU LOOKED. Nothing asked WHETHER
# WHAT YOU CITED IS STILL TRUE. A stale ID and a live one are byte-identical in
# a block, so the reader cannot tell them apart either — the same argument that
# put the provenance receipt here in the first place, one level in.
#
# The failure mode is specifically a CONTEXT-RICH one. The longer a session
# runs, the more confidently it can name a bead from memory, and the likelier
# that memory predates the close. So the check has to be mechanical: it must
# not depend on the judgement of the thing whose judgement is compromised.
#
# LINEAGE — why a live, open, correctly-cited bead can still be the wrong
# recommendation.
#
# On 2026-09-03 three consecutive goals (1b53da77, c60de386, c4cda02c) each
# recommended the next as its successor, all under one epic. The fourth
# recommendation passed provenance, freshness, and shape, and was still the
# wrong goal: nothing had asked whether it merely repeated the lineage of the
# goals just closed. Every check above asks whether a cited bead is real and
# open; the session with the most context is the one least able to notice that
# it has stopped ranking and started inheriting.
#
# The rule, mechanical: read the last WINDOW closed goals (default 4, env
# CLAVAIN_NEXT_GOAL_LINEAGE_WINDOW) from `ic goal list` in every reachable bead
# root. A goal's lineage is the set of root epics of its own bead and of every
# bead labeled ic_goal_id:<goal>. A recommendation (--recommend) whose root
# epic is in the lineage of at least MIN of those goals (default 2, env
# CLAVAIN_NEXT_GOAL_LINEAGE_MIN) is DISQUALIFIED — unless --beat names an open,
# out-of-lineage candidate verified in the same run, in which case it is a
# warning and the override is on record. A run without --recommend whose every
# usable candidate is in the streak lineage is disqualified as a whole. A goal
# whose lineage cannot be read never counts toward the streak. No `ic` anywhere,
# or no store that answers, makes lineage UNAVAILABLE and says so; the rest of
# the verdict stands.
#
# OUT CLAUSE — why a live, open, out-of-lineage pick can still be the wrong
# recommendation.
#
# On 2026-09-04 the goal jawnomicon ia-preview closed with the clause
# "OUT: index density, export currency 646 to 694, families v31 naming, ...".
# The Next-goal block that closed it recommended "export currency 646 to 694".
# The exclusion was the user's decision, made in the goal they had just
# ratified, and the block silently reopened it three minutes after it landed.
# Nothing above can see this: the pick was free text (no bead to read back),
# and no check compares a recommendation against what the last goal excluded.
#
# --text carries the /goal text the block is about to emit; --out-of names
# where the just-closed goal's condition lives (a bead whose description holds
# it, a file, or the literal text) and may repeat. When the goal store answers,
# the most recently closed goal's ConditionText is read automatically as well.
# A recommendation that matches an item of any OUT clause is DISQUALIFIED —
# unless --out-override gives the reason it is now in, which downgrades the
# refusal to a warning and puts the reason on the receipt. The block must make
# that case in prose too.
#
# WORKTREES — a linked git worktree (git worktree add, bd worktree create)
# carries its own .beads copy that nothing syncs, so beads created from the
# main checkout read as "no such bead" there. Roots found inside a linked
# worktree resolve to the checkout the tracker actually lives in.
#
# Usage:
#   next-goal-verify.sh [--recommend <id>] [--beat <id>] [--text <goal text>]
#                       [--out-of <bead|file|text>]... [--out-override <reason>]
#                       <bead-id> [<bead-id>...]
#   next-goal-verify.sh --path apps/web/components/x/ <bead-id>     # see --path
#   next-goal-verify.sh --recommend mk-12 --beat mk-40 mk-12 mk-40  # see LINEAGE
#   next-goal-verify.sh --recommend mk-12 --text "/goal ..." --out-of mk-9 mk-12  # see OUT CLAUSE
#
# Exit: 0 = every candidate usable (or verification unavailable — fail-open),
#       3 = at least one candidate DISQUALIFIED. Always prints one JSON object.

set -uo pipefail

SCHEMA_VERSION="clavain.next-goal-verify/v3"
MAX_ROOTS="${CLAVAIN_NEXT_GOAL_MAX_ROOTS:-6}"
BD_TIMEOUT="${CLAVAIN_NEXT_GOAL_BD_TIMEOUT:-20}"

RECEIPT_DIR="${CLAVAIN_VERIFY_DIR:-$HOME/.cache/clavain/next-goal-verify}"
RECEIPT_SESSION="${CLAUDE_SESSION_ID:-unknown}"

IDS=()
PATHS=()
RECOMMEND=""
BEAT=""
TEXT=""
OUT_OF=()
OUT_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --path) PATHS+=("${2:-}"); shift 2 || shift ;;
        --path=*) PATHS+=("${1#--path=}"); shift ;;
        --recommend) RECOMMEND="${2:-}"; shift 2 || shift ;;
        --recommend=*) RECOMMEND="${1#--recommend=}"; shift ;;
        --beat) BEAT="${2:-}"; shift 2 || shift ;;
        --beat=*) BEAT="${1#--beat=}"; shift ;;
        --text) TEXT="${2:-}"; shift 2 || shift ;;
        --text=*) TEXT="${1#--text=}"; shift ;;
        --out-of) OUT_OF+=("${2:-}"); shift 2 || shift ;;
        --out-of=*) OUT_OF+=("${1#--out-of=}"); shift ;;
        --out-override) OUT_OVERRIDE="${2:-}"; shift 2 || shift ;;
        --out-override=*) OUT_OVERRIDE="${1#--out-override=}"; shift ;;
        -h|--help) sed -n '2,60p' "$0"; exit 0 ;;
        *) IDS+=("$1"); shift ;;
    esac
done

# The pick and the candidate it beat are verified like any other candidate: a
# --recommend that was never read back at source would be the 2026-08-14
# failure with a new flag on it.
for extra in "$RECOMMEND" "$BEAT"; do
    [[ -z "$extra" ]] && continue
    present=0
    for id in ${IDS[@]+"${IDS[@]}"}; do
        [[ "$id" == "$extra" ]] && { present=1; break; }
    done
    [[ $present -eq 0 ]] && IDS+=("$extra")
done

emit_and_exit() {
    # $1 = compact JSON payload, $2 = exit code
    record_receipt "$1"
    printf '%s\n' "$1"
    exit "$2"
}

record_receipt() {
    # Mirrors next-goal-candidates.sh's receipt discipline: session-keyed, so a
    # yesterday's verification cannot vouch for today's block, and written via
    # temp+mv so a concurrent hook read never sees a half-written object.
    [[ "${CLAVAIN_PROVENANCE_DISABLE:-0}" == "1" ]] && return 0
    mkdir -p "$RECEIPT_DIR" 2>/dev/null || return 0
    local tmp="${RECEIPT_DIR}/.${RECEIPT_SESSION}.$$.tmp"
    printf '%s\n' "$1" >"$tmp" 2>/dev/null || return 0
    mv -f "$tmp" "${RECEIPT_DIR}/${RECEIPT_SESSION}.json" 2>/dev/null || rm -f "$tmp" 2>/dev/null
    return 0
}

unavailable() {
    # FAIL-OPEN, but never fail-SILENT. `ok` is null rather than true: an
    # unrun check is not a passed one, and the caller is required to say which
    # it got. Same reason the roadmap's `undated` is treated as stale here —
    # unknown is not healthy.
    local payload
    payload="$(printf '{"schema_version":"%s","available":false,"ok":null,"reason":"%s","beads":[],"paths":[],"disqualified":[],"warnings":[],"lineage":{"available":false,"reason":"not evaluated: verification itself was unavailable"}}' \
        "$SCHEMA_VERSION" "$1")"
    emit_and_exit "$payload" 0
}

command -v jq >/dev/null 2>&1 || unavailable "jq not installed"
[[ ${#IDS[@]} -gt 0 || ${#PATHS[@]} -gt 0 || -n "$TEXT" ]] || unavailable "nothing to verify"

# bd is required only for BEAD IDs. A --path run asks the filesystem whether an
# artifact exists and never touches a tracker, so demanding bd for it made the
# whole run report `available: false` on any host without bd — surrendering the
# half of the check that was still perfectly answerable. Caught on a CI runner
# that has no bd: a paths-only invocation returned no `paths` array at all.
if [[ ${#IDS[@]} -gt 0 ]]; then
    command -v bd >/dev/null 2>&1 || unavailable "bd not installed"
fi

# ---------------------------------------------------------------- root discovery
#
# Deliberately identical to next-goal-candidates.sh: walk up crossing nested-git
# boundaries, because bd resolves from $PWD and stops at the first git root, and
# then add the workspace tracker, which is not an ancestor of every checkout.
# Two different resolution schemes for the same ID space would be a way for the
# gate to disagree with the thing it is gating.
# A linked git worktree carries its own .beads copy that nothing syncs. Resolve
# a root found inside one to the checkout the tracker actually lives in, so
# the beads the session created from the main checkout can be read back.
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
    local dir="$PWD" depth=0
    while [[ -n "$dir" && "$dir" != "/" && $depth -lt 12 ]]; do
        [[ -d "$dir/.beads" ]] && tracker_home "$dir"
        dir="$(dirname "$dir")"
        depth=$((depth + 1))
    done
    [[ -d "$HOME/projects/.beads" ]] && printf '%s\n' "$HOME/projects"
}

mapfile -t ROOTS < <(discover_roots | awk 'NF && !seen[$0]++' | head -n "$MAX_ROOTS")
[[ ${#ROOTS[@]} -gt 0 ]] && ROOTS_OK=1 || ROOTS_OK=0

# Reachability is decided AFTER the loop, by whether a tracker actually
# answered — see the ANSWERED check below. Counting roots here would not do it:
# CLAVAIN_NEXT_GOAL_ROOTS is taken on trust, so a configured path with no
# tracker behind it produces a root that cannot answer anything.

bd_show() {
    # $1 = root, $2 = id. Prints the raw JSON, or nothing.
    #
    # `bd show <missing-id> --json` EXITS 0 and prints {"error": ...}. The exit
    # status is not the answer; the payload is. A gate that trusted `$?` here
    # would clear every fabricated ID it was built to catch.
    if command -v timeout >/dev/null 2>&1; then
        (cd "$1" 2>/dev/null && timeout "$BD_TIMEOUT" bd show "$2" --json 2>/dev/null)
    else
        (cd "$1" 2>/dev/null && bd show "$2" --json 2>/dev/null)
    fi
}

BEADS_JSON="[]"
DISQUALIFIED="[]"
ANSWERED=0

for id in ${IDS[@]+"${IDS[@]}"}; do
    found=""
    found_root=""
    for root in ${ROOTS[@]+"${ROOTS[@]}"}; do
        raw="$(bd_show "$root" "$id")"
        [[ -z "$raw" ]] && continue
        # An array means bd resolved it. An object carries {"error": ...}.
        if jq -e 'type == "array" and length > 0' >/dev/null 2>&1 <<<"$raw"; then
            found="$raw"; found_root="$root"; ANSWERED=1; break
        fi
        # A parseable error object is still a TRACKER ANSWERING — it looked and
        # said no. That is the only thing that earns the right to call an id
        # nonexistent below, and it is a different fact from silence.
        if jq -e 'type == "object" and has("error")' >/dev/null 2>&1 <<<"$raw"; then
            ANSWERED=1
        fi
    done

    if [[ -z "$found" ]]; then
        entry="$(jq -cn --arg id "$id" \
            '{id: $id, root: null, status: null, verdict: "disqualified",
              reason: "no such bead in any reachable tracker — do not cite an ID that cannot be read back"}')"
    else
        entry="$(jq -c --arg root "$found_root" '
            .[0]
            | {id, root: $root, status, issue_type, priority, parent: (.parent // null),
               title: (.title // ""), closed_at: (.closed_at // null)}
            | . + (
                if   .status == "closed"
                then {verdict: "disqualified",
                      reason: ("already closed" + (if .closed_at then " (" + .closed_at + ")" else "" end)
                               + " — proposing it recommends work that is already done")}
                elif .status == "deferred"
                then {verdict: "disqualified",
                      reason: "deferred — parking it was a decision, and re-proposing it silently reopens that decision"}
                elif .status == "in_progress"
                then {verdict: "warn",
                      reason: "already in progress — usable only if the goal is to finish it, and say so"}
                elif .status == "blocked"
                then {verdict: "warn",
                      reason: "blocked — usable only if the goal is to unblock it, and name what it waits on"}
                else {verdict: "ok", reason: "open"}
                end)
        ' <<<"$found")"
    fi
    BEADS_JSON="$(jq -c --argjson e "$entry" '. + [$e]' <<<"$BEADS_JSON")"
done

# SILENCE IS NOT A VERDICT — and this script shipped its first draft getting
# that wrong, which is precisely the defect it exists to prevent.
#
# If no tracker answered for ANY id, every one of them fell through to the
# not-found branch and the run reported `no such bead in any reachable tracker`
# about beads that were perfectly alive, then exited 3. A gate that says "your
# candidate does not exist" when the truth is "I never reached a tracker" is
# worse than no gate: it is confidently wrong in the direction that drops real
# work, and next-goal-candidates.sh carries ten lines of comment on the same
# distinction one level out. Found by running it on a host missing `awk`.
if [[ ${#IDS[@]} -gt 0 && $ANSWERED -eq 0 ]]; then
    unavailable "no bead root reachable, so a live candidate cannot be told from a closed one"
fi

# --------------------------------------------------------------------- lineage
#
# The third claim a block makes, and the one neither check above touches: that
# the recommendation was CHOSEN rather than inherited. See LINEAGE in the
# header. The window is read from `ic goal list` in every bead root, the same
# way bd is asked, so the two never disagree about which stores exist.
LINEAGE_WINDOW="${CLAVAIN_NEXT_GOAL_LINEAGE_WINDOW:-4}"
LINEAGE_MIN="${CLAVAIN_NEXT_GOAL_LINEAGE_MIN:-2}"
LINEAGE_JSON='{"available":false,"reason":"no bead candidates, so there is no recommendation to place","window":[],"streak":[]}'
LAST_GOAL_ID=""
LAST_GOAL_CONDITION=""
RUN_DISQ=""
ROOT_EPIC=""
declare -A ROOT_MEMO

ic_goal_list() {
    # $1 = root. Prints the raw JSON, or nothing. `ic` opens its store from
    # $PWD, so this runs inside the root exactly as bd_show does.
    if command -v timeout >/dev/null 2>&1; then
        (cd "$1" 2>/dev/null && timeout "$BD_TIMEOUT" ic goal list --json 2>/dev/null)
    else
        (cd "$1" 2>/dev/null && ic goal list --json 2>/dev/null)
    fi
}

bd_list_label() {
    # $1 = root, $2 = label. Prints the raw JSON array, or nothing. --all,
    # because a goal's lineage is mostly the beads it CLOSED.
    if command -v timeout >/dev/null 2>&1; then
        (cd "$1" 2>/dev/null && timeout "$BD_TIMEOUT" bd list --label "$2" --all --json 2>/dev/null)
    else
        (cd "$1" 2>/dev/null && bd list --label "$2" --all --json 2>/dev/null)
    fi
}

root_epic() {
    # $1 = root, $2 = id. Follows `parent` until null (depth cap 8) and sets
    # ROOT_EPIC to the top-level bead's id, or "" when the chain cannot be
    # read. It sets a variable instead of printing because a $(...) call would
    # run in a subshell and throw the memo away on return; the memo is what
    # keeps a ten-bead lineage from costing ten identical `bd show`s.
    local root="$1" cur="$2" depth=0 raw parent result="?" p
    local -a walked=()
    ROOT_EPIC=""
    while :; do
        if [[ -n "${ROOT_MEMO[$cur]+x}" ]]; then result="${ROOT_MEMO[$cur]}"; break; fi
        [[ $depth -ge 8 ]] && break
        raw="$(bd_show "$root" "$cur")"
        jq -e 'type == "array" and length > 0' >/dev/null 2>&1 <<<"$raw" || break
        walked+=("$cur")
        parent="$(jq -r '.[0].parent // empty' <<<"$raw")"
        if [[ -z "$parent" ]]; then result="$cur"; break; fi
        cur="$parent"
        depth=$((depth + 1))
    done
    for p in ${walked[@]+"${walked[@]}"}; do ROOT_MEMO[$p]="$result"; done
    [[ "$result" == "?" ]] || ROOT_EPIC="$result"
    return 0
}

root_epic_of() {
    # $1 = root, $2 = id, $3 = its parent ("" when top-level). For a bead the
    # caller already holds, so it is not fetched a second time. Sets ROOT_EPIC.
    if [[ -z "$3" ]]; then ROOT_MEMO[$2]="$2"; ROOT_EPIC="$2"; return 0; fi
    root_epic "$1" "$3"
    ROOT_MEMO[$2]="${ROOT_EPIC:-?}"
    return 0
}

if [[ ${#IDS[@]} -gt 0 ]]; then
    if ! command -v ic >/dev/null 2>&1; then
        LINEAGE_JSON='{"available":false,"reason":"ic not installed, so the lineage of the last closed goals cannot be read","window":[],"streak":[]}'
    else
        GOALS_ALL="[]"
        GOALS_SEEN=0
        for root in ${ROOTS[@]+"${ROOTS[@]}"}; do
            raw="$(ic_goal_list "$root")"
            jq -e 'type == "array"' >/dev/null 2>&1 <<<"$raw" || continue
            GOALS_SEEN=1
            GOALS_ALL="$(jq -c --arg root "$root" --argjson g "$raw" \
                '. + [$g[] | select(.Status == "closed")
                      | {id: .ID, closed_at: (.ClosedAt // 0), bead_id: (.BeadID // null), _root: $root,
                         condition: (.ConditionText // "")}]' <<<"$GOALS_ALL")"
        done
        if [[ $GOALS_SEEN -eq 0 ]]; then
            LINEAGE_JSON='{"available":false,"reason":"no goal store answered in any reachable root, so the lineage of the last closed goals cannot be read","window":[],"streak":[]}'
        else
            WINDOW_JSON="$(jq -c --argjson w "$LINEAGE_WINDOW" 'sort_by(-(.closed_at)) | .[0:$w]' <<<"$GOALS_ALL")"
            LAST_GOAL_ID="$(jq -r '.[0].id // empty' <<<"$WINDOW_JSON")"
            LAST_GOAL_CONDITION="$(jq -r '.[0].condition // empty' <<<"$WINDOW_JSON")"

            # Each goal's lineage: root epics of its own bead and of every bead
            # labeled with it. Empty means UNKNOWN, and unknown never counts.
            WINDOW_OUT="[]"
            while IFS= read -r goal; do
                gid="$(jq -r '.id' <<<"$goal")"
                groot="$(jq -r '._root' <<<"$goal")"
                gbead="$(jq -r '.bead_id // empty' <<<"$goal")"
                groots="[]"
                if [[ -n "$gbead" ]]; then
                    root_epic "$groot" "$gbead"
                    [[ -n "$ROOT_EPIC" ]] && groots="$(jq -c --arg r "$ROOT_EPIC" '. + [$r]' <<<"$groots")"
                fi
                labeled="$(bd_list_label "$groot" "ic_goal_id:$gid")"
                if jq -e 'type == "array"' >/dev/null 2>&1 <<<"$labeled"; then
                    while IFS=$'\t' read -r lid lparent; do
                        [[ -z "$lid" ]] && continue
                        root_epic_of "$groot" "$lid" "$lparent"
                        [[ -n "$ROOT_EPIC" ]] && groots="$(jq -c --arg r "$ROOT_EPIC" '. + [$r]' <<<"$groots")"
                    done < <(jq -r '.[] | [.id, (.parent // "")] | @tsv' <<<"$labeled")
                fi
                groots="$(jq -c 'unique' <<<"$groots")"
                WINDOW_OUT="$(jq -c --argjson g "$goal" --argjson r "$groots" \
                    '. + [{id: $g.id, closed_at: $g.closed_at, bead_id: $g.bead_id, root: $g._root,
                           roots: $r, unknown: (($r | length) == 0)}]' <<<"$WINDOW_OUT")"
            done < <(jq -c '.[]' <<<"$WINDOW_JSON")

            # Each usable candidate: its root epic, and which window goals share it.
            CAND_OUT="[]"
            while IFS=$'\t' read -r cid croot cparent; do
                [[ -z "$cid" ]] && continue
                root_epic_of "$croot" "$cid" "$cparent"
                streak="[]"
                if [[ -n "$ROOT_EPIC" ]]; then
                    streak="$(jq -c --arg r "$ROOT_EPIC" '[.[] | select(any(.roots[]; . == $r)) | .id]' <<<"$WINDOW_OUT")"
                fi
                CAND_OUT="$(jq -c --arg id "$cid" --arg r "$ROOT_EPIC" --argjson s "$streak" --argjson m "$LINEAGE_MIN" \
                    '. + [{id: $id, root_epic: (if $r == "" then null else $r end), streak: $s,
                           in_streak: (($s | length) >= $m)}]' <<<"$CAND_OUT")"
            done < <(jq -r '.[] | select(.verdict == "ok" or .verdict == "warn")
                             | [.id, .root, (.parent // "")] | @tsv' <<<"$BEADS_JSON")

            # The decision. --beat is not a bypass: it names an OPEN candidate
            # OUTSIDE the streak that was weighed and lost, verified in this same
            # run, so an override cannot cite something closed, in the same
            # lineage, or never looked at. Without --recommend, every in-streak
            # candidate is a warning, and a run made only of them is refused.
            DECISION="$(jq -cn \
                --argjson beads "$BEADS_JSON" --argjson cands "$CAND_OUT" --argjson window "$WINDOW_OUT" \
                --arg rec "$RECOMMEND" --arg beat "$BEAT" --argjson w "$LINEAGE_WINDOW" '
                def cand($id): first($cands[] | select(.id == $id)) // null;
                def bead($id): first($beads[] | select(.id == $id)) // null;
                def ids($c): ($c.streak | join(", "));
                (if $rec == "" then null else cand($rec) end) as $rc
                | (if $beat == "" then null else cand($beat) end) as $bc
                | (if $beat == "" then null else bead($beat) end) as $bb
                | (if $rc != null and $rc.in_streak then
                     (if $beat != "" and $beat != $rec and $bc != null and ($bc.in_streak | not) and $bb.verdict == "ok"
                      then {verdict: "warn",
                            reason: ("continues the lineage of " + ids($rc) + " (" + $rc.root_epic + "); allowed because it beat " + $beat + " (" + $bc.root_epic + ")")}
                      else {verdict: "disqualified",
                            reason: ("continues the lineage of " + ($rc.streak | length | tostring) + " of the last " + ($w | tostring)
                                     + " closed goals (" + ids($rc) + ", epic " + $rc.root_epic + ") — name the open out-of-lineage candidate it beat with --beat, or recommend that one")}
                      end)
                   else null end) as $ro
                | ([$cands[] | select(.in_streak)]) as $ins
                | (if $rec == "" and ($cands | length) > 0 and ($ins | length) == ($cands | length)
                   then ("<run>: every candidate shares the lineage of " + ([$ins[].streak[]] | unique | join(", "))
                         + " (epic " + ([$ins[].root_epic] | unique | join(", ")) + "); add one from next-goal-candidates.sh outside it")
                   else null end) as $run_disq
                | {
                    beads: [$beads[] | . as $b
                      | (if $ro != null and $b.id == $rec then . + $ro
                         elif (cand($b.id) // {in_streak: false}).in_streak and $b.id != $rec then
                           . + {verdict: (if .verdict == "ok" then "warn" else .verdict end),
                                reason: (.reason + "; continues the lineage of " + ids(cand($b.id)) + " (epic " + cand($b.id).root_epic + ")")}
                         else . end)],
                    run_disqualified: $run_disq,
                    verdict: (if ($ro.verdict // "") == "disqualified" or $run_disq != null then "disqualified"
                              elif ($ro.verdict // "") == "warn" or ($rec == "" and ($ins | length) > 0) then "warn"
                              else "ok" end),
                    reason: ($ro.reason // $run_disq
                             // (if $rec != "" and $rc == null then ("--recommend " + $rec + " is not a usable candidate (see beads), so its lineage was not judged")
                                 elif $rec != "" then ($rec + " (epic " + ($rc.root_epic // "unknown") + ") is outside the lineage of the last " + ($window | length | tostring) + " closed goals")
                                 elif ($ins | length) > 0 then ("in-lineage candidates: " + ([$ins[].id] | join(", ")) + " — usable, but not as the recommendation without --beat")
                                 else ("no usable candidate continues the lineage of the last " + ($window | length | tostring) + " closed goals") end))
                  }')"
            BEADS_JSON="$(jq -c '.beads' <<<"$DECISION")"
            RUN_DISQ="$(jq -r '.run_disqualified // empty' <<<"$DECISION")"
            LINEAGE_JSON="$(jq -cn --argjson d "$DECISION" --argjson window "$WINDOW_OUT" --argjson cands "$CAND_OUT" \
                --argjson w "$LINEAGE_WINDOW" --argjson m "$LINEAGE_MIN" --arg rec "$RECOMMEND" --arg beat "$BEAT" \
                '{available: true, window: $window, threshold: {window: $w, min: $m},
                  recommend: (if $rec == "" then null else $rec end),
                  beat: (if $beat == "" then null else $beat end),
                  candidates: $cands, verdict: $d.verdict, reason: $d.reason}')"
        fi
    fi
fi

# ------------------------------------------------------------------ path checks
#
# The second half of the 2026-08-14 failure: the block proposed BUILDING things
# that already existed. A bead status check cannot catch that — the epic could
# have been open and the components still present. So a candidate whose verb is
# "create"/"build"/"add" has to assert the artifact's absence, and asserting is
# a command, not a belief.
# ---------------------------------------------------------------- OUT clause

# Every source the just-closed goal's condition can come from, in the order
# the user gave them, then the goal store's most recently closed goal.
OUT_SOURCES="[]"
for src in ${OUT_OF[@]+"${OUT_OF[@]}"}; do
    [[ -z "$src" ]] && continue
    label="text"; body="$src"
    if [[ "$src" =~ ^[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9.]+$ ]] && command -v bd >/dev/null 2>&1; then
        for root in ${ROOTS[@]+"${ROOTS[@]}"}; do
            raw="$(bd_show "$root" "$src")"
            if jq -e 'type == "array" and length > 0' >/dev/null 2>&1 <<<"$raw"; then
                label="bead $src"; body="$(jq -r '.[0].description // ""' <<<"$raw")"; break
            fi
        done
    fi
    if [[ "$label" == "text" && -f "$src" ]]; then
        label="file $src"; body="$(cat "$src" 2>/dev/null)"
    fi
    OUT_SOURCES="$(jq -c --arg l "$label" --arg b "$body" '. + [{source: $l, text: $b}]' <<<"$OUT_SOURCES")"
done
if [[ -n "$LAST_GOAL_ID" && -n "$LAST_GOAL_CONDITION" ]]; then
    OUT_SOURCES="$(jq -c --arg l "goal $LAST_GOAL_ID" --arg b "$LAST_GOAL_CONDITION" '. + [{source: $l, text: $b}]' <<<"$OUT_SOURCES")"
fi

# The recommendation as the reader will see it: the /goal text plus the
# recommended bead's title. Not its description — a bead filed as a follow-up
# often explains that it is OUT of the goal that spawned it, and would match.
REC_TITLE=""
if [[ -n "$RECOMMEND" ]]; then
    REC_TITLE="$(jq -r --arg id "$RECOMMEND" 'first(.[] | select(.id == $id)) | .title // ""' <<<"$BEADS_JSON")"
fi

OUT_JSON="$(jq -cn \
    --argjson sources "$OUT_SOURCES" --arg text "$TEXT" --arg title "$REC_TITLE" \
    --arg rec "$RECOMMEND" --arg override "$OUT_OVERRIDE" '
    def norm: ascii_downcase | gsub("[^a-z0-9]+"; " ") | gsub("^ +| +$"; "");
    def stop: ["any","the","a","an","to","of","or","and","in","on","for","with","by","from",
               "its","it","this","that","not","no","all","as","at","is","are","be","into","up"];
    def toks: norm | split(" ") | map(select(length > 0)) | map(select(. as $t | stop | index($t) | not));
    # Words gate the match; numbers and version tags ride along free, so
    # "export currency 646 to 694" still names "export currency at 694".
    def words: toks | map(select(test("[0-9]") | not));
    # Shared-prefix similarity: families/family, harvest/harvesting match;
    # currency/current does not.
    def cp($a; $b): [range(0; ([($a | length), ($b | length)] | min))] | map(select($a[:. + 1] == $b[:. + 1])) | length;
    def sim($a; $b): ($a == $b) or (cp($a; $b) as $c | $c >= 4 and $c >= (([($a | length), ($b | length)] | min) - 2));
    # The clause after the first "OUT:" up to the end of that paragraph.
    # jq splits "" into [], so the no-clause path must not index null.
    def clause: (split("OUT:") | if length > 1 then .[1:] | join("OUT:") else "" end) | (split("\n\n")[0] // "");
    def items: clause | split(",") | map(split(";")[]) | map(gsub("^\\s+|\\s+$"; ""))
               | map(select(length > 0))
               | map({item: ., words: words})
               | map(select((.words | length) >= 2 or ((.words | length) == 1 and (.words[0] | length) >= 6)));
    (($text + " " + $title) | toks) as $cand
    | [$sources[] | . as $s | (.text | items)[] | . + {source: $s.source}] as $all
    | [$all[] | select(all(.words[]; . as $w | any($cand[]; sim(.; $w))))] as $hits
    | (if $rec != "" then $rec elif $text != "" then "<text>" else null end) as $subject
    | if ($sources | length) == 0 then
        {available: false, reason: "no OUT source: pass --out-of <bead|file|text>, or no goal store answered", subject: $subject,
         sources: [], items: 0, matched: [], verdict: null}
      elif ($all | length) == 0 then
        {available: true, reason: ("no OUT clause found in " + ([$sources[].source] | join(", "))), subject: $subject,
         sources: [$sources[].source], items: 0, matched: [], verdict: "ok"}
      elif $cand == [] then
        {available: false, reason: "nothing to judge: pass --text with the /goal text and/or --recommend <bead>", subject: $subject,
         sources: [$sources[].source], items: ($all | length), matched: [], verdict: null}
      elif ($hits | length) == 0 then
        {available: true, reason: ("outside the OUT clause of " + ([$sources[].source] | unique | join(", "))), subject: $subject,
         sources: [$sources[].source], items: ($all | length), matched: [], verdict: "ok"}
      elif $override != "" then
        {available: true, verdict: "warn", subject: $subject,
         sources: [$sources[].source], items: ($all | length), matched: [$hits[] | {item, source}], override: $override,
         reason: ("named in the OUT clause of " + ($hits[0].source) + " (\"" + $hits[0].item + "\"); allowed on record because: " + $override)}
      else
        {available: true, verdict: "disqualified", subject: $subject,
         sources: [$sources[].source], items: ($all | length), matched: [$hits[] | {item, source}],
         reason: ("named in the OUT clause of " + ($hits[0].source) + " (\"" + $hits[0].item + "\") — the user excluded it there; re-proposing it reopens that decision. Say why it is now in with --out-override, or recommend something else")}
      end')"

if [[ "$(jq -r '.verdict // empty' <<<"$OUT_JSON")" == "disqualified" ]]; then
    OUT_REASON="$(jq -r '.reason' <<<"$OUT_JSON")"
    if [[ -n "$RECOMMEND" ]]; then
        BEADS_JSON="$(jq -c --arg id "$RECOMMEND" --arg r "$OUT_REASON" \
            'map(if .id == $id then . + {verdict: "disqualified", reason: $r} else . end)' <<<"$BEADS_JSON")"
    fi
    OUT_DISQ="$(jq -r '(.subject // "<text>") + " (" + (.matched[0].source) + " OUT: \"" + (.matched[0].item) + "\")"' <<<"$OUT_JSON")"
else
    OUT_DISQ=""
fi

for p in ${PATHS[@]+"${PATHS[@]}"}; do
    if [[ -e "$p" ]]; then
        detail="exists"
        [[ -d "$p" ]] && detail="exists, $(find "$p" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ') file(s)"
        entry="$(jq -cn --arg path "$p" --arg d "$detail" \
            '{path: $path, exists: true, verdict: "disqualified",
              reason: ("already present (" + $d + ") — a goal to build it would rebuild what is there")}')"
    else
        entry="$(jq -cn --arg path "$p" \
            '{path: $path, exists: false, verdict: "ok", reason: "absent, so there is something to build"}')"
    fi
    PATHS_JSON="${PATHS_JSON:-[]}"
    PATHS_JSON="$(jq -c --argjson e "$entry" '. + [$e]' <<<"$PATHS_JSON")"
done
PATHS_JSON="${PATHS_JSON:-[]}"

DISQUALIFIED="$(jq -cn --argjson b "$BEADS_JSON" --argjson p "$PATHS_JSON" --arg run "$RUN_DISQ" --arg out "$OUT_DISQ" \
    '[($b[] | select(.verdict == "disqualified") | .id),
      ($p[] | select(.verdict == "disqualified") | .path)]
     + (if $run == "" then [] else [$run] end)
     + (if $out == "" then [] else [$out] end) | unique')"

# `ok: (($disq | length) == 0)` — the OUTER parentheses are load-bearing. jq 1.7
# (Debian, and the CI runner) rejects `key: a == b` inside an object literal
# with "syntax error, unexpected ==", while jq 1.8 accepts it. Written the
# permissive way, this script emitted a compile error instead of JSON on every
# Linux host and parsed fine on the machine it was written on — the third time
# in this change's own history that a platform difference hid a defect, and the
# reason the header insists the environment where a bug cannot appear is not
# evidence it is absent. CI is the guard here; there is no way to pin a jq
# version from inside a test.
PAYLOAD="$(jq -cn \
    --arg schema "$SCHEMA_VERSION" \
    --arg stamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson roots_seen "$ROOTS_OK" \
    --argjson beads "$BEADS_JSON" \
    --argjson paths "$PATHS_JSON" \
    --argjson disq "$DISQUALIFIED" \
    --argjson lineage "$LINEAGE_JSON" \
    --argjson out "$OUT_JSON" \
    '{schema_version: $schema, available: true, verified_at: $stamp,
      roots_discovered: ($roots_seen == 1),
      beads: $beads, paths: $paths, disqualified: $disq,
      warnings: ([$beads[] | select(.verdict == "warn") | .id]
                 + (if $out.verdict == "warn" then [($out.subject // "<text>")] else [] end)),
      lineage: $lineage,
      out_clause: $out,
      ok: (($disq | length) == 0)}')"

if [[ "$(jq -r '.ok' <<<"$PAYLOAD")" == "true" ]]; then
    emit_and_exit "$PAYLOAD" 0
fi
emit_and_exit "$PAYLOAD" 3
