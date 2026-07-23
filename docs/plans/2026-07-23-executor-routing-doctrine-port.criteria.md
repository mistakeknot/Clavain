## Acceptance Criteria

1. routing.yaml declares executor_routing with the parity-grounded classes.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && python3 -c "import yaml; e=yaml.safe_load(open('config/routing.yaml'))['executor_routing']; assert e['classes']['tagging']==['kimi','codex'] and e['classes']['reasoning']==['codex'] and e['default']==['codex']; print('YAML_OK')"
   ```
2. lib-routing resolves per-class order, unmapped → default.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && bash -c 'source scripts/lib-routing.sh; a=$(routing_resolve_executor_order tagging); b=$(routing_resolve_executor_order zzz); [ "$a" = "kimi codex" ] && [ "$b" = "codex" ] && echo RESOLVE_OK'
   ```
3. Kimi backend is untrusted-input-safe by default (restricted profile + =-bound prompt), with an explicit unsafe opt-out.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && s=$(bash scripts/dispatch.sh --dry-run --to kimi -C /tmp "hello" 2>&1); echo "$s" | grep -q -- "--agent-file" && echo "$s" | grep -q -- "--prompt=hello" && u=$(bash scripts/dispatch.sh --dry-run --to kimi --kimi-unsafe -C /tmp "hello" 2>&1); echo "$u" | grep -qv -- "--agent-file"; echo "$u" | grep -q -- "-p" && echo KIMI_SAFE_OK
   ```
4. `--to auto --class` routes free-first for a parity class and safe for reasoning/unmapped.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && t=$(bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" 2>&1); r=$(bash scripts/dispatch.sh --dry-run --to auto --class reasoning -C /tmp "hi" 2>&1); g=$(bash scripts/dispatch.sh --dry-run --to auto --class bogus -C /tmp "hi" 2>&1); echo "$t" | grep -q kimi && echo "$r" | grep -q "codex exec" && echo "$g" | grep -q "codex exec" && echo AUTO_OK
   ```
5. The parity-eval harness parses, self-tests, and produces an explicit-threshold verdict.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && python3 -c "import ast; ast.parse(open('scripts/executor-parity-eval.py').read())" && python3 scripts/executor-parity-eval.py --self-test 2>&1 | grep -q SELFTEST_OK && echo HARNESS_OK
   ```
6. The routing test suite passes.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && bash tests/routing/executor-routing-test.sh 2>&1 | grep -q PASS && echo TESTS_OK
   ```
