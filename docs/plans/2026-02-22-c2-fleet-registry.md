# Plan: C2 — Agent Fleet Registry

**Sprint:** iv-i1i3
**Parent bead:** iv-lx00
**Depends on:** C1 agency specs (iv-asfy, done), B1 static routing (iv-dd9q, done)
**Blocks:** C3 Composer (iv-240m)
**Reviewed by:** fd-architecture, fd-correctness, fd-quality (2026-02-22)

---

## Context

Clavain's agency-spec.yaml (C1) declares what each stage *needs* — roles, capabilities, model tiers. But there's no registry of what agents *exist* and what they can do. The Composer (C3) needs a data source to match specs to agents. That's the fleet registry.

**Existing data sources:**
- `os/clavain/agents/{review,workflow}/*.md` — 4 clavain agents with YAML frontmatter
- `interverse/interflux/agents/{review,research}/*.md` — ~17 interflux agents
- `.claude/agents/*.md` — 10 project-local agents (fd-cli-ux, fd-dispatch-efficiency, etc.)
- `os/clavain/config/agency-spec.yaml` — companion capability declarations
- `os/clavain/config/routing.yaml` — model tier definitions and costs
- `os/clavain/config/agency/*.yaml` — per-stage agent dispatch configs

**Tool dependency:** yq v4.52.4 (installed at `~/.local/bin/yq`)

---

## Feature Breakdown

### F1: Fleet registry YAML schema + seed data (iv-jd91)

**File:** `os/clavain/config/fleet-registry.yaml`
**Schema:** `os/clavain/config/fleet-registry.schema.json` (JSON Schema draft-07)

Each agent entry:

```yaml
version: "1.0"

# Capability vocabulary — closed set derived from agency-spec.yaml companions.
# Schema enforces this enum. Add new capabilities here first, then reference in agents.
capability_vocabulary:
  - domain_review
  - multi_perspective
  - artifact_generation
  - multi_agent_coordination
  - file_reservation
  - conflict_detection
  - phase_tracking
  - gate_validation
  - cross_ai_review
  - roadmap_generation
  - drift_detection
  - freshness_monitoring
  - test_discipline
  - debugging
  - verification
  - verdict_aggregation
  - multi_agent_synthesis

agents:
  fd-architecture:
    source: interflux                    # plugin that owns this agent (or "local" for .claude/agents)
    category: review                     # review | research | workflow | synthesis
    description: "Architecture & design reviewer — evaluates module boundaries, coupling, design patterns"
    capabilities:                        # from capability_vocabulary above
      - domain_review
      - multi_perspective
    roles:                               # agency-spec role labels this agent can fulfill
      - fd-architecture
    runtime:
      mode: subagent                     # subagent | command | codex
      subagent_type: "interflux:review:fd-architecture"
    models:
      preferred: sonnet
      supported: [haiku, sonnet, opus]
    tools:
      - Read
      - Grep
      - Glob
      - Bash
    cold_start_tokens: 800               # integer — estimated prompt overhead before useful output
    tags: []                             # free-form tags for future filtering
```

**Fields added per review:**
- `roles: []` — agency-spec dispatches by role labels (M1). For concrete agents like fd-architecture, role = agent ID. For abstract roles (brainstorm-facilitator, strategist), roles must be declared explicitly.
- `runtime` block — `mode` + invocation details (M2). Modes: `subagent` (Claude Code Task tool), `command` (slash command invocation), `codex` (Codex CLI dispatch).
- `capability_vocabulary` — top-level closed set derived from agency-spec.yaml (S5). Schema enforces capabilities are drawn from this list.

**Tasks (revised order per review S4):**
1. **Capability audit** — extract the closed capability set from agency-spec.yaml `companions.*.provides` and `stages.*.requires.capabilities`. Produce the `capability_vocabulary` list.
2. **Write JSON schema** (draft-07, matching agency-spec.schema.json). Enforce capability enum. Validate with `python3 -m jsonschema` via `uv run` (not ajv — consistent with existing project tooling).
3. **Hand-author seed data** for all ~31 known agents:
   - 4 clavain agents (data-migration-expert, plan-reviewer, bug-reproduction-validator, pr-comment-resolver)
   - 12 interflux review agents (fd-architecture through fd-systems)
   - 5 interflux research agents (best-practices-researcher through repo-research-analyst)
   - ~10 `.claude/agents` project-local agents (source: `local`)
4. Cross-reference: every capability in agency-spec `requires` must be provided by at least one agent.

