# Bulk Rename: clodex -> interserve in interflux plugin

**Date:** 2026-02-16
**Status:** Complete

---

## Summary

Performed a bulk rename of `clodex` -> `interserve` across 6 files in the interflux plugin at `/root/projects/Interverse/plugins/interflux/`. All instances of `clodex` (lowercase), `Clodex` (title case), and the derived term `Codex spark`/`Codex Spark` (the feature name within slicing.md) were renamed. No `CLODEX` (all-caps) instances were found.

---

## Files Updated

### 1. `plugins/interflux/skills/flux-drive/phases/slicing.md`

**Changes (5 replacements):**
- Line 191: `(Codex Spark)` -> `(Interserve Spark)` (method heading)
- Line 191: `clodex MCP` -> `interserve MCP`
- Line 193: `Invoke clodex extract_sections` -> `Invoke interserve extract_sections`
- Line 194: `Invoke clodex classify_sections` + `Codex spark assigns` -> `Invoke interserve classify_sections` + `Interserve spark assigns`
- Line 201: `Codex spark is unavailable` -> `Interserve spark is unavailable`

### 2. `plugins/interflux/skills/flux-drive/phases/launch.md`

**Changes (2 replacements):**
- Line 91: `Invoke clodex MCP classify_sections` -> `Invoke interserve MCP classify_sections`
- Line 93: Step 2.1c Case 2 classification tool reference

### 3. `plugins/interflux/skills/flux-drive/phases/launch-codex.md`

**Changes (5 replacements):**
- Line 13-14: Path `*/skills/clodex/templates/review-agent.md` -> `*/skills/interserve/templates/review-agent.md` (2 find commands)
- Line 44-45: Path `*/skills/clodex/templates/create-review-agent.md` -> `*/skills/interserve/templates/create-review-agent.md` (2 find commands)
- Line 97: `clodex mode` -> `interserve mode`, `.claude/clodex-toggle.flag` -> `.claude/interserve-toggle.flag`

**Preserved Codex CLI references** (14 instances): These all refer to the external Codex CLI product, not the clodex feature. Examples: "Codex Dispatch", "Codex CLI", "DISPATCH_MODE = codex", "Codex timeout", "launch-codex.md". These correctly remain unchanged.

### 4. `plugins/interflux/skills/flux-drive/SKILL.md`

**Changes (2 replacements):**
- Line 417: `If clodex mode is detected` -> `If interserve mode is detected`
- Line 447: `When clodex mode is active` + `clavain:clodex` -> `When interserve mode is active` + `clavain:interserve`

### 5. `plugins/interflux/skills/flux-drive/references/agent-roster.md`

**Changes (1 replacement):**
- Line 13: `clodex mode is active` -> `interserve mode is active`; `clodex mode is NOT active` -> `interserve mode is NOT active`

### 6. `plugins/interflux/docs/brainstorms/2026-02-14-flux-research-brainstorm.md`

**Changes (1 replacement):**
- Line 512: `Codex dispatch (clodex mode)` -> `Codex dispatch (interserve mode)`

---

## Patterns Applied

| Pattern | Occurrences Found | Occurrences Changed |
|---------|-------------------|---------------------|
| `clodex` (lowercase) | 12 | 12 |
| `Clodex` (title case) | 0 | 0 |
| `CLODEX` (all caps) | 0 | 0 |
| `Codex Spark` / `Codex spark` (feature name) | 3 | 3 |
| `clodex-toggle.flag` | 1 | 1 (now `interserve-toggle.flag`) |
| `/clodex` (slash command path) | 0 | 0 (none found in interflux) |

**Total replacements: 16**

---

## Verification

Post-edit grep for `clodex|Clodex|CLODEX` across entire interflux plugin directory returned **zero matches**.

Remaining `Codex` references (14 instances across 5 files) all refer to the external **Codex CLI product** and are correctly preserved:
- `launch-codex.md` filename and heading
- `DISPATCH_MODE = codex`
- "Codex CLI", "Codex dispatch", "Codex timeout"
- "Codex reads CLAUDE.md natively"
- `shared-contracts.md` Codex dispatch references
- `AGENTS.md` file tree references to `launch-codex.md`

---

## Not In Scope

The following related files were NOT in scope for this task (not part of the interflux plugin):
- `.claude/clodex-toggle.flag` -> `.claude/interserve-toggle.flag` (flag file itself, lives in project root)
- Clavain hub files referencing clodex (separate rename task)
- Other plugins referencing clodex
