# Flux-Drive Multi-Agent Review System: Pattern Analysis

**Research Date:** 2026-02-09
**Project:** Clavain Plugin
**Focus:** Agent output formats, dispatch mechanisms, synthesis contract, and gaps between producer/consumer expectations

---

## Executive Summary

The flux-drive skill implements a sophisticated multi-agent review system with 18 agents across 4 tiers. There is a **fundamental gap** between what agents are instructed to produce (YAML frontmatter) and what many agents actually produce (prose-only with section-based output). The synthesis phase includes validation and fallback logic to handle malformed outputs, but this creates a two-tier quality system where some agents provide machine-parseable metadata and others require prose parsing.

**Key Finding:** Only 2/18 agents explicitly reference YAML frontmatter in their system prompts. The remaining 16 agents use domain-specific prose formats that must be retrofitted with frontmatter at runtime via the launch prompt template.

---

## 1. Agent Output Formats: Catalog of 18 Agents

### 1.1 Output Format Specification by Agent

All agents are expected to produce YAML frontmatter per the launch prompt template (`phases/launch.md` lines 110-129), but their **intrinsic system prompts** specify various prose formats:

#### **Tier 1: Codebase-Aware Agents (2)**

| Agent | Documented Output Format | Frontmatter? | Structure |
|-------|--------------------------|--------------|-----------|
| **fd-user-experience** | Section-based prose | ❌ | `### UX Assessment` → `### Specific Issues (numbered)` → `### Summary` |
| **fd-code-quality** | Section-based prose | ❌ | `### Conventions Check` → `### Specific Issues (numbered)` → `### Summary` |

Both Tier 1 agents specify **numbered issues with severity in prose**, but do not mention YAML frontmatter in their system prompts.

#### **Tier 2: Project-Specific Agents (Variable)**

Tier 2 agents are dynamically generated from `.claude/agents/fd-*.md` files. Their output format is **inherited from the project's agent templates**, which may or may not include frontmatter requirements.

#### **Tier 3: Adaptive Specialists (13)**

| Agent | Documented Output Format | Frontmatter? | Structure |
|-------|--------------------------|--------------|-----------|
| **architecture-strategist** | Section-based prose | ❌ | `### Architecture Assessment` → `### Specific Issues (numbered)` → `### Summary` |
| **security-sentinel** | Section-based prose | ❌ | `### Threat Model Context` → `### Specific Issues (numbered, by severity)` → `### Summary` |
| **performance-oracle** | Section-based prose | ❌ | `### Performance Profile` → `### Specific Issues (numbered, by impact)` → `### Summary` |
| **code-simplicity-reviewer** | Markdown template | ✅ | Explicit markdown template with `## Simplification Analysis` → sections → `### Final Assessment` |
| **pattern-recognition-specialist** | Structured report | ❌ | Pattern report with specific sections (no explicit format documented) |
| **data-integrity-reviewer** | Prose analysis | ❌ | Analysis approach described, no output template |
| **concurrency-reviewer** | Prose analysis | ❌ | Review principles described, no output template |
| **deployment-verification-agent** | Go/No-Go checklist | ✅ | Explicit markdown template with checklists and tables |
| **go-reviewer** | Review analysis | ❌ | Review principles described, no output template |
| **python-reviewer** | Review analysis | ❌ | Review principles described, no output template |
| **typescript-reviewer** | Review analysis | ❌ | Review principles described, no output template |
| **shell-reviewer** | Review analysis | ❌ | Review principles described, no output template |
| **rust-reviewer** | Review analysis | ❌ | Review principles described, no output template |

**Pattern:** Language reviewers (5 agents) and concurrency/data-integrity reviewers (2 agents) have **no documented output template** in their system prompts. They describe review principles and approach but leave output structure implicit.

**Exception:** `code-simplicity-reviewer` and `deployment-verification-agent` include explicit markdown templates in their system prompts.

#### **Tier 4: Cross-AI (1)**

| Agent | Invocation | Output | Frontmatter? |
|-------|-----------|--------|--------------|
| **oracle-council** | CLI via Bash | Plain markdown written to file | ❌ |

Oracle is invoked via `oracle --wait -p "<prompt>" -f "<files>"` and outputs plain markdown with no frontmatter. Error handling is explicit: timeouts/failures are treated as "Oracle: no findings."

### 1.2 Common Output Patterns

**Across all agents, common prose sections:**
- Summary/Assessment (3-5 lines)
- Section-by-Section or Issue-by-Issue breakdown
- Numbered findings with severity (P0/P1/P2 or Critical/High/Medium/Low)
- Recommendations or improvements
- Overall verdict or assessment

