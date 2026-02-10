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

**Run isolation:** Before launching agents, clean or verify the output directory:
- If `{OUTPUT_DIR}/` already exists and contains `.md` files, remove them to prevent stale results from contaminating this run.
- Alternatively, append a short timestamp to OUTPUT_DIR (e.g., `{INPUT_STEM}-20260209T1430`) to isolate runs. Use the simpler clean approach by default.

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
- Type: [plan | brainstorm/design | spec/ADR | prd | README/overview | repo-review | other]
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
- PRD → "Challenge assumptions, validate business case, find missing user evidence, surface scope risks"
- Other → Infer the appropriate review goal from the document's content

Do this analysis yourself (no subagents needed). The profile drives triage in Step 1.2.

### Step 1.2: Select Agents from Roster

#### Step 1.2a: Pre-filter agents

Before scoring, eliminate agents that cannot plausibly score ≥1 based on the document profile:

1. **Data filter**: Skip fd-v2-correctness unless the document mentions databases, migrations, data models, concurrency, or async patterns.
2. **Product filter**: Skip fd-v2-user-product unless the document type is PRD, proposal, strategy document, or has user-facing flows.
3. **Deploy filter**: Skip fd-v2-safety unless the document mentions security, credentials, deployments, infrastructure, or trust boundaries.

Domain-general agents always pass the filter: fd-v2-architecture, fd-v2-quality, fd-v2-performance.

Present only passing agents in the scoring table below.

Score the pre-filtered agents against the document profile. Present the scoring as a markdown table:

- **2 (relevant)**: Domain directly overlaps with document content.
- **1 (maybe)**: Adjacent domain. Include only for sections that are thin.
- **0 (irrelevant)**: Wrong language, wrong domain, no relationship to this document.

> **Note**: Base score 0 means the agent is excluded. Category bonuses cannot override irrelevance.

**Category bonuses** (applied only when base score ≥ 1): Project Agents get +1 (project-specific). Plugin Agents get +1 when the target project has CLAUDE.md/AGENTS.md (they auto-detect and use codebase-aware mode). An agent with base score 0 is always excluded regardless of bonuses.

**Selection rules**:
1. All agents scoring 2+ are included
2. Agents scoring 1 are included only if their domain covers a thin section
3. **Cap at 8 agents total** (hard maximum)
4. **Deduplication**: If a Project Agent covers the same domain as a Plugin Agent, prefer the Project Agent
5. Prefer fewer, more relevant agents over many marginal ones

#### Stage assignment

After selecting agents, assign dispatch stages:
- **Stage 1**: Top 2-3 agents by score (ties broken by: Project > Plugin > Cross-AI)
- **Stage 2**: All remaining selected agents

Present the triage table with a Stage column:

| Agent | Category | Score | Stage | Reason | Action |
|-------|----------|-------|-------|--------|--------|

### Scoring Examples

**Plan reviewing Go API changes (project has CLAUDE.md):**

| Agent | Category | Score | Reason | Action |
|-------|----------|-------|--------|--------|
| fd-v2-architecture | Plugin | 2+1=3 | Module boundaries directly affected, project docs exist | Launch |
| fd-v2-safety | Plugin | 2+1=3 | API adds new endpoints with auth, project docs exist | Launch |
| fd-v2-quality | Plugin | 2+1=3 | Go code changes, project docs exist | Launch |
| fd-v2-performance | Plugin | 1+1=2 | API mentioned but no perf section (thin) | Launch |
| fd-v2-correctness | Plugin | 0 | No database/concurrency changes | Skip |
| fd-v2-user-product | Plugin | 0 | No user-facing changes | Skip |

**README review for Python CLI tool:**

| Agent | Category | Score | Reason | Action |
|-------|----------|-------|--------|--------|
| fd-v2-user-product | Plugin | 2+1=3 | CLI UX directly relevant, project docs exist | Launch |
| fd-v2-quality | Plugin | 2+1=3 | Conventions review, project docs exist | Launch |
| fd-v2-architecture | Plugin | 1+1=2 | Only if architecture section is thin | Launch |
| fd-v2-performance | Plugin | 0 | README, no performance concerns | Skip |
| fd-v2-safety | Plugin | 0 | README, no security concerns | Skip |
| fd-v2-correctness | Plugin | 0 | No data/concurrency concerns | Skip |

**PRD for new user onboarding flow:**

