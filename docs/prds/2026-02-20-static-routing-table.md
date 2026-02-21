# PRD: B1 — Static Routing Table

**Bead:** iv-dd9q
**Brainstorm:** [2026-02-20-static-routing-table-brainstorm.md](../brainstorms/2026-02-20-static-routing-table-brainstorm.md)
**Track:** B (Model Routing) — Step 1 of 3
**Review:** Flux-drive (fd-architecture, fd-correctness, fd-user-product) — 2026-02-20

## Problem

Model routing policy is scattered across three independent systems (agent frontmatter, tiers.yaml, interspect overrides) with no unified view. You can't answer "what model will this agent use in this phase?" without reading multiple files and understanding implicit resolution rules. This blocks B2 (complexity-aware routing) and B3 (adaptive routing), which need a single config to extend.

## Solution

A single `config/routing.yaml` file declaring all model routing policy, a `lib-routing.sh` shell library for resolution, and migration of existing routing systems into the unified config. Zero runtime overhead — pure config lookup, no DB queries, no subprocesses beyond YAML parsing.

## Features

### F1: Routing config schema (`config/routing.yaml`)

**What:** Create the routing.yaml file with nested-inheritance schema: defaults, phase overrides, and dispatch tiers.

**Acceptance criteria:**
- [ ] `config/routing.yaml` exists with `defaults`, `phases`, and `dispatch` sections
- [ ] Resolution order is `phases[current].categories > phases[current].model > defaults.categories > defaults.model`
- [ ] Phase keys match the live codebase phase names: `brainstorm`, `brainstorm-reviewed`, `strategized`, `planned`, `executing`, `shipping`, `reflect`, `done` (NOT display names like `strategy`, `plan`, `quality-gates`)
- [ ] `dispatch.tiers` section contains the same tier definitions currently in `config/dispatch/tiers.yaml` (fast, fast-clavain, deep, deep-clavain) plus fallback mappings
- [ ] Default values match the current economy profile: research=haiku, review=sonnet, workflow=sonnet, synthesis=haiku
- [ ] Phase mappings reflect current implicit behavior: brainstorm=opus, brainstorm-reviewed=opus, strategized=opus, planned=sonnet, executing=sonnet (with review category=opus), shipping=sonnet, reflect=sonnet, done=sonnet
- [ ] No inline comments on value lines (YAML parser simplicity). Comments go on their own lines above the key.
- [ ] File includes a header comment documenting the resolution order

**Schema:**
```yaml
# config/routing.yaml
#
# Model routing policy for Clavain.
# Resolution: phases[current].categories > phases[current].model > defaults.categories > defaults.model
# If --category is omitted, categories block is skipped — only .model is consulted.
# `resolve_model` MUST never return "inherit" — it is an internal sentinel meaning "delete this override."

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
  brainstorm-reviewed:
    model: opus
  strategized:
    model: opus
  planned:
    model: sonnet
  executing:
    model: sonnet
    categories:
      # Reviews get opus during execution phase (quality gates run here)
      review: opus
  shipping:
    model: sonnet
  reflect:
    model: sonnet
  done:
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
```

### F2: Resolution library (`hooks/lib-routing.sh`)

**What:** Shell library providing `resolve_model()` that reads routing.yaml and returns the correct model for a given phase + category combination.

**Acceptance criteria:**
- [ ] `resolve_model --phase <phase> --category <category>` returns the correct model per the inheritance chain
- [ ] `resolve_model --phase <phase>` (no category) returns `phases[phase].model`, falling back to `defaults.model`. Never consults `categories` blocks without explicit `--category`.
- [ ] `resolve_model` with no arguments returns `defaults.model`
- [ ] `resolve_model` MUST never return the string `inherit`. If `inherit` is encountered during resolution, it means "this level has no override — continue to next level." If the entire chain resolves to `inherit`, return `defaults.model` hardcoded fallback.
- [ ] Falls back to hardcoded defaults if routing.yaml is missing or malformed (matches economy profile). Malformed config produces a stderr warning, NOT silent fallback.
- [ ] `resolve_dispatch_tier <tier>` replaces `resolve_tier_model()` from dispatch.sh, reading from `routing.yaml` dispatch section
- [ ] Handles interserve mode tier remapping (fast→fast-clavain, deep→deep-clavain)
- [ ] YAML parser strips comments (lines starting with `#` and inline `# ...` after values)
- [ ] YAML parser strips trailing whitespace from values
- [ ] Config discovery chain: (1) `$CLAVAIN_ROUTING_CONFIG` env var, (2) script-relative `../config/routing.yaml`, (3) `$CLAVAIN_SOURCE_DIR/config/routing.yaml`, (4) `~/.claude/plugins/cache/*/clavain/*/config/routing.yaml`
- [ ] Resolution completes in <5ms (no subprocess calls, YAML parsed with awk/sed)
- [ ] Has corresponding bats-core tests validating all resolution paths, including: comment stripping, `inherit` sentinel interception, missing config fallback, phase-only resolution (no category), and config discovery chain

### F3: Dispatch migration

**What:** Migrate `dispatch.sh` from reading `config/dispatch/tiers.yaml` to sourcing `lib-routing.sh` and calling `resolve_dispatch_tier`.

