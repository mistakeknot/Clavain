# Quality & Consistency Review of Clavain

**Date:** 2026-02-11
**Reviewer:** fd-quality (Flux-drive Quality & Style)
**Scope:** Full plugin audit -- frontmatter, naming, counts, hooks, scripts, docs, dead code

---

## Executive Summary

Clavain is well-structured overall. The codebase exhibits strong naming consistency, clean namespace separation (no superpowers:/compound-engineering: contamination), and good shell script discipline. The main issues are **count mismatches across 5 documentation surfaces** (each claims different numbers), **6 fd-\* agents missing required `<example>` blocks**, **jq dependency risk in 2 hook scripts**, and **inconsistent hook invocation styles**. None are correctness bugs, but they create confusion for contributors and users.

**Severity breakdown:**
- P1 (should fix soon): 3 findings
- P2 (fix when convenient): 8 findings
- P3 (minor/cosmetic): 5 findings

---

## 1. Count Mismatches (P1)

### Actual component counts (from filesystem):

| Component | Actual Count |
|-----------|-------------|
| Skills | **33** |
| Agents | **16** (9 review + 5 research + 2 workflow) |
| Commands | **26** (not 25) |
| Hooks | **5** |
| MCP Servers | **2** |

### What each document claims:

| Document | Skills | Agents | Commands | Status |
|----------|--------|--------|----------|--------|
| **Actual filesystem** | 33 | 16 | **26** | Ground truth |
| `AGENTS.md` Quick Reference table (line 12) | 33 | 16 | **25** | WRONG (commands) |
| `AGENTS.md` Architecture tree (line 26) | **34** | 16 | -- | WRONG (skills) |
| `using-clavain/SKILL.md` (line 24) | **34** | 16 | **23** | WRONG (skills, commands) |
| `plugin.json` description (line 4) | 33 | 16 | **25** | WRONG (commands) |
| `agent-rig.json` description (line 4) | 33 | 16 | **23** | WRONG (commands) |
| `README.md` (line 7) | 33 | 16 | **25** | WRONG (commands) |
| `CLAUDE.md` validation comment | 33 | -- | **25** | WRONG (commands) |
| Test suite (`test_commands.py` line 23) | 33 | 16 | **26** | CORRECT |

**Root cause:** The `model-routing` command was added recently but documentation counts were not updated. The `using-clavain/SKILL.md` routing table has never been accurate since it was written (claims 34 skills and 23 commands).

### Recommended fix:

Update ALL of the following to `33 skills, 16 agents, 26 commands`:
- `/root/projects/Clavain/AGENTS.md` lines 12, 26
- `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 24
- `/root/projects/Clavain/.claude-plugin/plugin.json` line 4
- `/root/projects/Clavain/agent-rig.json` line 4
- `/root/projects/Clavain/README.md` line 7
- `/root/projects/Clavain/CLAUDE.md` validation section

---

## 2. Agent `<example>` Blocks Missing (P1)

AGENTS.md (line 129-130) states:

> Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger

Six agents violate this convention:

| Agent | File |
|-------|------|
| fd-architecture | `/root/projects/Clavain/agents/review/fd-architecture.md` |
| fd-correctness | `/root/projects/Clavain/agents/review/fd-correctness.md` |
| fd-performance | `/root/projects/Clavain/agents/review/fd-performance.md` |
| fd-quality | `/root/projects/Clavain/agents/review/fd-quality.md` |
| fd-safety | `/root/projects/Clavain/agents/review/fd-safety.md` |
| fd-user-product | `/root/projects/Clavain/agents/review/fd-user-product.md` |

All 6 are the core flux-drive agents. They have detailed system prompts but their `description` field is a single-line summary without `<example>` blocks. The other 10 agents all have proper example blocks.

**Mitigating factor:** These agents are typically dispatched programmatically by the flux-drive skill, not matched by Claude Code's agent routing. So the practical impact is low.

**Recommendation:** Either add example blocks to the descriptions (consistent with convention) or update AGENTS.md to explicitly exempt programmatically-dispatched agents from the example block requirement.

---

## 3. jq Dependency Risk in Hook Scripts (P1)

Two hook scripts use `jq` for parsing input JSON **without guarding** the dependency, then separately guard `jq` for output JSON:

### `/root/projects/Clavain/hooks/auto-compound.sh`

```bash
# Lines 24, 29 -- UNGUARDED jq usage (will fail under set -euo pipefail if jq missing)
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')

