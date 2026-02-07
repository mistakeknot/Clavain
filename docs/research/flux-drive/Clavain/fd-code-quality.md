---
agent: fd-code-quality
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Documentation Counts"
    title: "AGENTS.md Quick Reference and architecture tree report stale component counts (31/22 vs actual 32/24)"
  - id: P0-2
    severity: P0
    section: "Routing Table Counts"
    title: "using-clavain/SKILL.md line 22 says '31 skills, 23 agents, and 22 commands' but actual is 32/23/24"
  - id: P0-3
    severity: P0
    section: "Upstream Sync Mapping"
    title: "upstreams.json fileMap references 5 snake_case command filenames that no longer exist"
  - id: P1-1
    severity: P1
    section: "Skill Description Style"
    title: "9 of 32 skills deviate from the 'Use when' description convention"
  - id: P1-2
    severity: P1
    section: "Agent Description Format"
    title: "plan-reviewer uses YAML literal block (description: |) while all 22 others use inline string"
  - id: P1-3
    severity: P1
    section: "Command Prose Quality"
    title: "resolve-parallel command has informal/unfinished prose including typo 'liek this'"
  - id: P1-4
    severity: P1
    section: "Rails Content in General-Purpose Agents"
    title: "deployment-verification-agent and framework-docs-researcher still contain Rails-specific content"
  - id: P2-1
    severity: P2
    section: "Agent Extra Fields"
    title: "pr-comment-resolver has unique 'color: blue' field not used by any other agent"
  - id: P2-2
    severity: P2
    section: "Routing Table Coverage"
    title: "8 commands and 2 skills missing from using-clavain routing table"
  - id: P2-3
    severity: P2
    section: "Command Frontmatter"
    title: "write-plan and execute-plan lack argument-hint field"
improvements:
  - id: IMP-1
    title: "Update all stale component counts to 32/23/24"
    section: "Documentation Counts"
  - id: IMP-2
    title: "Fix upstreams.json fileMap to reference renamed kebab-case command files"
    section: "Upstream Sync Mapping"
  - id: IMP-3
    title: "Normalize skill descriptions to 'Use when' trigger pattern"
    section: "Skill Description Style"
  - id: IMP-4
    title: "Generalize Rails-specific content in deployment-verification-agent and framework-docs-researcher"
    section: "Rails Content in General-Purpose Agents"
  - id: IMP-5
    title: "Add missing commands and skills to the using-clavain routing table"
    section: "Routing Table Coverage"
verdict: needs-changes
---

## Summary

Clavain is a well-structured plugin with 79 component files (32 skills, 23 agents, 24 commands) and strong conventions documented in AGENTS.md. Several issues from the prior review have been fixed: snake_case command names are now kebab-case, `lib/skills-core.js` has been removed, the `engineering-docs` heading is corrected, Rails content has been cleaned from 3 of the 5 previously flagged agents, and `security-sentinel` no longer contains framework-specific grep patterns. However, new drift has appeared: component counts are stale in AGENTS.md and the `using-clavain` routing skill (still showing 31/22 instead of 32/24), `upstreams.json` references 5 command files by their old snake_case names (files that no longer exist), and 9 skill descriptions deviate from the documented "Use when" convention. The prose quality issue in `resolve-parallel.md` and the `description: |` format in `plan-reviewer.md` persist from the prior review.

---

## Section-by-Section Review

### 1. Component Count Accuracy

Actual on-disk component counts verified via glob:

| Component | Actual | CLAUDE.md | README.md | AGENTS.md QR | AGENTS.md tree | plugin.json | using-clavain |
|-----------|--------|-----------|-----------|--------------|----------------|-------------|---------------|
| Skills | **32** | 32 | 32 | **31** | **31** | **32** | **31** |
| Agents | **23** | 23 | 23 | 23 | 23 (15+5+3) | 23 | 23 |
| Commands | **24** | 24 | 24 | **22** | **22** | **24** | **22** |

