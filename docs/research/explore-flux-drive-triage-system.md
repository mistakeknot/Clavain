# Flux-Drive Phase 1 Triage System Deep Dive

**Date**: 2026-02-12  
**Scope**: Understanding the triage flow, domain classification integration points, and required data structures

---

## Executive Summary

Flux-drive uses a **two-step triage model** in Phase 1:
1. **Step 1.0-1.1**: Analyze the project and document, extract a structured profile (no agents yet)
2. **Step 1.2**: Score pre-filtered agents against the profile, select top N, assign dispatch stages

Domain classification is **not yet integrated** into Phase 1. The current system:
- Pre-filters agents by hardcoded rules (Data, Product, Deploy, Game filters)
- Scores agents on document content
- Never reads domain profiles from `config/flux-drive/domains/`

**Integration point identified**: Domain profiles should be consumed in **Step 1.0** (after project analysis, before document analysis), injecting domain-specific scoring bonuses and filtering adjustments into Step 1.2.

---

## File Inventory

### Core Skill File
- **`skills/flux-drive/SKILL.md`** (374 lines)
  - Lines 43-276: Phase 1 (Analyze + Static Triage)
  - Lines 278-340: Agent roster definitions, integration notes

### Phase Files
- **`phases/launch.md`** (339 lines) — Phase 2: dispatch agents, monitor completion
- **`phases/synthesize.md`** (304 lines) — Phase 3: collect findings, deduplicate, report
- **`phases/shared-contracts.md`** (98 lines) — Output format, completion signals, diff slicing contract
- **`phases/cross-ai.md`** — Phase 4 (not detailed in analysis)

### Configuration Files
- **`config/flux-drive/diff-routing.md`** (134 lines) — Maps file patterns/keywords to agents for diff slicing
- **`config/flux-drive/domains/index.yaml`** (454 lines) — Domain detection signals for 11 domains
- **`config/flux-drive/domains/game-simulation.md`** (104 lines) — Example domain profile with injection criteria

---

## Phase 1 Flow: Step-by-Step Breakdown

### Input Detection (before Step 1.0)

```
INPUT_PATH (user-provided)
    ↓
Detect type: file | directory | diff
    ↓
Derive paths:
  INPUT_FILE   = path to file (if file input)
  INPUT_DIR    = directory containing file (or the directory itself if repo review)
  INPUT_TYPE   = file | directory | diff
  INPUT_STEM   = filename without ext, or dir basename
  PROJECT_ROOT = nearest .git ancestor
  OUTPUT_DIR   = {PROJECT_ROOT}/docs/research/flux-drive/{INPUT_STEM}
```

**Isolation strategy**: If `{OUTPUT_DIR}` exists with `.md` files, delete them to prevent stale artifacts.

---

### Step 1.0: Understand the Project

**Purpose**: Before analyzing the document, understand the actual tech stack and project context.

**Actions**:
1. Check `{PROJECT_ROOT}/` for build system files (Cargo.toml, go.mod, package.json, etc.)
2. For **file inputs**: Read the document, compare against actual codebase
3. For **directory inputs**: Read README.md, build files, key source files, directory structure
4. **[OPTIONAL]** Use qmd MCP tools for semantic search on architecture decisions, conventions, known issues
5. **Detect divergence**: If document describes different tech stack than actual code:
   - Note it as `divergence: [description]` in the profile
   - Read 2-3 actual codebase files
   - Use ACTUAL tech stack for triage, not the document's
   - All agent prompts must include divergence context + actual file paths

**Critical insight**: Divergence (e.g., "plan says Swift but code is Rust+TS") is itself a P0 finding—every agent must be told.

---

### Step 1.1: Analyze the Document

**Produces**: A structured **Document Profile** (or **Diff Profile** for diffs).

#### Document Profile (file/directory inputs)

```yaml
Document Profile:
  Type: [plan | brainstorm/design | spec/ADR | prd | README/overview | repo-review | other]
  Summary: [1-2 sentence description]
  Languages: [from codebase, not just document]
  Frameworks: [from codebase, not just document]
  Domains touched: [architecture, security, performance, UX, data, API, etc.]
  Technologies: [specific tech mentioned]
  Divergence: [none | description]
  Key codebase files: [3-5 actual files agents should read]
  Section analysis:
    - [Section name]: [thin/adequate/deep] — [1-line summary]
    - ...
  Estimated complexity: [small/medium/large]
  Review goal: [1 sentence — what should agents focus on?]
```

