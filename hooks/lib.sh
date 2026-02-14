#!/usr/bin/env bash
# Shared utilities for Clavain hook scripts

# Discover the interphase companion plugin root directory.
# Checks INTERPHASE_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_beads_plugin() {
    if [[ -n "${INTERPHASE_ROOT:-}" ]]; then
        echo "$INTERPHASE_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interphase/*/hooks/lib-gates.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # lib-gates.sh is at <root>/hooks/lib-gates.sh, so strip two levels
        echo "$(dirname "$(dirname "$f")")"
        return 0
    fi
    echo ""
}

# Escape string for JSON embedding using bash parameter substitution.
# Each ${s//old/new} is a single C-level pass — fast and reliable.
escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\b'/\\b}"
    s="${s//$'\f'/\\f}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    local i ch esc
    for i in {1..31}; do
        case "$i" in 8|9|10|12|13) continue ;;  # already handled as \b, \t, \n, \f, \r
        esac
        printf -v ch "\\$(printf '%03o' "$i")"
        printf -v esc '\\u%04x' "$i"
        s="${s//$ch/$esc}"
    done
    printf '%s' "$s"
}
