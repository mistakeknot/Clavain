#!/usr/bin/env bats
# Structural tests for /clavain:quality-gates routing integration.

setup() {
    load test_helper
    QUALITY_GATES="$BATS_TEST_DIRNAME/../../commands/quality-gates.md"
}

@test "quality-gates small shortcut routes fd-quality through B2 complexity resolver" {
  run grep -q 'routing_resolve_agents --phase "quality-gates" --agents "fd-quality"' "$QUALITY_GATES"
  [ "$status" -eq 0 ]
  run grep -q -- '--prompt-tokens "$REVIEW_TOKENS" --file-count "$CHANGED_FILES" --reasoning-depth "$REVIEW_DEPTH"' "$QUALITY_GATES"
  [ "$status" -eq 0 ]
  run grep -q 'model: "${FD_QUALITY_MODEL}"' "$QUALITY_GATES"
  [ "$status" -eq 0 ]
}

@test "quality-gates full flux-drive handoff carries quality-gates phase" {
  run grep -q '/interflux:flux-drive $DIFF_PATH --phase=quality-gates' "$QUALITY_GATES"
  [ "$status" -eq 0 ]
}
