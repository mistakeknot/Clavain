---
agent: pattern-recognition-specialist
tier: 3
issues:
  - id: P0-1
    severity: P0
    section: "Cross-Reference Integrity"
    title: "agent-native-audit command uses /clavain:agent-native-architecture (skill slash-invocation) which is not valid syntax"
  - id: P1-1
    severity: P1
    section: "Stale Component Counts"
    title: "AGENTS.md and using-clavain/SKILL.md say 31 skills and 22 commands but actual counts are 32 skills and 24 commands"
  - id: P1-2
    severity: P1
    section: "Routing Table Completeness"
    title: "using-clavain routing table is missing 7 commands and 2 skills added after the initial merge"
  - id: P1-3
    severity: P1
    section: "Content Duplication"
    title: "resolve-parallel and resolve-todo-parallel share identical workflow text with typo 'liek this' and missing space 'type.Make'"
  - id: P1-4
    severity: P1
    section: "Upstream Residue"
    title: "engineering-docs skill uses custom XML tags (critical_sequence, validation_gate, decision_gate) contradicting create-agent-skills guidance of 'No XML tags'"
  - id: P1-5
    severity: P1
    section: "Functional Overlap"
    title: "create-agent-skills and writing-skills skills overlap significantly in purpose -- both cover skill authoring"
  - id: P2-1
    severity: P2
    section: "YAML Frontmatter Consistency"
    title: "Skill description quoting is inconsistent -- 2 of 32 quoted, 30 unquoted"
  - id: P2-2
    severity: P2
    section: "YAML Frontmatter Consistency"
    title: "Skill description phrasing varies -- 26 use 'Use when', 3 use 'This skill should be used when', 3 use declarative/imperative form"
  - id: P2-3
    severity: P2
    section: "YAML Frontmatter Consistency"
    title: "command argument-hint quoting inconsistent -- 2 of 21 unquoted with YAML-ambiguous square brackets"
  - id: P2-4
    severity: P2
    section: "YAML Frontmatter Consistency"
    title: "Agent description format varies -- plan-reviewer uses YAML block scalar '|' while all other 22 use inline double-quoted strings"
  - id: P2-5
    severity: P2
    section: "YAML Frontmatter Consistency"
    title: "pr-comment-resolver is the only agent with a 'color' field -- remnant from compound-engineering"
  - id: P2-6
    severity: P2
    section: "YAML Frontmatter Consistency"
    title: "learnings-researcher is the only agent with model: haiku -- all other 22 use model: inherit"
  - id: P2-7
    severity: P2
    section: "Content Duplication"
    title: "learnings command and engineering-docs skill overlap in purpose -- command orchestrates parallel subagents for the same task the skill handles step-by-step"
improvements:
  - id: IMP-1
    title: "Update AGENTS.md and using-clavain/SKILL.md counts to 32 skills and 24 commands"
    section: "Stale Component Counts"
  - id: IMP-2
    title: "Add missing commands and skills to using-clavain routing table"
    section: "Routing Table Completeness"
  - id: IMP-3
    title: "Extract shared resolve workflow into a skill referenced by both resolve-parallel and resolve-todo-parallel"
    section: "Content Duplication"
  - id: IMP-4
    title: "Replace custom XML tags in engineering-docs with standard markdown or remove enforcement attributes"
    section: "Upstream Residue"
  - id: IMP-5
    title: "Merge create-agent-skills into writing-skills or document clear scope boundary between them"
    section: "Functional Overlap"
  - id: IMP-6
    title: "Fix agent-native-audit to use Skill tool invocation instead of slash command for skill loading"
    section: "Cross-Reference Integrity"
  - id: IMP-7
    title: "Create a CI validation script that checks component counts and cross-references against filesystem"
    section: "Cross-Reference Integrity"
  - id: IMP-8
    title: "Standardize skill description phrasing to 'Use when...' pattern"
    section: "YAML Frontmatter Consistency"
verdict: needs-changes
---

### Summary