**Acceptance:** `yq '.agents | keys | length' fleet-registry.yaml` returns 31+. `yq -o=json fleet-registry.yaml | python3 -m jsonschema --instance /dev/stdin fleet-registry.schema.json` passes. `cold_start_tokens` survives YAML→JSON round-trip as integer.

---

### F2: scan-fleet.sh generator script (iv-z7wm)

**File:** `os/clavain/scripts/scan-fleet.sh`
**Header:** `set -euo pipefail`

Auto-discovers agents by scanning:
1. Agent .md files in `*/agents/**/*.md` — parse YAML frontmatter
2. plugin.json manifests — extract plugin name as `source`
3. agency-spec.yaml companion declarations — map capabilities

**Frontmatter extraction** (corrected per review M5):
```bash
# Extract content between --- delimiters, excluding delimiters themselves
awk '/^---$/{f=!f; next} f{print}' "$agent_file" | head -50
```
NOT `sed -n '/^---$/,/^---$/p'` which includes delimiters and breaks yq parsing.

After extraction, validate non-empty `name`:
```bash
name=$(yq '.name // ""' "$tmpfile" 2>/dev/null) || { warn "Failed to parse: $file"; continue; }
[[ -z "$name" ]] && { name="$(basename "$file" .md)"; warn "No name in frontmatter, using filename: $name"; }
```

**Merge semantics** (revised per review M3):
- **Generated (overwritten on every scan):** `source`, `category`, `runtime`
- **Seed defaults (written on first discovery, preserved thereafter):** `description`, `capabilities`, `roles`, `models`, `cold_start_tokens`, `tags`, `tools`

Category assignment:
- Plugin agents with `agents/{category}/name.md` layout: category from directory name
- `.claude/agents/*.md` (flat layout): requires manual category or defaults to `workflow`

subagent_type generation:
- Plugin agents: `{plugin-name}:{category}:{agent-name}`
- Local agents (`.claude/agents/`): just the agent name (Claude Code convention)

**Stale entry handling** (per review M4):
Agents in the existing registry not found during scan get an `orphaned_at: <ISO-date>` field added (matches `critical-patterns.md` pattern). Consumers must check `orphaned_at` absence before dispatching. `--dry-run` output shows three sections: **added**, **updated**, **orphaned**.

**Atomic writes** (per review S6):
`--in-place` writes to a temp file then `mv`:
```bash
tmpfile="$(mktemp "${fleet_registry_path}.XXXXXX")"
generate_registry > "$tmpfile"
mv "$tmpfile" "$fleet_registry_path"
```

**Tasks:**
1. Write scan-fleet.sh with `set -euo pipefail`
2. Implement frontmatter extraction with awk + yq (error-wrapped)
3. Implement merge logic with seed-default semantics
4. Implement orphaned_at tombstoning for stale entries
5. `--dry-run` flag with added/updated/orphaned sections
6. `--include-local` flag for `.claude/agents/` (off by default)
7. Atomic temp-file+mv for `--in-place`

**Known limitation:** Agent renames (fd-old → fd-new) orphan the old entry's curated fields. No automatic migration. `--dry-run` makes this visible by showing the old entry as orphaned and new entry as added in the same category.

**Acceptance:** `scan-fleet.sh` produces valid fleet-registry.yaml. `scan-fleet.sh --dry-run` shows correct added/updated/orphaned sections.

---

### F3: lib-fleet.sh query library (iv-tx83)

**File:** `os/clavain/scripts/lib-fleet.sh`

Shell library sourced by sprint pipeline, flux-drive triage, and future C3 Composer. Uses yq for all queries. No `set -euo pipefail` (sourced library — strict mode would exit the parent shell).

**yq dependency check** (per review S2):
```bash
_fleet_require_yq() {
  if ! command -v yq >/dev/null 2>&1; then
    [[ -x "${HOME}/.local/bin/yq" ]] && export PATH="${HOME}/.local/bin:${PATH}" || {
      echo "lib-fleet: yq not found. Install: https://github.com/mikefarah/yq" >&2; return 1
    }
  fi
  local ver; ver="$(yq --version 2>&1 | grep -oE 'v[0-9]+' | head -1)"
  [[ "$ver" == "v4" ]] || { echo "lib-fleet: yq v4 required (found ${ver:-unknown})" >&2; return 1; }
}
```

**Guard pattern** (revised per review M6):
```bash
# Guard compares cached path — invalidates if config path changed
_fleet_find_config  # resolves to _FLEET_RESOLVED_PATH
if [[ "${_FLEET_LOADED_PATH:-}" == "$_FLEET_RESOLVED_PATH" ]]; then
  return 0  # same config, already loaded
fi
# ... load and cache ...
_FLEET_LOADED_PATH="$_FLEET_RESOLVED_PATH"
```

