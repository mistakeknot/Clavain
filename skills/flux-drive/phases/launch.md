# Phase 2: Launch (Task Dispatch)

### Step 2.0: Prepare output directory

Create the research output directory before launching agents. Resolve to an absolute path:
```bash
mkdir -p {OUTPUT_DIR}  # Must be absolute, e.g. /root/projects/Foo/docs/research/flux-drive/my-doc-name
```

Then enforce run isolation before dispatch:
```bash
find {OUTPUT_DIR} -maxdepth 1 -type f \( -name "*.md" -o -name "*.md.partial" \) -delete
```

Use a timestamped `OUTPUT_DIR` only when you intentionally need to preserve previous run artifacts.

### Step 2.1: Retrieve knowledge context

Before launching agents, retrieve relevant knowledge entries for each selected agent. This step is OPTIONAL — if qmd is unavailable, skip and proceed to Step 2.2.

**For each selected agent**, construct a retrieval query:
1. Combine the agent's domain keywords with the document summary from Phase 1
2. Use the qmd MCP tool to search:
   ```
   Tool: mcp__plugin_clavain_qmd__vsearch
   Parameters:
     collection: "Clavain"
     query: "{agent domain} {document summary keywords}"
     path: "config/flux-drive/knowledge/"
     limit: 5
   ```
3. If qmd returns results, format them as a knowledge context block

**Domain keywords by agent:**
| Agent | Domain keywords |
|-------|----------------|
| fd-architecture | architecture boundaries coupling patterns complexity |
| fd-safety | security threats credentials deployment rollback trust |
| fd-correctness | data integrity transactions races concurrency async |
| fd-quality | naming conventions testing code quality style idioms |
| fd-user-product | user experience flows UX value proposition scope |
| fd-performance | performance bottlenecks rendering memory scaling |
| fd-game-design | game balance pacing player psychology feedback loops emergent behavior |

**Cap**: 5 entries per agent maximum. If qmd returns more, take the top 5 by relevance score.

**Fallback**: If qmd MCP tool is unavailable or errors, skip knowledge injection entirely — agents run without it (effectively v1 behavior). Do NOT block agent launch on qmd failures.

**Pipelining**: Start qmd queries before agent dispatch. While queries run, prepare agent prompts. Inject results when both are ready.

### Step 2.1a: Load domain-specific review criteria

**Skip this step if Step 1.0.1 detected no domains** (document profile shows "none detected").

For each detected domain (from the Document Profile's `Project domains` field), load the corresponding domain profile and extract per-agent injection criteria:

1. **Read the domain profile file**: `${CLAUDE_PLUGIN_ROOT}/config/flux-drive/domains/{domain-name}.md`
2. **For each selected agent**, find the `### fd-{agent-name}` subsection under `## Injection Criteria`
3. **Extract the bullet points** — these are the domain-specific review criteria for that agent
4. **Store as `{DOMAIN_CONTEXT}`** per agent, formatted as shown in the prompt template below

**Multi-domain injection:**
- Inject criteria from ALL detected domains, not just the primary one (a game server should get both `game-simulation` and `web-api` criteria)
- Order sections by confidence score (primary domain first)
- **Cap at 3 domains** to prevent prompt bloat — if more than 3 detected, use only the top 3 by confidence
- If a domain profile has no matching `### fd-{agent-name}` section for a particular agent, skip that domain for that agent

**Fallback**: If the domain profile file doesn't exist or can't be read, skip that domain silently. Do NOT block agent launch on domain profile failures.

**Performance**: Domain profile files are small (~90-100 lines each). Reading 1-3 files adds negligible overhead. This step should take <1 second.

### Step 2.1c: Write document to temp file(s)

Write the document (or per-agent slices) to temp files so agents can Read them instead of receiving inline content. This eliminates document duplication across agent prompts.

**Timestamp**: Generate once for all temp files in this run:
```bash
TS=$(date +%s)
```

#### Case 1: File/directory inputs — small document (< 200 lines)

One shared file for all agents:
```bash
REVIEW_FILE="/tmp/flux-drive-${INPUT_STEM}-${TS}.md"
```
Write the full document content. All agents reference this single file.

#### Case 2: File/directory inputs — document slicing active (>= 200 lines)

Uses the `section_map` from Step 1.2c. Write per-agent temp files for domain-specific agents:

1. **Cross-cutting agents** (fd-architecture, fd-quality): Write one shared full-document file:
   ```bash
   REVIEW_FILE="/tmp/flux-drive-${INPUT_STEM}-${TS}.md"
   ```

2. **Domain-specific agents**: Write one file per agent containing priority sections in full + context section summaries:
   ```bash
   REVIEW_FILE_fd_safety="/tmp/flux-drive-${INPUT_STEM}-fd-safety-${TS}.md"
   REVIEW_FILE_fd_correctness="/tmp/flux-drive-${INPUT_STEM}-fd-correctness-${TS}.md"
   ```

   **Per-agent file structure**:
   ```markdown
   [Document slicing active: {P} priority sections ({L1} lines), {C} context sections ({L2} lines summarized)]

   ## Priority Sections (full content)

   {priority section content — preserve original markdown including headings}

   ## Context Sections (summaries)

   - **{Section Name}**: {1-line summary} ({N} lines)
   - **{Section Name}**: {1-line summary} ({N} lines)

   > If you need full content for a context section, note it as
   > "Request full section: {name}" in your findings.
   ```

3. **Pyramid Summary** (documents >= 500 lines): Prepend the pyramid summary to each agent's file (it's small and helps agents navigate).