This is a fresh analysis of the Clavain plugin (32 skills, 23 agents, 24 commands) following the upstream merge debt scrub in commit 94ba13f. The scrub resolved many previously-flagged issues: snake_case command filenames are now kebab-case, dead agent references (`cora-test-reviewer`, `data-integrity-guardian`) are removed, the `engineering-docs` heading is corrected, `user-invocable` field naming is consistent, the learnings-researcher path to `yaml-schema.md` is fixed, and `@agent-` dispatch syntax in plan-review is gone. However, new issues have surfaced: AGENTS.md and the routing table have not been updated to reflect post-scrub additions (32 skills, 24 commands), 7 commands and 2 skills are absent from the routing table, and structural inconsistencies from the multi-upstream origin remain (custom XML tags in engineering-docs, overlapping skill scopes, duplicated command workflow text with typos).

---

### Section-by-Section Review

#### 1. YAML Frontmatter Consistency

**Skills (32 files)**

All 32 skills have the required `name` and `description` fields. The `name` field consistently uses kebab-case and matches the directory name in every case. No skill is missing either required field.

Optional fields used by some skills:
- `allowed-tools`: 2 skills (`engineering-docs`, `slack-messaging`)
- `preconditions`: 1 skill (`engineering-docs`)
- `user-invocable: false`: 1 skill (`slack-messaging`)

Description quoting is inconsistent. 30 of 32 skills use unquoted descriptions. Two use double-quoted strings:
- `/root/projects/Clavain/skills/flux-drive/SKILL.md`: `description: "Intelligent document review ..."`
- `/root/projects/Clavain/skills/brainstorming/SKILL.md`: `description: "You MUST use this before any creative work ..."`

Both contain em-dashes that could cause YAML parsing issues in some parsers. However, many unquoted descriptions also contain em-dashes (e.g., `landing-a-change`, `refactor-safely`, `oracle-review`) without quoting, so the quoting is not consistently applied.

Description phrasing patterns across all 32 skills:

| Pattern | Count | Skills |
|---------|-------|--------|
| "Use when..." | 26 | Most skills follow this convention |
| "This skill should be used when..." | 3 | `file-todos`, `distinctive-design` (reworded from previous review -- `engineering-docs` no longer uses this phrasing) |
| Declarative/imperative form | 3 | `agent-native-architecture` ("Build applications where..."), `create-agent-skills` ("Expert guidance for..."), `codex-first-dispatch` ("Streamlined single-task Codex dispatch...") |
| "Use MCP..." | 1 | `mcp-cli` |
| Coercive phrasing | 1 | `brainstorming` ("You MUST use this before...") |

Note: some skills use multiple patterns. The totals above reflect the primary opening pattern. The dominant "Use when..." convention should be standardized.

One special case: `engineering-docs` uses a declarative start ("Capture solved problems...") which is neither "Use when" nor "This skill should be used when." This is the only skill with a completely terse declarative description lacking any trigger condition.

**Agents (23 files)**

All 23 agents have the required `name`, `description`, and `model` fields. Every agent has `<example>` and `<commentary>` blocks in the description (100% compliance). Every agent uses `model: inherit` except one:
- `/root/projects/Clavain/agents/research/learnings-researcher.md`: `model: haiku`

This is an intentional choice -- the learnings-researcher is a lightweight grep-based search agent that benefits from the cheaper, faster model. This is a legitimate exception but should be documented in AGENTS.md.

One agent has an extra field not present in any other:
- `/root/projects/Clavain/agents/workflow/pr-comment-resolver.md`: `color: blue`

No other agent uses `color`. This appears to be a remnant from the compound-engineering upstream.

Description format consistency. 22 of 23 agents use inline double-quoted strings for the description field. One exception:
- `/root/projects/Clavain/agents/review/plan-reviewer.md`: uses YAML block scalar (`description: |`)

The block scalar is functionally equivalent but visually different from the standard pattern. All other agents embed `<example>` blocks within the quoted string using `\\n` for newlines.

Agent description lengths continue to vary enormously. The shortest (`code-simplicity-reviewer`) has 2 examples in approximately 8 lines. The longest (`spec-flow-analyzer`) has 3 detailed examples spanning approximately 30 lines. While all follow the `<example>` + `<commentary>` convention, the extreme length variation means context window cost varies significantly per agent dispatch.

