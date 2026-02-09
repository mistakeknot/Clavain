# Phase 2: Launch (Task Dispatch)

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

If `CLODEX_MODE=true`: Read `phases/launch-codex.md` instead of continuing here.
If `CLODEX_MODE=false`: Continue with step 2.2 below.

### Step 2.2: Launch agents (Task dispatch)

**Condition**: Use this step when `CLODEX_MODE=false` (default).

Launch all selected agents as parallel Task calls in a **single message**.

**Critical**: Every agent MUST use `run_in_background: true`. This prevents agent output from flooding the main conversation context.

### How to launch each agent type:

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
- Output goes to `{OUTPUT_DIR}/oracle-council.md`

**Orchestrator: Token trimming (before constructing prompt below):**
For file inputs with 200+ lines, trim the document before including it in the prompt:
1. Keep FULL content for sections in the agent's focus area
2. Keep Summary, Goals, Non-Goals in full (if present)
3. For ALL OTHER sections: replace with: `## [Section Name] — [1-sentence summary]`
4. For repo reviews: include README + build files + 2-3 key source files only

Target: ~50% of original document. The agent should not see trimming instructions.

### Prompt template for each agent:

```
## CRITICAL: Output Format Override

Your agent definition has a default output format. IGNORE IT for this task.
You MUST use the format specified below. This is a flux-drive review task
and synthesis depends on machine-parseable YAML frontmatter.

### Required Output

Your FIRST action MUST be: use the Write tool to create the findings file.
ALL findings go in that file — do NOT return findings in your response text.

**Output file:** {OUTPUT_DIR}/{agent-name}.md

The file MUST start with this YAML frontmatter block:

---
agent: {agent-name}
tier: {domain|project|adaptive|cross-ai}
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

After launching all agents, tell the user:
- How many agents were launched
- That they are running in background
- Estimated wait time (~3-5 minutes)

### Step 2.3: Verify agent completion

After all background tasks complete (check via TaskOutput or output file existence):

1. List `{OUTPUT_DIR}/` — expect one `.md` file per launched agent
2. For any missing file after 5 minutes:
   a. Check the background task output for errors
   b. **Retry once** (Task-dispatched agents only): Re-launch the agent with the same prompt (use `run_in_background: false` so you get direct output). Do NOT retry Oracle — its bash command already writes failure to the output file.
   c. If retry produces output, write it to `{OUTPUT_DIR}/{agent-name}.md`
   d. If retry also fails, create a stub file:
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
3. Report to user: "N/M agents completed successfully, K retried, J failed"
