#!/usr/bin/env bash
# Review receipt for --role cross-lab-review (mk-zek32). One self-contained JSON
# file per reviewed PR head, for a verifier that must not need a second lookup.
# Written with mode 0600 by exclusive create, never overwritten. The file
# catches mistakes only: writer and verifier share an account.
#
# State, set by the flag parser in dispatch.sh:
#   RR_REPO RR_REPO_ID RR_PR RR_HEAD RR_BASE   (all five or none)
# Computed by _review_receipt_prepare, which runs before the review starts so a
# bad flag fails fast:
#   RR_HEAD_TREE RR_MERGE_TREE RR_DIFF_STAT RR_DIFF_SHA256

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
  local g=(git -C "${workdir:-.}")
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
}

# Strict verdict from the reviewer's final line. Prints PASS, "PASS WITH NOTES"
# or BLOCK; prints nothing (rc 1) when there is no acceptable VERDICT line, so
# no receipt is written. No Markdown is parsed: the output must contain no code
# fence (three backticks or tildes) and no HTML comment delimiter anywhere, and
# NUL bytes are rejected; the ruling must be the last non-blank line, start at column 0 and follow a
# blank line (or begin the file). Reviews that quote fences or comments get no
# receipt rather than a guess at what they render as.
_review_receipt_verdict() {
  local out="$1" last
  [[ -f "$out" ]] || return 1
  # Continue only on grep status 1 (no delimiter found); a match or any scan
  # error rejects. NUL bytes are rejected first: shell capture would drop them.
  local rc
  LC_ALL=C tr -d '\000' <"$out" | cmp -s - "$out" || return 1
  LC_ALL=C grep -qE '```|~~~|<!--|-->' "$out"; rc=$?
  [[ $rc -eq 1 ]] || return 1
  last="$(awk '
    { sub(/\r$/, "") }
    $0 ~ /[^[:space:]]/ { last = $0; lastok = (blank || NR == 1); blank = 0; next }
    { blank = 1 }
    END { if (lastok) print last }' "$out")"
  local re='^(\*\*|__)?[Vv][Ee][Rr][Dd][Ii][Cc][Tt][[:space:]]*:(\*\*|__)?[[:space:]]*(([^[:space:]*_`.]|[^[:space:]*_`].*[^[:space:]*_`.]))(\*\*|__)?[[:space:]]*$'
  [[ "$last" =~ $re ]] || return 1
  local v="${BASH_REMATCH[3]}"
  case "${v^^}" in
    PASS) echo PASS ;;
    "PASS WITH NOTES") echo "PASS WITH NOTES" ;;
    *) echo BLOCK ;;
  esac
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

# Writes the receipt. Args: output file, exit code. Echoes the path on success;
# on a non-write prints the reason to stderr and returns 1. Reviewer identity,
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
  local verdict
  verdict="$(_review_receipt_verdict "$out")" || { echo "review receipt: not written (no VERDICT line in review output)" >&2; return 1; }

  local dir file tmp
  dir="$(_review_receipt_dir)/${RR_REPO//\//__}"
  file="$dir/${RR_PR}-${RR_HEAD}.json"
  (umask 077; mkdir -p "$dir") 2>/dev/null || { echo "review receipt: cannot create $dir" >&2; return 1; }
  chmod 700 "$dir" 2>/dev/null || true
  tmp="$(jq -n --arg repo "$RR_REPO" --arg repo_id "$RR_REPO_ID" --argjson pr "$RR_PR" \
    --arg head "$RR_HEAD" --arg head_tree "$RR_HEAD_TREE" --arg base "$RR_BASE" \
    --arg merge_tree "$RR_MERGE_TREE" --arg stat "$RR_DIFF_STAT" --arg dsha "$RR_DIFF_SHA256" \
    --arg producer "$PRODUCER_IDENTITY" --arg reviewer "$reviewer" --arg verdict "$verdict" \
    --arg policy "$policy_hash" --arg did "${DISPATCH_ID:-}" --arg aid "${ATTEMPT_ID:-}" \
    --arg rel "${VALIDATOR_RELATIONSHIP:-}" --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '
    def nn: if . == "" then null else . end;
    {schema_version: 1, kind: "cross-lab-review-receipt", role: "cross-lab-review",
     repo: $repo, repo_id: $repo_id, pr: $pr, head_sha: $head, head_tree: $head_tree,
     base_sha: $base, expected_merge_tree: $merge_tree, diff_stat: $stat, diff_sha256: $dsha,
     producer_identity: $producer, reviewer_identity: $reviewer, validator_relationship: ($rel|nn),
     verdict: $verdict, policy_hash: $policy,
     dispatch_id: ($did|nn), attempt_id: ($aid|nn), created_at: $now}')" || return 1
  # Exclusive create: write a private temp file, then hard-link it into place.
  # link(2) fails on any existing entry, symlinks included, and the receipt
  # appears complete or not at all.
  local tmpf
  tmpf="$(umask 077; mktemp "$dir/.new.XXXXXX")" || { echo "review receipt: cannot create temp file in $dir" >&2; return 1; }
  if ! printf '%s\n' "$tmp" > "$tmpf" || ! ln -T "$tmpf" "$file" 2>/dev/null; then
    rm -f "$tmpf"
    echo "review receipt: not written ($file already exists or is unwritable)" >&2
    return 1
  fi
  rm -f "$tmpf"
  echo "review receipt: $file" >&2
  return 0
}
