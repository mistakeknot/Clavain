# C1: Agency Specs — Declarative Per-Stage Agent/Model/Tool Config
**Bead:** iv-ssck

**Date:** 2026-02-22
**Bead:** iv-asfy
**References:** [roadmap.md Track C](../roadmap.md), [clavain-vision.md](../clavain-vision.md), [pi_agent_rust lessons](2026-02-19-pi-agent-rust-lessons-brainstorm.md) section 2, [routing.yaml](../../config/routing.yaml)

---

## What We're Building

A YAML-based specification format that declares what each macro-stage (Discover, Design, Build, Ship, Reflect) needs: which agents to dispatch, which models to use, which tools are available, what artifacts are required, what gates must pass, and how budget is allocated. Today this knowledge is implicit — scattered across skill files, hooks, and hardcoded logic in `lib-sprint.sh`. Making it declarative enables the Composer (C3), the fleet registry (C2), and ultimately the self-building loop (C5).

## Why This Approach

### The Implicit Architecture Problem

Today's sprint pipeline has a hidden spec encoded in code:

| What | Where it lives today | Problem |
|------|---------------------|---------|
| Which agents run during review | `interflux` triage logic + `quality-gates` skill | Adding a new review agent requires editing multiple skills |
| Which model runs each agent | `routing.yaml` (phases) + plugin defaults | No connection between phase purpose and model choice |
| What artifacts are required per phase | Hardcoded in `sprint.md` instruction text | Can't validate programmatically, can't vary by project |
| Gate rules | `lib-sprint.sh` enforce_gate function | Gate logic is imperative, not declarative |
| Budget allocation | Per-run token budget, no per-phase granularity | Can't allocate 60% to Build and 10% to Reflect |
| Tool availability | Implicit — all tools available everywhere | No constraint on what a review agent can do vs a build agent |

The spec makes all of this explicit and machine-readable. The immediate consumer is the sprint pipeline itself — it reads the spec instead of hardcoding behavior. The future consumer is C3 (Composer), which matches specs to the fleet registry to optimize dispatch.

### Design Principles

1. **Descriptive, not prescriptive** — The spec says what a stage *needs* (capabilities, artifacts, quality), not *how* to achieve it. The Composer (C3) decides the how.

2. **Layered override** — Project-level specs override the default. Run-level overrides (e.g., `--budget=5000`) override project-level. This follows the existing routing.yaml pattern.

3. **Backward compatible** — When no spec exists, the sprint pipeline falls back to current behavior. The spec enhances, it doesn't gate.

4. **Capability declarations now, enforcement later** — Per the pi_agent_rust lesson: declare capabilities in the spec, validate in shadow mode, enforce only when data shows it's safe.

---

## The Spec Schema

### Top-Level Structure

```yaml
# agency-spec.yaml — default lives at os/clavain/config/agency-spec.yaml
# Project overrides at .clavain/agency-spec.yaml
version: "1"

defaults:
  budget_allocation: proportional  # proportional | fixed | uncapped
  gate_mode: enforce               # enforce | shadow | off
  model_routing: routing.yaml      # reference to routing config
  capability_mode: shadow          # enforce | shadow | off

stages:
  discover: { ... }
  design: { ... }
  build: { ... }
  ship: { ... }
  reflect: { ... }

companions:
  interflux: { ... }
  interlock: { ... }
  # ... capability declarations per companion
```

### Stage Spec

Each stage declares its intent, not its implementation:

