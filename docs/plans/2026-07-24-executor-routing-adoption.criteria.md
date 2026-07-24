## Acceptance Criteria

1. routing.yaml declares shadow mode + the category→class map (implementation→reasoning safe).
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && python3 -c "import yaml; e=yaml.safe_load(open('config/routing.yaml'))['executor_routing']; assert e['mode']=='shadow'; m=e['category_class_map']; assert m['test-generation']=='tagging' and m['doc-update']=='tagging' and m['implementation']=='reasoning'; print('MAP_OK')"
   ```
2. lib-routing maps category→class, unmapped → reasoning (safe).
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && bash -c 'source scripts/lib-routing.sh; a=$(routing_resolve_class_for_category test-generation); b=$(routing_resolve_class_for_category nonesuch); [ "$a" = tagging ] && [ "$b" = reasoning ] && echo CAT_OK'
   ```
3. Shadow mode logs the would-route decision AND routes the safe backend (nothing to kimi).
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && bash -c 'source scripts/lib-routing.sh; out=$(routing_resolve_executor_order tagging 2>/tmp/exsh.$$); grep -q "\[executor-shadow\] class=tagging would-route=kimi codex routed=codex" /tmp/exsh.$$ && [ "$out" = codex ] && echo SHADOW_OK; rm -f /tmp/exsh.$$'
   ```
4. `--to auto --class tagging` surfaces the shadow line and uses codex (dry-run, no kimi).
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && s=$(bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" 2>&1); echo "$s" | grep -q "\[executor-shadow\]" && echo "$s" | grep -q "codex exec" && echo "$s" | grep -qv "kimi --agent-file" && echo DISPATCH_SHADOW_OK
   ```
5. interserve-engine passes --class from the task category.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && grep -q -- "--class" skills/interserve-engine/SKILL.md && grep -q "routing_resolve_class_for_category" skills/interserve-engine/SKILL.md && echo SKILL_OK
   ```
6. The shadow report tallies would-route events per class.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && printf '[executor-shadow] class=tagging would-route=kimi codex routed=codex\n[executor-shadow] class=tagging would-route=kimi codex routed=codex\n[executor-shadow] class=reasoning would-route=codex routed=codex\n' > /tmp/exrep.$$ && bash scripts/executor-routing-shadow-report.sh --from-file /tmp/exrep.$$ --json | grep -q '"class":"tagging","count":2' && echo REPORT_OK; rm -f /tmp/exrep.$$
   ```
7. The adoption test suite passes.
   ```check
   cd /Users/sma/projects/Sylveste/os/Clavain && bash tests/routing/executor-adoption-test.sh 2>&1 | grep -q PASS && echo TESTS_OK
   ```
