---
agent: fd-code-quality
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: Documentation Drift
    title: "Review agent sub-count is wrong on 3 documentation surfaces (AGENTS.md, README.md, plugin-audit.md)"
  - id: P0-2
    severity: P0
    section: Documentation Drift
    title: "README disabled-conflicts table lists only 5 of 8 disabled plugins"
  - id: P1-1
    severity: P1
    section: Agent Frontmatter
    title: "5 fd-* agents lack <example> blocks required by AGENTS.md convention"
  - id: P1-2
    severity: P1
    section: Skill Description Convention
    title: "6 of 34 skills deviate from the 'Use when' description pattern"
  - id: P1-3
    severity: P1
    section: Routing Table Coverage
    title: "plan-reviewer agent absent from using-clavain routing table"
  - id: P1-4
    severity: P1
    section: Routing Table Coverage
    title: "3 commands (setup, compound, interpeer) absent from 3-layer routing tables"
  - id: P2-1
    severity: P2
    section: Command Frontmatter
    title: "flux-drive.md command has unique user-invocable and quoted description deviating from other commands"
  - id: P2-2
    severity: P2
    section: Agent Naming
    title: "Review agent naming suffixes use 7 different patterns (-reviewer, -strategist, -expert, -agent, -specialist, -oracle, -sentinel)"
  - id: P2-3
    severity: P2
    section: Description Quoting
    title: "Agents use quoted descriptions (29/29), skills use unquoted (34/34), commands are mixed (1 quoted, 26 unquoted)"
  - id: P2-4
    severity: P2
    section: Hook Quality
    title: "lib.sh omits set -euo pipefail; hooks.json SessionEnd entry omits matcher field"
  - id: P2-5
    severity: P2
    section: Agent Model Field
    title: "learnings-researcher uses model: haiku while all other 28 agents use model: inherit"
improvements:
  - id: IMP-1
    title: "Fix review agent counts across all documentation surfaces to 21"
    section: Documentation Drift
  - id: IMP-2
    title: "Add missing disabled plugins to README conflicts table"
    section: Documentation Drift
  - id: IMP-3
    title: "Add <example> blocks to the 5 fd-* codebase-aware agents"
    section: Agent Frontmatter
  - id: IMP-4
    title: "Normalize skill descriptions to 'Use when' pattern"
    section: Skill Description Convention
  - id: IMP-5
    title: "Add plan-reviewer, setup, compound, interpeer to routing tables"
    section: Routing Table Coverage
  - id: IMP-6
    title: "Standardize description quoting across component types"
    section: Description Quoting
  - id: IMP-7
    title: "Add set -euo pipefail to lib.sh and matcher to SessionEnd hook"
    section: Hook Quality
verdict: PASS with issues. The codebase is structurally sound -- all 34 skills, 29 agents, and 27 commands follow kebab-case naming, have valid frontmatter with correct name-to-file mappings, and are reachable through the routing system. No stale namespace references (superpowers:, compound-engineering:) remain. JSON manifests are valid, shell scripts pass syntax checks. The issues found are documentation drift (stale sub-counts, incomplete conflict lists) and convention inconsistencies (description patterns, quoting, example blocks), not structural defects.
---

# Code Quality Review — Clavain v0.4.6

## Summary

Clavain's code quality is solid at the structural level. All components follow the kebab-case convention, frontmatter `name` fields match file/directory names without exception, JSON manifests are valid, and shell scripts pass `bash -n` syntax checking. The old namespace references (`superpowers:`, `compound-engineering:`) have been completely cleaned from active code.

The issues found fall into three categories:
1. **Documentation drift** (P0): Review agent sub-counts are stale on 3 surfaces, and the README omits 3 disabled plugins from its conflicts table.
2. **Convention inconsistency** (P1-P2): 5 agents missing `<example>` blocks, 6 skills deviating from the "Use when" description pattern, mixed description quoting across component types, and minor routing table gaps.
3. **Hook quality** (P2): `lib.sh` missing the `set -euo pipefail` preamble that AGENTS.md requires for "all hook scripts," and the SessionEnd hook entry in `hooks.json` lacks a `matcher` field unlike its siblings.

None of these issues affect runtime behavior. The plugin loads, routes, and dispatches correctly.

---

## Section-by-Section Review

### 1. Naming Conventions

**Result: PASS**

All 34 skills, 29 agents, and 27 commands use consistent kebab-case naming. Every frontmatter `name` field matches its corresponding file or directory name:

