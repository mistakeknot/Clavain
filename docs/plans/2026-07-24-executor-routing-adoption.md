---
artifact_type: plan
bead: Sylveste-d3m
stage: design
---
# Adopt --to auto --class across Clavain dispatch — phase 1 (shadow) plan

> **For Claude:** mechanical shell + YAML + skill-doc edits. Complete code below.
> Verify via `--dry-run`, sourced-function calls, and a shadow-log check. NO real
> LLM calls anywhere in this plan.

**Bead:** Sylveste-d3m
**Goal:** Wire `--class` into Clavain's highest-volume dispatch path
(interserve-engine) via a category→class map, and add an `executor_routing`
SHADOW mode that logs the would-route decision while routing nothing to kimi —
building the corpus for the phase-2 per-class parity evals.

**Architecture:** Additive to the shipped executor-routing layer (Sylveste-dnl).
routing.yaml gains a `category_class_map` + honors `mode: shadow`; lib-routing
gains a category→class resolver and a shadow would-route log in the executor-order
path (mirroring the existing B2/B5 shadow pattern); interserve-engine passes
`--class` mapped from its Step-1 classification; a report script summarizes
per-class volume. Enforce/flip is explicitly OUT (phase 2).

**Tech Stack:** bash (lib-routing.sh, dispatch.sh, report script), YAML
(routing.yaml), markdown (interserve-engine SKILL). No new deps.

---

## Must-Haves

**Truths:**
- routing.yaml declares a category→class map; `mode: shadow` logs would-route but
  routes the safe backend (codex), `mode: enforce` routes free-first, `off` bypasses.
- `routing_resolve_class_for_category <cat>` returns the mapped class (unmapped →
  "reasoning", the safe class).
- In shadow, `--to auto --class tagging` emits an `[executor-shadow]` would-route
  line AND resolves to codex (nothing to kimi).
- interserve-engine's dispatch passes `--class` derived from its task category.
- A report script summarizes `[executor-shadow]` lines per class.

**Artifacts:**
- `config/routing.yaml` — `category_class_map`; executor_routing `mode: shadow`.
- `scripts/lib-routing.sh` — `routing_resolve_class_for_category`; shadow log in
  `routing_resolve_executor_order`.
- `scripts/dispatch.sh` — shadow-aware `--to auto` (log + safe route).
- `skills/interserve-engine/SKILL.md` — pass `--class`.
- `scripts/executor-routing-shadow-report.sh`.
- `tests/routing/executor-adoption-test.sh`.

**Key Links:**
- interserve-engine category → `routing_resolve_class_for_category` → `--class` →
  dispatch.sh `--to auto` → `routing_resolve_executor_order` (shadow-aware).

---

## Task 1: routing.yaml — category_class_map + shadow default

**Files:** Modify `config/routing.yaml` (executor_routing section).

**Step 1.** Set `mode: shadow` (was enforce) and add the map under executor_routing:
```yaml
executor_routing:
  mode: shadow             # off | shadow | enforce  (phase-1 adoption: shadow)
  # category -> parity class. Source = delegation.categories; class = what the
  # parity eval verdicts on. implementation spans mechanical+reasoning -> safe
  # (reasoning) until sub-classified. Unmapped category -> reasoning (safe).
  category_class_map:
    test-generation: tagging
    doc-update:      tagging
    exploration:     reasoning
    implementation:  reasoning
    review:          reasoning
    architecture:    reasoning
    brainstorm:      reasoning
    interactive:     reasoning
  classes:
    tagging:   [kimi, codex]
    reasoning: [codex]
  default:     [codex]
```

<verify>
- run: `cd /Users/sma/projects/Sylveste/os/Clavain && python3 -c "import yaml; e=yaml.safe_load(open('config/routing.yaml'))['executor_routing']; assert e['mode']=='shadow'; assert e['category_class_map']['test-generation']=='tagging'; assert e['category_class_map']['implementation']=='reasoning'; print('MAP_OK')"`
  expect: contains "MAP_OK"
</verify>

## Task 2: lib-routing.sh — category→class resolver

**Files:** Modify `scripts/lib-routing.sh`.

