# Functional Test: Key Clavain Scripts

**Date:** 2026-02-22
**Working directory:** /home/mk/projects/Demarch
**Clavain root:** /home/mk/projects/Demarch/os/clavain

## Test Results

### 1. dispatch.sh — Agent Dispatch Engine

**Path:** `os/clavain/scripts/dispatch.sh`

#### Test: `--help`
- **Exit code:** 0
- **Result:** PASS
- **Output (first 5 lines):**
  ```
  clavain dispatch — wraps codex exec with sensible defaults

  Usage:
    dispatch.sh [OPTIONS] "prompt"
    dispatch.sh [OPTIONS] --prompt-file <file>
  ```
- **Notes:** Comprehensive help output. Documents all options including `-C`, `-o`, `-s`, `-m`, `--tier`, `--phase`, `--inject-docs`, `--name`, `--prompt-file`, `--template`, `--dry-run`. Includes usage examples.

#### Test: `--dry-run` (no prompt)
- **Exit code:** 1
- **Result:** PASS (correct error behavior)
- **Output:**
  ```
  Error: No prompt provided
  Usage: dispatch.sh -C <dir> -o <output> [OPTIONS] "prompt"
         dispatch.sh --prompt-file <file> [OPTIONS]
         dispatch.sh --help for all options
  ```
- **Notes:** Correctly validates that a prompt is required. `--dry-run` alone is not enough; it needs a prompt to dry-run.

---

### 2. lib-routing.sh — Routing Library

**Path:** `os/clavain/scripts/lib-routing.sh`

#### Test: Source and check functions
- **Exit code:** 0
- **Result:** PASS (with naming clarification)
- **Output:**
  ```
  declare -f _routing_find_config
  declare -f _routing_load_cache
  declare -f routing_classify_complexity
  declare -f routing_list_mappings
  declare -f routing_resolve_dispatch_tier
  declare -f routing_resolve_dispatch_tier_complex
  declare -f routing_resolve_model
  declare -f routing_resolve_model_complex
  ```
- **Notes:** The original test looked for `routing_resolve` and `routing_list_routes` — these function names do not exist. The actual public API functions are:
  - `routing_resolve_model` (not `routing_resolve`)
  - `routing_list_mappings` (not `routing_list_routes`)
  - `routing_resolve_dispatch_tier`
  - `routing_classify_complexity`
  - `routing_resolve_model_complex`
  - `routing_resolve_dispatch_tier_complex`
  - Plus 2 private helpers: `_routing_find_config`, `_routing_load_cache`

  The library file header documents the correct API:
  ```
  # Public API (B1 — static routing):
  #   routing_resolve_model --phase <phase> [--category <cat>] [--agent <name>]
  #   routing_resolve_dispatch_tier <tier-name>
  #   routing_list_mappings
  #
  # Public API (B2 — complexity-aware routing):
  #   routing_classify_complexity --prompt-tokens <n> [--file-count <n>] [--reasoning-depth <n>]
  #   routing_resolve_model_complex --complexity <tier> [--phase ...] [--category ...] [--agent ...]
  #   routing_resolve_dispatch_tier_complex --complexity <tier> <tier-name>
  ```

  All 8 functions (6 public + 2 private) are properly exported. Library sources cleanly with no errors.

---

### 3. check-versions.sh — Version Consistency Checker

**Path:** `os/clavain/scripts/check-versions.sh`

#### Test: Run from Demarch root
- **Exit code:** 1
- **Result:** FAIL (location-dependent)
- **Output:**
  ```
  Error: No .claude-plugin/plugin.json found at /home/mk/projects/Demarch
  ```

#### Test: Run from Clavain directory
- **Exit code:** 1
- **Result:** PASS* (correctly detects real version drift)
- **Output:**
  ```
  Marketplace version drift!
    plugin.json:    0.6.60
    marketplace:    0.6.59

  Run: scripts/bump-version.sh 0.6.60
  ```
- **Notes:** The script itself works correctly — it must be run from the Clavain root (or any directory with a `.claude-plugin/plugin.json`). When run from the correct location, it successfully detects a real version drift between `plugin.json` (0.6.60) and the marketplace catalog (0.6.59). Exit code 1 is correct behavior when drift is detected. **The script functions as designed; the version drift is a real issue that should be resolved.**

---

### 4. bump-version.sh — Version Bumper

**Path:** `os/clavain/scripts/bump-version.sh`

#### Test: Run with no arguments
- **Exit code:** 1
- **Result:** PASS (correct usage error)
- **Output:**
  ```
  Usage: /home/mk/projects/Demarch/scripts/interbump.sh <version> [--dry-run]
    version   Semver string, e.g. 0.5.0
    --dry-run Show what would change without writing
  ```