- **Skills**: `name` matches directory name in all 34 cases (e.g., `name: systematic-debugging` in `skills/systematic-debugging/SKILL.md`).
- **Agents**: `name` matches filename (minus `.md`) in all 29 cases (e.g., `name: security-sentinel` in `agents/review/security-sentinel.md`).
- **Commands**: `name` matches filename (minus `.md`) in all 27 cases (e.g., `name: flux-drive` in `commands/flux-drive.md`).

No camelCase, snake_case, or mixed-case names were found in any component.

**One naming pattern observation** (P2-2): The review agents use 7 different naming suffix conventions. While each name is individually reasonable and has organic history, the inconsistency means there is no predictable pattern for discovering agents by name:

| Suffix Pattern | Count | Examples |
|---------------|-------|---------|
| `-reviewer` | 10 | concurrency-reviewer, go-reviewer, python-reviewer |
| `fd-` prefix (no suffix) | 5 | fd-architecture, fd-code-quality, fd-security |
| `-strategist` | 1 | architecture-strategist |
| `-expert` | 1 | data-migration-expert |
| `-agent` | 1 | deployment-verification-agent |
| `-specialist` | 1 | pattern-recognition-specialist |
| `-oracle` | 1 | performance-oracle |
| `-sentinel` | 1 | security-sentinel |

This is a style observation, not a functional defect. The varied suffixes provide richer semantic differentiation (a "sentinel" connotes proactive monitoring, an "oracle" connotes deep insight, etc.).

### 2. Agent Frontmatter Consistency

**Result: PARTIAL PASS — 5 agents lack `<example>` blocks**

AGENTS.md line 120 states: "Description must include concrete `<example>` blocks with `<commentary>` explaining WHY to trigger." Checking all 29 agents:

- **24 agents** have `<example>` blocks: all research (5), all workflow (3), and 16 of 21 review agents.
- **5 agents** lack `<example>` blocks: `fd-architecture`, `fd-code-quality`, `fd-performance`, `fd-security`, `fd-user-experience`.

These 5 are the codebase-aware Tier 1 agents that were absorbed from gurgeh-plugin. Their descriptions use a different pattern — they embed trigger conditions directly in the description string rather than in `<example>` blocks:

```yaml
description: "Codebase-aware architecture reviewer. Knows project boundaries, module layout, and integration patterns. Use when reviewing plans that touch component structure, cross-tool boundaries, or system design."
```

This is functionally adequate for routing (the description contains trigger phrases), but it violates the documented convention that requires `<example>` blocks with `<commentary>`.

**model field**: 28 of 29 agents use `model: inherit`. One agent (`learnings-researcher`) uses `model: haiku` with an inline comment: "Grep-based filtering + frontmatter scanning -- no heavy reasoning needed." This is an intentional optimization, not an oversight, but it is the only agent that deviates.

### 3. Skill Description Convention

**Result: PARTIAL PASS — 6 skills deviate from convention**

The AGENTS.md convention (line 102) says skill descriptions should be "third-person, with trigger phrases." The `writing-skills` skill template (line 108) shows: `description: Use when [specific triggering conditions]`. Checking actual practice: 28 of 34 skills start with "Use when" (imperative with trigger conditions). 6 skills deviate:

| Skill | Description Start | Pattern |
|-------|------------------|---------|
| `clodex` | "Dispatch tasks to Codex CLI agents..." | Imperative without trigger |
| `interpeer` | "Auto-detecting cross-AI peer review..." | Declarative noun phrase |
| `prompterpeer` | "Oracle prompt optimizer with human review..." | Declarative noun phrase |
| `winterpeer` | "LLM Council review for critical decisions..." | Declarative noun phrase |
| `splinterpeer` | "Extract disagreements between AI models..." | Imperative without trigger |
| `brainstorming` | "Freeform brainstorming mode..." | Declarative noun phrase |

The cross-AI skills (interpeer, prompterpeer, winterpeer, splinterpeer) consistently use a different pattern -- they describe what the skill IS rather than when to use it. The `brainstorming` skill does contain "Use for" later in its description, but doesn't start with "Use when."

Note: the AGENTS.md convention says "third-person" but the actual predominant pattern is second-person imperative ("Use when..."). The documentation itself is slightly inconsistent about the expected voice.

### 4. Command Frontmatter Consistency

**Result: PASS with minor deviations**

All 27 commands have `name` and `description` fields. The optional `argument-hint` field is present in 23 of 27 commands. The 4 commands without `argument-hint` are:

