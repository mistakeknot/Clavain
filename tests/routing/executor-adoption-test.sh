#!/usr/bin/env bash
# Executor-routing adoption acceptance suite. All backend checks are dry-run or
# fixture-based; this suite never invokes a real codex/kimi/claude backend.
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

fixture="$(mktemp /tmp/executor-routing-adoption.XXXXXX)" || exit 1
shadow_log="$(mktemp /tmp/executor-routing-shadow.XXXXXX)" || exit 1
trap 'rm -f "$fixture" "$shadow_log"' EXIT

yaml_out="$(python3 -c "import yaml; d=yaml.safe_load(open('config/routing.yaml')); e=d['executor_routing']; assert e['mode']=='shadow'; assert e['category_class_map']['test-generation']=='tagging'; assert e['category_class_map']['implementation']=='reasoning'; print('YAML_OK')")" \
  || fail "routing YAML assertion failed"
contains "$yaml_out" "YAML_OK"

classes="$(bash -c 'source scripts/lib-routing.sh; printf "%s %s %s\n" "$(routing_resolve_class_for_category test-generation)" "$(routing_resolve_class_for_category implementation)" "$(routing_resolve_class_for_category nonesuch)"')" \
  || fail "category class resolver failed"
[[ "$classes" == "tagging reasoning reasoning" ]] || fail "category classes were '$classes'"

shadow_order="$(bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging' 2>"$shadow_log")" \
  || fail "shadow order resolver failed"
[[ "$shadow_order" == "codex" ]] || fail "shadow order was '$shadow_order'"
shadow_line="$(cat "$shadow_log")"
contains "$shadow_line" "[executor-shadow] class=tagging would-route=kimi codex routed=codex"

dispatch="$(bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" 2>&1)" \
  || fail "auto tagging dry-run failed"
contains "$dispatch" "[executor-shadow]"
contains "$dispatch" "codex exec"
not_contains "$dispatch" "kimi --agent-file"

# The criterion above greps the whole output, which includes the shadow log line
# ("would-route=kimi codex") — so a real kimi invocation could hide behind it.
# Assert against the command body with the shadow line stripped.
dispatch_cmd="$(printf '%s\n' "$dispatch" | grep -v '\[executor-shadow\]')"
not_contains "$dispatch_cmd" "kimi"

# Wiring regression (Sylveste-d3m): --class is only read on the `auto` path, so a
# call site that passes --class without --to auto silently logs nothing and the
# phase-2 parity corpus stays empty. Pin both halves at the only adopted call site.
classless="$(bash scripts/dispatch.sh --dry-run --class tagging -C /tmp "hi" 2>&1)" \
  || fail "class-without-auto dry-run failed"
not_contains "$classless" "[executor-shadow]"

for doc in skills/interserve-engine/SKILL.md skills/interserve-engine/SKILL-compact.md; do
  doc_body="$(cat "$doc")"
  contains "$doc_body" "--to auto"
  contains "$doc_body" "--class"
done

# Mode normalization (Sylveste-d3m): YAML 1.1 parses a bare `mode: off` as the
# boolean False. Before normalization that missed the "off" and "shadow" branches
# and fell through to enforce — the documented kill switch routed live traffic to
# kimi. Every non-enforce spelling must resolve to "route nothing new".
mode_cfg="$(mktemp /tmp/executor-routing-mode.XXXXXX)" || exit 1
trap 'rm -f "$fixture" "$shadow_log" "$mode_cfg"' EXIT
for spelling in off on yes no bogus '"off"'; do
  cat > "$mode_cfg" <<YAML
executor_routing:
  mode: $spelling
  default: [codex]
  classes:
    tagging: [kimi, codex]
YAML
  got="$(CLAVAIN_ROUTING_CONFIG="$mode_cfg" bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging' 2>/dev/null)"
  [[ -z "$got" ]] || fail "mode: $spelling resolved to '$got' (expected routing bypassed, not enforce)"
done

# enforce is still honored — the fix must not disable routing outright.
cat > "$mode_cfg" <<'YAML'
executor_routing:
  mode: enforce
  default: [codex]
  classes:
    tagging: [kimi, codex]
YAML
enforced="$(CLAVAIN_ROUTING_CONFIG="$mode_cfg" bash -c 'source scripts/lib-routing.sh; routing_resolve_executor_order tagging' 2>/dev/null)"
[[ "$enforced" == "kimi codex" ]] || fail "enforce mode resolved to '$enforced'"

printf '%s\n' \
  '[executor-shadow] class=tagging would-route=kimi codex routed=codex' \
  '[executor-shadow] class=reasoning would-route=codex routed=codex' \
  '[executor-shadow] class=tagging would-route=kimi codex routed=codex' > "$fixture"
report="$(bash scripts/executor-routing-shadow-report.sh --from-file "$fixture" --json)" \
  || fail "shadow report failed"
contains "$report" '"class":"tagging","count":2'
contains "$report" '"class":"reasoning","count":1'

echo "PASS: executor routing adoption suite"
