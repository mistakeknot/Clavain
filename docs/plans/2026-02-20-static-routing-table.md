# Plan: B1 — Static Routing Table

**Bead:** iv-dd9q
**Phase:** planned (as of 2026-02-21T04:24:15Z)
**PRD:** [2026-02-20-static-routing-table.md](../prds/2026-02-20-static-routing-table.md)
**Track:** B (Model Routing) — Step 1 of 3

## Current State

B1 is **partially implemented**. Previous work shipped:
- `config/routing.yaml` — exists but has wrong phase names and schema issues
- `scripts/lib-routing.sh` — exists but missing `inherit` handling and correctness fixes
- `dispatch.sh` — already sources `lib-routing.sh` (F3 complete)
- `config/dispatch/tiers.yaml` — already deleted (F3 complete)
- `commands/model-routing.md` — partially updated to read routing.yaml

**This plan addresses the remaining gaps** identified by flux-drive review.

## Tasks

### Task 1: Fix `config/routing.yaml` schema

**Files:** `hub/clavain/config/routing.yaml`
**Bead:** iv-i64p (F1)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

Changes:
1. **Fix phase names** — rename `strategy:` → `strategized:`, `plan:` → `planned:`, `execute:` → `executing:`, `quality-gates:` → remove (move review override to `executing:`), `ship:` → `shipping:`. Add missing phases: `brainstorm-reviewed:`, `reflect:`, `done:`.
2. **Remove `overrides` section** — per flux-drive review, conflicts with Interspect's `routing-overrides.json`. Remove entirely (including commented example).
3. **Move inline comments off value lines** — the parser strips them, but the PRD says "no inline comments on value lines." Move to comment-only lines above the key.
4. **Keep `subagents:` wrapper** — the parser already expects it. Changing to flat `defaults:`/`phases:` at top level would break the parser without benefit. The PRD schema shows flat but the existing parser is built for `subagents:`. Keep the parser's expectation.
5. **Update header comment** — document the corrected resolution order.

**Verification:** Parser loads file without error; `routing_resolve_model --phase executing --category review` returns `opus`.

### Task 2: Add `inherit` sentinel handling to `lib-routing.sh`

**Files:** `hub/clavain/scripts/lib-routing.sh`
**Bead:** iv-jayq (F2)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

Changes to `routing_resolve_model()`:
1. After each resolution step, check if the value is `inherit`. If so, skip to the next level.
2. If the entire chain resolves to `inherit`, return the hardcoded fallback `sonnet`.
3. `resolve_model` MUST never return the string `inherit` as a final value.

Implementation: add a wrapper around the current return logic:
```bash
local result=""
# ... existing resolution chain ...
# At the end:
if [[ "$result" == "inherit" || -z "$result" ]]; then
  result="${_ROUTING_SA_DEFAULT_MODEL:-sonnet}"
fi
if [[ "$result" == "inherit" ]]; then
  result="sonnet"  # ultimate fallback
fi
echo "$result"
```

**Verification:** Test with routing.yaml where `defaults.model: inherit` — should return `sonnet`.

### Task 3: Add `CLAVAIN_ROUTING_CONFIG` env var support

**Files:** `hub/clavain/scripts/lib-routing.sh`
**Bead:** iv-jayq (F2)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

Add to `_routing_find_config()` as the highest-priority path:
```bash
# 0. Explicit env var override
if [[ -n "${CLAVAIN_ROUTING_CONFIG:-}" && -f "$CLAVAIN_ROUTING_CONFIG" ]]; then
  echo "$CLAVAIN_ROUTING_CONFIG"
  return 0
fi
```

**Verification:** `CLAVAIN_ROUTING_CONFIG=/tmp/test.yaml routing_resolve_model` uses the specified file.

### Task 4: Add malformed config warning

**Files:** `hub/clavain/scripts/lib-routing.sh`
**Bead:** iv-jayq (F2)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

In `_routing_load_cache()`, after parsing completes, check if we got any meaningful data:
```bash
if [[ -n "$_ROUTING_CONFIG_PATH" && -z "$_ROUTING_SA_DEFAULT_MODEL" && ${#_ROUTING_SA_DEFAULTS[@]} -eq 0 ]]; then
  echo "Warning: routing.yaml exists but no subagent defaults were parsed — possible malformed config" >&2
fi
```

**Verification:** Create a routing.yaml with garbage content → stderr warning appears.

### Task 5: Fix resolution when `--category` is omitted

**Files:** `hub/clavain/scripts/lib-routing.sh`
**Bead:** iv-jayq (F2)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

Current behavior: `routing_resolve_model --phase brainstorm` correctly falls through to `phases[brainstorm].model` then `defaults.model` — this already works because the category check at step 2 requires `$category` to be non-empty.

**No code change needed.** The existing logic is correct: step 2 (`PHASE_CAT`) requires both `$phase` and `$category` to be non-empty. When `--category` is omitted, it skips directly to step 3 (`PHASE_MODEL`).

