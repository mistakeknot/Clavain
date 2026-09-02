#!/usr/bin/env bash
# check-plugin-cache.sh — does every installed plugin's cache directory actually exist?
#
# WHY THIS EXISTS
#
# On 2026-09-01 ~/.claude/plugins/cache/interagency-marketplace/clavain/ held
# four symlinks and no directory: 0.6.300 -> 0.6.302 and 0.6.302 -> 0.6.300
# (and the same pair for 0.6.296/0.6.297, dated Aug 14). installed_plugins.json
# pointed installPath at 0.6.302. Every hooks.json command is
# ${CLAUDE_PLUGIN_ROOT}/hooks/<name>.sh, so every Clavain hook failed to START
# in every new session, with no error anywhere a person would look. The doctor's
# cache check iterated a hardcoded list of seven companion plugins and never
# looked at clavain itself (bead mk-i3u8).
#
# This walks the REGISTRY, not the cache directory: the registry is what Claude
# Code resolves ${CLAUDE_PLUGIN_ROOT} from, so a plugin missing from it is a
# different problem (see modpack-associate.sh) and a directory the registry does
# not point at is irrelevant however healthy it looks.
#
# THE THREE VERDICTS, WHICH MUST NOT COLLAPSE
#
#   PASS  installPath is a real directory holding .claude-plugin/plugin.json at
#         the registered version
#   WARN  it resolves, but has no manifest (lsp-only plugins), or the manifest
#         version disagrees with the registry, or the tree is suspiciously small
#   FAIL  installPath does not resolve to a directory at all (missing, dangling
#         symlink, symlink LOOP) — nothing can execute from it
#
# Exit: 0 = no FAIL (WARNs allowed), 1 = at least one FAIL, 2 = could not
# evaluate (registry unreadable, jq missing). 2 is never 0: a check that could
# not run must not read as clean.
#
# Usage: check-plugin-cache.sh [--registry <installed_plugins.json>] [--json]

set -uo pipefail

REGISTRY="${CLAUDE_PLUGINS_REGISTRY:-$HOME/.claude/plugins/installed_plugins.json}"
JSON=0
MIN_FILES="${CLAVAIN_PLUGIN_CACHE_MIN_FILES:-3}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --registry) REGISTRY="${2:-}"; shift 2 || shift ;;
        --registry=*) REGISTRY="${1#--registry=}"; shift ;;
        --json) JSON=1; shift ;;
        -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v jq >/dev/null 2>&1 || { echo "plugin cache: could not evaluate (jq not installed)" >&2; exit 2; }
[[ -r "$REGISTRY" ]] || { echo "plugin cache: could not evaluate (registry not readable: $REGISTRY)" >&2; exit 2; }

