## Flux Drive Enhancement Summary

Reviewed by 3 agents (1 domain specialist, 2 adaptive reviewers) on 2026-02-09.

### Key Findings
- Tier naming migration was incomplete — Codex dispatch TIER field, cross-ai.md, and "Tier 4" heading all missed (3/3 agents)
- Duplicate wait-for-completion logic between Step 2.3 (launch) and Step 3.0 (synthesize) (1/3 agents)
- Codex review-agent.md template lacked output format override preamble (1/3 agents)

### Issues to Address
- [x] launch-codex.md TIER field uses numeric `{1|2|3}` — fixed (2/3 agents)
- [x] cross-ai.md omitted from tier rename scope — fixed (2/3 agents)
- [x] "Tier 4" heading in SKILL.md — fixed (2/3 agents)
- [x] launch.md "codebase-aware agents" residual — fixed (1/3 agents)
- [x] launch-codex.md "Tier 4 (Oracle)" reference — fixed (2/3 agents)
- [x] Duplicate wait logic in Step 2.3 + Step 3.0 — fixed, simplified Step 3.0 (1/3 agents)
- [x] Oracle retry under-specified — fixed, added "do NOT retry Oracle" note (1/3 agents)
- [x] Codex review-agent.md missing override preamble — fixed (1/3 agents)

---

# Flux-Drive Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use clavain:executing-plans to implement this plan task-by-task.

**Goal:** Fix the flux-drive multi-agent review system's output contract, prompt clarity, error handling, and naming inconsistencies across 6 beads.

**Architecture:** All changes are to markdown skill/agent/phase files — no code. The P0 fix (output format) reshapes the prompt template in phases/launch.md to make frontmatter requirements unambiguous and override agent native formats. P1s clarify trimming responsibility and file-write instructions within the same template. P2s update tier naming across SKILL.md + phases and add retry logic to launch.md. P3 aligns timeout values.

**Tech Stack:** Markdown (skill definitions, agent definitions, phase files)

---

### Task 1: Fix output format contract (Clavain-cna, P0)

**Problem:** Agent .md files define native output formats that conflict with flux-drive's YAML frontmatter requirement. The frontmatter spec is in the task prompt (user message) but agent system prompts override it.

**Files:**
- Modify: `skills/flux-drive/phases/launch.md:53-149` (prompt template)

**Step 1: Restructure the prompt template**

Move the Output Requirements section to the VERY TOP of the prompt template, before Project Context, and make it an explicit override:

Replace the current prompt template (lines 55-149) with this structure:

```
## CRITICAL: Output Format Override

Your agent definition has a default output format. IGNORE IT for this task.
Instead, you MUST use the format below. This is a flux-drive review task
and synthesis depends on machine-parseable YAML frontmatter.

### Required Output

Your FIRST action: Use the Write tool to create the file at the path below.
ALL findings go in that file — do not return findings in your response.

**Output file:** {OUTPUT_DIR}/{agent-name}.md

The file MUST start with this YAML frontmatter block:

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

After the frontmatter, use EXACTLY this prose structure:

### Summary (3-5 lines)
[Your top findings]

### Issues Found
[Numbered, with severity: P0/P1/P2. Must match frontmatter.]

### Improvements Suggested
[Numbered, with rationale]

### Overall Assessment
[1-2 sentences]

If you have zero findings, still write the file with an empty issues list
and verdict: safe.

---

## Review Task

You are reviewing a {document_type} for {review_goal}.

## Project Context
...rest of template unchanged...
```

Key changes:
1. Output format is FIRST (before review context) — agents read top-to-bottom
2. Explicit "IGNORE your default output format" override
3. File-write instruction is integrated (solves Clavain-ljy too)
4. "Section-by-Section Review" heading removed — it conflicted with agents that don't organize by section

**Step 2: Verify the template is well-formed**

Read the modified file back and confirm:
- The YAML frontmatter example has matching `---` delimiters
- The prose structure has exactly 4 headings (Summary, Issues Found, Improvements Suggested, Overall Assessment)
- The `{OUTPUT_DIR}/{agent-name}.md` placeholder appears exactly once in the output section

**Step 3: Commit**

```bash
git add skills/flux-drive/phases/launch.md
git commit -m "fix(flux-drive): move output format to top of prompt template with explicit override

Agents' system prompts define native output formats that conflict with
flux-drive's YAML frontmatter requirement. By placing the output contract
first and explicitly telling agents to ignore their default format, we
ensure machine-parseable synthesis in Phase 3.

Also integrates the file-write instruction (Clavain-ljy) into the same block.

Closes Clavain-cna, Clavain-ljy"
```

---

