---
name: flux-drive
description: Use when reviewing documents or codebases with multi-agent analysis — triages relevant agents from roster, launches only what matters in background mode
---

# Flux Drive — Intelligent Document Review

You are executing the flux-drive skill. This skill reviews any document (plan, brainstorm, spec, ADR, README) or an entire repository by launching **only relevant** agents selected from a static roster. Follow each phase in order. Do NOT skip phases.

## Input

The user provides a file or directory path as an argument. If no path is provided, ask for one using AskUserQuestion.

Detect the input type and derive paths for use throughout all phases:

```
INPUT_PATH = <the path the user provided>
```

Then detect:
- If `INPUT_PATH` is a **file**: `INPUT_FILE = INPUT_PATH`, `INPUT_DIR = <directory containing file>`
- If `INPUT_PATH` is a **directory**: `INPUT_FILE = none (repo review mode)`, `INPUT_DIR = INPUT_PATH`

Derive:
```
INPUT_STEM    = <filename without extension, or directory basename for repo reviews>
PROJECT_ROOT  = <nearest ancestor directory containing .git, or INPUT_DIR>
OUTPUT_DIR    = {PROJECT_ROOT}/docs/research/flux-drive/{INPUT_STEM}
```

**Critical:** Resolve `OUTPUT_DIR` to an **absolute path** before using it in agent prompts. Agents inherit the main session's CWD, so relative paths write to the wrong project during cross-project reviews.

---

## Phase 1: Analyze + Static Triage

### Step 1.0: Understand the Project

**Before profiling the document**, understand the project's actual tech stack and structure. This is always useful — even for repo reviews.

1. Check the project root for build system files:
   ```bash
   ls {PROJECT_ROOT}/  # Look for Cargo.toml, go.mod, package.json, etc.
   ```
2. For **file inputs**: Compare what the document describes against reality (language, framework, architecture)
3. For **directory inputs**: This IS the primary analysis — read README, build files, key source files
4. If there is a **significant divergence** between what a document describes and the actual codebase (e.g., document says Swift but code is Rust+TS):
   - Note it in the document profile as `divergence: [description]`
   - Read 2-3 key codebase files to understand the actual tech stack
   - Use the **actual** tech stack for triage, not the document's
   - All agent prompts must include the divergence context and actual file paths

A document-codebase divergence is itself a P0 finding — every agent should be told about it.

### Step 1.1: Analyze the Document

For **file inputs**: Read the file at `INPUT_FILE`.
For **repo reviews**: Read README.md (or equivalent), build system files (go.mod, package.json, Cargo.toml, etc.), directory structure (`ls` key directories), and 2-3 key source files.

Extract a structured profile:

```
Document Profile:
- Type: [plan | brainstorm/design | spec/ADR | README/overview | repo-review | other]
- Summary: [1-2 sentence description of what this document is]
- Languages: [from codebase, not just the document]
- Frameworks: [from codebase, not just the document]
- Domains touched: [architecture, security, performance, UX, data, API, etc.]
- Technologies: [specific tech mentioned]
- Divergence: [none | description — only for documents that describe code]
- Key codebase files: [list 3-5 actual files agents should read]
- Section analysis:
  - [Section name]: [thin/adequate/deep] — [1-line summary]
  - ...
- Estimated complexity: [small/medium/large]
- Review goal: [1 sentence — what should agents focus on?]
```

The `Review goal` adapts to document type:
- Plan → "Find gaps, risks, missing steps"
- Brainstorm/design → "Evaluate feasibility, surface missing alternatives, challenge assumptions"
- README/repo-review → "Evaluate quality, find gaps, suggest improvements"
- Spec/ADR → "Find ambiguities, missing edge cases, implementation risks"
- Other → Infer the appropriate review goal from the document's content

Do this analysis yourself (no subagents needed). The profile drives triage in Step 1.2.

### Step 1.2: Select Agents from Roster

Consult the **Agent Roster** below and score each agent against the document profile:

- **2 (relevant)**: Domain directly overlaps with document content.
- **1 (maybe)**: Adjacent domain. Include only for sections that are thin.
- **0 (irrelevant)**: Wrong language, wrong domain, no relationship to this document.

**Tier bonuses**: Tier 1 agents get +1 (they know this codebase). Tier 2 agents get +1 (project-specific).

