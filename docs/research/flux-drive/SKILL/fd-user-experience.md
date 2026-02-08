---
agent: fd-user-experience
tier: 1
issues:
  - id: P0-1
    severity: P0
    section: "Step 3.5: Report to User"
    title: "Final report is underdefined — no format, no structure, no actionability guidance"
  - id: P1-1
    severity: P1
    section: "Step 1.3: User Confirmation"
    title: "No triage context for uninitiated users — score arithmetic is insider notation"
  - id: P1-2
    severity: P1
    section: "Phase 4: Steps 4.1/4.3/4.4"
    title: "Three sequential user prompts in Phase 4 create decision fatigue after a long wait"
  - id: P1-3
    severity: P1
    section: "Step 1.3: User Confirmation"
    title: "Edit selection flow has no guidance on what editing means or how to express changes"
  - id: P1-4
    severity: P1
    section: "Step 3.5 / Phase 4"
    title: "User gets no progress signal between launch (Phase 2) and final report (Step 3.5)"
  - id: P1-5
    severity: P1
    section: "Step 3.4: Update the Document"
    title: "Inline blockquote findings pollute the original document with review artifacts"
  - id: P2-1
    severity: P2
    section: "Step 4.1: Detect Oracle Participation"
    title: "Interpeer suggestion is a dead-end — no affordance to act on it"
  - id: P2-2
    severity: P2
    section: "Phase 4: Step 4.5"
    title: "Cross-AI summary table duplicates information already in Step 3.5 report"
  - id: P2-3
    severity: P2
    section: "Step 1.3: User Confirmation"
    title: "Tier labels (T1/T2/T3) are meaningless to the user without a legend"
improvements:
  - id: IMP-1
    title: "Define the Step 3.5 report format explicitly, with a template"
    section: "Step 3.5: Report to User"
  - id: IMP-2
    title: "Add a progress heartbeat between Phase 2 launch and Phase 3 synthesis"
    section: "Phase 2/3 boundary"
  - id: IMP-3
    title: "Collapse Phase 4 user prompts into a single decision point"
    section: "Phase 4"
  - id: IMP-4
    title: "Replace tier codes with human-readable labels in the confirmation table"
    section: "Step 1.3: User Confirmation"
  - id: IMP-5
    title: "Offer a non-destructive write-back mode (separate file) as the default"
    section: "Step 3.4: Update the Document"
  - id: IMP-6
    title: "Add estimated token cost or agent count to the confirmation prompt"
    section: "Step 1.3: User Confirmation"
verdict: needs-changes
---

### Summary

The flux-drive skill defines a sophisticated multi-agent review pipeline, but the user-facing touchpoints -- the moments where a human reads, decides, or waits -- are the weakest part of the spec. The triage confirmation (Step 1.3) uses insider notation that only a plugin developer would parse. The final report (Step 3.5) is specified in seven lines with no template, despite being the single most important output the user sees. Between launch and report, the user gets zero progress signals during a 3-5 minute wait. Phase 4 introduces up to three sequential decision prompts (interpeer offer, splinterpeer notification, winterpeer escalation), creating decision fatigue at the point where the user is least equipped to evaluate options. The information architecture needs to be inverted: the user-facing surfaces need the most specification, not the least.

### Section-by-Section Review

#### Step 1.3: User Confirmation (Lines 132-153)

This is the user's first and most consequential decision point. The spec prescribes a table with columns Agent, Tier, Score, Reason, and Action. Several problems:

**Score notation is opaque.** The example shows `2+1` -- a raw arithmetic expression from the scoring algorithm. The user has no context for what "2" means, what the "+1" bonus represents, or why it matters. The spec defines these on lines 96-100, but that section is for the orchestrator, not the user. The confirmation table is the user's interface, and it should speak the user's language: "highly relevant," "adjacent coverage," or similar.

**Tier labels are jargon.** "T1," "T2," "T3" are meaningless without a legend. The user does not know that T1 means "reads your project's CLAUDE.md" and T3 means "generic checklist reviewer." This distinction matters -- it's the difference between a reviewer who knows your codebase and one who does not -- but the table buries it in a code.

**The "Edit selection" option is unspecified.** Line 151 says "If user selects 'Edit selection', adjust and re-present." But what does editing look like? Can the user say "drop security-sentinel"? "Add fd-performance"? "Replace the T3 with the T1"? The spec does not define the interaction grammar. A user who selects "Edit" gets no guidance on what to type, leading to a frustrating free-text exchange where the orchestrator has to guess intent.

**No cost signal.** The confirmation says "Launching N agents" but does not convey what that costs in time or tokens. For a user who has never run flux-drive, "5 agents" is meaningless. Adding "~3-5 min, ~50k tokens" would set expectations and let the user make an informed approve/cancel decision.

**The summary line is good.** "Launching N agents (M codebase-aware, K generic)" on line 146 is the right information at the right level. But it appears after the dense table, where it should appear before it as a headline.

#### Step 3.4: Update the Document (Lines 400-466)

The write-back mechanism (lines 429-433) injects blockquote annotations directly into the original document:

