# Formalize Interactive-to-Autonomous Shift-Work Boundary

**Bead:** Clavain-xweh (P2)
**Inspired by:** StrongDM Software Factory — [Shift Work](https://factory.strongdm.ai/techniques/shift-work)

## Problem

Clavain's `/lfg` workflow already separates interactive work (brainstorm, strategy, plan, review) from autonomous work (execute, test, quality-gates, resolve, ship). But the boundary is **implicit** — there's no explicit signal that says "spec is complete, switching to autonomous mode."

StrongDM's insight: when specs + tests are fully defined, an agent can run end-to-end without back-and-forth. Their tool (Attractor) operates on this principle. Our current workflow has the same structure but doesn't leverage it — the executing-plans skill still runs in the same interactive mode as brainstorming.

### What "Shift Work" Means for Us

| Phase | Mode | Current Behavior | Ideal Behavior |
|-------|------|-----------------|----------------|
| Steps 1-4 (brainstorm → flux-drive) | Interactive | User iterates with agent, approves plan | Same |
| **Boundary** | Shift | Nothing happens | Explicit completeness check + mode switch |
| Steps 5-9 (execute → ship) | Autonomous | Agent asks for batch approval, waits for feedback | Agent runs with minimal interruption, reports at end |

## Design

### The Spec Completeness Signal

Before transitioning from interactive to autonomous mode, verify:

```markdown
## Spec Completeness Checklist
- [ ] Plan file exists and has been approved (flux-drive verdict: safe or needs-changes with fixes applied)
- [ ] Acceptance criteria defined (explicit "done when" statements in plan)
- [ ] Test strategy specified (which tests to run, what constitutes passing)
- [ ] Dependencies identified (external services, other features, blocking issues)
- [ ] Scope bounded (explicit "not in scope" list prevents scope creep)
```

If all checked → suggest autonomous mode. If any unchecked → stay interactive, surface what's missing.

### Option A: Add Shift Boundary to lfg.md (Recommended)

Add between Step 4 (flux-drive) and Step 4.5 (learnings):

```markdown
## Step 4a: Spec Completeness Gate

Before switching to autonomous execution, verify the spec is complete:

1. Check plan file for:
   - Acceptance criteria (search for "done when", "acceptance", "success criteria")
   - Test strategy (search for "test", "verify", "validate")
   - Scope boundary (search for "not in scope", "out of scope", "deferred")
2. If any are missing, ask the user:
   - "Plan is missing [X]. Add it before autonomous execution, or proceed anyway?"
3. If all present (or user says proceed):
   - Print: "📋 Spec complete. Switching to autonomous execution mode."
   - Set execution mode: autonomous (fewer checkpoints, batch reports at end)

**In autonomous mode:**
- executing-plans runs with batch size = ALL (not 3)
- No per-batch approval — report at end
- Still stops on blockers (test failures, missing dependencies)
- Still runs quality-gates before shipping
```

### Option B: Formalize in using-clavain Skill

Document the shift-work pattern as a general principle in the `using-clavain` skill, not specific to lfg:

```markdown
## Shift Work Pattern

Clavain workflows have two modes:
1. **Interactive**: brainstorm, strategy, planning — agent asks questions, iterates
2. **Autonomous**: execution, testing, shipping — agent runs end-to-end, reports results

The shift happens when the spec is complete. Look for these signals:
- Plan approved by flux-drive (no P0/P1 remaining)
- Acceptance criteria defined
- Test strategy specified

When all signals present, the executing agent can run with minimal interruption.
```

### Option C: Integrate with clodex-toggle (Future)

The clodex-toggle already represents a manual "shift to autonomous" — it dispatches tasks to Codex agents for parallel execution. A smarter version would:

1. Auto-detect spec completeness
2. Suggest clodex mode when appropriate
3. Fall back to interactive mode when spec is incomplete

This requires changes to both lfg.md and the clodex-toggle mechanism. Out of scope for now.

## Recommended: Option A + Option B

- Option A gives lfg a concrete spec completeness gate
- Option B documents the pattern for other workflows to adopt

### Changes to commands/lfg.md

Add Step 4a between Step 4 and Step 4.5.

### Changes to executing-plans Skill

Add an "autonomous batch mode" toggle:
- When activated (by lfg Step 4a), run all tasks without per-batch approval
- Still stop on blockers, still report progress
- Default is the current interactive behavior (batch of 3, wait for feedback)

### Changes to using-clavain Skill

Add a section documenting the Shift Work pattern as a general Clavain principle.

## Implementation Order

1. Add Step 4a to `commands/lfg.md` — spec completeness gate
2. Add autonomous batch mode to `executing-plans/SKILL.md`
3. Add Shift Work documentation to `using-clavain/SKILL.md`
4. Test with a full lfg run to verify the boundary works

## Connection to StrongDM's Model

StrongDM's Shift Work goes further than us — their Attractor tool is *purely non-interactive*. It takes a spec and produces code without any human touchpoints. We're not going that far (quality-gates and resolve still have human checkpoints), but formalizing the boundary makes it clear where interactive ends and autonomous begins.

Their key insight we should adopt: **"When intent is complete (specs, tests, existing apps), an agent can run end-to-end without back-and-forth."** Our intent-completeness check is the spec completeness gate in Step 4a.

## Risk

- **Over-automation:** Agent runs autonomously but produces wrong code → caught by quality-gates and tests. The safeguard is that autonomous mode doesn't skip verification, just reduces checkpoints.
- **Under-signaling:** Spec completeness check is too lenient → agent goes autonomous on an incomplete spec. Mitigated by making the checklist explicit and asking the user when items are missing.
- **Scope creep:** This feature itself could expand into a full "autonomous agent framework." Keep it simple — one gate, one mode toggle.