#### Case 3: Diff inputs — no slicing (< 1000 lines or cross-cutting)

One shared file:
```bash
REVIEW_FILE="/tmp/flux-drive-${INPUT_STEM}-${TS}.diff"
```

#### Case 4: Diff inputs — with per-agent slicing (>= 1000 lines)

Per-agent files with priority hunks + context summaries (unchanged from existing diff slicing logic):
```bash
REVIEW_FILE_fd_safety="/tmp/flux-drive-${INPUT_STEM}-fd-safety-${TS}.diff"
```

Record all REVIEW_FILE paths for use in prompt construction (Step 2.2).

### Step 2.2: Stage 1 — Launch top agents

**Condition**: Use this step when `DISPATCH_MODE = task` (default).

Launch Stage 1 agents (top 2-3 by triage score) as parallel Task calls with `run_in_background: true`.

Wait for Stage 1 agents to complete (use the polling from Step 2.3).

### Step 2.2b: Domain-aware expansion decision

After Stage 1 completes, read the Findings Index from each Stage 1 output file. Then use the **expansion scoring algorithm** to recommend which Stage 2 agents (and expansion pool agents) to launch.

#### Domain adjacency map

Agents with related domains. A finding in one agent's domain makes adjacent agents more valuable:

```yaml
adjacency:
  fd-architecture: [fd-performance, fd-quality]
  fd-correctness: [fd-safety, fd-performance]
  fd-safety: [fd-correctness, fd-architecture]
  fd-quality: [fd-architecture, fd-user-product]
  fd-user-product: [fd-quality, fd-game-design]
  fd-performance: [fd-architecture, fd-correctness]
  fd-game-design: [fd-user-product, fd-correctness, fd-performance]
```

#### Expansion scoring algorithm

For each Stage 2 / expansion pool agent, compute an expansion score:

```
expansion_score = 0

# Severity signals (from Stage 1 findings)
if any P0 in an adjacent agent's domain:    expansion_score += 3
if any P1 in an adjacent agent's domain:    expansion_score += 2
if Stage 1 agents disagree on a finding in this agent's domain: expansion_score += 2

# Domain signals
if agent has domain injection criteria for a detected domain: expansion_score += 1
```

#### Expansion decision

| max(expansion_scores) | Decision |
|---|---|
| ≥ 3 | **RECOMMEND expansion** — present specific agents with reasoning (default first option) |
| 2 | **OFFER expansion** — present as user's choice (no default recommendation) |
| ≤ 1 | **RECOMMEND stop** — "Stop here" is the default first option |

#### Presenting to user

Use **AskUserQuestion** with reasoning about WHY each agent should be added:

```yaml
AskUserQuestion:
  question: "Stage 1 complete. [findings summary]. [expansion reasoning]"
  options:
    # When recommending expansion (max score ≥ 3):
    - label: "Launch [specific agents] (Recommended)"
      description: "[reasoning — e.g., 'P0 in game design → fd-correctness validates simulation state']"
    - label: "Launch all Stage 2 (N agents)"
      description: "Full coverage from remaining agents"
    - label: "Stop here"
      description: "Stage 1 findings are sufficient"
    # When offering (max score = 2):
    - label: "Launch [specific agents]"
      description: "[reasoning]"
    - label: "Stop here"
      description: "Stage 1 findings are sufficient"
    # When recommending stop (max score ≤ 1):
    - label: "Stop here (Recommended)"
      description: "Only P2/improvements found — Stage 1 is sufficient"
    - label: "Launch all Stage 2 anyway"
      description: "Run remaining N agents for extra coverage"
```

**Example reasoning**: "Stage 1 found a P0 in game design (death spiral in storyteller). fd-correctness is adjacent to fd-game-design and has domain criteria for simulation state consistency — it could validate whether this is a code bug or design issue. Launch fd-correctness + fd-performance for Stage 2?"

If the user chooses expansion, launch only the recommended agents (not all Stage 2) unless they explicitly select "Launch all."