- **Notes:** The script delegates to `/home/mk/projects/Demarch/scripts/interbump.sh` (the monorepo-level version bumper). It correctly shows usage when no version argument is provided. The exit code 1 is appropriate for a missing required argument. Note: the usage message shows the `interbump.sh` path rather than `bump-version.sh` — this is a minor cosmetic issue since `bump-version.sh` is a thin wrapper.

---

### 5. codex-bootstrap.sh — Codex Environment Bootstrap

**Path:** `os/clavain/scripts/codex-bootstrap.sh`

#### Test: `--help`
- **Exit code:** 0
- **Result:** PASS
- **Output:**
  ```
  Usage:
    codex-bootstrap.sh [options]

  Options:
    --source PATH     Use this Clavain checkout as source.
    --check-only      Do not run install/refresh; doctor only.
    --json            Print doctor output as JSON.
    -h, --help        Show this help.
  ```
- **Notes:** Clean help output with all options documented. Supports `--source`, `--check-only`, `--json`, and `-h`/`--help`.

---

### 6. sync-upstreams.sh — Upstream Sync Engine

**Path:** `os/clavain/scripts/sync-upstreams.sh`

#### Test: `--help`
- **Exit code:** 0
- **Result:** PASS
- **Output:**
  ```
  Usage: os/clavain/scripts/sync-upstreams.sh [--dry-run] [--auto] [--upstream NAME] [--no-ai] [--report [FILE]]

  Modes:
    (default)    Interactive — prompts for divergent files
    --dry-run    Preview classification, no file changes
    --auto       Non-interactive — applies COPY/AUTO, AI-resolves conflicts
    --upstream   Sync a single upstream by name

  Options:
    --no-ai      Disable AI conflict analysis (skip conflicts in auto, raw diff in interactive)
    --report     Generate markdown sync report (optionally to FILE, otherwise stdout)
  ```

#### Test: `--dry-run`
- **Exit code:** 0
- **Result:** PASS
- **Output (full):**
  ```
  === Clavain Upstream Sync ===
  Mode: dry-run  AI: true  Report: false
  Upstreams dir: /root/projects/upstreams

  --- beads ---
    444 new commits (4a90496 -> 4bdbba91)
    Summary: 0 copied, 0 auto, 0 kept, 0 conflict, 0 skipped, 0 review

  --- oracle ---
    2 new commits (5f3aef5 -> abc23048)
    Summary: 0 copied, 0 auto, 0 kept, 0 conflict, 0 skipped, 0 review

  --- superpowers ---
    16 new commits (a98c5df -> e4a2375)
    CONFLICT skills/brainstorming/SKILL.md
    CONFLICT skills/using-clavain/SKILL.md
    CONFLICT skills/writing-plans/SKILL.md
    Summary: 0 copied, 0 auto, 0 kept, 3 conflict, 0 skipped, 0 review

  --- superpowers-lab ---
    No new commits (HEAD: 897eebf)

  --- superpowers-dev ---
    No new commits (HEAD: 74afe93)

  --- compound-engineering ---
    60 new commits (e8f3bbc -> 63e76cf)
    Summary: 0 copied, 0 auto, 0 kept, 0 conflict, 0 skipped, 0 review

  === Summary ===
    Copied:       0
    Auto-applied: 0
    Kept local:   0
    Conflicts:    3 (0 AI-resolved)
    Skipped:      0
    Review:       0
    (dry-run -- no files were modified)
  ```
- **Notes:** Excellent output. Scans 6 upstreams (beads, oracle, superpowers, superpowers-lab, superpowers-dev, compound-engineering). Detects 3 real conflicts in the `superpowers` upstream for skill files. Dry-run mode correctly does not modify any files. The `beads` upstream shows 444 new commits — a significant upstream divergence.

---

### 7. Hook Libraries — Sourcing Verification

**Path:** `os/clavain/hooks/lib*.sh`

All 9 hook libraries were tested by sourcing them and checking for exported functions.

| Library | Source Result | Exit Code | Sample Functions | Result |
|---------|-------------|-----------|-----------------|--------|
| `hooks/lib.sh` | sourced OK | 0 | `_claude_project_dir`, `_detect_inflight_agents`, `_discover_beads_plugin`, `_discover_interflux_plugin`, `_discover_interlock_plugin` | PASS |
| `hooks/lib-intercore.sh` | sourced OK | 0 | `intercore_agency_load`, `intercore_agency_validate`, `intercore_available`, `intercore_check_or_die`, `intercore_cleanup_stale` | PASS |
| `hooks/lib-sprint.sh` | sourced OK | 0 | (inherits lib.sh functions) `_claude_project_dir`, `_detect_inflight_agents`, etc. | PASS |
| `hooks/lib-interspect.sh` | sourced OK | 0 | `_interspect_apply_override_locked`, `_interspect_apply_routing_override`, `_interspect_blacklist_pattern`, `_interspect_check_canaries`, `_interspect_classify_pattern` | PASS |
| `hooks/lib-signals.sh` | sourced OK | 0 | `detect_signals` | PASS |
| `hooks/lib-verdict.sh` | sourced OK | 0 | `verdict_clean`, `verdict_count_by_status`, `verdict_get_attention`, `verdict_init`, `verdict_parse_all` | PASS |
| `hooks/lib-spec.sh` | sourced OK | 0 | `spec_available`, `spec_get_agents`, `spec_get_budget`, `spec_get_companion`, `spec_get_default` | PASS |
| `hooks/lib-discovery.sh` | sourced OK | 0 | (inherits lib.sh functions) `_claude_project_dir`, `_detect_inflight_agents`, etc. | PASS |
| `hooks/lib-gates.sh` | sourced OK | 0 | (inherits lib.sh functions) `_claude_project_dir`, `_detect_inflight_agents`, etc. | PASS |

