#!/usr/bin/env bats
# An explicit assertion-library selection is a contract, not a hint.
#
# Sylveste-psey: the scheduled lane picks its tools deliberately and the harness
# must actually use the ones it picked. test_helper.bash autodetects helpers from
# five candidate roots, so an explicit selection that silently fell back to a
# different root would mean the suite was not testing what the lane chose --
# the same class of defect as a /tmp entry shadowing a selected binary.
#
# These cases build tiny throwaway libraries exporting distinct sentinels, so
# they run anywhere without installing packages. Real assertion-library
# compatibility is established by the equipped zklw suite, not here.

setup() {
    HELPER="$BATS_TEST_DIRNAME/test_helper.bash"
    [ -f "$HELPER" ]
    WORK="$BATS_TEST_TMPDIR/work"
    mkdir -p "$WORK"
}

# Build a helper root whose two libraries announce themselves.
_make_libs() {
    local root="$1" tag="$2"
    mkdir -p "$root/bats-support" "$root/bats-assert"
    printf 'export CLAVAIN_TEST_SUPPORT_TAG=%s\n' "$tag" > "$root/bats-support/load.bash"
    printf 'export CLAVAIN_TEST_ASSERT_TAG=%s\n' "$tag" > "$root/bats-assert/load.bash"
}

# Run test_helper.bash's resolution in a child, reporting what it loaded.
_resolve() {
    local dirname="$1"
    env CLAVAIN_BATS_LIBS="${CLAVAIN_BATS_LIBS-}" \
        BATS_TEST_DIRNAME="$dirname" \
        HELPER_UNDER_TEST="$HELPER" \
        bash -c '
            load() { source "$1.bash"; }
            source "$HELPER_UNDER_TEST" || exit $?
            printf "support=%s assert=%s root=%s\n" \
                "${CLAVAIN_TEST_SUPPORT_TAG:-none}" \
                "${CLAVAIN_TEST_ASSERT_TAG:-none}" \
                "${BATS_LIBS:-none}"
        '
}

@test "an explicit helper root is loaded, and both libraries come from it" {
    _make_libs "$WORK/chosen" chosen
    _make_libs "$WORK/fallback" fallback
    mkdir -p "$WORK/case"
    ln -s "$WORK/fallback" "$WORK/node_modules"

    CLAVAIN_BATS_LIBS="$WORK/chosen" run _resolve "$WORK/case"
    [ "$status" -eq 0 ]
    [[ "$output" == *"support=chosen"* ]]
    [[ "$output" == *"assert=chosen"* ]]
}

@test "an explicit helper root that is invalid FAILS, even when a fallback exists" {
    # The fallback is deliberately present and usable. Silently using it would
    # mean the lane's explicit choice was ignored.
    _make_libs "$WORK/fallback" fallback
    mkdir -p "$WORK/case" "$WORK/empty"
    ln -s "$WORK/fallback" "$WORK/node_modules"

    CLAVAIN_BATS_LIBS="$WORK/empty" run _resolve "$WORK/case"
    [ "$status" -ne 0 ]
    [[ "$output" == *"CLAVAIN_BATS_LIBS"* ]]
    [[ "$output" != *"support=fallback"* ]]
}

@test "an explicit helper root missing only bats-assert still FAILS" {
    mkdir -p "$WORK/half/bats-support" "$WORK/case"
    printf 'export CLAVAIN_TEST_SUPPORT_TAG=half\n' > "$WORK/half/bats-support/load.bash"

    CLAVAIN_BATS_LIBS="$WORK/half" run _resolve "$WORK/case"
    [ "$status" -ne 0 ]
    [[ "$output" == *"bats-assert"* ]]
}

@test "[negative control] with no explicit root, autodetection still works" {
    _make_libs "$WORK/fallback" fallback
    mkdir -p "$WORK/case"
    ln -s "$WORK/fallback" "$WORK/node_modules"

    unset CLAVAIN_BATS_LIBS
    run _resolve "$WORK/case"
    [ "$status" -eq 0 ]
    [[ "$output" == *"support=fallback"* ]]
}

@test "[negative control] no explicit root and no libraries anywhere is not an error" {
    # Ordinary local runs on a machine without the helpers must still work; only
    # an explicit, wrong selection is fatal.
    mkdir -p "$WORK/bare/case"
    CLAVAIN_BATS_LIBS="" run _resolve "$WORK/bare/case"
    [ "$status" -eq 0 ]
}
