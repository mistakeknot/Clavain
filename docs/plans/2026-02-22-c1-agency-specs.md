# Plan: C1 Agency Specs — Declarative Per-Stage Config

**Bead:** iv-ssck
**PRD:** [2026-02-22-c1-agency-specs.md](../prds/2026-02-22-c1-agency-specs.md)
**Brainstorm:** [2026-02-22-c1-agency-specs-brainstorm.md](../brainstorms/2026-02-22-c1-agency-specs-brainstorm.md)
**Reviews:** [architecture](../../docs/research/architecture-review-of-agency-spec-plan.md), [correctness](../../docs/research/correctness-review-of-agency-spec-plan.md), [quality](../../docs/research/quality-review-of-agency-spec-plan.md)

---

## Review Findings Incorporated

Three-agent flux-drive review (fd-architecture, fd-correctness, fd-quality) identified these issues. All addressed below:

| Finding | Severity | Resolution |
|---------|----------|------------|
| Gate short-circuit bypasses ic gates | Critical | ic gate check runs first as precondition; spec gates are additive (Task 3.1) |
| Corrupted spec cache skips all gates | Critical | Three-state loaded flag: `ok`/`failed`/`fallback` (Task 2.1) |
| `sprint_stage_tokens_spent` undefined | Medium | Explicitly defined (Task 3.2) |
| `sprint_budget_total` undefined | Medium | Explicitly defined (Task 3.2) |
| Budget overallocation via min_tokens | High | Normalize at load time; cap at runtime (Task 2.2) |
| Deep merge semantics unspecified | Medium | Arrays replace, dicts merge, `{disabled: true}` for deletion (Task 2.2) |
| PRD says yq, plan says Python | Medium | PRD needs correction (noted) |
| `query` subcommand redundant | Medium | Dropped — use jq on cached JSON (Task 2.2) |
| F6 companion declarations too detailed | Medium | Only `provides` array in C1; defer detail to C2 (Task 3.3) |
| Naming: `agency_*` inconsistent | Medium | Renamed to `spec_*` prefix (Task 2.1) |
| Python helper in hooks/ | Low | Moved to `scripts/agency-spec-helper.py` (Task 2.2) |
| `additionalProperties: true` needed | Medium | Added to schema for C2/C3 forward-compat (Task 1.1) |
| `condition` field premature | Low | Kept as optional unvalidated string with C3 note |
| `model_preference` routing overlap | Low | Renamed to `model_tier_hint` (Task 1.1) |
| `_phase_to_stage` naming | Low | Renamed to `_sprint_phase_to_stage` (Task 3.1) |
| `set -euo pipefail` prohibition | Low | Documented in lib-agency.sh header (Task 2.1) |
| Missing gate-type-specific tests | Medium | Added per-type + shadow + off tests (Testing Strategy) |
| `agency_get_default`/`agency_get_stage_gates` missing from inventory | Low | Added to function list (Task 2.1) |

---

## Implementation Order

1. **Batch 1 (parallel):** F1 schema + F2 default spec — YAML/JSON files, no code deps
2. **Batch 2:** F3 loader library — needs schema (F1) and spec (F2)
3. **Batch 3 (parallel):** F4 gates + F5 budget + F6 companions — all consume loader (F3)

---

## Batch 1: Schema + Default Spec

### Task 1.1: JSON Schema (`agency-spec.schema.json`)

**File:** `os/clavain/config/agency-spec.schema.json`

JSON Schema (draft-07). Key design decisions:
- `additionalProperties: true` on `companions.<name>` and `stages.<name>.agents[]` for C2/C3 extensibility
- `model_tier_hint` (not `model_preference`) in budget — routing.yaml always takes precedence
- `condition` field: optional unvalidated string, marked with `"x-note": "Evaluated by C3 Composer, inert in C1"`
- `count` field: string pattern `"N"` or `"N-M"` (C3 may split to `min_count`/`max_count` integers later)