**Thin/adequate/deep definitions**:
- **thin**: <5 lines or <3 bullet points
- **adequate**: 5-30 lines or 3-10 bullet points
- **deep**: 30+ lines or 10+ bullet points

**Review goal examples**:
- Plan → "Find gaps, risks, missing steps"
- Brainstorm/design → "Evaluate feasibility, surface missing alternatives, challenge assumptions"
- README/repo → "Evaluate quality, find gaps, suggest improvements"
- Spec/ADR → "Find ambiguities, missing edge cases, implementation risks"
- PRD → "Challenge assumptions, validate business case, find missing user evidence, surface scope risks"

#### Diff Profile (diff inputs)

```yaml
Diff Profile:
  File count: [N files changed]
  Stats: [+X lines added, -Y lines removed]
  Binary files: [list]
  Languages detected: [from file extensions]
  Domains touched: [architecture, security, performance, UX, data, API, etc.]
  Renamed files: [old → new list]
  Key files: [top 5 by change size]
  Commit message: [if available]
  Estimated complexity: [small <200 | medium 200-1000 | large 1000+]
  Slicing eligible: [yes if total diff >= 1000 lines, no otherwise]
  Review goal: "Find issues, risks, and improvements in the proposed changes"
```

**Parse the diff to extract**:
- File paths and per-file +/- line counts
- For slicing eligibility: count total added + removed lines (exclude diff metadata like @@ and headers)

**Key insight**: If diff >= 1000 lines AND slicing_eligible: yes, Phase 2 will apply soft-prioritize slicing from `config/flux-drive/diff-routing.md`.

---

### Step 1.2a: Pre-filter Agents

**Before scoring**, eliminate agents that cannot plausibly score ≥1:

#### For file/directory inputs (hardcoded filters):

1. **Data filter**: Skip `fd-correctness` unless document mentions:
   - databases, migrations, data models, concurrency, async patterns

2. **Product filter**: Skip `fd-user-product` unless:
   - Document type is PRD, proposal, strategy document, OR
   - Document has user-facing flows

3. **Deploy filter**: Skip `fd-safety` unless document mentions:
   - security, credentials, deployments, infrastructure, trust boundaries

4. **Game filter**: Skip `fd-game-design` unless document/project mentions:
   - game, simulation, AI behavior, storyteller, balance, procedural generation, tick loop, needs/mood systems, drama management

**Always pass filter**:
- `fd-architecture` — domain-general
- `fd-quality` — domain-general
- `fd-performance` — domain-general (for file/directory only; for diffs, filtered by routing patterns)

#### For diff inputs (uses `config/flux-drive/diff-routing.md` patterns):

Check if any changed file matches the agent's priority file patterns OR any hunk contains the agent's priority keywords:

1. **Data**: Skip unless patterns/keywords match
2. **Product**: Skip unless patterns/keywords match
3. **Deploy**: Skip unless patterns/keywords match
4. **Perf**: Skip unless patterns/keywords match
5. **Game**: Skip unless patterns/keywords match

**Domain-general agents always pass**: `fd-architecture`, `fd-quality`

---

### Step 1.2b: Score Pre-Filtered Agents

**Scoring table** (present to user):

```markdown
| Agent | Category | Score | Stage | Reason | Action |
|-------|----------|-------|-------|--------|--------|
| fd-architecture | Plugin | 2+1=3 | 1 | [reason] | Launch |
| fd-safety | Plugin | 1+1=2 | 2 | [reason] | Launch |
| ... | ... | ... | ... | ... | ... |
```

**Scoring rules**:
- **2 (relevant)**: Domain directly overlaps with document content
- **1 (maybe)**: Adjacent domain. Include only if the section is thin
- **0 (irrelevant)**: Wrong language, wrong domain, no relationship