**Severity taxonomies:**
- Tier 1 and most Tier 3: P0/P1/P2
- Security: Critical/High/Medium/Low
- Performance: High/Medium/Low impact
- Code simplicity: Complexity score

**The gap:** Agents produce rich prose, but the synthesis phase needs structured metadata to deduplicate, organize by section, and track convergence. The launch prompt template retrofits frontmatter requirements onto agents that don't natively expect it.

---

## 2. Flux-Drive Skill Architecture

### 2.1 Input Detection and Path Resolution

**Location:** `skills/flux-drive/SKILL.md` lines 12-34

```
INPUT_PATH = <user-provided path>
INPUT_FILE = INPUT_PATH (if file) or none (if directory)
INPUT_DIR = directory containing INPUT_FILE or INPUT_PATH
INPUT_STEM = filename without extension or directory basename
PROJECT_ROOT = nearest ancestor directory containing .git
OUTPUT_DIR = {PROJECT_ROOT}/docs/research/flux-drive/{INPUT_STEM}
```

**Critical requirement:** `OUTPUT_DIR` must be resolved to an **absolute path** before use in agent prompts. Agents inherit the main session's CWD, so relative paths break during cross-project reviews.

### 2.2 Phase Structure

Flux-drive uses **progressive loading** across 4 phases:

1. **Analyze + Static Triage** (`SKILL.md` lines 36-158)
   - Step 1.0: Understand the project (read build files, check for divergence)
   - Step 1.1: Analyze the document (extract structured profile)
   - Step 1.2: Select agents from roster (scoring table with tier bonuses)
   - Step 1.3: User confirmation (AskUserQuestion approval gate)

2. **Launch** (`phases/launch.md` or `phases/launch-codex.md`)
   - Detects dispatch mode (Task tool vs Codex CLI)
   - Creates output directory
   - Launches agents in parallel with background execution
   - Token optimization: trims 200+ line documents to ~50% by keeping focus sections in full and summarizing others

3. **Synthesize** (`phases/synthesize.md`)
   - Step 3.0: Wait for all agents (polls output directory)
   - Step 3.1: Validate agent output (frontmatter validation with prose fallback)
   - Step 3.2: Collect results (frontmatter-first parsing)
   - Step 3.3: Deduplicate and organize (group by section, track convergence)
   - Step 3.4: Update the document (amend file or create summary)
   - Step 3.5: Report to user

4. **Cross-AI Escalation** (`phases/cross-ai.md`, optional)
   - Only runs if Oracle participated
   - Compares Oracle findings vs Claude findings
   - Auto-chains to interpeer mine mode on disagreements
   - Offers interpeer council mode for critical decisions

### 2.3 Tier System

**Tier 1 — Codebase-Aware (2 agents)**
- `fd-user-experience`, `fd-code-quality`
- Read `CLAUDE.md` and `AGENTS.md` before analyzing
- +1 scoring bonus in triage
- Dispatched via `subagent_type: clavain:review:<name>`

**Tier 2 — Project-Specific (.claude/agents/fd-*.md, variable count)**
- Check if `.claude/agents/fd-*.md` exist in project root
- Bootstrap via Codex if missing (clodex mode only)
- Use `subagent_type: general-purpose` with full agent file as system prompt
- +1 scoring bonus in triage
- Deduplication rule: If Tier 1/2 covers same domain as Tier 3, drop Tier 3

**Tier 3 — Adaptive Specialists (13 agents)**
- Auto-detect CLAUDE.md/AGENTS.md for codebase-aware mode
- Fall back to generic best practices if no project docs
- architecture-strategist, security-sentinel, performance-oracle get +1 bonus when project docs exist
- Dispatched via `subagent_type: clavain:review:<name>`

**Tier 4 — Cross-AI (1 agent)**
- Oracle (GPT-5.2 Pro via browser automation)
- +1 diversity bonus (different model family)
- Invoked via Bash CLI, not Task tool
- Error handling: timeouts/failures → continue without cross-AI perspective
- Requires `DISPLAY=:99` and `CHROME_PATH=/usr/local/bin/google-chrome-wrapper`

**Cap:** Maximum 8 agents total. Oracle can replace lowest-scoring Tier 3 agent if roster is full.

---

## 3. Output Contract: What Flux-Drive Expects

### 3.1 YAML Frontmatter Specification

**Location:** `phases/launch.md` lines 110-129

**Required keys:**
```yaml
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
```

**Prose structure after frontmatter:**
```markdown
### Summary (3-5 lines)
[Top findings]

### Section-by-Section Review
[Only sections in agent's domain]

### Issues Found
[Numbered, with severity. Must match frontmatter.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]
```