```yaml
stages:
  design:
    description: "Strategy, specification, planning, and plan review"

    # Sub-phases within this stage
    phases:
      - brainstorm
      - brainstorm-reviewed
      - strategized
      - planned
      - plan-reviewed

    # What this stage needs to do (abstract capabilities)
    requires:
      capabilities:
        - deep_reasoning       # Strategy and system design
        - multi_perspective    # Plan review from multiple angles
        - cross_ai_review     # Oracle/GPT for design validation
        - artifact_generation  # PRD, plan docs

      tools:
        - file_read           # Read codebase for context
        - file_write          # Write plan/PRD documents
        - web_search          # Research during brainstorm
        - web_fetch           # Fetch docs during research

    # What this stage produces
    artifacts:
      brainstorm:
        type: markdown
        path_pattern: "docs/brainstorms/{date}-{slug}-brainstorm.md"
        required: true
      prd:
        type: markdown
        path_pattern: "docs/prds/{date}-{slug}.md"
        required: false  # Only for complex tasks
      plan:
        type: markdown
        path_pattern: "docs/plans/{date}-{slug}.md"
        required: true

    # Gates that must pass before advancing to next stage
    gates:
      plan_review:
        type: artifact_reviewed
        artifact: plan
        min_agents: 3
        max_p0_findings: 0
        max_p1_findings: 2

    # Budget allocation (percentage of run budget)
    budget:
      share: 25         # 25% of total run budget
      min_tokens: 5000   # Floor — even cheap runs get this
      model_preference: opus  # Preferred model tier for this stage

    # Agent roster — which agents CAN be dispatched here
    agents:
      required:
        - role: strategist
          description: "Deep reasoning for system design"
          model_tier: opus
        - role: plan_reviewer
          description: "Multi-perspective plan validation"
          count: 3-7  # Range — Composer picks within budget
          model_tier: sonnet  # Default, can be promoted
      optional:
        - role: cross_ai_reviewer
          description: "Oracle/GPT for design cross-validation"
          model_tier: oracle
          condition: "complexity >= 4"
```

### Companion Capability Declarations

Following pi_agent_rust's model, each companion declares what it can do:

```yaml
companions:
  interflux:
    capabilities:
      kernel:
        - events.tail
        - dispatch.spawn
        - dispatch.status
      filesystem:
        - read
        - write
      provides:
        - multi_perspective   # Plan/code review from multiple angles
        - artifact_generation # Synthesis reports
    agents:
      # Declares what each agent specializes in
      fd-architecture:
        specialization: [architecture, boundaries, patterns]
        default_model: sonnet
        cost_profile: medium
      fd-safety:
        specialization: [security, credentials, trust_boundaries]
        default_model: sonnet
        cost_profile: medium
      fd-correctness:
        specialization: [data_integrity, concurrency, async]
        default_model: opus
        cost_profile: high
      fd-quality:
        specialization: [naming, conventions, idioms]
        default_model: haiku
        cost_profile: low
      fd-performance:
        specialization: [bottlenecks, rendering, algorithms]
        default_model: sonnet
        cost_profile: medium
      fd-user-product:
        specialization: [user_flows, ux, product_reasoning]
        default_model: sonnet
        cost_profile: medium
      fd-game-design:
        specialization: [balance, pacing, emergent_behavior]
        default_model: sonnet
        cost_profile: medium
        condition: "project.domain == 'game'"

  interlock:
    capabilities:
      kernel:
        - dispatch.status
      filesystem:
        - read
        - write
      coordination:
        - file_reservation
        - conflict_detection
    provides:
      - multi_agent_coordination

  interphase:
    capabilities:
      kernel:
        - events.tail
        - run.phase
      provides:
        - phase_tracking
        - gate_validation

  interpeer:
    capabilities:
      external:
        - oracle_api
        - codex_api
      provides:
        - cross_ai_review
```

### Full Stage Examples