- **Notes:** All 9 libraries source without errors. Libraries like `lib-sprint.sh`, `lib-discovery.sh`, and `lib-gates.sh` appear to be shims that source `lib.sh` and may add their own functions beyond the first 5 shown. The core libraries (`lib-intercore.sh`, `lib-interspect.sh`, `lib-signals.sh`, `lib-verdict.sh`, `lib-spec.sh`) each expose a focused, well-namespaced API.

---

## Summary Table

| # | Script/Library | Test | Exit Code | Result | Notes |
|---|---------------|------|-----------|--------|-------|
| 1a | `dispatch.sh` | `--help` | 0 | **PASS** | Full help with examples |
| 1b | `dispatch.sh` | `--dry-run` (no prompt) | 1 | **PASS** | Correct validation error |
| 2 | `lib-routing.sh` | Source + check functions | 0 | **PASS** | 8 functions exported (6 public, 2 private). Test searched for wrong names |
| 3a | `check-versions.sh` | From Demarch root | 1 | **FAIL** | Requires cwd to have `.claude-plugin/plugin.json` |
| 3b | `check-versions.sh` | From Clavain root | 1 | **PASS*** | Correctly detects real version drift (0.6.60 vs 0.6.59) |
| 4 | `bump-version.sh` | No args | 1 | **PASS** | Shows interbump.sh usage; delegates correctly |
| 5 | `codex-bootstrap.sh` | `--help` | 0 | **PASS** | Clean help output |
| 6a | `sync-upstreams.sh` | `--help` | 0 | **PASS** | Documents all modes and options |
| 6b | `sync-upstreams.sh` | `--dry-run` | 0 | **PASS** | Scans 6 upstreams, finds 3 real conflicts |
| 7a | `hooks/lib.sh` | source | 0 | **PASS** | 5+ functions |
| 7b | `hooks/lib-intercore.sh` | source | 0 | **PASS** | 5+ intercore_* functions |
| 7c | `hooks/lib-sprint.sh` | source | 0 | **PASS** | Sources lib.sh |
| 7d | `hooks/lib-interspect.sh` | source | 0 | **PASS** | 5+ _interspect_* functions |
| 7e | `hooks/lib-signals.sh` | source | 0 | **PASS** | `detect_signals` function |
| 7f | `hooks/lib-verdict.sh` | source | 0 | **PASS** | 5+ verdict_* functions |
| 7g | `hooks/lib-spec.sh` | source | 0 | **PASS** | 5+ spec_* functions |
| 7h | `hooks/lib-discovery.sh` | source | 0 | **PASS** | Shim -> sources lib.sh |
| 7i | `hooks/lib-gates.sh` | source | 0 | **PASS** | Shim -> sources lib.sh |

**Overall: 17/18 tests PASS, 1 expected-context FAIL (check-versions.sh requires cwd inside a plugin directory)**

*Exit code 1 is correct behavior when version drift is detected — the script works, the drift is the real issue.*

## Issues Found

1. **Version drift (real issue):** `plugin.json` is at 0.6.60 but the marketplace catalog is at 0.6.59. The `check-versions.sh` script correctly detects this and recommends running `scripts/bump-version.sh 0.6.60`.

2. **check-versions.sh is location-sensitive:** Must be run from a directory containing `.claude-plugin/plugin.json`. Running from the monorepo root fails. This is by design (it is a per-plugin script) but could benefit from a `--plugin-dir` flag or auto-detection of the nearest plugin root.

3. **lib-routing.sh API naming mismatch in test:** The test checked for `routing_resolve` and `routing_list_routes`, but the actual functions are `routing_resolve_model` and `routing_list_mappings`. The library's public API is well-documented in its header comments.

4. **bump-version.sh usage message:** Shows the path to `interbump.sh` rather than `bump-version.sh` in its usage line. Minor cosmetic issue since it is a thin wrapper.

5. **Upstream divergence:** `sync-upstreams.sh --dry-run` reveals 3 unresolved conflicts in the `superpowers` upstream (skills/brainstorming, skills/using-clavain, skills/writing-plans) and significant commit divergence across upstreams (444 commits in beads, 60 in compound-engineering).