### 3.2 Validation and Fallback Logic

**Location:** `phases/synthesize.md` lines 14-25

Three classifications during validation:

1. **Valid:** Frontmatter parsed successfully → proceed with frontmatter-first collection
2. **Malformed:** File exists but frontmatter missing/incomplete → fall back to prose-based reading (read Summary + Issues sections directly)
3. **Missing:** File doesn't exist or is empty → "no findings"

**Fallback strategy:** For malformed outputs, synthesis reads the Summary + Issues sections as prose and extracts findings manually. This creates a two-tier quality system where valid outputs are processed efficiently via structured metadata, while malformed outputs require slower prose parsing.

**Actual behavior in production:** Based on example files reviewed, Tier 1 agents (fd-architecture, fd-code-quality) **do produce valid frontmatter**, suggesting the launch prompt template successfully overrides their native prose-only format.

---

## 4. Synthesis Phase: How Agent Output is Consumed

### 4.1 Collection Strategy

**Location:** `phases/synthesize.md` lines 27-33

**Frontmatter-first parsing:**
- For valid outputs, read **only the YAML frontmatter** first (first ~60 lines)
- Provides structured list of all issues and improvements without reading full prose
- Only read prose body if:
  - An issue needs more context to understand
  - Need to resolve a conflict between agents

**Prose fallback:**
- For malformed outputs, read Summary + Issues sections as prose
- Manual extraction of findings without structured metadata

**Key optimization:** Frontmatter allows synthesis to process 6-8 agent outputs without reading thousands of lines of prose. This is critical for staying within token budgets during synthesis.

### 4.2 Deduplication and Organization

**Location:** `phases/synthesize.md` lines 35-42

**Process:**
1. **Group by section:** Organize all findings under the section they apply to (or by topic for repo reviews)
2. **Deduplicate:** If multiple agents flag same issue, keep most specific one (prefer Tier 1/2 over Tier 3)
3. **Track convergence:** Count how many agents flagged each issue (e.g., "4/6 agents")
   - High convergence (3+ agents) = high confidence
   - Include convergence counts in Issues to Address checklist
4. **Flag conflicts:** If agents disagree, note both positions
5. **Priority from codebase-aware agents:** When Tier 1/2 and Tier 3 disagree, prefer codebase-aware recommendation

**Convergence tracking is critical:** It transforms individual agent findings into confidence-weighted recommendations. Example from synthesis:
- "Hook count mismatch" (1 agent) vs "Missing type hints" (4 agents) — convergence signals importance

### 4.3 Write-Back Strategy

**Location:** `phases/synthesize.md` lines 44-110

**Two modes based on input type:**

**File inputs (plans, brainstorms, specs):**
- **Amend** (default): Add findings to existing document
- **Flag for archival:** When document is fundamentally obsolete (wrong tech stack), add warning and recommend rewrite
- Add enhancement summary at top with key findings and Issues to Address checklist
- Add inline notes in each section: `> **Flux Drive** ({agent-name}): [finding]`
- **Deepen thin sections:** For plans/brainstorms, launch Task Explore agents to research and enrich sections marked `thin` in Step 1.1

**Directory inputs (repo reviews):**
- Do NOT modify repo's existing files
- Write new summary to `{OUTPUT_DIR}/summary.md`
- Link to individual agent reports

---

## 5. The Gap: Producer vs Consumer Contract

### 5.1 The Fundamental Mismatch

**What agents are told (system prompts):**
- Most agents: "Produce numbered findings with sections and summary"
- Format: Prose-based with implicit structure
- Severity: P0/P1/P2 or domain-specific scales

**What synthesis needs (launch prompt template):**
- YAML frontmatter with structured metadata
- Explicit keys: `agent`, `tier`, `issues`, `improvements`, `verdict`
- Machine-parseable for deduplication, grouping, convergence tracking

**How the gap is bridged:**
- Launch prompt template (`phases/launch.md` lines 110-129) **overrides** agent system prompts
- Explicitly instructs: "The file MUST start with a YAML frontmatter block"
- Provides template with required keys

**Success rate:**
- Example outputs show Tier 1 agents **do produce valid frontmatter** despite system prompts not mentioning it
- Suggests agents obey the task prompt (launch template) over their system prompt (agent .md file)
- Unknown: success rate across all tiers and agents under different conditions

### 5.2 Validation and Error Handling

**Validation logic:**
```
1. Check file starts with `---` (YAML delimiter)
2. Verify required keys exist: agent, tier, issues, verdict
3. Classify: Valid, Malformed, Missing
```

**Error handling patterns found:**

