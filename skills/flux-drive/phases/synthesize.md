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
2. **Deduplicate**: If multiple agents flagged the same issue, keep the most specific one (prefer Project Agents over plugin Plugin Agents, since they have deeper project context)
3. **Track convergence**: Note how many agents flagged each issue (e.g., "4/6 agents"). High convergence (3+ agents) = high confidence. Include convergence counts in the Issues to Address checklist.
**Partial agent sets**: If Stage 2 was not launched (early stop), adjust convergence counts to reflect the smaller agent set. Report in the summary: "Early stop after Stage 1: N agents ran, M agents skipped as unnecessary."
4. **Flag conflicts**: If agents disagree, note both positions
5. **Priority from project-specific agents**: When a Project Agent and an Plugin Agent give different advice on the same topic, prefer the Project Agent's recommendation
6. **Diff slicing awareness** (when `INPUT_TYPE = diff` and slicing was active): Use the `slicing_map` from `phases/shared-contracts.md` to track which agents had full vs summary access per file:
   - When counting convergence for a finding, only count agents that received the file as priority (full hunks). Agents that received it as context-only are excluded from convergence counts.
   - Tag findings from context-only files as `[discovered beyond sliced scope]` — these are especially valuable since the agent had limited visibility.
   - If 2+ agents independently request full hunks for the same context file (via "Request full hunks" notes), flag this as a routing improvement suggestion.
   - Include these observations in the Diff Slicing Report (see Step 3.5).

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

Use the Write tool to create this file. The orchestrator generates this from the collected Findings Indexes — agents never write JSON.

**Verdict logic**: If any finding is P0 → "risky". If any P1 → "needs-changes". Otherwise → "safe".

### Step 3.5: Report to User

Present the synthesis report using this exact structure. Fill in each section from the collected findings.

```markdown
## Flux Drive Review — {INPUT_STEM}

**Reviewed**: {YYYY-MM-DD} | **Agents**: {N launched}, {M completed} | **Verdict**: {safe|needs-changes|risky}
[If early stop:] *(Stage 1 only — {K} agents skipped as unnecessary)*

### Critical Findings (P0)
[List P0 findings with agent attribution and convergence. If none: "None."]

### Important Findings (P1)
[List P1 findings with convergence counts: "(3/5 agents)". If none: "None."]

### Improvements Suggested
[Top 3-5 improvements, prioritized. Each with agent attribution.]

### Section Heat Map
| Section | Issues | Improvements | Agents Reporting |
|---------|--------|-------------|-----------------|
| [Section Name] | P0: N, P1: N | N | agent1, agent2 |

### Conflicts
[Any disagreements between agents. If none: "No conflicts detected."]

### Files
- Summary: `{OUTPUT_DIR}/summary.md`
- Findings: `{OUTPUT_DIR}/findings.json`
- Individual reports: `{OUTPUT_DIR}/{agent-name}.md`

### Diff Slicing Report

[Include this section only when INPUT_TYPE = diff AND slicing was active (diff >= 1000 lines).]

| Agent | Mode | Priority Files | Context Files | Lines Reviewed (full) |
|-------|------|---------------|---------------|----------------------|
| fd-architecture | full | all | — | {total_lines} |
| fd-safety | sliced | {P} | {C} | {L1} |
| ... | ... | ... | ... | ... |

**Threshold**: {1000} lines (slicing activated)
**Slicing disagreements**: [List any context files that 2+ agents requested full hunks for, or "None"]
**Routing improvements**: [Suggest pattern additions to diff-routing.md if agents consistently needed context files, or "None suggested"]
**Out-of-scope discoveries**: [List findings tagged `[discovered beyond sliced scope]`, or "None"]

[If this is the first flux-drive run on this project (config/flux-drive/knowledge/ was empty):]
*First review on this project — building knowledge base for future reviews.*
```