# Line 81 -- GUARDED jq usage (has fallback)
if command -v jq &>/dev/null; then
    jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'
else
    # fallback...
fi
```

### `/root/projects/Clavain/hooks/session-handoff.sh`

Same pattern: lines 22, 27 use `jq` without checking; line 84 guards it.

**Contrast with good pattern:** `/root/projects/Clavain/hooks/autopilot.sh` correctly guards ALL jq usage:

```bash
if command -v jq &>/dev/null; then
  FILE_PATH="$(jq -r '.tool_input.file_path // ...' 2>/dev/null)" || true
fi
```

**Recommendation:** Add `command -v jq` guard to the input-parsing sections of both scripts, or add an early exit at the top of each script if jq is not found:

```bash
if ! command -v jq &>/dev/null; then
    exit 0  # Can't parse hook input without jq
fi
```

---

## 4. Hook Invocation Style Inconsistency (P2)

The `hooks.json` file uses two different styles for invoking hook scripts:

| Event | Style | Command |
|-------|-------|---------|
| PreToolUse | `bash "quoted"` | `bash "${CLAUDE_PLUGIN_ROOT}/hooks/autopilot.sh"` |
| SessionStart | bare unquoted | `${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh` |
| Stop (compound) | `bash "quoted"` | `bash "${CLAUDE_PLUGIN_ROOT}/hooks/auto-compound.sh"` |
| Stop (handoff) | `bash "quoted"` | `bash "${CLAUDE_PLUGIN_ROOT}/hooks/session-handoff.sh"` |
| SessionEnd | bare unquoted | `${CLAUDE_PLUGIN_ROOT}/hooks/dotfiles-sync.sh` |

All scripts have `#!/usr/bin/env bash` shebangs and `+x` permissions (except `lib.sh`, which is sourced, not executed). The bare invocation style relies on the execute bit being set, while the `bash` prefix style does not.

**Recommendation:** Pick one style and apply it consistently. The `bash "quoted"` style is more defensive since it doesn't depend on file permissions surviving packaging/installation.

---

## 5. Documentation vs Reality: Agent Model Field (P2)

AGENTS.md (line 129) states:

> `model` (usually `inherit`)

In practice, **zero** agents use `inherit`:

| Category | Actual Model | Count |
|----------|-------------|-------|
| Review | `sonnet` | 9 |
| Research | `haiku` | 5 |
| Workflow | `sonnet` | 2 |

This is deliberate -- the `model-routing` command explicitly implements this as the "economy" default. But AGENTS.md should reflect reality.

**Recommendation:** Change AGENTS.md line 129 from "usually `inherit`" to "typically `sonnet` for review/workflow, `haiku` for research (see `/model-routing` command)".

---

## 6. Skills Missing from Routing Table (P2)

Three skills are not mentioned anywhere in `/root/projects/Clavain/skills/using-clavain/SKILL.md`:

| Skill | What It Does |
|-------|-------------|
| `prompterpeer` | Oracle prompt optimizer with human review |
| `splinterpeer` | AI disagreement extraction into artifacts |
| `winterpeer` | LLM Council review for critical decisions |

These are all interpeer escalation modes. The `interpeer` skill IS mentioned, and it internally references these, but the routing table provides no path to discover them directly.

**Recommendation:** Add these to the routing table, either as a sub-list under the "Cross-AI Review" section or as entries in the Review stage row.

Additionally, the `clodex-toggle` and `fixbuild` commands are not mentioned in the routing table. The `model-routing` command is also missing from the table.

---

## 7. `lib.sh` Missing `set -euo pipefail` (P2)

`/root/projects/Clavain/hooks/lib.sh` does not include `set -euo pipefail`. AGENTS.md (line 163) requires it:

> Use `set -euo pipefail` in all hook scripts

**Mitigating factor:** `lib.sh` is sourced (not executed directly), so it inherits the caller's shell options. The only caller (`session-start.sh`) does set strict mode. However, if `lib.sh` were sourced by a script that forgot strict mode, the function would still work but error handling would be weaker.

**Recommendation:** Add `set -euo pipefail` at the top of `lib.sh` for defense-in-depth, or update AGENTS.md to note that sourced utility files are exempt.

---

## 8. `check-versions.sh` Missing Strict Mode (P2)

`/root/projects/Clavain/scripts/check-versions.sh` uses `set -e` but not `set -euo pipefail`:

```bash
#!/bin/bash
set -e
```

All other scripts in the project use `set -euo pipefail`. The script uses `$1` without `${1:-}` quoting on line 38, so adding `-u` would require that fix.

**Recommendation:** Add `set -euo pipefail` and change `$1` to `${1:-}`.

---

## 9. Shebang Inconsistency in Scripts (P3)

Most scripts use `#!/usr/bin/env bash` but two use `#!/bin/bash`:

| Script | Shebang |
|--------|---------|
| `/root/projects/Clavain/scripts/bump-version.sh` | `#!/bin/bash` |
| `/root/projects/Clavain/scripts/check-versions.sh` | `#!/bin/bash` |
| All others | `#!/usr/bin/env bash` |

**Recommendation:** Standardize on `#!/usr/bin/env bash` for portability.

---

## 10. Extra/Non-Standard Frontmatter Fields (P3)

Some skills use frontmatter fields not documented in AGENTS.md conventions:

| Skill | Extra Fields | Risk |
|-------|-------------|------|
| `clodex` | `version` | Unused by Claude Code plugin system |
| `engineering-docs` | `allowed-tools`, `preconditions` | May be ignored by runtime |
| `file-todos` | `disable-model-invocation` | Valid Claude Code field |
| `slack-messaging` | `user-invocable`, `allowed-tools` | Valid Claude Code fields |

One agent has an extra field:

| Agent | Extra Field |
|-------|------------|
| `pr-comment-resolver` | `color: blue` |

**Recommendation:** Remove `version` from `clodex` frontmatter (not a standard field). Document `allowed-tools`, `preconditions`, `disable-model-invocation`, and `user-invocable` as optional fields in AGENTS.md if they are intentionally used. Remove `color` from `pr-comment-resolver` if it has no effect.

---

## 11. `autopilot.sh` Does Not Read stdin (P3)

The `autopilot.sh` hook receives tool call JSON on stdin (as documented in its header comment), but it does NOT read stdin with `cat` or any input command. It only checks environment variables and file existence. The JSON payload goes unused.

This works correctly because the hook only needs `$CLAUDE_PROJECT_DIR` and file paths, not the tool input JSON... except it DOES use `jq` to parse stdin for the file path on line 33-34:

```bash
if command -v jq &>/dev/null; then
  FILE_PATH="$(jq -r '.tool_input.file_path // ...' 2>/dev/null)" || true
fi
```

This is actually correct -- `jq` reads from stdin implicitly. No issue here. The stdin data flows directly to jq without an intermediate variable, which is the efficient approach.

---

## 12. Namespace Contamination (CLEAN)

Grep across all active code directories confirms zero contamination:

- `superpowers:` -- 0 matches in skills/, agents/, commands/, hooks/
- `compound-engineering:` -- 0 matches in skills/, agents/, commands/, hooks/
- `ralph-wiggum:` -- 0 matches
- `/workflows:` -- 0 matches
- `Every.to` -- 0 matches
- `rails_model` / `hotwire_turbo` / `brief_system` -- 0 matches
- `/deepen-plan` -- 0 matches

---

## 13. Naming Consistency (CLEAN)

All naming checks pass:

- All 33 skill frontmatter `name` fields match their directory names
- All 26 command frontmatter `name` fields match their filenames (minus `.md`)
- All 16 agent frontmatter `name` fields match their filenames (minus `.md`)
- All names use consistent kebab-case
- No phantom `clavain:` references found (all point to existing components)

---

## 14. Dead Code Check (CLEAN)

All scripts in `scripts/` are referenced by at least one other file:

| Script | Referenced By |
|--------|--------------|
| `bump-version.sh` | CLAUDE.md, check-versions.sh, session-start.sh, docs |
| `check-versions.sh` | docs/research |
| `clone-upstreams.sh` | sync-upstreams.sh, pull-upstreams.sh |
| `debate.sh` | commands/debate.md, AGENTS.md, README.md |
| `dispatch.sh` | skills/clodex, AGENTS.md, commands/setup.md |
| `install-codex.sh` | agent-rig.json, AGENTS.md, README.md |
| `pull-upstreams.sh` | clone-upstreams.sh, docs |
| `sync-upstreams.sh` | .github/workflows/sync.yml |
| `upstream-check.sh` | skills/upstream-sync, AGENTS.md, workflows |
| `validate-roster.sh` | docs/plans, docs/solutions |
| `upstream-impact-report.py` | AGENTS.md, workflows |

No unreferenced scripts found.

---

## 15. Shell Script Quality Summary

| Script | Shebang | Strict Mode | jq Guard | Overall |
|--------|---------|-------------|----------|---------|
| `hooks/session-start.sh` | env bash | euo pipefail | N/A | Good |
| `hooks/auto-compound.sh` | env bash | euo pipefail | **Partial** (output only) | Needs fix |
| `hooks/session-handoff.sh` | env bash | euo pipefail | **Partial** (output only) | Needs fix |
| `hooks/autopilot.sh` | env bash | euo pipefail | Full | Good |
| `hooks/dotfiles-sync.sh` | env bash | euo pipefail | N/A | Good |
| `hooks/lib.sh` | env bash | **Missing** | N/A | Minor |
| `scripts/bump-version.sh` | /bin/bash | euo pipefail | N/A | Shebang |
| `scripts/check-versions.sh` | /bin/bash | **set -e only** | N/A | Needs fix |
| All other scripts | env bash | euo pipefail | N/A | Good |

---

## Summary of Recommended Actions

### P1 -- Fix Soon

1. **Update component counts** in 6+ documents to `33 skills, 16 agents, 26 commands`
2. **Add `<example>` blocks** to 6 fd-\* agent descriptions, or update AGENTS.md to exempt them
3. **Guard jq dependency** in `auto-compound.sh` and `session-handoff.sh` input parsing

### P2 -- Fix When Convenient

4. **Standardize hook invocation style** in `hooks.json` (pick `bash "quoted"` or bare)
5. **Update AGENTS.md** agent model field docs from "usually inherit" to actual defaults
6. **Add missing skills/commands to routing table** (prompterpeer, splinterpeer, winterpeer, clodex-toggle, fixbuild, model-routing)
7. **Add `set -euo pipefail` to `lib.sh`** or document exemption
8. **Fix `check-versions.sh`** strict mode (`set -euo pipefail` + `${1:-}`)

### P3 -- Minor/Cosmetic

9. **Standardize shebangs** to `#!/usr/bin/env bash`
10. **Clean up non-standard frontmatter fields** (clodex `version`, pr-comment-resolver `color`)
11. **Document optional frontmatter fields** in AGENTS.md (allowed-tools, preconditions, etc.)
