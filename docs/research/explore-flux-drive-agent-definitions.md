# Flux-Drive Agent Ecosystem Analysis

**Date**: 2026-02-09
**Scope**: Complete architecture analysis of flux-drive skill's agent system

## Executive Summary

The flux-drive skill orchestrates a sophisticated multi-tier agent review system with 18 specialized review agents, dynamic dispatch routing (Claude subagents vs Codex CLI), and intelligent triage based on document profiling. The system uses a namespace-based `subagent_type` convention (`clavain:review:<agent-name>`) that maps directly to agent markdown files, with system prompts loaded from file content and tools inherited from Claude Code's general-purpose subagent context.

## Agent Roster

### Tier 1: Codebase-Aware (Always Context-Rich)

**Location**: `agents/review/fd-*.md`

| Agent | File | subagent_type | Domain |
|-------|------|---------------|--------|
| fd-user-experience | fd-user-experience.md | clavain:review:fd-user-experience | CLI/TUI UX, keyboard ergonomics, terminal constraints |
| fd-code-quality | fd-code-quality.md | clavain:review:fd-code-quality | Naming conventions, test strategy, project idioms |

**Behavior**: These agents are **mandated** to read `CLAUDE.md` and `AGENTS.md` from the target project before analysis. Their system prompts explicitly state:

```markdown
## First Step (MANDATORY)

Before any analysis, read these files to understand the project:
1. `CLAUDE.md` in the project root
2. `AGENTS.md` in the project root (if it exists)
3. [Domain-specific discovery steps]
```

This makes them uniquely qualified for project-specific concerns where generic advice fails. They score +1 in triage due to this guarantee.

### Tier 2: Project-Specific (Bootstrap on Demand)

**Location**: `.claude/agents/fd-*.md` (in target project, NOT in plugin)

**Dispatch mode**: Only active when `CLODEX_MODE=true` (presence of `.claude/autopilot.flag`)

**Bootstrap logic** (`phases/launch-codex.md` lines 19-48):
1. Check for existing `.claude/agents/fd-*.md` files
2. Compute hash of `CLAUDE.md` + `AGENTS.md`
3. Compare to stored `.claude/agents/.fd-agents-hash`
4. If missing or stale → launch blocking Codex agent with `create-review-agent.md` template
5. Bootstrap creates project-specific review agents tailored to the codebase
6. Agents use `subagent_type: general-purpose` with full system prompt pasted into task prompt

**Key insight**: Tier 2 agents are NOT part of the plugin. They're dynamically created per-project, making flux-drive adaptable to any codebase without hardcoded assumptions.

### Tier 3: Adaptive Specialists (Auto-Detect Mode)

**Location**: `agents/review/<name>.md`

| Agent | subagent_type | Domain | Lines (frontmatter) |
|-------|---------------|--------|---------------------|
| architecture-strategist | clavain:review:architecture-strategist | Module boundaries, system design | 1-50 |
| security-sentinel | clavain:review:security-sentinel | Threat model, credential handling | 1-63 |
| performance-oracle | clavain:review:performance-oracle | Rendering, data access, resource usage | 1-63 |
| code-simplicity-reviewer | clavain:review:code-simplicity-reviewer | YAGNI, over-engineering | 1-30 |
| pattern-recognition-specialist | clavain:review:pattern-recognition-specialist | Anti-patterns, duplication | 1-30 |
| data-integrity-reviewer | clavain:review:data-integrity-reviewer | Migrations, transactions, ACID | 1-30 |
| concurrency-reviewer | clavain:review:concurrency-reviewer | Race conditions, async bugs | 1-30 |
| deployment-verification-agent | clavain:review:deployment-verification-agent | Pre/post-deploy checklists | 1-20 |
| go-reviewer | clavain:review:go-reviewer | Go idioms, error handling | 1-30 |
| python-reviewer | clavain:review:python-reviewer | Pythonic patterns, type hints | 1-30 |
| typescript-reviewer | clavain:review:typescript-reviewer | Type safety, React patterns | 1-30 |
| shell-reviewer | clavain:review:shell-reviewer | Shell safety, quoting | 1-30 |
| rust-reviewer | clavain:review:rust-reviewer | Ownership, unsafe soundness | 1-30 |

