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


# The reviewer's closing line as the sidecar reads it (mk-0qjva).
#   verdict_last_line FILE
# Prints the last non-blank line of FILE with list/quote/heading markers and
# balanced bold or code wrappers removed, or nothing when that line sits inside
# an unclosed code fence (quoted example text, not the ruling).
verdict_last_line() {
  local output_file="${1-}" last_line
  # A final line inside an unclosed code fence is quoted example
  # text, not the agent's ruling. Track fence char and opening length: a
  # closer must repeat the char, be at least as long, and carry no
  # trailing text.
  last_line="$(awk '
      { sub(/\r$/, "") }
      {
          line = $0
          # tolerate the same blockquote / list-item prefixes the
          # sed below strips, so a prefixed fence is still a fence
          if (match(line, /^ ? ? ?(>[ ]*|[-+*][ ]+|•[ ]+)*(```+|~~~+)/)) {
              rest = substr(line, RSTART + RLENGTH)
              run = substr(line, RSTART, RLENGTH)
              match(run, /(```+|~~~+)$/)
              run = substr(run, RSTART)
              ch = substr(run, 1, 1)
              if (open == "") {
                  # a backtick fence info string may not contain a
                  # backtick; such a line is not an opener
                  if (!(ch == "`" && index(rest, "`"))) { open = ch; olen = length(run) }
              }
              else if (ch == open && length(run) >= olen && rest ~ /^[ \t]*$/) { open = "" }
          }
      }
      $0 ~ /[^[:space:]]/ { last = $0 }
      END { if (open == "") print last }
  ' "$output_file" 2>/dev/null)" || last_line=""
  # Strip only balanced outer decoration: list/quote/heading markers,
  # then matching ** / __ / ` wrappers (also around just the label,
  # as in **Verdict:** PASS). Unbalanced or interior asterisks stay,
  # so "CLEAN*" and "P*ASS" never become a pass.
  last_line="$(sed -E 's/\r$//; s/^[[:space:]]*([>#+•-]+[[:space:]]*)+//; s/^[[:space:]]*\*[[:space:]]+//; s/[[:space:]]+$//' <<< "$last_line")"
  local _prev=""
  while [[ "$last_line" != "$_prev" ]]; do
      _prev="$last_line"
      last_line="$(sed -E 's/^(\*\*|__)([A-Za-z]+[[:space:]]*:)\1[[:space:]]*(\*\*|__)([^*_]*)\3$/\2 \4/; s/^(\*\*|__)([A-Za-z]+)\1[[:space:]]*:[[:space:]]*(\*\*|__)([^*_]*)\3$/\2: \4/; s/^\*\*([^*]*)\*\*$/\1/; s/^__(.*)__$/\1/; s/^`(.*)`$/\1/; s/^(\*\*|__|`)([A-Za-z]+[[:space:]]*:)\1([[:space:]]*)/\2 /' <<< "$last_line")"
      last_line="${last_line%"${last_line##*[![:space:]]}"}"
  done
  printf '%s\n' "$last_line"
}

# The class of the closing verdict line, read leniently as the sidecar does
# (verdict_last_line): PASS, PASS_WITH_NOTES, FAIL, UNKNOWN, or NONE when the
# closing line is not a "VERDICT:" line.
#   verdict_final_class FILE
verdict_final_class() {
  local line word
  line="$(verdict_last_line "${1-}")"
  if word="$(verdict_label_word "$line")"; then
    verdict_word_class "$word"
  else
    echo NONE
  fi
}

# The verdict word the review receipt reads: the strict selection. The ruling
# must be the last non-blank line, start at column 0 and follow a blank line (or
# begin the file); the file must hold no NUL byte, code fence or HTML comment
# delimiter anywhere. Prints the raw word, or prints nothing and returns 1.
# The receipt and the cross-lab sidecar both call this, so they cannot choose
# different lines (mk-0qjva).
#   verdict_strict_word FILE
verdict_strict_word() {
  local out="${1-}" last rc
  [[ -f "$out" ]] || return 1
  # Continue only on grep status 1 (no delimiter found); a match or any scan
  # error rejects. NUL bytes are rejected first: shell capture would drop them.
  LC_ALL=C tr -d '\000' <"$out" | cmp -s - "$out"
  [[ "${PIPESTATUS[0]}" -eq 0 && "${PIPESTATUS[1]}" -eq 0 ]] || return 1
  LC_ALL=C grep -qE '```|~~~|<!--|-->' "$out"; rc=$?
  [[ $rc -eq 1 ]] || return 1
  last="$(awk '
    { sub(/\r$/, "") }
    $0 ~ /[^[:space:]]/ { last = $0; lastok = (blank || NR == 1); blank = 0; next }
    { blank = 1 }
    END { if (lastok) print last }' "$out")" || return 1
  verdict_label_word "$last"
}

# Receipt-equivalent class of FILE: PASS, PASS_WITH_NOTES, FAIL, UNKNOWN, or
# NONE when the receipt would find no usable VERDICT line (and so write nothing).
#   verdict_strict_class FILE
verdict_strict_class() {
  local w
  if w="$(verdict_strict_word "${1-}")"; then
    verdict_word_class "$w"
  else
    echo NONE
  fi
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
