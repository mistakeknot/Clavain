#!/usr/bin/env bash
# review-round.sh — one governed review round with the gate speedups (beads
# mk-pldo4 panel, mk-1z4h1 CI+review together, mk-l4j9x pre-review gate,
# mk-tc198 confirming-round scope). It wraps scripts/dispatch.sh and changes no
# gate: every lens runs through `dispatch.sh --role cross-lab-review` with the
# producer identity, so reviewer independence and the seat rules are unchanged.
# The panel is ONE round. This script never loops rounds; the cap stays with the
# caller.
#
# Usage:
#   review-round.sh --mode first|confirm --repo DIR --base REF --head SHA \
#       --producer-identity ID --out-dir DIR [--prompt-file F] \
#       [--gate-cmd 'CMD']... [--ci-cmd 'CMD'] [--prior-findings FILE] [--dry-run]
#
# --gate-cmd  Pre-review gate (run in --repo, repeatable). Any failure stops the
#             round with exit 10 BEFORE any review is dispatched.
# --ci-cmd    Started in the background at the same head as the review; its log
#             is $OUT/ci.log and the path is given to every reviewer.
# --mode first    Panel: lenses general, safety, correctness run in parallel on
#                 the same head; findings merge into $OUT/receipt.md.
# --mode confirm  One reviewer; prompt carries the fix diff (previous head is
#                 --prior-head) plus --prior-findings; full PR stays available.
# --out-dir must be new or empty: one attempt directory per round, so an earlier
# lens file can never supply this round's verdict.
# A lens counts only if dispatch exited 0, its .verdict sidecar has STATUS pass,
# warn or fail, the body has exactly one VERDICT line (outside code fences, last
# before dispatch's trailing block) that agrees with the sidecar, and it carries
# no PROVISIONAL line (a same-lab capacity substitute is not an independent
# review). Routing evidence (actual reviewer, policy hash) stays in dispatch's own
# governed run receipt; this wrapper copies the sidecar but does not replace or
# re-derive it. Gates, CI and reviewers run in a fresh detached worktree.
# A failed CI run makes the round fail.
# Exit: 0 receipt, all lenses and CI clean; 2 usage; 3 a lens gave no valid
#       verdict; 4 CI failed; 5 a lens was provisional; 10 pre-gate failed;
#       11 checkout is not the clean exact head; 12 --prior-head is not an
#       ancestor of --head (rebase: run a full first round instead).
# The receipt's verdict line is PASS / PASS WITH NOTES only when every lens is
# clean; otherwise FAIL, NONE or PROVISIONAL, and the exit code is non-zero
# unless the verdict is a genuine FAIL from a reviewer (exit 0, receipt FAIL).
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"   # keep the caller's PATH: dispatch needs ic
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPATCH="${REVIEW_ROUND_DISPATCH:-$HERE/dispatch.sh}"