**Commands (24 files)**

All 24 commands have `name` and `description`. 21 of 24 include `argument-hint`. The 3 without are:
- `write-plan` and `execute-plan` (use `disable-model-invocation: true` instead)
- `upstream-sync` (uses `allowed-tools` list instead)

The `argument-hint` quoting is mostly consistent. 19 of 21 use double-quoted strings. Two exceptions:
- `/root/projects/Clavain/commands/heal-skill.md`: `argument-hint: [optional: specific issue to fix]` (unquoted)
- `/root/projects/Clavain/commands/create-agent-skill.md`: `argument-hint: [skill description or requirements]` (unquoted)

Both contain square brackets which YAML could interpret as arrays. These should be quoted for safety.

**Field naming is now consistent.** The previous report flagged `user_invocable` (underscore) vs `user-invocable` (hyphen). This has been fixed -- both `/root/projects/Clavain/commands/flux-drive.md` and `/root/projects/Clavain/skills/slack-messaging/SKILL.md` now use the hyphenated form.

---

#### 2. Naming Convention Consistency

**All naming conventions are now consistent.** The scrub commit (94ba13f) resolved the snake_case vs kebab-case split in command filenames.

- **Skill directories**: All 32 use kebab-case. No exceptions.
- **Agent files**: All 23 use kebab-case. No exceptions.
- **Command files**: All 24 use kebab-case. No exceptions.
- **Agent category directories**: All 3 (`review/`, `research/`, `workflow/`) use lowercase.

The `name` field in frontmatter matches the filename/directory in every case across all 79 components.

---

#### 3. Stale Component Counts

CLAUDE.md and plugin.json have been updated to "32 skills, 23 agents, 24 commands" but two critical files still show stale counts:

| File | Location | Says | Actual |
|------|----------|------|--------|
| `/root/projects/Clavain/AGENTS.md` | Line 12 | "31 skills, 23 agents, 22 commands" | 32 skills, 23 agents, 24 commands |
| `/root/projects/Clavain/AGENTS.md` | Line 20 | "31 discipline skills" | 32 |
| `/root/projects/Clavain/AGENTS.md` | Line 37 | "22 slash commands" | 24 |
| `/root/projects/Clavain/skills/using-clavain/SKILL.md` | Line 22 | "31 skills, 23 agents, and 22 commands" | 32 skills, 23 agents, and 24 commands |

The `using-clavain/SKILL.md` count mismatch is especially impactful because this file is injected into every session via the SessionStart hook. Users see "31 skills" at the start of every conversation when there are actually 32.

---

#### 4. Routing Table Completeness

The 3-layer routing table in `/root/projects/Clavain/skills/using-clavain/SKILL.md` is missing the following components:

**Missing commands (7):**
| Command | Suggested Stage |
|---------|----------------|
| `execute-plan` | Execute |
| `resolve-pr-parallel` | Review or Execute |
| `triage` | Review |
| `migration-safety` | Data domain |
| `agent-native-audit` | Review or Meta |
| `codex-first` | Execute (mode toggle) |
| `clodex` | Execute (alias for codex-first) |

**Missing skills (2):**
| Skill | Suggested Location |
|-------|-------------------|
| `codex-first-dispatch` | Execute stage, or under codex-delegation |
| `create-agent-skills` | Meta stage (currently only referenced via the `create-agent-skill` command) |

**Missing from Key Commands Quick Reference (line 122+):**
The quick reference table lists 10 commands. It omits high-use commands like `execute-plan`, `resolve-pr-parallel`, `migration-safety`, `triage`, and `codex-first`.

---

#### 5. Cross-Reference Integrity

The scrub commit resolved most dead references. The remaining issues:

**Dead slash-command reference:**
- `/root/projects/Clavain/commands/agent-native-audit.md` line 29: `/clavain:agent-native-architecture`
- `agent-native-architecture` is a **skill**, not a command. Skills are invoked via the `Skill` tool, not via slash command syntax. The command instructs the agent to invoke it as a slash command, which will fail or produce no effect.
- **Fix**: Replace `/clavain:agent-native-architecture` with an instruction to invoke the skill via the Skill tool (e.g., "Invoke the `clavain:agent-native-architecture` skill").