- `debate` -- could benefit from `"[topic or decision to debate]"`
- `codex-first` -- toggle command, no argument needed (reasonable omission)
- `clodex-toggle` -- toggle command, no argument needed (reasonable omission)
- `execute-plan` -- could benefit from `"[plan file path]"` since `/work` has one

One command (`flux-drive.md`) has a `user-invocable: true` field that no other command uses. This field is not documented in the AGENTS.md conventions section. The same command is also the only command with a quoted `description` value.

Two commands (`write-plan`, `execute-plan`) use `disable-model-invocation: true`. Five commands (`heal-skill`, `clodex-toggle`, `upstream-sync`, `create-agent-skill`, `codex-first`) use `allowed-tools`. These additional fields are documented in the AGENTS.md "Commands" section.

### 5. Documentation Drift

**Result: FAIL on sub-counts and conflicts list**

#### 5a. Component Counts (Top-Level)

The top-level counts are consistent across all 4 primary documentation surfaces:

| Surface | Count Statement |
|---------|----------------|
| `CLAUDE.md` line 7 | 34 skills, 29 agents, 27 commands, 3 hooks, 3 MCP servers |
| `README.md` line 7 | 34 skills, 29 agents, 27 commands, 3 hooks, 3 MCP servers |
| `AGENTS.md` line 12 | 34 skills, 29 agents, 27 commands, 3 hooks, 3 MCP servers |
| `using-clavain/SKILL.md` line 24 | 34 skills, 29 agents, 27 commands |
| `plugin.json` line 4 | 29 agents, 27 commands, 34 skills, 3 MCP servers |

These all agree and match the actual filesystem counts. The previous review's P0 (stale counts) has been fully resolved.

#### 5b. Review Agent Sub-Count (Stale)

The architecture tree diagrams and conflict tables still reference old review agent counts:

| Surface | Line | Says | Actual |
|---------|------|------|--------|
| `AGENTS.md` | 40 | "20 code review agents" | 21 |
| `AGENTS.md` | 275 | "15 review agents" (conflicts table) | 21 |
| `README.md` | 234 | "20 review agents" (conflicts table) | 21 |
| `README.md` | 259 | "20 code review agents" (architecture tree) | 21 |
| `docs/plugin-audit.md` | 21 | "15 review agents" | 21 |

`README.md` line 152 correctly says "Review (21):" -- so the README contradicts itself (21 in one place, 20 in two others).

The AGENTS.md categories section (line 125) correctly says "(21)". So AGENTS.md also contradicts itself (21 in the categories, 20 in the tree, 15 in the conflicts table).

#### 5c. Disabled Plugins Conflict List

Three documentation surfaces list disabled plugins:

| Surface | Plugins Listed |
|---------|---------------|
| `using-clavain/SKILL.md` line 122 | 8: code-review, pr-review-toolkit, code-simplifier, commit-commands, feature-dev, claude-md-management, frontend-design, hookify |
| `AGENTS.md` lines 274-282 | 8: same list |
| `README.md` lines 232-238 | **5 only**: code-review, pr-review-toolkit, code-simplifier, commit-commands, feature-dev |

README is missing: `claude-md-management`, `frontend-design`, `hookify`.

#### 5d. plugin.json Description

The `plugin.json` description mentions "29 agents, 27 commands, 34 skills, 3 MCP servers" but omits hooks. All other top-level count surfaces include "3 hooks." This is a minor omission.

### 6. Hook Script Quality

**Result: PASS with minor observations**

All 4 executable hook scripts (`autopilot.sh`, `session-start.sh`, `agent-mail-register.sh`, `dotfiles-sync.sh`) pass `bash -n` syntax checking and use `set -euo pipefail`.

**lib.sh**: Does NOT have `set -euo pipefail`. AGENTS.md line 148 says "Use `set -euo pipefail` in all hook scripts." `lib.sh` is technically a library (sourced, not executed), so the convention may not apply -- but it is listed in the validation checklist as a hook script to syntax-check. Adding `set -euo pipefail` would be a no-op since sourcing scripts inherit the caller's settings, but it would satisfy the documented convention.

**hooks.json**: The `SessionEnd` entry (lines 32-42) lacks a `matcher` field while both `PreToolUse` and `SessionStart` entries have matchers. This inconsistency may be intentional (SessionEnd always fires), but it means the three hook entries are not structurally uniform.

