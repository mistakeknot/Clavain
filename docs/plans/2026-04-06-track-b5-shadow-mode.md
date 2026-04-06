---
artifact_type: plan
bead: sylveste-kpj0
stage: planned
---

# Plan: Enable Clavain Track B5 Shadow Mode

**Bead:** sylveste-kpj0
**Date:** 2026-04-06

## Task 1: Add B5 resolution functions to lib-routing.sh

**File:** `scripts/lib-routing.sh`

Add three functions after the existing B2/B3 resolution code:

1. `_routing_b5_available()` — Cached health check (30s TTL) against interfer endpoint
2. `_routing_b5_resolve()` — Given complexity tier + agent name, return local model or reason for skip
3. Integration into `routing_resolve_model_complex()` — After B2 resolution, call B5 in shadow/enforce mode

**Implementation:**
- Read mode from yaml config (`local_models.mode`) with env override (`INTERFERE_ROUTING_MODE`)
- Read ineligible agents list from yaml
- Read complexity_routing map from yaml
- Health check: `curl -sf --max-time 1 "$endpoint/health"`, cache result
- Shadow log format: `[B5-shadow] would route locally: <cloud> → <local> (complexity=<C> agent=<name>)`

## Task 2: Update routing.yaml C3 mapping

**File:** `config/routing.yaml`

Change C3 from 122B to flash-moe 397B per benchmark results:
```yaml
C3: "flash-moe:qwen3.5-397b"  # SSD-streamed, ~1 tok/s, quality equivalent to 122B
```

Add flash-moe tier mapping:
```yaml
"flash-moe:qwen3.5-397b": 3   # SSD-streamed via flash-moe binary
```

## Task 3: Add B5 shadow report

**File:** `scripts/routing-b5-shadow-report.sh`

Adapt existing `routing-shadow-report.sh` pattern for B5 logs:
- Parse `[B5-shadow]` lines from session logs
- Show: would-route-locally count, ineligible count, unavailable count
- Per-agent breakdown
- Enforce readiness verdict

## Task 4: Add B5 tests

**File:** `tests/shell/test_routing.bats`

Test cases:
- B5 shadow mode logs but returns cloud model
- B5 ineligible agents (fd-safety, fd-correctness) are skipped
- B5 off mode returns cloud model with no log
- B5 complexity mapping (C1→35B, C2→35B, C3→397B)
- Health check caching (mock curl)

## Task 5: Update AGENTS.md

Document B5 shadow mode status and how to read shadow logs.

## Execution Order

Tasks 1-2 are the core work (sequential — 2 is a config change that 1 reads).
Task 3 is independent. Task 4 depends on 1. Task 5 depends on all.