```
Top-level required: version, stages
Top-level optional: defaults, companions

defaults:
  budget_allocation: enum [proportional, fixed, uncapped]
  gate_mode: enum [enforce, shadow, off]
  model_routing: string (path reference)
  capability_mode: enum [enforce, shadow, off]

stages.<name>: (additionalProperties: true)
  description: string (required)
  phases: array of strings (required)
  requires:
    capabilities: array of strings
    tools: array of strings
  artifacts:
    <name>:
      type: enum [markdown, json, git_diff, test_output, verdict_json, git_commit]
      path_pattern: string (optional)
      required: boolean
  gates:
    <name>:
      type: enum [artifact_reviewed, command, phase_completed, verdict_clean]
      disabled: boolean (optional — for project overrides to remove default gates)
      (type-specific fields per gate type)
  budget:
    share: integer 0-100
    min_tokens: integer >= 0
    model_tier_hint: enum [haiku, sonnet, opus, oracle, codex]
  agents:
    required: array of agent_spec (additionalProperties: true)
    optional: array of agent_spec (additionalProperties: true)

agent_spec:
  role: string (required)
  description: string
  model_tier: enum [haiku, sonnet, opus, oracle, codex]
  count: string pattern "N" or "N-M" (default "1")
  condition: string (optional, unvalidated — C3 dependency)

companions.<name>: (additionalProperties: true)
  source: enum [central, self-declared] (default: central)
  provides: array of strings (abstract capabilities)

Gate type-specific fields:
  artifact_reviewed: artifact (string), min_agents (int), max_p0_findings (int), max_p1_findings (int)
  command: command (string), exit_code (int)
  phase_completed: phase (string)
  verdict_clean: max_needs_attention (int)
```

**Gate commands must be idempotent and read-only** — documented in schema description.

### Task 1.2: Default `agency-spec.yaml`

**File:** `os/clavain/config/agency-spec.yaml`

Budget allocation:
- discover: 10%, min 2000
- design: 25%, min 5000
- build: 40%, min 10000
- ship: 20%, min 5000
- reflect: 5%, min 1000

Shares sum to 100%. Min tokens sum to 23000 — documented as the floor for meaningful per-stage budgets.

Each stage declares: description, phases, requires (capabilities + tools), artifacts, gates, budget, agents (required + optional).

---

## Batch 2: Loader Library

### Task 2.1: `lib-spec.sh`

**File:** `os/clavain/hooks/lib-spec.sh`

Prefix: `spec_*` (public), `_spec_*` (private). **Must NOT use `set -euo pipefail`** — sourced by hook entry points.

```bash
# Public functions:
spec_load()                        # Load + validate + cache as JSON
spec_get_stage <stage>             # Stage config as JSON
spec_get_gate <stage> <gate_name>  # Gate config as JSON
spec_get_stage_gates <stage>       # All gates for a stage as JSON
spec_get_default <key>             # Top-level defaults value
spec_get_budget <stage>            # {share, min_tokens, model_tier_hint}
spec_get_agents <stage>            # {required: [...], optional: [...]}
spec_get_companion <name>          # Companion config as JSON
spec_available                     # Returns 0 if loaded=ok, 1 otherwise
spec_invalidate_cache              # Force reload on next spec_load call
```

**Cache state machine:**
```
_SPEC_LOADED=""         → never loaded
_SPEC_LOADED="ok"       → loaded successfully, _SPEC_JSON is valid
_SPEC_LOADED="failed"   → load attempted, failed. _SPEC_JSON is empty
_SPEC_LOADED="fallback" → no spec file found. Functions return hardcoded defaults
```

**Critical invariant:** Set `_SPEC_JSON` first, then `_SPEC_LOADED="ok"`. If Python call fails, set `_SPEC_LOADED="failed"`. Never set the guard before the data.

**Query pattern:** All field extraction uses `jq` on `_SPEC_JSON`. No Python subprocess for reads.

**Spec resolution order:**
1. Project override: `${PROJECT_DIR}/.clavain/agency-spec.yaml`
2. Default: `${CLAVAIN_DIR}/config/agency-spec.yaml`
3. Neither: `_SPEC_LOADED=fallback`

**Deep merge semantics (documented in header):**
- Arrays: wholesale replace (project list replaces default list entirely)
- Dicts: recursive key-merge (project keys override matching default keys; unmatched default keys survive)
- Null values: ignored (not treated as deletion)
- Deletion: set `disabled: true` on gates; for other fields, override with an empty value