Four documents report stale counts:
- `/root/projects/Clavain/AGENTS.md` line 12: "31 skills, 23 agents, 22 commands"
- `/root/projects/Clavain/AGENTS.md` line 20: "# 31 discipline skills"
- `/root/projects/Clavain/AGENTS.md` line 37: "# 22 slash commands"
- `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 22: "31 skills, 23 agents, and 22 commands"

The `using-clavain` count is especially impactful because this content is injected into every session via the SessionStart hook, meaning every session starts with incorrect counts.

### 2. Upstream Sync Mapping (upstreams.json)

The file `/root/projects/Clavain/upstreams.json` contains `fileMap` entries for the compound-engineering upstream that reference 5 command filenames by their old snake_case names:

| upstreams.json reference | Actual filename on disk |
|--------------------------|------------------------|
| `commands/generate_command.md` | `commands/generate-command.md` |
| `commands/plan_review.md` | `commands/plan-review.md` |
| `commands/resolve_parallel.md` | `commands/resolve-parallel.md` |
| `commands/resolve_pr_parallel.md` | `commands/resolve-pr-parallel.md` |
| `commands/resolve_todo_parallel.md` | `commands/resolve-todo-parallel.md` |

When the upstream sync runs, it will try to merge upstream changes into non-existent files, causing silent failures or errors. This is a functional breakage, not just a cosmetic issue.

### 3. YAML Frontmatter Consistency

#### Skills (32 files)

All 32 SKILL.md files have valid frontmatter with `name` and `description` fields. All `name` fields match their directory names exactly.

**Description pattern adherence:** The documented convention (AGENTS.md line 88) is: `description` should be "third-person, with trigger phrases". The `writing-skills/SKILL.md` example template shows `description: Use when [specific triggering conditions]`. Of 32 skills, **23 follow the "Use when" pattern** and **9 deviate**:

| Skill | Current description start | Issue |
|-------|--------------------------|-------|
| `brainstorming` | `"You MUST use this before..."` | Aggressive second-person, not third-person |
| `distinctive-design` | `"This skill should be used when..."` | Passive voice instead of imperative |
| `file-todos` | `"This skill should be used when..."` | Passive voice instead of imperative |
| `agent-native-architecture` | `"Build applications where..."` | Imperative but no trigger phrase; "Use this skill when" appears mid-sentence |
| `flux-drive` | `"Intelligent document review..."` | Third-person summary without trigger phrase |
| `engineering-docs` | `"Capture solved problems..."` | Imperative without trigger phrase |
| `mcp-cli` | `"Use MCP servers on-demand..."` | Starts with "Use" but different pattern |
| `codex-first-dispatch` | `"Streamlined single-task..."` | Third-person summary without trigger phrase |
| `create-agent-skills` | `"Expert guidance for creating..."` | Third-person summary; "Use when" appears later |

**Optional fields** used by skills: `allowed-tools` (slack-messaging, engineering-docs, slack-messaging), `user-invocable` (slack-messaging), `preconditions` (engineering-docs). These are not documented as standard fields in AGENTS.md but are valid Claude Code plugin fields.

#### Agents (23 files)

All 23 agents have `name`, `description`, and `model` fields. All `name` fields match their filenames (minus `.md`). All 23 agents include at least one `<example>` block and one `<commentary>` block in their descriptions.

**One format outlier:** `/root/projects/Clavain/agents/review/plan-reviewer.md` uses `description: |` (YAML literal block scalar) while all other 22 agents use inline quoted strings (`description: "..."`). The content is correct but the format is unique.

**Model field:** 22 agents use `model: inherit`. One outlier: `/root/projects/Clavain/agents/research/learnings-researcher.md` uses `model: haiku` (intentional cost optimization for lightweight research tasks).

**Extra fields:** `/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` has `color: blue` on line 4. No other agent uses this field.

#### Commands (24 files)

All 24 commands have `name` and `description`. All `name` fields match their filenames (minus `.md`). All commands now use **kebab-case** consistently (the snake_case issue from the prior review has been fixed).

**argument-hint presence:** 18 of 24 commands have `argument-hint`. Missing: `write-plan`, `execute-plan`, `codex-first`, `clodex`, `upstream-sync`, `work`.

**Extra fields in use:**
- `disable-model-invocation: true`: Used by `write-plan`, `execute-plan`
- `allowed-tools`: Used by `codex-first`, `clodex`, `upstream-sync`, `heal-skill`, `create-agent-skill`
- `user-invocable: true`: Used by `flux-drive`

### 4. Namespace Consistency

The `superpowers:` and `compound-engineering:` namespace prefixes have been fully eliminated from all active component files (skills/, agents/, commands/, hooks/). The prior review's P1-5 (`lib/skills-core.js` superpowers namespace) is resolved -- the file no longer exists.

Remaining `superpowers` string occurrences are legitimate:
- Reference to upstream repo names in `upstream-sync/SKILL.md`, `AGENTS.md`, `README.md`
- Upstream plugin documentation in `developing-claude-code-plugins/references/common-patterns.md`
- Research documents in `docs/research/flux-drive/` (this review and prior)

No `compound-engineering:` namespace prefix references exist anywhere.

### 5. Rails/Framework-Specific Content

The design decision (CLAUDE.md) states: "General-purpose only -- no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation."

**Cleaned since prior review (3 agents):**
- `security-sentinel.md` -- Rails grep patterns and Rails-specific attention notes removed
- `performance-oracle.md` -- ActiveRecord reference removed
- `learnings-researcher.md` -- Rails-specific component categories removed

**Still containing Rails content (2 agents):**

1. `/root/projects/Clavain/agents/review/deployment-verification-agent.md` (lines 58, 104-112):
   - Line 58: Example table uses `rails db:migrate` and `rake data:backfill`
   - Lines 104-112: Code block tagged as ` ```ruby ` with `Record.where(...)` examples