1. **Oracle failures** (`SKILL.md` line 221):
   - Timeout/failure → note in output file, continue without Phase 4
   - Do NOT block synthesis on Oracle failures
   - Treat as "Oracle: no findings" and skip Steps 4.2-4.5

2. **Codex dispatch failures** (`phases/launch-codex.md` lines 99-105):
   - Retry once with same prompt file
   - If retry fails → fall back to Task dispatch for that agent
   - Note in synthesis: "Agent X: Codex dispatch failed, used Task fallback"

3. **Malformed frontmatter** (`phases/synthesize.md` lines 22-25):
   - Fall back to prose-based reading
   - Read Summary + Issues sections directly
   - Report: "5/6 agents returned valid frontmatter, 1 fallback to prose"

4. **Missing agent output** (`phases/synthesize.md` lines 7-12):
   - Poll output directory every 30 seconds
   - After 5 minutes: proceed with what you have
   - Note missing agents as "no findings"

**Pattern:** Error handling is **graceful degradation** — system continues with reduced functionality rather than failing. This is appropriate for a review system where partial results are valuable.

### 5.3 Retry Patterns

**Currently implemented:**
- Codex dispatch: 1 retry, then fallback to Task dispatch
- Oracle: No retry (timeout is generous at 300s, 600s in some invocations)
- Agent completion: No retry (poll for 5 minutes, then proceed)

**Not implemented:**
- No retry for malformed frontmatter (immediate fallback to prose)
- No retry for agents that produce empty files
- No validation of frontmatter schema beyond key existence

---

## 6. Dispatch Mechanisms: Task vs Codex

### 6.1 Task Dispatch (Default)

**Location:** `phases/launch.md` lines 2-155

**Mechanism:**
- All agents launched as parallel Task calls in a single message
- **Critical:** Every agent MUST use `run_in_background: true`
- Prevents agent output from flooding main conversation context

**Agent types:**
- **Tier 1:** `subagent_type: clavain:review:fd-user-experience` (native)
- **Tier 2:** `subagent_type: general-purpose` + full agent file content as system prompt
- **Tier 3:** `subagent_type: clavain:review:architecture-strategist` (native)
- **Tier 4:** Bash CLI (not Task tool)

**Completion detection:**
- Poll output directory for existence of `{OUTPUT_DIR}/{agent-name}.md`

### 6.2 Codex Dispatch (Clodex Mode)

**Location:** `phases/launch-codex.md`

**Activation:**
```bash
if [[ -f "${CLAUDE_PROJECT_DIR:-.}/.claude/autopilot.flag" ]]; then
  CLODEX_MODE=true
fi
```

**Key differences:**
- Agents dispatched through Codex CLI instead of Task tool
- Uses `scripts/dispatch.sh` with task description files
- **Tier 2 bootstrap:** Auto-generates `.claude/agents/fd-*.md` if missing/stale
- Hash tracking: `sha256sum CLAUDE.md AGENTS.md` → `.claude/agents/.fd-agents-hash`

**Task description file format:**
```
PROJECT:
{project name}

AGENT_IDENTITY:
{paste full system prompt}

REVIEW_PROMPT:
{same template from phases/launch.md}

AGENT_NAME:
{agent-name}

TIER:
{1|2|3}

OUTPUT_FILE:
{OUTPUT_DIR}/{agent-name}.md
```

**Section headers must be:**
- On own line with colon at end: `PROJECT:`
- Content on subsequent lines
- Matches dispatch.sh's `^[A-Z_]+:$` parser

**Error handling:**
- Retry once
- Fall back to Task dispatch if both fail
- Note failure in synthesis summary

### 6.3 Dispatch Mode Comparison

| Aspect | Task Dispatch | Codex Dispatch |
|--------|---------------|----------------|
| **Activation** | Default | `.claude/autopilot.flag` exists |
| **Tier 1** | Native subagent_type | Dispatch via CLI |
| **Tier 2** | Manual agent files | Auto-bootstrap if missing |
| **Tier 3** | Native subagent_type | Dispatch via CLI |
| **Tier 4** | Bash CLI | Bash CLI (unchanged) |
| **Completion** | Poll output files | Poll output files |
| **Error handling** | None (wait 5 min) | Retry once, fallback to Task |
| **Prompt delivery** | Via Task prompt | Via temp file + dispatch.sh |

---

## 7. Launch Prompt Template Analysis

### 7.1 Structure and Components

**Location:** `phases/launch.md` lines 53-149

**Template sections:**

1. **Context block:**
   ```
   You are reviewing a {document_type} for {review_goal}.

   ## Project Context
   Project root: {PROJECT_ROOT}
   Document: {INPUT_FILE}

   [CRITICAL CONTEXT: divergence warning if detected]
   ```