**All other cross-references verified clean:**
- All `/clavain:` command references in `lfg.md` resolve correctly.
- The `brainstorm` command correctly references the `brainstorming` skill.
- The `write-plan` and `execute-plan` commands correctly reference `writing-plans` and `executing-plans` skills.
- The `upstream-sync` command correctly references the `upstream-sync` skill.
- The `flux-drive` command correctly references the `flux-drive` skill.
- The `quality-gates` command references real agents from the review category.
- The `plan-review` command correctly uses `subagent_type: "clavain:review:*"` syntax for all 3 agents.
- The `learnings-researcher` agent correctly references `skills/engineering-docs/references/yaml-schema.md` (file exists).
- The `learnings` command correctly routes to `engineering-docs` skill (line 172).

---

#### 6. Content Duplication

**High duplication: resolve-parallel and resolve-todo-parallel**

These two commands share near-identical Plan and Implement sections. Both contain the same typo "liek this" (should be "like this") and the same missing space "type.Make" (should be "type. Make"). The `resolve-pr-parallel` command has been cleaned up and no longer shares this text.

Shared verbatim block in `/root/projects/Clavain/commands/resolve-parallel.md` lines 17-29 and `/root/projects/Clavain/commands/resolve-todo-parallel.md` lines 19-31:

```
Create a TodoWrite list of all unresolved items grouped by type.Make sure to look at
dependencies that might occur and prioritize the ones needed by others...

So if there are 3 comments, it will spawn 3 pr-comment-resolver agents in parallel. liek this
```

The `resolve-pr-parallel` command (lines 29-41) has the same structural pattern but with corrected text ("Like this" instead of "liek this") and no "type.Make" issue. This inconsistency confirms the scrub fixed one file but not the other two.

**Moderate duplication: Kieran reviewer agents**

The four Kieran reviewers share the same opening structure:
- Same persona: "You are Kieran, a super senior [X] developer..."
- Same first two sections: "EXISTING CODE MODIFICATIONS - BE VERY STRICT" / "NEW CODE - BE PRAGMATIC"
- Language-specific content diverges after that

This is acceptable by design -- each agent must be self-contained since they run as independent subagents. The `kieran-shell-reviewer` uses "systems engineer" instead of "developer" in its persona, which is a legitimate variation reflecting the different domain.

**Functional overlap: create-agent-skills vs writing-skills**

Both skills cover skill authoring:
- `/root/projects/Clavain/skills/create-agent-skills/SKILL.md`: "Expert guidance for creating, writing, and refining Claude Code Skills"
- `/root/projects/Clavain/skills/writing-skills/SKILL.md`: "Use when creating new skills, editing existing skills, or verifying skills work before deployment"

The `create-agent-skills` skill focuses on the Anthropic spec, markdown format, and code structure. The `writing-skills` skill focuses on the TDD-inspired process of testing skills with subagents. They are complementary but their descriptions overlap enough to cause confusion about which to invoke. The `create-agent-skill` command delegates to `create-agent-skills` via `allowed-tools: Skill(create-agent-skills)`, but the routing table lists `writing-skills` as the Meta-stage skill. A user asking to "write a skill" could reasonably be routed to either.

**Functional overlap: learnings command vs engineering-docs skill**

`/root/projects/Clavain/commands/learnings.md` orchestrates parallel subagents to document solved problems. `/root/projects/Clavain/skills/engineering-docs/SKILL.md` provides a detailed 7-step sequential process for the same task. The command says "Routes To: `engineering-docs` skill" (line 172) but does not actually invoke it -- it defines its own parallel workflow. The relationship between them is unclear: does the command replace the skill, augment it, or delegate to it?

---

#### 7. Upstream Residue (Post-Scrub)

The scrub commit removed most upstream contamination (Rails references, compound-docs heading, Every.to patterns, `/doc-fix` command, Python init script, `hotwire-native` reference). Remaining upstream residue:

**engineering-docs skill: Custom XML tags**