**Behavior**: These agents check for project docs on startup and switch modes:

```markdown
## First Step (MANDATORY)

Check for project documentation:
1. `CLAUDE.md` in the project root
2. `AGENTS.md` in the project root

**If found:** You are in codebase-aware mode. Your review must reference these docs.
**If not found:** You are in generic mode. Apply general architectural principles.
```

The adaptive agents with this pattern (`architecture-strategist`, `security-sentinel`, `performance-oracle`) get a +1 triage bonus when project docs exist, making them as valuable as Tier 1 agents in those contexts.

### Tier 4: Cross-AI (Oracle via CLI)

**Availability check** (`SKILL.md` lines 202-206):
1. SessionStart hook reports `oracle: available for cross-AI review`, OR
2. `which oracle` succeeds AND `pgrep -f "Xvfb :99"` finds running process

**Dispatch** (`SKILL.md` lines 215-221): Via Bash tool with background execution:
```bash
timeout 300 env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "<prompt>" -f "<files>" > {OUTPUT_DIR}/oracle-council.md 2>&1
```

**Scoring**: Gets +1 diversity bonus (different model family), counts toward 8-agent cap.

**Error handling**: If Oracle fails or times out, flux-drive continues without blocking synthesis. Treated as "Oracle: no findings" in Phase 4.

## System Prompt Loading

### How Agent Definitions Become System Prompts

The `subagent_type` naming convention (`clavain:review:<agent-name>`) is a **discovery path** for Claude Code's plugin system:

1. **Plugin registration**: `agents/review/<agent-name>.md` files are discovered by Claude Code at plugin load time
2. **Namespace resolution**: `clavain:review:foo` → Plugin "clavain", category "review", agent "foo"
3. **File content = System prompt**: The body of the markdown file (after YAML frontmatter) becomes the subagent's system prompt
4. **Frontmatter metadata**: `name`, `description`, `model` fields inform the Task tool's agent roster

**Example**: When flux-drive calls `Task(subagent_type="clavain:review:go-reviewer")`, Claude Code:
- Finds `Clavain/agents/review/go-reviewer.md`
- Reads lines 7+ (body after frontmatter) as the system prompt
- Spawns a subagent with that prompt and general-purpose tool access
- Agent inherits Read, Write, Edit, Grep, Glob, Bash, etc. (same as main session)

**Critical constraint**: The agent file's `name` field in frontmatter MUST match the `<agent-name>` portion of the `subagent_type`. Otherwise Claude Code can't resolve the reference.

### Frontmatter Schema

All agent files use this format:

```yaml
---
name: agent-name
description: "Use when [trigger condition]. <example>...</example>"
model: inherit
---
```

- **name**: Must match directory filename without `.md` extension
- **description**: Natural language with `<example>` blocks showing when/why to invoke. Used by Claude's routing logic to match user intent.
- **model**: Usually `inherit` (use same model as parent session). Can override to `sonnet` or `opus` for specific agents.

**Key finding**: The description field with embedded examples is how flux-drive's triage system decides relevance. More concrete examples = better routing.

## Tool Access

### What Tools Do Agents Have?

**Answer**: Full general-purpose tool suite, same as the main Claude session.

**Evidence** (`phases/launch-codex.md` line 176):
> `general-purpose` agents have full tool access (Read, Grep, Glob, Write, Bash, etc.)

This applies to ALL flux-drive agents:
- **Tier 1 (fd-*)**: Use `subagent_type: clavain:review:fd-*` → inherit general-purpose tools
- **Tier 2 (.claude/agents/)**: Explicitly set `subagent_type: general-purpose` → full tools
- **Tier 3 (clavain specialists)**: Use `subagent_type: clavain:review:*` → inherit general-purpose tools

**Constraint** (`phases/launch.md` lines 146-149):
```markdown
## Constraints (ALWAYS INCLUDE)
- Do NOT modify any source code
- Do NOT commit or push
- Do NOT reformat unchanged code
- ONLY create the output file specified above
```

Agents have full edit/write capability but are instructed not to use it. Enforcement is via prompt, not tool restriction.

### Tools They Actually Use

From analyzing agent system prompts:

| Tool | Used By | Purpose |
|------|---------|---------|
| Read | All agents | Reading project docs (CLAUDE.md, AGENTS.md), input file, source files |
| Grep | pattern-recognition-specialist, code-simplicity-reviewer | Searching for TODOs, duplicates, anti-patterns |
| Glob | Most agents | Discovering relevant files by pattern |
| Bash | deployment-verification-agent | Running verification SQL queries, checking service status |
| Write | All agents (mandatory) | Writing findings to `{OUTPUT_DIR}/{agent-name}.md` |

**Key observation**: Agents are read-heavy. The only required Write is the findings file. No agent is expected to modify the codebase under review.

## Task Tool Subagent Type Mapping

### The Contract

When flux-drive launches an agent via Task tool:

```
TaskCreate(
  subagent_type="clavain:review:architecture-strategist",
  description="Review architecture boundaries in docs/PLAN.md",
  run_in_background=true
)
```

**What happens**:
1. Claude Code parses `subagent_type` as `{plugin}:{category}:{agent-name}`
2. Looks up `~/.claude/plugins/cache/clavain-*/agents/review/architecture-strategist.md`
3. Loads the file body as the subagent's system prompt
4. Spawns a background task with general-purpose tools
5. Subagent writes findings to the output path specified in the task prompt

**Return value**: Task completion writes to the specified file. Main session polls `{OUTPUT_DIR}/` for file existence to detect completion.

### Special Case: `general-purpose` Subagent Type

For Tier 2 agents (project-specific `.claude/agents/fd-*.md` files):

```
TaskCreate(
  subagent_type="general-purpose",
  description="<full agent system prompt>\n\n<review prompt>",
  run_in_background=true
)
```

**Why**: These agents don't exist in the plugin, so there's no `clavain:review:*` to reference. Instead:
1. The full system prompt is pasted into the task `description` field
2. `subagent_type: general-purpose` tells Claude Code "use this prompt as-is"
3. Agent still gets full tool access

**Trade-off**: Larger prompt (system prompt + review instructions in one message) but enables dynamic per-project agents.

### Background Execution (CRITICAL)

**Rule** (`phases/launch.md` line 31):
> Every agent MUST use `run_in_background: true`.

**Why**: Without this, agent output floods the main conversation context. With 8 agents running in parallel, this would consume the entire context window before synthesis even starts.

**Implementation**: `run_in_background: true` → subagent writes to file, returns task ID. Main session doesn't see agent's reasoning, only the findings file.

## Dispatch Routing: Task vs Codex

### Detection Logic

**File**: `phases/launch.md` lines 10-20

```bash
if [[ -f "${CLAUDE_PROJECT_DIR:-.}/.claude/autopilot.flag" ]]; then
  CLODEX_MODE=true  # Dispatch via Codex CLI
else
  CLODEX_MODE=false # Dispatch via Task tool
fi
```

**Trigger**: Presence of `.claude/autopilot.flag` in the project root.

### Task Dispatch Path (Default)

**File**: `phases/launch.md` Step 2.2

**Mechanism**: 
- Parallel `TaskCreate` calls in a single message (one per agent)
- Each uses `subagent_type: clavain:review:<agent-name>`
- Each sets `run_in_background: true`
- Prompt includes trimmed document + focus area + output path

**Completion detection**: Poll `{OUTPUT_DIR}/` for `{agent-name}.md` files

### Codex Dispatch Path (Opt-in)

**File**: `phases/launch-codex.md`

**Mechanism**:
1. Resolve `dispatch.sh` and `review-agent.md` template from plugin cache
2. For each agent, write task description to `/tmp/flux-drive-XXXXXX/{agent-name}.md`
3. Launch via Bash tool (background, 10min timeout):
   ```bash
   bash "$DISPATCH" \
     --template "$REVIEW_TEMPLATE" \
     --prompt-file "$TMPDIR/{agent-name}.md" \
     -C "$PROJECT_ROOT" \
     -s workspace-write
   ```
4. Codex CLI reads `CLAUDE.md` natively (via `-C` flag), no `--inject-docs` needed
5. Agent writes findings directly to `{OUTPUT_DIR}/{agent-name}.md`
6. Same completion detection as Task path

**Fallback**: If `dispatch.sh` or template not found, fall back to Task dispatch (`CLODEX_MODE=false`)

