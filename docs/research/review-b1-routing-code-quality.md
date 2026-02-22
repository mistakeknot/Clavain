# B1 Static Routing Table — Code Quality Review

**Date:** 2026-02-20
**Scope:** `scripts/lib-routing.sh` (NEW), `scripts/dispatch.sh` (MODIFIED), `config/routing.yaml` (NEW)
**Languages:** Shell (Bash)
**Reviewer:** fd-quality agent

---

## Files Reviewed

- `/root/projects/Interverse/os/clavain/scripts/lib-routing.sh` — 379 lines, new shell library
- `/root/projects/Interverse/os/clavain/scripts/dispatch.sh` — modified to source lib-routing.sh and simplified resolve_tier_model
- `/root/projects/Interverse/os/clavain/config/routing.yaml` — new unified routing config (71 lines)

---

## Executive Summary

The B1 implementation is well-structured overall. The source-once and cache-once guard pattern is correct. The YAML parser is a robust line-by-line state machine with appropriate comment stripping. Error handling in the public API is consistent. Three issues require attention before this is considered fully correct:

1. `((hops++))` in `routing_resolve_dispatch_tier` is latently incompatible with `set -e` for direct callers (safe only via `$()` subshells on Bash 5.x due to a subshell arithmetic exception).
2. A misleading diagnostic note is emitted when interserve tier remapping fails and the base tier is used instead — the message incorrectly says "mapped to fast-clavain" when it actually fell back to "fast".
3. The `${printed_phases[@]:-}` expansion in `routing_list_mappings` is the wrong idiom for guarding an empty array under `set -u` — it produces one empty-string iteration rather than zero.

One documentation inconsistency (resolution order in routing.yaml omits `overrides[agent]`) and one intentional stub (`--phase` / `PHASE` no-op) are noted but are low severity.

---

## Detailed Findings

### Finding 1: `((hops++))` under `set -e` — latent correctness defect

**File:** `scripts/lib-routing.sh`, line 287
**Severity:** Medium

```bash
routing_resolve_dispatch_tier() {
  local tier="$1"
  local hops=0

  while [[ $hops -lt 3 ]]; do
    if [[ -n "${_ROUTING_DISPATCH_TIER[$tier]:-}" ]]; then
      echo "${_ROUTING_DISPATCH_TIER[$tier]}"
      return 0
    fi
    if [[ -n "${_ROUTING_DISPATCH_FALLBACK[$tier]:-}" ]]; then
      tier="${_ROUTING_DISPATCH_FALLBACK[$tier]}"
      ((hops++))     # line 287 — BUG HERE
    else
      break
    fi
  done
  return 1
}
```

**Root cause:** In Bash, `((expr))` returns exit code 1 when the arithmetic result is 0. When `hops=0`, `((hops++))` evaluates to 0 (the pre-increment value), so its exit code is 1. Under `set -e`, this kills the calling script.

**Tested behavior:**
- Direct call from `set -e` context: script exits before second iteration, fallback chain is skipped.
- Call via `$()` subshell (as used in `dispatch.sh`): Bash 5.x arithmetic exception suppresses `set -e` inside subshells, so the fallback works in practice. This is a Bash implementation detail, not a language guarantee.
- Confirmed: `bash -c 'set -e; hops=0; ((hops++)); echo ok'` exits with code 1 — the echo never runs.

**Impact:** Currently masked because `routing_resolve_dispatch_tier` is always called via `model="$(routing_resolve_dispatch_tier ...)" || model=""`. Any future direct call (test script, inline use, or Bash version change) will silently skip the fallback chain.

**Fix:**
```bash
hops=$(( hops + 1 ))
```
This form always exits 0 regardless of result.

---

### Finding 2: Misleading diagnostic note in `resolve_tier_model` fallback path

**File:** `scripts/dispatch.sh`, lines 185–193
**Severity:** Low-Medium

```bash
# If interserve tier not found, fall back to base tier
if [[ -z "$model" && "$target_tier" != "$tier" ]]; then
  echo "Note: tier '$target_tier' not found. Trying '$tier'." >&2
  model="$(routing_resolve_dispatch_tier "$tier" 2>/dev/null)" || model=""
fi

if [[ -n "$model" && "$target_tier" != "$tier" ]]; then
  echo "Note: tier '$tier' mapped to '$target_tier' for Clavain interserve mode." >&2
fi
```