# One line per registry entry: key<TAB>version<TAB>installPath. Entries are
# arrays per key (one per scope); each element is checked on its own.
ROWS="$(jq -r '
    (.plugins // {}) | to_entries[]
    | .key as $k
    | (if (.value|type) == "array" then .value else [.value] end)[]
    | [$k, (.version // ""), (.installPath // "")] | @tsv
' "$REGISTRY" 2>/dev/null)" || { echo "plugin cache: could not evaluate (registry is not the expected shape)" >&2; exit 2; }

RESULTS=()
FAILS=0; WARNS=0; PASSES=0

resolve_dir() {
    # Prints the resolved directory, or nothing. A symlink loop makes -d false
    # and readlink -f fail; both land in the empty branch, which is the point.
    local p="$1"
    [[ -n "$p" ]] || return 1
    [[ -d "$p" ]] || return 1
    ( cd "$p" 2>/dev/null && pwd -P )
}

while IFS=$'\t' read -r key version path; do
    [[ -n "$key" ]] || continue
    verdict="PASS"; reason="ok"
    if [[ -z "$path" ]]; then
        verdict="FAIL"; reason="registry entry has no installPath"
    elif ! real="$(resolve_dir "$path")"; then
        if [[ -L "$path" ]]; then
            if [[ -e "$path" ]]; then
                verdict="FAIL"; reason="installPath is a symlink to something that is not a directory"
            else
                # -L true, -e false: dangling — or a loop, which -e also reports
                # as nonexistent. Say which: a loop is the 2026-09-01 shape.
                target="$(readlink "$path" 2>/dev/null || true)"
                if [[ -n "$target" && -L "$(dirname "$path")/$target" ]]; then
                    verdict="FAIL"; reason="installPath is a symlink LOOP ($(basename "$path") -> $target -> ...); no directory exists; every hook under it fails to start"
                else
                    verdict="FAIL"; reason="installPath is a dangling symlink (-> ${target:-?})"
                fi
            fi
        else
            verdict="FAIL"; reason="installPath does not exist"
        fi
    else
        manifest="$real/.claude-plugin/plugin.json"
        nfiles="$(find "$real" -type f -not -path '*/.in_use/*' 2>/dev/null | wc -l | tr -d ' ')"
        if [[ ! -f "$manifest" ]]; then
            # A directory that resolves can run hooks, so this is not a FAIL.
            # LSP-only plugins from the official marketplace ship LICENSE +
            # README and no manifest at all; say so rather than cry wolf.
            verdict="WARN"; reason="no .claude-plugin/plugin.json under installPath (normal for lsp-only plugins)"
        else
            mver="$(jq -r '.version // ""' "$manifest" 2>/dev/null || true)"
            # Official-marketplace manifests carry no version and the registry
            # records a commit sha instead; only compare when both sides speak.
            if [[ -n "$mver" && -n "$version" && "$mver" != "$version" ]]; then
                verdict="WARN"; reason="manifest version $mver != registry version $version"
            elif [[ "$nfiles" -lt "$MIN_FILES" ]]; then
                verdict="WARN"; reason="only $nfiles file(s) under installPath — likely an empty cache, reinstall"
            fi
        fi
    fi
    case "$verdict" in
        PASS) PASSES=$((PASSES+1)) ;;
        WARN) WARNS=$((WARNS+1)) ;;
        FAIL) FAILS=$((FAILS+1)) ;;
    esac
    RESULTS+=("$(jq -cn --arg k "$key" --arg v "$version" --arg p "$path" --arg verdict "$verdict" --arg r "$reason" \
        '{plugin:$k, version:$v, installPath:$p, verdict:$verdict, reason:$r}')")
done <<<"$ROWS"

# Installer leftovers are reported, never counted: they are evidence about the
# updater, not about any registered plugin.
CACHE_ROOT="$(dirname "$REGISTRY")/cache"
LEFTOVERS="$(find "$CACHE_ROOT" -maxdepth 1 -type d -name 'temp_git_*' 2>/dev/null | wc -l | tr -d ' ')"

if [[ "$JSON" -eq 1 ]]; then
    printf '%s\n' "${RESULTS[@]+"${RESULTS[@]}"}" | jq -cs --argjson leftovers "$LEFTOVERS" \
        --argjson fails "$FAILS" --argjson warns "$WARNS" --argjson passes "$PASSES" \
        '{schema_version:"clavain.plugin-cache-check/v1", ok:($fails==0), fails:$fails, warns:$warns, passes:$passes,
          temp_git_leftovers:$leftovers, plugins:.}'
else
    for r in "${RESULTS[@]+"${RESULTS[@]}"}"; do
        jq -r '"  \(.plugin) \(.version): \(.verdict)" + (if .verdict=="PASS" then "" else " (" + .reason + ")" end)' <<<"$r"
    done
    if [[ "$FAILS" -gt 0 ]]; then
        echo "plugin cache: FAIL ($FAILS unusable, $WARNS warn, $PASSES ok; $LEFTOVERS temp_git_* leftover dir(s))"
        echo "  Fix: remove the offending symlinks/dirs, then: claude plugin update <plugin>@<marketplace>"
    elif [[ "$WARNS" -gt 0 ]]; then
        echo "plugin cache: WARN ($WARNS warn, $PASSES ok; $LEFTOVERS temp_git_* leftover dir(s))"
    else
        echo "plugin cache: PASS ($PASSES plugins; $LEFTOVERS temp_git_* leftover dir(s))"
    fi
fi

[[ "$FAILS" -gt 0 ]] && exit 1
exit 0
