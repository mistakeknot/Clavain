#!/usr/bin/env bash
# UI review standards for --role cross-lab-review (bead mk-kvwc9).
# When the PR diff touches user-facing files, dispatch.sh appends the ui-craft
# review standards to the review brief. The brief's own verdict format and
# VERDICT line stay in force: the section is inserted before the format
# instructions, and it tells the reviewer so. A missing standards file never
# blocks the review; it prints a notice on stderr and puts one line in the brief.
#
# Where the standards come from (first hit wins):
#   1. CLAVAIN_UI_REVIEW_STANDARDS  the review-standards.md file itself
#   2. CLAVAIN_UI_CRAFT_DIR         a ui-craft skill directory
#   3. the installed skill          ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/ui-craft
# CLAVAIN_UI_REVIEW=off turns the feature off.
#
# Two companion excerpts are embedded when their files sit in the same skill
# directory (<skill>/references/motion-and-performance.md section 3 and
# <skill>/SKILL.md "Never ship"), because standards 4 and 12 point at them.

_UI_EXT_RE='\.(tsx|jsx|vue|svelte|css|scss|sass|less|html|htm|astro|mdx|xaml)$'
_UI_DIR_RE='(^|/)(components|ui|styles|views|screens|pages)/'
_UI_TEST_RE='(\.(test|spec|story|stories)\.[^/]+$|(^|/)(__tests__|__snapshots__|__fixtures__|fixtures|stories|\.storybook|tests?|e2e|node_modules|vendor|vendored|dist|build)/)'
_UI_TOKEN_RE='(^|/)(tailwind\.config\.[^/]+|(theme|tokens)\.(ts|js|mjs|cjs|json|css))$'

# True when $1 is a user-facing file that is not a test, story, fixture or
# vendored/built file.
_ui_review_is_ui_file() {
  local p="$1"
  [[ "$p" =~ $_UI_TEST_RE ]] && return 1
  [[ "$p" =~ $_UI_EXT_RE ]] && return 0
  [[ "$p" =~ $_UI_TOKEN_RE ]] && return 0
  # Script and native-UI files count only under a UI directory.
  case "$p" in
    *.js|*.ts|*.mjs) [[ "$p" =~ $_UI_DIR_RE ]] && return 0 ;;
    *.swift) [[ "$p" =~ (^|/)(View|Views|UI)/ ]] && return 0 ;;
    *.go) [[ "$p" =~ (^|/)(tui|ui|views)/ ]] && return 0 ;;
    *.rs) [[ "$p" =~ (^|/)ui/ ]] && return 0 ;;
    *.svg) [[ "$p" =~ (^|/)(assets|dist|public|static)/ ]] || return 0 ;;
  esac
  return 1
}

# Prints the path of review-standards.md (it may not exist) on stdout.
_ui_review_standards_path() {
  if [[ -n "${CLAVAIN_UI_REVIEW_STANDARDS:-}" ]]; then
    printf '%s\n' "$CLAVAIN_UI_REVIEW_STANDARDS"
  elif [[ -n "${CLAVAIN_UI_CRAFT_DIR:-}" ]]; then
    printf '%s\n' "${CLAVAIN_UI_CRAFT_DIR%/}/references/review-standards.md"
  else
    printf '%s\n' "${CLAUDE_CONFIG_DIR:-${HOME:-/nonexistent}/.claude}/skills/ui-craft/references/review-standards.md"
  fi
}

# Extracts the markdown section that starts at the heading line matching $2
# (an awk regex) and ends before the next heading of the same or higher level.
_ui_review_extract_section() {
  awk -v pat="$2" '
    function level(s,   n) { n = 0; while (substr(s, n + 1, 1) == "#") n++; return n }
    on && /^#+ / && level($0) <= lvl { exit }
    !on && $0 ~ pat { on = 1; lvl = level($0) }
    on { print }
  ' "$1"
}

