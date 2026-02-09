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
4. If qmd MCP tools are available, run a semantic search for project context:
   - Search for architecture decisions, conventions, and known issues relevant to the document
   - This supplements CLAUDE.md/AGENTS.md reading with broader project knowledge
   - Feed relevant results into the document profile as additional context for triage
5. If there is a **significant divergence** between what a document describes and the actual codebase (e.g., document says Swift but code is Rust+TS):
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

Consult the **Agent Roster** below and score each agent against the document profile. Present the scoring as a markdown table:

- **2 (relevant)**: Domain directly overlaps with document content.
- **1 (maybe)**: Adjacent domain. Include only for sections that are thin.
- **0 (irrelevant)**: Wrong language, wrong domain, no relationship to this document.

**Tier bonuses**: Tier 1 agents get +1 (they know this codebase). Tier 2 agents get +1 (project-specific).

**Cross-project awareness**: Tier 1 agents read the target project's CLAUDE.md/AGENTS.md to ground their analysis. When reviewing a document for a different project, they adapt to that project's context. However, if the target project has no CLAUDE.md or AGENTS.md, their codebase awareness is limited — score them honestly and prefer Tier 3 agents when domain overlap is the same.

**Selection rules**:
1. All agents scoring 2+ are included
2. Agents scoring 1 are included only if their domain covers a thin section
3. **Cap at 8 agents total** (hard maximum)
4. **Deduplication**: If a Tier 1 or Tier 2 agent covers the same domain as a Tier 3 agent, drop the Tier 3 one — unless the target project lacks CLAUDE.md/AGENTS.md (no project context), in which case prefer the Tier 3 generic.
5. Prefer fewer, more relevant agents over many marginal ones

### Scoring Examples

**Plan reviewing Go API changes:**

| Agent | Tier | Score | Reason | Action |
|-------|------|-------|--------|--------|
| fd-architecture | T1 | 2+1=3 | Module boundaries directly affected | Launch |
| fd-security | T1 | 2+1=3 | API adds new endpoints | Launch |
| fd-performance | T1 | 1+1=2 | API mentioned but no perf section (thin) | Launch |
| fd-user-experience | T1 | 0+1=1 | No UI/CLI changes | Skip |
| security-sentinel | T3 | 0 | T1 fd-security covers this (deduplicated) | Skip |

**README review for Python CLI tool:**

| Agent | Tier | Score | Reason | Action |
|-------|------|-------|--------|--------|
| fd-user-experience | T1 | 2+1=3 | CLI UX directly relevant | Launch |
| fd-code-quality | T1 | 2+1=3 | Conventions review | Launch |
| code-simplicity-reviewer | T3 | 2 | YAGNI check | Launch |
| fd-architecture | T1 | 1+1=2 | Only if architecture section is thin | Launch |
| fd-security | T1 | 0 | README, no security concerns | Skip |

**Thin section thresholds:**
- **thin**: <5 lines or <3 bullet points — agent with adjacent domain should cover this
- **adequate**: 5-30 lines or 3-10 bullet points — standard review depth
- **deep**: 30+ lines or 10+ bullet points — validation only, don't over-review

### Step 1.3: User Confirmation

First, present the triage table showing all agents, tiers, scores, reasons, and Launch/Skip actions.

Then use **AskUserQuestion** to get approval:

```
AskUserQuestion:
  question: "Launch N agents (M codebase-aware, K generic) for flux-drive review?"
  options:
    - label: "Approve"
      description: "Launch all selected agents"
    - label: "Edit selection"
      description: "Adjust which agents to launch"
    - label: "Cancel"
      description: "Stop flux-drive review"
```

If user selects "Edit selection", adjust and re-present.
If user selects "Cancel", stop here.

---

## Agent Roster

### Tier 1 — Codebase-Aware

These agents read the target project's CLAUDE.md and AGENTS.md before analyzing, grounding their review in the project's actual architecture, conventions, and patterns rather than generic checklists.

| Agent | subagent_type | Domain |
|-------|--------------|--------|
| fd-architecture | clavain:review:fd-architecture | Module boundaries, component structure, cross-tool integration |
| fd-user-experience | clavain:review:fd-user-experience | CLI/TUI interaction, keyboard ergonomics, terminal constraints |
| fd-code-quality | clavain:review:fd-code-quality | Naming, test strategy, project conventions, idioms |
| fd-performance | clavain:review:fd-performance | Rendering, data processing, resource usage |
| fd-security | clavain:review:fd-security | Threat model, credential handling, access patterns |