`/root/projects/Clavain/skills/engineering-docs/SKILL.md` uses 5 custom XML tag types not found anywhere else in Clavain:
- `<critical_sequence name="..." enforce_order="strict">` (line 26)
- `<step number="N" required="true" depends_on="N">` (multiple instances)
- `<validation_gate name="..." blocking="true">` (line 148)
- `<decision_gate name="..." wait_for_user="true">` (line 257)
- `<integration_protocol>` (line 344)
- `<success_criteria>` (line 363)

These are from the compound-engineering origin. They contradict the guidance in `/root/projects/Clavain/skills/create-agent-skills/SKILL.md` line 18: "**No XML tags** - use standard markdown headings." The tags may or may not affect Claude's behavior (Claude does parse custom XML), but they create an inconsistency with Clavain's own documented conventions.

**pr-comment-resolver: color field**

`/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` has `color: blue` on line 4. No other agent uses this field. It is a cosmetic remnant from compound-engineering that has no documented effect in Claude Code's agent specification.

---

### Issues Found

#### P0 -- Critical

**P0-1: agent-native-audit uses slash-command syntax to invoke a skill**
- File: `/root/projects/Clavain/commands/agent-native-audit.md` line 29
- Text: `/clavain:agent-native-architecture`
- `agent-native-architecture` is a skill at `/root/projects/Clavain/skills/agent-native-architecture/SKILL.md`, not a command in `commands/`.
- Skills are loaded via the `Skill` tool, not slash commands. This instruction will either fail silently or do nothing.
- Impact: The agent-native-audit command's Step 1 fails, degrading the entire audit workflow.

#### P1 -- Important