**Cache invalidation:** `spec_invalidate_cache` clears `_SPEC_LOADED` and `_SPEC_JSON`. Automatically called by `sprint_set_artifact` when artifact path matches `*agency-spec.yaml`. Optional mtime check on `spec_load` (compare `_SPEC_MTIME` with `stat -c %Y`).

**Error visibility:** All warnings use `echo "spec: <message>" >&2` prefix for greppability.

### Task 2.2: Python Helper Script

**File:** `os/clavain/scripts/agency-spec-helper.py`

Two subcommands only (no `query` — use jq):

1. **`load <spec_path> [override_path]`** — Read YAML, merge override if provided, normalize budget shares, output compact JSON
2. **`validate <spec_path> <schema_path>`** — Validate against JSON Schema, exit 0/1, errors to stderr

**Budget normalization on load:** If shares don't sum to 100, scale proportionally. Log original vs normalized. If `sum(min_tokens)` exceeds a configurable floor (default 50000), warn.

**jsonschema dependency:** Check at runtime. If absent, skip validation, warn. PyYAML is required (available in test venv).

Target: <100 lines. Pure data transform.

---

## Batch 3: Integration (parallel tasks)

### Task 3.1: Data-Driven Gate Enforcement (F4)

**File:** `os/clavain/hooks/lib-sprint.sh` — modify `enforce_gate()`, add helpers

**New `enforce_gate` — ic gates are mandatory precondition, spec gates are additive:**

```bash
enforce_gate() {
    local bead_id="$1" target_phase="$2" artifact_path="${3:-}"

    # Check gate mode from agency spec
    local gate_mode
    gate_mode=$(spec_get_default "gate_mode") || gate_mode="enforce"
    [[ "$gate_mode" == "off" ]] && return 0

    # ALWAYS run ic gate check first (existing invariant — never bypassed)
    local run_id
    run_id=$(_sprint_resolve_run_id "$bead_id") || return 0
    if ! intercore_gate_check "$run_id"; then
        return 1  # ic gate blocked — spec gates cannot override
    fi

    # Additionally check spec-defined gates if spec loaded successfully
    if ! spec_available; then
        return 0  # No spec — ic gate passed, we're done
    fi

    local stage
    stage=$(_sprint_phase_to_stage "$target_phase")
    local gates_json
    gates_json=$(spec_get_stage_gates "$stage") || return 0

    local has_gates
    has_gates=$(echo "$gates_json" | jq 'length > 0' 2>/dev/null) || has_gates="false"
    [[ "$has_gates" != "true" ]] && return 0

    if [[ "$gate_mode" == "shadow" ]]; then
        _sprint_evaluate_spec_gates "$gates_json" "$bead_id" "$target_phase" "$artifact_path" "shadow" || true
        return 0  # Shadow: always pass
    fi

    _sprint_evaluate_spec_gates "$gates_json" "$bead_id" "$target_phase" "$artifact_path" "enforce"
}
```

**`_sprint_evaluate_spec_gates`** — iterates gate entries, dispatches by type:
- `artifact_reviewed` — check sprint artifact exists + review verdict count >= min_agents
- `command` — run command, check exit_code (must be idempotent/read-only)
- `phase_completed` — check phase completion state
- `verdict_clean` — check verdict files for max_needs_attention threshold
- Any gate with `disabled: true` — skip
- On internal error: log to stderr, return 0 (fail-open, same as existing convention)

**`_sprint_phase_to_stage`** — maps phase names to macro-stage names:
```bash
_sprint_phase_to_stage() {
    case "$1" in
        brainstorm) echo "discover" ;;
        brainstorm-reviewed|strategized|planned|plan-reviewed) echo "design" ;;
        executing) echo "build" ;;
        shipping) echo "ship" ;;
        reflect) echo "reflect" ;;
        done) echo "done" ;;
        *) echo "unknown" ;;
    esac
}
```

### Task 3.2: Per-Stage Budget Allocation (F5)

**File:** `os/clavain/hooks/lib-sprint.sh` — add budget functions

**New functions (all must define):**

