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

# Discover the interflux companion plugin root directory.
# Checks INTERFLUX_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interflux_plugin() {
    if [[ -n "${INTERFLUX_ROOT:-}" ]]; then
        echo "$INTERFLUX_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interflux/*/.claude-plugin/plugin.json' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # plugin.json is at <root>/.claude-plugin/plugin.json, so strip two levels
        echo "$(dirname "$(dirname "$f")")"
        return 0
    fi
    echo ""
}

# Discover the interpath companion plugin root directory.
# Checks INTERPATH_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interpath_plugin() {
    if [[ -n "${INTERPATH_ROOT:-}" ]]; then
        echo "$INTERPATH_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interpath/*/scripts/interpath.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # interpath.sh is at <root>/scripts/interpath.sh, so strip two levels
        echo "$(dirname "$(dirname "$f")")"
        return 0
    fi
    echo ""
}

# Discover the interwatch companion plugin root directory.
# Checks INTERWATCH_ROOT env var first, then searches the plugin cache.
# Output: plugin root path to stdout, or empty string if not found.
_discover_interwatch_plugin() {
    if [[ -n "${INTERWATCH_ROOT:-}" ]]; then
        echo "$INTERWATCH_ROOT"
        return 0
    fi
    local f
    f=$(find "${HOME}/.claude/plugins/cache" -maxdepth 5 \
        -path '*/interwatch/*/scripts/interwatch.sh' 2>/dev/null | sort -V | tail -1)
    if [[ -n "$f" ]]; then
        # interwatch.sh is at <root>/scripts/interwatch.sh, so strip two levels
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