### Step 2.2c: Stage 2 — Remaining agents (if expanded)

Launch Stage 2 agents with `run_in_background: true`. Wait for completion using the same polling mechanism.

### How to launch each agent type (applies to Stage 1 and Stage 2):

**Project Agents (.claude/agents/)**:
- `subagent_type: general-purpose`
- Include the agent file's full content as the system prompt
- Set `run_in_background: true`

**Plugin Agents (clavain)**:
- Use the native `subagent_type` from the roster (e.g., `clavain:review:fd-architecture`)
- Set `run_in_background: true`

**Cross-AI (Oracle)**:
- Run via Bash tool with `run_in_background: true` and `timeout: 600000`
- Requires `DISPLAY=:99` and `CHROME_PATH=/usr/local/bin/google-chrome-wrapper`
- Output goes to `{OUTPUT_DIR}/oracle-council.md.partial`, renamed to `.md` on success

**Document content**: Write the document to a temp file once; agents Read it as their first action. See Step 2.1c below.

**Exception for very large file/directory inputs** (1000+ lines): Include only the sections relevant to the agent's focus area plus Summary, Goals, and Non-Goals. Note which sections were omitted in the agent's prompt.

**Prompt trimming**: See `phases/shared-contracts.md` for trimming rules.

### Step 2.1b: Prepare diff content for agent prompts

**Skip this step if `INPUT_TYPE` is not `diff`.** For file/directory inputs, use the standard document content rules above.

For diff inputs, content preparation depends on diff size and the agent's routing classification:

#### Small diffs (< 1000 lines)

Send the full diff to all agents. No slicing needed.

#### Large diffs (>= 1000 lines) — Soft-Prioritize Slicing

When `slicing_eligible: yes` from the Diff Profile (Phase 1, Step 1.1):

1. **Read** `config/flux-drive/diff-routing.md` from the flux-drive skill directory
2. **Classify each changed file** as `priority` or `context` per agent:
   - A file is `priority` for an agent if it matches ANY of the agent's priority file patterns OR any hunk in the file contains ANY of the agent's priority keywords
   - All other files are `context` for that agent
3. **Cross-cutting agents** (fd-architecture, fd-quality): always receive the full diff — skip slicing entirely
4. **Domain-specific agents** (fd-safety, fd-correctness, fd-performance, fd-user-product): receive priority hunks in full + compressed context summary
5. **80% threshold**: If an agent's priority files cover >= 80% of total changed lines, skip slicing for that agent and send the full diff

#### Constructing per-agent diff content

For each **domain-specific agent** that receives sliced content:

**Priority section** — Include the complete diff hunks for all priority files, preserving the original diff format:
```
diff --git a/path/to/file b/path/to/file
--- a/path/to/file
+++ b/path/to/file
@@ ... @@
[full hunk content]
```

**Context section** — For non-priority files, include a one-line summary per file:
```
[context] path/to/file: +12 -5 (modified)
[context] path/to/other: +0 -0 (renamed from old/path)
[context] path/to/binary: [binary change]
```

#### Edge cases

| Case | Handling |
|------|----------|
| Binary files | Listed in context summary: `[binary] path: binary change`. Never priority (no text hunks). |
| Rename-only | Context summary: `[renamed] old → new: +0 -0`. Priority for fd-architecture regardless. |
| Multi-commit diff | Deduplicate: each file appears once with aggregate hunks. |
| No pattern matches | Agent gets only compressed summaries + stats. Still sees all file names. |

### Prompt template for each agent:

<!-- This template implements the Findings Index contract from shared-contracts.md -->