2. `/root/projects/Clavain/agents/research/framework-docs-researcher.md` (line 3, in description):
   - Example mentions "Active Storage" and "turbo-rails gem" as use cases

One additional note: `/root/projects/Clavain/agents/research/repo-research-analyst.md` line 103 mentions `ast-grep --lang ruby` but this is in a list alongside `--lang typescript` and is a general-purpose tool example, not Rails-specific content.

### 6. Code Quality of Bash Scripts

#### session-start.sh

`/root/projects/Clavain/hooks/session-start.sh` is well-written:
- Uses `set -euo pipefail` as required by AGENTS.md
- Portable path resolution via `BASH_SOURCE` and `dirname`
- JSON string escaping via parameter substitution (fast, correct)
- Handles missing `upstream-versions.json` gracefully
- Staleness check uses `stat -c %Y` (Linux-specific; would need `stat -f %m` on macOS, but this is a server-deployed plugin)
- Clean heredoc for JSON output

No issues found.

#### upstream-check.sh

`/root/projects/Clavain/scripts/upstream-check.sh` is well-structured:
- Uses `set -euo pipefail`
- Proper argument parsing loop
- Handles `gh api` errors gracefully with `|| true` fallbacks
- Uses `jq` correctly for JSON construction and manipulation
- Exit codes are documented and meaningful (0=changes, 1=no changes, 2=error)
- The `--update` flag correctly writes back to the versions file

One minor observation: the script builds `$RESULTS` by repeatedly piping through `jq` in the loop (line 105: `RESULTS=$(echo "$RESULTS" | jq --argjson r "$result" '. + [$r]')`). For 7 repos this is fine, but for larger lists this would be O(n^2). Not worth flagging given the fixed upstream count.

### 7. Routing Table Completeness

The routing table in `/root/projects/Clavain/skills/using-clavain/SKILL.md` omits several components.

**Commands not in routing table (8 of 24):**
- `execute-plan` (could go in Execute stage)
- `learnings` (could go in Ship or Meta stage)
- `migration-safety` (could go in Data domain or Deploy)
- `triage` (could go in Review stage)
- `resolve-pr-parallel` (could go in Execute stage alongside resolve-parallel)
- `agent-native-audit` (could go in Review stage)
- `codex-first` / `clodex` (could go in Meta or Execute stage)

