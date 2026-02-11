# Plan: Add lightweight document-review (Clavain-c9gv)

## Goal
Add a quick single-pass document refinement command that sits between `/brainstorm` and `/strategy` — cheaper and faster than flux-drive.

## Context
- Upstream compound-engineering has a document-review skill (assess → evaluate → simplify → fix)
- Clavain has flux-drive for comprehensive multi-agent review but nothing lightweight
- Positioned as "quick polish" vs flux-drive's "comprehensive gates"

## Steps

### Step 1: Create `commands/review-doc.md`
Lightweight document review command:

1. Read the document (brainstorm output, PRD, plan, or any markdown)
2. **Assess** — identify unclear, unnecessary, or missing sections
3. **Score** — rate Clarity / Completeness / Specificity / YAGNI (1-5 each)
4. **Identify** the single most critical issue to address
5. **Fix** — auto-fix minor issues (grammar, structure), ask approval for substantive changes
6. **Offer**: refine again (max 2 rounds) or proceed to next workflow step

Add `disable-model-invocation: true` (manual workflow command).

### Step 2: Update /lfg to mention review-doc as optional step
In `commands/lfg.md`, after brainstorm step, add note: "Optionally run `/review-doc` to polish brainstorm output before `/strategy`."

### Step 3: Update counts (→30 commands after triage-prs)
Update: CLAUDE.md, AGENTS.md, README.md, plugin.json, test_commands.py

### Step 4: Run tests and commit
Commit message: `feat: add /review-doc command for lightweight document refinement`

## Verification
- Quick review of a brainstorm doc should take <30 seconds (single pass, no subagents)
- Should NOT trigger fd-* agents (that's flux-drive's job)
