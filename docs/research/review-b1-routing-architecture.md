# Architecture Review: B1 Static Routing Table

**Date:** 2026-02-21
**Scope:** config/routing.yaml, scripts/lib-routing.sh, scripts/dispatch.sh (modified), commands/model-routing.md (modified)
**Reviewer:** fd-architecture (Flux-drive)

---

## Project Context

Clavain is a pure shell/markdown Claude Code plugin — no build step, no compiled binary. Config is read at runtime by bash scripts. The established convention for shared shell logic is sourced `.sh` libraries in `scripts/` (e.g., lib-sprint.sh, lib-gates.sh, lib-interspect.sh). `dispatch.sh` previously owned inline YAML parsing for `config/dispatch/tiers.yaml`.

---

## What Changed

1. `config/routing.yaml` — New unified config replacing the deleted `config/dispatch/tiers.yaml`. Two namespaces: `subagents:` (Claude model aliases) and `dispatch:` (Codex model IDs). Supports nested inheritance: defaults → phases → overrides.
2. `scripts/lib-routing.sh` — New shared shell library. Parses routing.yaml into global associative arrays on first load (singleton via `_ROUTING_LOADED` guard). Public API: `routing_resolve_model`, `routing_resolve_dispatch_tier`, `routing_list_mappings`.
3. `scripts/dispatch.sh` — Sources lib-routing.sh at load time. `resolve_tier_model()` trimmed from ~100 to ~25 lines. Added `--phase` flag (stores to `$PHASE`, echoes to stderr, not yet used).
4. `commands/model-routing.md` — Updated `status`/`economy`/`quality` branches to read/write `routing.yaml` first, fall back to agent frontmatter.

---

## Findings Index

| SEVERITY | ID | Section | Title |
|----------|----|---------|-------|
| MUST-FIX | B1-01 | Boundaries & Coupling | dispatch.sh sources lib-routing.sh unconditionally at script load — sourcing failure exits the entire script |
| MUST-FIX | B1-02 | Boundaries & Coupling | model-routing.md sed patterns are fragile YAML mutators that can corrupt routing.yaml |
| NEEDS-ATTENTION | B1-03 | Pattern Analysis | `--phase` flag is parsed, stored, and echoed but has no callers and no effect — premature extensibility point |
| NEEDS-ATTENTION | B1-04 | Pattern Analysis | routing_resolve_model is implemented but has no callers in this diff; subagent dispatch path does not read it |
| IMPROVEMENT | B1-05 | Simplicity & YAGNI | `routing_list_mappings` output order is non-deterministic (associative array iteration) |
| IMPROVEMENT | B1-06 | Pattern Analysis | The `_ROUTING_LOADED` guard is correct but `_ROUTING_CACHE_POPULATED` is a separate redundant sentinel |

**Verdict: needs-changes**

---

## Summary

The consolidation from tiers.yaml into routing.yaml is architecturally sound: one config file, one parser, two consumers. The lib-routing.sh design follows the established lib-*.sh pattern in `scripts/` and `hooks/`. The critical problems are (1) an unconditional `source` call in dispatch.sh that will silently break dispatch if lib-routing.sh is ever missing from a cached plugin install, and (2) the model-routing.md command instructs Claude to mutate routing.yaml via multi-level sed range patterns that are brittle against any comment, blank-line, or indent variation. The `--phase` flag and `routing_resolve_model` function are correct forward-laying hooks but have no wiring yet, which creates hidden dead weight in the shipped code.

---

## Issues Found

**B1-01. MUST-FIX: Unconditional source of lib-routing.sh at dispatch.sh load time**

`dispatch.sh` line 37 unconditionally sources `lib-routing.sh`:

```bash
source "${DISPATCH_SCRIPT_DIR}/lib-routing.sh"
```

`set -euo pipefail` is active (line 10). If lib-routing.sh is absent — for example, in a plugin cache install where the file was not correctly bundled, or during a partially applied upstream sync — the `source` command fails and the entire dispatch.sh exits immediately, before any argument parsing. Any Codex dispatch call will fail silently with a non-obvious error. The old inline parser in dispatch.sh only ran inside `resolve_tier_model()`, which is only reached when `--tier` is passed. The new design makes the dependency unconditional and load-time.

Smallest fix: Guard the source with a file existence check and fall back gracefully:

```bash
if [[ -f "${DISPATCH_SCRIPT_DIR}/lib-routing.sh" ]]; then
  source "${DISPATCH_SCRIPT_DIR}/lib-routing.sh"
fi
```

Then in `resolve_tier_model()`, check whether `routing_resolve_dispatch_tier` is declared before calling it:

```bash
if declare -f routing_resolve_dispatch_tier >/dev/null 2>&1; then
  model="$(routing_resolve_dispatch_tier "$target_tier" 2>/dev/null)" || model=""
fi
```

This preserves the same degradation behavior the old inline parser had (warning + return 1 when config absent).

---

**B1-02. MUST-FIX: model-routing.md sed patterns are brittle YAML mutators**

The `economy` and `quality` branches instruct Claude to run multi-level sed range patterns against routing.yaml:

```bash
sed -i '/^subagents:/,/^dispatch:/{
  /^  defaults:/,/^  phases:/{
    s/^\(    model:\).*/\1 sonnet/
    /^    categories:/,/^  [a-z]/{
      s/^\(      research:\).*/\1 haiku/
      ...
    }
  }
}' config/routing.yaml
```