**session-start.sh details**:
- Line 14: Uses `cat` with `2>&1` to capture stderr from reading `using-clavain/SKILL.md` -- good error handling.
- Line 22: Uses `find` to locate `dispatch.sh` -- functional but slower than a direct path check.
- Line 28: Checks for `.beads` directory in two places (relative to plugin root and current working directory) -- thorough.
- Line 33: Agent Mail health check has 1-second timeout -- appropriately fast for a startup hook.
- Line 52: Uses `stat -c %Y` for file age calculation -- Linux-specific (would fail on macOS). Acceptable given the documented Linux-only deployment.

**autopilot.sh details**:
- Has proper fallback for when `jq` is not available (lines 43-61).
- The `jq` fallback uses a heredoc with single-quoted delimiter (`'ENDJSON'`) preventing interpolation -- good security practice.
- Both code paths produce structurally identical JSON output.

**agent-mail-register.sh details**:
- Uses `python3` for JSON construction and parsing -- appropriate given the data complexity.
- Has graceful no-op behavior at every failure point (lines 35, 56-58, 62-65).
- Sources `lib.sh` and uses `escape_for_json` for output safety.

**dotfiles-sync.sh details**:
- Simple and focused: checks if sync script exists and is executable, runs it, logs output.
- Uses `|| true` to prevent sync failures from propagating -- appropriate for a session-end hook.

### 7. Stale References

**Result: PASS**

- No references to `superpowers:` namespace in active code (skills/, agents/, commands/, hooks/).
- No references to `compound-engineering:` namespace in active code.
- No references to removed skills (`codex-first-dispatch`, `codex-delegation`) in active code.
- `gurgeh-plugin` references exist only in `docs/research/` (historical reviews) and `docs/plugin-audit.md` (correctly struck through as "ABSORBED into Clavain").
- The `data-integrity-guardian.md` -> `data-integrity-reviewer.md` rename is only referenced in `upstreams.json` file mapping (correct -- this is the sync mapping).

### 8. Routing Table Coverage

**Result: PARTIAL PASS**

All 34 skills are accounted for in the routing tables (33 explicitly mapped + `using-clavain` itself which IS the routing table).

**Agents**: 23 of 29 agents appear in the routing tables. Missing:
- `plan-reviewer` -- not listed anywhere in Layers 1-3. The `plan-review` command is listed, and it dispatches this agent internally, but the agent itself is invisible in the routing table. This matters because agents can also be dispatched via the Task tool directly.
- `fd-architecture`, `fd-code-quality`, `fd-performance`, `fd-security`, `fd-user-experience` -- the 5 Tier 1 codebase-aware agents. These are covered by the "(triaged from roster -- up to 8 agents)" note on the Review (docs) row, which is arguably sufficient since they are exclusively dispatched by the flux-drive skill.

**Commands**: 24 of 27 commands appear in the 3-layer routing tables. Missing from the routing tables (but present in the Key Commands Quick Reference section):
- `setup` -- the modpack bootstrapper
- `compound` -- document solved problems
- `interpeer` -- quick cross-AI peer review

These 3 commands are all present in the quick reference section at the bottom of `using-clavain/SKILL.md`, so they are discoverable. But they are absent from the structured 3-layer routing tables where most routing decisions happen.

---

## Issues Found

### P0-1: Review agent sub-count wrong on 3 documentation surfaces

**Severity**: P0 (factual inaccuracy in user-facing documentation)

**Location**:
- `/root/projects/Clavain/AGENTS.md` line 40: says "20 code review agents" -- actual is 21
- `/root/projects/Clavain/AGENTS.md` line 275: says "15 review agents" -- actual is 21
- `/root/projects/Clavain/README.md` line 234: says "20 review agents" -- actual is 21
- `/root/projects/Clavain/README.md` line 259: says "20 code review agents" -- actual is 21
- `/root/projects/Clavain/docs/plugin-audit.md` line 21: says "15 review agents" -- actual is 21

**Impact**: The top-level counts (29 agents total) are correct everywhere, but the sub-counts within the architecture trees and conflict tables are stale. Users who read the conflict tables may underestimate the review capability. The internal contradictions (AGENTS.md saying both "21" on line 125 and "20" on line 40) erode trust in the documentation.

**Fix**: Replace all occurrences of "15 review agents" and "20 review agents" with "21 review agents" in the 3 affected files (5 line edits total).

### P0-2: README disabled-conflicts table lists only 5 of 8 disabled plugins

**Severity**: P0 (incomplete user-facing guidance)

**Location**: `/root/projects/Clavain/README.md` lines 232-238

