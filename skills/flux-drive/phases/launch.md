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

**Skip this step if Step 1.0a detected no domains** (document profile shows "none detected").

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

### Step 2.2: Stage 1 — Launch top agents

**Condition**: Use this step when `DISPATCH_MODE = task` (default).

Launch Stage 1 agents (top 2-3 by triage score) as parallel Task calls with `run_in_background: true`.

Wait for Stage 1 agents to complete (use the polling from Step 2.3).

### Step 2.2b: Expansion decision

After Stage 1 completes, read the Findings Index from each Stage 1 output file. Based on findings:

| Stage 1 Result | Action |
|---|---|
| Any P0 issue found | Launch ALL Stage 2 agents — need convergence data |
| Multiple P1 issues, or agents disagree | Launch ALL Stage 2 agents for coverage |
| Single P1 from one agent only | Launch 1-2 targeted Stage 2 agents in the flagged domain |
| Only P2/improvements or clean | **Early stop** — Stage 1 is sufficient |

Present the expansion decision to user:
```yaml
AskUserQuestion:
  question: "Stage 1 complete. [brief findings summary]. Expand to Stage 2?"
  options:
    - label: "Launch remaining N agents (Recommended)"
      description: "Get full coverage from Stage 2 agents"
    - label: "Stop here"
      description: "Stage 1 findings are sufficient"
    - label: "Launch specific agents"
      description: "Choose which Stage 2 agents to launch"
```

If findings are only P2/improvements or clean, make "Stop here (Recommended)" the default first option.
If expanding, present options appropriate to findings severity and continue with the user's choice.

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

**Document content**: Include the full document in each agent's prompt without trimming. Each agent gets the complete document content.

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
## CRITICAL: Output Format Override

Your agent definition has a default output format. IGNORE IT for this task.
You MUST use the format specified below. This is a flux-drive review task
and synthesis depends on a machine-parseable Findings Index.

### Required Output

Your FIRST action MUST be: use the Write tool to create `{OUTPUT_DIR}/{agent-name}.md.partial`.
ALL findings go in that file — do NOT return findings in your response text.
When complete, add `<!-- flux-drive:complete -->` as the last line, then rename the file
from `.md.partial` to `.md` using Bash: `mv {OUTPUT_DIR}/{agent-name}.md.partial {OUTPUT_DIR}/{agent-name}.md`

**Output file:** Write to `{OUTPUT_DIR}/{agent-name}.md.partial` during work.
When your review is complete, rename to `{OUTPUT_DIR}/{agent-name}.md`.
Your LAST action MUST be this rename. Add `<!-- flux-drive:complete -->` as the final line before renaming.

The file MUST start with a Findings Index block:

### Findings Index
- P0 | P0-1 | "Section Name" | Title of the issue
- P1 | P1-1 | "Section Name" | Title
- IMP | IMP-1 | "Section Name" | Title of improvement
Verdict: safe|needs-changes|risky

After the Findings Index, use EXACTLY this prose structure:

### Summary (3-5 lines)
[Your top findings]

### Issues Found
[Numbered, with severity: P0/P1/P2. Must match Findings Index.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]

If you have zero findings, still write the file with an empty Findings Index
(just the header and Verdict line) and verdict: safe.

---

## Review Task

You are reviewing a {document_type} for {review_goal}.

## Knowledge Context

[If knowledge entries were retrieved for this agent:]
The following patterns were discovered in previous reviews. Consider them as context but verify independently — do NOT simply re-confirm without checking.

{For each knowledge entry:}
- **Finding**: {entry body — first 1-3 lines}
  **Evidence**: {evidence anchors from entry body}
  **Last confirmed**: {lastConfirmed from frontmatter}

[If no knowledge entries were retrieved:]
No prior knowledge available for this review domain.

**Provenance note**: If any knowledge entry above matches a finding you would independently flag, note it as "independently confirmed" in your findings. If you are only re-stating a knowledge entry without independent evidence, note it as "primed confirmation" — this distinction is critical for knowledge decay.

## Domain Context

[If domains were detected in Step 1.0a AND Step 2.1a extracted criteria for this agent:]

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

[For INPUT_TYPE = file or directory:]

[Trimmed document content — orchestrator applies token optimization above.]

[For repo reviews: README + key structural info from Step 1.0.]

[When divergence exists, also include specific things for THIS agent to
check in the actual codebase — file paths, line numbers, known issues
you spotted during Step 1.0.]

## Diff to Review

[For INPUT_TYPE = diff only — replace the "Document to Review" section above with this:]

### Diff Stats
- Files changed: {file_count}
- Lines: +{added} -{removed}
- Commit: {commit_message or "N/A"}

### Priority Files (full hunks)

[Complete diff hunks for files classified as priority for this agent.
Preserve original unified diff format.]

{priority diff hunks}

### Context Files (summary only)

[One-liner per non-priority file — filename, change stats, change type.]

{context file summaries}

[Diff slicing active: {P} priority files ({L1} lines), {C} context files ({L2} lines summarized)]

> **Note to agent**: If you need full hunks for a context file to complete your review,
> note it in your findings as "Request full hunks: {filename}" — the orchestrator may
> re-run with adjusted routing.

[For cross-cutting agents or small diffs: omit the Priority/Context split and include the full diff under a single "### Full Diff" header instead.]

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
