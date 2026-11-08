#!/usr/bin/env bash
# phase-evidence.sh — observe-mode phase evidence hook (mk-4xzwm.1).
# Usage: phase-evidence.sh pre|post|stop. Records tool use in a per-session
# ledger and warns on missing evidence. Fails open: it exits 0 on every path
# (no python3, python crash or timeout, odd output) and prints only a
# systemMessage line the host cannot read as a block.
# CLAVAIN_PHASE_EVIDENCE_MODE=off disables it.
[[ "${CLAVAIN_PHASE_EVIDENCE_MODE:-observe}" == off ]] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0

event="${1:-post}"
payload=""
IFS= read -r -N 4194304 payload 2>/dev/null || true

# Bash calls matter only when the command could be a verifier; skip the
# python start-up for every other command. This prefilter is a superset of
# the precise check in phase-evidence.py.
if [[ "$event" == post && "$payload" =~ \"tool_name\"[[:space:]]*:[[:space:]]*\"Bash\" ]]; then
    verifier='(pytest|bats|shellcheck|ruff|mypy|tsc|eslint|golangci-lint|go[[:space:]]+(test|vet)|cargo|npm|pnpm|yarn|bun|make|py_compile|unittest|bash[[:space:]]+-n|git[[:space:]]+diff[[:space:]]+--check)'
    [[ "$payload" =~ $verifier ]] || exit 0
fi

guard=()
command -v timeout >/dev/null 2>&1 && guard=(timeout 4)
script="${BASH_SOURCE[0]%/*}/../scripts/phase-evidence.py"
out="$(printf '%s' "$payload" | "${guard[@]}" python3 "$script" hook "$event" 2>/dev/null)" || exit 0
if [[ "$out" == '{"systemMessage": "'* && "$out" != *$'\n'* && "$out" != *'"decision"'* ]]; then
    printf '%s\n' "$out"
fi
exit 0
