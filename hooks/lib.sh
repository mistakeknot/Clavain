#!/usr/bin/env bash
# Shared utilities for Clavain hook scripts

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