**Error handling** (`phases/launch-codex.md` lines 99-106):
- Check for missing findings files after all Bash calls complete
- Retry once with same prompt
- If still missing, fall back to Task dispatch for that agent
- Note failure in synthesis: "Agent X: Codex dispatch failed, used Task fallback"

### Why Two Dispatch Paths?

**Task path**: 
- ✅ Built into Claude Code, zero external dependencies
- ✅ Faster for small documents
- ❌ Agents run in same process, share context budget

**Codex path**:
- ✅ Agents run in separate Codex CLI processes, independent context
- ✅ Better for large repos (no context bleed between agents)
- ✅ Enables Tier 2 bootstrap (Codex can create project-specific agents)
- ❌ Requires Codex CLI installed
- ❌ Slower startup (process spawn overhead)

**Heuristic**: Use Codex for repo reviews, Task for single-file reviews.

## Prompt Assembly

### Document Trimming (Token Optimization)

**Rule** (`phases/launch.md` lines 75-83):
```markdown
IMPORTANT — Token Optimization:
For file inputs with 200+ lines, you MUST trim the document:
1. Keep FULL content for sections in agent's focus area
2. Keep Summary, Goals, Non-Goals in full (if present)
3. For ALL OTHER sections: replace with "## [Section Name] — [1-sentence summary]"
4. For repo reviews: include README + build files + 2-3 key source files only

Target: Agent should receive ~50% of the original document.
```

**Why**: With 8 agents, sending the full 1000-line document to each would use 8000 lines of context. Trimming to 500 lines saves 4000 lines per agent, enabling more agents to run in parallel.

**Implementation**: flux-drive's Step 1.1 profiles each section as thin/adequate/deep. The launch phase uses this profile to decide what to trim:
- Agent focused on Architecture? Send full Architecture section, summarize Testing section.
- Agent focused on Testing? Send full Testing section, summarize Architecture section.

### Prompt Template

**File**: `phases/launch.md` lines 53-149

All agents receive this structure:

```markdown
You are reviewing a {document_type} for {review_goal}.

## Project Context
Project root: {PROJECT_ROOT}
Document: {INPUT_FILE}

[If divergence detected:]
CRITICAL CONTEXT: Document describes X but codebase uses Y.
Review the ACTUAL CODEBASE. Note divergence as a finding.

## Document to Review
[Trimmed document per token optimization rules]

## Your Focus Area
You were selected because: [reason from triage]
Focus on: [specific sections]
Depth needed: [thin → deep, adequate → normal, deep → validation only]

## Output Requirements
Write findings to: {OUTPUT_DIR}/{agent-name}.md

File MUST start with YAML frontmatter:
---
agent: {agent-name}
tier: {1|2|3}
issues:
  - id: P0-1
    severity: P0
    section: "Section Name"
    title: "Short description"
improvements:
  - id: IMP-1
    title: "Short description"
verdict: safe|needs-changes|risky
---

[Prose structure after frontmatter]
```

**Key insight**: The prompt is assembled dynamically per agent, not a generic template. Each agent gets:
- Only the sections relevant to its domain
- Explicit instructions on what to prioritize
- Absolute output path (no relative paths, handles cross-project reviews)

### Codex Template Assembly

**File**: `skills/clodex/templates/review-agent.md`

For Codex dispatch, the template uses `{{MARKER}}` placeholders:

```markdown
You are a reviewer. Read project docs, analyze, write report.

## Project
{{PROJECT}}

## Your Agent Identity
{{AGENT_IDENTITY}}

## Phase 2: Analyze
{{REVIEW_PROMPT}}

## Phase 3: Write Report
Write findings to: {{OUTPUT_FILE}}
[Frontmatter schema]

## Constraints
- Do NOT modify source code
- Read files as needed
- Be concrete
```

**Assembly** (`scripts/dispatch.sh` lines 199-258):
- Parse task description into sections by `^[A-Z_]+:$` headers
- Extract values into associative array: `SECTIONS["PROJECT"]`, `SECTIONS["AGENT_IDENTITY"]`, etc.
- Replace `{{PROJECT}}` with `SECTIONS["PROJECT"]` using perl for safe multi-line handling
- Result: Fully assembled prompt passed to `codex exec`