**Cross-project awareness**: If the document is for a different project than the one where gurgeh-plugin is installed, Tier 1 agents' codebase knowledge is for the *wrong* project. In this case, their tier bonus reflects domain expertise only — score them honestly and prefer Tier 3 agents when the domain overlap is the same but the codebase is different.

**Selection rules**:
1. All agents scoring 2+ are included
2. Agents scoring 1 are included only if their domain covers a thin section
3. **Cap at 8 agents total** (hard maximum)
4. **Deduplication**: If a Tier 1 or Tier 2 agent covers the same domain as a Tier 3 agent, drop the Tier 3 one — unless the document is for a different project (cross-project mode), in which case prefer the Tier 3 generic.
5. Prefer fewer, more relevant agents over many marginal ones

### Step 1.3: User Confirmation

Present the triage using AskUserQuestion:

```
Flux Drive Triage — {INPUT_STEM}

| Agent | Tier | Score | Reason | Action |
|-------|------|-------|--------|--------|
| fd-architecture | T1 | 2+1 | Document restructures module boundaries | Launch |
| fd-user-experience | T1 | 2+1 | Document adds new TUI views | Launch |
| security-sentinel | T3 | 1 | Document adds API endpoint (thin section) | Launch |
| ... | ... | ... | ... | ... |

Launching N agents (M codebase-aware, K generic). Approve?
```

Options: `Approve` / `Edit selection` / `Cancel`

If user selects "Edit selection", adjust and re-present.
If user selects "Cancel", stop here.

---

## Agent Roster

### Tier 1 — Codebase-Aware (gurgeh-plugin)

These agents ship with gurgeh-plugin and have baked-in knowledge of the project's architecture, conventions, and patterns.

**Availability check**: Before triage, verify gurgeh-plugin is installed by checking if `gurgeh-plugin:fd-architecture` is in the Task tool's agent list. If gurgeh-plugin is not available, skip Tier 1 entirely and rely on Tier 2/3 agents. Note this in the triage output.

| Agent | subagent_type | Domain |
|-------|--------------|--------|
| fd-architecture | gurgeh-plugin:fd-architecture | Module boundaries, component structure, cross-tool integration |
| fd-user-experience | gurgeh-plugin:fd-user-experience | CLI/TUI interaction, keyboard ergonomics, terminal constraints |
| fd-code-quality | gurgeh-plugin:fd-code-quality | Naming, test strategy, project conventions, idioms |
| fd-performance | gurgeh-plugin:fd-performance | Rendering, data processing, resource usage |
| fd-security | gurgeh-plugin:fd-security | Threat model, credential handling, access patterns |

### Tier 2 — Project-Specific (.claude/agents/fd-*.md)

Check if `.claude/agents/fd-*.md` files exist in the project root. If so, include them in triage. Use `subagent_type: general-purpose` and include the agent file's full content as the system prompt in the task prompt.

**Note:** `general-purpose` agents have full tool access (Read, Grep, Glob, Write, Bash, etc.) — the same as Tier 1 agents. The difference is that Tier 1 agents get their system prompt from the plugin automatically, while Tier 2 agents need it pasted into the task prompt.

If no Tier 2 agents exist, skip this tier entirely. Do NOT create them — that's a separate workflow.

### Tier 3 — Generic Specialists (clavain)

These are general-purpose reviewers without codebase-specific knowledge. Only use when no Tier 1/2 agent covers the domain.

| Agent | subagent_type | Domain |
|-------|--------------|--------|
| architecture-strategist | clavain:review:architecture-strategist | System design, component boundaries |
| code-simplicity-reviewer | clavain:review:code-simplicity-reviewer | YAGNI, minimalism, over-engineering |
| performance-oracle | clavain:review:performance-oracle | Algorithms, scaling, bottlenecks |
| security-sentinel | clavain:review:security-sentinel | OWASP, vulnerabilities, auth |
| pattern-recognition-specialist | clavain:review:pattern-recognition-specialist | Anti-patterns, duplication, consistency |
| data-integrity-reviewer | clavain:review:data-integrity-reviewer | Migrations, data safety, transactions |

### Tier 4 — Cross-AI (Oracle)

**Availability check**: Oracle is available when the SessionStart hook reports "oracle: available for cross-AI review". If not detected, skip Tier 4 entirely.

When available, Oracle provides a GPT-5.2 Pro perspective on the same document. It scores like any other agent but gets a +1 diversity bonus (different model family reduces blind spots).