**Problem:** The second `if` block (line 190) prints the "mapped to" message when `model` is non-empty AND `target_tier != tier`. But this condition is true in BOTH the success scenario (fast-clavain found directly) AND the fallback scenario (fast-clavain not found, resolved via fast). In the fallback case, the message "tier 'fast' mapped to 'fast-clavain'" is factually wrong — we did not use fast-clavain, we fell back to fast.

**Trace for interserve fallback:**
1. `tier=fast`, `target_tier=fast-clavain`
2. `routing_resolve_dispatch_tier("fast-clavain")` → empty (not found)
3. Prints: `"Note: tier 'fast-clavain' not found. Trying 'fast'."`
4. `routing_resolve_dispatch_tier("fast")` → `gpt-5.3-codex-spark`
5. Condition: `model` is set AND `target_tier != tier` → prints `"Note: tier 'fast' mapped to 'fast-clavain' for Clavain interserve mode."` ← WRONG

**Fix:** Track whether the model came from `target_tier` or fell back to `tier`:

```bash
local used_fallback=false

model="$(routing_resolve_dispatch_tier "$target_tier" 2>/dev/null)" || model=""

if [[ -z "$model" && "$target_tier" != "$tier" ]]; then
  echo "Note: tier '$target_tier' not found. Trying '$tier'." >&2
  model="$(routing_resolve_dispatch_tier "$tier" 2>/dev/null)" || model=""
  used_fallback=true
fi

if [[ -n "$model" && "$target_tier" != "$tier" && "$used_fallback" == false ]]; then
  echo "Note: tier '$tier' mapped to '$target_tier' for Clavain interserve mode." >&2
fi
```

---

### Finding 3: `${printed_phases[@]:-}` incorrect idiom for empty array under `set -u`

**File:** `scripts/lib-routing.sh`, line 339
**Severity:** Low

```bash
local printed_phases=()
for k in "${!_ROUTING_SA_PHASE_MODEL[@]}"; do
  # ... build phase_info ...
  printed_phases+=("$k")
done
# Phases with only category overrides (no model)
for pc in "${!_ROUTING_SA_PHASE_CAT[@]}"; do
  local ph="${pc%%:*}"
  local already=false
  for pp in "${printed_phases[@]:-}"; do   # line 339
    [[ "$pp" == "$ph" ]] && already=true
  done
  ...
done
```

**Problem:** `${arr[@]:-}` when `arr` is empty expands to one empty string (not zero arguments). The `for pp in "${printed_phases[@]:-}"` loop therefore iterates once with `pp=""` when no phases have been printed yet. This is functionally harmless here because no real phase name can be an empty string (all phase keys match `^[a-z][a-z0-9_-]*$`), so `"" == "$ph"` is always false. But it is the wrong idiom and will confuse future readers or break if the guard pattern is reused in a context where an empty string could match.

**Correct idiom:**
```bash
for pp in "${printed_phases[@]+"${printed_phases[@]}"}"; do
```
This expands to zero arguments when the array is empty and to all elements otherwise.

---

### Finding 4: `routing.yaml` resolution order comment omits overrides

**File:** `config/routing.yaml`, line 8
**Severity:** Low (documentation only)

```yaml
# Subagent resolution order:
#   phases[phase].categories[cat] > phases[phase].model > defaults.categories[cat] > defaults.model
```

The actual resolution order implemented in `routing_resolve_model` (lib-routing.sh lines 239–270) is:

1. `overrides[agent]`  — **missing from YAML comment**
2. `phases[phase].categories[cat]`
3. `phases[phase].model`
4. `defaults.categories[cat]`
5. `defaults.model`

The missing `overrides[agent]` step means operators reading `routing.yaml` will not realize per-agent pinning is the highest-priority override. Since the `overrides` section is absent from the current `routing.yaml` (removed or not yet added), this is low-risk, but it should be corrected.

**Fix:** Update line 8 to:
```yaml
# Subagent resolution order:
#   overrides[agent] > phases[phase].categories[cat] > phases[phase].model > defaults.categories[cat] > defaults.model
```

