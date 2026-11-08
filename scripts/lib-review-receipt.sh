#!/usr/bin/env bash
# Review receipt for --role cross-lab-review (mk-zek32). One self-contained JSON
# file per reviewed PR head, for a verifier that must not need a second lookup.
# Written with mode 0600 by exclusive create, never overwritten. The file
# catches mistakes only: writer and verifier share an account.
#
# Receipts are append-only per head: <pr>-<head>.json, then .2.json, .3.json.
# The first file is never rewritten, so a reader that opens only
# <pr>-<head>.json sees the first ruling and not a later correction. A reader
# that needs the effective ruling must follow the numbered chain, or call
# _review_receipt_effective. A later receipt supersedes an earlier one only when
# both have the same base_sha and diff_sha256 (mk-0qjva). The .verdict sidecar
# is unchanged by this layout.
#
# State, set by the flag parser in dispatch.sh:
#   RR_REPO RR_REPO_ID RR_PR RR_HEAD RR_BASE   (all five or none)
# Computed by _review_receipt_prepare, which runs before the review starts so a
# bad flag fails fast:
#   RR_HEAD_TREE RR_MERGE_TREE RR_DIFF_STAT RR_DIFF_SHA256 RR_CHANGED_PATHS_JSON

# Shared verdict word classifier (mk-0qjva): the same one dispatch.sh uses for
# the .verdict sidecar, so the receipt and the sidecar cannot disagree.
_rr_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-verdict.sh
# shellcheck source=lib-verdict.sh
source "$_rr_lib_dir/lib-verdict.sh"

_review_receipt_requested() {
  [[ -n "${RR_REPO:-}${RR_REPO_ID:-}${RR_PR:-}${RR_HEAD:-}${RR_BASE:-}" ]]
}

_review_receipt_dir() {
  printf '%s\n' "${CLAVAIN_REVIEW_RECEIPT_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/clavain/reviews}"
}