**Step 1.** Add (near `routing_resolve_executor_order`):
```bash
# Map a delegation category to a parity class via executor_routing.category_class_map.
# Unmapped/empty category -> "reasoning" (the safe class). Prints the class.
routing_resolve_class_for_category() {
  local category="$1"
  local cfg; cfg="$(_routing_find_config)" || { echo reasoning; return 0; }
  [[ -n "$cfg" && -f "$cfg" ]] || { echo reasoning; return 0; }
  python3 - "$cfg" "$category" <<'PY' 2>/dev/null || echo reasoning
import sys, yaml
cfg, cat = sys.argv[1], sys.argv[2]
d = yaml.safe_load(open(cfg)) or {}
m = ((d.get("executor_routing") or {}).get("category_class_map") or {})
print(m.get(cat, "reasoning"))
PY
}
```

<verify>
- run: `cd /Users/sma/projects/Sylveste/os/Clavain && bash -c 'source scripts/lib-routing.sh; a=$(routing_resolve_class_for_category test-generation); b=$(routing_resolve_class_for_category implementation); c=$(routing_resolve_class_for_category nonesuch); [ "$a" = tagging ] && [ "$b" = reasoning ] && [ "$c" = reasoning ] && echo CAT_OK'`
  expect: contains "CAT_OK"
</verify>

## Task 3: lib-routing.sh — shadow would-route log in the order resolver

**Files:** Modify `scripts/lib-routing.sh` (`routing_resolve_executor_order`).

**Step 1.** Make the resolver mode-aware: in `shadow`, emit an `[executor-shadow]`
line to stderr recording the would-route order, then return the SAFE order
(`default`, i.e. codex) so nothing routes to kimi. In `enforce`, return the class
order. Replace the python read so it reports mode + would-order + safe-order:
```bash
routing_resolve_executor_order() {
  local class="$1"
  local cfg; cfg="$(_routing_find_config)" || return 0
  [[ -n "$cfg" && -f "$cfg" ]] || return 0
  python3 - "$cfg" "$class" <<'PY' 2>/dev/null || true
import sys, yaml
cfg, cls = sys.argv[1], sys.argv[2]
d = yaml.safe_load(open(cfg)) or {}
e = d.get("executor_routing") or {}
mode = e.get("mode", "off")
if mode == "off":
    sys.exit(0)
classes = e.get("classes") or {}
default = e.get("default") or []
would = classes.get(cls) or default
if mode == "shadow":
    # log what WOULD route, then return the safe (default) order — route nothing new
    sys.stderr.write(f"[executor-shadow] class={cls} would-route={' '.join(would)} routed={' '.join(default)}\n")
    print(" ".join(default))
else:  # enforce
    print(" ".join(would))
PY
}
```

<verify>
- run: `cd /Users/sma/projects/Sylveste/os/Clavain && bash -c 'source scripts/lib-routing.sh; out=$(routing_resolve_executor_order tagging 2>/tmp/exsh.$$); grep -q "\[executor-shadow\] class=tagging would-route=kimi codex routed=codex" /tmp/exsh.$$ && [ "$out" = codex ] && echo SHADOW_OK; rm -f /tmp/exsh.$$'`
  expect: contains "SHADOW_OK"
</verify>

## Task 4: dispatch.sh — shadow log surfaces on `--to auto`

**Files:** Modify `scripts/dispatch.sh` (the `ENGINE == auto` block, ~line 918).

**Step 1.** The auto block already calls `routing_resolve_executor_order`, whose
stderr now carries the `[executor-shadow]` line — so it surfaces automatically.
No code change needed beyond ensuring the resolver's stderr is NOT swallowed.
Confirm the call does not redirect stderr to /dev/null; if it does, remove that so
the shadow line reaches the user/log.

<verify>
- run: `cd /Users/sma/projects/Sylveste/os/Clavain && bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" 2>&1 | grep -q "\[executor-shadow\]" && bash scripts/dispatch.sh --dry-run --to auto --class tagging -C /tmp "hi" 2>&1 | grep -q "codex exec" && echo DISPATCH_SHADOW_OK`
  expect: contains "DISPATCH_SHADOW_OK"
</verify>

## Task 5: interserve-engine SKILL — pass --class from the task category

**Files:** Modify `skills/interserve-engine/SKILL.md`.