**Impact**: Users who follow only the README will not disable `claude-md-management`, `frontend-design`, or `hookify`, leading to duplicate agents and confusing routing. The `/clavain:setup` command handles this automatically, but users who manually configure their plugins based on the README will miss 3 conflicts.

**Fix**: Add the 3 missing rows to the README disabled-conflicts table to match AGENTS.md lines 280-282.

### P1-1: 5 fd-* agents lack `<example>` blocks

**Severity**: P1 (convention violation)

**Location**:
- `/root/projects/Clavain/agents/review/fd-architecture.md`
- `/root/projects/Clavain/agents/review/fd-code-quality.md`
- `/root/projects/Clavain/agents/review/fd-performance.md`
- `/root/projects/Clavain/agents/review/fd-security.md`
- `/root/projects/Clavain/agents/review/fd-user-experience.md`

**Impact**: These agents are exclusively dispatched by the flux-drive skill (not by user routing), so the missing `<example>` blocks have minimal impact on discoverability. However, they violate the documented convention and could cause confusion if a contributor tries to add these agents to manual dispatch workflows.

### P1-2: 6 of 34 skills deviate from 'Use when' description pattern

**Severity**: P1 (convention inconsistency)

**Location**: Skills `clodex`, `interpeer`, `prompterpeer`, `winterpeer`, `splinterpeer`, `brainstorming`

**Impact**: The inconsistency is systematic: the cross-AI skills (4 of 6) consistently use declarative descriptions. This could be considered a justified sub-convention for that skill family. But the current AGENTS.md does not document this exception. The routing system still works because descriptions contain trigger phrases regardless of format.

**Suggested normalization examples**:
- `clodex`: "Use when dispatching tasks to Codex CLI agents -- single megaprompt for one task, parallel delegation for many."
- `interpeer`: "Use when seeking a quick cross-AI second opinion -- auto-detects host agent and calls the other for feedback."
- `brainstorming`: "Use when doing freeform brainstorming without structured phases -- loads collaborative dialogue style."

### P1-3: plan-reviewer agent absent from routing table

**Severity**: P1 (routing gap)

**Location**: `/root/projects/Clavain/skills/using-clavain/SKILL.md` -- absent from all routing layers

**Impact**: The `plan-reviewer` agent is dispatched internally by the `plan-review` command, but it is not listed as a Key Agent in any routing row. Users who want to dispatch it directly via the Task tool would not discover it through the routing table.

**Fix**: Add `plan-reviewer` to the Plan stage Key Agents column (alongside `architecture-strategist, spec-flow-analyzer`).

### P1-4: 3 commands absent from 3-layer routing tables

**Severity**: P1 (routing gap)

**Location**: `/root/projects/Clavain/skills/using-clavain/SKILL.md` -- `setup`, `compound`, `interpeer` only appear in Key Commands Quick Reference, not in the routing tables

**Impact**: The Quick Reference section provides a flat list that users can scan, but the 3-layer routing tables are the primary discovery mechanism. Commands not in the routing tables are less likely to be suggested by the routing heuristic.

**Suggested placements**:
- `setup` -> Meta stage commands
- `compound` -> Ship stage commands (it documents solved problems after implementation)
- `interpeer` -> Review stage commands (it is a review tool)

### P2-1: flux-drive.md command has unique frontmatter fields

**Severity**: P2 (minor convention deviation)

**Location**: `/root/projects/Clavain/commands/flux-drive.md` line 4

**Impact**: `user-invocable: true` is not documented in AGENTS.md conventions and is not used by any other command. The quoted description (`description: "..."`) also differs from the unquoted format used by the other 26 commands. Functionally harmless.

### P2-2: Review agent naming suffixes inconsistent

**Severity**: P2 (style observation)

**Impact**: 7 different suffix patterns across 21 review agents. Not a functional issue, but makes the naming scheme unpredictable. The variation has organic history (different upstream sources) and arguably provides richer semantic differentiation.

### P2-3: Description quoting inconsistent across component types

**Severity**: P2 (style inconsistency)

**Impact**: Agents consistently quote descriptions (29/29). Skills consistently do not (34/34). Commands are mixed (1 quoted, 26 unquoted). YAML technically handles both, so this is cosmetic, but the inconsistency between component types suggests no deliberate convention.

### P2-4: lib.sh missing set -euo pipefail; SessionEnd missing matcher

**Severity**: P2 (minor convention gap)

**Impact**: `lib.sh` is sourced (not executed), so the missing `set -euo pipefail` is a no-op in practice. The SessionEnd hook's missing `matcher` means it fires on all session-end events, which is likely the intended behavior but differs structurally from the other hook entries.

