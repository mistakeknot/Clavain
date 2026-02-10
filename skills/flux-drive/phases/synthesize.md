# Phase 3: Synthesize

### Step 3.0: Verify all agents completed

Phase 2 (Step 2.3) guarantees one `.md` file per launched agent — either findings or an error stub. Verify:

```bash
ls {OUTPUT_DIR}/
```

Confirm N files (one per launched agent). If count < N, Phase 2 did not complete properly — check Step 2.3 output before proceeding.

### Step 3.1: Validate Agent Output

For each agent's output file, validate structure before reading content:

1. Check the file starts with `### Findings Index` (first non-empty line)
2. Verify index lines match `- SEVERITY | ID | "Section" | Title` pattern
3. Check for a `Verdict:` line after the index entries
4. Classification:
   - **Valid**: Findings Index parsed successfully → proceed with index-first collection
   - **Error**: File contains "verdict: error" or "Verdict: error" → note as "agent failed" in summary, don't count toward convergence
   - **Malformed**: File exists but Findings Index is missing/unrecognizable → fall back to prose-based reading (read Summary + Issues sections directly)
   - **Missing**: File doesn't exist or is empty → "no findings"

Report validation results to user: "5/6 agents returned valid Findings Index, 1 failed"

### Step 3.2: Collect Results

For each **valid** agent output, read the **Findings Index** first (first ~30 lines). This gives you a structured list of all issues and improvements without reading full prose. Only read the prose body if:
- An issue needs more context to understand
- You need to resolve a conflict between agents

For **malformed** outputs, read the Summary + Issues sections as prose fallback.

### Step 3.3: Deduplicate and Organize

1. **Group findings by section** — organize all agent findings under the section they apply to (or by topic for repo reviews)
2. **Deduplicate**: If multiple agents flagged the same issue, keep the most specific one (prefer Project Agents over plugin Adaptive Reviewers, since they have deeper project context)
3. **Track convergence**: Note how many agents flagged each issue (e.g., "4/6 agents"). High convergence (3+ agents) = high confidence. Include convergence counts in the Issues to Address checklist.
**Partial agent sets**: If Stage 2 was not launched (early stop), adjust convergence counts to reflect the smaller agent set. Report in the summary: "Early stop after Stage 1: N agents ran, M agents skipped as unnecessary."
4. **Flag conflicts**: If agents disagree, note both positions
5. **Priority from project-specific agents**: When a Project Agent and an Adaptive Reviewer give different advice on the same topic, prefer the Project Agent's recommendation

### Step 3.4: Update the Document

**The write-back strategy depends on input type:**

#### For file inputs (plans, brainstorms, specs, etc.)

Write findings to `{OUTPUT_DIR}/summary.md` (same as repo reviews). Do NOT modify `INPUT_FILE` by default.

The summary file should contain:

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

### Improvements Suggested
- [Numbered, with rationale and agent attribution]

### Individual Agent Reports
- [{agent-name}](./{agent-name}.md) — [1-line verdict summary]
- ...
```

After writing the summary file, ask:

```yaml
AskUserQuestion:
  question: "Summary written to {OUTPUT_DIR}/summary.md. Add inline annotations to the original document?"
  options:
    - label: "No, summary only (Recommended)"
      description: "Keep the original document clean"
    - label: "Yes, add inline annotations"
      description: "Add findings as blockquotes in the original document"
```

If the user opts in to inline annotations, then apply the existing inline logic: add the Enhancement Summary header at the top of `INPUT_FILE` and add per-section blockquotes:

```markdown
> **Flux Drive** ({agent-name}): [Concise finding or suggestion]
```

#### For repo reviews (directory input, no specific file)

Do NOT modify the repo's README or any existing files. Instead, write a new summary file to `{OUTPUT_DIR}/summary.md` that:

- Summarizes all findings organized by topic
- Links to individual agent reports in the same directory
- Includes the same Enhancement Summary format (Key Findings, Issues to Address checklist)

### Step 3.4a: Generate findings.json

After collecting and deduplicating findings, generate `{OUTPUT_DIR}/findings.json`:

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
      "agent": "architecture-strategist",
      "section": "Section Name",
      "title": "Short description",
      "convergence": 3
    }
  ],
  "improvements": [
    {
      "id": "IMP-1",
      "agent": "fd-code-quality",
      "section": "Section Name",
      "title": "Short description"
    }
  ],
  "verdict": "needs-changes",
  "early_stop": false
}
```

Use the Write tool to create this file. The orchestrator generates this from the collected Findings Indexes — agents never write JSON.

**Verdict logic**: If any finding is P0 → "risky". If any P1 → "needs-changes". Otherwise → "safe".

### Step 3.5: Report to User

Tell the user:
- How many agents ran
- Top findings (3-5 most important)
- Which sections got the most feedback
- Where full analysis files are saved (`{OUTPUT_DIR}/`)
