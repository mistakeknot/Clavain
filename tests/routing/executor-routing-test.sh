#!/usr/bin/env bash
# Executor-routing doctrine acceptance suite. All backend checks are dry-run or
# self-test paths; this suite never invokes a real codex/kimi/claude backend.
# Sylveste-d3m phase 1: also covers executor shadow mode and the parity corpus log.
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

# --- Sylveste-d3m phase 1: shadow mode + parity corpus ---------------------
shadow_log="$(mktemp)"
rm -f "$shadow_log"

shadow_tag="$(CLAVAIN_EXECUTOR_ROUTING_MODE=shadow CLAVAIN_EXECUTOR_SHADOW_LOG="$shadow_log" bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging' 2>/dev/null)" \
  || fail "shadow tagging resolver failed"
[[ -z "$shadow_tag" ]] || fail "shadow mode must print no order, got '$shadow_tag'"
[[ ! -s "$shadow_log" ]] || fail "the resolver must not write the corpus; dispatch.sh is the single logging site"

rm -f "$shadow_log"
shadow_dispatch="$(CLAVAIN_EXECUTOR_ROUTING_MODE=shadow CLAVAIN_EXECUTOR_SHADOW_LOG="$shadow_log" bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" 2>&1)" \
  || fail "shadow tagging dry-run failed"
contains "$shadow_dispatch" "codex exec"
not_contains "$shadow_dispatch" "--agent-file"
[[ -s "$shadow_log" ]] || fail "shadow dispatch wrote no corpus row"
[[ "$(wc -l < "$shadow_log" | tr -d ' ')" == "1" ]] || fail "expected exactly one corpus row per dispatch, got $(wc -l < "$shadow_log")"
contains "$(cat "$shadow_log")" '"class": "tagging"'
contains "$(cat "$shadow_log")" '"mode": "shadow"'
contains "$(cat "$shadow_log")" '"would_route": ["kimi", "codex"]'
contains "$(cat "$shadow_log")" '"chosen": "codex"'

off_tag="$(CLAVAIN_EXECUTOR_ROUTING_MODE=off bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging')" \
  || fail "off resolver failed"
[[ -z "$off_tag" ]] || fail "off mode must print no order, got '$off_tag'"

enforce_tag="$(CLAVAIN_EXECUTOR_ROUTING_MODE=enforce bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging')" \
  || fail "enforce resolver failed"
[[ "$enforce_tag" == "kimi codex" ]] || fail "enforce tagging order was '$enforce_tag'"

rm -f "$shadow_log"
fast="$(CLAVAIN_EXECUTOR_SHADOW_LOG="$shadow_log" bash scripts/dispatch.sh --dry-run --to auto --class interserve-fast -C /tmp "hi" 2>&1)" \
  || fail "auto interserve-fast dry-run failed"
contains "$fast" "codex exec"
not_contains "$fast" "kimi"
[[ -s "$shadow_log" ]] || fail "dispatch --to auto wrote no corpus row"
contains "$(cat "$shadow_log")" '"class": "interserve-fast"'
contains "$(cat "$shadow_log")" '"chosen": "codex"'
python3 -c "import json,sys; [json.loads(l) for l in open('$shadow_log')]; print('CORPUS_JSON_OK')" | grep -q CORPUS_JSON_OK || fail "corpus rows are not valid JSON lines"

default_log="$HOME/.clavain/executor-routing-shadow.jsonl"
before_lines=0; [[ -f "$default_log" ]] && before_lines="$(wc -l < "$default_log" | tr -d ' ')"
bash scripts/dispatch.sh --dry-run --to auto --class interserve-deep -C /tmp "hi" >/dev/null 2>&1 || fail "auto interserve-deep dry-run failed"
CLAVAIN_EXECUTOR_ROUTING_MODE=shadow bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" >/dev/null 2>&1 || fail "shadow dry-run failed"
after_lines=0; [[ -f "$default_log" ]] && after_lines="$(wc -l < "$default_log" | tr -d ' ')"
[[ "$before_lines" == "$after_lines" ]] || fail "dry-run must not write the default corpus log (enforce or shadow)"

grep -q -- '--to auto --class interserve-deep' skills/interserve-engine/SKILL.md || fail "interserve-engine does not pass --class"
rm -f "$shadow_log"

echo "PASS: executor routing suite"