```markdown
> **Flux Drive** ({agent-name}): [Concise finding or suggestion]
```

This is invasive. The user's document -- their plan, spec, or brainstorm -- becomes permanently annotated with review artifacts. There is no "clean" version anymore. For documents under version control, this creates noisy diffs that mix content changes with review metadata. For documents that will be shared with stakeholders, the annotations are inappropriate.

The spec does not offer a choice. It says "Write the updated document back to `INPUT_FILE`" (line 434) -- a destructive overwrite with no opt-out. The repo review path (lines 468-474) correctly avoids modifying existing files and writes to a separate summary. File inputs should have a similar non-destructive option, or at minimum, the user should be asked before their document is modified.

The "Flag for archival" strategy (lines 409-410) adds a divergence warning at the top of the file. Combined with the Enhancement Summary block (lines 413-426) and per-section inline notes, a heavily-reviewed document could gain 30-50 lines of review scaffolding above the actual content. The information hierarchy is inverted: review metadata dominates, original content recedes.

#### Step 3.5: Report to User (Lines 476-483)

This is the most important user-facing output in the entire skill -- the payoff after a 3-5 minute wait -- and it gets seven lines of specification. Compare this to the 95-line prompt template (lines 255-349) or the 35-line Agent Roster tables. The spec tells the orchestrator what to report but not how:

- No format template (unlike the agent output format on lines 310-348, which is fully specified)
- No guidance on length (should this be 5 lines or 50?)
- No priority ordering (are findings sorted by severity? by convergence? by section?)
- No call-to-action (what should the user do next?)

The agent prompt template (lines 304-348) is a model of clarity: it specifies frontmatter structure, section headings, and behavioral constraints. Step 3.5 should receive the same treatment. Without it, every orchestrator invocation will produce a different report shape, making flux-drive feel inconsistent.

#### Phase 4: User-Facing Escalation (Lines 486-556)

Phase 4 has up to three points where the user must read, evaluate, and decide:

1. **Step 4.1** (line 494): "Want a second opinion? /clavain:interpeer" -- or, if Oracle participated, proceed silently
2. **Step 4.3** (line 522): "Disagreements detected. Running splinterpeer..." -- this auto-chains without user consent
3. **Step 4.4** (line 547): "Critical decision detected. Options: 1/2/3" -- another decision prompt

From the user's perspective, they just waited 3-5 minutes, received a report, and now face a sequence of prompts about tools they may never have heard of (interpeer, splinterpeer, winterpeer). Each prompt introduces new vocabulary and asks the user to evaluate something they have no basis to judge.

**Step 4.3 auto-chains without consent** (line 529-532): "Disagreements detected. Running splinterpeer to extract actionable artifacts..." This is the only place in the spec where the orchestrator takes a significant action (invoking a full skill workflow inline) without asking the user. Every other consequential action has a confirmation gate. This one does not.

**Step 4.4's three options assume expertise** (lines 548-553): "Resolve now," "Run winterpeer council," and "Continue without escalation" require the user to know what winterpeer is, what a "multi-model consensus review" provides that they do not already have, and whether it is worth the additional time. The spec does not provide enough context for a user to make this choice.

**The interpeer suggestion in Step 4.1 is a dead end** (lines 494-497): When Oracle was not in the roster, the spec says to suggest `/clavain:interpeer`. But it does not explain what interpeer does, how long it takes, or what the user would get. It is a suggestion with no affordance -- the user has to leave flux-drive, invoke a different command, and hope it applies.

#### Information Flow: Triage to Launch to Results

The overall information flow has a significant gap between Phase 2 (launch) and Phase 3 (synthesis). The spec says to tell the user agents are running and give an estimated wait time of 3-5 minutes (lines 352-354). Then the next user-visible event is the full report in Step 3.5. During those 3-5 minutes, the user sees nothing.

For a CLI tool, silence during a long operation is poor UX. The user does not know if the process is stuck, how far along it is, or whether any agents have failed. The polling mechanism on line 368 (`ls` every 30 seconds) is an internal implementation detail -- it is never surfaced to the user.

The validation report on line 382 ("5/6 agents returned valid frontmatter, 1 fallback to prose") is a good signal, but it only fires after all agents complete. Moving a lightweight progress indicator earlier -- "3/6 agents complete..." -- would significantly improve the wait experience.

### Issues Found

**P0-1: Final report format is underdefined (Step 3.5, lines 476-483)**
The single most important user-facing output -- the synthesis report -- has no template, no format guidance, and no structural constraints. Every other output in the spec (agent prompts, frontmatter, Enhancement Summary) is precisely templated. The report is the user's payoff for a multi-minute wait and it is specified in seven lines of bullet points. This will produce inconsistent, unpredictable reports across invocations. Severity is P0 because this is the primary value delivery mechanism of the entire skill.

**P1-1: Score notation is insider jargon (Step 1.3, lines 136-146)**
The triage table shows raw score arithmetic (`2+1=3`) that is meaningful to the orchestrator but opaque to the user. Users cannot evaluate whether the triage is correct because they do not understand the scoring system. This undermines the purpose of confirmation: a user who cannot evaluate the selection will always click "Approve," making the gate performative rather than functional.