**P1-1: AGENTS.md and using-clavain/SKILL.md show stale component counts**
- `/root/projects/Clavain/AGENTS.md` line 12: says "31 skills, 23 agents, 22 commands" -- should be "32 skills, 23 agents, 24 commands"
- `/root/projects/Clavain/AGENTS.md` line 20: says "31 discipline skills" -- should be "32"
- `/root/projects/Clavain/AGENTS.md` line 37: says "22 slash commands" -- should be "24"
- `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 22: says "31 skills, 23 agents, and 22 commands" -- should be "32 skills, 23 agents, and 24 commands"
- Impact: Every session starts with incorrect counts. Users trusting the routing table may miss newer components.

**P1-2: Routing table missing 7 commands and 2 skills**
- File: `/root/projects/Clavain/skills/using-clavain/SKILL.md` Layer 1 table (lines 32-41)
- Missing commands: `execute-plan`, `resolve-pr-parallel`, `triage`, `migration-safety`, `agent-native-audit`, `codex-first`, `clodex`
- Missing skills: `codex-first-dispatch`, `create-agent-skills`
- Impact: The routing table is the primary discovery mechanism. Missing components are effectively invisible.

**P1-3: resolve-parallel and resolve-todo-parallel contain duplicated text with typos**
- Files: `/root/projects/Clavain/commands/resolve-parallel.md` line 23, `/root/projects/Clavain/commands/resolve-todo-parallel.md` line 25
- Typo: "liek this" (should be "like this")
- Missing space: "type.Make" (should be "type. Make")
- The cleaned-up `resolve-pr-parallel` no longer has these typos, confirming the scrub missed these two files.
- Impact: Cosmetic but undermines quality perception. The duplicated text should be factored out.

**P1-4: engineering-docs uses custom XML tags contradicting create-agent-skills guidance**
- File: `/root/projects/Clavain/skills/engineering-docs/SKILL.md` lines 26, 148, 257, 344, 363
- Tags: `<critical_sequence>`, `<step>`, `<validation_gate>`, `<decision_gate>`, `<integration_protocol>`, `<success_criteria>`
- Contradicts: `/root/projects/Clavain/skills/create-agent-skills/SKILL.md` line 18: "**No XML tags** - use standard markdown headings"
- Impact: Internal inconsistency in Clavain's own guidance. If someone creates a new skill following `create-agent-skills`, they would avoid XML tags, but `engineering-docs` demonstrates the opposite pattern.

**P1-5: create-agent-skills and writing-skills have overlapping scope**
- `/root/projects/Clavain/skills/create-agent-skills/SKILL.md`: "Expert guidance for creating, writing, and refining Claude Code Skills"
- `/root/projects/Clavain/skills/writing-skills/SKILL.md`: "Use when creating new skills, editing existing skills, or verifying skills work before deployment"
- The routing table only lists `writing-skills` in the Meta stage. The `create-agent-skill` command delegates to `create-agent-skills`.
- Impact: Ambiguity about which skill to invoke for skill authoring. A clear scope boundary should be documented.

#### P2 -- Low

**P2-1: Skill description quoting inconsistency**
- 30 of 32 unquoted; 2 double-quoted (`brainstorming`, `flux-drive`)
- Both quoted descriptions contain em-dashes, but so do many unquoted ones

**P2-2: Skill description phrasing inconsistency**
- 26 of 32 use "Use when..." (the convention in AGENTS.md)
- 3 use "This skill should be used when..." (`file-todos`, `distinctive-design`)
- 3 use declarative/imperative form (`agent-native-architecture`, `create-agent-skills`, `codex-first-dispatch`)

**P2-3: Unquoted argument-hint values with square brackets**
- `/root/projects/Clavain/commands/heal-skill.md`: `argument-hint: [optional: specific issue to fix]`
- `/root/projects/Clavain/commands/create-agent-skill.md`: `argument-hint: [skill description or requirements]`
- YAML may interpret unquoted `[...]` as arrays

**P2-4: plan-reviewer uses YAML block scalar for description**
- `/root/projects/Clavain/agents/review/plan-reviewer.md` line 3: `description: |`
- All other 22 agents use inline double-quoted strings
- Functionally equivalent but visually inconsistent

**P2-5: pr-comment-resolver has orphaned color field**
- `/root/projects/Clavain/agents/workflow/pr-comment-resolver.md` line 4: `color: blue`
- No other agent uses this field

**P2-6: learnings-researcher uses model: haiku**
- `/root/projects/Clavain/agents/research/learnings-researcher.md` line 4: `model: haiku`
- All other 22 agents use `model: inherit`
- This is intentional but undocumented in AGENTS.md

**P2-7: Overlap between learnings command and engineering-docs skill**
- `/root/projects/Clavain/commands/learnings.md` defines a 7-subagent parallel workflow
- `/root/projects/Clavain/skills/engineering-docs/SKILL.md` defines a 7-step sequential workflow
- The command claims to route to the skill but implements its own workflow
- Unclear which is canonical

---

### Improvements Suggested

**IMP-1: Update component counts** (fixes P1-1)
- `/root/projects/Clavain/AGENTS.md` line 12: change to "32 skills, 23 agents, 24 commands, 2 hooks, 2 MCP servers"
- `/root/projects/Clavain/AGENTS.md` line 20: change "31 discipline skills" comment to "32 discipline skills"
- `/root/projects/Clavain/AGENTS.md` line 37: change "22 slash commands" comment to "24 slash commands"
- `/root/projects/Clavain/skills/using-clavain/SKILL.md` line 22: change to "32 skills, 23 agents, and 24 commands"

**IMP-2: Complete the routing table** (fixes P1-2)
- Add `execute-plan` to Execute stage commands (alongside `work` and `lfg`)
- Add `resolve-pr-parallel` to Review or Execute stage
- Add `triage` to Review stage
- Add `migration-safety` to Data domain
- Add `agent-native-audit` to Review or Meta stage
- Add `codex-first`/`clodex` to Execute stage or Meta stage
- Add `codex-first-dispatch` to Execute stage skills
- Add `create-agent-skills` to Meta stage skills (alongside `writing-skills`)
- Expand the Key Commands Quick Reference to include at least `execute-plan`, `triage`, `migration-safety`

**IMP-3: Extract shared resolve workflow** (fixes P1-3)
- Create a shared skill (e.g., `skills/parallel-resolution/SKILL.md`) containing the common Analyze/Plan/Implement/Commit workflow
- Have `resolve-parallel`, `resolve-todo-parallel`, and `resolve-pr-parallel` reference this skill
- Fix the "liek this" typo and "type.Make" spacing in the shared content
- Differentiate each command only in Step 1 (what to resolve: TODOs vs todos/ files vs PR comments)

**IMP-4: Replace custom XML tags in engineering-docs** (fixes P1-4)
- Convert `<critical_sequence>`, `<step>`, `<validation_gate>`, `<decision_gate>`, `<integration_protocol>`, and `<success_criteria>` to standard markdown sections
- Example: `<step number="1" required="true">` becomes `### Step 1 (Required)`
- Example: `<validation_gate name="yaml-schema" blocking="true">` becomes `### Validation Gate: YAML Schema (Blocking)`
- This aligns with `create-agent-skills` guidance and removes the last major upstream structural remnant