**Skills not in routing table (2 of 32, excluding self-reference):**
- `codex-first-dispatch` (sub-skill of codex-first command -- arguably intentional)
- `create-agent-skills` (partially covered: the `create-agent-skill` command is in Meta, but the skill itself is not listed)

The Key Commands Quick Reference at the bottom of `using-clavain` lists 10 commands. The routing table lists 16 unique commands. Together they cover 18 of 24 commands.

### 8. Prose Quality

`/root/projects/Clavain/commands/resolve-parallel.md` contains multiple informal/draft-quality passages:

- Line 13: "Gather the things todo from above." (informal phrasing)
- Line 17: "I'll put the to-dos in the mermaid diagram flow-wise so the agent knows how to proceed in order." (first-person; commands are instructions FOR Claude, not from a human)
- Line 23: "liek this" (typo for "like this")
- Line 17: Missing space after period ("type.Make sure to look")

This command appears to be an unedited draft that was never polished. Compare with the professional tone of `resolve-pr-parallel.md` or `resolve-todo-parallel.md` which handle similar workflows.

---

## Issues Found

### P0-1: AGENTS.md reports stale component counts

**Severity:** P0
**Location:** `/root/projects/Clavain/AGENTS.md` lines 12, 20, 37
**Convention:** Component counts should be accurate and consistent across all documentation.
**Violation:** Quick Reference says "31 skills, 23 agents, 22 commands". Architecture tree says "31 discipline skills" and "22 slash commands". Actual counts are 32 skills, 23 agents, 24 commands.
**Fix:** Update line 12 to "32 skills, 23 agents, 24 commands, 2 hooks, 2 MCP servers", line 20 to "# 32 discipline skills", line 37 to "# 24 slash commands".

### P0-2: using-clavain routing skill reports stale counts