```yaml
stages:
  discover:
    description: "Research, brainstorming, and problem definition"
    phases: [research, brainstorm]
    requires:
      capabilities:
        - long_context_exploration
        - ambient_research
        - deep_reasoning
      tools:
        - file_read
        - web_search
        - web_fetch
    artifacts:
      research_briefing:
        type: markdown
        required: false
      brainstorm:
        type: markdown
        path_pattern: "docs/brainstorms/{date}-{slug}-brainstorm.md"
        required: true
    gates: {}  # No gates — discover is exploratory
    budget:
      share: 10
      min_tokens: 2000
      model_preference: opus
    agents:
      required:
        - role: brainstormer
          description: "Collaborative brainstorming with deep reasoning"
          model_tier: opus
      optional:
        - role: researcher
          description: "Background research and trend detection"
          model_tier: haiku
          count: 1-3

  build:
    description: "Implementation and testing"
    phases: [executing]
    requires:
      capabilities:
        - code_generation
        - test_execution
        - multi_agent_coordination
      tools:
        - file_read
        - file_write
        - bash
        - grep
    artifacts:
      code_changes:
        type: git_diff
        required: true
      test_results:
        type: test_output
        required: true
    gates:
      tests_pass:
        type: command
        command: "project_test_command"
        exit_code: 0
      plan_reviewed:
        type: phase_completed
        phase: plan-reviewed
    budget:
      share: 40
      min_tokens: 10000
      model_preference: sonnet
    agents:
      required:
        - role: implementer
          description: "Code generation and modification"
          model_tier: sonnet
      optional:
        - role: parallel_implementer
          description: "Independent module implementation"
          model_tier: codex
          count: 0-4
          condition: "plan.independent_modules > 1"
        - role: tdd_agent
          description: "Test-driven development discipline"
          model_tier: haiku

  ship:
    description: "Final review, deployment, and knowledge capture"
    phases: [shipping]
    requires:
      capabilities:
        - multi_perspective
        - cross_ai_review
      tools:
        - file_read
        - file_write
        - bash
    artifacts:
      review_verdicts:
        type: verdict_json
        required: true
      commit:
        type: git_commit
        required: true
    gates:
      quality_gates:
        type: verdict_clean
        max_needs_attention: 0
      no_test_failures:
        type: command
        command: "project_test_command"
        exit_code: 0
    budget:
      share: 20
      min_tokens: 5000
      model_preference: sonnet
    agents:
      required:
        - role: reviewer
          description: "Multi-agent code review"
          count: 4-12
          model_tier: sonnet
      optional:
        - role: critical_reviewer
          description: "Oracle cross-validation for high-risk changes"
          model_tier: oracle
          condition: "complexity >= 4 or risk_profile == 'high'"

  reflect:
    description: "Capture learnings, calibrate complexity"
    phases: [reflect]
    requires:
      capabilities:
        - artifact_generation
      tools:
        - file_read
        - file_write
    artifacts:
      learnings:
        type: markdown
        required: true
      complexity_calibration:
        type: json
        required: false
    gates: {}  # Soft gate — warn but don't block
    budget:
      share: 5
      min_tokens: 1000
      model_preference: haiku
    agents:
      required:
        - role: reflector
          description: "Learning capture and complexity calibration"
          model_tier: haiku
      optional:
        - role: deep_reflector
          description: "Full solution doc for complex work"
          model_tier: opus
          condition: "complexity >= 3"
```

---

## Integration Points

### 1. Sprint Pipeline Reads the Spec

Today `sprint.md` hardcodes step order and behavior. With agency specs:

```
sprint_start → load agency-spec.yaml → for each stage:
  1. Read stage requirements from spec
  2. Match requirements to available companions/agents (manual now, Composer later)
  3. Allocate budget from stage.budget.share
  4. Dispatch agents per stage.agents
  5. Validate artifacts against stage.artifacts
  6. Check gates against stage.gates
  7. Advance to next stage
```

**Immediate value:** The spec replaces hardcoded step logic. Adding a new review agent to the ship stage is a YAML edit, not a skill rewrite.

### 2. Routing.yaml Stays — Spec Adds Policy Layer

`routing.yaml` handles model resolution (B1/B2). The agency spec adds *why* a model is needed (stage purpose, agent role). They compose:

```
Agency spec: "Ship stage needs multi_perspective review with sonnet-tier agents"
Routing.yaml: "shipping phase uses sonnet, review category uses opus"
Resolution: opus (routing.yaml phase+category beats spec default)
```

The spec's `model_tier` is a preference hint. Routing.yaml has final authority for the actual model.

### 3. Gate Definitions Move to Spec

Currently gates are hardcoded in `lib-sprint.sh`:enforce_gate. With the spec:

```yaml
gates:
  plan_review:
    type: artifact_reviewed
    artifact: plan
    min_agents: 3
```

`enforce_gate` reads the spec, validates conditions, returns pass/fail. Gate logic becomes data-driven.

### 4. Budget Allocation Becomes Per-Stage

Today: one `--token-budget` per run, no breakdown.
With spec: budget splits across stages. `sprint_budget_remaining` can report per-stage, not just per-run. The Composer (C3) uses per-stage budgets to decide agent roster size and model tier.

### 5. Companion Capabilities Feed C2 (Fleet Registry)

