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

### Step 2.1: Detect dispatch mode

Check if clodex mode is active:

```bash
if [[ -f "${CLAUDE_PROJECT_DIR:-.}/.claude/autopilot.flag" ]]; then
  echo "CLODEX_MODE=true — dispatching review agents through Codex"
else
  echo "CLODEX_MODE=false — dispatching review agents through Task tool"
fi
```

If `CLODEX_MODE=true`: Read `phases/launch-codex.md` instead of continuing here.
If `CLODEX_MODE=false`: Continue with step 2.2 below.

### Step 2.2: Stage 1 — Launch top agents

**Condition**: Use this step when `CLODEX_MODE=false` (default).

Launch Stage 1 agents (top 2-3 by triage score) as parallel Task calls with `run_in_background: true`.

Wait for Stage 1 agents to complete (use the polling from Step 2.3).

### Step 2.2b: Expansion decision

After Stage 1 completes, read the YAML frontmatter from each Stage 1 output file. Based on findings:

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

**Adaptive Reviewers (clavain)**:
- Use the native `subagent_type` from the roster (e.g., `clavain:review:architecture-strategist`)
- Set `run_in_background: true`

**Cross-AI (Oracle)**:
- Run via Bash tool with `run_in_background: true` and `timeout: 600000`
- Requires `DISPLAY=:99` and `CHROME_PATH=/usr/local/bin/google-chrome-wrapper`
- Output goes to `{OUTPUT_DIR}/oracle-council.md.partial`, renamed to `.md` on success

**Document content**: Include the full document in each agent's prompt without trimming. Each agent gets the complete document content.

**Exception for very large inputs** (1000+ lines): Include only the sections relevant to the agent's focus area plus Summary, Goals, and Non-Goals. Note which sections were omitted in the agent's prompt.

### Prompt trimming for agent system prompts

Before including an agent's system prompt in the task prompt, strip the following sections to save tokens:

1. **`<example>` blocks**: Remove all `<example>...</example>` blocks (including nested `<commentary>...</commentary>`). These are for triage routing only and are not needed during the agent's review execution.

2. **Output Format sections**: Remove any section titled "Output Format", "Output", "Response Format", or similar. Flux-drive provides its own output format via the override below.

3. **Style/personality sections**: Remove any section about tone, writing style, wit, humor, or directness. These don't affect finding quality in structured output mode.

**Do NOT strip**: Role definition, review approach/checklist, pattern libraries, language-specific checks. These affect finding quality.

**Note**: This trimming applies to **Project Agents** whose `.md` content is pasted manually. Adaptive Reviewers load their system prompt via `subagent_type` — the orchestrator cannot strip content from those. The token cost of example blocks in Adaptive Reviewer prompts is accepted.

### Prompt template for each agent:

```
## CRITICAL: Output Format Override

Your agent definition has a default output format. IGNORE IT for this task.
You MUST use the format specified below. This is a flux-drive review task
and synthesis depends on machine-parseable YAML frontmatter.

### Required Output

Your FIRST action MUST be: use the Write tool to create `{OUTPUT_DIR}/{agent-name}.md.partial`.
ALL findings go in that file — do NOT return findings in your response text.
When complete, add `<!-- flux-drive:complete -->` as the last line, then rename the file
from `.md.partial` to `.md` using Bash: `mv {OUTPUT_DIR}/{agent-name}.md.partial {OUTPUT_DIR}/{agent-name}.md`

**Output file:** Write to `{OUTPUT_DIR}/{agent-name}.md.partial` during work.
When your review is complete, rename to `{OUTPUT_DIR}/{agent-name}.md`.
Your LAST action MUST be this rename. Add `<!-- flux-drive:complete -->` as the final line before renaming.

The file MUST start with this YAML frontmatter block:

---
agent: {agent-name}
tier: {project|adaptive|cross-ai}
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

After the frontmatter, use EXACTLY this prose structure:

### Summary (3-5 lines)
[Your top findings]

### Issues Found
[Numbered, with severity: P0/P1/P2. Must match frontmatter.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]

If you have zero findings, still write the file with empty issues/improvements
lists and verdict: safe.

---

## Review Task

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

[Trimmed document content — orchestrator applies token optimization above.]

[For repo reviews: README + key structural info from Step 1.0.]

[When divergence exists, also include specific things for THIS agent to
check in the actual codebase — file paths, line numbers, known issues
you spotted during Step 1.0.]

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

After dispatching a stage of agents, report the initial status and then poll for completion:

**Initial status:**
```
Agent dispatch complete. Monitoring N agents...
⏳ architecture-strategist
⏳ security-sentinel
⏳ go-reviewer
...
```

**Polling loop** (every 30 seconds, up to 5 minutes):
1. Check `{OUTPUT_DIR}/` for `.md` files (not `.md.partial` — those are still in progress)
2. For each new `.md` file found since the last check, report:
   ```
   ✅ architecture-strategist (47s)
   [2/5 agents complete]
   ```
3. If all expected `.md` files exist, stop polling — all agents are done
4. After 5 minutes, report any agents still pending:
   ```
   ⚠️ Timeout: security-sentinel still running after 300s
   ```

**Completion verification** (after polling ends):
1. List `{OUTPUT_DIR}/` — expect one `.md` file per launched agent (not `.md.partial`)
2. For any agent where only `.md.partial` exists (started but did not complete) or no file exists:
   a. Check the background task output for errors
   b. **Pre-retry guard**: If `{OUTPUT_DIR}/{agent-name}.md` already exists (not `.partial`), do NOT retry — the agent completed successfully
   c. **Retry once** (Task-dispatched agents only): Re-launch with the same prompt, `run_in_background: false`, `timeout: 300000` (5 min cap). Do NOT retry Oracle.
   d. If retry produces output, ensure it ends with `<!-- flux-drive:complete -->` and is saved as `{OUTPUT_DIR}/{agent-name}.md` (not `.partial`)
   e. If retry also fails, create a stub file:
      ```yaml
      ---
      agent: {agent-name}
      tier: {tier}
      issues: []
      improvements: []
      verdict: error
      ---
      Agent failed to produce findings after retry. Error: {error message}
      ```
3. Clean up: remove any remaining `.md.partial` files in `{OUTPUT_DIR}/`
4. Report to user: "N/M agents completed successfully, K retried, J failed"