# lens_verdict FILE SIDECAR_STATUS PROVISIONAL(0|1) -> prints the lens verdict:
# PASS | PASS WITH NOTES | FAIL | PROVISIONAL | NONE (reason). Pure: reads FILE only.
# Body verdict: strip the reviewer's trailing block; the last non-blank line must
# be the only line-start VERDICT, outside any code fence. A terminal block, when
# present, must be exactly STATUS + '---' and carry the status of that body
# verdict. The sidecar must be one dispatch can produce for that body (dispatch
# records a first-line FAIL as warn, and a blockless PASS WITH NOTES as pass).
lens_verdict() {
  local f=$1 sst=$2 prov=$3 ndelim body blk tailok=1 blkst= last fenced nver bwant ok
  ndelim=$(grep -c '^--- VERDICT ---\r\?$' "$f" || true)
  if [ "$ndelim" -eq 0 ]; then body=$(cat "$f")
  elif [ "$ndelim" -eq 1 ]; then
    body=$(awk '/^--- VERDICT ---\r?$/ {exit} {print}' "$f")
    blk=$(awk 'f&&NF{sub(/\r$/,""); print} /^--- VERDICT ---\r?$/{f=1}' "$f")
    if [ "$(wc -l <<< "$blk")" -eq 2 ] && [[ "$(sed -n 1p <<< "$blk")" =~ ^STATUS:\ (pass|warn|fail)$ ]] && [ "$(sed -n 2p <<< "$blk")" = "---" ]; then
      blkst=${BASH_REMATCH[1]}
    else tailok=0; fi
  else body=$(cat "$f"); tailok=0; fi
  last=$(grep -v '^[[:space:]]*$' <<< "$body" | tail -1 || true)
  # Markdown fence state (backtick or tilde, closing fence at least as long):
  # the verdict line must sit outside every fence and no fence may stay open.
  fenced=$(awk '
    { if (match($0,/^ {0,3}(`{3,}|~{3,})/)) { m=substr($0,RSTART,RLENGTH); gsub(/ /,"",m); c=substr(m,1,1); n=length(m)
        if (!open) { open=1; fc=c; fl=n; next }
        else if (c==fc && n>=fl) { t=$0; sub(/^ {0,3}/,"",t); sub(/[ \t\r]*$/,"",t); gsub(c,"",t); if (t=="") { open=0; next } } }
      if (open && $0 ~ /^VERDICT: /) bad=1 }
    END { print (open||bad) ? 1 : 0 }' <<< "$body")
  nver=$(grep -c '^VERDICT: ' <<< "$body" || true)
  bwant=; case "$last" in "VERDICT: PASS") bwant=pass;; "VERDICT: PASS WITH NOTES") bwant=warn;; "VERDICT: FAIL") bwant=fail;; esac
  [ "$ndelim" -eq 0 ] || [ "$blkst" = "$bwant" ] || tailok=0
  ok=0
  case "$last:$sst" in
    "VERDICT: PASS:pass"|"VERDICT: PASS WITH NOTES:warn"|"VERDICT: FAIL:fail"|"VERDICT: FAIL:warn") ok=1;;
    "VERDICT: PASS WITH NOTES:pass") [ "$ndelim" -ne 0 ] || ok=1;;
  esac
  if [ "$tailok" -ne 1 ] || [ "$nver" -ne 1 ] || [ "$fenced" -ne 0 ] || [ "$ok" -ne 1 ]; then
    echo "NONE (verdict line malformed, fenced, or disagrees with sidecar STATUS: $sst)"
  elif [ "$last" = "VERDICT: FAIL" ]; then echo FAIL
  elif [ "$prov" = 1 ]; then echo PROVISIONAL
  else echo "${last#VERDICT: }"
  fi
}
[ "${REVIEW_ROUND_SOURCE_ONLY:-}" != 1 ] || return 0 2>/dev/null || exit 0


MODE=first; REPO=; BASE=; HEAD=; PRODUCER=; OUT=; PROMPT=; CI=; PRIOR=; PRIOR_HEAD=; DRY=0
GATES=()
die() { echo "review-round: $*" >&2; exit 2; }
while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE=$2; shift 2;;
    --repo) REPO=$2; shift 2;;
    --base) BASE=$2; shift 2;;
    --head) HEAD=$2; shift 2;;
    --producer-identity) PRODUCER=$2; shift 2;;
    --out-dir) OUT=$2; shift 2;;
    --prompt-file) PROMPT=$2; shift 2;;
    --gate-cmd) GATES+=("$2"); shift 2;;
    --ci-cmd) CI=$2; shift 2;;
    --prior-findings) PRIOR=$2; shift 2;;
    --prior-head) PRIOR_HEAD=$2; shift 2;;
    --dry-run) DRY=1; shift;;
    -h|--help) sed -n 2,28p "$0"; exit 0;;
    *) die "unknown argument: $1";;
  esac
done
[ -n "$REPO" ] && [ -n "$BASE" ] && [ -n "$HEAD" ] && [ -n "$PRODUCER" ] && [ -n "$OUT" ] || die "--repo, --base, --head, --producer-identity and --out-dir are required"
case "$MODE" in first|confirm) ;; *) die "--mode must be first or confirm";; esac
if [ "$MODE" = confirm ]; then
  [ -n "$PRIOR" ] && [ -f "$PRIOR" ] || die "--mode confirm needs --prior-findings FILE"
  [ -n "$PRIOR_HEAD" ] || die "--mode confirm needs --prior-head SHA"
fi
REPO=$(realpath "$REPO"); OUT=$(realpath -m "$OUT")
[ -z "$PROMPT" ] || PROMPT=$(realpath "$PROMPT"); [ -z "$PRIOR" ] || PRIOR=$(realpath "$PRIOR")
if [ -d "$OUT" ] && [ -n "$(ls -A "$OUT")" ]; then die "--out-dir $OUT is not empty; use a new directory per round"; fi
mkdir -p "$OUT"

# Evidence is fresh only at the exact head: refuse a moved checkout.
exact_head() {
  [ "$(git -C "$REPO" rev-parse HEAD)" = "$HEAD" ] && [ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]
}
exact_head || { echo "review-round: checkout is not the clean exact head $HEAD" >&2; exit 11; }
# Everything below (gates, CI, reviewers) runs in a fresh detached worktree at the
# exact head, so a gate, the CI run or another process cannot alter what the
# reviewers read, and untracked files in the caller's checkout cannot leak in.
SRC_REPO=$REPO
REPO="$OUT/wt"; CIWT="$OUT/wt-ci"   # separate trees: CI cannot alter what reviewers read
git -C "$SRC_REPO" worktree add -q --detach "$REPO" "$HEAD" || die "cannot create isolated worktree"
git -C "$SRC_REPO" worktree add -q --detach "$CIWT" "$HEAD" || die "cannot create CI worktree"
trap 'git -C "$SRC_REPO" worktree remove --force "$REPO" >/dev/null 2>&1 || true; git -C "$SRC_REPO" worktree remove --force "$CIWT" >/dev/null 2>&1 || true' EXIT
exact_head_wt() { [ "$(git -C "$REPO" rev-parse HEAD)" = "$HEAD" ] && [ -z "$(git -C "$REPO" status --porcelain --untracked-files=all)" ]; }
if [ "$MODE" = confirm ]; then
  git -C "$REPO" merge-base --is-ancestor "$PRIOR_HEAD" "$HEAD" 2>/dev/null || { echo "review-round: $PRIOR_HEAD is not an ancestor of $HEAD (rebased?); run a full first round" >&2; exit 12; }
fi

# C. Pre-review gate: nothing is dispatched until it passes.
: > "$OUT/gate.log"
for g in "${GATES[@]+"${GATES[@]}"}"; do
  echo "\$ $g" >> "$OUT/gate.log"
  if ! (cd "$REPO" && bash -c "$g") >> "$OUT/gate.log" 2>&1; then
    echo "review-round: pre-review gate failed: $g (see $OUT/gate.log); no review dispatched" >&2
    exit 10
  fi
done

exact_head_wt || { echo "review-round: a gate command changed the worktree" >&2; exit 11; }

# B. CI at the same head, started alongside the review.
CIPID=
if [ -n "$CI" ]; then
  if [ "$DRY" = 1 ]; then echo "would start CI: $CI"; else
    ( rc=0; (cd "$CIWT" && bash -c "$CI") || rc=$?; echo "CI-EXIT: $rc"; exit "$rc" ) > "$OUT/ci.log" 2>&1 & CIPID=$!
  fi
fi
CINOTE="Tests: you are read-only and cannot run them. "
[ -n "$CI" ] && CINOTE="${CINOTE}CI for this exact head runs alongside you; its log is $OUT/ci.log (it may still be growing; a final line 'CI-EXIT: N' marks completion). Read it instead of reporting tests as not run. "

lens_text() {
  case "$1" in
    general) echo "General cross-lab review.";;
    safety) echo "Lens: security and safety only (credentials, trust boundaries, fail-open paths, injection, destructive actions, rollback). Apply the interflux fd-safety discipline.";;
    correctness) echo "Lens: correctness only (data consistency, races, error handling, edge cases, test adequacy). Apply the interflux fd-correctness discipline.";;
  esac
}
build_prompt() { # lens -> file
  local lens=$1 f="$OUT/prompt-$1.txt"
  {
    [ -n "$PROMPT" ] && cat "$PROMPT"
    echo
    lens_text "$lens"
    echo "Exact head under review: $HEAD (checked out at $REPO). $CINOTE"
    if [ "$MODE" = confirm ]; then
      echo "Confirming round. Primary scope is the fix diff since $PRIOR_HEAD (git diff $PRIOR_HEAD..$HEAD) and whether each earlier finding below is fixed; the full PR (git diff $BASE...$HEAD) is available for context and anything new you find in it still counts."
      echo "Earlier findings:"; cat "$PRIOR"
    else
      echo "Review git diff $BASE...$HEAD."
    fi
    echo "Report each finding with severity LOW / MEDIUM / HIGH. Run only read-only commands."
    echo "End with a line 'VERDICT: PASS', 'VERDICT: PASS WITH NOTES' or 'VERDICT: FAIL' (exactly one such line, not inside a code fence), then as the very last lines this block with STATUS pass (for PASS), warn (PASS WITH NOTES) or fail (FAIL):"
    printf -- '--- VERDICT ---\nSTATUS: pass|warn|fail\n---\n'
  } > "$f"
  echo "$f"
}

LENSES=(general); [ "$MODE" = first ] && LENSES=(general safety correctness)
PIDS=(); declare -A LPID
for l in "${LENSES[@]}"; do
  pf=$(build_prompt "$l")
  cmd=("$DISPATCH" --role cross-lab-review --producer-identity "$PRODUCER" -s read-only --prompt-file "$pf" -C "$REPO" -o "$OUT/lens-$l.md")
  if [ "$DRY" = 1 ]; then echo "would run: ${cmd[*]}"; continue; fi
  "${cmd[@]}" > "$OUT/lens-$l.log" 2>&1 & LPID[$l]=$!
done
[ "$DRY" = 1 ] && exit 0

RC=0; VERD=(); PROV=0
for l in "${LENSES[@]}"; do
  drc=0; wait "${LPID[$l]}" || drc=$?
  f="$OUT/lens-$l.md"; v=NONE
  sst=$(sed -n 's/^STATUS: //p' "$f.verdict" 2>/dev/null | head -1 || true)
  if [ "$drc" -ne 0 ]; then v="NONE (dispatch exit $drc)"
  elif ! [[ "$sst" =~ ^(pass|warn|fail)$ ]]; then v="NONE (dispatch sidecar STATUS '${sst:-missing}')"
  else
    pl=0; ! grep -q '^PROVISIONAL:' "$f.verdict" 2>/dev/null || pl=1
    v=$(lens_verdict "$f" "$sst" "$pl")
    [ "$v" != PROVISIONAL ] || PROV=1
  fi
  case "$v" in NONE*) RC=3;; esac
  VERD+=("$l: $v")
done
CIRC=0
if [ -n "$CIPID" ]; then
  wait "$CIPID" || CIRC=$?
  [ "$CIRC" -eq 0 ] || RC=4
fi
[ "$RC" -ne 0 ] || [ "$PROV" -eq 0 ] || RC=5
ci_wt_ok() { [ -z "$CIPID" ] || { [ "$(git -C "$CIWT" rev-parse HEAD)" = "$HEAD" ] && [ -z "$(git -C "$CIWT" status --porcelain --untracked-files=no)" ]; }; }
ci_wt_ok || { echo "review-round: CI changed its worktree; its result is not evidence for $HEAD" >&2; RC=11; }
exact_head_wt || { echo "review-round: worktree changed during the round; evidence is not at $HEAD" >&2; RC=11; }

# Merge: one receipt; findings de-duplicated by normalised text; overall verdict
# is the worst lens (FAIL > NONE > PASS WITH NOTES > PASS), never an average.
{
  echo "# Review round receipt"
  echo "mode: $MODE  head: $HEAD  producer: $PRODUCER  lenses: ${LENSES[*]}"
  echo "counts as one round"
  echo; echo "## Lens verdicts"; printf -- '- %s\n' "${VERD[@]}"
  echo; echo "## Merged findings (de-duplicated)"
  for l in "${LENSES[@]}"; do
    grep -iE '(^|[^A-Za-z])(LOW|MEDIUM|HIGH)([^A-Za-z]|$)' "$OUT/lens-$l.md" 2>/dev/null | grep -v '^VERDICT:' | sed "s/\$/  [$l]/" || true
  done | awk '{k=tolower($0); sub(/ *\[[a-z]+\]$/,"",k); gsub(/[^a-z0-9]+/," ",k); if(!(k in s)){s[k]=1;print}}'
  echo; echo "## Lens receipts"
  for l in "${LENSES[@]}"; do
    echo "- $OUT/lens-$l.md sha256 $(sha256sum "$OUT/lens-$l.md" 2>/dev/null | cut -d' ' -f1)"
    sed -n '1,6p' "$OUT/lens-$l.md.verdict" 2>/dev/null | sed 's/^/    sidecar: /' || true
  done
  [ -n "$CI" ] && echo "- CI log $OUT/ci.log: $(tail -1 "$OUT/ci.log")"
  worst=PASS
  for v in "${VERD[@]}"; do
    case "${v#*: }" in
      FAIL) worst=FAIL;;
      NONE*) [ "$worst" = FAIL ] || worst=NONE;;
      PROVISIONAL) case "$worst" in FAIL|NONE) ;; *) worst=PROVISIONAL;; esac;;
      "PASS WITH NOTES") [ "$worst" = PASS ] && worst="PASS WITH NOTES";;
    esac
  done
  # Anything else that stopped the round overrides a passing verdict.
  case "$RC" in 0|3|5) ;; *) worst=FAIL;; esac
  echo; echo "VERDICT: $worst"
} > "$OUT/receipt.md"
echo "$OUT/receipt.md"
exit "$RC"
