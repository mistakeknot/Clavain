# B1: Static Routing Table — Phase-to-Model Mapping in Config

**Bead:** iv-dd9q
**Phase:** brainstorm (as of 2026-02-21T04:03:58Z)
**Date:** 2026-02-20
**Track:** B (Model Routing)

---

## What We're Building

A single YAML configuration file (`config/routing.yaml`) that declares all model routing policy for Clavain. It replaces two current systems:

1. **Agent frontmatter** (`model: sonnet` in agent `.md` files) — currently toggled via `/clavain:model-routing` between economy and quality modes
2. **Dispatch tiers** (`config/dispatch/tiers.yaml`) — maps tier names to Codex model names for interserve dispatch

After B1, there is one file that answers "what model does this agent/phase/dispatch use?" for both Claude Code subagents and Codex dispatch.

## Why This Approach

### Design constraints from the vision

1. **Routing is OS policy** — The vision places model routing in Layer 2 (Clavain), not Layer 1 (Intercore). "The kernel doesn't know what 'brainstorm' means." The routing table lives in Clavain's config, not in `ic`.

2. **Zero-cost abstraction** — From pi_agent_rust lessons (section 3): when B3 (adaptive routing) is off, routing must collapse to a static config lookup with zero overhead. B1's schema is that static path.

3. **Compose through contracts** — Vision principle 2: prefer declarative specs over implicit behavior. The routing table is a typed, readable contract.

4. **Single source of truth** — Currently three independent systems (agent frontmatter, tiers.yaml, interspect overrides) make it impossible to answer "why did this agent get this model?" B1 consolidates them.

### What it enables

- **B2 (complexity-aware)**: Adds a `complexity_overrides:` section. Resolution becomes: complexity > phase > default. Same file, one new section.
- **B3 (adaptive)**: Adds an `adaptive:` section driven by Interspect. Resolution chain extends: adaptive > complexity > phase > default.
- **C2 (fleet registry)**: Reads routing.yaml to build capability + cost profiles per agent x model combination.

## Key Decisions

### 1. Nested YAML with explicit inheritance

Schema uses layered resolution: `defaults → phases → overrides`. Each level inherits from its parent unless overridden.

```yaml
# config/routing.yaml
#
# Model routing policy for Clavain.
# Resolution order: overrides > phases[current].categories > phases[current].model > defaults.categories > defaults.model

defaults:
  model: sonnet
  categories:
    research: haiku
    review: sonnet
    workflow: sonnet
    synthesis: haiku

phases:
  brainstorm:
    model: opus
    categories:
      research: haiku       # even in brainstorm, research agents don't need opus
  strategy:
    model: opus
  plan:
    model: sonnet
  execute:
    model: sonnet
  quality-gates:
    categories:
      review: opus           # reviews get opus for quality-gates phase
  ship:
    model: sonnet

# Codex dispatch tiers (replaces config/dispatch/tiers.yaml)
dispatch:
  tiers:
    fast:
      model: gpt-5.3-codex-spark
      description: Scoped read-only tasks, exploration, verification
    fast-clavain:
      model: gpt-5.3-codex-spark-xhigh
      description: Clavain interserve-mode read-only tasks
    deep:
      model: gpt-5.3-codex
      description: Generative tasks, implementation, complex reasoning
    deep-clavain:
      model: gpt-5.3-codex-xhigh
      description: Clavain interserve-mode high-complexity tasks
  fallback:
    fast: deep
    fast-clavain: deep-clavain
    deep-clavain: deep

# Per-agent pinning (wins over everything)
overrides: {}
  # fd-architecture: opus     # example: pin a specific agent regardless of phase
```

**Why nested over flat**: CSS-like specificity (option A) has implicit resolution order that violates "compose through contracts." When B2 adds complexity overrides, implicit resolution becomes a debugging nightmare. Nested inheritance is self-documenting — you read the file top to bottom and know exactly what wins.