| Agent | Category | Score | Reason | Action |
|-------|----------|-------|--------|--------|
| fd-v2-user-product | Plugin | 2+1=3 | PRD — user flows, value prop, scope validation, project docs exist | Launch |
| fd-v2-architecture | Plugin | 1+1=2 | PRD mentions architecture changes, project docs exist | Launch |
| fd-v2-safety | Plugin | 1 | Onboarding may involve auth — thin section | Launch |
| fd-v2-performance | Plugin | 0 | No performance surface changes | Skip |
| fd-v2-quality | Plugin | 0 | No code changes | Skip |
| fd-v2-correctness | Plugin | 0 | No data/concurrency changes | Skip |

**Thin section thresholds:**
- **thin**: <5 lines or <3 bullet points — agent with adjacent domain should cover this
- **adequate**: 5-30 lines or 3-10 bullet points — standard review depth
- **deep**: 30+ lines or 10+ bullet points — validation only, don't over-review

### Step 1.3: User Confirmation

First, present the triage table showing all agents, tiers, scores, stages, reasons, and Launch/Skip actions.

Then use **AskUserQuestion** to get approval:

```
AskUserQuestion:
  question: "Stage 1: [agent names]. Stage 2 (on-demand): [agent names]. Launch Stage 1?"
  options:
    - label: "Approve"
      description: "Launch Stage 1 agents"
    - label: "Edit selection"
      description: "Adjust stage assignments or agents"
    - label: "Cancel"
      description: "Stop flux-drive review"
```

If user selects "Edit selection", adjust and re-present.
If user selects "Cancel", stop here.

---

## Agent Roster

### Project Agents (.claude/agents/fd-*.md)

Check if `.claude/agents/fd-*.md` files exist in the project root. If so, include them in triage. Use `subagent_type: general-purpose` and include the agent file's full content as the system prompt in the task prompt.

**Note:** `general-purpose` agents have full tool access (Read, Grep, Glob, Write, Bash, etc.) — the same as Plugin Agents. The difference is that Plugin Agents get their system prompt from the plugin automatically, while Project Agents need it pasted into the task prompt.

If no Project Agents exist AND clodex mode is active, flux-drive will bootstrap them via Codex (see `phases/launch-codex.md`). If no Project Agents exist and clodex mode is NOT active, skip this category entirely.

### Plugin Agents (clavain)

These agents are provided by the Clavain plugin. They auto-detect project documentation: when CLAUDE.md/AGENTS.md exist, they provide codebase-aware analysis; otherwise they fall back to general best practices.

| Agent | subagent_type | Domain |
|-------|--------------|--------|
| fd-v2-architecture | clavain:review:fd-v2-architecture | Module boundaries, coupling, patterns, anti-patterns, complexity |
| fd-v2-safety | clavain:review:fd-v2-safety | Threats, credentials, trust boundaries, deploy risk, rollback |
| fd-v2-correctness | clavain:review:fd-v2-correctness | Data consistency, race conditions, transactions, async bugs |
| fd-v2-quality | clavain:review:fd-v2-quality | Naming, conventions, test approach, language-specific idioms |
| fd-v2-user-product | clavain:review:fd-v2-user-product | User flows, UX friction, value prop, scope, missing edge cases |
| fd-v2-performance | clavain:review:fd-v2-performance | Bottlenecks, resource usage, algorithmic complexity, scaling |

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
  -f "{INPUT_FILE or key files}" > {OUTPUT_DIR}/oracle-council.md.partial 2>&1 && \
  echo '<!-- flux-drive:complete -->' >> {OUTPUT_DIR}/oracle-council.md.partial && \
  mv {OUTPUT_DIR}/oracle-council.md.partial {OUTPUT_DIR}/oracle-council.md || \
  (echo -e "---\nagent: oracle-council\ntier: cross-ai\nissues: []\nimprovements: []\nverdict: error\n---\nOracle failed (exit $?)" > {OUTPUT_DIR}/oracle-council.md)
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

## Phase 4: Cross-AI Comparison (Optional)

**Skip this phase if Oracle was not in the review roster.** For cross-AI options without Oracle, mention `/clavain:interpeer` in the Phase 3 report.

If Oracle participated, read `phases/cross-ai.md` now.

---

## Integration

**Chains to (user-initiated, after Phase 4 consent gate):**
- `interpeer` — when user wants to investigate cross-AI disagreements

**Suggests (when Oracle absent, in Phase 3 report):**
- `interpeer` — lightweight cross-AI second opinion

**Called by:**
- `/clavain:flux-drive` command

**See also:**
- `interpeer/references/oracle-reference.md` — Oracle CLI reference
- `interpeer/references/oracle-troubleshooting.md` — Oracle troubleshooting
- qmd MCP server — semantic search for project documentation (used in Step 1.0)
- When clodex mode is active, flux-drive dispatches review agents through Codex CLI instead of Claude subagents. See `clavain:clodex` for Codex dispatch details.