```bash
# Get total budget for a sprint (reads token_budget from sprint state)
sprint_budget_total() {
    local sprint_id="$1"
    [[ -z "$sprint_id" ]] && { echo "0"; return 0; }
    local state
    state=$(sprint_read_state "$sprint_id") || { echo "0"; return 0; }
    local budget
    budget=$(echo "$state" | jq -r '.token_budget // 0' 2>/dev/null) || budget="0"
    [[ "$budget" == "null" ]] && budget="0"
    echo "$budget"
}

# Get allocated budget for a stage
sprint_budget_stage() {
    local sprint_id="$1" stage="$2"
    local total_budget
    total_budget=$(sprint_budget_total "$sprint_id") || { echo "0"; return 0; }
    [[ "$total_budget" == "0" || -z "$total_budget" ]] && { echo "0"; return 0; }

    local stage_budget_json
    stage_budget_json=$(spec_get_budget "$stage") || { echo "$total_budget"; return 0; }
    local share min_tokens
    share=$(echo "$stage_budget_json" | jq -r '.share // 20')
    min_tokens=$(echo "$stage_budget_json" | jq -r '.min_tokens // 1000')

    # Guard non-numeric values
    [[ "$share" =~ ^[0-9]+$ ]] || share=20
    [[ "$min_tokens" =~ ^[0-9]+$ ]] || min_tokens=1000

    local allocated
    allocated=$(( total_budget * share / 100 ))
    [[ $allocated -lt $min_tokens ]] && allocated=$min_tokens

    # Cap: if all stages' min_tokens push total above budget, scale down
    local uncapped_sum
    uncapped_sum=$(_sprint_sum_all_stage_allocations "$sprint_id")
    if [[ $uncapped_sum -gt $total_budget && $uncapped_sum -gt 0 ]]; then
        allocated=$(( allocated * total_budget / uncapped_sum ))
    fi

    echo "$allocated"
}

# Sum tokens spent across all phases belonging to a stage
sprint_stage_tokens_spent() {
    local sprint_id="$1" stage="$2"
    local run_id
    run_id=$(_sprint_resolve_run_id "$sprint_id") || { echo "0"; return 0; }
    local phase_tokens_json
    phase_tokens_json=$(intercore_state_get "phase_tokens" "$run_id" 2>/dev/null) || phase_tokens_json="{}"
    local total=0
    while IFS= read -r phase; do
        [[ -z "$phase" ]] && continue
        local phase_stage
        phase_stage=$(_sprint_phase_to_stage "$phase")
        if [[ "$phase_stage" == "$stage" ]]; then
            local phase_total
            phase_total=$(echo "$phase_tokens_json" | jq -r \
                --arg p "$phase" '(.[($p)].input_tokens // 0) + (.[($p)].output_tokens // 0)' 2>/dev/null) || phase_total=0
            [[ "$phase_total" =~ ^[0-9]+$ ]] || phase_total=0
            total=$(( total + phase_total ))
        fi
    done <<< "$(echo "$phase_tokens_json" | jq -r 'keys[]' 2>/dev/null)"
    echo "$total"
}

# Get remaining budget for a stage
sprint_budget_stage_remaining() {
    local sprint_id="$1" stage="$2"
    local allocated spent remaining
    allocated=$(sprint_budget_stage "$sprint_id" "$stage")
    spent=$(sprint_stage_tokens_spent "$sprint_id" "$stage")
    [[ "$allocated" =~ ^[0-9]+$ ]] || allocated=0
    [[ "$spent" =~ ^[0-9]+$ ]] || spent=0
    remaining=$(( allocated - spent ))
    [[ $remaining -lt 0 ]] && remaining=0
    echo "$remaining"
}

# Check and warn if stage budget exceeded
sprint_budget_stage_check() {
    local sprint_id="$1" stage="$2"
    local remaining
    remaining=$(sprint_budget_stage_remaining "$sprint_id" "$stage")
    if [[ "$remaining" -le 0 ]]; then
        echo "budget_exceeded|$stage|stage budget depleted" >&2
        return 1
    fi
    return 0
}

# Private: sum allocations for all 5 stages (for cap calculation)
_sprint_sum_all_stage_allocations() {
    local sprint_id="$1"
    local total_budget
    total_budget=$(sprint_budget_total "$sprint_id")
    local sum=0
    for stage in discover design build ship reflect; do
        local stage_json share min_tokens alloc
        stage_json=$(spec_get_budget "$stage" 2>/dev/null) || continue
        share=$(echo "$stage_json" | jq -r '.share // 20')
        min_tokens=$(echo "$stage_json" | jq -r '.min_tokens // 1000')
        [[ "$share" =~ ^[0-9]+$ ]] || share=20
        [[ "$min_tokens" =~ ^[0-9]+$ ]] || min_tokens=1000
        alloc=$(( total_budget * share / 100 ))
        [[ $alloc -lt $min_tokens ]] && alloc=$min_tokens
        sum=$(( sum + alloc ))
    done
    echo "$sum"
}
```