| Agent | Invocation | Domain |
|-------|-----------|--------|
| oracle-review | `oracle --wait -p "<prompt>" -f "<files>"` | Cross-model validation, blind spot detection |

**Important**: Oracle runs via CLI, not Task tool. Launch it in background:
```bash
DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "Review this {document_type} for {review_goal}. Focus on: issues a Claude-based reviewer might miss. Provide numbered findings with severity." \
  -f "{INPUT_FILE or key files}" > {OUTPUT_DIR}/oracle-review.md 2>&1
```

Oracle counts toward the 8-agent cap. If the roster is already full, Oracle replaces the lowest-scoring Tier 3 agent.

---

## Phase 2: Launch

### Step 2.0: Prepare output directory

Create the research output directory before launching agents. Resolve to an absolute path:
```bash
mkdir -p {OUTPUT_DIR}  # Must be absolute, e.g. /root/projects/Foo/docs/research/flux-drive/my-doc-name
```

### Step 2.1: Launch agents

Launch all selected agents as parallel Task calls in a **single message**.

**Critical**: Every agent MUST use `run_in_background: true`. This prevents agent output from flooding the main conversation context.

### How to launch each agent type:

**Tier 1 agents (gurgeh-plugin)**:
- Use the native `subagent_type` from the roster (e.g., `gurgeh-plugin:fd-architecture`)
- Set `run_in_background: true`

**Tier 2 agents (.claude/agents/)**:
- `subagent_type: general-purpose`
- Include the agent file's full content as the system prompt
- Set `run_in_background: true`

**Tier 3 agents (clavain)**:
- Use the native `subagent_type` from the roster (e.g., `clavain:review:architecture-strategist`)
- Set `run_in_background: true`

**Tier 4 agent (Oracle)**:
- Run via Bash tool with `run_in_background: true` and `timeout: 600000`
- Requires `DISPLAY=:99` and `CHROME_PATH=/usr/local/bin/google-chrome-wrapper`
- Output goes to `{OUTPUT_DIR}/oracle-review.md`

### Prompt template for each agent:

```
You are reviewing a {document_type} for {review_goal}.

## Project Context

Project root: {PROJECT_ROOT}
Document: {INPUT_FILE or "Repo-level review (no specific document)"}

[If document-codebase divergence was detected in Step 1.0, add:]

CRITICAL CONTEXT: The document describes [document's tech stack] but the actual
codebase uses [actual tech stack]. Key actual files to read:
- [file1] — [what it contains]
- [file2] — [what it contains]
- [file3] — [what it contains]
Review the ACTUAL CODEBASE, not what the document describes. Note divergence
as a finding.

## Document to Review

[For file inputs: Include ONLY the sections relevant to this agent's focus area.
For large documents (200+ lines), trim sections outside the agent's domain
to a 1-line summary each. Always include: Summary, Goals, Non-Goals (if present),
and the specific sections listed in "Focus on" below.]

[For repo reviews: Include README content + key structural info gathered in Step 1.0.]

[When divergence exists, also list specific things for THIS agent to
check in the actual codebase — file paths, line numbers, known issues
you spotted during Step 1.0. This front-loads context so agents don't
waste cycles being confused by phantom code.]

## Your Focus Area

You were selected because: [reason from triage table]
Focus on: [specific sections relevant to this agent's domain]
Depth needed: [thin sections need more depth, deep sections need only validation]

## Output Requirements

Write your findings to: {OUTPUT_DIR}/{agent-name}.md

IMPORTANT: Use this EXACT absolute path. Do NOT use a relative path.

The file MUST start with a YAML frontmatter block for machine-parseable synthesis:

---
agent: {agent-name}
tier: {1|2|3}
issues:
  - id: P0-1
    severity: P0
    section: "Section Name"
    title: "Short description of the issue"
  - id: P1-1
    severity: P1
    section: "Section Name"
    title: "Short description"
improvements:
  - id: IMP-1
    title: "Short description"
    section: "Section Name"
verdict: safe|needs-changes|risky
---

After the frontmatter, structure the prose analysis as:

### Summary (3-5 lines)
[Your top findings — this is the most important section]

### Section-by-Section Review
[Only sections in your domain]

### Issues Found
[Numbered, with severity: P0/P1/P2. Must match frontmatter.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]

Be concrete. Reference specific sections by name. Don't give generic advice.
```

After launching all agents, tell the user:
- How many agents were launched
- That they are running in background
- Estimated wait time (~3-5 minutes; codebase-aware agents take longer as they explore the repo)

