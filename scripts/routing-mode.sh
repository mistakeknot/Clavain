#!/usr/bin/env bash
# routing-mode.sh — toggle config/routing.yaml between economy and quality
# WITHOUT touching the doctrine-pinned phases.
#
# Sylveste-0pk: the old inline seds in commands/model-routing.md rewrote every
# `model:` line under subagents.phases, so a mode toggle silently reverted the
# routing-table v2 entries (brainstorm/strategized/planned → fable, with cheap
# categories as the dose guard; see commands/model-routing.md § Routing-table
# v2). Those three phases are never rewritten here. Everything else under
# phases: is, and so are the defaults.
set -euo pipefail

ROUTING_FILE="${ROUTING_FILE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/config/routing.yaml}"
PROTECTED_PHASES="${PROTECTED_PHASES:-brainstorm strategized planned}"

usage() { echo "usage: routing-mode.sh economy|quality|status" >&2; exit 2; }
[[ $# -eq 1 ]] || usage
mode="$1"

rewrite_defaults() {
  # $1 = model for defaults.model, $2..$5 = research review workflow synthesis
  local m="$1" r="$2" v="$3" w="$4" s="$5"
  sed -i.bak "/^subagents:/,/^dispatch:/{
  /^  defaults:/,/^  phases:/{
    s/^\(    model:\).*/\1 $m/
    /^    categories:/,/^  [a-z]/{
      s/^\(      research:\).*/\1 $r/
      s/^\(      review:\).*/\1 $v/
      s/^\(      workflow:\).*/\1 $w/
      s/^\(      synthesis:\).*/\1 $s/
    }
  }
}" "$ROUTING_FILE" && rm -f "$ROUTING_FILE.bak"
}

rewrite_phases() {
  # $1 = value for unprotected phase `model:` lines
  # $2 = value for unprotected phase category lines, or "keep" to leave them
  local phase_model="$1" cat_model="$2" tmp
  tmp="$(mktemp)"
  awk -v pm="$phase_model" -v cm="$cat_model" -v protected=" $PROTECTED_PHASES " '
    BEGIN { inphases = 0; phase = "" }
    /^  phases:/ { inphases = 1; print; next }
    inphases && /^[a-z]/ { inphases = 0 }          # left the subagents block
    inphases && /^  [a-z]/ && !/^  phases:/ { inphases = 0 }   # next top-level key under subagents
    inphases && /^    [a-z][a-z0-9_-]*:/ {
      phase = $1; sub(":", "", phase)
      print; next
    }
    inphases && index(protected, " " phase " ") == 0 && /^      model:/ {
      sub(/model:.*/, "model: " pm); print; next
    }
    inphases && index(protected, " " phase " ") == 0 && cm != "keep" && /^        [a-z][a-z0-9_-]*:/ {
      sub(/:.*/, ": " cm); print; next
    }
    { print }
  ' "$ROUTING_FILE" > "$tmp" && mv "$tmp" "$ROUTING_FILE"
}

case "$mode" in
  economy)
    rewrite_defaults sonnet haiku sonnet sonnet haiku
    rewrite_phases sonnet keep
    echo "routing: economy (doctrine phases untouched: $PROTECTED_PHASES)"
    ;;
  quality)
    rewrite_defaults opus opus opus opus opus
    rewrite_phases inherit inherit
    echo "routing: quality (doctrine phases untouched: $PROTECTED_PHASES)"
    ;;
  status)
    awk '/^subagents:/,/^dispatch:/' "$ROUTING_FILE" | grep -E '^(  defaults:|    model:|      (research|review|workflow|synthesis):|    [a-z][a-z0-9_-]*:$|      model:)' | sed 's/^/  /'
    ;;
  *) usage ;;
esac
