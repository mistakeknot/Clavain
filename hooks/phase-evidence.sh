#!/usr/bin/env bash
# phase-evidence.sh — observe-mode phase evidence hook (mk-4xzwm.1).
# Usage: phase-evidence.sh pre|post|stop. Records tool use in a per-session
# ledger and warns on missing evidence. Fails open: it exits 0 on every path
# (no python3, python crash or hang, incomplete stdin, odd output) and prints
# only a systemMessage line the host cannot read as a block.
# Deadline: the stdin read (4 MiB cap), the prefilter and python are each killed
# after 2 s by a watchdog written in bash, so the bound holds without `timeout`.
# CLAVAIN_PHASE_EVIDENCE_MODE=off disables it.
[[ "${CLAVAIN_PHASE_EVIDENCE_MODE:-observe}" == off ]] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0

event="${1:-post}"

# bounded SECS CMD...: run CMD, killing it after SECS seconds. A bash watchdog
# keeps the bound without the `timeout` command; fd 3 becomes its stdin
# (a bash background job otherwise reads /dev/null); other redirections apply.
bounded() {
    local secs="$1" p d s; shift
    "$@" <&3 & p=$!
    ( read -rt "$secs" <> <(:); kill -9 "$p" ) >/dev/null 2>&1 &
    d=$!
    wait "$p" 2>/dev/null; s=$?
    kill "$d" 2>/dev/null
    wait "$d" 2>/dev/null
    return "$s"
}

# Read stdin through a byte-capped pipe under a 2 s limit (bash `read -N` skips
# NUL bytes and `read -t` does not bound a regular file or a sparse one). More
# than the cap, a timeout or a failed read means no evidence: stay silent.
LC_ALL=C
icap=4194304
inp="$(mktemp "${TMPDIR:-/tmp}/clavain-phase-evidence-in.XXXXXX" 2>/dev/null)" || exit 0
tmp=""
trap 'rm -f "$inp" "$tmp"' EXIT
bounded 2 head -c $((icap + 1)) 3<&0 >"$inp" 2>/dev/null || exit 0
isize="$(wc -c <"$inp" 2>/dev/null)" || exit 0
(( isize > 0 && isize <= icap )) || exit 0

# Bash calls matter only when the command could be a verifier; skip the
# python start-up for every other command. This prefilter is a superset of
# the precise check in phase-evidence.py. The payload is serialized JSON, so
# escaped whitespace (\t \n \r \f \u00xx) counts as a separator. One sed pass
# under the watchdog; a timeout or failure means silence.
if [[ "$event" == post ]]; then
    verifier='(pytest|bats|shellcheck|ruff|mypy|tsc|eslint|golangci-lint|go[[:space:]]+(test|vet)|cargo|npm|pnpm|yarn|bun|make|py_compile|unittest|bash[[:space:]]+-n|git[[:space:]]+diff[[:space:]]+--check)'
    pre="$(mktemp "${TMPDIR:-/tmp}/clavain-phase-evidence-pre.XXXXXX" 2>/dev/null)" || exit 0
    trap 'rm -f "$inp" "$tmp" "$pre"' EXIT
    bounded 2 sed -En ':a;$!{N;ba};/"tool_name"[[:space:]]*:[[:space:]]*"Bash"/!{s/.*/n/p;q};s/\\[tnrf]/ /g;s/\\u00[0-9a-fA-F]{2}/ /g;/'"$verifier"'/{s/.*/y/p;q}' "$inp" 3</dev/null >"$pre" 2>/dev/null || exit 0
    verdict="$(head -c 2 "$pre" 2>/dev/null)"
    [[ "$verdict" == n* || "$verdict" == y* ]] || exit 0
fi

script="${BASH_SOURCE[0]%/*}/../scripts/phase-evidence.py"
tmp="$(mktemp "${TMPDIR:-/tmp}/clavain-phase-evidence.XXXXXX" 2>/dev/null)" || exit 0
trap 'rm -f "$inp" "$tmp" "$pre"' EXIT
bounded 2 python3 "$script" hook "$event" 3<"$inp" >"$tmp" 2>/dev/null
status=$?
[[ "$status" == 0 ]] || exit 0  # crashed, killed by the watchdog or failed: relay nothing
# Read at most 16 KiB through a byte-capped pipe under a 1 s limit (bash `read -N`
# skips NUL bytes and `read -t` does nothing on a regular file). A message over the
# cap, a read that times out or fails, or one holding NUL bytes is no evidence.
LC_ALL=C
cap=16384
limit=(); command -v timeout >/dev/null 2>&1 && limit=(timeout 1)
size="$(set -o pipefail; "${limit[@]}" head -c $((cap + 1)) "$tmp" 2>/dev/null | wc -c)" || exit 0
(( size > 0 && size <= cap )) || exit 0  # empty, over the cap, or timed out (the pipe yields a short count)
plain="$(set -o pipefail; "${limit[@]}" head -c $((cap + 1)) "$tmp" 2>/dev/null | tr -d '\0' | wc -c)" || exit 0
(( plain == size )) || exit 0  # NUL bytes: not a pure message
out="$("${limit[@]}" head -c $((cap + 1)) "$tmp" 2>/dev/null)" || exit 0
out="${out%$'\n'}"

# Relay exactly one key, systemMessage, holding a valid JSON string (JSON string
# grammar: no raw control characters, only the JSON escapes). Anything else
# (extra keys such as hookSpecificOutput or decision, several lines, a bad
# escape) is dropped.
relay='^\{"systemMessage": "([^"\\[:cntrl:]]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"\}$'
if [[ "$out" =~ $relay && "$out" != *$'\n'* ]]; then
    printf '%s\n' "$out"
fi
exit 0
