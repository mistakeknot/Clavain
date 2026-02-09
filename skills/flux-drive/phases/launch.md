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

**Tier 1 agents (codebase-aware)**:
- Use the native `subagent_type` from the roster (e.g., `clavain:review:fd-user-experience`)
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