The `companions:` section in agency-spec.yaml is the seed data for the fleet registry. When C2 ships, it reads these declarations and enriches them with actual cost/quality data from Interspect. The spec declares *what companions claim they can do*; the registry tracks *what they actually deliver*.

---

## Open Questions

1. **Spec location:** Default at `os/clavain/config/agency-spec.yaml` alongside `routing.yaml`? Or in a `specs/` directory? The config directory is simpler and follows the existing pattern.

2. **Capability vocabulary:** The `requires.capabilities` field uses free-form strings like `deep_reasoning`, `multi_perspective`. Should this be a fixed enum? A fixed enum is more validatable but harder to extend. Start with convention + validation warnings, formalize into enum when the vocabulary stabilizes.

3. **Project-level overrides:** `.clavain/agency-spec.yaml` in each project overrides the default. Merge strategy: deep merge (project values override matching keys, defaults fill gaps)? Or replace (project spec replaces entire stage)?  Deep merge is more useful — a Go project might only override build.agents to add golangci-lint, inheriting everything else.

4. **Companion self-declaration vs central declaration:** Should companions declare their capabilities in their own `plugin.json`, or should Clavain's agency spec centrally list all companions? Central is easier now (single file to edit), but self-declaration scales better for the platform play (circle 3). Start central, add self-declaration protocol in C2.

5. **Gate extensibility:** The gate types proposed (artifact_reviewed, command, phase_completed, verdict_clean) cover current needs. Custom gate types would need a plugin mechanism. Defer until real need emerges.

6. **Dynamic agent count:** `count: 3-7` for reviewer agents — who decides the actual number? Today it's interflux triage logic. With the spec, the Composer (C3) decides. Until C3 ships, the spec's min value is used. This is a graceful degradation: min-count today, optimized count with Composer.

---

## What's NOT in Scope

- **C2 (Fleet Registry)** — This spec declares companion capabilities; C2 enriches them with cost/quality data. C2 is a separate bead.
- **C3 (Composer)** — This spec defines what stages need; C3 matches needs to available resources. C3 is a separate bead.
- **Enforcement of capability restrictions** — Following pi_agent_rust lessons: declare now, shadow-validate later, enforce after data.
- **Dynamic spec modification** — The spec is static config. Interspect may eventually propose spec changes (B3/C5 territory), but the spec itself is a file, not a runtime object.

---

## Implementation Approach

### Phase 1: Schema + Default Spec (this sprint)

1. Define the YAML schema (JSON Schema for validation)
2. Write the default `agency-spec.yaml` encoding current implicit behavior
3. Add a loader function to `lib-sprint.sh` (or a new `lib-agency.sh`)
4. Validate the spec at sprint start (schema check + companion availability)

### Phase 2: Sprint Pipeline Integration

1. `enforce_gate` reads gate definitions from spec instead of hardcoded logic
2. Budget allocation splits per-stage share from run total
3. Agent roster validation — warn if dispatched agents exceed spec's count range
4. Artifact validation — verify required artifacts exist at stage transitions

### Phase 3: Companion Capability Declarations

1. Add `capabilities` section to spec for all 31+ companions
2. Shadow-mode validation: log when a companion uses an undeclared capability
3. Generate companion capability report from spec (for fleet registry seed data)

---

## Success Criteria

- [ ] `agency-spec.yaml` exists with all 5 macro-stages defined
- [ ] JSON Schema validates the spec format
- [ ] Sprint pipeline loads and reads the spec (gate definitions, budget shares)
- [ ] At least 5 companion plugins have capability declarations
- [ ] Adding a new review agent to a stage is a YAML edit, not a code change
- [ ] `enforce_gate` reads gate config from spec, not from hardcoded conditionals
- [ ] Per-stage budget allocation works (visible in sprint summary)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Over-engineering the schema before real usage data | High | Medium | Start minimal — 5 stages, basic gates, simple budgets. Iterate based on sprint experience. |
| Spec drift from actual behavior | Medium | High | Validation at sprint start checks spec against available companions/agents. Fail fast on mismatch. |
| Breaking existing sprint pipeline | Medium | High | Backward compatible: when no spec exists, fall back to current behavior. Spec enhances, doesn't gate. |
| Schema migration pain as spec evolves | Low | Medium | Version field in spec. Migration script for breaking changes. |