2. **Document content (optimized):**
   - For 200+ line files: trim to ~50%
   - Keep FULL content for sections in "Focus on"
   - Keep Summary, Goals, Non-Goals in full
   - Replace other sections with: `## [Section Name] — [1-sentence summary]`
   - For repo reviews: README + build files + 2-3 key source files only

3. **Focus area:**
   ```
   ## Your Focus Area
   You were selected because: [reason from triage]
   Focus on: [specific sections relevant to domain]
   Depth needed: [thin/adequate/deep]
   ```

4. **Output requirements:**
   - Absolute path specification
   - YAML frontmatter template (overrides agent system prompt)
   - Prose structure after frontmatter
   - "Be concrete. Reference specific sections by name."

### 7.2 Token Optimization Strategy

**Problem:** Sending full 500-line documents to 8 agents = massive token consumption

**Solution:** Intelligent trimming based on agent's focus area

**Rules:**
- Documents under 200 lines: send in full
- Documents 200+ lines: trim to ~50%
- Keep agent's focus sections in full
- Summarize all other sections to single line
- Always keep Summary, Goals, Non-Goals in full

**Example:**
- Architecture agent reviewing 400-line plan
- Keep FULL: "Architecture" section (80 lines), "Summary" (10 lines)
- SUMMARY: "Commands table" → "## Commands (24) — skill routing table"
- Result: ~200 lines instead of 400

**Impact:** Reduces synthesis token load by ~50% while maintaining review quality in agent's domain

### 7.3 Divergence Handling

**Problem:** Document describes Swift but codebase is Rust+TS — agents get confused

**Detection:** Step 1.0 compares document tech stack to actual build files

**Solution:** Inject divergence context into every agent prompt:
```
CRITICAL CONTEXT: The document describes [document's tech stack] but
the actual codebase uses [actual tech stack]. Key actual files:
- [file1] — [description]
- [file2] — [description]

Review the ACTUAL CODEBASE, not what the document describes.
Note divergence as a finding.
```

**Why critical:** Without this, agents waste cycles being confused by phantom code, or produce reviews of fictional implementations

**Archival flag:** When divergence is severe, synthesis adds warning to document: "Consider archiving this document and writing a new one"

---

## 8. Patterns That Could Inform Unified Solutions

### 8.1 The Frontmatter Override Pattern

**Current pattern:**
- Agent system prompts specify prose formats
- Launch prompt template overrides with frontmatter requirement
- Agents obey task prompt over system prompt (usually)

**Why it works:**
- Task prompt is more recent/specific than system prompt
- Explicit template with "MUST start with" language
- Validation fallback if agents ignore it

**Unified solution opportunity:**
- Standardize all agent system prompts to include frontmatter template
- Make it part of agent identity, not launch-time override
- Reduces prompt complexity and token usage
- Makes agent outputs consistent across all use cases (not just flux-drive)

**Implementation:**
```markdown
## Output Format

Write findings to the specified output file path.

**File must start with YAML frontmatter:**
```yaml
---
agent: {agent-name}
tier: {provided-tier}
issues:
  - id: P0-1
    severity: P0
    section: "Section Name"
    title: "Short description"
verdict: safe|needs-changes|risky
---
```

**After frontmatter, structure prose as:**
[agent-specific prose format]
```

### 8.2 The Validation-Fallback Pattern

**Current pattern:**
1. Optimistic: Try to parse frontmatter
2. Classify: Valid, Malformed, Missing
3. Degrade: Fall back to prose parsing for malformed
4. Report: "5/6 valid, 1 fallback"

**Why it works:**
- Graceful degradation preserves value of partial results
- User visibility into quality (validation report)
- Two-tier processing: fast for valid, slow for malformed

**Unified solution opportunity:**
- Apply to all multi-agent workflows (not just flux-drive)
- Standard validation library for agent outputs
- Typed output schemas for different agent roles

### 8.3 The Convergence Tracking Pattern

**Current pattern:**
- Track which agents flagged each issue
- Count convergence: "4/6 agents"
- High convergence (3+) = high confidence
- Prefer codebase-aware agents when conflict

**Why it works:**
- Transforms individual findings into weighted recommendations
- Reduces noise from outlier agents
- Prioritizes issues multiple perspectives agree on

**Unified solution opportunity:**
- Standard convergence metric across all review types
- Visualization: issue heatmap by agent + section
- Confidence scoring formula: `confidence = (convergence_count / total_agents) * tier_weight`

### 8.4 The Tier Deduplication Pattern

