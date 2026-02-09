---
agent: fd-code-quality
tier: domain
issues:
  - id: P1-1
    severity: P1
    section: "Task 3: Reconcile tier naming"
    title: "launch-codex.md TIER field still uses {1|2|3} — not updated to new tier names"
  - id: P1-2
    severity: P1
    section: "Task 3: Reconcile tier naming"
    title: "cross-ai.md not listed in Task 3 files but contains 'Tier 4' references needing rename"
  - id: P2-1
    severity: P2
    section: "Task 3: Reconcile tier naming"
    title: "SKILL.md line 200 heading 'Tier 4 — Cross-AI (Oracle)' inconsistent with new naming scheme"
  - id: P2-2
    severity: P2
    section: "Task 3: Reconcile tier naming"
    title: "launch.md line 159 still says 'codebase-aware agents' — old terminology in a parenthetical"
  - id: P2-3
    severity: P2
    section: "Task 3: Reconcile tier naming"
    title: "launch-codex.md line 97 references 'Tier 4 (Oracle)' — should use new naming"
improvements:
  - id: IMP-1
    title: "Plan should explicitly list all 5 flux-drive files (add cross-ai.md to Task 3 scope)"
    section: "Task 3: Reconcile tier naming"
  - id: IMP-2
    title: "Plan's old/new tier table should include Tier 4 rename to 'Cross-AI (Oracle)' without the 'Tier 4' prefix"
    section: "Task 3: Reconcile tier naming"
  - id: IMP-3
    title: "Add a grep-based verification step to Task 3 commit to catch stale tier references"
    section: "Task 3: Reconcile tier naming"
verdict: needs-changes
---

### Summary (3-5 lines)

The plan's tier rename (Task 3) has been partially executed: SKILL.md, launch.md, and synthesize.md already use the new names (Domain Specialists, Project Agents, Adaptive Reviewers). However, two files were missed or incompletely updated: `launch-codex.md` still uses `{1|2|3}` for the TIER field on line 74, and `cross-ai.md` is not even listed in Task 3's file scope despite containing "Tier 4" references on line 7. Additionally, SKILL.md retains the heading "Tier 4 -- Cross-AI (Oracle)" at line 200 and `launch.md` line 159 still uses the phrase "codebase-aware agents" which was the old Tier 1 label. The inconsistency between the Codex dispatch path (`{1|2|3}`) and the Task dispatch path (`{domain|project|adaptive|cross-ai}`) means synthesize.md will encounter mixed tier values in agent output frontmatter.

### Issues Found

**P1-1: launch-codex.md TIER field still uses numeric tiers**
- File: `/root/projects/Clavain/skills/flux-drive/phases/launch-codex.md`, line 74
- Current value: `{1|2|3}`
- launch.md line 82 uses: `{domain|project|adaptive|cross-ai}`
- Impact: Agents dispatched via Codex will write `tier: 1` in frontmatter while Task-dispatched agents write `tier: domain`. Synthesis (Step 3.1) parses the `tier` field -- mixed values will cause dedup logic and convergence counting to fail silently. This is a data contract inconsistency between two dispatch paths feeding the same synthesis pipeline.
- Fix: Change line 74 of launch-codex.md from `{1|2|3}` to `{domain|project|adaptive|cross-ai}` to match launch.md.

**P1-2: cross-ai.md omitted from Task 3 file scope**
- File: `/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md`, line 7
- Contains: `If Oracle (Tier 4) was **not** in the roster`
- The plan's Task 3 lists exactly 4 files: SKILL.md, synthesize.md, launch.md, launch-codex.md. It omits `phases/cross-ai.md` entirely, even though Phase 4 references "Tier 4" which should either stay as-is (if Tier 4 is kept for Oracle) or be renamed to "Cross-AI" (if the rename is comprehensive).
- Fix: Add `phases/cross-ai.md` to Task 3's file list. Change line 7 from "Oracle (Tier 4)" to "Oracle (Cross-AI)" or simply "Oracle" to match the pattern in the rest of the roster where "Cross-AI (Oracle)" is the heading style.

**P2-1: SKILL.md "Tier 4" heading inconsistency**
- File: `/root/projects/Clavain/skills/flux-drive/SKILL.md`, line 200
- The heading `### Tier 4 -- Cross-AI (Oracle)` is the only remaining "Tier N" heading. The other three tiers were renamed to remove numeric prefixes (Domain Specialists, Project Agents, Adaptive Reviewers). Line 206 also says "skip Tier 4 entirely."
- The plan's rename table says Tier 4 becomes "Cross-AI (Oracle)" -- but the plan does not call out removing the "Tier 4 --" prefix from the heading, leaving it as the sole survivor of the old scheme.
- Fix: Rename to `### Cross-AI (Oracle)` and change line 206 to "skip Cross-AI entirely" for consistency.

**P2-2: launch.md "codebase-aware agents" residual old terminology**
- File: `/root/projects/Clavain/skills/flux-drive/phases/launch.md`, line 159
- Text: "codebase-aware agents take longer as they explore the repo"
- The old Tier 1 was called "Codebase-Aware." While "codebase-aware" is still a meaningful adjective, using it as a category label in the same sentence structure as the old tier names creates ambiguity. The plan's Task 3 does not call out this line.
- Fix: Change to "Domain Specialists take longer as they explore the repo" for consistency with the renamed categories.

**P2-3: launch-codex.md "Tier 4 (Oracle)" reference**
- File: `/root/projects/Clavain/skills/flux-drive/phases/launch-codex.md`, line 97
- Text: `**Tier 4 (Oracle)**: Unchanged`
- Same residual numbering as P2-1.
- Fix: Change to `**Cross-AI (Oracle)**: Unchanged`

### Improvements Suggested

**IMP-1: Expand Task 3 file scope to include cross-ai.md**
The plan lists 4 files for Task 3 but there are 5 files in the flux-drive phases directory. A systematic approach would be to grep all files under `skills/flux-drive/` for any `Tier` references and update them all. The plan should add:
```
- Modify: `skills/flux-drive/phases/cross-ai.md` (Tier 4 reference)
```

**IMP-2: Clarify the Tier 4 rename in the plan's mapping table**
The plan's table says `Tier 4 -- Cross-AI | Cross-AI (Oracle) | Unchanged`. But "unchanged" is misleading -- the heading in SKILL.md still says "Tier 4 --" which is the OLD format. The table should clarify that the "Tier N --" prefix is being dropped from ALL headings, including Tier 4. Suggested table row:
```
| Tier 4 — Cross-AI (Oracle) | Cross-AI (Oracle) | Drop numeric prefix for consistency |
```

**IMP-3: Add a post-commit verification grep to Task 3**
After the Task 3 commit, the plan should include a verification step:
```bash
grep -rn 'Tier [1234]' skills/flux-drive/ && echo "FAIL: stale tier references remain" || echo "PASS: all tier references updated"
```
This would have caught P1-1, P2-1, and P2-3 before commit. The Clavain AGENTS.md validation checklist pattern (which already includes `grep -r 'superpowers:'` checks for dropped namespaces) supports this approach -- the same pattern should apply to dropped tier naming.

### Overall Assessment

The plan's tier rename is mostly sound in concept and largely executed, but it has 2 P1 gaps (one data contract inconsistency between dispatch paths, one missed file) and 3 P2 residual naming inconsistencies that undermine the stated goal of eliminating the misleading numeric tier scheme. Adding `cross-ai.md` to scope and a post-commit grep would close all gaps.
