#!/usr/bin/env bats

setup() {
    ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    T="$(mktemp -d)"
    git -C "$T" init -q
    mkdir -p "$T/bin"
    export PROBE_COUNT="$T/count" PROBE_SCENARIO=success
    export REAL_PYTHON="$(command -v python3)" PROBE_FIXTURE="$ROOT/tests/fixtures/pool-probe.py"
    cat > "$T/bin/python3" <<'SH'
#!/usr/bin/env bash
case "$1" in
    */bb-host.py) exit 0 ;;
    */bb-pool-eligibility.py) exec "$REAL_PYTHON" "$PROBE_FIXTURE" "$@" ;;
    *) exec "$REAL_PYTHON" "$@" ;;
esac
SH
    chmod +x "$T/bin/python3"
    export PATH="$T/bin:$PATH"
    export BB_SERVER_URL=http://127.0.0.1 BB_THREAD_ID=fixture
    export ANTHROPIC_AUTH_TOKEN=dummy CODEX_POOL_AUTH_TOKEN=dummy
    export ANTHROPIC_BASE_URL="$BB_SERVER_URL/api/v1/plugins/account-pool/http"
    export CODEX_OPENAI_BASE_URL="$ANTHROPIC_BASE_URL/v1"
    export CLAVAIN_BB_DIRECT_POOL=1 CLAVAIN_CONTEXT_GATEWAY_MODE=off
    export CLAVAIN_BB_POOL_PROBE_RETRIES=2 CLAVAIN_BB_POOL_PROBE_BACKOFF=0
    export CLAVAIN_DISPATCH_FAILURE_FILE="$T/failure"
}

teardown() { rm -rf "$T"; }

dispatch() {
    run bash "$ROOT/scripts/dispatch.sh" --dry-run --to "$1" -C "$T" fixture
    if [[ "$status" -ne 0 ]]; then printf '%s\n' "$output"; fi
}

@test "probe timeouts and transport failures have distinct transient status" {
    for scenario in timeout transport http500 http503; do
        export PROBE_SCENARIO="$scenario"
        run python3 "$ROOT/scripts/bb-pool-eligibility.py" claude
        [ "$status" -eq 4 ]
        [[ "$output" == *"transient"* ]]
        [[ "$output" != *dummy* ]]
    done
}

@test "timeout retries twice then succeeds for both providers" {
    export PROBE_SCENARIO=recover
    for provider in claude codex; do
        echo 0 > "$PROBE_COUNT"
        dispatch "$provider"
        [ "$status" -eq 0 ]
        [ "$(cat "$PROBE_COUNT")" -eq 3 ]
        [[ "$output" != *"falling back"* ]]
    done
}

@test "persistent transient failures fall back after bounded retries" {
    for scenario in timeout transport http503; do
        export PROBE_SCENARIO="$scenario"
        for provider in claude codex; do
            echo 0 > "$PROBE_COUNT"
            dispatch "$provider"
            [ "$status" -eq 0 ]
            [ "$(cat "$PROBE_COUNT")" -eq 3 ]
            [[ "$output" == *"falling back to non-pooled"* ]]
            [[ "$output" != *'model_provider=\"bb-account-pool\"'* ]]
            [ ! -f "$T/failure" ]
        done
    done
}

@test "configuration errors remain terminal without retries" {
    for scenario in invalid-origin missing-token malformed http401 http403 http404; do
        for provider in claude codex; do
            echo 0 > "$PROBE_COUNT"
            export PROBE_SCENARIO="$scenario"
            export BB_SERVER_URL=http://127.0.0.1 ANTHROPIC_AUTH_TOKEN=dummy CODEX_POOL_AUTH_TOKEN=dummy
            if [[ "$scenario" == invalid-origin ]]; then export BB_SERVER_URL=invalid; fi
            export ANTHROPIC_BASE_URL="$BB_SERVER_URL/api/v1/plugins/account-pool/http"
            export CODEX_OPENAI_BASE_URL="$ANTHROPIC_BASE_URL/v1"
            dispatch "$provider"
            [ "$status" -ne 0 ]
            [ "$(cat "$PROBE_COUNT")" -eq 1 ]
            [ "$(cat "$T/failure")" == terminal_configuration ]
            [[ "$output" != *"falling back"* ]]
        done
    done
}

@test "ineligible status does not retry or emit a transient notice" {
    export PROBE_SCENARIO=ineligible
    dispatch claude
    [ "$status" -eq 0 ]
    [ "$(cat "$PROBE_COUNT")" -eq 1 ]
    [[ "$output" != *transient* ]]
}