### Tier 2 — Project-Specific (.claude/agents/fd-*.md)

Check if `.claude/agents/fd-*.md` files exist in the project root. If so, include them in triage. Use `subagent_type: general-purpose` and include the agent file's full content as the system prompt in the task prompt.

**Note:** `general-purpose` agents have full tool access (Read, Grep, Glob, Write, Bash, etc.) — the same as Tier 1 agents. The difference is that Tier 1 agents get their system prompt from the plugin automatically, while Tier 2 agents need it pasted into the task prompt.

If no Tier 2 agents exist AND clodex mode is active, flux-drive will bootstrap them via Codex (see step `2.3`). If no Tier 2 agents exist and clodex mode is NOT active, skip this tier entirely.

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
| concurrency-reviewer | clavain:review:concurrency-reviewer | Race conditions, async bugs, goroutine/channel lifecycle |
| deployment-verification-agent | clavain:review:deployment-verification-agent | Pre/post-deploy checklists, rollback, migration safety |
| go-reviewer | clavain:review:go-reviewer | Go code quality, idioms, error handling |
| python-reviewer | clavain:review:python-reviewer | Python code quality, Pythonic patterns, type hints |
| typescript-reviewer | clavain:review:typescript-reviewer | TypeScript code quality, type safety, React patterns |
| shell-reviewer | clavain:review:shell-reviewer | Shell script safety, quoting, portability |
| rust-reviewer | clavain:review:rust-reviewer | Rust code quality, ownership, unsafe soundness |

### Tier 4 — Cross-AI (Oracle)

**Availability check**: Oracle is available when:
1. The SessionStart hook reports "oracle: available for cross-AI review", OR
2. `which oracle` succeeds AND `pgrep -f "Xvfb :99"` finds a running process

If neither check passes, skip Tier 4 entirely.

When available, Oracle provides a GPT-5.2 Pro perspective on the same document. It scores like any other agent but gets a +1 diversity bonus (different model family reduces blind spots).

| Agent | Invocation | Domain |
|-------|-----------|--------|
| oracle-council | `oracle --wait -p "<prompt>" -f "<files>"` | Cross-model validation, blind spot detection |

**Important**: Oracle runs via CLI, not Task tool. Launch it in background with a timeout:
```bash
timeout 300 env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "Review this {document_type} for {review_goal}. Focus on: issues a Claude-based reviewer might miss. Provide numbered findings with severity." \
  -f "{INPUT_FILE or key files}" > {OUTPUT_DIR}/oracle-council.md 2>&1 || echo "Oracle failed (exit $?) — continuing without cross-AI perspective" >> {OUTPUT_DIR}/oracle-council.md
```

**Error handling**: If the Oracle command fails or times out, note it in the output file and continue without Phase 4. Do NOT block synthesis on Oracle failures — treat it as "Oracle: no findings" and skip Steps 4.2-4.5.

Oracle counts toward the 8-agent cap. If the roster is already full, Oracle replaces the lowest-scoring Tier 3 agent.

---

## Phase 2: Launch

### Step 2.0: Prepare output directory

Create the research output directory before launching agents. Resolve to an absolute path:
```bash
mkdir -p {OUTPUT_DIR}  # Must be absolute, e.g. /root/projects/Foo/docs/research/flux-drive/my-doc-name
```

### Step 2.1: Detect dispatch mode

Check if clodex mode is active:

```bash
if [[ -f "${CLAUDE_PROJECT_DIR:-.}/.claude/autopilot.flag" ]]; then
  echo "CLODEX_MODE=true — dispatching review agents through Codex"
else
  echo "CLODEX_MODE=false — dispatching review agents through Task tool"
fi
```

If `CLODEX_MODE=true`: Use step `2.3` (Codex dispatch) instead of step `2.2`.
If `CLODEX_MODE=false`: Use step `2.2` (Task dispatch) as normal.

### Step 2.2: Launch agents (Task dispatch)

**Condition**: Use this step when `CLODEX_MODE=false` (default). Skip to step `2.3` if clodex mode is active.

Launch all selected agents as parallel Task calls in a **single message**.

**Critical**: Every agent MUST use `run_in_background: true`. This prevents agent output from flooding the main conversation context.

### How to launch each agent type:

