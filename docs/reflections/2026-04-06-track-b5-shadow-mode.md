---
artifact_type: reflection
bead: sylveste-kpj0
stage: reflect
---

# Reflection: Enable Clavain Track B5 Shadow Mode

**Bead:** sylveste-kpj0
**Date:** 2026-04-06

## What happened

Implemented Track B5 local model routing in lib-routing.sh. The config was
already declared in routing.yaml (mode=shadow, tier mappings, complexity routing,
ineligible agents, confidence cascade) but the resolution logic was missing from
the shell library. Added ~80 lines: config parsing, health check with 30s cache,
shadow logging, and integration into routing_resolve_model_complex.

Also updated C3 tier mapping from qwen3.5-122b-a10b to flash-moe:qwen3.5-397b
based on the 122B benchmark results (sylveste-e25).

## What we learned

1. **Config-code gap is invisible.** The routing.yaml had a complete B5 section
   since 2026-03-26 (promoted from off to shadow), but no code read it. AGENTS.md
   said "mode: shadow (current)" suggesting it was working. The config declares
   intent; only the code delivers it.

2. **Bats + bash associative arrays don't mix with `run`.** The `run` command
   creates a subshell that inherits scalar variables but loses associative array
   contents. All pre-existing test failures (12 of 32) share this root cause.
   The B5 tests use direct function calls to avoid this.

3. **The existing routing infrastructure (B1-B4) is well-designed for extension.**
   Adding B5 was straightforward: parse a new section, add resolution functions,
   hook into the existing resolve chain. The shadow/enforce mode pattern from B2
   transferred directly.

## What we'd do differently

The B5 shadow log format should include the **cloud model cost** alongside the
local model name, so the shadow report can estimate savings. Currently it just
logs the model swap. Future: `[B5-shadow] would save ~$0.02: sonnet → local:35b`.
