#!/usr/bin/env bash
# lib-ship-class.sh — one definition of "ship-class", sourced by every caller.
#
# Ship-class surfaces execute or gate platform code: plugin manifests, MCP
# configs, hook scripts, interlock/authorization/capability files, signing-key
# paths, shell-out paths. An unreviewed change to one of them is an RCE /
# supply-chain risk, so interflux makes fd-safety a MANDATORY reviewer for any
# diff touching them (interflux SKILL.md Step 1.2a).
#
# WHY THIS FILE EXISTS. The regex lived inline in commands/quality-gates.md
# Phase 2, where the mandatory-reviewer guard reads it. Phase 1's small-change
# shortcut — one fd-quality agent, "Skip Phases 2-3" — ran BEFORE that guard and
# never consulted it, so a single-file diff under 20 lines bypassed mandatory
# safety review entirely. An 8-line edit to a hook script reproduced it. Two
# callers need the same answer, and a second inline copy would drift; this is
# the one copy.
#
# Sourced, not executed. Callers must have `set -euo pipefail` if they want it.

# Keep this identical to what the Phase 2 guard enforced. Widening it is safe;
# narrowing it removes a surface from mandatory review and must not happen by
# accident — tests/shell/ship_class_shortcut.bats pins each alternative.
CLAVAIN_SHIP_CLASS_RE='(^|/)plugin\.json$|(^|/)mcp-[^/]*\.(json|ya?ml)$|(^|/)mcp-server\.|(^|/)hooks/[^/]*\.(sh|py|ts|js)$|(^|/)hooks\.json$|(^|/)(interlock|authorization|capability)[^/]*\.(json|ya?ml)$|(^|/)\.clavain/keys/|shell-exec'

# ship_class_match <<< "<newline-separated paths>"
# Prints the matching paths; exit 0 when at least one matched, 1 when none did.
ship_class_match() {
    grep -E "$CLAVAIN_SHIP_CLASS_RE"
}

# is_ship_class_paths <path>...
# Exit 0 when ANY argument is a ship-class surface.
is_ship_class_paths() {
    [[ $# -gt 0 ]] || return 1
    printf '%s\n' "$@" | grep -Eq "$CLAVAIN_SHIP_CLASS_RE"
}

# review_path_decision  (paths on STDIN, one per line)
# Prints the decision a caller must obey, on stdout, because the callers are
# markdown fences executed one per shell: an exported variable does not survive
# to the next fence, but printed output reaches the reader that acts on it.
# Reads stdin rather than argv so callers need no mapfile (absent on bash 3.2,
# which is what /bin/bash is on macOS).
review_path_decision() {
    local paths matched
    paths="$(cat)"
    matched="$(printf '%s\n' "$paths" | grep -E "$CLAVAIN_SHIP_CLASS_RE" || true)"
    if [[ -n "$matched" ]]; then
        echo "REVIEW_PATH=full"
        echo "REVIEW_PATH_REASON=ship-class diff (plugin/MCP/hooks/interlock/keys/shell-out); fd-safety is mandatory, the small-change shortcut is NOT available"
        printf '%s\n' "$matched" | sed 's/^/  ship-class: /'
        return 0
    fi
    echo "REVIEW_PATH=shortcut-eligible"
    echo "REVIEW_PATH_REASON=no ship-class surface in this diff"
}
