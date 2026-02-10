#!/usr/bin/env bats
# Tests for hooks/dotfiles-sync.sh

setup() {
    load test_helper
}

@test "dotfiles-sync: exits zero when sync script is missing" {
    run bash -c "HOME='/nonexistent' bash '$HOOKS_DIR/dotfiles-sync.sh'"
    assert_success
}

@test "dotfiles-sync: exits zero always" {
    run bash "$HOOKS_DIR/dotfiles-sync.sh"
    assert_success
}
