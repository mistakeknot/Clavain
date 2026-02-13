# Document Review Integration Plan

**Date:** 2026-02-11  
**Status:** Research & Planning  
**Context:** Analyzing upstream compound-engineering's document-review skill for lightweight integration into Clavain's workflow.

---

## Executive Summary

The upstream document-review skill provides a **structured refinement process** (5 steps: Get → Assess → Evaluate → Identify Critical Issue → Make Changes). Clavain should integrate this as a **new optional command** (`/clavain:review-doc`) that sits between `/brainstorm` and `/strategy`, allowing users to refine brainstorm output before committing to a PRD. The skill is lightweight and requires minimal customization—drop unneeded complexity, keep the core assess/evaluate/simplify logic.

---

## Upstream Skill Analysis

### What Does document-review Do?

The upstream skill refines **brainstorm or plan documents** through six structured steps:

1. **Get the Document** — Locate or read the document (with fallback to recent files in `docs/brainstorms/` or `docs/plans/`)
2. **Assess** — Surface clarity issues via five diagnostic questions:
   - What is unclear?
   - What is unnecessary?
   - What decision is being avoided?
   - What assumptions are unstated?
   - Where could scope accidentally expand?
3. **Evaluate** — Score against four criteria:
   - **Clarity** — No vague language ("probably," "consider," "try to")
   - **Completeness** — Required sections present, constraints/open questions flagged
   - **Specificity** — Concrete enough for next step (brainstorm → can plan, plan → can implement)
   - **YAGNI** — No hypothetical features, simplest approach chosen
   - *Bonus (in workflow context):* User intent fidelity
4. **Identify Critical Improvement** — Highlight the single highest-impact issue
5. **Make Changes** — Auto-fix minor issues, request approval for substantive changes, update inline
6. **Offer Next Action** — Ask refine-again or review-complete; limit to 2 passes

### Key Design Philosophy

- **Non-rewriting** — Fixes clarity and structure, does NOT rewrite entire sections
- **Purposeful simplification** — Removes hypothetical complexity, but preserves constraints/rationale/open questions
- **Iterative** — Allows refinement passes but caps at 2 (diminishing returns)
- **Inline updates** — No separate files or metadata sections

---

## Clavain's Workflow Context

### Current Flow

```
brainstorm (WHAT) → strategy (PRD + beads) → write-plan (HOW) → flux-drive (validation)
```

**Phases in each command:**

**`/brainstorm`** (3 phases):
- Phase 1: Understand the idea (research + dialogue)
- Phase 2: Explore approaches (2-3 options + recommendation)
- Phase 3: Capture design (write brainstorm doc)
- Phase 4: Handoff (offer proceed to `/strategy`)

**`/strategy`** (5 phases):
- Phase 1: Extract features
- Phase 2: Write PRD
- Phase 3: Create beads
- Phase 4: Validate (run `/flux-drive` on PRD)
- Phase 5: Handoff (offer proceed to `/write-plan`)

**`/flux-drive`** (multi-phase):
- Reviews documents or repos with **multi-agent analysis** (9 agents, selective roster)
- Detects file vs. directory, outputs to `docs/research/flux-drive/{INPUT_STEM}/`

**`/write-plan`** (not shown, but follows strategy):
- Detailed implementation planning for selected features

---

## Recommended Integration: `/clavain:review-doc`

### Where It Fits

Insert **between `/brainstorm` and `/strategy`**:

```
brainstorm (raw capture) 
    → review-doc (OPTIONAL refinement) 
    → strategy (structured PRD) 
    → write-plan (implementation planning)
    → flux-drive (multi-agent validation)
```

**Rationale:**
- **Brainstorm output is often exploratory** — good raw material, but may have unclear sections, unstated assumptions, or accidental scope creep
- **Strategy expects a clean input** — PRD phase needs clarity to extract features accurately
- **Review-doc sits ideally in between** — user can optionally refine brainstorm before committing to PRD structure
- **Users skip it if not needed** — lightweight handoff from `/brainstorm` suggests optional review

### Should It Be a Skill, Command, or Option?

**Recommendation: New command `/clavain:review-doc`**

