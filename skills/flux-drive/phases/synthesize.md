# Phase 3: Synthesize

### Step 3.0: Verify all agents completed

Phase 2 (Step 2.3) guarantees one `.md` file per launched agent — either findings or an error stub. Verify:

```bash
ls {OUTPUT_DIR}/
```

Confirm N files (one per launched agent). If count < N, Phase 2 did not complete properly — check Step 2.3 output before proceeding.

### Step 3.1: Validate Agent Output

For each agent's output file, validate structure before reading content:

1. Check the file starts with `---` (YAML frontmatter delimiter)
2. Verify required keys exist: `agent`, `tier`, `issues`, `verdict`
3. Classification:
   - **Valid**: Frontmatter parsed successfully → proceed with frontmatter-first collection
   - **Error**: File exists with `verdict: error` → note as "agent failed" in summary, don't count toward convergence
   - **Malformed**: File exists but frontmatter is missing/incomplete → fall back to prose-based reading (read Summary + Issues sections directly)
   - **Missing**: File doesn't exist or is empty → "no findings"

Report validation results to user: "5/6 agents returned valid frontmatter, 1 failed"

### Step 3.2: Collect Results

For each **valid** agent output, read the **YAML frontmatter** first (first ~60 lines). This gives you a structured list of all issues and improvements without reading full prose. Only read the prose body if:
- An issue needs more context to understand
- You need to resolve a conflict between agents

For **malformed** outputs, read the Summary + Issues sections as prose fallback.

### Step 3.3: Deduplicate and Organize

1. **Group findings by section** — organize all agent findings under the section they apply to (or by topic for repo reviews)
2. **Deduplicate**: If multiple agents flagged the same issue, keep the most specific one (prefer Project Agents over plugin Adaptive Reviewers, since they have deeper project context)
3. **Track convergence**: Note how many agents flagged each issue (e.g., "4/6 agents"). High convergence (3+ agents) = high confidence. Include convergence counts in the Issues to Address checklist.
4. **Flag conflicts**: If agents disagree, note both positions
5. **Priority from project-specific agents**: When a Project Agent and an Adaptive Reviewer give different advice on the same topic, prefer the Project Agent's recommendation

### Step 3.4: Update the Document

**The write-back strategy depends on input type:**

#### For file inputs (plans, brainstorms, specs, etc.)

Read the current file at `INPUT_FILE`. **Decide the update strategy:**

- **Amend** (default): Add findings to the existing document. Use when the document is mostly correct and findings are incremental improvements.
- **Flag for archival**: When the document is fundamentally obsolete (e.g., wrong tech stack, wrong architecture), add a prominent warning at the top recommending the document be archived and rewritten. Still add findings — they apply to the actual codebase even if the document is wrong.

Add a summary section at the top:

```markdown
## Flux Drive Enhancement Summary

Reviewed by N agents on YYYY-MM-DD.
[If divergence detected:] **WARNING: This document is outdated.** The codebase has diverged from the described [tech stack]. Consider archiving this document and writing a new one.

### Key Findings
- [Top 3-5 findings across all agents, with convergence: "(N/M agents)"]

### Issues to Address
- [ ] [Issue 1 — from agents X, Y, Z] (severity, N/M agents)
- [ ] [Issue 2 — from agent Y] (severity)
- ...
```

For each section that received feedback, add an inline note:

```markdown
> **Flux Drive** ({agent-name}): [Concise finding or suggestion]
```

Write the updated document back to `INPUT_FILE`.

#### For repo reviews (directory input, no specific file)

Do NOT modify the repo's README or any existing files. Instead, write a new summary file to `{OUTPUT_DIR}/summary.md` that:

- Summarizes all findings organized by topic
- Links to individual agent reports in the same directory
- Includes the same Enhancement Summary format (Key Findings, Issues to Address checklist)

### Step 3.5: Report to User

Tell the user:
- How many agents ran
- Top findings (3-5 most important)
- Which sections got the most feedback
- Where full analysis files are saved (`{OUTPUT_DIR}/`)