**P1-2: Phase 4 creates decision fatigue with sequential prompts (Steps 4.1/4.3/4.4)**
Three decision points in Phase 4, each introducing new tool vocabulary (interpeer, splinterpeer, winterpeer), exhaust the user's decision-making capacity at a moment when they have already invested significant time. Step 4.3 auto-chains without consent. The user needs a single, consolidated decision point, not a sequence.

**P1-3: "Edit selection" interaction is unspecified (Step 1.3, line 151)**
The spec says to "adjust and re-present" but does not define how the user expresses edits, what constraints apply (can they add agents not in the triage?), or what the re-presentation looks like. This creates an ambiguous free-text interaction.

**P1-4: No progress signal during 3-5 minute wait (Phase 2/3 boundary)**
Between the launch message (line 352) and the final report (line 476), the user receives zero feedback. For a CLI tool, 3-5 minutes of silence suggests a hang. The internal polling mechanism (line 368) is never surfaced.

**P1-5: Inline blockquote annotations are invasive (Step 3.4, lines 429-433)**
Writing review findings directly into the user's document as blockquotes permanently alters the original content. There is no opt-out and no clean-versus-annotated choice. For version-controlled documents, this creates noisy diffs mixing review artifacts with real content.

**P2-1: Interpeer suggestion is a dead end (Step 4.1, lines 494-497)**
When Oracle is absent, the spec suggests `/clavain:interpeer` without explaining what it does, how long it takes, or what the user gains. The suggestion lacks sufficient context for a user to act on it.

**P2-2: Cross-AI summary duplicates Step 3.5 content (Step 4.5, lines 558-583)**
The Phase 4 final summary (Step 4.5) overlaps significantly with the Step 3.5 report. The user receives two summary reports in sequence -- one from synthesis, one from cross-AI analysis. The spec does not define how these relate or whether Step 4.5 replaces or supplements Step 3.5.

**P2-3: Tier labels are jargon in confirmation table (Step 1.3, line 143)**
"T1," "T2," "T3" labels in the triage table carry no meaning for the user. The distinction between "codebase-aware" and "generic" is important but requires a legend or human-readable labels.

### Improvements Suggested

**IMP-1: Define the Step 3.5 report with a full template.**
Create a template parallel to the agent output template (lines 310-348). Include: a severity-sorted findings list, convergence counts, sections with heaviest feedback, a "what to do next" section with concrete actions, and a pointer to the full agent reports in `OUTPUT_DIR`. Specify target length (15-25 lines) and ordering (P0 first, then by convergence count).

**IMP-2: Add a progress heartbeat during the wait.**
After launching agents, surface completion progress to the user. Each time an agent completes (detected via task output or file existence), print a one-line status: "Agent 3/6 complete (fd-architecture)." This transforms a silent 3-5 minute wait into a visible pipeline. The polling loop on line 368 is already checking -- it just needs to emit user-facing output.

**IMP-3: Collapse Phase 4 into a single decision point.**
Instead of three sequential prompts, present one consolidated offer after synthesis:

```
Additional perspectives available:
- [If Oracle participated]: Cross-AI analysis found N agreements, M blind spots, D disagreements
  → Auto-resolve disagreements? [Y/n]
- [If critical decision]: Architecture/security decision needs deeper review
  → Run winterpeer council? [Y/n]
- [If Oracle absent]: Quick cross-model check available via /clavain:interpeer
```

This lets the user make all escalation decisions at once, with enough context to choose.

**IMP-4: Replace tier codes with human-readable labels in confirmation.**
Instead of "T1" / "T3", use "project-aware" and "generic." Instead of `2+1=3`, use "high relevance" or a visual indicator (three dots, three stars). The summary line already uses "codebase-aware vs generic" -- propagate that language into the table.

**IMP-5: Offer a non-destructive write-back option.**
Default to writing the Enhancement Summary and inline findings to a separate file (`{OUTPUT_DIR}/summary.md`) rather than modifying `INPUT_FILE`. Offer the user a choice: "Write findings to [summary file] or annotate [original file] directly?" This preserves the original document and gives version control clean diffs.

**IMP-6: Add estimated time/cost to confirmation prompt.**
Below the triage table, add: "Estimated time: ~3-5 minutes. N agents will read the document and relevant codebase files." This sets expectations and makes the Approve/Cancel decision informed.

### Overall Assessment

The flux-drive skill has strong engineering in its triage algorithm, agent dispatch, and synthesis pipeline, but the user-facing surfaces are underspecified relative to the internal machinery. The confirmation flow uses insider notation. The final report -- the skill's primary deliverable -- lacks a template. The wait experience is silent. Phase 4 introduces decision fatigue with sequential prompts. These are fixable issues: the spec already demonstrates good template discipline in the agent prompt (lines 255-349) and the Enhancement Summary format (lines 413-426). Applying that same rigor to Step 1.3, Step 3.5, and Phase 4's user prompts would bring the user experience in line with the system's sophistication. Verdict: **needs-changes** -- the internal pipeline is solid, but the user-facing contract needs tightening before the spec can be implemented with consistent results.