**Why nested over table**: A (phase x category) matrix requires every phase to declare every category, leading to matrix explosion when B2 adds complexity tiers. Nested inheritance avoids the repetition.

### 2. Merge dispatch tiers into routing.yaml

The `dispatch:` section replaces `config/dispatch/tiers.yaml`. One file for all model routing — both internal (Claude Code subagents) and external (Codex dispatch). `dispatch.sh` reads `routing.yaml` instead of `tiers.yaml`.

**Migration**: `tiers.yaml` is deleted. `dispatch.sh`'s `resolve_tier_model()` function is updated to read from `routing.yaml`'s `dispatch.tiers` path instead.

### 3. Shell library as sole consumer API

A new `lib-routing.sh` provides `resolve_model()`:

```bash
resolve_model --phase execute --category review
# Returns: sonnet (from defaults.categories.review, since phases.execute has no review override)

resolve_model --phase quality-gates --category review
# Returns: opus (from phases.quality-gates.categories.review)

resolve_model --phase brainstorm
# Returns: opus (from phases.brainstorm.model)

resolve_model --agent fd-architecture
# Returns: fd-architecture's override if set, else falls through to phase+category resolution
```

**Why shell, not ic**: The vision says "the policy authority is in the OS." Adding `ic routing resolve` would leak OS policy into the kernel — the exact "kernel primitive creep" the pi_agent_rust lessons (section 4) warn against. Shell resolution is ~1ms (YAML parse + lookup), vs ~10-50ms for an `ic` subprocess call.

**Audit trail deferred to B2/B3**: B1 has no event emission. When B2 needs to audit "what model was chosen and why," it adds `ic event emit routing-decision ...` after resolution. The kernel stores the event without interpreting it — mechanism, not policy.

### 4. `/clavain:model-routing` becomes a routing.yaml editor

Instead of `sed`-ing agent frontmatter, the command reads/writes `routing.yaml`:
- `model-routing economy` → sets defaults to the current economy profile (research=haiku, review/workflow=sonnet)
- `model-routing quality` → sets defaults to inherit (all opus)
- `model-routing status` → displays the resolved routing table for all phases

Agent `.md` frontmatter `model:` lines are removed — the routing table is the source of truth.

### 5. Phase is caller-provided, not ambient

Skills/hooks pass the current phase explicitly when resolving: `resolve_model --phase "$current_phase" --category review`. There is no ambient "current phase" environment variable. This keeps agents phase-unaware (they don't need to know what phase they're in) and makes resolution deterministic and testable.

## Open Questions

1. **Agent category assignment**: How do we know an agent's category? Currently it's implicit from the directory (`agents/research/`, `agents/review/`). Should routing.yaml reference categories, or should each agent declare its category in frontmatter? (Categories: research, review, workflow, synthesis, dispatch.)

2. **Companion plugin agents**: Interflux, intercraft, and intersynth all have agents with `model:` frontmatter. Should routing.yaml govern companion agents too, or only Clavain's own agents? If yes, how does the companion discover the routing table? (It's in Clavain's config dir, not theirs.)

3. **Fallback behavior**: If `routing.yaml` is missing or malformed, what happens? Options: (a) error out, (b) fall back to hardcoded defaults, (c) fall back to agent frontmatter. For zero-cost B1 the answer is probably (b) — hardcoded defaults that match the current economy profile.

4. **Dispatch tier selection within phases**: Should `routing.yaml` also map phases to dispatch tiers? E.g., brainstorm phase uses `--tier deep`, execute phase uses `--tier fast` for exploration sub-tasks. Or is tier selection orthogonal to phase?

---

## Summary

B1 delivers a single `config/routing.yaml` file with nested-inheritance schema, a `lib-routing.sh` shell library for resolution, and migration of both agent frontmatter and `tiers.yaml` into the unified config. It's designed as the zero-cost static path that B2 (complexity) and B3 (adaptive) extend without schema breaks.