**Config resolution** (per review S1):
```bash
# Resolution order (same as lib-routing.sh):
#   1. CLAVAIN_FLEET_REGISTRY env var (for testing/override)
#   2. Script-relative: ../config/fleet-registry.yaml
#   3. CLAVAIN_SOURCE_DIR/config/fleet-registry.yaml
#   4. Plugin cache: ~/.claude/plugins/cache/*/clavain/*/config/fleet-registry.yaml
```

**yq invocation safety** (per review S3):
- Pass user values via `--arg`, never string interpolation
- Numeric comparisons use explicit `tonumber` casting
- Check `$_FLEET_REGISTRY_PATH` before every yq call; return 1 if absent

```bash
fleet_by_capability() {
  [[ -z "${_FLEET_REGISTRY_PATH:-}" ]] && { echo "lib-fleet: no registry loaded" >&2; return 1; }
  yq --arg cap "$1" '.agents | to_entries[] | select(.value.capabilities[] == $cap) | .key' "$_FLEET_REGISTRY_PATH"
}

fleet_within_budget() {
  local max="$1" cat="${2:-}"
  yq --arg max "$max" --arg cat "$cat" \
    '.agents | to_entries[] | select((.value.cold_start_tokens | tonumber) <= ($max | tonumber)) | select($cat == "" or .value.category == $cat) | .key' \
    "$_FLEET_REGISTRY_PATH"
}
```

**Public API:**

```bash
source lib-fleet.sh

# Basic queries — output: newline-separated agent IDs
fleet_list                                  # all agent IDs (excludes orphaned)
fleet_get <agent_id>                        # full YAML block (without agent ID key)
fleet_by_category <category>                # agents in category
fleet_by_capability <capability>            # agents providing a capability
fleet_by_source <plugin>                    # agents from a plugin
fleet_by_role <role>                        # agents that can fulfill a role

# Cost/budget queries
fleet_cost_estimate <agent_id>              # cold_start_tokens (integer to stdout)
fleet_within_budget <max_tokens> [category] # agents whose cold_start <= budget

# Coverage check
fleet_check_coverage <capability...>
# Returns 0 if ALL listed capabilities are covered by at least one non-orphaned agent.
# Returns 1 if ANY capability has no covering agent.
# Prints uncovered capabilities to stderr.

# Output control
# Set FLEET_FORMAT=json for JSON output from fleet_get.
# List functions always output newline-separated IDs regardless of FLEET_FORMAT.
```

**Tasks:**
1. Write lib-fleet.sh with config-finding logic, yq require/version check
2. Implement path-aware guard (invalidates on config path change)
3. Implement all 9 query functions (added `fleet_by_role`)
4. All yq calls use `--arg` for user values, `tonumber` for numerics
5. `fleet_list` and all `fleet_by_*` exclude agents with `orphaned_at` field

**Acceptance:** All 9 functions return correct results against the seed registry. Functions fail clearly when yq is absent or registry is missing.

---

### F4: Fleet registry tests (iv-8g3y)

**File:** `os/clavain/tests/shell/test_fleet.bats`
**Fixtures:** `os/clavain/tests/fixtures/fleet/`

**Test setup pattern** (per review M6, following test_routing.bats):
```bash
setup() {
    load test_helper
    SCRIPTS_DIR="$BATS_TEST_DIRNAME/../../scripts"
    TEST_DIR="$(mktemp -d)"
    # Critical: reset guard so each test starts clean
    unset _FLEET_LOADED_PATH
    unset _FLEET_REGISTRY_PATH
}

_source_fleet() {
    unset _FLEET_LOADED_PATH
    export CLAVAIN_FLEET_REGISTRY="$TEST_DIR/fleet-registry.yaml"
    source "$SCRIPTS_DIR/lib-fleet.sh"
}
```

**Test plan (expanded per reviews):**

1. **Schema tests:**
   - Fixture registry validates against JSON schema via `yq -o=json | python3 -m jsonschema`
   - `cold_start_tokens` survives YAML→JSON round-trip as integer (not string)

2. **scan-fleet.sh tests:**
   - Mock plugin directory with 3 agents → generates valid registry
   - Merge mode preserves seed-default fields (description, capabilities, models, etc.)
   - Handles missing frontmatter gracefully (falls back to filename)
   - **Ghost agent test:** Registry has 3 agents, scan finds 2 → third gets `orphaned_at`
   - `--dry-run` shows added/updated/orphaned sections
   - Atomic write: `--in-place` creates temp file then mv (verify no partial writes)