### P2-5: learnings-researcher uses model: haiku

**Severity**: P2 (intentional deviation, documented inline)

**Location**: `/root/projects/Clavain/agents/research/learnings-researcher.md` line 4

**Impact**: The inline comment explains the rationale ("Grep-based filtering + frontmatter scanning -- no heavy reasoning needed"). This is a valid optimization, but it is the only agent that deviates from `model: inherit`. Worth noting for awareness but not a defect.

---

## Improvements Suggested

### IMP-1: Fix review agent counts (addresses P0-1)

Update 5 lines across 3 files:
1. `AGENTS.md` line 40: "20" -> "21"
2. `AGENTS.md` line 275: "15" -> "21"
3. `README.md` line 234: "20" -> "21"
4. `README.md` line 259: "20" -> "21"
5. `docs/plugin-audit.md` line 21: "15" -> "21"

Estimated effort: 2 minutes.

### IMP-2: Add missing disabled plugins to README (addresses P0-2)

Add 3 rows to the README disabled-conflicts table:

```markdown
| claude-md-management | `engineering-docs` skill |
| frontend-design | `distinctive-design` skill |
| hookify | Clavain manages hooks directly |
```

Estimated effort: 2 minutes.

### IMP-3: Add `<example>` blocks to fd-* agents (addresses P1-1)

Each fd-* agent needs 1-2 `<example>` blocks showing when flux-drive would dispatch them. Template:

```markdown
<example>
User is reviewing a plan that restructures the module layout of a Go project.
<commentary>The plan touches component boundaries and cross-module integration patterns, which is exactly what the codebase-aware architecture reviewer analyzes differently from the generic architecture-strategist.</commentary>
</example>
```

Estimated effort: 20 minutes.

### IMP-4: Normalize skill descriptions to 'Use when' pattern (addresses P1-2)

Either normalize the 6 deviating skills to "Use when" format, or document the cross-AI skills as a recognized exception in AGENTS.md. Also update AGENTS.md line 102 from "third-person" to match the actual "Use when" imperative convention used by 28 of 34 skills.

Estimated effort: 10 minutes if normalizing, 5 minutes if documenting the exception.

### IMP-5: Add missing components to routing tables (addresses P1-3, P1-4)

Add to `using-clavain/SKILL.md`:
- `plan-reviewer` to Plan stage Key Agents
- `setup` to Meta stage commands
- `compound` to Ship stage commands
- `interpeer` to Review stage commands

Estimated effort: 5 minutes.

### IMP-6: Standardize description quoting (addresses P2-3)

Choose one convention (quoted or unquoted) and apply it consistently. Since skills (34) and most commands (26) use unquoted, the path of least resistance is to unquote the agent descriptions and the one quoted command description. Alternatively, document that agents use quoted descriptions as a convention.

Estimated effort: 30 minutes if changing, 2 minutes if documenting.

### IMP-7: Add set -euo pipefail to lib.sh and matcher to SessionEnd (addresses P2-4)

Add `set -euo pipefail` to line 2 of `lib.sh`. Add `"matcher": ""` or a descriptive matcher to the SessionEnd entry in `hooks.json` for structural consistency.

Estimated effort: 2 minutes.

---

## Overall Assessment

Clavain v0.4.6 is in good structural shape. The previous review rounds (v1, v2) resolved the major issues: stale top-level counts, phantom namespace references, and missing routing table entries. The remaining issues are:

**High priority (P0)**: Two documentation drift problems where sub-counts and conflict lists are incomplete. These are 5-minute fixes.

**Medium priority (P1)**: Convention gaps (missing `<example>` blocks, description pattern deviations, routing table coverage). These affect documentation consistency more than runtime behavior.

**Low priority (P2)**: Style observations (naming suffixes, quoting, hook boilerplate) that are cosmetically inconsistent but functionally harmless.

The codebase demonstrates disciplined conventions that are largely self-consistent. The 34 skills all have matching directory-to-frontmatter names. The 29 agents all have matching filename-to-frontmatter names. The 27 commands all have matching filename-to-frontmatter names. The hook scripts are well-written with proper error handling, graceful degradation, and security-conscious JSON construction. The routing table covers all skills and nearly all agents and commands.

The most impactful improvement would be fixing the P0 documentation drift (IMP-1 and IMP-2) -- 7 line edits that eliminate factual inaccuracies from user-facing documentation.