This is a YAML writer implemented as sed range patterns. The patterns depend on exact line ordering (e.g., `defaults:` must precede `phases:` in the file), exact indentation (4-space for `model:`, 6-space for categories), and no intervening blank lines or comments inside the matched range. The current routing.yaml satisfies these constraints. However:

- Adding a comment inside `defaults:` will break the range termination.
- Reordering `categories:` above `model:` inside defaults breaks the substitution.
- The `dispatch:` section presence is used as the range end anchor — if dispatch is moved or renamed, the sed range runs past the intended section.

More critically: the sed patterns are embedded in a markdown command file that Claude interprets and executes. This is a config mutation path where a partial match (sed runs but misses a line) leaves routing.yaml in a half-updated state with no error signal.

The correct fix is to write `scripts/set-routing-mode.sh economy|quality` — a small dedicated script that reads the file, validates it, writes target values explicitly, and exits non-zero on any ambiguity. The command file then simply calls that script. This moves mutable config logic from sed-in-markdown to a testable shell script, consistent with how other config mutations in this codebase are handled (via explicit scripts, not inline sed).

Until the script exists, the minimum safer alternative is to make the sed patterns fail-loudly: wrap them with a pre-check that reads and validates routing.yaml structure before mutating, and a post-check that reads back the expected values.

---

**B1-03. NEEDS-ATTENTION: `--phase` flag is a no-op extensibility point**

`dispatch.sh` accepts `--phase <NAME>` (line 233-237 of the modified file), stores it to `$PHASE`, and logs it to stderr:

```bash
if [[ -n "$PHASE" ]]; then
  echo "Phase context: $PHASE" >&2
fi
```

That is the complete effect. The value is not passed to Codex, not stored in a state file, not used in model resolution. The `routing_resolve_model` function in lib-routing.sh accepts `--phase` but is not called from dispatch.sh at all.

This is premature extensibility: a flag that exists only to mark a future hook point. In a CLI tool, accepting flags that do nothing creates user confusion (callers pass `--phase execute` and believe it affects routing) and creates dead code that must be maintained when B2 is actually built.

The correct path for a future B2 hook: do not add the flag to dispatch.sh until the resolution logic is wired. The plan document can describe the intended interface. Adding the flag and the echo at the same time as the routing library with no actual use is scope creep relative to B1's stated goal.

If keeping the flag for integration testing purposes, add an explicit `# NOT YET WIRED` comment at the echo site and document it clearly in `--help` output as "reserved for B2; no current effect".

---

**B1-04. NEEDS-ATTENTION: routing_resolve_model has no callers**

`lib-routing.sh` implements `routing_resolve_model` (lines 226-271) with a 5-priority resolution chain (override → phase+category → phase → category default → global default). It is the primary value-add of the B1 feature for subagent dispatch.

However, nothing in this diff calls it. The `model-routing.md` command reads routing.yaml only for status display and writes it for economy/quality toggle. The actual subagent dispatch paths (agent frontmatter `model:` fields) are not wired to routing.yaml. The function exists, is correctly implemented, but has no integration point.

This is not a bug in B1 if the intent is "config structure + parser now; subagent wiring in B2". But the framing of the feature ("unified model routing config replacing scattered config") implies the replacement is complete. If subagent frontmatter remains the actual routing mechanism, routing.yaml's `subagents:` section is a configuration island that does not control what it claims to control.

The recommended resolution: explicitly scope what B1 delivers. If B1 delivers only dispatch tier unification (tiers.yaml → routing.yaml) plus the schema and parser for subagent routing (to be wired in B2), document that in routing.yaml and in AGENTS.md. The current state is safe to ship as long as the scope is explicit. If the intent was to wire subagent routing, that work is missing from this diff.

---

## Improvements

**B1-05. routing_list_mappings output order is non-deterministic**

Bash associative arrays (`declare -gA`) do not preserve insertion order. `routing_list_mappings` iterates `${!_ROUTING_SA_DEFAULTS[@]}`, `${!_ROUTING_SA_PHASE_MODEL[@]}`, and `${!_ROUTING_DISPATCH_TIER[@]}` for display. The output order will vary across runs and bash versions. For a status command used interactively and potentially diffed, stable output is preferable.

Fix: collect keys into a sorted array before printing: `mapfile -t sorted_keys < <(printf '%s\n' "${!_ROUTING_SA_DEFAULTS[@]}" | sort)`. Applies to all three iteration sites in `routing_list_mappings`.

---

**B1-06. Dual-sentinel loading state (`_ROUTING_LOADED` + `_ROUTING_CACHE_POPULATED`) adds unnecessary complexity**

The library uses two guards: `_ROUTING_LOADED` (set to 1 at the last line of the file, prevents re-sourcing the entire script) and `_ROUTING_CACHE_POPULATED` (set inside `_routing_load_cache`, prevents re-parsing). The `_routing_load_cache` function checks `_ROUTING_CACHE_POPULATED` at entry. The `_ROUTING_LOADED` guard at the top of the file short-circuits the entire `source` call.

Because sourcing a bash file is idempotent for function definitions, the `_ROUTING_LOADED` guard only prevents re-declaring functions and re-declaring global variables. The `_ROUTING_CACHE_POPULATED` guard prevents re-parsing. Both are doing different jobs but the split is not obvious to a reader.

Simplification: one guard named `_LIB_ROUTING_INITIALIZED` checked at the top of the file, set at the bottom, covering both re-source and re-parse. The internal `_routing_load_cache` idempotency then relies on the outer guard rather than its own inner check. This removes one state variable and one check, making the loading lifecycle easier to audit.

This is a low-priority cleanup; the current behavior is correct.