# Validates the flags and derives the head tree, expected merge tree and diff
# hash from the -C checkout. Returns 1 with a message on any problem.
_review_receipt_prepare() {
  local workdir="$1"
  local missing=""
  [[ -n "${RR_REPO:-}" ]] || missing+=" --repo"
  [[ -n "${RR_REPO_ID:-}" ]] || missing+=" --repo-id"
  [[ -n "${RR_PR:-}" ]] || missing+=" --pr"
  [[ -n "${RR_HEAD:-}" ]] || missing+=" --head"
  [[ -n "${RR_BASE:-}" ]] || missing+=" --base"
  if [[ -n "$missing" ]]; then
    echo "Error: review receipt needs all of --repo --repo-id --pr --head --base (missing:$missing)" >&2
    return 1
  fi
  [[ "$RR_REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ && "$RR_REPO" != */. && "$RR_REPO" != */.. && "$RR_REPO" != ../* && "$RR_REPO" != ./* ]] || { echo "Error: --repo must be OWNER/NAME" >&2; return 1; }
  [[ "$RR_REPO_ID" =~ ^[A-Za-z0-9_=-]+$ ]] || { echo "Error: --repo-id must be the immutable repository id" >&2; return 1; }
  [[ "$RR_PR" =~ ^[1-9][0-9]{0,8}$ ]] || { echo "Error: --pr must be a positive integer" >&2; return 1; }
  [[ "$RR_HEAD" =~ ^[0-9a-f]{40}$ ]] || { echo "Error: --head must be a full 40-hex commit sha" >&2; return 1; }
  [[ "$RR_BASE" =~ ^[0-9a-f]{40}$ ]] || { echo "Error: --base must be a full 40-hex commit sha" >&2; return 1; }
  command -v git >/dev/null 2>&1 || { echo "Error: git is required for a review receipt" >&2; return 1; }
  command -v jq >/dev/null 2>&1 || { echo "Error: jq is required for a review receipt" >&2; return 1; }
  # Review scratch mode: the -C checkout is the caller's real repository and its
  # local config is untrusted (merge drivers fire in merge-tree, and a clean
  # filter, textconv or external diff in a diff). Read it only through an
  # objects-only bare repository that borrows the real object store via
  # alternates, so no repo-local config or attributes are ever consulted. Every
  # object these commands write lands in that throwaway, not in the real repo.
  local shim="" rc
  if [[ "${REVIEW_SCRATCH:-false}" == true ]]; then
    shim="$(_review_receipt_shim "${workdir:-.}")" || {
      echo "Error: cannot open the -C checkout object store read-only for the review receipt" >&2; return 1; }
  fi
  _review_receipt_derive "${workdir:-.}" "$shim"; rc=$?
  [[ -z "$shim" ]] || rm -rf -- "$shim" 2>/dev/null || true
  return "$rc"
}

# Prints the path of an objects-only bare repository whose alternates point at
# the object store of the checkout in $1. No config, no attributes, no hooks.
_review_receipt_shim() {
  local workdir="$1" objdir shim
  declare -F _review_scratch_git >/dev/null || return 1
  objdir="$(_review_scratch_git -C "$workdir" rev-parse --path-format=absolute --git-path objects 2>/dev/null)" \
    && [[ -d "$objdir" ]] || return 1
  shim="$(mktemp -d "${TMPDIR:-/tmp}/clavain-review-shim.XXXXXX")" || return 1
  if _review_scratch_git init --bare --quiet --template= "$shim" >/dev/null 2>&1 \
     && printf '%s\n' "$objdir" >"$shim/objects/info/alternates"; then
    printf '%s\n' "$shim"
  else
    rm -rf -- "$shim" 2>/dev/null || true
    return 1
  fi
}

_review_receipt_derive() {
  local workdir="$1" shim="$2"
  local g=(git -C "${workdir:-.}")
  [[ -z "$shim" ]] || g=(_review_scratch_git --git-dir "$shim")
  local sha
  for sha in "$RR_HEAD" "$RR_BASE"; do
    [[ "$("${g[@]}" cat-file -t "$sha" 2>/dev/null)" == commit ]] || {
      echo "Error: $sha is not a commit in the -C checkout" >&2; return 1; }
  done
  RR_HEAD_TREE="$("${g[@]}" rev-parse --verify "${RR_HEAD}^{tree}" 2>/dev/null)" || return 1
  # Tree git would produce by merging head onto base; no worktree touched.
  local mt mt_rc
  mt="$("${g[@]}" merge-tree --write-tree "$RR_BASE" "$RR_HEAD" 2>/dev/null)"; mt_rc=$?
  RR_MERGE_TREE="${mt%%$'\n'*}"
  [[ "$mt_rc" == 0 && "$RR_MERGE_TREE" =~ ^[0-9a-f]{40}$ ]] || {
    echo "Error: head does not merge cleanly onto base; no expected merge tree" >&2; return 1; }
  RR_DIFF_STAT="$("${g[@]}" diff --no-ext-diff --no-textconv --no-renames --shortstat "$RR_BASE" "$RR_HEAD" 2>/dev/null)" || {
    echo "Error: git diff --shortstat failed" >&2; return 1; }
  RR_DIFF_STAT="${RR_DIFF_STAT#"${RR_DIFF_STAT%%[![:space:]]*}"}"
  # sha256 of the raw diff bytes, with no shell capture in between. Both stages
  # must succeed, or a failed diff would attest the empty-stream digest.
  local dsum
  dsum="$("${g[@]}" diff --no-ext-diff --no-textconv --no-renames --binary "$RR_BASE" "$RR_HEAD" 2>/dev/null | sha256sum; printf ' %s' "${PIPESTATUS[0]}")"
  [[ "${dsum##* }" == 0 ]] || { echo "Error: git diff failed; no diff hash" >&2; return 1; }
  RR_DIFF_SHA256="${dsum%% *}"
  [[ "$RR_DIFF_SHA256" =~ ^[0-9a-f]{64}$ ]] || return 1
  # Repo-relative changed paths. git emits NUL-separated names; NUL boundaries are
  # kept until JSON encoding (a name may contain a newline). The result is a JSON
  # object {"total": N, "paths": [first 200, sorted]}, so no later step ever
  # handles the full list.
  local pj
  pj="$("${g[@]}" diff --no-ext-diff --no-textconv --no-renames --name-only -z "$RR_BASE" "$RR_HEAD" 2>/dev/null \
    | python3 -c '
import json, sys
names = sorted(n.decode("utf-8", "replace") for n in sys.stdin.buffer.read().split(b"\0") if n)
json.dump({"total": len(names), "paths": names[:200]}, sys.stdout)
'; printf ' %s' "${PIPESTATUS[0]}${PIPESTATUS[1]}")"
  [[ "${pj##* }" == 00 ]] || { echo "Error: git diff --name-only failed" >&2; return 1; }
  RR_CHANGED_PATHS_JSON="${pj% *}"
}

# Verdict from the reviewer's final line, in two steps that share one word list
# (scripts/lib-verdict.sh):
#   _review_receipt_verdict_word FILE   prints the raw word after "VERDICT:"
#   _review_receipt_verdict FILE        prints PASS, "PASS WITH NOTES", BLOCK or UNKNOWN
# PASS, PASS WITH NOTES (also PASS-WITH-NOTES, PASS_WITH_NOTES) and FAIL are the
# vocabulary. FAIL and its alias BLOCK both record BLOCK (mk-tl0ou.3.4). Only
# FAIL and BLOCK may carry an explanation; a passing ruling allows at most a
# trailing period. A word outside the vocabulary (APPROVE, a misspelling, PASS
# followed by prose) is recorded as UNKNOWN with a warning on stderr: it is
# neither a pass nor a block, and a later review of the same change (same base
# and diff hash) can supersede it (mk-0qjva, mk-4c909). Both return 1, printing nothing, when there is no
# acceptable VERDICT line at all, so no receipt is written and the dispatch
# fails. No Markdown is parsed: the output must contain no code fence (three
# backticks or tildes) and no HTML comment delimiter anywhere, and NUL bytes are
# rejected; the ruling must be the last non-blank line, start at column 0 and
# follow a blank line (or begin the file). Reviews that quote fences or comments
# get no receipt rather than a guess at what they render as.
_review_receipt_verdict_word() {
  verdict_strict_word "$1"
}

_review_receipt_verdict() {
  local out="$1" v
  v="$(_review_receipt_verdict_word "$out")" || return 1
  case "$(verdict_word_class "$v")" in
    PASS) echo PASS ;;
    PASS_WITH_NOTES) echo "PASS WITH NOTES" ;;
    FAIL) echo BLOCK ;;
    *)
      echo "review receipt: unrecognised verdict word '$(_review_receipt_clean_word "$v")'; accepted: PASS, PASS WITH NOTES, FAIL (BLOCK is read as FAIL). Recorded as UNKNOWN, not as a pass or a block." >&2
      echo UNKNOWN ;;
  esac
}

