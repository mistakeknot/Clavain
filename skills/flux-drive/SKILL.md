---
name: flux-drive
description: Use when reviewing documents or codebases with multi-agent analysis — triages relevant agents from roster, launches only what matters in background mode
---

# Flux Drive — Intelligent Document Review

You are executing the flux-drive skill. This skill reviews any document (plan, brainstorm, spec, ADR, README) or an entire repository by launching **only relevant** agents selected from a static roster. Follow each phase in order. Do NOT skip phases.

**File organization:** This skill is split across phase files for readability. Read `phases/shared-contracts.md` first (defines output format and completion signals), then read each phase file as you reach it.

## Input

The user provides a file or directory path as an argument. If no path is provided, ask for one using AskUserQuestion.

Detect the input type and derive paths for use throughout all phases:

```
INPUT_PATH = <the path the user provided>
```

Then detect:
- If `INPUT_PATH` is a **file** AND content starts with `diff --git` or `--- a/`: `INPUT_FILE = INPUT_PATH`, `INPUT_DIR = <directory containing file>`, `INPUT_TYPE = diff`
- If `INPUT_PATH` is a **file** (non-diff): `INPUT_FILE = INPUT_PATH`, `INPUT_DIR = <directory containing file>`, `INPUT_TYPE = file`
- If `INPUT_PATH` is a **directory**: `INPUT_FILE = none (repo review mode)`, `INPUT_DIR = INPUT_PATH`, `INPUT_TYPE = directory`

Derive:
```
INPUT_TYPE    = file | directory | diff
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

### Step 1.0.1: Classify Project Domain

Detect the project's domain(s) using signals from `config/flux-drive/domains/index.yaml`. This runs once per project and is cached.

**Cache check:** Look for `{PROJECT_ROOT}/.claude/flux-drive.yaml`. If it exists and contains `domains:` with at least one entry, skip detection and use cached results. If the file also contains `override: true`, never re-detect — the user has manually set their domains.

**Detection** (when no cache or cache is stale):

Run the domain detection script:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py {PROJECT_ROOT} --json
```

The script reads `config/flux-drive/domains/index.yaml`, scans directories/files/build-deps/keywords, computes weighted scores (directories 0.3, files 0.2, frameworks 0.3, keywords 0.2), and writes a cache to `{PROJECT_ROOT}/.claude/flux-drive.yaml`. The highest-confidence domain is marked `primary: true`.

- **Exit 0**: Domains detected — use the JSON output.
- **Exit 1**: No domains detected — use LLM fallback below.
- **Exit 2**: Script error — log warning, proceed without domain classification.

**LLM fallback** (exit code 1, first scan only): Infer domain from the Document Profile (Step 1.1) or build system files. Set confidence to 0.5 for inferred domains. Write results to `{PROJECT_ROOT}/.claude/flux-drive.yaml`.

**Performance budget:** This step should take <10 seconds. Use `ls` and targeted `grep`, not recursive find. Skip keyword scanning if directory+file+framework signals already exceed min_confidence for at least one domain.

**Output:** The detected domains feed into Step 1.0.2 (staleness check), Step 1.1 (document profile), Step 1.2 (agent scoring with domain bonuses), and Step 2.1a (domain-specific review criteria injection into agent prompts).

### Step 1.0.2: Check Staleness (pure, no side effects)

Check if the cached domain detection results are outdated due to structural project changes. This uses a three-tier strategy (hash → git → mtime) that completes in <100ms for the common case.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py {PROJECT_ROOT} --check-stale
```

Exit codes:
- **0** → Cache is fresh, use cached domains. Proceed to Step 1.1.
- **3** → Cache is stale (structural changes detected). Proceed to Step 1.0.3.
- **4** → No cache exists (first run or deleted). Proceed to Step 1.0.3.
- **1** → No domains detected. Skip agent generation entirely. Proceed to Step 1.1.
- **2** → Script error. Log warning: "Domain detection unavailable (detect-domains.py error). Agent auto-generation skipped. Run /flux-gen manually. Proceeding with core agents only." Proceed to Step 1.1.

### Step 1.0.3: Re-detect and Compare (writes cache only)

When staleness is detected (exit 3) or no cache exists (exit 4):

1. Read previous domains from cache (if any) before re-detection.

2. Re-run detection:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py {PROJECT_ROOT} --no-cache --json
   ```
   - If exit 1 (no domains): log "No domains detected." Proceed to Step 1.1.
   - If exit 2 (error): log error, proceed to Step 1.1.

