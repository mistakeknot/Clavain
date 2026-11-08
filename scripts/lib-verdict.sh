#!/usr/bin/env bash
# Shared review-verdict word classifier (mk-0qjva, mk-4c909, mk-8m912).
#
# Two readers used to keep their own word lists: dispatch.sh (_extract_verdict,
# the .verdict sidecar) and lib-review-receipt.sh (the receipt). They drifted:
# PASS-WITH-NOTES and APPROVE were a pass in neither, but the receipt recorded
# an unlisted word as a failed dispatch and dispatch recorded it as an
# unrecognised verdict. Both now classify the verdict word here, so the same
# word can never mean two things.
#
# Sourced, not executed. Defines only functions; safe to source twice.
#
#   verdict_word_class WORD
#       prints one of:
#         PASS             PASS, optionally followed by one period
#         PASS_WITH_NOTES  PASS WITH NOTES; the words may be joined by spaces,
#                          hyphens or underscores (PASS-WITH-NOTES, pass_with_notes)
#         FAIL             FAIL or BLOCK (BLOCK is an alias of FAIL), alone or
#                          followed by an explanation after a separator
#         UNKNOWN          anything else, including APPROVE, CLEAN-ish prose,
#                          and PASS followed by any explanation
#       Never fails: an unusable word is UNKNOWN, never a pass.
#
#   verdict_label_word LINE
#       Prints the word after a "VERDICT:" label on LINE (the whole line may be
#       wrapped in ** or __ bold) and returns 0; returns 1 when LINE is not a
#       verdict-label line.
#
# Design choice: only an exact PASS-class word is a pass. Explanatory text after
# PASS could contradict it in wording we cannot enumerate, so it stays UNKNOWN.
# A FAIL-class word keeps its explanation because the result is a block either way.

verdict_word_class() {
  local w="${1-}" up
  # Trim, then upper-case. A single trailing period is allowed.
  w="${w#"${w%%[![:space:]]*}"}"
  w="${w%"${w##*[![:space:]]}"}"
  up="${w^^}"
  local pass_re='^PASS\.?$'
  local notes_re='^PASS[[:space:]_-]+WITH[[:space:]_-]+NOTES\.?$'
  local fail_re='^(FAIL|BLOCK)($|[[:space:]:;.,(].*)'
  if [[ "$up" =~ $pass_re ]]; then
    echo PASS
  elif [[ "$up" =~ $notes_re ]]; then
    echo PASS_WITH_NOTES
  elif [[ "$up" =~ $fail_re ]]; then
    echo FAIL
  else
    echo UNKNOWN
  fi
}

verdict_label_word() {
  local line="${1-}"
  # shellcheck disable=SC2016  # the backtick is a literal in the regex
  local re='^(\*\*|__)?[Vv][Ee][Rr][Dd][Ii][Cc][Tt][[:space:]]*:(\*\*|__)?[[:space:]]*(([^[:space:]*_`]|[^[:space:]*_`].*[^[:space:]*_`]))[[:space:]]*(\*\*|__)?[[:space:]]*$'
  [[ "$line" =~ $re ]] || return 1
  printf '%s\n' "${BASH_REMATCH[3]}"
}

# Role verdict-block instruction (mk-z770, parser contract sections 3 and 4.3).
#   verdict_role_suffix ROLE RELATIONSHIP PROMPT
# Prints the instruction to append to a resolved role's prompt, or nothing when
# none applies:
#   - cross-lab-review has its own final-line VERDICT contract; a trailing block
#     would break it, so it gets nothing.
#   - a prompt that already carries the interflux findings contract (a Findings
#     Index or its Verdict line) wins: a second declared value would make a
#     compliant file contradict itself.
#   - review roles (plan-review, validation, or any dispatch with a validator
#     relationship) use the review vocabulary; every REVIEW value is read as
#     STATUS: warn, never pass, so this adds no new approval path.
#   - other roles use the completion vocabulary (pass = completed as asked,
#     warn = completed with caveats, error = could not complete).
# The checker and the repair dispatch from the same contract wait on mk-yjki.
verdict_role_suffix() {
  local role="${1-}" rel="${2-}" prompt="${3-}"
  [[ -n "$role" && "$role" != cross-lab-review ]] || return 0
  if grep -qE '^###? *Findings Index|^Verdict: (safe|needs-changes|risky|error)$' <<<"$prompt"; then
    return 0
  fi
  if [[ "$role" == plan-review || "$role" == validation || -n "$rel" ]]; then
    cat <<'SUFFIX'

When you finish, end your output with exactly this block as the last lines,
replacing the REVIEW value with one of approve, approve-with-changes, revise or
reject. Keep STATUS: warn. Your review is read by a person, not as an automatic
pass:

--- VERDICT ---
STATUS: warn
REVIEW: approve
---
SUFFIX
  else
    cat <<'SUFFIX'

When you finish, end your output with exactly this block as the last lines,
using STATUS: pass if you completed the task as asked, STATUS: warn if you
completed it with caveats the caller must read, or STATUS: error if you could
not complete it:

--- VERDICT ---
STATUS: pass
---
SUFFIX
  fi
}