**Why perl?** (`dispatch.sh` lines 247-255): Bash string replacement breaks with backticks, quotes, dollar signs in system prompts. Perl's `\Q...\E` handles literal replacements safely.

## Triage System

### Static Roster Scoring

**File**: `SKILL.md` lines 95-136

Each agent gets a base relevance score:
- **2 (relevant)**: Domain directly overlaps with document content
- **1 (maybe)**: Adjacent domain, include only if sections are thin
- **0 (irrelevant)**: Wrong language, wrong domain, skip

**Tier bonuses**:
- Tier 1: +1 (always codebase-aware)
- Tier 2: +1 (project-specific)
- Tier 3 (architecture-strategist, security-sentinel, performance-oracle): +1 when `CLAUDE.md`/`AGENTS.md` exist (adaptive mode)
- Tier 4 (Oracle): +1 (diversity bonus, different model family)

**Selection rules**:
1. All agents scoring 2+ are included
2. Agents scoring 1 included only if their domain covers a thin section
3. **Hard cap at 8 agents total**
4. **Deduplication**: If Tier 1/2 covers same domain as Tier 3, drop Tier 3
5. Prefer fewer, more relevant agents over many marginal ones

### Example Scoring

**Plan reviewing Go API changes (project has CLAUDE.md):**

| Agent | Tier | Base | Bonus | Total | Action |
|-------|------|------|-------|-------|--------|
| architecture-strategist | T3 | 2 | +1 (docs exist) | 3 | Launch |
| security-sentinel | T3 | 2 | +1 (docs exist) | 3 | Launch |
| performance-oracle | T3 | 1 | +1 (docs exist) | 2 | Launch (perf section thin) |
| fd-user-experience | T1 | 0 | +1 (tier bonus) | 1 | Skip (no UI changes) |
| go-reviewer | T3 | 2 | 0 | 2 | Launch |

Result: 4 agents (under cap, all relevant)

**README review for Python CLI tool:**

| Agent | Tier | Base | Bonus | Total | Action |
|-------|------|------|-------|-------|--------|
| fd-user-experience | T1 | 2 | +1 (tier) | 3 | Launch |
| fd-code-quality | T1 | 2 | +1 (tier) | 3 | Launch |
| code-simplicity-reviewer | T3 | 2 | 0 | 2 | Launch |
| architecture-strategist | T3 | 1 | 0 | 1 | Skip (architecture section adequate) |
| security-sentinel | T3 | 0 | 0 | 0 | Skip (README, no security concerns) |

Result: 3 agents (minimal, highly relevant)

### Thin Section Thresholds

**File**: `SKILL.md` lines 133-136

- **thin**: <5 lines or <3 bullet points → select agents with adjacent domain to cover gaps
- **adequate**: 5-30 lines or 3-10 bullet points → standard review depth
- **deep**: 30+ lines or 10+ bullet points → validation only, don't over-review

**Why this matters**: If a plan has a thin Security section (2 bullets) but the rest is deep, flux-drive will include `security-sentinel` even if its base relevance is 1. This ensures no domain is left uncovered.

## Output Format and Synthesis

### Findings File Schema

**Required** (`phases/launch.md` lines 110-147):

```yaml
---
agent: {agent-name}
tier: {1|2|3}
issues:
  - id: P0-1
    severity: P0
    section: "Section Name"
    title: "Short description"
  - id: P1-1
    severity: P1
    section: "Different Section"
    title: "Another issue"
improvements:
  - id: IMP-1
    title: "Suggested improvement"
    section: "Section Name"
verdict: safe|needs-changes|risky
---

### Summary (3-5 lines)
[Agent's top findings]

### Section-by-Section Review
[Only sections in agent's domain]

### Issues Found
[Numbered, with severity: P0/P1/P2. Must match frontmatter.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]
```

**Validation** (`phases/synthesize.md` lines 14-25):
1. Check file starts with `---` (YAML delimiter)
2. Verify required keys: `agent`, `tier`, `issues`, `verdict`
3. Classification:
   - **Valid**: Frontmatter parsed → use frontmatter-first collection
   - **Malformed**: File exists but frontmatter missing → read prose directly
   - **Missing**: File doesn't exist → "no findings"