**Step 1.** In the megaprompt dispatch example (Step 2) and the parallel-delegation
dispatch (Step 4), after the existing Step-1 classification, add a line resolving
the category to a class and passing it. Add a short subsection "Executor class
(--class)":
```markdown
### Executor class (--class)
After classifying the task (Step 1), pass `--class` so the shipped
executor-routing layer can log/route (phase-1 SHADOW routes nothing to kimi —
it only records the would-route decision for the phase-2 parity evals). Resolve
the class from the task category:

    CLASS=$(bash "$(dirname "$DISPATCH")/lib-routing.sh" >/dev/null 2>&1; \
            source "$(dirname "$DISPATCH")/lib-routing.sh"; \
            routing_resolve_class_for_category "<category>")

Then add `--class "$CLASS"` to the dispatch invocation. `<category>` is the
delegation category (implementation | exploration | review | test-generation |
doc-update | architecture). Unmapped/unsure -> the resolver returns `reasoning`
(safe).
```
Add `--class "$CLASS"` to the two example dispatch commands.

<verify>
- run: `cd /Users/sma/projects/Sylveste/os/Clavain && grep -q -- "--class" skills/interserve-engine/SKILL.md && grep -q "routing_resolve_class_for_category" skills/interserve-engine/SKILL.md && echo SKILL_OK`
  expect: contains "SKILL_OK"
</verify>

## Task 6: executor-routing-shadow-report.sh

**Files:** Create `scripts/executor-routing-shadow-report.sh`.

**Step 1.** Mirror `routing-shadow-report.sh`: harvest `[executor-shadow]` lines
(from a passed logfile arg, or `cass`/`/tmp` fallback), tally per class:
would-route counts, and print a summary (`--json` optional). Include a
`--from-file <path>` for deterministic testing.
```bash
#!/usr/bin/env bash
# Summarize [executor-shadow] would-route decisions per parity class.
# Feeds phase-2: which classes have enough volume to be worth a parity eval.
set -uo pipefail
FROM_FILE=""; JSON=false
while [[ $# -gt 0 ]]; do case "$1" in
  --from-file) FROM_FILE="$2"; shift 2;;
  --json) JSON=true; shift;;
  *) shift;; esac; done
lines=""
if [[ -n "$FROM_FILE" && -f "$FROM_FILE" ]]; then
  lines="$(grep -h '\[executor-shadow\]' "$FROM_FILE" 2>/dev/null || true)"
else
  lines="$(find /tmp -maxdepth 1 -name 'interstat-*' -mtime -7 -exec grep -h '\[executor-shadow\]' {} + 2>/dev/null || true)"
fi
if [[ -z "$lines" ]]; then echo "No [executor-shadow] lines found."; exit 0; fi
# tally class= occurrences
printf '%s\n' "$lines" | sed -n 's/.*class=\([^ ]*\).*/\1/p' | sort | uniq -c | \
while read -r n cls; do
  if $JSON; then printf '{"class":"%s","count":%s}\n' "$cls" "$n"; else printf '  %-10s %s would-route events\n' "$cls" "$n"; fi
done
```

<verify>
- run: `cd /Users/sma/projects/Sylveste/os/Clavain && printf '[executor-shadow] class=tagging would-route=kimi codex routed=codex\n[executor-shadow] class=reasoning would-route=codex routed=codex\n[executor-shadow] class=tagging would-route=kimi codex routed=codex\n' > /tmp/exrep.$$ && bash scripts/executor-routing-shadow-report.sh --from-file /tmp/exrep.$$ | grep -q "tagging" && bash scripts/executor-routing-shadow-report.sh --from-file /tmp/exrep.$$ --json | grep -q '"class":"tagging","count":2' && echo REPORT_OK; rm -f /tmp/exrep.$$`
  expect: contains "REPORT_OK"
</verify>

## Task 7: tests

**Files:** Create `tests/routing/executor-adoption-test.sh` (style: existing
tests/routing/*.sh, PASS:/FAIL: + exit).

**Step 1.** Assert: (a) category map YAML; (b) `routing_resolve_class_for_category`
tagging/reasoning/unmapped; (c) shadow order-resolver logs `[executor-shadow]` and
returns codex; (d) `--dry-run --to auto --class tagging` surfaces the shadow line
AND uses codex exec (nothing to kimi); (e) the report tallies per class from a
fixture file.

<verify>
- run: `cd /Users/sma/projects/Sylveste/os/Clavain && bash tests/routing/executor-adoption-test.sh 2>&1 | grep -q PASS && echo TESTS_OK`
  expect: contains "TESTS_OK"
</verify>

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
