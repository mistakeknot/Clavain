#!/usr/bin/env bash
# phase-evidence.sh — observe-mode phase evidence hook (mk-4xzwm.1).
# Usage: phase-evidence.sh pre|post|stop. Records tool use in a per-session
# ledger and warns on missing evidence. Fails open: it exits 0 on every path
# (no python3, python crash or hang, incomplete stdin, odd output) and prints
# only a systemMessage line the host cannot read as a block.
# Deadline: the stdin read is bounded (2 s) and python is killed after 2 s by a
# watchdog written in bash, so the bound holds without the `timeout` command.
# CLAVAIN_PHASE_EVIDENCE_MODE=off disables it.
[[ "${CLAVAIN_PHASE_EVIDENCE_MODE:-observe}" == off ]] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0

event="${1:-post}"
payload=""
# A stream that never completes yields whatever arrived after 2 s (the JSON is
# then invalid and python records nothing).
IFS= read -r -N 4194304 -t 2 payload 2>/dev/null || true

# Bash calls matter only when the command could be a verifier; skip the
# python start-up for every other command. This prefilter is a superset of
# the precise check in phase-evidence.py. The payload is serialized JSON, so
# escaped whitespace (\t \n \r \f \u00xx) counts as a separator.
if [[ "$event" == post && "$payload" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"Bash\" ]]; then
    flat="${payload//\\[tnrf]/ }"
    flat="${flat//\\u00[0-9a-fA-F][0-9a-fA-F]/ }"
    verifier='(pytest|bats|shellcheck|ruff|mypy|tsc|eslint|golangci-lint|go[[:space:]]+(test|vet)|cargo|npm|pnpm|yarn|bun|make|py_compile|unittest|bash[[:space:]]+-n|git[[:space:]]+diff[[:space:]]+--check)'
    [[ "$flat" =~ $verifier ]] || exit 0
fi

script="${BASH_SOURCE[0]%/*}/../scripts/phase-evidence.py"
tmp="$(mktemp "${TMPDIR:-/tmp}/clavain-phase-evidence.XXXXXX" 2>/dev/null)" || exit 0
trap 'rm -f "$tmp"' EXIT
python3 "$script" hook "$event" <<<"$payload" >"$tmp" 2>/dev/null &
pid=$!
# Watchdog: `read -t` on a pipe nobody writes is a sleep that needs no command.
( read -rt 2 <> <(:); kill -9 "$pid" ) >/dev/null 2>&1 &
dog=$!
wait "$pid" 2>/dev/null
status=$?
kill "$dog" 2>/dev/null
wait "$dog" 2>/dev/null
[[ "$status" == 0 ]] || exit 0  # crashed, killed by the watchdog or failed: relay nothing
out="$(<"$tmp")" 2>/dev/null || exit 0

# Relay exactly one key, systemMessage, holding a JSON string. Anything else
# (extra keys such as hookSpecificOutput or decision, several lines) is dropped.
relay='^\{"systemMessage": "([^"\\]|\\.)*"\}$'
if [[ "$out" =~ $relay && "$out" != *$'\n'* ]]; then
    printf '%s\n' "$out"
fi
exit 0