**Current pattern:**
- If Tier 1/2 agent covers same domain as Tier 3, drop Tier 3
- Prefer codebase-aware recommendations when conflict
- Explicit scoring bonuses for tiers with more context

**Why it works:**
- Prevents redundant reviews on same domain
- Prioritizes agents with more project-specific knowledge
- Keeps agent count under cap (8 agents)

**Unified solution opportunity:**
- Generalize to all multi-agent systems
- Domain coverage matrix: which agents cover which domains
- Auto-deduplication based on tier + domain overlap

### 8.5 The Background Execution Pattern

**Current pattern:**
- All agents launched in parallel with `run_in_background: true`
- Prevents output flooding main conversation
- Poll completion via output file existence
- Continue after timeout (5 minutes)

**Why it works:**
- Parallel execution reduces wall-clock time (3-5 minutes for 6-8 agents)
- Token efficiency: agent outputs isolated to files
- Resilient to agent failures (missing output = no findings)

**Unified solution opportunity:**
- Standard pattern for all multi-agent workflows
- Task orchestration library with timeout, retry, fallback
- Progress reporting: "3/6 complete, 2 in progress, 1 timed out"

### 8.6 The Token Optimization Pattern

**Current pattern:**
- Detect large documents (200+ lines)
- Trim to ~50% based on agent's focus area
- Keep focus sections in full, summarize others
- Target: agent receives relevant content without noise

**Why it works:**
- Reduces synthesis token load by ~50%
- Maintains review quality in agent's domain
- Prevents agents from being overwhelmed by irrelevant content

**Unified solution opportunity:**
- Dynamic context windowing for all agent tasks
- Relevance scoring: which sections matter for this agent?
- Adaptive trimming based on token budget

### 8.7 The Error Handling Hierarchy

**Current pattern:**
1. Oracle timeout → continue without cross-AI
2. Codex dispatch fail → retry once → fallback to Task
3. Malformed frontmatter → fallback to prose
4. Missing output → "no findings"

**Why it works:**
- Failures at each level have specific remediation
- System continues with degraded functionality
- User informed of degradation mode

**Unified solution opportunity:**
- Standard error handling DSL for multi-agent workflows
- Retry policies per agent tier
- Fallback chains: primary → retry → alternative → graceful degradation

---

## 9. Recommendations for Unified Solution

### 9.1 Agent Output Schema

**Problem:** 16/18 agents don't mention frontmatter in system prompts, creating dependency on launch template override

**Solution:** Standardize agent output schema across all review agents

**Proposal:**

1. **Update all agent system prompts** (`agents/review/*.md`) to include:
   ```markdown
   ## Output Format

   Write findings to the specified output file path.

   **REQUIRED: File must start with YAML frontmatter:**
   ```yaml
   ---
   agent: {agent-name}
   tier: {provided-at-runtime}
   issues:
     - id: {severity}-{number}
       severity: P0|P1|P2
       section: "Section Name"
       title: "One-line description"
   improvements:
     - id: IMP-{number}
       title: "One-line description"
       section: "Section Name"
   verdict: safe|needs-changes|risky
   ---
   ```

   **After frontmatter, structure prose as:**
   [agent-specific sections remain unchanged]
   ```

2. **Benefits:**
   - Agents produce consistent output regardless of dispatch mechanism
   - Launch template can be simplified (no need to override)
   - Easier to test agents in isolation
   - Reduces token usage in prompts

3. **Migration path:**
   - Update one agent (e.g., `go-reviewer`) as proof of concept
   - Test with flux-drive to verify frontmatter + prose coexistence
   - Roll out to remaining 17 agents
   - Simplify launch template to remove frontmatter override

### 9.2 Validation Library

**Problem:** Validation logic is embedded in synthesis phase, not reusable

**Solution:** Extract validation into shared library

**Proposal:**

Create `skills/flux-drive/lib/validate-output.sh` (or `.ts` if using TypeScript):

```typescript
interface AgentOutput {
  agent: string;
  tier: 1 | 2 | 3 | 4;
  issues: Issue[];
  improvements: Improvement[];
  verdict: 'safe' | 'needs-changes' | 'risky';
}

interface Issue {
  id: string;        // e.g., "P0-1"
  severity: 'P0' | 'P1' | 'P2';
  section: string;
  title: string;
}

interface Improvement {
  id: string;        // e.g., "IMP-1"
  title: string;
  section: string;
}

type ValidationResult =
  | { status: 'valid'; output: AgentOutput }
  | { status: 'malformed'; reason: string; proseContent: string }
  | { status: 'missing'; filePath: string };

function validateAgentOutput(filePath: string): ValidationResult {
  // 1. Check file exists
  // 2. Parse YAML frontmatter
  // 3. Validate required keys
  // 4. Return typed result
}
```