# _ui_review_section: prints the brief section for the changed paths in
# $RR_CHANGED_PATHS_JSON (set by _review_receipt_prepare). Prints nothing when
# the feature is off or no changed path is a UI file. A missing or empty
# standards file prints a one-line notice instead of the rubric, plus a stderr
# notice. Always returns 0.
_ui_review_section() {
  [[ "${CLAVAIN_UI_REVIEW:-on}" != off ]] || return 0
  [[ -n "${RR_CHANGED_PATHS_JSON:-}" ]] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  local paths total p odd
  local -a ui=()
  # Path names are untrusted text that ends up in the brief. A name with a
  # control character (a newline, a carriage return, an escape) could start a
  # new line of instructions there, so such names are neither checked nor
  # listed; only their count is reported. Listed names are capped at 200 chars.
  paths="$(jq -r '.paths[]? | select(type == "string" and (test("[\u0001-\u001f\u007f\u0085\u2028\u2029]") | not))' <<< "$RR_CHANGED_PATHS_JSON" 2>/dev/null)" || return 0
  odd="$(jq -r '[.paths[]? | select(type != "string" or test("[\u0001-\u001f\u007f\u0085\u2028\u2029]"))] | length' <<< "$RR_CHANGED_PATHS_JSON" 2>/dev/null)" || odd=0
  [[ "$odd" =~ ^[0-9]+$ ]] || odd=0
  total="$(jq -r '.total // 0' <<< "$RR_CHANGED_PATHS_JSON" 2>/dev/null)" || total=0
  while IFS= read -r p; do
    [[ -n "$p" ]] && _ui_review_is_ui_file "$p" && ui+=("$p")
  done <<< "$paths"
  [[ ${#ui[@]} -gt 0 ]] || return 0

  local std skill_dir
  std="$(_ui_review_standards_path)"
  if [[ ! -r "$std" || ! -s "$std" ]]; then
    echo "Notice: this PR touches UI files but the ui-craft review standards were not found at $std; reviewing without them (set CLAVAIN_UI_REVIEW_STANDARDS or CLAVAIN_UI_CRAFT_DIR)." >&2
    printf '\nUI lens: this change touches user-facing files, but the ui-craft review standards file was not available to dispatch, so this review ran without them. Say in your findings that the UI standards were not applied.\n'
    return 0
  fi
  skill_dir="$(dirname "$(dirname "$std")")"

  printf '\nUI lens: this change touches user-facing files:\n'
  local i=0
  for p in "${ui[@]}"; do
    (( ++i > 40 )) && break
    printf -- '- %s\n' "${p:0:200}"
  done
  (( ${#ui[@]} > 40 )) && printf -- '- ... and %d more\n' "$(( ${#ui[@]} - 40 ))"
  if [[ "$total" =~ ^[0-9]+$ ]] && (( total > 200 )); then
    printf '(Only the first 200 of %s changed paths were checked for UI files.)\n' "$total"
  fi
  if (( odd > 0 )); then
    printf '(%d changed path(s) with control characters in the name were not checked or listed.)\n' "$odd"
  fi
  printf '%s\n' \
    'Apply the standards below in addition to your other checks. Report their findings' \
    "in this brief's own format and under its own verdict rule. The standards' own" \
    '"Block" and "Approve" close maps onto the packaged verdict: Block is FAIL, Approve is' \
    'PASS or PASS WITH NOTES. Do not write a second verdict. The brief'"'"'s VERDICT line,' \
    'given at the end of this brief, is the only verdict.' \
    '' '--- ui-craft review standards ---'
  cat "$std"
  printf '\n--- end ui-craft review standards ---\n'

  local motion="$skill_dir/references/motion-and-performance.md" skillmd="$skill_dir/SKILL.md" ex
  ex=""
  [[ -r "$motion" ]] && ex="$(_ui_review_extract_section "$motion" '^## 3\. Duration budgets')"
  if [[ -n "$ex" ]]; then
    printf '\n--- referenced by standard 4: motion-and-performance.md, section 3 ---\n%s\n--- end ---\n' "$ex"
  else
    printf '\n(Standard 4 refers to the duration budgets in motion-and-performance.md section 3; that file was not available to dispatch.)\n'
  fi
  ex=""
  [[ -r "$skillmd" ]] && ex="$(_ui_review_extract_section "$skillmd" '^## Never ship')"
  if [[ -n "$ex" ]]; then
    printf '\n--- referenced by standard 12: SKILL.md, "Never ship" checklist ---\n%s\n--- end ---\n' "$ex"
  else
    printf '\n(Standard 12 refers to the never-ship checklist in the ui-craft SKILL.md; that file was not available to dispatch.)\n'
  fi
  return 0
}
