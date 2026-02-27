#!/usr/bin/env bash
# Shared test helper for Clavain bats tests

# Resolve directories relative to this file
HOOKS_DIR="$BATS_TEST_DIRNAME/../../hooks"
FIXTURES_DIR="$BATS_TEST_DIRNAME/../fixtures"
export CLAUDE_PLUGIN_ROOT="$BATS_TEST_DIRNAME/../.."

# Load bats-support and bats-assert
# Try local tests/node_modules first, then npm global paths
BATS_LIBS=""
for candidate in "$BATS_TEST_DIRNAME/../node_modules" /usr/lib/node_modules /usr/local/lib/node_modules; do
    if [[ -d "$candidate/bats-support" ]]; then
        BATS_LIBS="$candidate"
        break
    fi
done

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