### Task 2: Clarify document trimming responsibility (Clavain-uyt, P1)

**Problem:** The "Token Optimization" block in the prompt template reads as an instruction to the agent, but trimming should happen BEFORE the prompt is sent.

**Files:**
- Modify: `skills/flux-drive/phases/launch.md` (prompt template, Document to Review section)

**Step 1: Replace the Token Optimization block**

The current block (lines 75-84 in original, will be at a different offset after Task 1) says:

```
IMPORTANT — Token Optimization:
For file inputs with 200+ lines, you MUST trim...
```

Replace with a comment/instruction directed at the ORCHESTRATOR (flux-drive), not the agent. Move it OUTSIDE the prompt template (above the template, as a note to the skill executor):

```markdown
**Orchestrator note — Token trimming (before pasting into prompt):**
For file inputs with 200+ lines, trim the document before including it in the prompt:
1. Keep FULL content for sections in the agent's focus area
2. Keep Summary, Goals, Non-Goals in full (if present)
3. For ALL OTHER sections: replace with: "## [Section Name] — [1-sentence summary]"
4. For repo reviews: include README + build files + 2-3 key source files only
Target: ~50% of original document. The agent should not see the trimming instructions.
```

Inside the prompt template, the "Document to Review" section becomes simply:

```
## Document to Review

[Trimmed document content — orchestrator applies token optimization above]

[For repo reviews: README + key structural info from Step 1.0]
```

**Step 2: Commit**

```bash
git add skills/flux-drive/phases/launch.md
git commit -m "fix(flux-drive): move token trimming to orchestrator instructions, out of agent prompt

The Token Optimization block was ambiguous — agents received it but
can't trim a document they're already receiving. Trimming is the
orchestrator's job before constructing the prompt.

Closes Clavain-uyt"
```

---

### Task 3: Reconcile tier naming (Clavain-dxp, P2)

**Problem:** "Tier 1" agents run on sonnet (cheaper), "Tier 3" adaptive agents run on opus (inherit). The numbering implies Tier 1 > Tier 3, but capability is reversed. Synthesis also incorrectly prefers Tier 1/2 over Tier 3.

**Files:**
- Modify: `skills/flux-drive/SKILL.md` (Agent Roster section, scoring rules, scoring examples)
- Modify: `skills/flux-drive/phases/synthesize.md` (dedup preference rule)
- Modify: `skills/flux-drive/phases/launch.md` (tier references in prompt template)
- Modify: `skills/flux-drive/phases/launch-codex.md` (tier references)

**Step 1: Rename tiers in SKILL.md Agent Roster**

Replace the current tier headings:

| Old | New | Rationale |
|-----|-----|-----------|
| Tier 1 — Codebase-Aware | Domain Specialists | They're domain-specific (UX, code quality), always codebase-aware |
| Tier 2 — Project-Specific | Project Agents | User-created per-project agents |
| Tier 3 — Adaptive Specialists | Adaptive Reviewers | They adapt based on project docs presence |
| Tier 4 — Cross-AI | Cross-AI (Oracle) | Unchanged |

Update the scoring rules:
- Remove "Tier bonuses" language that references Tier 1/2/3 numbers
- Replace with: "Domain Specialists get +1 (always codebase-aware). Project Agents get +1 (project-specific). Adaptive Reviewers with architecture-strategist, security-sentinel, or performance-oracle get +1 when the target project has CLAUDE.md/AGENTS.md."
- Dedup rule: "If a Domain Specialist or Project Agent covers the same domain as an Adaptive Reviewer, prefer the more specific agent"

Update scoring examples to use new names.

**Step 2: Update synthesis dedup preference**

In `phases/synthesize.md`, Step 3.3 item 2 currently says:
> "keep the most specific one (prefer Tier 1/2 over Tier 3)"

Replace with:
> "keep the most specific one (prefer Domain Specialists and Project Agents over Adaptive Reviewers, since they have deeper project context)"

Step 3.3 item 5 currently says:
> "When a Tier 1/2 and Tier 3 agent give different advice..."

Replace with:
> "When a Domain Specialist/Project Agent and an Adaptive Reviewer give different advice on the same topic, prefer the more project-specific recommendation"

**Step 3: Update launch.md tier references**

In the prompt template, the frontmatter `tier:` field currently uses `{1|2|3}`. Keep the numeric tiers in frontmatter for backward compatibility but add a comment:

```
tier: {domain|project|adaptive|cross-ai}
```

Update the "How to launch each agent type" section headings to use new names.

**Step 4: Update launch-codex.md references**

Replace "Tier 2 bootstrap" heading and "Tier 2 agents" references with "Project Agent bootstrap" and "Project Agents".