3. **lib-fleet.sh tests:**
   - `fleet_list` returns all non-orphaned agents from fixture
   - `fleet_list` on empty `agents: {}` returns exit 0 with empty output
   - `fleet_get` returns correct agent block (without ID key)
   - `fleet_by_category review` returns only review agents
   - `fleet_by_capability domain_review` returns agents with that capability
   - `fleet_by_source interflux` returns correct subset
   - `fleet_by_role strategist` returns agents with that role
   - `fleet_cost_estimate` returns cold_start_tokens for a known agent
   - `fleet_within_budget 500` excludes agents with cold_start > 500
   - `fleet_check_coverage covered_cap` → exit 0
   - `fleet_check_coverage covered_cap missing_cap` → exit 1, prints `missing_cap`
   - `FLEET_FORMAT=json fleet_get` produces valid JSON
   - Orphaned agents excluded from all query functions

4. **Environmental tests:**
   - lib-fleet fails with clear message when yq is absent (PATH manipulation)
   - lib-fleet fails with clear message when yq is v3 (mock yq wrapper)
   - Guard invalidates when `CLAVAIN_FLEET_REGISTRY` changes between sources
   - Subshell invocation: `run bash -c "source lib-fleet.sh; fleet_list"` succeeds

**Fixture strategy:** fleet-registry.yaml with 6 agents (2 review, 2 research, 1 workflow, 1 orphaned) from 2 sources covering all query edge cases. Plus a mock plugin directory for scan-fleet.sh tests.

**Tasks:**
1. Create test fixtures (fleet-registry.yaml, mock plugin dir, mock agent .md files)
2. Write bats tests — all cases above
3. Add integration smoke test: run lib-fleet queries against real seeded fleet-registry.yaml (31 agents) to catch YAML encoding issues invisible in 6-agent fixtures
4. Verify all pass

**Acceptance:** `bats tests/shell/test_fleet.bats` — all green.

---

## Execution Order

```
F1 (capability audit → schema → seed data)
         ↓
F3 (lib-fleet.sh)  ←  needs schema + seed data to test against
         ↓
F3.5 (smoke test lib-fleet against real 31-agent registry)
         ↓
F2 (scan-fleet.sh)  ←  needs lib-fleet to validate output
         ↓
F4 (full test suite)
```

F1 internal order: capability audit first, then schema, then seed data (per review S4 — schema needs the capability enum from the audit).

## Non-goals

- **No yq migration of lib-routing.sh** — follow-up bead, not this sprint
- **No yq fallback parser** — lib-fleet.sh hard-depends on yq v4+; fail fast if absent
- **No C3 Composer integration** — this sprint builds the data layer, C3 consumes it later
- **No runtime cost tracking** — cold_start_tokens are static estimates; interstat integration is future work
- **No agent health/availability checks** — fleet registry is a static catalog, not a service mesh
- **No automatic rename migration** — agent renames orphan old entries; documented limitation

## Dependencies

- **yq v4.52.4** — installed at `~/.local/bin/yq`. lib-fleet.sh auto-discovers `~/.local/bin` if not in PATH. Version check at load time rejects v3.
- **bats-core 1.13** — installed at `/usr/bin/bats`
- **python3 + jsonschema** — for schema validation in tests. Install via `uv run`.

## Review Findings Incorporated

| # | Source | Finding | Resolution |
|---|--------|---------|------------|
| M1 | arch | Missing `roles` field | Added `roles: []` to schema |
| M2 | arch | Missing `runtime` block | Added `runtime: {mode, subagent_type}` |
| M3 | arch+quality | `description` should be curated, not generated | Moved to seed-default (preserved on merge) |
| M4 | correctness | Ghost agents silently preserved | `orphaned_at` tombstone + consumer exclusion |
| M5 | correctness+quality | Frontmatter sed pattern broken | Switched to awk; validate non-empty name |
| M6 | correctness | `_FLEET_LOADED` guard insufficient | Path-aware guard; tests unset in setup() |
| S1 | quality | Unnamed env var override | Named `CLAVAIN_FLEET_REGISTRY`; documented resolution order |
| S2 | quality | yq PATH/version risk | Auto-discover `~/.local/bin`; v4 version check |
| S3 | correctness | yq injection via string interpolation | `--arg` for all user values; `tonumber` for numerics |
| S4 | quality+correctness | Missing test cases | Added 8 additional test cases |
| S5 | arch | Capability string drift | `capability_vocabulary` with schema enum enforcement |
| S6 | quality | Non-atomic `--in-place` | Temp file + mv |
