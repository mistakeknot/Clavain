---
name: flux-drive
description: Use when reviewing documents or codebases with multi-agent analysis — triages relevant agents from roster, launches only what matters in background mode
---

# Flux Drive — Intelligent Document Review

You are executing the flux-drive skill. This skill reviews any document (plan, brainstorm, spec, ADR, README) or an entire repository by launching **only relevant** agents selected from a static roster. Follow each phase in order. Do NOT skip phases.

**Progressive loading:** This skill is split across phase files. Read each phase file when you reach it — not before.

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

**Category bonuses**: Domain Specialists get +1 (always codebase-aware). Project Agents get +1 (project-specific). Adaptive Reviewers architecture-strategist, security-sentinel, and performance-oracle get +1 when the target project has CLAUDE.md/AGENTS.md (they auto-detect and use codebase-aware mode).

**Selection rules**:
1. All agents scoring 2+ are included
2. Agents scoring 1 are included only if their domain covers a thin section
3. **Cap at 8 agents total** (hard maximum)
4. **Deduplication**: If a Domain Specialist or Project Agent covers the same domain as an Adaptive Reviewer, prefer the more specific agent
5. Prefer fewer, more relevant agents over many marginal ones

### Scoring Examples

**Plan reviewing Go API changes (project has CLAUDE.md):**

| Agent | Category | Score | Reason | Action |
|-------|----------|-------|--------|--------|
| architecture-strategist | Adaptive | 2+1=3 | Module boundaries directly affected, project docs exist | Launch |
| security-sentinel | Adaptive | 2+1=3 | API adds new endpoints, project docs exist | Launch |
| performance-oracle | Adaptive | 1+1=2 | API mentioned but no perf section (thin) | Launch |
| fd-user-experience | Domain | 0+1=1 | No UI/CLI changes | Skip |
| go-reviewer | Adaptive | 2 | Go code changes | Launch |

**README review for Python CLI tool:**

| Agent | Category | Score | Reason | Action |
|-------|----------|-------|--------|--------|
| fd-user-experience | Domain | 2+1=3 | CLI UX directly relevant | Launch |
| fd-code-quality | Domain | 2+1=3 | Conventions review | Launch |
| code-simplicity-reviewer | Adaptive | 2 | YAGNI check | Launch |
| architecture-strategist | Adaptive | 1+1=2 | Only if architecture section is thin | Launch |
| security-sentinel | Adaptive | 0 | README, no security concerns | Skip |

**Thin section thresholds:**
- **thin**: <5 lines or <3 bullet points — agent with adjacent domain should cover this
- **adequate**: 5-30 lines or 3-10 bullet points — standard review depth
- **deep**: 30+ lines or 10+ bullet points — validation only, don't over-review

### Step 1.3: User Confirmation

First, present the triage table showing all agents, tiers, scores, reasons, and Launch/Skip actions.

Then use **AskUserQuestion** to get approval:

```
AskUserQuestion:
  question: "Launch N agents (M domain specialists, K adaptive reviewers) for flux-drive review?"
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

### Domain Specialists

These agents always read the target project's CLAUDE.md and AGENTS.md before analyzing, grounding their review in the project's actual architecture, conventions, and patterns rather than generic checklists.

| Agent | subagent_type | Domain |
|-------|--------------|--------|
| fd-user-experience | clavain:review:fd-user-experience | CLI/TUI interaction, keyboard ergonomics, terminal constraints |
| fd-code-quality | clavain:review:fd-code-quality | Naming, test strategy, project conventions, idioms |

### Project Agents (.claude/agents/fd-*.md)

Check if `.claude/agents/fd-*.md` files exist in the project root. If so, include them in triage. Use `subagent_type: general-purpose` and include the agent file's full content as the system prompt in the task prompt.

**Note:** `general-purpose` agents have full tool access (Read, Grep, Glob, Write, Bash, etc.) — the same as Domain Specialists. The difference is that Domain Specialists get their system prompt from the plugin automatically, while Project Agents need it pasted into the task prompt.

If no Project Agents exist AND clodex mode is active, flux-drive will bootstrap them via Codex (see `phases/launch-codex.md`). If no Project Agents exist and clodex mode is NOT active, skip this category entirely.

### Adaptive Reviewers (clavain)

These agents auto-detect project documentation: when CLAUDE.md/AGENTS.md exist, they provide codebase-aware analysis; otherwise they fall back to general best practices.

| Agent | subagent_type | Domain |
|-------|--------------|--------|
| architecture-strategist | clavain:review:architecture-strategist | Module boundaries, component structure, system design |
| security-sentinel | clavain:review:security-sentinel | Threat model, credential handling, access patterns |
| performance-oracle | clavain:review:performance-oracle | Rendering, data processing, resource usage, scaling |
| code-simplicity-reviewer | clavain:review:code-simplicity-reviewer | YAGNI, minimalism, over-engineering |
| pattern-recognition-specialist | clavain:review:pattern-recognition-specialist | Anti-patterns, duplication, consistency |
| data-integrity-reviewer | clavain:review:data-integrity-reviewer | Migrations, data safety, transactions |
| concurrency-reviewer | clavain:review:concurrency-reviewer | Race conditions, async bugs, goroutine/channel lifecycle |
| deployment-verification-agent | clavain:review:deployment-verification-agent | Pre/post-deploy checklists, rollback, migration safety |
| go-reviewer | clavain:review:go-reviewer | Go code quality, idioms, error handling |
| python-reviewer | clavain:review:python-reviewer | Python code quality, Pythonic patterns, type hints |
| typescript-reviewer | clavain:review:typescript-reviewer | TypeScript code quality, type safety, React patterns |
| shell-reviewer | clavain:review:shell-reviewer | Shell script safety, quoting, portability |
| rust-reviewer | clavain:review:rust-reviewer | Rust code quality, ownership, unsafe soundness |

### Cross-AI (Oracle)

**Availability check**: Oracle is available when:
1. The SessionStart hook reports "oracle: available for cross-AI review", OR
2. `which oracle` succeeds AND `pgrep -f "Xvfb :99"` finds a running process

If neither check passes, skip Cross-AI entirely.

When available, Oracle provides a GPT-5.2 Pro perspective on the same document. It scores like any other agent but gets a +1 diversity bonus (different model family reduces blind spots).

| Agent | Invocation | Domain |
|-------|-----------|--------|
| oracle-council | `oracle --wait -p "<prompt>" -f "<files>"` | Cross-model validation, blind spot detection |

**Important**: Oracle runs via CLI, not Task tool. Launch it in background with a timeout:
```bash
timeout 480 env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "Review this {document_type} for {review_goal}. Focus on: issues a Claude-based reviewer might miss. Provide numbered findings with severity." \
  -f "{INPUT_FILE or key files}" > {OUTPUT_DIR}/oracle-council.md 2>&1 || echo "Oracle failed (exit $?) — continuing without cross-AI perspective" >> {OUTPUT_DIR}/oracle-council.md
```

**Error handling**: If the Oracle command fails or times out, note it in the output file and continue without Phase 4. Do NOT block synthesis on Oracle failures — treat it as "Oracle: no findings" and skip Steps 4.2-4.5.

Oracle counts toward the 8-agent cap. If the roster is already full, Oracle replaces the lowest-scoring Adaptive Reviewer.

---

## Phase 2: Launch

**Read the launch phase file now:**
- Read `phases/launch.md` (in the flux-drive skill directory)
- If clodex mode is detected, also read `phases/launch-codex.md`

## Phase 3: Synthesize

**Read the synthesis phase file now:**
- Read `phases/synthesize.md` (in the flux-drive skill directory)

## Phase 4: Cross-AI Escalation (Optional)

**Read the cross-AI phase file now:**
- Read `phases/cross-ai.md` (in the flux-drive skill directory)

---

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
