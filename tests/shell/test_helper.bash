#!/usr/bin/env bash
# Shared test helper for Clavain bats tests

# Resolve directories relative to this file
HOOKS_DIR="$BATS_TEST_DIRNAME/../../hooks"
FIXTURES_DIR="$BATS_TEST_DIRNAME/../fixtures"
export CLAUDE_PLUGIN_ROOT="$BATS_TEST_DIRNAME/../.."

# Load bats-support and bats-assert from npm global modules
# Try common npm global paths
NPM_GLOBAL=""
for candidate in /usr/lib/node_modules /usr/local/lib/node_modules; do
    if [[ -d "$candidate/bats-support" ]]; then
        NPM_GLOBAL="$candidate"
        break
    fi
done

if [[ -n "$NPM_GLOBAL" ]]; then
    load "$NPM_GLOBAL/bats-support/load"
    load "$NPM_GLOBAL/bats-assert/load"
fi

# Stub network commands to prevent real network calls in tests
stub_network() {
    curl() { return 1; }
    wget() { return 1; }
    export -f curl wget
}