**Frontmatter-first collection** (`phases/synthesize.md` lines 27-34):
- Read first ~60 lines (just YAML frontmatter)
- Get structured list of all issues and improvements without reading full prose
- Only read prose body if need context or resolving conflicts

**Why**: With 8 agents, reading 8 full prose reports would consume context. Frontmatter gives structured data, prose is on-demand.

### Synthesis Workflow

**File**: `phases/synthesize.md`

**Step 3.0**: Wait for all agents (poll `{OUTPUT_DIR}/` for N files)

**Step 3.1**: Validate agent output (valid/malformed/missing)

**Step 3.2**: Collect results from frontmatter (issues, improvements, verdicts)

**Step 3.3**: Deduplicate and organize
- Group findings by section
- If multiple agents flag same issue, keep most specific (prefer Tier 1/2 over Tier 3)
- Track convergence: Note how many agents flagged each issue (e.g., "4/6 agents")
- High convergence (3+ agents) = high confidence
- Flag conflicts if agents disagree

**Step 3.4**: Update the document
- **For file inputs**: Add summary section + inline notes per section
- **For repo reviews**: Write `{OUTPUT_DIR}/summary.md` (don't modify existing files)
- **Deepen thin sections** (plans only): Launch research agents, add "Research Insights" blocks

**Step 3.5**: Report to user
- How many agents ran (N codebase-aware, M generic)
- Top 3-5 findings
- Which sections got most feedback
- Where full analysis saved

### Convergence Scoring

**Key insight** (`phases/synthesize.md` line 39):
> High convergence (3+ agents) = high confidence. Include convergence counts in checklist.

**Example output**:
```markdown
### Issues to Address
- [ ] Architecture section missing error handling strategy (4/6 agents) — P1
- [ ] Security section doesn't address input validation (security-sentinel only) — P2
- [ ] Performance section lacks concrete metrics (2/6 agents) — P2
```

**Why this matters**: User can prioritize fixes based on how many independent agents flagged the same issue. 4/6 agents agreeing = strong signal, not one agent's opinion.

## Integration Points

### Chains To (when Oracle participates)

- **interpeer mine mode**: Automatically invoked when Oracle and Claude agents disagree
- **interpeer council mode**: Offered when critical decisions surface

### Chains To (when Oracle absent)

- **interpeer quick mode**: Offered as lightweight cross-AI option (Claude ↔ Codex)

### Called By

- `/clavain:flux-drive` command
- `plan-review` command (for plans specifically)
- Any workflow that needs multi-agent document review

### Uses

- **qmd MCP server**: Semantic search for project documentation (Step 1.0)
- **Context7 MCP**: Framework-specific documentation (synthesis deepening)
- **Task tool**: Subagent dispatch (default path)
- **Codex CLI**: Alternative dispatch (opt-in via autopilot.flag)
- **Oracle CLI**: Cross-AI review (Tier 4, when available)

## Architecture Insights

### Key Design Decisions

1. **Progressive loading**: flux-drive's SKILL.md is split into 4 phase files. Each phase is read on-demand, not upfront. This saves context tokens — main session only loads what it needs for current step.

2. **Namespace convention over registration**: Agents aren't "registered" in a central manifest. The `subagent_type` naming convention (`clavain:review:<agent-name>`) is self-documenting and maps directly to file paths. Claude Code discovers agents by scanning `agents/review/*.md`.

3. **Prompt-based constraints, not tool restrictions**: All agents have full Read/Write/Bash access, but prompts say "Do NOT modify source code". This trusts the agent rather than sandboxing. Trade-off: simpler implementation, relies on prompt adherence.

4. **Background execution is non-negotiable**: The entire system depends on `run_in_background: true`. Without it, 8 agents would flood context. With it, main session stays clean, synthesis reads findings files.

5. **Adaptive agents bridge generic and codebase-aware**: Tier 3 agents check for `CLAUDE.md`/`AGENTS.md` and switch modes. This means the same agent can do generic reviews (OSS projects without docs) or deep project-aware reviews (internal projects with docs) without code duplication.

6. **Tier 2 bootstrap enables per-project specialization**: Instead of hardcoding all possible project-specific agents in the plugin, flux-drive can create them on-demand via Codex. This makes the system extensible without plugin updates.

### What's Missing

1. **Agent tool restriction API**: No way to give an agent Read-only access. All agents can Write, relying on prompt to prevent misuse.

2. **Structured result format enforcement**: Agents are instructed to write YAML frontmatter, but there's no schema validation. Malformed frontmatter falls back to prose parsing.

3. **Parallel Bash dispatch in Task mode**: Task dispatch is parallel (multiple TaskCreate calls in one message), but Codex dispatch is sequential Bash calls. Potential for future optimization.

4. **Oracle fallback is brittle**: If Oracle fails, synthesis proceeds without it. No retry logic, no alternative cross-AI path. Could offer interpeer quick mode as fallback.

## Concrete Examples

### Example 1: fd-user-experience System Prompt

**File**: `agents/review/fd-user-experience.md` lines 7-52

```markdown
You are a User Experience Reviewer specialized in CLI and TUI applications.

## First Step (MANDATORY)
Before any analysis, read:
1. `CLAUDE.md` in the project root
2. `AGENTS.md` in the project root
3. Any TUI/CLI documentation

## Review Approach
1. Command ergonomics: discoverable? follow conventions?
2. Keyboard interactions: conflicts? work across terminals?
3. Information hierarchy: right info at right time?
4. Error experience: actionable feedback?
5. Progressive disclosure: new users can start simple?
6. Workflow coherence: smooth or jarring transitions?

## Terminal-Specific Concerns
- Color accessibility: degrade gracefully
- Screen real estate: work at 80x24 minimum
- Inline vs fullscreen: choice matters
- Copy-paste: can users copy output?

## Output Format
### UX Assessment
- Workflows affected
- Impact: improvement/neutral/regression

### Specific Issues (numbered)
- Location, Problem, Suggestion

### Summary
- Overall UX impact
- Top 1-3 changes
```

**Key observations**:
- Mandatory project doc reading (Tier 1 guarantee)
- Domain-specific evaluation criteria (not generic UX advice)
- Concrete constraints (80x24, copy-paste, color degradation)
- Structured output with numbered issues

### Example 2: architecture-strategist Adaptive Mode

**File**: `agents/review/architecture-strategist.md` lines 9-19

```markdown
## First Step (MANDATORY)

Check for project documentation:
1. `CLAUDE.md` in the project root
2. `AGENTS.md` in the project root
3. `docs/ARCHITECTURE.md` (if exists)

**If found:** You are in codebase-aware mode. Your review must reference these docs.
**If not found:** You are in generic mode. Apply general architectural principles (SOLID, coupling/cohesion).
```

**Key observations**:
- Mode detection is agent's responsibility, not flux-drive's
- Explicit fallback to generic advice when no docs
- "Must reference these docs" → codebase-aware reviews cite actual conventions

### Example 3: Codex Dispatch Task Description

**File**: `phases/launch-codex.md` lines 56-78

For agent `fd-code-quality` reviewing `docs/PLAN.md`:

```
PROJECT:
Clavain plugin — review task (read-only)

AGENT_IDENTITY:
You are a Code Quality Reviewer who evaluates plans against the project's actual conventions.

## First Step (MANDATORY)
Before any analysis, read:
1. `CLAUDE.md` in the project root
2. `AGENTS.md` in the project root
3. A few representative source files

[... full system prompt from fd-code-quality.md ...]

REVIEW_PROMPT:
You are reviewing a plan for "Add flux-drive skill".

## Project Context
Project root: /root/projects/Clavain
Document: docs/PLAN.md

## Document to Review
[Trimmed plan content — 50% of original]

## Your Focus Area
You were selected because: Project conventions and naming consistency
Focus on: Naming, file organization, test strategy
Depth needed: Normal review

## Output Requirements
Write findings to: /root/projects/Clavain/docs/research/flux-drive/PLAN/fd-code-quality.md
[YAML frontmatter schema]

AGENT_NAME:
fd-code-quality

TIER:
1

OUTPUT_FILE:
/root/projects/Clavain/docs/research/flux-drive/PLAN/fd-code-quality.md
```

Then `dispatch.sh` runs:
```bash
bash dispatch.sh \
  --template review-agent.md \
  --prompt-file /tmp/flux-drive-abc123/fd-code-quality.md \
  -C /root/projects/Clavain \
  -s workspace-write
```

**Key observations**:
- Section headers (`PROJECT:`, `AGENT_IDENTITY:`) match dispatch.sh parser
- Full system prompt embedded in task description (no separate file)
- Absolute paths throughout (handles cross-project reviews)
- Codex CLI reads `CLAUDE.md` natively (no `--inject-docs` needed)

## Critical Constraints

1. **subagent_type must match file structure**: `clavain:review:foo` → `agents/review/foo.md`. If mismatched, Claude Code can't resolve the agent.

2. **Background execution required**: Without `run_in_background: true`, agents flood context. With it, synthesis depends on file polling, so agents MUST write to the exact output path.

3. **Frontmatter is required but not enforced**: Agents are instructed to write YAML frontmatter, but if they don't, synthesis falls back to prose parsing. No hard validation.

4. **Absolute paths for cross-project reviews**: If flux-drive reviews `/root/projects/Foo` from `/root/projects/Bar`, relative paths break. All `OUTPUT_DIR` paths must be resolved to absolute before passing to agents.

5. **8-agent hard cap**: More agents = longer wait, more context in synthesis, diminishing returns. Hard cap prevents runaway triage.

6. **Oracle requires Xvfb + env vars**: `DISPLAY=:99` and `CHROME_PATH=/usr/local/bin/google-chrome-wrapper` aren't inherited from shell. Must be set explicitly in Bash command.

## Recommendations

### For Adding New Agents

1. **Use the namespace convention**: `agents/review/<agent-name>.md` → `clavain:review:<agent-name>`
2. **Include concrete examples in description**: `<example>` blocks with `<commentary>` help flux-drive's triage
3. **Mandate project doc reading if Tier 1**: First step must be "Read CLAUDE.md and AGENTS.md"
4. **Support adaptive mode if Tier 3**: Check for project docs, switch modes, note which mode in output
5. **Write YAML frontmatter religiously**: Even if synthesis has a prose fallback, structured data is faster

### For Extending Flux-Drive

1. **Add Tier 2 bootstrap templates**: Current system only has `create-review-agent.md`. Could add specialized templates for different project types (CLI, web app, library, etc.).
2. **Implement convergence voting**: Right now synthesis notes "4/6 agents agreed" manually. Could auto-calculate consensus and flag outliers.
3. **Add Oracle retry logic**: If Oracle times out, fall back to `interpeer quick` automatically.
4. **Support agent dependencies**: Some agents should run only if others find issues (e.g., deployment-verification-agent only if data-integrity-reviewer flags migration risks).
5. **Parallel Codex dispatch**: Launch all Codex agents in parallel Bash calls (like Task mode) instead of sequential.

### For Debugging Agent Issues

1. **Check agent file name matches subagent_type**: `clavain:review:foo` must correspond to `agents/review/foo.md`
2. **Verify frontmatter `name` field**: Must match filename without `.md`
3. **Test agent in isolation**: Launch single agent via Task tool with simplified prompt before adding to flux-drive roster
4. **Check findings file path**: Must be absolute, must exist after agent completes
5. **Enable verbose mode**: Add `echo` statements in dispatch.sh to see prompt assembly

## Conclusion

Flux-drive's agent ecosystem is a sophisticated multi-tier system that balances generic best practices (Tier 3 adaptive agents) with deep project-specific analysis (Tier 1 codebase-aware agents, Tier 2 bootstrap). The `subagent_type` convention is simple but powerful: namespace-based discovery, file content = system prompt, no central registration required.

The key innovation is **adaptive agents** that auto-detect project documentation and switch between codebase-aware and generic modes. This makes flux-drive usable for both well-documented internal projects and undocumented OSS repos, without maintaining separate agent sets.

The system's architecture prioritizes context efficiency (background execution, progressive loading, trimmed prompts) and flexibility (dual dispatch paths, bootstrap-on-demand) over rigid structure. This makes it extensible — new agents can be added by dropping a file in `agents/review/`, and new dispatch modes can be added by creating new `phases/launch-*.md` files.

The main limitation is reliance on prompt-based constraints rather than tool restrictions, but this is a conscious trade-off for simplicity. As Claude Code's plugin system matures, more structured agent capabilities (tool restrictions, schema validation, dependency resolution) could enhance flux-drive's reliability without sacrificing its flexibility.
