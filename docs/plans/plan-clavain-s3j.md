# Plan: Clavain-s3j — Implement incremental depth: launch top agents first, expand on demand

## Context
Currently flux-drive launches ALL selected agents simultaneously in Phase 2. For clean/simple documents where top agents find nothing concerning, this wastes 50%+ of agent tokens. This feature implements a two-stage dispatch: launch the top 2-3 agents first, evaluate results, then decide whether to launch the rest.

## Current State
- Phase 1 (SKILL.md) triage scores all agents, selects up to 8
- Phase 2 (launch.md) dispatches all selected agents at once with `run_in_background: true`
- Phase 3 (synthesize.md) collects all results and synthesizes
- No mechanism for staged dispatch or early stopping

## Implementation Plan

### Step 1: Add Stage 1/Stage 2 dispatch to launch.md
**File:** `skills/flux-drive/phases/launch.md`

Replace the single-dispatch model in Step 2.2 with staged dispatch:

**Step 2.2a: Stage 1 — Top agents (blocking)**
1. From the triage-selected agents, take the top 2-3 by score (ties broken by: Project > Adaptive > Cross-AI)
2. Launch these agents with `run_in_background: true`
3. Wait for Stage 1 agents to complete (use the polling pattern from Clavain-690 if available, otherwise file-check loop)
4. Read Stage 1 results — parse YAML frontmatter only (frontmatter-first approach)

**Step 2.2b: Expansion decision**
Based on Stage 1 findings, decide:

| Stage 1 Result | Action |
|---|---|
| Any P0 issue found | Launch ALL remaining agents (need convergence data) |
| P1 issues found, multiple agents agree | Launch remaining agents for coverage |
| P1 issues but only one agent flagged | Launch 1-2 targeted agents in the flagged domain |
| Only P2/improvements or clean | **Stop early** — Stage 1 is sufficient |
| Agents disagree on a key point | Launch a tiebreaker agent in the disputed domain |

Present the expansion decision to user via AskUserQuestion:
```
Stage 1 complete: [brief summary of findings]
Options:
- "Launch remaining N agents (Recommended)" / "Stop here — findings are sufficient" / "Launch specific agents: [list]"
```

**Step 2.2c: Stage 2 — Remaining agents (if expanded)**
1. Launch remaining selected agents with `run_in_background: true`
2. Wait for completion (same polling as Stage 1)

### Step 2: Update launch-codex.md for staged dispatch
**File:** `skills/flux-drive/phases/launch-codex.md`

Same two-stage model but using Codex dispatch:
- Stage 1: Dispatch top 2-3 agents, wait for completion
- Expansion decision: Same logic
- Stage 2: Dispatch remaining if needed

### Step 3: Update synthesize.md for partial agent sets
**File:** `skills/flux-drive/phases/synthesize.md`

Handle the case where only Stage 1 agents ran:
- Convergence counting adjusts for smaller N (e.g., "2/2 agents" instead of "2/6")
- Summary notes: "Early stop: N agents sufficient, M agents skipped"
- No quality loss — the decision to stop was informed by actual findings

### Step 4: Update SKILL.md triage output
**File:** `skills/flux-drive/SKILL.md`

Modify Step 1.2 output to include stage assignment:
- Triage table gets a "Stage" column: `1` for top agents, `2` for the rest
- Step 1.3 user confirmation shows stages: "Stage 1: [agents], Stage 2 (on-demand): [agents]"

## Design Decisions
- **2-3 top agents in Stage 1**: Enough for convergence signal without over-committing. If they find nothing, we're confident it's clean.
- **User confirmation for expansion**: The user might know the document well enough to skip Stage 2 even with P1 findings. Let them decide.
- **Frontmatter-first for Stage 1 evaluation**: Parse YAML frontmatter only to make the expansion decision fast — no need to read full prose at this point.
- **Score-based staging**: Natural — highest-scoring agents are most domain-relevant, best positioned to find real issues.
- **Tiebreaker agent**: If Stage 1 agents disagree, a third opinion is more valuable than bulk dispatch.

## Files Changed
1. `skills/flux-drive/phases/launch.md` — Major restructure: two-stage dispatch, expansion logic
2. `skills/flux-drive/phases/launch-codex.md` — Same two-stage pattern for Codex
3. `skills/flux-drive/phases/synthesize.md` — Handle partial agent sets, adjusted convergence
4. `skills/flux-drive/SKILL.md` — Stage column in triage table, updated Phase 2 description

## Estimated Scope
~60-80 lines of new/modified instructional content. Largest change is in launch.md.

## Risk
- **Quality regression**: If Stage 1 agents miss something that a Stage 2 agent would catch. Mitigated by: user confirmation before early stop, and P0/P1 always triggers expansion.
- **Complexity**: Staged dispatch adds decision points. Mitigated by: clear decision table, user always has override.

## Acceptance Criteria
- [ ] Triage table includes Stage 1/Stage 2 assignment
- [ ] Stage 1 launches top 2-3 agents and waits for results
- [ ] Expansion decision is based on Stage 1 finding severity
- [ ] User is asked before stopping early or expanding
- [ ] Synthesize handles partial agent sets correctly
- [ ] Early stop is reported in final summary
- [ ] Works for both Task and Codex dispatch modes
