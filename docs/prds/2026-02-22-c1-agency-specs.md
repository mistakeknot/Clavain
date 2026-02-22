# PRD: C1 Agency Specs — Declarative Per-Stage Config

**Bead:** iv-ssck
**Parent bead:** iv-asfy

## Problem

Clavain's sprint pipeline encodes stage behavior (agents, models, gates, budgets) implicitly across skill files, hooks, and hardcoded logic. Adding a review agent, changing a gate rule, or adjusting budget allocation requires editing code in multiple places. This blocks the Composer (C3), fleet registry (C2), and self-building loop (C5) — all of which need a machine-readable description of what each stage requires.

## Solution

A YAML-based agency spec (`agency-spec.yaml`) that declares what each macro-stage (Discover, Design, Build, Ship, Reflect) needs. The sprint pipeline reads this spec instead of hardcoding behavior. Companion plugins declare their capabilities centrally. Gates, budgets, and agent rosters become data-driven.

## Features

### F1: YAML Schema Definition
**What:** Define a JSON Schema that validates agency-spec.yaml structure.
**Acceptance criteria:**
- [ ] JSON Schema file exists at `os/clavain/config/agency-spec.schema.json`
- [ ] Schema validates: top-level structure (version, defaults, stages, companions)
- [ ] Schema validates: stage fields (description, phases, requires, artifacts, gates, budget, agents)
- [ ] Schema validates: companion fields (capabilities, provides, agents)
- [ ] Schema rejects malformed specs with clear error messages

### F2: Default Agency Spec
**What:** Write the canonical `agency-spec.yaml` encoding current implicit behavior for all 5 macro-stages.
**Acceptance criteria:**
- [ ] File exists at `os/clavain/config/agency-spec.yaml`
- [ ] All 5 stages defined: discover, design, build, ship, reflect
- [ ] Each stage has: description, phases, requires, artifacts, gates, budget, agents
- [ ] Budget shares sum to 100% across stages
- [ ] Agent rosters match current sprint pipeline behavior (what's actually dispatched today)
- [ ] Passes JSON Schema validation (F1)

### F3: Spec Loader Library
**What:** A bash library (`lib-agency.sh`) that loads, validates, and queries the agency spec.
**Acceptance criteria:**
- [ ] `agency_load_spec` loads the spec from config path, with project-level override support
- [ ] `agency_get_stage <stage>` returns a stage's full config as JSON
- [ ] `agency_get_gate <stage> <gate_name>` returns a gate's config
- [ ] `agency_get_budget <stage>` returns budget share and min_tokens
- [ ] `agency_get_agents <stage>` returns required and optional agent rosters
- [ ] Falls back gracefully when no spec exists (returns defaults matching current behavior)
- [ ] Validates spec against JSON Schema on load; warns on invalid spec, does not crash

### F4: Data-Driven Gate Enforcement
**What:** `enforce_gate` in `lib-sprint.sh` reads gate definitions from the agency spec instead of hardcoded logic.
**Acceptance criteria:**
- [ ] `enforce_gate` calls `agency_get_gate` to get gate config
- [ ] Supports gate types: `artifact_reviewed`, `command`, `phase_completed`, `verdict_clean`
- [ ] Gate behavior matches current hardcoded behavior when spec encodes current rules
- [ ] When spec is absent, falls back to current hardcoded behavior (backward compatible)
- [ ] Gate mode respects `defaults.gate_mode` (enforce/shadow/off)

### F5: Per-Stage Budget Allocation
**What:** Budget splits across stages based on spec percentages, visible in sprint summary.
**Acceptance criteria:**
- [ ] `sprint_budget_remaining` can report per-stage budget (not just per-run)
- [ ] Budget allocation computed at sprint start from run total and stage shares
- [ ] `budget.warning` emits when a stage exceeds its allocated share
- [ ] Sprint summary shows per-stage budget usage
- [ ] When spec is absent, falls back to current behavior (single run-level budget)

### F6: Companion Capability Declarations
**What:** Declare capabilities for the top 8 companions in the agency spec's `companions:` section.
**Acceptance criteria:**
- [ ] At least 8 companions declared: interflux, interlock, interphase, interpeer, interpath, interwatch, intertest, intersynth
- [ ] Each companion has: capabilities (kernel, filesystem, external), provides (abstract capabilities), agents (with specialization, default_model, cost_profile)
- [ ] `agency_get_companion <name>` returns a companion's capability declaration
- [ ] Shadow-mode validation: log (don't block) when agent dispatch doesn't match spec roster
- [ ] Capability data is structured for future C2 fleet registry consumption

## Non-goals

- **Enforcing capability restrictions** — Declare only, shadow-validate. Enforcement is post-C2.
- **Dynamic spec modification** — The spec is static config. Interspect-proposed changes are C5 territory.
- **Composer integration** — C3 will consume the spec, but building the Composer is out of scope.
- **Self-declaration protocol** — Companions declaring their own capabilities in plugin.json is a C2 concern. C1 uses central declaration.
- **Custom gate type plugin mechanism** — The four built-in gate types cover current needs.

## Dependencies

- `routing.yaml` (B1/B2) — exists, agency spec references but does not replace it
- `lib-sprint.sh` — existing sprint library, F3/F4 modify it
- `python3` + PyYAML — for YAML parsing in bash (`yq` is not installed; Python + PyYAML + jsonschema are available)

## Open Questions

1. **YAML parser:** ~~`yq` is installed on this server.~~ `yq` is NOT available. **Decision: use `python3` + PyYAML** via a helper script (`scripts/agency-spec-helper.py`). Called once per `spec_load()`; all subsequent queries use `jq` on cached JSON.
2. **Deep merge semantics for project overrides:** Arrays replace, dicts merge recursively. Set `disabled: true` on gates to remove defaults. Implemented in Python helper's `deep_merge()`.
3. **Capability vocabulary formalization:** Start with free-form strings, add enum validation in a follow-up when vocabulary stabilizes through usage.
