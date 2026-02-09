# Tier 4 Beads Polish Issues — Creation Log

> Created: 2026-02-09
> Context: Post-flux-drive polish pass — low-priority bugs and tasks identified during agent roster and scoring review.

## Summary

Six beads issues created for Clavain covering tier vocabulary fixes, agent categorization, roster validation tooling, scoring edge cases, and minor SKILL.md / interpeer UX improvements. Three are bugs (P3), one is a P3 task, and two are P4 tasks.

## Issues Created

### 1. Clavain-th4 — Fix tier vocabulary (P3, bug)
- **Title:** Fix tier vocabulary: remove unused 'domain' tier, standardize across files
- **Rationale:** The "domain" tier label appears in some files but is not used in the current 3-layer routing (Stage → Domain → Language). This creates confusion between "domain" as a routing layer and "domain" as a tier label. The fix is to audit all files referencing tier names and remove or replace the unused "domain" tier.

### 2. Clavain-4q1 — Fix spec-flow-analyzer categorization (P3, bug)
- **Title:** Move spec-flow-analyzer to own sub-table or rename Adaptive Reviewers table
- **Rationale:** `spec-flow-analyzer` is listed under Adaptive Reviewers but is not a reviewer — it is a research/analysis agent. Either it needs its own sub-table or the table heading needs to be broadened to "Adaptive Agents" to accurately reflect its contents.

### 3. Clavain-16r — Add roster validation script (P3, task)
- **Title:** Add scripts/validate-roster.sh to check roster-to-file correspondence
- **Rationale:** Currently there is no automated check that every agent listed in the roster YAML/tables has a corresponding `.md` file, and vice versa. A validation script would catch orphaned files and missing roster entries during CI or manual checks.

### 4. Clavain-m2v — Fix scoring category bonus (P3, bug)
- **Title:** Fix scoring: category bonus should not elevate base-0 agents
- **Rationale:** The current scoring logic can add a category bonus to agents with a base relevance score of 0, causing irrelevant agents to appear in results. The fix is to guard the category bonus so it only applies when base score > 0.

### 5. Clavain-f0m — Add Phase 4 skip gate (P4, task)
- **Title:** Add explicit Phase 4 skip condition in SKILL.md before file read
- **Rationale:** Phase 4 (cross-AI classification) should be skippable when no relevant findings exist, but the current SKILL.md does not have an explicit skip condition before initiating file reads. Adding a gate saves unnecessary file I/O and context consumption.

### 6. Clavain-c6m — Add interpeer description (P4, task)
- **Title:** Add 1-sentence description to interpeer quick mode suggestion in Step 4.1
- **Rationale:** When the skill suggests running interpeer in quick mode (Step 4.1), there is no description of what that mode does. A single sentence explaining the purpose would help users make an informed decision about whether to accept the suggestion.

## Verification

All six issues confirmed present via `bd list`. They appear at the bottom of the backlog at P3 and P4 priority, below the existing P0–P2 items.

### Current Backlog Snapshot (P3–P4 only)

| ID | Priority | Type | Title |
|----|----------|------|-------|
| Clavain-m2v | P3 | bug | Fix scoring: category bonus should not elevate base-0 agents |
| Clavain-16r | P3 | task | Add scripts/validate-roster.sh to check roster-to-file correspondence |
| Clavain-4q1 | P3 | bug | Move spec-flow-analyzer to own sub-table or rename Adaptive Reviewers table |
| Clavain-th4 | P3 | bug | Fix tier vocabulary: remove unused 'domain' tier, standardize across files |
| Clavain-c6m | P4 | task | Add 1-sentence description to interpeer quick mode suggestion in Step 4.1 |
| Clavain-f0m | P4 | task | Add explicit Phase 4 skip condition in SKILL.md before file read |
