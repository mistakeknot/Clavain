#!/usr/bin/env bats

SCRIPT="$BATS_TEST_DIRNAME/../install-codex-interverse.sh"
CLAVAIN_ROOT="$BATS_TEST_DIRNAME/.."

setup() {
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
}

@test "fallback recommended plugin list matches agent-rig recommended marketplace plugins" {
    local expected actual

    expected="$(jq -r '
        .plugins.recommended[]?
        | .source // empty
        | select(endswith("@interagency-marketplace"))
        | split("@")[0]
    ' "$CLAVAIN_ROOT/agent-rig.json" | sort -u)"

    actual="$(awk '
        /recommended_interverse_plugins_fallback\(\)/ { in_fn=1; next }
        in_fn && /cat <<'\''EOF'\''/ { in_list=1; next }
        in_list && /^EOF$/ { exit }
        in_list { print }
    ' "$SCRIPT" | sort -u)"

    run diff -u <(printf "%s\n" "$expected") <(printf "%s\n" "$actual")
    assert_success
}
