# Plan: Clavain-m2v — Fix scoring: category bonus should not elevate base-0 agents

## Context
Bug in Step 1.2 scoring: category bonus (+1 for Project/Plugin Agents) can turn a base score of 0 into 1, causing irrelevant agents to pass the "include if thin section" rule. A security reviewer scoring 0 (wrong domain) + 1 (project docs exist) = 1 should NOT be included just because a section is thin.

## Changes

### 1. `skills/flux-drive/SKILL.md` — Fix scoring rules
- Add explicit rule: "Category bonuses apply only to agents with base score ≥ 1"
- Or equivalently: "An agent with base score 0 is always excluded regardless of bonuses"
- Update the scoring table description near line 119 to make this clear
- Update scoring examples if any show 0+1=1 → Launch (they should show Skip)

### 2. Check scoring examples
- Review the three scoring examples (Go API, Python CLI, PRD) to ensure none demonstrate a 0+bonus=launch pattern
- If any do, fix them

## Acceptance Criteria
- Scoring rules explicitly state base-0 agents cannot be elevated by bonuses
- No scoring example shows a 0+bonus agent being launched
- The "0 (irrelevant)" definition is clear that bonus doesn't change this
