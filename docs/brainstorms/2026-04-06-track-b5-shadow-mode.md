---
artifact_type: brainstorm
bead: sylveste-kpj0
stage: brainstorm
---

# Brainstorm: Enable Clavain Track B5 Shadow Mode

**Bead:** sylveste-kpj0
**Date:** 2026-04-06

## Current State

Track B5 is **configured but not implemented**:
- `routing.yaml` (lines 202-253): mode=shadow, endpoint, tier mappings, complexity routing, confidence cascade, ineligible agents — all declared
- `lib-routing.sh`: `_routing_model_tier()` knows local model tiers (lines 50-62) for safety floor comparisons
- **Missing**: No B5 resolution function, no interfer availability check, no shadow logging

B2 shadow mode (complexity routing) is the template — it was promoted from shadow to enforce on 2026-03-18 after the shadow report showed 80%+ downgrades.

## What B5 Shadow Mode Needs

### 1. `routing_resolve_local_model` function in lib-routing.sh

Given a resolved cloud model (from B1/B2/B3), determine what local model would handle it:

```
Input:  cloud_model=sonnet, complexity=C2, agent=fd-architecture, phase=executing
Output: local_model=local:qwen3.5-35b-a3b-4bit  (or "ineligible" or "unavailable")
```

Logic:
1. Check if agent is in ineligible list → return "ineligible"
2. Read B5 mode (off/shadow/enforce) from yaml + env override
3. If off → return early
4. Check interfer availability (curl health endpoint, cache for 30s)
5. Map complexity tier to local model via `complexity_routing` config
6. If shadow → log `[B5-shadow] would route locally: sonnet → local:qwen3.5-35b-a3b-4bit`
7. If enforce → return local model instead of cloud model

### 2. Health check with caching

Don't curl interfer on every resolution. Cache the result for 30 seconds:
```bash
_B5_HEALTH_CACHE=""
_B5_HEALTH_CACHE_TIME=0
_routing_b5_available() {
    now=$(date +%s)
    if (( now - _B5_HEALTH_CACHE_TIME < 30 )); then
        echo "$_B5_HEALTH_CACHE"; return
    fi
    if curl -sf --max-time 1 "http://localhost:8421/health" >/dev/null 2>&1; then
        _B5_HEALTH_CACHE="yes"; _B5_HEALTH_CACHE_TIME=$now; echo "yes"
    else
        _B5_HEALTH_CACHE="no"; _B5_HEALTH_CACHE_TIME=$now; echo "no"
    fi
}
```

### 3. Shadow logging format

Match B2 pattern for shadow report compatibility:
```
[B5-shadow] would route locally: sonnet → local:qwen3.5-35b-a3b-4bit (complexity=C2 phase=executing agent=fd-architecture)
[B5-shadow] ineligible: fd-safety (safety floor)
[B5-shadow] unavailable: interfer not responding
```

### 4. Integration point

The existing `routing_resolve_model_complex` function is the right place to add B5.
After B2 resolves the cloud model, B5 checks if it can be served locally.

### 5. Shadow report for B5

Adapt `routing-shadow-report.sh` to also parse `[B5-shadow]` lines.
Or create a separate `routing-b5-shadow-report.sh`.

### 6. Update routing.yaml C3 mapping

Per the 122B benchmark results, C3 should map to flash-moe:397B, not 122B:
```yaml
C3: "flash-moe:qwen3.5-397b"  # was local:qwen3.5-122b-a10b-4bit
```

## What This Does NOT Change

- No enforce mode — just shadow logging
- No actual local routing — all tasks still go to cloud
- No confidence cascade implementation (future: enforce mode)
- No privacy routing implementation (future: enforce mode)

## Success Criteria

- [ ] `routing_resolve_model_complex` calls B5 check after B2
- [ ] Shadow logs appear in stderr with `[B5-shadow]` prefix
- [ ] Interfer availability cached (no per-call latency)
- [ ] Ineligible agents logged and skipped
- [ ] Shadow report script parses B5 logs
- [ ] Tests in test_routing.bats cover B5 shadow cases