**After the report**, suggest next steps based on the verdict:
- **risky**: "Consider addressing P0 findings before proceeding. Run `/clavain:resolve` to auto-fix."
- **needs-changes**: "Review P1 findings. Run `/clavain:flux-drive` again after changes to verify."
- **safe**: "No blocking issues found. Individual reports available for detailed review."

---

## Post-Synthesis: Silent Compounding

After presenting the review to the user (Step 3.5), run a compounding step in the background. This step is SILENT — no user-visible output. The user's last interaction is the Step 3.5 report.

### Purpose

Extract durable patterns from agent findings and save them to `config/flux-drive/knowledge/` for future reviews. This is how flux-drive "gets smarter" over time.

### Implementation

Launch a background Task agent (model: sonnet) with this prompt:

````markdown
You are the flux-drive compounding agent. Your job is to extract durable, reusable patterns from review findings and save them as knowledge entries.

## Input

Read the agent output files in {OUTPUT_DIR}/:
- Read the Findings Index from each agent's .md file (first ~30 lines)
- For P0/P1 findings, read the full prose section for evidence anchors

## Decision Criteria

For each finding, decide: **compound or skip?**

**Compound** (save as knowledge entry) when the finding is:
- A pattern likely to recur in future reviews (not a one-off typo or style nit)
- Backed by concrete evidence (file paths, line numbers, symbol names)
- Generalizable beyond this specific document (not "line 47 has a typo")

**Skip** when:
- The finding is document-specific and won't recur
- The finding lacks evidence anchors
- The finding is a stylistic preference, not a correctness or safety concern
- The finding is an improvement suggestion, not a discovered pattern

## Knowledge Entry Format

For each finding worth compounding, write a markdown file to `config/flux-drive/knowledge/`:

Filename: `{short-kebab-case-description}.md` (e.g., `auth-middleware-swallows-cancellation.md`)

Content:
```yaml
---
lastConfirmed: {today's date YYYY-MM-DD}
provenance: independent
---
{1-3 sentence description of the pattern}

Evidence: {file paths, symbol names, line ranges from the agent's finding}
Verify: {1-3 steps to confirm this finding is still valid}
```

## Provenance Rules

- If this is a NEW finding (no matching knowledge entry was injected): set `provenance: independent`
- If this finding MATCHES a knowledge entry that was injected into the agent's context: check the agent's provenance note
  - If the agent noted "independently confirmed": update the existing entry's `lastConfirmed` date and set `provenance: independent`
  - If the agent noted "primed confirmation": do NOT update `lastConfirmed` — the confirmation is primed, not genuine

## Sanitization Rules

Before writing ANY knowledge entry, sanitize it:
- Remove specific file paths from external repos (not the Clavain repo)
- Remove hostnames, internal endpoints, org names, customer identifiers
- Generalize to heuristic form: "Auth middleware often swallows context cancellation" not "auth.go:47 in ProjectX"
- Entries about Clavain's own codebase CAN include Clavain-specific paths

## Decay Check

After compounding new entries, scan existing entries in `config/flux-drive/knowledge/`:
- Read each entry's `lastConfirmed` date
- If an entry has not been independently confirmed in the last 10 reviews (approximate by date: >60 days), move it to `config/flux-drive/knowledge/archive/`
- Log archived entries (for your own tracking, not user-visible)

## Output

This agent produces no user-visible output. It only writes/updates files in `config/flux-drive/knowledge/`.
If compounding fails for any reason, the review is still complete — this is best-effort infrastructure.
````

### First-Run Bootstrap

On the first flux-drive v2 run on a project, the knowledge directory will be empty. The compounding agent will:
1. Create initial knowledge entries from the first review's findings
2. All entries will have `provenance: independent` (no prior entries to be primed by)

Add a note in the Step 3.5 report template: after the Files section, add:
```markdown
[If this is the first flux-drive run on this project (config/flux-drive/knowledge/ was empty):]
*First review on this project — building knowledge base for future reviews.*
```

### Failure Handling

If the compounding Task fails:
- Do NOT report the failure to the user
- Do NOT retry
- The review is complete regardless of compounding success
- Log the error internally for debugging
