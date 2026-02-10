## Simplification Analysis

### Core Purpose

Phase 4 exists for one reason: after multi-agent synthesis, surface any findings where Oracle (GPT-5.2 Pro) and Claude-based agents see things differently, and let the user decide whether to investigate further via interpeer.

### Unnecessary Complexity Found

**1. Steps 4.3-4.5 are a 66-line auto-chaining pipeline that re-implements interpeer inline**
(`/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` lines 31-97)

The interpeer skill already owns mine mode, council mode, and their output formats. Phase 4 re-specifies mine mode's workflow (lines 46-49: "Structure each disagreement as a conflict... Generate artifacts... Present summary"), council mode's trigger logic (lines 53-57: severity indicators, P0 checks), and a 22-line summary template (lines 75-97) that duplicates interpeer's own output format.

This is flux-drive telling interpeer how to do interpeer's job. The interpeer SKILL.md already defines conflict structure (The Conflict, Evidence, Resolution, Minority Report), artifact generation (tests, spec clarifications, stakeholder questions), and council workflow (independent opinion, Oracle query, synthesis). None of this needs restating.

**2. Step 4.3 auto-chains to interpeer mine mode without user consent**
(`/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` lines 31-49)

The text says "Disagreements detected. Running interpeer mine mode to extract actionable artifacts..." and proceeds automatically. This violates the user's autonomy. The self-review summary (`summary.md`) already flagged this as P1: "Add user consent gate before auto-chaining to interpeer mine mode." Mine mode invokes external model calls and can take minutes. Running it without asking is hostile UX.

**3. Step 4.4 has a second decision prompt that creates a 3-choice menu mid-flow**
(`/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` lines 51-69)