---

### Finding 5: `--phase` / `PHASE` is a no-op stub (informational)

**File:** `scripts/dispatch.sh`, lines 233–240, 337–340
**Severity:** Informational / not a defect

`PHASE` is parsed and echoed to stderr but never stored, passed to the routing library, or used in any way. The comment says "stored for future B2 phase-aware dispatch." This is an intentional forward stub — the flag exists so callers can already pass `--phase` without breaking, and B2 will wire it up.

No action needed, but the `echo "Phase context: $PHASE" >&2` on line 339 is noisy for operators. Consider suppressing it or wrapping it in a debug-mode check until B2 is implemented.

---

## Improvements (Non-blocking)

### I1: `_routing_load_cache` error path could be clearer

When `_routing_find_config` fails (no routing.yaml found), `_routing_load_cache` sets `_ROUTING_CACHE_POPULATED=1` and returns 0. This means all resolvers silently return empty. The silent behavior is intentional (fallback to agent frontmatter), but a debug-level message would aid troubleshooting:

```bash
_ROUTING_CONFIG_PATH="$(_routing_find_config)" || {
  # No routing.yaml found — all resolvers will return empty (callers use their own defaults)
  _ROUTING_CACHE_POPULATED=1
  return 0
}
```

The comment already explains this. The improvement would be an optional `[[ "${ROUTING_DEBUG:-}" == "1" ]] && echo "lib-routing: no config found, using defaults" >&2` for debug tracing.

### I2: `routing_list_mappings` guard condition logic could be simplified

Line 301:
```bash
if [[ -z "$_ROUTING_CACHE_POPULATED" || -z "$_ROUTING_CONFIG_PATH" ]]; then
  echo "No routing.yaml found. Using agent frontmatter defaults."
  return 0
fi
```

After calling `_routing_load_cache`, `_ROUTING_CACHE_POPULATED` is always non-empty (set to 1). The `[[ -z "$_ROUTING_CACHE_POPULATED" ]]` branch can never be true at this point. The meaningful check is only `[[ -z "$_ROUTING_CONFIG_PATH" ]]`. Simplify to:

```bash
if [[ -z "$_ROUTING_CONFIG_PATH" ]]; then
  echo "No routing.yaml found. Using agent frontmatter defaults."
  return 0
fi
```

### I3: Phase names in routing.yaml diverge from documented sprint phase names

The routing.yaml uses phases: `brainstorm`, `brainstorm-reviewed`, `strategized`, `planned`, `executing`, `shipping`, `reflect`, `done`. The dispatch.sh `--phase` help says "Sprint phase context." Callers need to know these exact strings to get phase-aware routing. Consider adding a reference to the canonical phase list (e.g., from intercore/interphase) in the routing.yaml comment header, or validating the phase name against the known list.

---

## What Is Working Well

- **Source-once guard** (line 11: `[[ -n "${_ROUTING_LOADED:-}" ]] && return 0`) and **cache-once guard** (line 53: `[[ -n "$_ROUTING_CACHE_POPULATED" ]] && return 0`) are correctly implemented as separate concerns.
- **Config search order** in `_routing_find_config` (script-relative → `CLAVAIN_SOURCE_DIR` → plugin cache) mirrors the existing pattern from the old tiers.yaml loader. Correct and consistent.
- **Comment stripping** using `${BASH_REMATCH[1]%%[[:space:]#]*}` correctly handles inline YAML comments without false positives for model names.
- **`routing_resolve_dispatch_tier` fallback chain** is capped at 3 hops to prevent infinite loops.
- **`resolve_tier_model` in dispatch.sh** is significantly cleaner than the old inline YAML parser it replaced — the separation of concerns is a clear improvement.
- **`routing_resolve_model` priority chain** (lines 239–270) is readable and correctly ordered with explicit named steps.
- **`set -euo pipefail`** is present in `dispatch.sh`. `lib-routing.sh` inherits it when sourced.
- **`shellcheck source=lib-routing.sh`** annotation is present in `dispatch.sh`.
- **Naming consistency**: all public functions use the `routing_` prefix, all internal functions use `_routing_` prefix, all cache variables use `_ROUTING_` prefix. Clean namespace.