**Category bonuses** (applied only if base score ≥1):
- **Project Agents**: +1 (project-specific knowledge)
- **Plugin Agents**: +1 if target project has CLAUDE.md/AGENTS.md (codebase-aware mode)

**Critical rule**: Base score 0 means the agent is **excluded**. Bonuses cannot override irrelevance.

#### Selection Rules

1. **Include all agents scoring 2+**
2. **Include agents scoring 1 ONLY if their domain covers a thin section**
3. **Hard cap: 8 agents maximum**
4. **Deduplication**: If Project Agent and Plugin Agent cover same domain, prefer Project Agent
5. **Quality over quantity**: Fewer, more relevant agents over many marginal ones

#### Stage Assignment

After selection, assign dispatch stages:

- **Stage 1**: Top 2-3 agents by score (ties broken by: Project > Plugin > Cross-AI)
- **Stage 2**: All remaining selected agents

**Present triage table with Stage column** showing which agents launch immediately vs on-demand.

---

### Step 1.2c: Pyramid Scan (large documents only)

**Trigger**: `INPUT_TYPE = file` AND document > 500 lines

**Purpose**: Help agents focus by tagging sections.

**Actions**:
1. Extract all top-level sections (## headings)
2. Summarize each in 1-2 sentences
3. For each selected agent, tag each section:
   - `full` — section is in agent's core domain
   - `summary` — section is adjacent but not core
   - `skip` — section has no relevance
4. **Safety override**: Any section mentioning auth, credentials, secrets, tokens, or certificates is ALWAYS `full` for fd-safety

**Include in agent prompts** (Phase 2): Prepend the pyramid summary before the full document.

**Note**: Agents still get the full document—the pyramid summary is a focus guide, not a content gate.

---

### Step 1.3: User Confirmation

**Present the triage table** with all agents, categories, scores, stages, reasons, and Launch/Skip actions.

**Ask for approval**:
```yaml
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

**If user selects "Edit selection"**: Adjust and re-present.
**If user selects "Cancel"**: Stop here.

---

## Agent Roster

### Plugin Agents (Clavain)

| Agent | subagent_type | Domain |
|-------|--------------|--------|
| fd-architecture | clavain:review:fd-architecture | Module boundaries, coupling, patterns, complexity |
| fd-safety | clavain:review:fd-safety | Threats, credentials, trust, deploy risk, rollback |
| fd-correctness | clavain:review:fd-correctness | Data consistency, races, transactions, async bugs |
| fd-quality | clavain:review:fd-quality | Naming, conventions, testing, language idioms |
| fd-user-product | clavain:review:fd-user-product | User flows, UX friction, value prop, scope |
| fd-performance | clavain:review:fd-performance | Bottlenecks, memory, algorithmic complexity, scaling |
| fd-game-design | clavain:review:fd-game-design | Balance, pacing, psychology, feedback loops, emergent behavior |

**Auto-detection**: When CLAUDE.md/AGENTS.md exist, agents provide codebase-aware analysis. Otherwise, they fall back to general best practices.

### Project Agents (.claude/agents/)

Check if `.claude/agents/fd-*.md` files exist. If yes:
- Include them in triage
- Use `subagent_type: general-purpose`
- Paste agent file's full content as system prompt in task prompt

### Cross-AI (Oracle)

**Availability check**:
1. SessionStart hook reports "oracle: available for cross-AI review", OR
2. `which oracle` succeeds AND `pgrep -f "Xvfb :99"` finds a running process

If neither, skip Cross-AI entirely.

When available:
- Invocation: `oracle --wait -p "<prompt>" -f "<files>" --write-output {OUTPUT_DIR}/oracle-council.md.partial`
- Domain: Cross-model validation, blind spot detection
- Diversity bonus: +1 (different model family reduces blind spots)
- Output: Clean response to file (not stdout redirect)

**Oracle counts toward 8-agent cap**. If roster is full, Oracle replaces lowest-scoring Plugin Agent.

---

## Domain Profiles System (Current State)

### File Structure

**`config/flux-drive/domains/index.yaml`** (454 lines):
- Defines 11 domain profiles with detection signals
- Each domain has: `profile`, `min_confidence`, `signals`
- Signals include: directories, files, frameworks, keywords

**`config/flux-drive/domains/<domain>.md`**:
- Detection signals (primary, secondary)
- Injection criteria (per-agent domain-specific review bullets)
- Optional: domain-specific agent specs

**Example: `game-simulation.md`** (104 lines):
- Detection: directories like `game/`, `simulation/`, `ecs/`
- Detection: files like `*.gd`, `project.godot`, `balance.yaml`
- Detection: frameworks like Godot, Unity, Bevy, Pygame
- Detection: keywords like `tick_rate`, `storyteller`, `behavior_tree`
- Injection: 5 core agents (fd-architecture, fd-safety, fd-correctness, fd-quality, fd-performance, fd-user-product) + 3 optional domain-specific agents (fd-simulation-kernel, fd-game-systems, fd-agent-narrative)

### Injection Criteria Format

When a domain is detected, inject domain-specific review bullets into each core agent's prompt. Example from `game-simulation.md`:

**fd-architecture bullets**:
- Check that game systems (movement, combat, AI, economy) are decoupled enough to test and tune independently
- Verify tick/update loop architecture separates input, simulation, and rendering phases
- Flag ECS anti-patterns: systems that reach into unrelated component sets, god-components with 10+ fields
- [etc., 5 bullets per agent]

---

## Current System: Pre-Domain Integration

**Flux-drive Phase 1 currently:**
- ✅ Analyzes project (Step 1.0)
- ✅ Analyzes document (Step 1.1)
- ✅ Pre-filters agents by hardcoded rules (Step 1.2a)
- ✅ Scores agents on document content (Step 1.2b)
- ❌ **Does NOT read domain profiles** (`config/flux-drive/domains/`)
- ❌ **Does NOT inject domain-specific scoring bonuses**
- ❌ **Does NOT refine pre-filters based on detected domains**

---

## Integration Point: Where Domain Classification Fits

### Proposed Location: Step 1.0 Expansion

After understanding the project (Step 1.0), add a **domain detection substep**:

**Step 1.0a: Detect Project Domains**

1. **For each domain in `config/flux-drive/domains/index.yaml`**:
   - Score the project against the domain's signals
   - Count matching signals (directories, files, frameworks, keywords in PROJECT_ROOT)
   - If score ≥ min_confidence: domain is "detected"

2. **Detected domains list** (e.g., `["game-simulation", "web-api", "ml-pipeline"]`):
   - Can be multiple domains (e.g., a game server is both game-simulation and web-api)
   - Feed this list into Step 1.2a (pre-filtering) and Step 1.2b (scoring)

### Proposed Changes to Step 1.2a: Pre-filter Agents

**New rule**: If a domain is detected and has a profile .md file:
- Read `config/flux-drive/domains/{domain}.md`
- Check if it specifies optional domain-specific agents
- Add them to the roster before pre-filtering

Example: If `game-simulation` is detected, add fd-simulation-kernel, fd-game-systems, fd-agent-narrative to the candidate pool (they may still be filtered if the document doesn't mention them).

### Proposed Changes to Step 1.2b: Score Agents

**New bonus rule**: If a domain is detected and an agent's domain matches:
- Apply an **injection bonus**: +1 to any agent whose domain directly corresponds to a detected domain
- Example: If `game-simulation` is detected, fd-game-design gets +1 bonus

### Prompt Modification (Phase 2)

When agents are dispatched, if domain profiles were detected:
- Append domain-specific injection bullets to each agent's prompt
- Example: If fd-architecture was selected AND game-simulation was detected, inject the game-simulation bullets from `game-simulation.md` into the fd-architecture prompt

---

## Data Structures and Examples

### Document Profile (Example: Go API Plan)

```yaml
Document Profile:
  Type: plan
  Summary: "Proposal to refactor order API endpoints for streaming and reduce latency"
  Languages: [Go, SQL, TypeScript]
  Frameworks: [Fiber (Go), gorm (ORM), React (frontend)]
  Domains touched: [architecture, performance, API design]
  Technologies: [gRPC streaming, PostgreSQL, Redis caching]
  Divergence: none
  Key codebase files:
    - cmd/api/main.go (API entry point)
    - internal/models/order.go (data structures)
    - internal/handlers/order_handler.go (current endpoints)
  Section analysis:
    - Overview: adequate (5 sentences, clear scope)
    - Current Architecture: deep (20 lines + 3 diagrams, thorough baseline)
    - Proposed Changes: thin (3 bullets, lacks detail on streaming protocol)
    - Rollback Plan: thin (1 sentence)
  Estimated complexity: medium
  Review goal: "Validate API design choices, identify performance risks, assess rollback strategy"
```

### Triage Table (Example: Go API Plan)

| Agent | Category | Score | Stage | Reason | Action |
|-------|----------|-------|-------|--------|--------|
| fd-architecture | Plugin | 2+1=3 | 1 | Module boundaries directly affected, project docs exist | Launch |
| fd-performance | Plugin | 2+1=3 | 1 | Streaming + caching directly relevant, project docs exist | Launch |
| fd-safety | Plugin | 1+1=2 | 2 | Rollback section is thin, auth mentioned briefly | Launch |
| fd-quality | Plugin | 1+1=2 | 2 | Code changes present, project docs exist | Launch |
| fd-correctness | Plugin | 0 | — | No data model/transaction changes | Skip |
| fd-user-product | Plugin | 0 | — | No user-facing UX changes | Skip |

**Stage 1 launch**: fd-architecture, fd-performance  
**Stage 2 on-demand**: fd-safety, fd-quality

### Diff Profile (Example: Large Refactoring)

```yaml
Diff Profile:
  File count: 12 files changed
  Stats: +847 lines, -312 lines
  Binary files: none
  Languages detected: [Go, SQL]
  Domains touched: [architecture, performance, data integrity]
  Renamed files:
    - internal/handlers/order_v1.go → internal/handlers/orders/handler.go
    - internal/cache/redis.go → internal/cache/store.go
  Key files:
    - internal/handlers/orders/handler.go (+234 lines)
    - internal/models/order.go (+156 lines)
    - internal/db/migrations/002_add_streaming.sql (+47 lines)
  Commit message: "refactor: split order handlers, add streaming support"
  Estimated complexity: medium (200-1000 lines)
  Slicing eligible: yes
  Review goal: "Find issues, risks, and improvements in the proposed changes"
```

### Domain Detection (Example: Game Simulation)

```yaml
Detected domains:
  - game-simulation (confidence: 0.45)
    matching_signals:
      directories: [game/, ai/behavior/, tick/]
      files: [game_config.yaml, balance.json]
      frameworks: [bevy]
      keywords: [tick_rate, difficulty_curve, spawn_rate]
```

### Injection Criteria (Example: fd-architecture + game-simulation)

```yaml
fd-architecture injection:
  - Check that game systems (movement, combat, AI, economy) are decoupled enough to test and tune independently
  - Verify tick/update loop architecture separates input, simulation, and rendering phases
  - Flag ECS anti-patterns: systems that reach into unrelated component sets, god-components with 10+ fields
  - Check that save/load serialization covers all mutable game state (not just player data)
  - Verify event bus or messaging patterns don't create hidden coupling between game systems
```

---

## Diff-Routing System

### File: `config/flux-drive/diff-routing.md`

Maps file patterns and hunk keywords to agents for soft-prioritize slicing when diff >= 1000 lines.

**Two agent types**:

1. **Cross-cutting agents** (always get full diff):
   - fd-architecture
   - fd-quality

2. **Domain-specific agents** (soft-prioritized slicing):
   - fd-safety, fd-correctness, fd-performance, fd-user-product, fd-game-design

### Routing Rules

For each domain-specific agent, define:

**Priority file patterns** (glob syntax):
```
fd-safety patterns:
  - **/auth/**, **/authentication/**, **/authorization/**
  - **/deploy/**, **/deployment/**, **/infra/**, **/terraform/**
  - **/credential*, **/secret*, **/vault/**
  - **/.env*, **/docker-compose*, **/Dockerfile*
  - [etc., 9 more patterns]
```

**Priority hunk keywords** (comma-separated, case-insensitive):
```
fd-safety keywords:
  password, secret, token, api_key, apikey, api-key, credential, private_key,
  encrypt, decrypt, hash, salt, bearer, oauth, jwt, session, cookie, csrf, cors,
  helmet, sanitize, escape, inject, trust, allow_origin, chmod, chown, sudo, root, admin
```

### How Slicing Works

1. **Threshold**: If diff >= 1000 lines AND slicing_eligible: yes
2. **Cross-cutting agents** (fd-architecture, fd-quality): Always get full diff
3. **Domain-specific agents**: 
   - Classify each file as **priority** or **context**
   - A file is priority if it matches ANY pattern OR any hunk contains ANY keyword
   - Send priority files in full + context files as one-liners
4. **80% threshold**: If an agent's priority files cover ≥80% of total lines, send full diff anyway (no slicing overhead)

---

## Phase 2: Launch

### Step 2.0: Output Directory Preparation

```bash
mkdir -p {OUTPUT_DIR}  # Must be absolute path
find {OUTPUT_DIR} -maxdepth 1 -type f \( -name "*.md" -o -name "*.md.partial" \) -delete
```

### Step 2.1: Knowledge Retrieval (Optional)

Before launching agents, retrieve prior knowledge entries from qmd:

```
Tool: mcp__plugin_clavain_qmd__vsearch
Parameters:
  collection: "Clavain"
  query: "{agent domain} {document summary keywords}"
  limit: 5
```

If qmd unavailable or errors: skip knowledge injection, agents run without it.

### Step 2.2: Stage 1 Launch

Launch top 2-3 agents from triage table as Task calls with `run_in_background: true`.

**Wait for Stage 1 to complete** using polling (Step 2.3).

### Step 2.2b: Expansion Decision

After Stage 1 completes, read the Findings Index from each output file:

| Stage 1 Result | Action |
|---|---|
| Any P0 issue found | Launch ALL Stage 2 agents — need convergence data |
| Multiple P1 issues or agents disagree | Launch ALL Stage 2 agents for coverage |
| Single P1 from one agent only | Launch 1-2 targeted Stage 2 agents in the flagged domain |
| Only P2/improvements or clean | **Early stop** — Stage 1 is sufficient |

### Step 2.2c: Stage 2 Launch

If expanding, launch Stage 2 agents with `run_in_background: true`.

### Step 2.1b: Diff Content Preparation

For diff inputs >= 1000 lines with slicing_eligible: yes:

1. **Read** `config/flux-drive/diff-routing.md`
2. **Classify files** as priority or context per agent
3. **Cross-cutting agents** (fd-architecture, fd-quality): Full diff
4. **Domain-specific agents**: Priority hunks (full) + context summaries (one-liners)
5. **80% threshold**: If agent's priority files cover ≥80% of changed lines, send full diff

### Step 2.3: Monitoring

Poll every 30 seconds for `.md` files in `{OUTPUT_DIR}`:
- Report each completion with elapsed time
- Report running count: `[N/M agents complete]`
- Timeout: 5 minutes (Task), 10 minutes (Codex)
- Report any agents still pending after timeout

**Completion verification**:
1. List `{OUTPUT_DIR}/` — expect one `.md` file per launched agent
2. For any agent with only `.md.partial` or no file:
   - Check background task output for errors
   - Retry once with `run_in_background: false, timeout: 300000`
   - If retry fails, create error stub with "Verdict: error"
3. Clean up remaining `.md.partial` files
4. Report: "N/M agents completed successfully, K retried, J failed"

---

## Phase 3: Synthesis

### Step 3.0: Verify Completion

```bash
ls {OUTPUT_DIR}/
```

Confirm N files (one per launched agent).

### Step 3.1: Validate Agent Output

For each agent file:
1. Check file starts with `### Findings Index`
2. Verify index lines match `- SEVERITY | ID | "Section" | Title` pattern
3. Check for `Verdict:` line
4. Classification:
   - **Valid**: Findings Index parsed → index-first collection
   - **Error**: File contains "verdict: error" → note as "agent failed", don't count toward convergence
   - **Malformed**: Missing/unrecognizable index → read Summary + Issues as prose fallback
   - **Missing**: File doesn't exist → "no findings"

Report: "5/6 agents returned valid Findings Index, 1 failed"

### Step 3.2: Collect Results

For each **valid** agent, read **Findings Index** first (first ~30 lines). Only read full prose if:
- An issue needs more context
- You need to resolve conflicts between agents

For **malformed** outputs, read Summary + Issues sections as prose fallback.

### Step 3.3: Deduplicate and Organize

1. **Group findings by section**
2. **Deduplicate**: Keep most specific findings (prefer Project Agents over Plugin Agents)
3. **Track convergence**: Note how many agents flagged each issue (e.g., "4/6 agents")
4. **Flag conflicts**: If agents disagree, note both positions
5. **Priority from project-specific agents**: When Project Agent and Plugin Agent disagree, prefer Project Agent
6. **Diff slicing awareness**: When counting convergence, only count agents that received the file as priority (full hunks)

### Step 3.4: Update the Document

#### For file inputs:
Write findings to `{OUTPUT_DIR}/summary.md` (not modifying INPUT_FILE by default).

Summary file contains:
- Flux Drive Enhancement Summary header
- Warning if divergence detected
- Key Findings (top 3-5 with convergence counts)
- Issues to Address (checklist with severity, agent attribution, convergence)
- Improvements Suggested (numbered with rationale)
- Individual Agent Reports (links to agent .md files)

Ask user: "Add inline annotations to the original document?"

If yes: Add blockquotes to INPUT_FILE:
```markdown
> **Flux Drive** ({agent-name}): [Concise finding or suggestion]
```

#### For repo reviews (directory input):
Write to `{OUTPUT_DIR}/summary.md` — do NOT modify existing files.

### Step 3.4a: Generate findings.json

```json
{
  "reviewed": "YYYY-MM-DD",
  "input": "{INPUT_PATH}",
  "agents_launched": ["agent1", "agent2"],
  "agents_completed": ["agent1", "agent2"],
  "findings": [
    {
      "id": "P0-1",
      "severity": "P0",
      "agent": "fd-architecture",
      "section": "Section Name",
      "title": "Short description",
      "convergence": 3
    }
  ],
  "improvements": [
    {
      "id": "IMP-1",
      "agent": "fd-quality",
      "section": "Section Name",
      "title": "Short description"
    }
  ],
  "verdict": "needs-changes",
  "early_stop": false
}
```

**Verdict logic**: P0 found → "risky". P1 found → "needs-changes". Otherwise → "safe".

### Step 3.5: Report to User

Present synthesis report:

```markdown
## Flux Drive Review — {INPUT_STEM}

**Reviewed**: {YYYY-MM-DD} | **Agents**: {N launched}, {M completed} | **Verdict**: {safe|needs-changes|risky}

### Critical Findings (P0)
[List with agent attribution and convergence]

### Important Findings (P1)
[List with convergence counts: "(3/5 agents)"]

### Improvements Suggested
[Top 3-5 improvements, prioritized]

### Section Heat Map
| Section | Issues | Improvements | Agents Reporting |

### Conflicts
[Disagreements between agents, or "No conflicts detected."]

### Files
- Summary: {OUTPUT_DIR}/summary.md
- Findings: {OUTPUT_DIR}/findings.json
- Individual reports: {OUTPUT_DIR}/{agent-name}.md

### Diff Slicing Report
[If INPUT_TYPE = diff AND slicing was active]

| Agent | Mode | Priority Files | Context Files | Lines Reviewed (full) |
```

---

## Phase 4: Cross-AI Comparison (Optional)

**Skip if Oracle was not in roster.**

If Oracle participated, read `phases/cross-ai.md` for comparison flow.

---

## Output Format Contract

### Findings Index (Machine-Parseable)

```
### Findings Index
- P0 | P0-1 | "Section Name" | Title of the issue
- P1 | P1-1 | "Section Name" | Title
- IMP | IMP-1 | "Section Name" | Title of improvement
Verdict: safe|needs-changes|risky
```

### Prose Sections (after index)

```
### Summary (3-5 lines)
[Top findings]

### Issues Found
[Numbered, with severity: P0/P1/P2. Must match Findings Index.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]
```

### Completion Signal

- Write to `{OUTPUT_DIR}/{agent-name}.md.partial` during work
- Add `<!-- flux-drive:complete -->` as last line
- Rename to `{OUTPUT_DIR}/{agent-name}.md` as final action
- Orchestrator detects completion by checking for `.md` files (not `.partial`)

### Error Stub

When agent fails after retry:
```
### Findings Index
Verdict: error

Agent failed to produce findings after retry. Error: {error message}
```

---

## Knowledge Injection System

### Location: `config/flux-drive/knowledge/`

After each flux-drive run, a compounding agent (silent background task) extracts durable patterns and saves them as knowledge entries.

**Knowledge entry format**:
```yaml
---
lastConfirmed: YYYY-MM-DD
provenance: independent|primed
---

[1-3 sentence description of the pattern]

Evidence: [file paths, symbol names, line ranges from the agent's finding]
Verify: [1-3 steps to confirm this finding is still valid]
```

**Provenance rules**:
- **independent**: New finding, or existing finding re-confirmed independently
- **primed**: Finding injected in agent context, then agent re-confirmed it (useful but weaker signal)

**Decay check**: If entry not independently confirmed in last 10 reviews (~60 days), move to `config/flux-drive/knowledge/archive/`.

---

## Integration Hooks

### SessionStart Hook

When flux-drive skill loads, the SessionStart hook injects `using-clavain` skill content via `additionalContext` JSON. This provides quick reference routing tables and agent descriptions.

### clodex Mode (Optional)

When clodex mode is detected, flux-drive dispatches agents through Codex CLI instead of Claude Task tool. See `phases/launch-codex.md` for details.

### qmd MCP Tool

Optional semantic search for project documentation (used in Step 1.0). If unavailable, flux-drive continues without knowledge injection.

---

## Summary: Domain Classification Integration Checklist

### What Exists Now
- ✅ Document/diff analysis (Step 1.1)
- ✅ Pre-filtering by hardcoded rules (Step 1.2a)
- ✅ Agent scoring on document content (Step 1.2b)
- ✅ Domain profiles in YAML + markdown (config/flux-drive/domains/)
- ✅ Diff-routing system for large diffs

### What Needs to Be Added
1. **Step 1.0a: Domain Detection**
   - Read `config/flux-drive/domains/index.yaml`
   - Score project against each domain's signals
   - Build detected_domains list

2. **Step 1.2a Update: Pre-filter Using Detected Domains**
   - If domain detected, add optional domain-specific agents to candidate pool

3. **Step 1.2b Update: Score Using Detected Domains**
   - If domain detected, apply injection bonus (+1) to matching agents

4. **Step 2.2 Update: Prompt Modification**
   - If domain profiles detected, append domain-specific injection bullets to agent prompts

5. **Test Coverage**
   - Verify domain detection scoring
   - Verify injection bonus application
   - Verify agent roster expansion
   - Verify injection bullet formatting in agent prompts

---

## Appendix: File Reference

### Core Flux-Drive Files
- `/root/projects/Clavain/skills/flux-drive/SKILL.md` — Main skill file (374 lines)
- `/root/projects/Clavain/skills/flux-drive/phases/launch.md` — Phase 2 dispatch (339 lines)
- `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md` — Phase 3 synthesis (304 lines)
- `/root/projects/Clavain/skills/flux-drive/phases/shared-contracts.md` — Output contracts (98 lines)
- `/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` — Phase 4 (optional)
- `/root/projects/Clavain/skills/flux-drive/phases/launch-codex.md` — Codex dispatch (alternative)

### Configuration Files
- `/root/projects/Clavain/config/flux-drive/diff-routing.md` — Diff slicing patterns (134 lines)
- `/root/projects/Clavain/config/flux-drive/domains/index.yaml` — Domain index (454 lines, 11 domains)
- `/root/projects/Clavain/config/flux-drive/domains/game-simulation.md` — Example domain profile (104 lines)

### Knowledge Directory
- `/root/projects/Clavain/config/flux-drive/knowledge/` — Extracted patterns from past reviews (initially empty)

---

**End of Analysis**

Generated: 2026-02-12
Scope: Comprehensive exploration of flux-drive triage system, domain classification integration points, and data structures.
