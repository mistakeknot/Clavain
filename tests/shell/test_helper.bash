#!/usr/bin/env bash
# Shared test helper for Clavain bats tests

# Resolve directories relative to this file
HOOKS_DIR="$BATS_TEST_DIRNAME/../../hooks"
FIXTURES_DIR="$BATS_TEST_DIRNAME/../fixtures"
export CLAUDE_PLUGIN_ROOT="$BATS_TEST_DIRNAME/../.."

# Load bats-support and bats-assert.
#
# CLAVAIN_BATS_LIBS is an explicit selection and therefore a contract: if it is
# set and wrong, fail loudly (Sylveste-psey). The scheduled lane picks its tools
# deliberately, and a harness that silently fell back to a different root would
# not be testing what the lane chose -- the same class of defect as a /tmp entry
# on PATH shadowing a selected binary.
#
# Unset, the ordinary autodetection below applies, and finding nothing is not an
# error: plenty of local runs have no helpers installed. Note that the last
# candidate is `npm root -g`; on a machine whose npm prefix is not one of the
# hard-coded paths, that is the one that resolves.
BATS_LIBS=""
if [[ -n "${CLAVAIN_BATS_LIBS:-}" ]]; then
    if [[ -r "$CLAVAIN_BATS_LIBS/bats-support/load.bash" \
       && -r "$CLAVAIN_BATS_LIBS/bats-assert/load.bash" ]]; then
        BATS_LIBS="$CLAVAIN_BATS_LIBS"
    else
        printf 'test_helper: CLAVAIN_BATS_LIBS=%s must contain readable %s and %s; refusing to fall back to autodetection\n' \
            "$CLAVAIN_BATS_LIBS" "bats-support/load.bash" "bats-assert/load.bash" >&2
        return 1 2>/dev/null || exit 1
    fi
else
    # Try local tests/node_modules first, then npm global paths
    # (Linux, macOS Homebrew, and the active npm prefix)
    for candidate in "$BATS_TEST_DIRNAME/../node_modules" /usr/lib/node_modules /usr/local/lib/node_modules \
                     /opt/homebrew/lib/node_modules "$(npm root -g 2>/dev/null)"; do
        if [[ -d "$candidate/bats-support" ]]; then
            BATS_LIBS="$candidate"
            break
        fi
    done
fi

if [[ -n "$BATS_LIBS" ]]; then
    load "$BATS_LIBS/bats-support/load"
    load "$BATS_LIBS/bats-assert/load"
fi

# Stub network commands to prevent real network calls in tests
stub_network() {
    curl() { return 1; }
    wget() { return 1; }
    export -f curl wget
}