**Verification:** Add explicit test case in bats.

### Task 6: Write bats-core tests for `lib-routing.sh`

**Files:** `hub/clavain/tests/shell/test_routing.bats` (new file)
**Bead:** iv-jayq (F2)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

Test cases:
1. `resolve_model --phase executing --category review` → `opus` (phase-category override)
2. `resolve_model --phase executing --category research` → `haiku` (falls through to defaults.categories)
3. `resolve_model --phase brainstorm` → `opus` (phase model, no category)
4. `resolve_model --phase planned` → `sonnet` (phase model)
5. `resolve_model` (no args) → `sonnet` (default model)
6. `resolve_model --category research` → `haiku` (default category, no phase)
7. `inherit` sentinel: config with `defaults.model: inherit` → returns `sonnet` fallback
8. Missing config: `CLAVAIN_ROUTING_CONFIG=/nonexistent` → returns empty (caller's default)
9. Malformed config: garbage file → stderr warning
10. `resolve_dispatch_tier fast` → `gpt-5.3-codex-spark`
11. `resolve_dispatch_tier fast-clavain` → `gpt-5.3-codex-spark-xhigh`
12. Fallback chain: `resolve_dispatch_tier` with missing tier → follows fallback
13. Comment stripping: value with inline comment → comment not in result
14. `CLAVAIN_ROUTING_CONFIG` env var overrides default discovery

Pattern: Follow existing bats test structure in `test_lib_sprint.bats` — use `setup()` with temp dir, source lib-routing.sh, create test routing.yaml.

### Task 7: Update `commands/model-routing.md`

**Files:** `hub/clavain/commands/model-routing.md`
**Bead:** iv-sz5b (F4)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

Changes:
1. **Status output** — specify the exact format: mode label (`economy`/`quality`/`custom`), per-category defaults, per-phase overrides that differ from defaults.
2. **Economy mode** — writes economy defaults to routing.yaml (already partially in the command; verify correctness).
3. **Quality mode** — must write `inherit` at EVERY level in `phases` AND set `defaults.model: opus` and all `defaults.categories: opus`. Current implementation only writes `inherit` to defaults — that's the bug the correctness review caught.
4. **Remove sed-on-frontmatter** — the command currently also writes to agent frontmatter as a fallback. Remove that path since routing.yaml is now the source of truth.

### Task 8: Remove `model:` frontmatter from Clavain agents

**Files:** 4 agent `.md` files
**Bead:** iv-sz5b (F4)
**Phase:** planned (as of 2026-02-21T04:24:15Z)

Remove the `model: sonnet` line from frontmatter of:
- `agents/review/plan-reviewer.md` (line 4)
- `agents/review/data-migration-expert.md` (line 4)
- `agents/workflow/bug-reproduction-validator.md` (line 4)
- `agents/workflow/pr-comment-resolver.md` (line 5)

**Note:** Companion plugin agents (interflux, intercraft, intersynth) keep their frontmatter — deferred to B2.

## Execution Order

```
Task 1 (fix routing.yaml)     → independent
Task 2 (inherit handling)      → independent
Task 3 (env var)               → independent
Task 4 (malformed warning)     → independent
Task 5 (verify --category)     → independent (no code change)
Task 6 (bats tests)            → depends on Tasks 1-4 (tests validate the fixes)
Task 7 (model-routing command) → depends on Task 1 (needs correct phase names)
Task 8 (remove frontmatter)    → depends on Tasks 1-4 (routing.yaml must be correct first)
```

**Parallel batch 1:** Tasks 1, 2, 3, 4 (all independent edits to different files or sections)
**Sequential batch 2:** Task 6 (tests verify batch 1)
**Sequential batch 3:** Tasks 7, 8 (command update and frontmatter removal)

## Risk Assessment

**Low risk.** This is a config + shell library change. No new architecture. The routing.yaml and lib-routing.sh already exist and are wired into dispatch.sh. We're fixing correctness bugs and completing the last two features (command update + frontmatter removal).

**Rollback:** If something breaks, the agent frontmatter still exists until Task 8 removes it. Claude Code reads frontmatter as the default model — routing.yaml is an overlay, not a replacement. Task 8 should be the last step.

## Files Modified

| File | Change | Task |
|------|--------|------|
| `config/routing.yaml` | Fix phase names, remove overrides, fix comments | 1 |
| `scripts/lib-routing.sh` | Add inherit handling, env var, malformed warning | 2, 3, 4 |
| `tests/shell/test_routing.bats` | New test file | 6 |
| `commands/model-routing.md` | Fix status format, quality mode, remove sed path | 7 |
| `agents/review/plan-reviewer.md` | Remove `model:` line | 8 |
| `agents/review/data-migration-expert.md` | Remove `model:` line | 8 |
| `agents/workflow/bug-reproduction-validator.md` | Remove `model:` line | 8 |
| `agents/workflow/pr-comment-resolver.md` | Remove `model:` line | 8 |
