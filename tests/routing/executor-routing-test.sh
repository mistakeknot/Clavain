#!/usr/bin/env bash
# Executor-routing doctrine acceptance suite. All backend checks are dry-run or
# self-test paths; this suite never invokes a real codex/kimi/claude backend.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

contains() {
  local haystack="$1" needle="$2"
  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain '$needle'"
}

not_contains() {
  local haystack="$1" needle="$2"
  [[ "$haystack" != *"$needle"* ]] || fail "expected output not to contain '$needle'"
}

yaml_out="$(python3 -c "import yaml; d=yaml.safe_load(open('config/routing.yaml')); e=d['executor_routing']; assert e['classes']['tagging']==['kimi','codex']; assert e['classes']['reasoning']==['codex']; assert e['default']==['codex']; print('YAML_OK')")" \
  || fail "routing YAML assertion failed"
contains "$yaml_out" "YAML_OK"

# Expectations are mode-dependent (Sylveste-d3m flipped the default to shadow):
#   off     -> resolver returns nothing
#   shadow  -> logs the would-route order, returns the safe default (codex)
#   enforce -> returns the class order (kimi codex for tagging)
MODE="$(python3 -c "import yaml; print((yaml.safe_load(open('config/routing.yaml')).get('executor_routing') or {}).get('mode','off'))")" \
  || fail "could not read executor_routing.mode"

tag_order="$(bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging' 2>/dev/null)" \
  || fail "tagging resolver failed"
unmapped_order="$(bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order somethingunmapped' 2>/dev/null)" \
  || fail "unmapped resolver failed"

case "$MODE" in
  enforce)
    [[ "$tag_order" == "kimi codex" ]] || fail "enforce: tagging order was '$tag_order'"
    [[ "$unmapped_order" == "codex" ]] || fail "enforce: unmapped order was '$unmapped_order'" ;;
  shadow)
    [[ "$tag_order" == "codex" ]] || fail "shadow: tagging order was '$tag_order' (expected the safe default)"
    [[ "$unmapped_order" == "codex" ]] || fail "shadow: unmapped order was '$unmapped_order'" ;;
  off)
    [[ -z "$tag_order" ]] || fail "off: tagging order was '$tag_order' (expected empty)" ;;
  *) fail "unknown executor_routing.mode '$MODE'" ;;
esac

safe="$(bash scripts/dispatch.sh --dry-run --to kimi -C /tmp "hello" 2>&1)" \
  || fail "safe kimi dry-run failed"
contains "$safe" "--agent-file"
contains "$safe" "--prompt=hello"

unsafe="$(bash scripts/dispatch.sh --dry-run --to kimi --kimi-unsafe -C /tmp "hello" 2>&1)" \
  || fail "unsafe kimi dry-run failed"
contains "$unsafe" "-p"
not_contains "$unsafe" "--agent-file"

tagging="$(bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" 2>&1)" \
  || fail "auto tagging dry-run failed"
reasoning="$(bash scripts/dispatch.sh --dry-run --to auto --class reasoning -C /tmp "hi" 2>&1)" \
  || fail "auto reasoning dry-run failed"
bogus="$(bash scripts/dispatch.sh --dry-run --to auto --class bogus -C /tmp "hi" 2>&1)" \
  || fail "auto bogus dry-run failed"
# Strip the shadow log line before asserting on the backend: it contains the
# literal "would-route=kimi codex", so a bare `contains "$tagging" "kimi"` passes
# even when nothing is actually dispatched to kimi.
tagging_cmd="$(printf '%s\n' "$tagging" | grep -v '\[executor-shadow\]')"
case "$MODE" in
  enforce) contains "$tagging_cmd" "kimi" ;;
  shadow)  contains "$tagging" "[executor-shadow]"
           not_contains "$tagging_cmd" "kimi"
           contains "$tagging_cmd" "codex exec" ;;
  off)     contains "$tagging_cmd" "codex exec" ;;
esac
contains "$reasoning" "codex exec"
contains "$bogus" "codex exec"

parse="$(python3 -c "import ast; ast.parse(open('scripts/executor-parity-eval.py').read()); print('PARSE_OK')")" \
  || fail "parity harness did not parse"
contains "$parse" "PARSE_OK"
self_test="$(python3 scripts/executor-parity-eval.py --self-test 2>&1)" \
  || fail "parity harness self-test failed"
contains "$self_test" "SELFTEST_OK"
wrapper_test="$(EXECUTOR_PARITY_LOG_INTERVAL=0.1 bash scripts/executor-parity-eval.sh --self-test 2>&1)" \
  || fail "parity wrapper self-test failed"
contains "$wrapper_test" "SELFTEST_OK"

echo "PASS: executor routing suite"