**Acceptance criteria:**
- [ ] `dispatch.sh` sources `lib-routing.sh` and calls `resolve_dispatch_tier` instead of `resolve_tier_model`
- [ ] `config/dispatch/tiers.yaml` is deleted
- [ ] `dispatch.sh --tier fast` produces identical output before and after migration
- [ ] `dispatch.sh --tier deep` produces identical output before and after migration
- [ ] Interserve mode remapping (fast→fast-clavain) still works
- [ ] Fallback chain (fast→deep when spark unavailable) still works
- [ ] `skills/interserve/SKILL.md` and `skills/interserve/references/cli-reference.md` updated to reference `routing.yaml` instead of `tiers.yaml`

### F4: Update `/clavain:model-routing` command

**What:** Rewrite the model-routing command to read/write routing.yaml instead of sed-ing agent frontmatter.

**Acceptance criteria:**
- [ ] `model-routing status` reads routing.yaml and displays: (1) a single-word mode label (`economy`/`quality`/`custom`), (2) per-category default models, (3) per-phase overrides that differ from defaults
- [ ] `model-routing economy` writes the economy defaults to routing.yaml (research=haiku, review/workflow=sonnet, synthesis=haiku)
- [ ] `model-routing quality` writes `inherit` at every level in `phases` (deleting all phase overrides) AND sets `defaults.model: opus` and all `defaults.categories` to `opus`. Result: all resolution paths return opus.
- [ ] Agent `.md` frontmatter `model:` lines in **Clavain's own agents only** (4 agents in `agents/review/` and `agents/workflow/`) are removed
- [ ] Command no longer runs `sed` on agent files

**Status output example:**
```
Mode: economy

Defaults:
  research: haiku | review: sonnet | workflow: sonnet | synthesis: haiku

Phase overrides:
  brainstorm:          opus (all categories)
  brainstorm-reviewed: opus (all categories)
  strategized:         opus (all categories)
  executing:           review → opus
```

## Non-goals

- **No per-agent overrides in routing.yaml** — Deferred to B2/B3. Interspect already manages per-agent overrides via `.claude/routing-overrides.json`. B1 does not duplicate or conflict with that system.
- **No complexity-aware routing** — That's B2. routing.yaml has extension points for it but no `complexity_overrides` section yet.
- **No event emission / audit trail** — That's B2/B3. B1 doesn't emit routing decisions to the kernel.
- **No adaptive routing** — That's B3. No Interspect integration.
- **No companion plugin frontmatter removal** — Interflux, intercraft, and intersynth agents keep their `model:` frontmatter in B1. Companion agent routing requires a mechanism to pass resolved models through the Claude Code Task tool, which doesn't exist yet. Deferred to B2.
- **No per-agent routing in skills** — Skills don't yet pass `--phase` to resolve_model. That integration is a follow-up after the library is proven.
- **No runtime agent category registration** — Agent categories are inferred from directory path. Formal registration is deferred.

## Dependencies

- `config/dispatch/tiers.yaml` (will be deleted and replaced)
- `dispatch.sh` `resolve_tier_model()` function (will be replaced)
- `commands/model-routing.md` (rewrite)
- `skills/interserve/SKILL.md` and `skills/interserve/references/cli-reference.md` (tiers.yaml path references)
- Clavain agent `.md` files (4 files: `agents/review/plan-reviewer.md`, `agents/review/data-migration-expert.md`, `agents/workflow/bug-reproduction-validator.md`, `agents/workflow/pr-comment-resolver.md`)

## Resolved Questions (from flux-drive review)

1. **Phase names**: Use codebase phase names (`strategized`, `planned`, `executing`, `shipping`), NOT display names (`strategy`, `plan`, `quality-gates`, `ship`). `quality-gates` is not a phase — review-agent routing for that step uses `phases.executing.categories.review: opus`.

2. **`inherit` semantics**: `inherit` means "this level has no override — continue to next level in the chain." It is an internal sentinel that `resolve_model` resolves before returning. `resolve_model` MUST never return `inherit` as a final value.

3. **Per-agent overrides**: Removed from B1 scope. Interspect's `routing-overrides.json` already handles this. B2/B3 will integrate routing.yaml with Interspect's override system.

4. **Companion frontmatter**: NOT removed in B1. Companion agents keep `model:` frontmatter until B2 provides a mechanism to pass routing table results through the Claude Code Task tool dispatch path.

5. **`--category` omission**: When `--category` is not provided, `resolve_model` returns `phases[phase].model` (falling back to `defaults.model`). The `categories` block is never consulted without an explicit `--category` argument.

6. **Config path discovery**: `lib-routing.sh` uses the same three-location probe pattern as `dispatch.sh` — env var override, script-relative, cache fallback.

## Open Questions

1. **Companion agent routing mechanism (B2)**: How will `resolve_model` results reach companion agents at Task tool dispatch time? Options: (a) pre-resolve in the skill and pass `model:` param explicitly, (b) hook that intercepts Task tool calls and injects model, (c) companion agents source `lib-routing.sh` themselves. Research needed for B2.

2. **Interspect override integration (B2/B3)**: How does `routing-overrides.json` compose with routing.yaml? Does Interspect write to routing.yaml directly, or does `resolve_model` consult both files? The resolution chain for B2+ will need to be: `interspect_overrides > complexity > phases > defaults`.
