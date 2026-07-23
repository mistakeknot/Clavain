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

tag_order="$(bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging')" \
  || fail "tagging resolver failed"
unmapped_order="$(bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order somethingunmapped')" \
  || fail "unmapped resolver failed"
[[ "$tag_order" == "kimi codex" ]] || fail "tagging order was '$tag_order'"
[[ "$unmapped_order" == "codex" ]] || fail "unmapped order was '$unmapped_order'"

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
contains "$tagging" "kimi"
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