**Severity:** P0
**Location:** `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 22
**Convention:** The routing skill is injected into every session and must be authoritative.
**Violation:** Says "31 skills, 23 agents, and 22 commands" but actual is 32/23/24.
**Fix:** Update line 22 to "Clavain provides 32 skills, 23 agents, and 24 commands."

### P0-3: upstreams.json references 5 non-existent snake_case command files

**Severity:** P0
**Location:** `/root/projects/Clavain/upstreams.json` lines 106, 109-113 (compound-engineering fileMap)
**Convention:** fileMap values must point to existing files in the Clavain repo.
**Violation:** Five entries reference old snake_case filenames that were renamed to kebab-case:
- `commands/generate_command.md` -> should be `commands/generate-command.md`
- `commands/plan_review.md` -> should be `commands/plan-review.md`
- `commands/resolve_parallel.md` -> should be `commands/resolve-parallel.md`
- `commands/resolve_pr_parallel.md` -> should be `commands/resolve-pr-parallel.md`
- `commands/resolve_todo_parallel.md` -> should be `commands/resolve-todo-parallel.md`
**Fix:** Update the 5 fileMap values to their kebab-case equivalents.

### P1-1: 9 of 32 skills deviate from 'Use when' description convention

**Severity:** P1
**Location:** SKILL.md files for brainstorming, distinctive-design, file-todos, agent-native-architecture, flux-drive, engineering-docs, mcp-cli, codex-first-dispatch, create-agent-skills
**Convention:** AGENTS.md line 88: "description (third-person, with trigger phrases)". Template shows `description: Use when [condition]`.
**Violation:** 9 skills use different patterns: aggressive ("You MUST"), passive ("This skill should be used when"), third-person summaries without trigger phrases, or imperative without triggers.
**Fix:** Rewrite descriptions to follow the `Use when [specific triggering conditions]` pattern. Examples:
- `brainstorming`: "Use when starting creative work -- creating features, building components, adding functionality, or modifying behavior"
- `flux-drive`: "Use when reviewing any document (plan, brainstorm, spec, ADR, README) or an entire repository with multi-agent triage"
- `codex-first-dispatch`: "Use when dispatching a single code task to a Codex agent in codex-first mode"

### P1-2: plan-reviewer uses YAML literal block (description: |) while all others use inline

**Severity:** P1
**Location:** `/root/projects/Clavain/agents/review/plan-reviewer.md` line 3
**Convention:** All 22 other agents use `description: "..."` (inline quoted string).
**Violation:** Uses `description: |` followed by multi-line content.
**Fix:** Convert to inline quoted string format matching the other 22 agents.

### P1-3: resolve-parallel command has draft-quality prose

**Severity:** P1
**Location:** `/root/projects/Clavain/commands/resolve-parallel.md` lines 13, 17, 23
**Convention:** Commands contain instructions for Claude in professional imperative tone.
**Violation:** Contains "liek this" (typo), "Gather the things todo from above" (informal), "I'll put the to-dos in the mermaid diagram" (first-person), missing space after period.
**Fix:** Rewrite to match the professional tone of `resolve-pr-parallel.md` and `resolve-todo-parallel.md`.

### P1-4: Two agents still contain Rails-specific content

**Severity:** P1
**Location:** `/root/projects/Clavain/agents/review/deployment-verification-agent.md` lines 58, 104-112; `/root/projects/Clavain/agents/research/framework-docs-researcher.md` line 3
**Convention:** CLAUDE.md: "General-purpose only -- no Rails, Ruby gems, Every.to, Figma, Xcode, browser-automation"
**Violation:** `deployment-verification-agent` uses `rails db:migrate`, `rake data:backfill`, and a Ruby code block as examples. `framework-docs-researcher` description uses "Active Storage" and "turbo-rails gem" in example blocks.
**Fix:** Replace Rails-specific examples with generic equivalents (e.g., `./migrate.sh`, generic SQL verification, language-agnostic library examples in the description).

### P2-1: pr-comment-resolver has unique 'color: blue' field

**Severity:** P2
**Location:** `/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` line 4
**Convention:** No other agent uses a `color` field. AGENTS.md documents `name`, `description`, `model` as the standard agent frontmatter fields.
**Violation:** Extra `color: blue` field appears to be an upstream artifact from compound-engineering.
**Fix:** Remove the `color: blue` line unless it serves a documented purpose in Claude Code's agent system.

### P2-2: 8 commands and 2 skills missing from routing table

**Severity:** P2
**Location:** `/root/projects/Clavain/skills/using-clavain/SKILL.md` lines 32-54
**Convention:** The routing table should help Claude discover all available components.
**Violation:** Commands `execute-plan`, `learnings`, `migration-safety`, `triage`, `resolve-pr-parallel`, `agent-native-audit`, `codex-first`, `clodex` are not in any routing row. Skills `codex-first-dispatch` and `create-agent-skills` are not explicitly listed (though partially reachable via commands that reference them).
**Fix:** Add missing commands to appropriate routing rows. `codex-first-dispatch` omission may be intentional (internal sub-skill).

### P2-3: write-plan and execute-plan lack argument-hint

**Severity:** P2
**Location:** `/root/projects/Clavain/commands/write-plan.md`, `/root/projects/Clavain/commands/execute-plan.md`
**Convention:** Most commands (18 of 24) include `argument-hint` for user guidance.
**Violation:** These two high-use commands provide no hint about expected arguments.
**Fix:** Add `argument-hint: "[spec, brainstorm document, or feature description]"` to `write-plan` and `argument-hint: "[plan file path]"` to `execute-plan`.

---

## Improvements Suggested

### IMP-1: Update all stale component counts to 32/23/24

Four locations need updating:
1. `/root/projects/Clavain/AGENTS.md` line 12: change "31 skills, 23 agents, 22 commands" to "32 skills, 23 agents, 24 commands"
2. `/root/projects/Clavain/AGENTS.md` line 20: change "# 31 discipline skills" to "# 32 discipline skills"
3. `/root/projects/Clavain/AGENTS.md` line 37: change "# 22 slash commands" to "# 24 slash commands"
4. `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 22: change "31 skills, 23 agents, and 22 commands" to "32 skills, 23 agents, and 24 commands"