**Tier 1 agents (codebase-aware)**:
- Use the native `subagent_type` from the roster (e.g., `clavain:review:fd-architecture`)
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
- Output goes to `{OUTPUT_DIR}/oracle-council.md`

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

IMPORTANT — Token Optimization:
For file inputs with 200+ lines, you MUST trim the document before including it:
1. Keep FULL content for sections listed in "Focus on" below
2. Keep Summary, Goals, Non-Goals in full (if present)
3. For ALL OTHER sections: replace with a single line: "## [Section Name] — [1-sentence summary]"
4. For repo reviews: include README + build files + 2-3 key source files only

Target: Agent should receive ~50% of the original document, not 100%.

[For file inputs: Include the trimmed document following the rules above.]

[For repo reviews: Include README content + key structural info gathered in Step 1.0.]

[When divergence exists, also list specific things for THIS agent to
check in the actual codebase — file paths, line numbers, known issues
you spotted during Step 1.0. This front-loads context so agents don't
waste cycles being confused by phantom code.]

## Your Focus Area

You were selected because: [reason from triage table]
Focus on: [specific sections relevant to this agent's domain]
Depth needed: [thin sections need more depth, deep sections need only validation]

When constructing the prompt, explicitly list which sections to include in full
and which to summarize. Example:
- FULL: Architecture, Security (agent's domain)
- SUMMARY: Skills table, Commands table, Credits (not in domain)

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

### Step 2.3: Launch agents (Codex dispatch)

**Condition**: Use this step when `CLODEX_MODE=true`. This routes review agents through Codex CLI instead of Claude subagents.

#### Resolve paths (with guards)

```bash
DISPATCH=$(find ~/.claude/plugins/cache -path '*/clavain/*/scripts/dispatch.sh' 2>/dev/null | head -1)
[[ -z "$DISPATCH" ]] && DISPATCH=$(find ~/projects/Clavain -name dispatch.sh -path '*/scripts/*' 2>/dev/null | head -1)
[[ -z "$DISPATCH" ]] && { echo "FATAL: dispatch.sh not found — falling back to Task dispatch"; CLODEX_MODE=false; }

REVIEW_TEMPLATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/skills/clodex/templates/review-agent.md' 2>/dev/null | head -1)
[[ -z "$REVIEW_TEMPLATE" ]] && REVIEW_TEMPLATE=$(find ~/projects/Clavain -path '*/skills/clodex/templates/review-agent.md' 2>/dev/null | head -1)
[[ -z "$REVIEW_TEMPLATE" ]] && { echo "FATAL: review-agent.md template not found — falling back to Task dispatch"; CLODEX_MODE=false; }
```

If either path resolution fails, fall back to Task dispatch (step `2.2`) for this run.

#### Tier 2 bootstrap (clodex mode only)

Before dispatching Tier 2 agents, check if they exist and are current:

```bash
FD_AGENTS=$(ls .claude/agents/fd-*.md 2>/dev/null)

if [[ -z "$FD_AGENTS" ]]; then
  BOOTSTRAP=true
else
  CURRENT_HASH=$(sha256sum CLAUDE.md AGENTS.md 2>/dev/null | sha256sum | cut -d' ' -f1)
  STORED_HASH=$(cat .claude/agents/.fd-agents-hash 2>/dev/null || echo "none")
  if [[ "$CURRENT_HASH" != "$STORED_HASH" ]]; then
    echo "Tier 2 agents are stale (project docs changed) — regenerating"
    BOOTSTRAP=true
  else
    BOOTSTRAP=false
  fi
fi
```

When `BOOTSTRAP=true`, dispatch a **blocking** Codex agent to create Tier 2 agents:

```bash
BOOTSTRAP_TEMPLATE=$(find ~/.claude/plugins/cache -path '*/clavain/*/skills/clodex/templates/create-review-agent.md' 2>/dev/null | head -1)
[[ -z "$BOOTSTRAP_TEMPLATE" ]] && BOOTSTRAP_TEMPLATE=$(find ~/projects/Clavain -path '*/skills/clodex/templates/create-review-agent.md' 2>/dev/null | head -1)
[[ -z "$BOOTSTRAP_TEMPLATE" ]] && { echo "WARNING: create-review-agent.md not found — skipping Tier 2 bootstrap"; BOOTSTRAP=false; }
```

Dispatch **without `run_in_background`** so it blocks until complete. Set `timeout: 300000` (5 minutes). If bootstrap fails or times out, skip Tier 2 for this run — do NOT block the rest of the review.

#### Create temp directory and task description files

```bash
FLUX_TMPDIR=$(mktemp -d /tmp/flux-drive-XXXXXX)
```

For each selected agent, write a task description file to `$FLUX_TMPDIR/{agent-name}.md`.

**IMPORTANT**: Each section header (`PROJECT:`, `AGENT_IDENTITY:`, etc.) must be on its own line with the colon at end-of-line. Content goes on subsequent lines. This matches dispatch.sh's `^[A-Z_]+:$` section parser.

```
PROJECT:
{project name} — review task (read-only)

AGENT_IDENTITY:
{paste the agent's full system prompt from the agent .md file}

REVIEW_PROMPT:
{the same prompt template from step `2.2`, with trimmed document content, focus area, and output requirements}

AGENT_NAME:
{agent-name}

TIER:
{1|2|3}

OUTPUT_FILE:
{OUTPUT_DIR}/{agent-name}.md
```

#### Dispatch all agents in parallel

Launch all Codex agents via parallel Bash calls in a single message:

```bash
bash "$DISPATCH" \
  --template "$REVIEW_TEMPLATE" \
  --prompt-file "$FLUX_TMPDIR/{agent-name}.md" \
  -C "$PROJECT_ROOT" \
  -s workspace-write
```

Notes:
- Set `run_in_background: true` and `timeout: 600000` on each Bash call
- Do NOT use `--inject-docs` — Codex reads CLAUDE.md natively via `-C`
- Do NOT use `-o` for output capture — the agent writes findings directly to `{OUTPUT_DIR}/{agent-name}.md`
- Completion is detected by checking that file's existence (same as Task dispatch path)
- **Tier 4 (Oracle)**: Unchanged — already dispatched via Bash

#### Error handling

After all background Bash calls complete, check for missing findings files. For any agent whose `{OUTPUT_DIR}/{agent-name}.md` does not exist:
1. Check the background Bash exit code — if non-zero, log the error
2. Retry once with the same prompt file
3. If retry also produces no findings file, fall back to Task dispatch for that agent
4. Note the failure in the synthesis summary: "Agent X: Codex dispatch failed, used Task fallback"

#### Cleanup

After Phase 3 synthesis completes, remove the temp directory:
```bash
rm -rf "$FLUX_TMPDIR"
```

---

## Phase 3: Synthesize

### Step 3.0: Wait for all agents

**Do NOT start synthesis until all agents have completed.** Starting early leads to missed findings and re-edits.

Check completion by reading the task output files (preferred) or polling the output directory:
```bash
ls {OUTPUT_DIR}/
```

You expect N files (one per launched agent). If using `ls`, poll every 30 seconds. If after 5 minutes some are missing, proceed with what you have and note missing agents as "no findings."

### Step 3.1: Validate Agent Output

For each agent's output file, validate structure before reading content:

1. Check the file starts with `---` (YAML frontmatter delimiter)
2. Verify required keys exist: `agent`, `tier`, `issues`, `verdict`
3. Classification:
   - **Valid**: Frontmatter parsed successfully → proceed with frontmatter-first collection
   - **Malformed**: File exists but frontmatter is missing/incomplete → fall back to prose-based reading (read Summary + Issues sections directly)
   - **Missing**: File doesn't exist or is empty → "no findings"

Report validation results to user: "5/6 agents returned valid frontmatter, 1 fallback to prose"

### Step 3.2: Collect Results

For each **valid** agent output, read the **YAML frontmatter** first (first ~60 lines). This gives you a structured list of all issues and improvements without reading full prose. Only read the prose body if:
- An issue needs more context to understand
- You need to resolve a conflict between agents

For **malformed** outputs, read the Summary + Issues sections as prose fallback.

### Step 3.3: Deduplicate and Organize

1. **Group findings by section** — organize all agent findings under the section they apply to (or by topic for repo reviews)
2. **Deduplicate**: If multiple agents flagged the same issue, keep the most specific one (prefer Tier 1/2 over Tier 3)
3. **Track convergence**: Note how many agents flagged each issue (e.g., "4/6 agents"). High convergence (3+ agents) = high confidence. Include convergence counts in the Issues to Address checklist.
4. **Flag conflicts**: If agents disagree, note both positions
5. **Priority from codebase-aware agents**: When a Tier 1/2 and Tier 3 agent give different advice on the same topic, prefer the codebase-aware recommendation

### Step 3.4: Update the Document

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

### Step 3.5: Report to User

Tell the user:
- How many agents ran and how many were codebase-aware vs generic
- Top findings (3-5 most important)
- Which sections got the most feedback
- Where full analysis files are saved (`{OUTPUT_DIR}/`)

---

## Phase 4: Cross-AI Escalation (Optional)

After synthesis, check whether Oracle was in the review roster and offer escalation into the interpeer skill stack.

### Step 4.1: Detect Oracle Participation

If Oracle (Tier 4) was **not** in the roster, offer a lightweight option:

```
Cross-AI: No Oracle perspective was included in this review.
Want a second opinion? /clavain:interpeer (quick mode) for Claude↔Codex feedback.
```

Then stop. Phase 4 only continues if Oracle participated.

### Step 4.2: Compare Model Perspectives

When Oracle was in the roster, compare its findings against the Claude-based agents:

1. Read `{OUTPUT_DIR}/oracle-council.md`
2. Compare Oracle's findings with the synthesized findings from Step 3.2
3. Classify each finding into:

| Category | Definition | Count |
|----------|-----------|-------|
| **Agreement** | Oracle and Claude agents flagged the same issue | Strong signal |
| **Oracle-only** | Oracle found something no Claude agent raised | Potential blind spot |
| **Claude-only** | Claude agents found something Oracle missed | May be codebase-specific |
| **Disagreement** | Oracle and Claude agents conflict on the same topic | Needs investigation |

### Step 4.3: Auto-Chain to Interpeer Mine Mode

If **any disagreements** were found in Step 4.2:

```
Cross-AI Analysis:
- Agreements: N (high confidence)
- Oracle-only findings: M (review these — potential blind spots)
- Claude-only findings: K (likely codebase-specific context)
- Disagreements: D (need resolution)

Disagreements detected. Running interpeer mine mode to extract actionable artifacts...
```

Then invoke `interpeer` in **mine** mode inline (do not dispatch a subagent — this runs in the main session):

1. Structure each disagreement as a conflict (The Conflict, Evidence, Resolution, Minority Report)
2. Generate artifacts: tests that would resolve the disagreement, spec clarifications, stakeholder questions
3. Present the mine mode summary

### Step 4.4: Offer Interpeer Council for Critical Decisions

After mine mode completes (or if there were no disagreements but Oracle raised P0/P1 findings), check if any finding represents a **critical architectural or security decision**. Indicators:
- P0 severity from any source
- Disagreement on architecture or security topic
- Oracle flagged a security issue that Claude agents missed

If critical decisions exist, offer council escalation:

```
Critical decision detected: [brief description]

Options:
1. Resolve now — I'll synthesize the best recommendation from available perspectives
2. Run interpeer council — full multi-model consensus review on this specific decision
3. Continue without escalation
```

If user chooses option 2, invoke `interpeer` in **council** mode for just the critical decision (not the whole document).

### Step 4.5: Final Cross-AI Summary

Present a final summary that includes the cross-AI dimension:

```markdown
## Cross-AI Review Summary

**Model diversity:** Claude agents (N) + Oracle (GPT-5.2 Pro)

| Finding Type | Count | Confidence |
|-------------|-------|-----------|
| Cross-model agreement | A | High |
| Oracle-only (blind spots) | B | Review |
| Claude-only (codebase context) | C | Moderate |
| Resolved disagreements | D | Varies |

[If interpeer mine mode ran:]
### Artifacts Generated
- N tests proposed to resolve disagreements
- M spec clarifications needed
- K stakeholder questions identified

[If interpeer council mode ran:]
### Council Decision
[Brief summary of council's synthesis on the critical decision]
```

## Integration

**Chains to (when Oracle participates):**
- `interpeer` **mine** mode — Automatically invoked when Oracle and Claude agents disagree
- `interpeer` **council** mode — Offered when critical decisions surface

**Chains to (when Oracle absent):**
- `interpeer` **quick** mode — Offered as lightweight cross-AI option

**Called by:**
- `/clavain:flux-drive` command

**See also:**
- `interpeer/references/oracle-reference.md` — Oracle CLI reference
- `interpeer/references/oracle-troubleshooting.md` — Oracle troubleshooting
- qmd MCP server — semantic search for project documentation (used in Step 1.0)
- When clodex mode is active, flux-drive dispatches review agents through Codex CLI instead of Claude subagents. See `clavain:clodex` for Codex dispatch details.