**IMP-5: Clarify skill scope boundaries** (fixes P1-5)
- Document in AGENTS.md: `writing-skills` = TDD-inspired process for testing and iterating skills; `create-agent-skills` = structural guidance on SKILL.md format and Anthropic spec compliance
- Alternatively, merge them into a single `writing-skills` skill with the format reference from `create-agent-skills` as a sub-file

**IMP-6: Fix agent-native-audit skill invocation** (fixes P0-1)
- Replace line 29 of `/root/projects/Clavain/commands/agent-native-audit.md` from:
  ```
  /clavain:agent-native-architecture
  ```
  to:
  ```
  Invoke the `clavain:agent-native-architecture` skill using the Skill tool.
  ```

**IMP-7: Create a CI validation script for component counts and cross-references**
- Count SKILL.md files, agent .md files, command .md files
- Compare against stated counts in AGENTS.md, CLAUDE.md, using-clavain/SKILL.md, plugin.json
- Scan for `/clavain:*` references and verify each resolves to an actual command file
- Scan for `clavain:*` skill references and verify each resolves to an actual skill directory
- Run as part of the existing validation checklist in AGENTS.md (lines 162-173)

**IMP-8: Standardize skill description phrasing** (fixes P2-2)
- Convert the 6 non-conforming descriptions to "Use when..." pattern:
  - `distinctive-design`: "Use when creating distinctive..." (from "This skill should be used when...")
  - `file-todos`: "Use when managing the file-based todo..." (from "This skill should be used when...")
  - `agent-native-architecture`: "Use when designing agent-native applications..." (from "Build applications where...")
  - `create-agent-skills`: "Use when creating, writing, or refining Claude Code Skills..." (from "Expert guidance for...")
  - `codex-first-dispatch`: "Use when dispatching a single task to Codex..." (from "Streamlined single-task...")
  - `engineering-docs`: "Use when documenting a solved problem..." (from "Capture solved problems...")

---

### Overall Assessment

The Clavain plugin's structural integrity has improved significantly since the upstream merge debt scrub (commit 94ba13f). The most severe issues from the previous review -- dead agent references, snake_case filenames, stale upstream headings, and inconsistent field naming -- are all resolved. The naming convention is now uniformly kebab-case across all 79 components. All 23 agents comply with the `<example>` + `<commentary>` description pattern. All frontmatter has the required fields.

The remaining issues cluster into two categories:

1. **Post-scrub staleness** (P1-1, P1-2): The scrub added new components (codex-first-dispatch skill, codex-first command, clodex command) and renamed others, but AGENTS.md and the routing table were not updated to reflect the new counts and additions. This is the highest-priority fix because the routing table is the architectural linchpin -- it is injected into every session and determines how the agent discovers capabilities.

2. **Structural legacy from multi-upstream origin** (P1-3, P1-4, P1-5, P2-5, P2-7): The engineering-docs skill retains custom XML tags from compound-engineering. The resolve commands retain duplicated text with typos. The create-agent-skills/writing-skills overlap exists because they came from different upstreams (superpowers-dev vs superpowers) and have not been reconciled. These are not blocking but represent ongoing maintenance debt.

The single P0 issue (agent-native-audit using slash-command syntax for a skill) is a quick one-line fix.

**Verdict: needs-changes** -- the P0 skill invocation error and P1 stale routing table should be fixed before the next release. The P1 typos and XML tag cleanup should follow shortly. The P2 items are maintenance-level work that can be scheduled incrementally.