### Task 3.3: Companion Capability Declarations (F6)

**File:** `os/clavain/config/agency-spec.yaml` — add `companions:` section

**Scoped narrowly for C1:** Only `provides` array (abstract capabilities) and `source: central`. Per-agent kernel/filesystem capability detail deferred to C2 self-declaration.

```yaml
companions:
  interflux:
    source: central
    provides: [multi_perspective, artifact_generation, domain_review]
  interlock:
    source: central
    provides: [multi_agent_coordination, file_reservation, conflict_detection]
  interphase:
    source: central
    provides: [phase_tracking, gate_validation]
  interpeer:
    source: central
    provides: [cross_ai_review]
  interpath:
    source: central
    provides: [artifact_generation, roadmap_generation]
  interwatch:
    source: central
    provides: [drift_detection, freshness_monitoring]
  intertest:
    source: central
    provides: [test_discipline, debugging, verification]
  intersynth:
    source: central
    provides: [verdict_aggregation, multi_agent_synthesis]
```

Add `spec_get_companion()` to `lib-spec.sh`.

Shadow-mode dispatch validation: `spec_validate_dispatch()` logs warning if dispatched agent isn't in spec roster for current stage. Stderr only.

---

## File Summary

| File | Action | Feature |
|------|--------|---------|
| `os/clavain/config/agency-spec.schema.json` | Create | F1 |
| `os/clavain/config/agency-spec.yaml` | Create | F2, F6 |
| `os/clavain/hooks/lib-spec.sh` | Create | F3 |
| `os/clavain/scripts/agency-spec-helper.py` | Create | F3 |
| `os/clavain/hooks/lib-sprint.sh` | Modify | F4, F5 |

Total: 4 new files, 1 modified file.

---

## Testing Strategy

1. **Schema validation:** Valid spec passes, malformed spec fails with clear error
2. **Loader:** `spec_get_stage design` returns expected JSON from default spec
3. **Override merge:** Project override changes `build.budget.share`, verify merge. Array field in override replaces default. Dict field merges.
4. **Gate tests (per type):**
   - `command` gate in enforce mode — passes/fails based on exit code
   - `artifact_reviewed` gate — passes when artifact exists with min review count
   - `phase_completed` gate — passes when phase recorded as complete
   - `verdict_clean` gate — passes when attention count below threshold
   - Shadow mode — all gate types always return 0
   - `gate_mode: off` — early exit, no evaluation
5. **Gate conjunction:** When both spec gates and ic gates exist, both must pass. Mock ic gate to return 1 — verify enforce_gate returns 1 regardless of spec gate result.
6. **Cache state machine:** Load success → ok, load failure → failed, no file → fallback. After invalidate_cache, next load retries.
7. **Budget:** Set 100k budget, verify stage splits (10k/25k/40k/20k/5k). Verify min_tokens floor. Verify overallocation cap when min_tokens sum > budget.
8. **Budget functions defined:** `sprint_budget_total`, `sprint_stage_tokens_spent`, `sprint_budget_stage`, `sprint_budget_stage_remaining` — all callable, no phantom functions.
9. **Companion:** `spec_get_companion interflux` returns expected provides array
10. **Structural:** Python helper at `scripts/agency-spec-helper.py` covered by existing `test_scripts.py`

Tests in `os/clavain/tests/`.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Python helper startup latency | Cache JSON in bash variable; helper called once per `spec_load` |
| jsonschema not installed | Degrade gracefully — skip validation, log `spec: jsonschema not available` |
| Spec gates vs ic gates ambiguity | ic gates run first as precondition; spec gates are additive only |
| Budget overallocation via min_tokens | Normalize shares at load; cap allocations at runtime |
| Spec cache staleness mid-session | Mtime check on `spec_load`; auto-invalidate on `sprint_set_artifact` |
| Companion declarations drift from reality | C1 declares only abstract `provides`; C2 adds detail via self-declaration |