```
## Output Format

Write findings to `{OUTPUT_DIR}/{agent-name}.md.partial`. Rename to `.md` when done.
Add `<!-- flux-drive:complete -->` as the last line before renaming.

ALL findings go in that file — do NOT return findings in your response text.

File structure:

### Findings Index
- SEVERITY | ID | "Section" | Title
Verdict: safe|needs-changes|risky

### Summary
[3-5 lines]

### Issues Found
[ID. SEVERITY: Title — 1-2 sentences with evidence]

### Improvements
[ID. Title — 1 sentence with rationale]

Zero findings: empty index + verdict: safe.

---

## Review Task

You are reviewing a {document_type} for {review_goal}.

[Only include this section if knowledge entries were retrieved in Step 2.1 for this agent.
If no knowledge entries exist, omit the entire Knowledge Context section — do not include it empty.]

## Knowledge Context

The following patterns were discovered in previous reviews. Consider them as context but verify independently — do NOT simply re-confirm without checking.

{For each knowledge entry:}
- **Finding**: {entry body — first 1-3 lines}
  **Evidence**: {evidence anchors from entry body}
  **Last confirmed**: {lastConfirmed from frontmatter}

**Provenance note**: If any knowledge entry above matches a finding you would independently flag, note it as "independently confirmed" in your findings. If you are only re-stating a knowledge entry without independent evidence, note it as "primed confirmation" — this distinction is critical for knowledge decay.

## Domain Context

[If domains were detected in Step 1.0.1 AND Step 2.1a extracted criteria for this agent:]

This project is classified as: {domain1} ({confidence1}), {domain2} ({confidence2}), ...

Additional review criteria for your focus area in these project types:

### {domain1-name}
{bullet points from domain profile's ### fd-{agent-name} section}

### {domain2-name}
{bullet points from domain profile's ### fd-{agent-name} section}

[Repeat for up to 3 detected domains. Omit any domain that has no matching section for this agent.]

Apply these criteria **in addition to** your standard review approach. They highlight common issues specific to this project type. Treat them as additional checks, not replacements for your core analysis.

[If no domains detected OR no criteria found for this agent:]
(Omit this section entirely — do not include an empty Domain Context header.)

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

**File path**: `{REVIEW_FILE}` [or `{REVIEW_FILE_{agent-name}}` if document slicing is active]

Your FIRST action must be to Read this file using the Read tool.

[For full-document agents (cross-cutting, or document < 200 lines):]
It contains the full document under review.

[For sliced agents (document >= 200 lines, domain-specific):]
This file contains priority sections for your review domain in full,
plus one-line summaries of other sections. If you need full content
for a summarized section, note "Request full section: {name}" in your findings.

[For repo reviews: Include README + key structural info from Step 1.0 inline,
then reference the temp file for the full content.]

[When divergence exists, also include specific things for THIS agent to
check in the actual codebase — file paths, line numbers, known issues
you spotted during Step 1.0.]

## Diff to Review

[For INPUT_TYPE = diff only — replace the "Document to Review" section above with this:]

### Diff Stats
- Files changed: {file_count}
- Lines: +{added} -{removed}
- Commit: {commit_message or "N/A"}

**Diff file**: `{REVIEW_FILE}` (or `{REVIEW_FILE_{agent-name}}` if per-agent slicing is active)

Your FIRST action must be to Read this file. It contains the diff content for your review.

[If diff slicing is active for this agent, add:]
This file contains your priority hunks in full + context file summaries.
If you need full hunks for a context file, note it as "Request full hunks: {filename}" in your findings.

[Diff slicing active: {P} priority files ({L1} lines), {C} context files ({L2} lines summarized)]

[For cross-cutting agents or small diffs: all agents share one diff file with the full content.]

## Your Focus Area

You were selected because: [reason from triage table]
Focus on: [specific sections relevant to this agent's domain]
Depth needed: [thin sections need more depth, deep sections need only validation]

Be concrete. Reference specific sections by name. Don't give generic advice.
```

After each stage launch, tell the user:
- How many agents were launched in that stage
- That they are running in background
- Estimated wait time (~3-5 minutes)

### Step 2.3: Monitor and verify agent completion

This step implements the shared monitoring contract.

After dispatching a stage of agents, report the initial status and then poll for completion:

**Initial status:**
```
Agent dispatch complete. Monitoring N agents...
⏳ fd-architecture
⏳ fd-safety
⏳ fd-quality
...
```

**Polling loop** (every 30 seconds, up to 5 minutes):
1. Check `{OUTPUT_DIR}/` for `.md` files (not `.md.partial` — those are still in progress)
2. For each new `.md` file found since the last check, report:
   ```
   ✅ fd-architecture (47s)
   [2/5 agents complete]
   ```
3. If all expected `.md` files exist, stop polling — all agents are done
4. After 5 minutes, report any agents still pending:
   ```
   ⚠️ Timeout: fd-safety still running after 300s
   ```

**Completion verification** (after polling ends):
1. List `{OUTPUT_DIR}/` — expect one `.md` file per launched agent (not `.md.partial`)
2. For any agent where only `.md.partial` exists (started but did not complete) or no file exists:
   a. Check the background task output for errors
   b. **Pre-retry guard**: If `{OUTPUT_DIR}/{agent-name}.md` already exists (not `.partial`), do NOT retry — the agent completed successfully
   c. **Retry once** (Task-dispatched agents only): Re-launch with the same prompt, `run_in_background: false`, `timeout: 300000` (5 min cap). Do NOT retry Oracle.
   d. If retry produces output, ensure it ends with `<!-- flux-drive:complete -->` and is saved as `{OUTPUT_DIR}/{agent-name}.md` (not `.partial`)
   e. If retry also fails, create an error stub following the format in `phases/shared-contracts.md`.
3. Clean up: remove any remaining `.md.partial` files in `{OUTPUT_DIR}/`
4. Report to user: "N/M agents completed successfully, K retried, J failed"