This is a 5-minute fix with high trust impact. The `using-clavain` update is especially important since it flows into every session.

### IMP-2: Fix upstreams.json fileMap to reference renamed kebab-case command files

Update 5 entries in `/root/projects/Clavain/upstreams.json` under the compound-engineering upstream's `fileMap`:

```
"commands/generate_command.md": "commands/generate-command.md"
"commands/plan_review.md": "commands/plan-review.md"
"commands/resolve_parallel.md": "commands/resolve-parallel.md"
"commands/resolve_pr_parallel.md": "commands/resolve-pr-parallel.md"
"commands/resolve_todo_parallel.md": "commands/resolve-todo-parallel.md"
```

Without this fix, the weekly upstream sync will fail to apply compound-engineering command updates to the correct local files.

### IMP-3: Normalize skill descriptions to 'Use when' trigger pattern

Rewrite 9 skill descriptions to follow the documented convention. Priority order (by user-facing impact):

1. `brainstorming` -- highest visibility, invoked frequently
2. `flux-drive` -- new skill, sets precedent
3. `codex-first-dispatch` -- new skill
4. `distinctive-design`, `file-todos` -- passive voice fix
5. `agent-native-architecture`, `engineering-docs`, `mcp-cli`, `create-agent-skills` -- minor wording adjustments

### IMP-4: Generalize Rails-specific content in two agents

Replace framework-specific examples with generic equivalents:

1. `/root/projects/Clavain/agents/review/deployment-verification-agent.md`:
   - Line 58: Replace `rails db:migrate` with `./scripts/migrate.sh` or `<migration command>`
   - Lines 104-112: Replace Ruby code block with generic pseudo-code or SQL

2. `/root/projects/Clavain/agents/research/framework-docs-researcher.md`:
   - Line 3 (description examples): Replace "Active Storage" with a generic library example, replace "turbo-rails gem" with a generic dependency example

### IMP-5: Add missing commands and skills to routing table

Add to `/root/projects/Clavain/skills/using-clavain/SKILL.md` routing table:

| Command | Suggested routing row |
|---------|----------------------|
| `execute-plan` | Execute stage (alongside `work`) |
| `resolve-pr-parallel` | Execute stage (alongside `resolve-parallel`) |
| `learnings` | Ship stage (alongside `changelog`) |
| `migration-safety` | Data domain or Deploy domain |
| `triage` | Review stage |
| `agent-native-audit` | Review stage or Code domain |
| `codex-first` / `clodex` | Meta stage |

---

## Overall Assessment

**Verdict: needs-changes**

The project has improved significantly since the prior review. The command naming standardization (snake_case to kebab-case) is complete, `lib/skills-core.js` is gone, 3 of 5 flagged agents have been cleaned of Rails content, and the `engineering-docs` heading is fixed. These were the most impactful items from the prior review.

However, three new P0 issues have emerged:
1. The kebab-case rename left `upstreams.json` pointing at non-existent files (functional breakage for the sync pipeline)
2. AGENTS.md counts are stale (were not bumped when skills `codex-first-dispatch` and `upstream-sync` and commands `codex-first`, `clodex` were added)
3. The `using-clavain` routing skill -- injected into every session -- reports wrong counts

**Top 3 changes for consistency:**

1. **Fix `upstreams.json` fileMap** (P0-3) -- the 5 broken references will cause the upstream sync pipeline to silently drop compound-engineering command updates. This is a 2-minute fix with immediate functional impact.

2. **Update stale counts** (P0-1 + P0-2) -- AGENTS.md and `using-clavain` both show 31 skills / 22 commands instead of 32 / 24. Every new session inherits the wrong numbers. Another 2-minute fix.

3. **Clean `resolve-parallel.md` prose** (P1-3) -- this command has a typo ("liek this"), first-person voice, and informal phrasing that stands out against the professional tone of all other commands. A quick rewrite brings it in line.
