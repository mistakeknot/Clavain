#!/usr/bin/env bats

# mk-42j9.44 rework pass 2, P2 finding #11: the --brief-bead block must hand
# the assembler the same role, routing policy, decision context and producer
# identity this dispatch resolves, so the briefing's §2 Authority describes
# the route the lane actually runs under. Each is passed only when set.

setup() {
    load test_helper

    DISPATCH_SCRIPT="$BATS_TEST_DIRNAME/../../scripts/dispatch.sh"
    TMPDIR_T="$(mktemp -d)"

    BLOCK="$TMPDIR_T/brief-block.sh"
    awk '
        /^if \[\[ -n "\$BRIEF_BEAD" \]\]; then/ { emit=1 }
        emit {
            print
            if ($0 ~ /^fi[[:space:]]*$/) { emit=0 }
        }
    ' "$DISPATCH_SCRIPT" > "$BLOCK"
    grep -q 'BRIEF_ARGS' "$BLOCK"

    # A stub assembler that prints its own argv, one per line.
    DISPATCH_SCRIPT_DIR="$TMPDIR_T/scripts"
    mkdir -p "$DISPATCH_SCRIPT_DIR"
    cat > "$DISPATCH_SCRIPT_DIR/assemble-briefing.py" <<'EOF'
import sys
print("\n".join(sys.argv[1:]))
EOF
}

teardown() {
    rm -rf "$TMPDIR_T"
}

_run_block() {
    PROMPT="task"
    BRIEF_BEAD="mk-1"
    BRIEF_BD_CWD=""
    WORKDIR="$TMPDIR_T"
    # shellcheck disable=SC1090
    source "$BLOCK"
    printf '%s\n' "$PROMPT"
}

@test "--brief-bead passes role, policy, decision context and producer identity when set" {
    ROLE="validation"
    PRODUCER_IDENTITY="claude:opus"
    export CLAVAIN_ROUTING_POLICY="$TMPDIR_T/routing.yaml"
    export CLAVAIN_DECISION_CONTEXT="$TMPDIR_T/ctx.json"
    run _run_block
    [ "$status" -eq 0 ]
    [[ "$output" == *$'--role\nvalidation'* ]]
    [[ "$output" == *$'--policy\n'"$TMPDIR_T/routing.yaml"* ]]
    [[ "$output" == *$'--decision-context\n'"$TMPDIR_T/ctx.json"* ]]
    [[ "$output" == *$'--producer-identity\nclaude:opus'* ]]
}

@test "--brief-bead omits unset routing arguments" {
    ROLE=""
    PRODUCER_IDENTITY=""
    unset CLAVAIN_ROUTING_POLICY CLAVAIN_DECISION_CONTEXT
    run _run_block
    [ "$status" -eq 0 ]
    [[ "$output" == *$'--bead\nmk-1'* ]]
    [[ "$output" != *"--role"* ]]
    [[ "$output" != *"--policy"* ]]
    [[ "$output" != *"--decision-context"* ]]
    [[ "$output" != *"--producer-identity"* ]]
}