# The raw word as stored in a receipt or printed in a warning: control
# characters removed, at most 120 characters.
_review_receipt_clean_word() {
  local w
  w="$(printf '%s' "$1" | LC_ALL=C tr -d '[:cntrl:]')"
  printf '%s' "${w:0:120}"
}

_review_receipt_lab() {
  case "${1,,}" in
    claude*|anthropic*|opus*|sonnet*|haiku*|fable*) echo anthropic ;;
    gpt*|codex*|openai*|astra*|sol*|o[0-9]*) echo openai ;;
    kimi*|moonshot*) echo moonshot ;;
    gemini*|google*) echo google ;;
    *) echo "unknown:${1,,}" ;;
  esac
}

# Effective receipt for the change reviewed by a receipt. Arg: the path of any
# receipt in the chain (normally the first, <pr>-<head>.json). Prints the path
# of the highest-numbered regular receipt with the same base_sha and
# diff_sha256 as that receipt, across gaps in the numbering; prints that receipt's own path when nothing
# later matches. Returns 1 when the argument is not a readable receipt with a
# base_sha and diff_sha256. Symlinks and non-regular entries are ignored.
_review_receipt_effective() {
  local given="$1" first scope want n pf best=""
  [[ -f "$given" && ! -L "$given" ]] || return 1
  first="$given"
  if [[ "$given" =~ ^(.*)\.[0-9]+\.json$ ]]; then first="${BASH_REMATCH[1]}.json"; fi
  scope="$(jq -r '[.base_sha, .diff_sha256] | join(" ")' "$given" 2>/dev/null)" || return 1
  [[ -n "$scope" && "$scope" != " " && "$scope" != null* ]] || return 1
  best="$given"
  # Scan every possible numbered path, highest first, across gaps. Only
  # existing regular files are read; the first one in the same scope wins.
  for (( n = 999; n >= 1; n-- )); do
    if (( n == 1 )); then pf="$first"; else pf="${first%.json}.$n.json"; fi
    [[ -f "$pf" && ! -L "$pf" ]] || continue
    if [[ "$(jq -r '[.base_sha, .diff_sha256] | join(" ")' "$pf" 2>/dev/null)" == "$scope" ]]; then
      best="$pf"; break
    fi
  done
  printf '%s\n' "$best"
}