**Benefits:**
- Reusable across flux-drive and other multi-agent workflows
- Type-safe validation
- Easier to test
- Consistent error messages

### 9.3 Convergence Tracker

**Problem:** Convergence tracking is manual in synthesis phase

**Solution:** Extract into structured tracker

**Proposal:**

```typescript
interface Finding {
  id: string;
  severity: string;
  section: string;
  title: string;
  agents: string[];  // Which agents flagged this
  tier_levels: number[];  // Tier of each agent
}

class ConvergenceTracker {
  private findings: Map<string, Finding> = new Map();

  addFinding(agent: string, tier: number, issue: Issue) {
    const key = this.deduplicationKey(issue);
    if (this.findings.has(key)) {
      // Add agent to existing finding
      const finding = this.findings.get(key)!;
      finding.agents.push(agent);
      finding.tier_levels.push(tier);
    } else {
      // New finding
      this.findings.set(key, {
        ...issue,
        agents: [agent],
        tier_levels: [tier],
      });
    }
  }

  getConfidence(finding: Finding): number {
    const convergence = finding.agents.length / this.totalAgents;
    const tierWeight = Math.max(...finding.tier_levels) / 3;
    return convergence * 0.7 + tierWeight * 0.3;
  }

  private deduplicationKey(issue: Issue): string {
    // Normalize section + title for deduplication
    return `${issue.section}:${issue.title.toLowerCase().slice(0, 50)}`;
  }
}
```

**Benefits:**
- Automatic convergence tracking
- Confidence scoring formula
- Deduplication by normalized key
- Tier-weighted prioritization

### 9.4 Error Handling DSL

**Problem:** Error handling is scattered across multiple phase files

**Solution:** Centralize error handling configuration

**Proposal:**

Create `skills/flux-drive/lib/error-policies.yaml`:

```yaml
policies:
  oracle_timeout:
    max_duration: 300s
    retry: false
    fallback: continue_without_oracle
    message: "Oracle timed out — continuing without cross-AI perspective"

  codex_dispatch_failure:
    retry: true
    retry_count: 1
    fallback: task_dispatch
    message: "Codex dispatch failed, falling back to Task dispatch"

  malformed_frontmatter:
    retry: false
    fallback: prose_parsing
    message: "Agent {agent} returned malformed frontmatter, parsing prose"

  missing_output:
    max_wait: 300s
    poll_interval: 30s
    fallback: no_findings
    message: "Agent {agent} did not produce output within 5 minutes"
```

**Benefits:**
- Declarative error handling
- Easy to adjust timeouts/retries
- Consistent messaging
- Testable in isolation

### 9.5 Prompt Component Library

**Problem:** Launch template is monolithic and hard to maintain

**Solution:** Decompose into reusable components

**Proposal:**

Create `skills/flux-drive/prompts/` directory:

```
prompts/
├── context.md          # Project context block
├── divergence.md       # Divergence warning template
├── focus-area.md       # Agent focus area template
├── output-format.md    # Frontmatter + prose structure
└── optimization.md     # Token optimization instructions
```

Each component is a Jinja/Handlebars template with variables.

**Assembly:**
```typescript
const launchPrompt = assemblePrompt({
  context: renderTemplate('context.md', { PROJECT_ROOT, INPUT_FILE }),
  divergence: hasDivergence ? renderTemplate('divergence.md', { ... }) : '',
  document: optimizeDocument(document, agent.focusSections),
  focusArea: renderTemplate('focus-area.md', { agent, reason, sections }),
  outputFormat: renderTemplate('output-format.md', { agent }),
});
```

**Benefits:**
- Easier to maintain individual components
- Reusable across different agent types
- Version control shows changes to specific parts
- Testable in isolation

---

## 10. Gaps and Open Questions

### 10.1 Frontmatter Compliance Rate

**Gap:** Unknown actual success rate of agents producing valid frontmatter

**Evidence:**
- Example outputs show Tier 1 agents produce valid frontmatter
- But: only 2 examples reviewed out of 18 possible agents
- Unknown: compliance rate across all tiers under different conditions

**Questions:**
1. What percentage of agent outputs have valid frontmatter in production?
2. Which agents consistently produce malformed output?
3. Does compliance rate vary by tier or agent type?

**Recommendation:** Add telemetry to track validation results per agent

### 10.2 Prose Fallback Quality

**Gap:** No analysis of whether prose fallback produces equivalent results to frontmatter parsing

**Questions:**
1. Does prose fallback miss issues that frontmatter would capture?
2. Is deduplication as accurate without structured metadata?
3. What's the token cost difference between frontmatter-first and prose parsing?