After mine mode completes (or doesn't), Step 4.4 presents another interactive decision point: "Resolve now / Run interpeer council / Continue without escalation." This creates a branching conversation tree inside what should be a report. The user already approved agent selection in Phase 1. They should not face two more interactive gates in Phase 4.

**4. The 22-line summary template at Step 4.5 duplicates the synthesis summary**
(`/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` lines 72-97)

Phase 3 already produces a summary with key findings, issues to address, and convergence counts. Step 4.5 generates a second summary with overlapping content (finding counts, confidence levels) plus conditional blocks for mine mode artifacts and council decisions. The user gets two summaries, which dilutes both.

**5. The 4-category classification table is more granular than useful**
(`/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` lines 23-29)

The Agreement/Oracle-only/Claude-only/Disagreement taxonomy looks precise but three of the four categories collapse in practice:
- **Agreement** = "both flagged it" -- already captured by synthesis convergence counting in Step 3.3.
- **Claude-only** = "Oracle didn't mention it" -- silence is not a finding. This category generates noise ("Oracle missed 12 things Claude found") when the real signal is in the reverse direction.
- **Disagreement** = the only category that requires action, and it's the rarest. In the self-review, Oracle timed out entirely, which means this whole classification pipeline produced zero value.

Only two categories matter: "Oracle found something Claude agents didn't" (blind spots) and "Oracle contradicts Claude agents" (disagreements). Everything else is already in the synthesis.

**6. Step 4.1's "lightweight option" for absent Oracle is a dead-end suggestion**
(`/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` lines 6-14)

When Oracle is not in the roster, Step 4.1 prints a suggestion to run `/clavain:interpeer (quick mode)` and stops. This is 9 lines to display a one-line hint. It could be a single sentence in the synthesis output or, better, handled by the skip condition in SKILL.md that the bead spec already calls for.

### Code to Remove

| Location | Lines | Reason |
|----------|-------|--------|
| Step 4.3 (auto-chain to mine mode) | 31-49 | Re-implements interpeer mine mode inline; runs without consent |
| Step 4.4 (council offering) | 51-69 | Re-implements interpeer council trigger inline; adds unnecessary interactive gate |
| Step 4.5 (22-line summary template) | 72-97 | Duplicates synthesis summary; conditional blocks for modes that may not have run |
| Step 4.1 (9-line absent-Oracle message) | 6-14 | Replace with skip condition in SKILL.md |
| 2 of 4 classification categories | 23-29 | Agreement and Claude-only add noise, not signal |

Estimated LOC reduction: 66 lines removed (Steps 4.3-4.5), 9 lines removed (Step 4.1 message), ~6 lines simplified (classification table). Total: ~81 of 97 lines.

### Simplification Recommendations

**1. Replace the entire 97-line file with a ~30-line cross-AI coda** (highest impact)
- Current: 5 steps, 2 interactive gates, inline re-specification of interpeer mine and council modes, 22-line summary template, 4-category classification.
- Proposed: 1 step that classifies Oracle vs Claude findings into 2 categories (blind spots, disagreements), presents results in a compact table, and offers interpeer escalation behind a single AskUserQuestion consent gate.
- Impact: 97 lines to ~30 lines. Eliminates duplicate interpeer logic, duplicate summary, and unauthorized auto-chaining.

The rewritten Phase 4 should contain exactly:
1. A note that it only runs when Oracle participated (2 lines)
2. Classification into blind spots (Oracle-only) and disagreements (Oracle contradicts Claude) -- skip Agreement and Claude-only (4 lines for the table)
3. A compact results display showing counts and top findings (8 lines)
4. An AskUserQuestion consent gate: "Investigate with interpeer?" with Approve/Skip options (6 lines)
5. If approved, invoke `/clavain:interpeer` (the skill, not inline re-implementation) with the disagreements as input (4 lines)
6. No second summary -- the synthesis summary from Phase 3 is the final output (0 lines)

**2. Move the Oracle-absent skip condition to SKILL.md** (medium impact)
- Current: Step 4.1 in cross-ai.md displays a 9-line message suggesting interpeer quick mode.
- Proposed: Add a 2-line skip condition in SKILL.md's Phase 4 section: "If Oracle was not in the roster, skip Phase 4. The synthesis summary is the final output."
- Impact: Removes 9 lines from cross-ai.md. The interpeer hint can go in the synthesis output's "Next steps" if desired.

**3. Collapse the 4-category classification to 2 categories** (clarity improvement)
- Current: Agreement / Oracle-only / Claude-only / Disagreement with a formatted table.
- Proposed: **Blind spots** (Oracle found, Claude didn't) and **Conflicts** (Oracle contradicts Claude). Agreement is already in synthesis. Claude-only is just "Oracle didn't mention it" -- not actionable.
- Impact: Halves the classification logic. Focuses attention on the two categories that actually warrant user action.

**4. Update SKILL.md Integration section to remove chaining promises** (consistency)
- Current: SKILL.md lines 257-263 promise three separate chaining modes (mine automatic, council offered, quick when absent).
- Proposed: "Chains to: interpeer (user-initiated, when Oracle disagreements found)". One line instead of six.
- Impact: Integration section shrinks and accurately reflects the simplified Phase 4.

### YAGNI Violations

**1. Inline interpeer mine mode specification (Steps 4.3, lines 31-49)**
Violates YAGNI because: interpeer already defines mine mode's workflow, structure, and output format. Duplicating it here means two places to update when mine mode changes, two places that can drift, and a skill boundary violation where flux-drive tells interpeer how to run.
What to do instead: Invoke `/clavain:interpeer mine` as a skill call with the disagreements as context. Let interpeer own its own workflow.

**2. Inline interpeer council trigger logic (Step 4.4, lines 51-69)**
Violates YAGNI because: The council offering with its P0-severity detection and 3-option menu is speculative. The self-review Oracle timed out. The council mode has never been triggered from flux-drive in practice. Building trigger logic for an untested integration path is textbook YAGNI.
What to do instead: If the user wants council, they invoke `/clavain:interpeer council` themselves. A consent gate with a single "Investigate with interpeer?" question is sufficient.

**3. The 22-line conditional summary template (Step 4.5, lines 72-97)**
Violates YAGNI because: It has conditional blocks for "[If interpeer mine mode ran:]" and "[If interpeer council mode ran:]" -- building a template that handles all permutations of modes that may or may not have executed. This is template-driven design for branches that rarely (or never) fire.
What to do instead: No separate summary. Phase 3's synthesis is the summary. If interpeer runs, interpeer produces its own output.

**4. Agreement and Claude-only classification categories (Step 4.2)**
Violates YAGNI because: Agreement is already tracked in synthesis convergence. Claude-only findings ("Oracle didn't mention this") are not actionable -- silence from one model is not a signal. These categories exist to make the classification feel complete (4 is more "professional" than 2), not because they drive decisions.
What to do instead: Track only blind spots and conflicts. Two categories that each have a clear action path.

### Final Assessment

Total potential LOC reduction: 67 lines (97 to ~30), which is 69% of the file.

Complexity score: High -- the current Phase 4 has 5 sequential steps with 2 interactive branching points, inline re-specification of two interpeer modes, a 4-way classification scheme, and a 22-line conditional template. This for a phase that is marked "(Optional)" and whose primary external dependency (Oracle) timed out in the only recorded self-review.

Recommended action: Proceed with full rewrite. The minimum viable Phase 4 is: classify Oracle findings into blind spots and conflicts, show results, ask user if they want to escalate to interpeer, and stop. Everything else is either already in synthesis, already in interpeer, or speculative branching for untested integration paths.

### Proposed Rewrite Structure

The new `cross-ai.md` should contain approximately:

```
# Phase 4: Cross-AI Escalation (Optional)

> Only runs when Oracle participated. If Oracle was not in the roster, skip.

### Step 4.1: Classify Oracle vs Claude Findings

Read `{OUTPUT_DIR}/oracle-council.md`. Compare against synthesis findings from Phase 3.

Classify into two categories:

| Category | Definition |
|----------|-----------|
| **Blind spots** | Oracle raised something no Claude agent flagged |
| **Conflicts** | Oracle and Claude agents disagree on the same topic |

Findings that both Oracle and Claude agents agree on are already in the synthesis
and need no separate treatment.

### Step 4.2: Present and Offer Escalation

Present the classification:

    Cross-AI Analysis:
    - Blind spots (Oracle-only): N
    - Conflicts: M
    [List top 3 findings briefly]

If there are conflicts or notable blind spots, use AskUserQuestion:

    question: "Escalate N cross-AI findings to interpeer for investigation?"
    options:
      - label: "Investigate"
        description: "Run /clavain:interpeer with these findings"
      - label: "Skip"
        description: "Keep synthesis as final output"

If user approves, invoke /clavain:interpeer with the blind spots and conflicts
as input context. Let interpeer choose the appropriate mode (mine for conflicts,
deep for blind spots).

If user skips or there are no findings, Phase 4 ends. The synthesis from Phase 3
is the final output.
```

That is 35 lines including whitespace and code blocks. It preserves the core value (cross-AI classification and escalation path) while eliminating inline interpeer re-specification, unauthorized auto-chaining, duplicate summaries, and noise categories.