**Step 5: Update Phase 1 triage table (SKILL.md)**

In Step 1.2, update scoring examples to use new tier names instead of T1/T2/T3.

In Step 1.3, update the AskUserQuestion: change "M codebase-aware, K adaptive" to "M domain specialists, K adaptive reviewers".

**Step 6: Commit**

```bash
git add skills/flux-drive/SKILL.md skills/flux-drive/phases/synthesize.md skills/flux-drive/phases/launch.md skills/flux-drive/phases/launch-codex.md
git commit -m "refactor(flux-drive): rename tiers to Domain Specialists / Adaptive Reviewers

Tier 1/2/3 numbering was misleading — 'Tier 1' (sonnet) was less capable
than 'Tier 3' (opus, adaptive). New names describe function, not rank:
Domain Specialists, Project Agents, Adaptive Reviewers, Cross-AI.

Closes Clavain-dxp"
```

---

### Task 4: Add Task dispatch retry/error handling (Clavain-ko8, P2)

**Problem:** Codex dispatch has retry logic but the default Task dispatch path has none.

**Files:**
- Modify: `skills/flux-drive/phases/launch.md` (add retry section after dispatch)
- Modify: `skills/flux-drive/phases/synthesize.md` (add missing-agent handling)

**Step 1: Add error handling to launch.md**

After the "After launching all agents" block at the end of launch.md, add:

```markdown
### Step 2.3: Verify agent completion

After all background tasks complete (check via TaskOutput or output file existence):

1. List `{OUTPUT_DIR}/` — expect one `.md` file per launched agent
2. For any missing file after 5 minutes:
   a. Check the background task output for errors
   b. **Retry once**: Re-launch the agent with the same prompt (not in background this time — use `run_in_background: false` so you get direct output)
   c. If retry produces output, write it to `{OUTPUT_DIR}/{agent-name}.md`
   d. If retry also fails, create a stub file:
      ```
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
```

**Step 2: Update synthesize.md to handle error verdicts**

In Step 3.1, add to the classification:
- **Error**: File exists with `verdict: error` — note as "agent failed" in summary, don't count toward convergence

**Step 3: Commit**

```bash
git add skills/flux-drive/phases/launch.md skills/flux-drive/phases/synthesize.md
git commit -m "feat(flux-drive): add retry/error handling for Task-dispatched agents

Mirrors the Codex dispatch path's retry logic. Failed agents get one
retry (non-background), then a stub file with verdict: error so
synthesis can report the failure cleanly.

Closes Clavain-ko8"
```

---

### Task 5: Fix Oracle timeout inconsistency (Clavain-kto, P3)

**Problem:** SKILL.md says `timeout 300` (5 min), launch.md says `timeout: 600000` (10 min).

**Files:**
- Modify: `skills/flux-drive/SKILL.md` (Oracle bash example in roster)

**Step 1: Align timeouts**

The `timeout: 600000` in launch.md is for the Bash tool's timeout parameter (10 minutes for the whole Bash call including Oracle startup). The `timeout 300` in the Oracle bash command is for the `timeout` Unix command wrapping just the Oracle process.

These are actually different things — the Bash tool timeout is the outer boundary, the Unix timeout is the inner kill. But 5 min inner + overhead should fit in 10 min outer. The issue is that Oracle can legitimately take 5+ minutes for complex reviews.

Change the Oracle bash example in SKILL.md from `timeout 300` to `timeout 480` (8 min) — leaves 2 min headroom within the 10-min Bash tool timeout:

```bash
timeout 480 env DISPLAY=:99 CHROME_PATH=/usr/local/bin/google-chrome-wrapper \
  oracle --wait -p "..." -f "..." > {OUTPUT_DIR}/oracle-council.md 2>&1 || ...
```

**Step 2: Commit**

```bash
git add skills/flux-drive/SKILL.md
git commit -m "fix(flux-drive): align Oracle timeout to 480s (8min inner, 10min outer)

The Unix timeout (300s) and Bash tool timeout (600s) were inconsistent.
Set inner to 480s, leaving 2min headroom within the 10min outer boundary.

Closes Clavain-kto"
```

---

## Execution Order

Tasks 1 and 2 both modify `phases/launch.md` — run sequentially (Task 1 first since Task 2 depends on the restructured template).

Task 3 modifies SKILL.md + all phase files — run after Tasks 1-2 to avoid merge conflicts.

Tasks 4 and 5 touch different parts of launch.md and SKILL.md respectively — can run after Task 3.

**Recommended order:** Task 1 → Task 2 → Task 3 → Task 4 → Task 5

All tasks are markdown-only — no tests, no builds, just careful editing and reading back to verify.