---

## Phase 3: Synthesize

### Step 3.0: Wait for all agents

**Do NOT start synthesis until all agents have completed.** Starting early leads to missed findings and re-edits.

Check completion by reading the task output files (preferred) or polling the output directory:
```bash
ls {OUTPUT_DIR}/
```

You expect N files (one per launched agent). If using `ls`, poll every 30 seconds. If after 5 minutes some are missing, proceed with what you have and note missing agents as "no findings."

### Step 3.1: Collect Results

For each agent's output file, read the **YAML frontmatter** first (first ~60 lines). This gives you a structured list of all issues and improvements without reading full prose. Only read the prose body if:
- An issue needs more context to understand
- You need to resolve a conflict between agents
- The frontmatter is missing or malformed (fallback to reading Summary + Issues sections)

If an agent's output file doesn't exist or is empty, note it as "no findings" and move on.

### Step 3.2: Deduplicate and Organize

1. **Group findings by section** — organize all agent findings under the section they apply to (or by topic for repo reviews)
2. **Deduplicate**: If multiple agents flagged the same issue, keep the most specific one (prefer Tier 1/2 over Tier 3)
3. **Track convergence**: Note how many agents flagged each issue (e.g., "4/6 agents"). High convergence (3+ agents) = high confidence. Include convergence counts in the Issues to Address checklist.
4. **Flag conflicts**: If agents disagree, note both positions
5. **Priority from codebase-aware agents**: When a Tier 1/2 and Tier 3 agent give different advice on the same topic, prefer the codebase-aware recommendation

### Step 3.3: Update the Document

**The write-back strategy depends on input type:**

#### For file inputs (plans, brainstorms, specs, etc.)

Read the current file at `INPUT_FILE`. **Decide the update strategy:**

- **Amend** (default): Add findings to the existing document. Use when the document is mostly correct and findings are incremental improvements.
- **Flag for archival**: When the document is fundamentally obsolete (e.g., wrong tech stack, wrong architecture), add a prominent warning at the top recommending the document be archived and rewritten. Still add findings — they apply to the actual codebase even if the document is wrong.

Add a summary section at the top:

```markdown
## Flux Drive Enhancement Summary

Reviewed by N agents (M codebase-aware, K generic) on YYYY-MM-DD.
[If divergence detected:] **WARNING: This document is outdated.** The codebase has diverged from the described [tech stack]. Consider archiving this document and writing a new one.

### Key Findings
- [Top 3-5 findings across all agents, with convergence: "(N/M agents)"]

### Issues to Address
- [ ] [Issue 1 — from agents X, Y, Z] (severity, N/M agents)
- [ ] [Issue 2 — from agent Y] (severity)
- ...
```

For each section that received feedback, add an inline note:

```markdown
> **Flux Drive** ({agent-name}): [Concise finding or suggestion]
```

Write the updated document back to `INPUT_FILE`.

#### Deepen thin sections (plans only)

If the document type is **plan** or **brainstorm/design**, and the section analysis from Step 1.1 identified any sections as `thin`, enrich them with researched content. For each thin section:

1. Launch a `Task Explore` agent to research best practices, patterns, and concrete examples for that section's topic
2. Use Context7 MCP to pull framework-specific documentation if technologies are mentioned
3. Add a `### Research Insights` block below the original content:

```markdown
### Research Insights

**Best Practices:**
- [Concrete, actionable recommendation]

**Edge Cases:**
- [Edge case and handling strategy]

**Implementation Example:**
```[language]
// Concrete code pattern from research
```

**References:**
- [Documentation or article URL]
```

Rules:
- Preserve all original content — only add below it
- Only enrich sections marked `thin` — adequate/deep sections get inline findings only
- Code examples must be syntactically correct and match the project's actual tech stack
- Skip this step entirely for specs, ADRs, READMEs, and repo reviews

#### For repo reviews (directory input, no specific file)

Do NOT modify the repo's README or any existing files. Instead, write a new summary file to `{OUTPUT_DIR}/summary.md` that:

- Summarizes all findings organized by topic
- Links to individual agent reports in the same directory
- Includes the same Enhancement Summary format (Key Findings, Issues to Address checklist)

### Step 3.4: Report to User

Tell the user:
- How many agents ran and how many were codebase-aware vs generic
- Top findings (3-5 most important)
- Which sections got the most feedback
- Where full analysis files are saved (`{OUTPUT_DIR}/`)