**Why not a skill?**
- Skills are embedded in workflow or user context (e.g., `brainstorming` is embedded in `/brainstorm`'s Phase 1 dialogue)
- Review-doc is a **standalone workflow** (user initiates it independently, returns control cleanly)

**Why not an option within an existing command?**
- `/brainstorm` already has 4 phases (understand → explore → capture → handoff); adding review would bloat it
- `/strategy` is designed to ingest brainstorm output; review should happen *before* strategy, not within it
- Cleaner separation of concerns: one command = one responsibility

**Command signature:**
```
/clavain:review-doc [document-path-or-description]
```

**Argument resolution:**
1. If path provided → read it
2. If no path → check `docs/brainstorms/` for most recent
3. If no brainstorm exists → ask user which document to review

---

## What to Keep vs. Drop

### Keep (Core Refinement Logic)

✅ **Assess phase** — Five diagnostic questions surface real issues  
✅ **Evaluate phase** — Four-criterion scoring (Clarity, Completeness, Specificity, YAGNI)  
✅ **Identify Critical Improvement** — Highlights single highest-impact issue  
✅ **Make Changes logic** — Auto-fix minor, ask approval for substantive  
✅ **Iteration cap** — Limit to 2 passes, then recommend completion  
✅ **Simplification guidance** — Clear rules on what to simplify vs. preserve  

### Drop (Upstream Bloat)

❌ **Separate "plan document" branch** — Clavain doesn't need review-doc to work on plans in the same way (plans are output by `/write-plan`, which is later in workflow). Focus on **brainstorm review only** for v1.

❌ **Metadata sections** — The upstream skill warns against separate review files or metadata. Clavain's approach: **update the original brainstorm inline, no separate artifacts**.

❌ **Complex auto-detection logic** — Upstream checks for workflow context ("if invoked within a workflow after /workflows:brainstorm or /workflows:plan"). Clavain is simpler: assume this is always called **after `/brainstorm`**, so just refine the brainstorm doc.

### Customizations

1. **Namespace** — Use `/clavain:review-doc`, not `/compound-engineering:document-review`
2. **Description** — Focus on **brainstorm refinement** (not plan review), positioned as pre-strategy optional step
3. **Output** — Updated brainstorm doc + summary of changes + option to refine again or proceed to strategy
4. **Success criteria** — "Document is ready for strategy phase" (i.e., clear features, no unstated assumptions, reasonable scope)

---

## Implementation Roadmap

### Phase 1: Create Skill (`/root/projects/Clavain/skills/review-doc/SKILL.md`)

Adapt upstream SKILL.md:
- Remove plan-document branch (brainstorm-only focus)
- Simplify "Get Document" logic (assume brainstorm path)
- Keep Assess/Evaluate/Identify/Make Changes/Next Action steps
- Add context about workflow position (between brainstorm and strategy)

### Phase 2: Create Command (`/root/projects/Clavain/commands/review-doc.md`)

Structure mirrors `/brainstorm` and `/strategy`:
- **Input handling** — Argument resolution (file path, recent brainstorm, ask user)
- **Embed skill content** — Via SessionStart hook `additionalContext` (like `/brainstorm` embeds `brainstorming` skill)
- **Execution** — Follow 6 steps from SKILL.md inline
- **Handoff** — Offer three options:
  1. Refine again (iterative loop)
  2. Review complete (proceed to `/strategy`)
  3. Cancel (return later)

### Phase 3: Testing

- **Smoke test** — Review a sample brainstorm, verify clarity/completeness scoring works
- **Edge cases** — No document found, user cancels after 1st pass, 2-pass limit enforced
- **Integration** — Call review-doc from `/brainstorm` handoff as optional next step

### Phase 4: Documentation

- Update workflow diagram in main README (add review-doc between brainstorm and strategy)
- Link from `/brainstorm` handoff to `/review-doc` command
- Note: optional step, not required

---

## Sample Review-Doc Command Structure

```markdown
---
name: review-doc
description: Refine brainstorm documents for clarity before moving to strategy phase
argument-hint: "[brainstorm doc path, or leave empty to use most recent]"
---

# Review Document

Improve brainstorm documents through structured assessment and refinement.

## Input Resolution

[Argument resolution logic: file path → recent brainstorm → ask user]

## Phase 1: Assess

[Five diagnostic questions]

## Phase 2: Evaluate

[Four-criterion scoring table]

## Phase 3: Identify Critical Issue

[Highlight single highest-impact finding]

## Phase 4: Make Changes

[Auto-fix minor issues, ask approval for substantive changes]

## Phase 5: Offer Next Action

[Refine again / Review complete / Cancel]

---

**Examples & Tips**
[Brief best practices for reviewing brainstorms]
```

---

## Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| Users skip review-doc, miss clarity issues | Offer it in `/brainstorm` handoff; make it optional but visible |
| Review-doc becomes bloat (unused skill) | Monitor early adoption; consider removing if <10% of brainstorms reviewed |
| Scope creep in review iterations | Hard cap at 2 passes; recommend completion after 2nd pass |
| Conflicts between review-doc and flux-drive | Separate concerns: review-doc = structural clarity, flux-drive = multi-agent design validation |

---

## Approval Checklist

- [ ] Skill created and tested (review-doc/SKILL.md)
- [ ] Command created and tested (commands/review-doc.md)
- [ ] SessionStart hook updated (embed review-doc skill via additionalContext)
- [ ] Integration with `/brainstorm` handoff tested
- [ ] Documentation updated (README, workflow diagram)
- [ ] Smoke tests pass (3+ test cases)
- [ ] Version bumped and published

---

## References

- **Upstream:** `/root/projects/upstreams/compound-engineering/plugins/compound-engineering/skills/document-review/SKILL.md`
- **Clavain brainstorm:** `/root/projects/Clavain/commands/brainstorm.md`
- **Clavain strategy:** `/root/projects/Clavain/commands/strategy.md`
- **Clavain flux-drive:** `/root/projects/Clavain/skills/flux-drive/SKILL.md` (Phase 1, lines 1-50)