3. Compare new domain list to previous:
   - Domains unchanged → proceed to Step 1.0.4 (check agents only)
   - Domains changed → log: "Domain shift: [old] → [new]". Proceed to Step 1.0.4 with change flag set.

### Step 1.0.4: Agent Generation (writes agent files)

Auto-generate project-specific agents when domains are detected but agents are missing. This step is silent (no AskUserQuestion) — it runs non-interactively within the flux-drive pipeline.

1. **Validate domain profiles exist:**
   For each detected domain, check that `${CLAUDE_PLUGIN_ROOT}/config/flux-drive/domains/{domain}.md` exists AND has an `## Agent Specifications` section.
   - If profile missing: log warning, remove domain from generation list.
   - If ALL profiles missing: log error, suggest `--no-cache` re-detect. Skip generation.

2. **Check for existing project agents:**
   ```bash
   ls {PROJECT_ROOT}/.claude/agents/fd-*.md 2>/dev/null
   ```

3. **Decision matrix:**
   a. Agents exist AND domains unchanged → skip generation. Report "up to date."
   b. Agents exist AND domains changed →
      - Identify orphaned agents (domain removed) via YAML frontmatter check: parse `generated_by: flux-gen` and `domain:` fields
      - Identify missing agents (new domain added)
      - Log: "Domain shift: N new agents needed, M agents orphaned."
      - Generate only missing agents (don't touch existing)
   c. No agents exist AND domains detected →
      - Log: "Generating project agents for [domain1, domain2]..."
      - Generate agents using the template from `/flux-gen` Step 4 (including YAML frontmatter with `generated_by`, `domain`, `generated_at`, `flux_gen_version`)

4. **Track generation status per agent:**
   - On success: report agent name and focus line
   - On failure: log error with reason
   - After loop: "Generated N of M agents. K failed."
   - If any failed: list failures with reasons. Do NOT abort flux-drive.

5. **Report summary:**
   ```
   Domain check: game-simulation (0.65) — fresh (scanned 2026-02-09)
   Project agents: 2 exist, 1 generated, 0 failed
   ```

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
- Project domains: [from Step 1.0.1 — e.g., "game-simulation (0.65), cli-tool (0.35)" or "none detected"]
- Technologies: [specific tech mentioned]
- Divergence: [none | description — only for documents that describe code]
- Key codebase files: [list 3-5 actual files agents should read]
- Section analysis:
  - [Section name]: [thin/adequate/deep] — [1-line summary]
  - ...
- Estimated complexity: [small/medium/large]
- Review goal: [1 sentence — what should agents focus on?]
```

#### Diff Profile (when `INPUT_TYPE = diff`)

For **diff inputs**, extract a diff-specific profile instead of the document profile above:

```
Diff Profile:
- File count: [N files changed]
- Stats: [+X lines added, -Y lines removed]
- Binary files: [list any binary file changes]
- Languages detected: [from file extensions in the diff]
- Domains touched: [architecture, security, performance, UX, data, API, etc.]
- Project domains: [from Step 1.0.1 — e.g., "game-simulation (0.65), cli-tool (0.35)" or "none detected"]
- Renamed files: [list of old → new renames]
- Key files: [top 5 files by change size]
- Commit message: [if available from diff header]
- Estimated complexity: [small (<200 lines) | medium (200-1000) | large (1000+)]
- Slicing eligible: [yes if total diff lines >= 1000, no otherwise]
- Review goal: "Find issues, risks, and improvements in the proposed changes"
```

Parse the diff to extract file paths and per-file `+`/`-` line counts. For slicing eligibility, count total added + removed lines (excluding diff metadata lines like `@@` hunks and `diff --git` headers).

If `slicing_eligible: yes`, the orchestrator will apply diff slicing in Phase 2 using `config/flux-drive/diff-routing.md`. See `phases/launch.md` Step 2.1b.

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

Before scoring, eliminate agents that cannot plausibly score ≥1 based on the document/diff profile:

**For file and directory inputs:**

1. **Data filter**: Skip fd-correctness unless the document mentions databases, migrations, data models, concurrency, or async patterns.
2. **Product filter**: Skip fd-user-product unless the document type is PRD, proposal, strategy document, or has user-facing flows.
3. **Deploy filter**: Skip fd-safety unless the document mentions security, credentials, deployments, infrastructure, or trust boundaries.

**For file and directory inputs (continued):**

4. **Game filter**: Skip fd-game-design unless Step 1.0.1 detected `game-simulation` domain OR the document/project mentions game, simulation, AI behavior, storyteller, balance, procedural generation, tick loop, needs/mood systems, or drama management.

**For diff inputs** (use `config/flux-drive/diff-routing.md` patterns):

1. **Data filter**: Skip fd-correctness unless any changed file matches its priority file patterns or any hunk contains its priority keywords.
2. **Product filter**: Skip fd-user-product unless any changed file matches its priority file patterns or any hunk contains its priority keywords.
3. **Deploy filter**: Skip fd-safety unless any changed file matches its priority file patterns or any hunk contains its priority keywords.
4. **Perf filter**: Skip fd-performance unless any changed file matches its priority file patterns or any hunk contains its priority keywords.
5. **Game filter**: Skip fd-game-design unless any changed file matches its priority file patterns or any hunk contains its priority keywords.

Domain-general agents always pass the filter: fd-architecture, fd-quality, and fd-performance (for file/directory inputs only — for diffs, fd-performance is filtered by routing patterns like other domain agents).

Present only passing agents in the scoring table below.

Score the pre-filtered agents against the document profile using a **0-7 scale**:

```
Score Components:
  base_score:     0-3 (0=irrelevant, 1=tangential, 2=adjacent, 3=core domain)
  domain_boost:   0-2 (from domain profile match — see below)
  project_bonus:  0-1 (project has CLAUDE.md/AGENTS.md)
  domain_agent:   0-1 (for domain-specific generated agents from /flux-gen)

  final_score = base_score + domain_boost + project_bonus + domain_agent
  max possible = 3 + 2 + 1 + 1 = 7
```

> **Note**: Base score 0 means the agent is excluded. Bonuses cannot override irrelevance.

**Base score guide:**
- **3 (core)**: Agent's domain directly overlaps with document content (e.g., fd-safety for a security audit).
- **2 (adjacent)**: Agent's domain is relevant but not the primary focus (e.g., fd-performance for an API plan with a perf section).
- **1 (tangential)**: Agent's domain is marginally relevant. Include only for thin sections that need more depth.
- **0 (irrelevant)**: Wrong language, wrong domain, no relationship. Always excluded.

**Project bonus** (+0 or +1): Plugin Agents get +1 when the target project has CLAUDE.md/AGENTS.md (they auto-detect and use codebase-aware mode). Project Agents get +1 (project-specific by definition).

**Domain boost** (+0, +1, or +2; applied only when base score ≥ 1): When Step 1.0.1 detected a project domain, check each agent's injection criteria in the corresponding domain profile (`config/flux-drive/domains/*.md`):
- Agent has injection criteria with ≥3 bullets for this domain → +2
- Agent has injection criteria (1-2 bullets) for this domain → +1
- Agent has no injection criteria for this domain → +0

Domain profiles also provide domain-specific review bullets loaded during Phase 2 (Step 2.1a) and injected into each agent's prompt.

**Domain agent bonus** (+0 or +1): Project-specific agents generated by `/flux-gen` get +1 when the detected domain matches their specialization.

**Selection rules**:
1. All agents scoring 3+ are included (strong relevance)
2. Agents scoring 2 are included if slots remain
3. Agents scoring 1 are included only if their domain covers a thin section AND slots remain
4. **Dynamic slot ceiling** (see below) — replaces hard cap
5. **Deduplication**: If a Project Agent covers the same domain as a Plugin Agent, prefer the Project Agent
6. Prefer fewer, more relevant agents over many marginal ones

#### Dynamic slot allocation

The agent ceiling adapts to review scope and domain density:

```
base_slots    = 4                        # minimum for any review
scope_slots:
  - single file:          +0
  - small diff (<500 lines): +1
  - large diff (500+):    +2
  - directory/repo:       +3
domain_slots:
  - 0 domains detected:   +0
  - 1 domain detected:    +1
  - 2+ domains detected:  +2
generated_slots:
  - project has /flux-gen agents: +2
  - no /flux-gen agents:  +0

total_ceiling = base + scope + domain + generated
hard_maximum  = 12                       # absolute cap for resource sanity
```

**Examples:**
- Single-file review, no domain → 4 slots (lean)
- Repo review, 1 domain → 4+3+1 = 8 slots (standard)
- Repo review, 2 domains, with /flux-gen agents → 4+3+2+2 = 11 slots (full)
- Small diff, no domain → 4+1 = 5 slots (quick check)

#### Stage assignment

After selecting agents, assign dispatch stages:
- **Stage 1**: Top 40% of total slots (rounded up, min 2, max 5). Fill with highest-scoring agents. Ties broken by: Project > Plugin > Cross-AI.
- **Stage 2**: All remaining selected agents
- **Expansion pool**: Agents that scored ≥2 but didn't get a slot — these are candidates for domain-aware expansion after Stage 1 (see `phases/launch.md` Step 2.2b)

Present the triage table with a Stage column:

| Agent | Category | Score | Stage | Reason | Action |
|-------|----------|-------|-------|--------|--------|

### Scoring Examples

**Plan reviewing Go API changes (project has CLAUDE.md, web-api domain detected):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) = 5 slots. Stage 1: top 2 (40% of 5, rounded up).

| Agent | Category | Base | Domain Boost | Project | Total | Stage | Action |
|-------|----------|------|-------------|---------|-------|-------|--------|
| fd-architecture | Plugin | 3 | +2 (5 web-api items) | +1 | 6 | 1 | Launch |
| fd-safety | Plugin | 3 | +1 (4 web-api items) | +1 | 5 | 1 | Launch |
| fd-quality | Plugin | 2 | +1 (5 web-api items) | +1 | 4 | 2 | Launch |
| fd-performance | Plugin | 1 | +1 (5 web-api items) | +1 | 3 | 2 | Launch |
| fd-correctness | Plugin | 0 | — | — | 0 | — | Skip |
| fd-user-product | Plugin | 0 | — | — | 0 | — | Skip |

**README review for Python CLI tool (cli-tool domain detected):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) = 5 slots. Stage 1: top 2.

| Agent | Category | Base | Domain Boost | Project | Total | Stage | Action |
|-------|----------|------|-------------|---------|-------|-------|--------|
| fd-user-product | Plugin | 3 | +2 (5 cli-tool items) | +1 | 6 | 1 | Launch |
| fd-quality | Plugin | 3 | +1 (5 cli-tool items) | +1 | 5 | 1 | Launch |
| fd-architecture | Plugin | 1 | +1 (5 cli-tool items) | +1 | 3 | 2 | Launch (thin section) |
| fd-performance | Plugin | 0 | — | — | 0 | — | Skip |
| fd-safety | Plugin | 0 | — | — | 0 | — | Skip |
| fd-correctness | Plugin | 0 | — | — | 0 | — | Skip |

**PRD for new user onboarding flow (web-api domain detected):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) = 5 slots. Stage 1: top 2.

| Agent | Category | Base | Domain Boost | Project | Total | Stage | Action |
|-------|----------|------|-------------|---------|-------|-------|--------|
| fd-user-product | Plugin | 3 | +2 (5 web-api items) | +1 | 6 | 1 | Launch |
| fd-architecture | Plugin | 2 | +2 (5 web-api items) | +1 | 5 | 1 | Launch |
| fd-safety | Plugin | 1 | +1 (4 web-api items) | +1 | 3 | 2 | Launch (auth — thin) |
| fd-performance | Plugin | 0 | — | — | 0 | — | Skip |
| fd-quality | Plugin | 0 | — | — | 0 | — | Skip |
| fd-correctness | Plugin | 0 | — | — | 0 | — | Skip |

**Game project plan (game-simulation domain at 0.65, project has CLAUDE.md + /flux-gen agents):**

Slot ceiling: 4 (base) + 0 (single file) + 1 (1 domain) + 2 (flux-gen) = 7 slots. Stage 1: top 3 (40% of 7, rounded up).

| Agent | Category | Base | Domain Boost | Project | DA | Total | Stage | Action |
|-------|----------|------|-------------|---------|-----|-------|-------|--------|
| fd-game-design | Plugin | 3 | +2 (5 game items) | +1 | — | 6 | 1 | Launch |
| fd-simulation-kernel* | Project | 3 | +2 (generated) | +1 | +1 | 7 | 1 | Launch |
| fd-architecture | Plugin | 3 | +1 (5 game items) | +1 | — | 5 | 1 | Launch |
| fd-correctness | Plugin | 2 | +2 (5 game items, high-priority) | +1 | — | 5 | 2 | Launch |
| fd-performance | Plugin | 2 | +1 (5 game items) | +1 | — | 4 | 2 | Launch |
| fd-quality | Plugin | 2 | +1 (4 game items) | +1 | — | 4 | 2 | Launch |
| fd-safety | Plugin | 1 | +1 (4 game items) | +1 | — | 3 | 2 | Launch |
| fd-user-product | Plugin | 0 | — | — | — | 0 | — | Skip |

*Generated via /flux-gen. DA = domain_agent bonus.

**Thin section thresholds:**
- **thin**: <5 lines or <3 bullet points — agent with adjacent domain should cover this
- **adequate**: 5-30 lines or 3-10 bullet points — standard review depth
- **deep**: 30+ lines or 10+ bullet points — validation only, don't over-review

### Step 1.2c: Document Section Mapping

**Trigger:** `INPUT_TYPE = file` AND document exceeds 200 lines.

Split the document into sections and classify relevance per agent. This enables per-agent content slicing in Phase 2 (Step 2.1c).

1. **Extract sections** — Split document by `##` headings. Each section = heading + content until next heading.
2. **Classify per agent** — For each selected **domain-specific** agent, classify each section using the routing keywords from `config/flux-drive/diff-routing.md` (Section-Level Routing):
   - `priority` — section heading or body matches any of the agent's keywords → include in full
   - `context` — no keyword match → include as 1-line summary only
3. **Cross-cutting agents** (fd-architecture, fd-quality) — always receive the full document. Skip classification for these agents.
4. **Safety override** — Any section mentioning auth, credentials, secrets, tokens, or certificates is always `priority` for fd-safety.
5. **80% threshold** — If an agent's priority sections cover >= 80% of total document lines, skip slicing for that agent (send full document).

**For documents >= 500 lines**, also generate a Pyramid Summary:
- Write 1-2 sentence summaries per section
- Prepend to each agent's content as a focus guide (even cross-cutting agents benefit from the summary)

**For documents 200-500 lines**, skip summaries — classify sections only (the savings come from slicing, not from summarization overhead).

**For documents < 200 lines**, skip this step entirely — all agents receive the full document.

**Output**: A `section_map` per agent, used in Step 2.1c to write per-agent temp files:
```
section_map:
  fd-safety: {priority: ["Security", "Deployment"], context: ["Architecture", "Performance"]}
  fd-performance: {priority: ["Performance", "Scaling"], context: ["Security", "Deployment"]}
  fd-architecture: {mode: full}
  fd-quality: {mode: full}
```

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
| fd-architecture | clavain:review:fd-architecture | Module boundaries, coupling, patterns, anti-patterns, complexity |
| fd-safety | clavain:review:fd-safety | Threats, credentials, trust boundaries, deploy risk, rollback |
| fd-correctness | clavain:review:fd-correctness | Data consistency, race conditions, transactions, async bugs |
| fd-quality | clavain:review:fd-quality | Naming, conventions, test approach, language-specific idioms |
| fd-user-product | clavain:review:fd-user-product | User flows, UX friction, value prop, scope, missing edge cases |
| fd-performance | clavain:review:fd-performance | Bottlenecks, resource usage, algorithmic complexity, scaling |
| fd-game-design | clavain:review:fd-game-design | Balance, pacing, player psychology, feedback loops, emergent behavior |

### Cross-AI (Oracle)

**Availability check**: Oracle is available when:
1. The SessionStart hook reports "oracle: available for cross-AI review", OR
2. `which oracle` succeeds AND `pgrep -f "Xvfb :99"` finds a running process

If neither check passes, skip Cross-AI entirely.

When available, Oracle provides a GPT-5.2 Pro perspective on the same document. It scores like any other agent but gets a +1 diversity bonus (different model family reduces blind spots).

| Agent | Invocation | Domain |
|-------|-----------|--------|
| oracle-council | `oracle --wait -p "<prompt>" -f "<files>"` | Cross-model validation, blind spot detection |

**Important**: Oracle runs via CLI, not Task tool. Use `--write-output` to capture the clean response (stdout redirect loses output in browser mode). Do NOT wrap with `timeout` — Oracle has its own internal timeout that handles session cleanup properly.

```bash
env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait --timeout 1800 \
  --write-output {OUTPUT_DIR}/oracle-council.md.partial \
  -p "Review this {document_type} for {review_goal}. Focus on: issues a Claude-based reviewer might miss. Provide numbered findings with severity." \
  -f "{INPUT_FILE or key files}" && \
  echo '<!-- flux-drive:complete -->' >> {OUTPUT_DIR}/oracle-council.md.partial && \
  mv {OUTPUT_DIR}/oracle-council.md.partial {OUTPUT_DIR}/oracle-council.md || \
  (echo -e "---\nagent: oracle-council\ntier: cross-ai\nissues: []\nimprovements: []\nverdict: error\n---\nOracle failed (exit $?)" > {OUTPUT_DIR}/oracle-council.md)
```

**Why `--write-output` instead of `> file`**: Oracle browser mode writes the GPT response via `console.log` (not raw stdout). When piped to a file, ANSI escape codes contaminate the output and the response can be lost if the process is killed before flush. `--write-output` writes clean assistant text directly to the specified path after the browser scrape completes.

**Why no `timeout` wrapper**: External `timeout` sends SIGTERM, which kills Oracle before it can update session status or write output. Oracle's internal `--timeout` handles cleanup: it marks the session as timed-out, writes partial output, and exits cleanly. Default for gpt-5.2-pro is 60 minutes; we cap at 30 minutes (`1800`).

**Error handling**: If the Oracle command fails or times out, note it in the output file and continue without Phase 4. Do NOT block synthesis on Oracle failures — treat it as "Oracle: no findings" and skip Steps 4.2-4.5.

Oracle counts toward the dynamic slot ceiling. If the roster is already full, Oracle replaces the lowest-scoring Plugin Agent.

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