# Writes the receipt. Args: output file, exit code. Echoes the path on success;
# on a non-write prints the reason to stderr and returns 1. A receipt whose
# verdict word is not in the vocabulary is written as UNKNOWN and returns 3. Reviewer identity,
# producer identity and policy hash come from the run, never from flags.
_review_receipt_write() {
  local out="$1" rc="$2"
  [[ "$rc" == 0 ]] || { echo "review receipt: not written (dispatch exit $rc)" >&2; return 1; }
  [[ -n "${PRODUCER_IDENTITY:-}" ]] || { echo "review receipt: not written (no producer identity)" >&2; return 1; }
  local reviewer="${MODEL:-}" policy_hash
  [[ -n "$reviewer" ]] || { echo "review receipt: not written (no reviewer model identity)" >&2; return 1; }
  policy_hash="$(jq -r '.policy_hash // empty' <<< "${RESOLVED_ROUTE_JSON:-}" 2>/dev/null)"
  [[ "$policy_hash" =~ ^[0-9a-f]{64}$ ]] || { echo "review receipt: not written (no policy hash)" >&2; return 1; }
  local prod_lab rev_lab
  prod_lab="$(_review_receipt_lab "$PRODUCER_IDENTITY")"
  rev_lab="$(_review_receipt_lab "$reviewer")"
  if [[ "$prod_lab" == unknown:* || "$rev_lab" == unknown:* || "$prod_lab" == "$rev_lab" ]]; then
    echo "review receipt: not written (producer lab '$prod_lab' and reviewer lab '$rev_lab' are not provably different)" >&2
    return 1
  fi
  [[ "${CAPACITY_SUBSTITUTE_JSON:-}" == "" ]] || { echo "review receipt: not written (capacity substitute review)" >&2; return 1; }
  local verdict verdict_raw
  verdict="$(_review_receipt_verdict "$out")" || { echo "review receipt: not written (no usable VERDICT line in review output; the last line must be 'VERDICT: PASS', 'VERDICT: PASS WITH NOTES' (a trailing period is allowed) or start with 'VERDICT: FAIL' or 'VERDICT: BLOCK' with an optional explanation)" >&2; return 1; }
  verdict_raw="$(_review_receipt_clean_word "$(_review_receipt_verdict_word "$out")")"

  # Additive fields (schema_version stays 1; verdict logic is untouched). One
  # extractor, scripts/receipt-findings.py: unparsed bodies record
  # findings_source "unknown" and findings_total null, never a fake zero.
  local fx_json _rr_here
  _rr_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fx_json="$(python3 "$_rr_here/receipt-findings.py" --detail "$out" 2>/dev/null)" || fx_json=""
  jq -e 'type == "object"' <<<"$fx_json" >/dev/null 2>&1 || fx_json='{"source":"unknown","total":null,"findings":[]}'

  # No review-derived text goes on the jq command line (OS argument limit):
  # findings and changed paths are read from process substitutions; the rest
  # are fixed-size identities, hashes and a one-line shortstat.
  # Sandbox the review ran under. A scratch-write receipt is bound to the same
  # head as any other and also records the tree of the clone it ran in, which
  # must equal head_tree; a mismatch means no receipt.
  local sandbox_mode="${SANDBOX:-}" scratch_tree=""
  if [[ "${REVIEW_SCRATCH:-false}" == true ]]; then
    sandbox_mode="scratch-write"
    scratch_tree="${REVIEW_SCRATCH_TREE:-}"
    [[ -n "$scratch_tree" && "$scratch_tree" == "$RR_HEAD_TREE" ]] || {
      echo "review receipt: not written (scratch tree does not match head tree)" >&2; return 1; }
  fi
  local dir file tmp
  dir="$(_review_receipt_dir)/${RR_REPO//\//__}"
  file="$dir/${RR_PR}-${RR_HEAD}.json"
  (umask 077; mkdir -p "$dir") 2>/dev/null || { echo "review receipt: cannot create $dir" >&2; return 1; }
  chmod 700 "$dir" 2>/dev/null || true
  tmp="$(jq -n --arg repo "$RR_REPO" --arg repo_id "$RR_REPO_ID" --argjson pr "$RR_PR" \
    --arg head "$RR_HEAD" --arg head_tree "$RR_HEAD_TREE" --arg base "$RR_BASE" \
    --arg merge_tree "$RR_MERGE_TREE" --arg stat "$RR_DIFF_STAT" --arg dsha "$RR_DIFF_SHA256" \
    --arg producer "$PRODUCER_IDENTITY" --arg reviewer "$reviewer" --arg verdict "$verdict" --arg verdict_raw "$verdict_raw" \
    --arg policy "$policy_hash" --arg did "${DISPATCH_ID:-}" --arg aid "${ATTEMPT_ID:-}" \
    --arg rel "${VALIDATOR_RELATIONSHIP:-}" --arg sandbox "$sandbox_mode" --arg scratch_tree "$scratch_tree" --slurpfile fxs <(printf '%s' "$fx_json") --slurpfile cp <(printf '%s' "${RR_CHANGED_PATHS_JSON:-}") --arg now "$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)" '
    def nn: if . == "" then null else . end;
    $fxs[0] as $fx |
    {schema_version: 1, kind: "cross-lab-review-receipt", role: "cross-lab-review",
     repo: $repo, repo_id: $repo_id, pr: $pr, head_sha: $head, head_tree: $head_tree,
     base_sha: $base, expected_merge_tree: $merge_tree, diff_stat: $stat, diff_sha256: $dsha,
     producer_identity: $producer, reviewer_identity: $reviewer, validator_relationship: ($rel|nn),
     verdict: $verdict, verdict_raw: $verdict_raw, policy_hash: $policy, sandbox: ($sandbox|nn),
     dispatch_id: ($did|nn), attempt_id: ($aid|nn), created_at: $now,
     findings: (($fx.findings // [])[:200]),
     findings_source: (if $fx.source == "unknown" then "unknown" elif $fx.source == "conflict" then "conflict" else "body" end),
     findings_total: (if $fx.source == "unknown" then null else $fx.total end),
     changed_paths: ($cp[0].paths // [])}
    + (if $scratch_tree != "" then {scratch_tree: $scratch_tree} else {} end)
    + (if ($cp[0].total // 0) > 200 then {changed_paths_truncated: true} else {} end)
    + (if (($fx.findings // []) | length) > 200 then {findings_truncated: true} else {} end)
    + (if $fx.source == "conflict" then {findings_block_total: $fx.block_total} else {} end)')" || return 1
  # Append-only: the first receipt for a head is <pr>-<head>.json; a later run
  # on the same head is recorded as <pr>-<head>.2.json, .3.json, ... and nothing
  # is overwritten or deleted, so a reader that only reads <pr>-<head>.json sees
  # exactly what it always saw. The number is the order of successful insertion,
  # not of review start; created_at is each receipt's own clock. A path that
  # is not a regular file (directory, symlink) is refused, never skipped.
  # Exclusive create: write a private temp file, then hard-link it into place.
  # link(2) fails on any existing entry, symlinks included, and the receipt
  # appears complete or not at all.
  #
  # Supersession is scoped (design choice, mk-0qjva): a later receipt names an
  # earlier one in supersedes/supersedes_verdict only when both reviewed the same
  # change, meaning equal base_sha and equal diff_sha256. The nearest earlier
  # receipt with that scope is named. A receipt for a different base or diff (for
  # example an empty diff with base equal to head) is written as its own receipt
  # and supersedes nothing, so it cannot clear a block it did not review.
  local tmpf n=1 cand="$file"
  tmpf="$(umask 077; mktemp "$dir/.new.XXXXXX")" || { echo "review receipt: cannot create temp file in $dir" >&2; return 1; }
  while :; do
    # Find a free numbered path first (cheap existence checks only), so the
    # predecessor scan below runs once per attempt and not once per occupied
    # slot. A symlink (dangling included) or non-regular entry is refused.
    while [[ -e "$cand" || -L "$cand" ]]; do
      if [[ -L "$cand" || ! -f "$cand" || $n -ge 999 ]]; then
        rm -f "$tmpf"
        echo "review receipt: not written ($cand is not a regular file or unwritable)" >&2
        return 1
      fi
      n=$((n + 1)); cand="${file%.json}.$n.json"
    done
    local prev_name="" prev_file="" prev_verdict="" k pf
    if (( n > 1 )); then
      for (( k = n - 1; k >= 1; k-- )); do
        if (( k == 1 )); then pf="$file"; else pf="${file%.json}.$k.json"; fi
        [[ -f "$pf" && ! -L "$pf" ]] || continue
        if [[ "$(jq -r '[.base_sha, .diff_sha256] | join(" ")' "$pf" 2>/dev/null)" == "$RR_BASE $RR_DIFF_SHA256" ]]; then
          prev_file="$pf"; break
        fi
      done
      if [[ -n "$prev_file" ]]; then
        prev_name="${prev_file##*/}"
        prev_verdict="$(jq -r '.verdict // empty' "$prev_file" 2>/dev/null)" || prev_verdict=""
      fi
    fi
    jq --argjson seq "$n" --arg prev "$prev_name" --arg pv "$prev_verdict" \
      '.sequence = $seq | if $prev != "" then .supersedes = $prev | .supersedes_verdict = (if $pv == "" then null else $pv end) else . end' \
      <<<"$tmp" > "$tmpf" || { rm -f "$tmpf"; echo "review receipt: not written ($file is unwritable)" >&2; return 1; }
    # Exclusive create. If another writer took the slot in the meantime, loop:
    # the free-slot search moves past it and the chain is rescanned.
    ln -T "$tmpf" "$cand" 2>/dev/null && break
    if [[ ! -e "$cand" && ! -L "$cand" ]]; then
      rm -f "$tmpf"; echo "review receipt: not written ($cand is unwritable)" >&2; return 1
    fi
  done
  file="$cand"
  rm -f "$tmpf"
  echo "review receipt: $file" >&2
  # An UNKNOWN verdict is on record but is not a usable ruling: return 3 so the
  # dispatch still exits non-zero and the review is run again (mk-0qjva).
  [[ "$verdict" != UNKNOWN ]] || return 3
  return 0
}