**Recommendation:** A/B test synthesis with forced prose fallback vs valid frontmatter

### 10.3 Token Budget Analysis

**Gap:** No data on actual token consumption per phase

**Questions:**
1. What's the token distribution: triage, launch, agent execution, synthesis?
2. Does token optimization achieve the claimed ~50% reduction?
3. What's the token cost per agent type (Tier 1 vs 3 vs 4)?

**Recommendation:** Instrument flux-drive with token tracking per phase

### 10.4 Agent Selection Quality

**Gap:** No feedback loop on whether triage correctly selects relevant agents

**Questions:**
1. What percentage of launched agents produce no findings?
2. Are "skip" agents ever retroactively needed?
3. Does the 8-agent cap discard useful perspectives?

**Recommendation:** Track finding density (findings per agent) to tune triage scoring

### 10.5 Convergence Correlation

**Gap:** No validation that convergence actually correlates with issue importance

**Questions:**
1. Do high-convergence issues actually matter more?
2. Are unique findings (1 agent) false positives or blind spots?
3. Does tier weight correlate with finding accuracy?

**Recommendation:** User study: which findings do engineers actually fix?

---

## 11. Implementation Roadmap for Unified Solution

### Phase 1: Standardize Agent Outputs (2 weeks)

**Goal:** All agents produce consistent frontmatter

**Tasks:**
1. Update 16 agent system prompts with frontmatter template
2. Test each agent in isolation (unit test with mock input)
3. Test with flux-drive (integration test)
4. Verify validation success rate improves

**Success metric:** 95%+ agents produce valid frontmatter

### Phase 2: Extract Validation Library (1 week)

**Goal:** Reusable validation across workflows

**Tasks:**
1. Create `lib/validate-output.ts` with typed validation
2. Extract from synthesis phase
3. Add unit tests for valid/malformed/missing cases
4. Update synthesis to use library

**Success metric:** Synthesis phase code reduced by 30%, validation testable in isolation

### Phase 3: Build Convergence Tracker (1 week)

**Goal:** Automatic convergence and confidence scoring

**Tasks:**
1. Create `lib/convergence-tracker.ts` with Finding interface
2. Implement deduplication by normalized key
3. Implement confidence scoring formula
4. Update synthesis to use tracker

**Success metric:** Synthesis produces confidence scores for all findings

### Phase 4: Centralize Error Handling (1 week)

**Goal:** Declarative error policies

**Tasks:**
1. Create `lib/error-policies.yaml` with retry/fallback config
2. Implement policy interpreter
3. Update launch and synthesis phases to use policies
4. Add telemetry for policy activation

**Success metric:** All error handling in one file, measurable failure rates

### Phase 5: Componentize Prompts (1 week)

**Goal:** Maintainable prompt templates

**Tasks:**
1. Extract launch template into `prompts/` components
2. Implement template assembly logic
3. Update launch phase to use components
4. Add tests for each component

**Success metric:** Launch template assembly is declarative, components testable in isolation

### Total: 6 weeks to unified solution

---

## 12. Conclusion

The flux-drive multi-agent review system is sophisticated and functional, but has a **fundamental gap** between what agents are designed to produce (prose) and what synthesis needs (structured metadata). This gap is currently bridged by the launch prompt template overriding agent system prompts, which works but creates fragility.

**Key insights:**

1. **Frontmatter override pattern works but is fragile:** Launch template successfully instructs agents to produce YAML frontmatter despite system prompts not mentioning it, but this creates dependency on prompt engineering rather than agent design.

2. **Validation fallback is essential:** The two-tier validation system (frontmatter-first, prose fallback) enables graceful degradation and keeps synthesis working even with malformed outputs.

3. **Convergence tracking adds value:** Tracking which agents flag each issue and prioritizing high-convergence findings transforms individual agent outputs into confidence-weighted recommendations.

4. **Token optimization is critical:** Trimming 200+ line documents to ~50% based on agent focus areas enables 8 agents to run in parallel without exhausting token budgets.

5. **Error handling enables resilience:** Graceful degradation at each failure point (Oracle timeout, Codex dispatch fail, malformed output) allows the system to produce partial results rather than failing completely.

**Recommended path forward:**

Standardize agent outputs at the source (update system prompts with frontmatter template) rather than relying on runtime overrides. Extract validation, convergence tracking, and error handling into reusable libraries. Componentize launch templates for maintainability. Total effort: ~6 weeks to unified solution.

**The payoff:** A robust multi-agent review system that can be reused across workflows, with predictable output formats, measurable quality metrics, and maintainable error handling.
