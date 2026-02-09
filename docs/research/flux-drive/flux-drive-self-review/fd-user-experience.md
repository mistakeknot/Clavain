---
agent: fd-user-experience
tier: adaptive
issues:
  - id: P0-1
    severity: P0
    section: "Step 3.5: Report to User"
    title: "Final synthesis report has no template -- the skill's primary deliverable is the least specified output"
  - id: P0-2
    severity: P0
    section: "Phase 2/3 boundary"
    title: "3-5 minute silent wait with zero progress feedback violates basic CLI UX -- user cannot distinguish hang from work"
  - id: P1-1
    severity: P1
    section: "Step 1.3: User Confirmation"
    title: "Score arithmetic (2+1=3) is orchestrator internals leaked to user -- not actionable for approve/reject decision"
  - id: P1-2
    severity: P1
    section: "Phase 4: Steps 4.1 through 4.4"
    title: "Three sequential decision prompts introduce new tool vocabulary (interpeer, mine, council) at the user's lowest attention point"
  - id: P1-3
    severity: P1
    section: "Step 1.3: User Confirmation"
    title: "Edit selection option has no interaction grammar -- user gets free-text prompt with no guidance on valid edits"
  - id: P1-4
    severity: P1
    section: "Step 3.4: Update the Document"
    title: "Inline blockquote annotations are a destructive write-back with no opt-out, polluting version-controlled documents"
  - id: P1-5
    severity: P1
    section: "Step 4.3: Auto-Chain to Interpeer Mine Mode"
    title: "Auto-chains to interpeer mine mode without user consent -- the only significant action in the spec with no confirmation gate"
  - id: P1-6
    severity: P1
    section: "Step 2.3: Verify agent completion"
    title: "Completion verification is invisible to user -- polling happens internally but user sees nothing between launch and synthesis"
  - id: P2-1
    severity: P2
    section: "Step 4.1: Detect Oracle Participation"
    title: "Interpeer quick mode suggestion is a dead-end reference with no context about what it does or costs"
  - id: P2-2
    severity: P2
    section: "Step 4.5: Final Cross-AI Summary"
    title: "Cross-AI summary duplicates Step 3.5 report without defining the relationship between them"
  - id: P2-3
    severity: P2
    section: "Step 1.2: Select Agents from Roster"
    title: "Category bonus system (+1 for Adaptive when docs exist) can promote irrelevant agents -- base 0 + bonus 1 = 1, which triggers thin-section inclusion"
  - id: P2-4
    severity: P2
    section: "Overall workflow"
    title: "No dry-run or preview mode -- user must commit to full 3-5 minute run to see any results"
improvements:
  - id: IMP-1
    title: "Define Step 3.5 with a full template matching the rigor of the agent prompt template"
    section: "Step 3.5: Report to User"
  - id: IMP-2
    title: "Surface per-agent completion ticks during the wait period (e.g. 'Agent 3/6 done: architecture-strategist')"
    section: "Phase 2/3 boundary"
  - id: IMP-3
    title: "Replace score arithmetic with human-readable relevance labels (High / Medium / Low) in triage table"
    section: "Step 1.3: User Confirmation"
  - id: IMP-4
    title: "Collapse Phase 4 into a single consolidated escalation prompt presented after synthesis"
    section: "Phase 4"
  - id: IMP-5
    title: "Default to writing findings to OUTPUT_DIR/summary.md for file inputs too, with an opt-in for inline annotation"
    section: "Step 3.4: Update the Document"
  - id: IMP-6
    title: "Add estimated time and agent count to the confirmation prompt so the user can make an informed approve/cancel decision"
    section: "Step 1.3: User Confirmation"
  - id: IMP-7
    title: "Guard the category bonus so base-0 agents stay at 0 regardless of project docs"
    section: "Step 1.2: Select Agents from Roster"
  - id: IMP-8
    title: "Require explicit user consent before auto-chaining to interpeer mine mode in Step 4.3"
    section: "Phase 4"
verdict: needs-changes
---

### Summary

Flux-drive is a well-engineered multi-agent review pipeline with strong internal machinery -- triage scoring, parallel dispatch, frontmatter-first synthesis, convergence tracking -- but the user-facing surfaces are systematically underspecified relative to the orchestration internals. The primary deliverable (Step 3.5 report) has seven lines of guidance while the agent prompt template gets 95 lines. The 3-5 minute wait between launch and results produces zero user-visible feedback. The triage confirmation table leaks orchestrator internals (score arithmetic, tier codes) instead of presenting actionable information. Phase 4 introduces three sequential decision points using tool vocabulary the user has never encountered. The write-back mechanism modifies the user's original file without consent. These are not architectural problems -- the pipeline structure is sound. They are information hierarchy problems: the spec lavishes attention on agent-facing contracts while treating user-facing contracts as afterthoughts.

### Section-by-Section Review

#### Step 1.3: User Confirmation -- Triage Table

The triage confirmation is the user's first and only decision gate before a 3-5 minute commitment. Its quality determines whether the confirmation is a genuine checkpoint or a rubber stamp.

**Score arithmetic is orchestrator language, not user language.** The scoring examples in SKILL.md lines 114-145 show columns like "2+1=3" with cryptic bonus rules. This notation is meaningful to the orchestrator (it determines launch/skip decisions) but meaningless to a user. A user cannot evaluate whether "architecture-strategist: 2+1=3" is correct or whether the +1 bonus is deserved. The confirmation becomes performative: the user will always click "Approve" because they lack the information to do otherwise.

The fix is straightforward: translate scores into human-readable relevance labels. "High relevance (codebase-aware)" tells the user more than "3". The summary line on SKILL.md line 157 ("Launch N agents for flux-drive review?") already uses plain language -- propagate that clarity into the table.

**The "Edit selection" path is unspecified.** SKILL.md line 169 says "If user selects 'Edit selection', adjust and re-present." This is the entire specification for a potentially complex interaction. Can the user add agents not in the triage? Can they force-include a score-0 agent? Can they change agent priority? Without an interaction grammar, the user will type free-text ("drop the security one", "add Python reviewer") and the orchestrator must guess intent.

The minimum viable specification: define what edits are possible (add/remove agents from the scored list), show the available-but-skipped agents, and re-present with changes highlighted. The current spec leaves this entirely to the orchestrator's improvisation.

**No cost signal.** "Launch 6 agents for flux-drive review?" gives no sense of what that costs in time, tokens, or cognitive load. Adding "~3-5 min wait, 6 background analyses" would set expectations and make Cancel a real option instead of an "I'm scared" button.

#### Phase 2/3 Boundary: The Silent Wait

After Step 2.2 launches agents and tells the user "they are running in background, estimated wait time ~3-5 minutes" (launch.md line 152-154), the next user-visible event is the synthesis report. During those 3-5 minutes, the user sees nothing.

This is the single biggest UX gap in the entire workflow.

For context: the internal polling mechanism (Step 2.3, launch.md line 157-177) already checks for agent completion and handles retries. It knows when each agent finishes. But this information is never surfaced. The user stares at a terminal that appears frozen.

In CLI tools, long silence universally signals "something is wrong." The mental model for a terminal user is: if the tool is working, it should be telling me. Unix commands from `rsync` to `apt` to `make` all provide progress output during long operations. Flux-drive's 3-5 minutes of silence is an anti-pattern.

The implementation path is clear: each time the orchestrator detects an agent's findings file has appeared (already part of Step 2.3's polling), emit a one-line status: "Agent 3/6 complete: architecture-strategist." This transforms a black-box wait into a visible pipeline and costs zero additional computation.

The completion report in Step 2.3 line 177 ("N/M agents completed successfully, K retried, J failed") is a good signal -- but it fires at the end of the wait, not during it. Move the per-agent completion ticks earlier, and the end summary becomes a natural conclusion rather than the first sign of life after minutes of silence.

#### Step 3.4: Document Write-Back

The write-back mechanism has two problems: it is destructive by default, and it mixes review artifacts with original content.

**Destructive default.** For file inputs, synthesize.md line 77 says "Write the updated document back to INPUT_FILE." This is a one-way operation with no opt-out. The user's plan, spec, or brainstorm is permanently altered. For documents under version control, the diff will show interleaved content changes and review metadata, making code review of the actual changes harder.

The repo review path (synthesize.md lines 111-117) correctly avoids this: it writes a separate `{OUTPUT_DIR}/summary.md` and never touches existing files. File inputs should follow the same pattern by default. The user should be offered a choice: "Write findings to `{OUTPUT_DIR}/summary.md` or annotate the original file directly?"

**Content pollution.** The inline annotation format (synthesize.md lines 73-74):

```markdown
> **Flux Drive** ({agent-name}): [Concise finding or suggestion]
```

Interleaves review artifacts with original content. A heavily-reviewed document accumulates an Enhancement Summary block (10-15 lines), an Issues to Address checklist (5-20 lines), and per-section blockquotes (1-3 per section). On a 100-line plan, this can add 30-50 lines of review scaffolding, inverting the information hierarchy so that review metadata dominates the file.

If the document is run through flux-drive again (iterative review), the annotations accumulate further. There is no mechanism to detect or remove prior flux-drive annotations before adding new ones.

#### Step 3.5: Report to User -- The Missing Template

This is the most critical UX gap and a recurring finding across multiple prior flux-drive runs (see the SKILL/ and Clavain-v3 reports which both flagged this as P0).

Step 3.5 in synthesize.md lines 119-126 specifies the report as four bullet points:
- How many agents ran
- Top findings (3-5 most important)
- Which sections got the most feedback
- Where full analysis files are saved

Compare this to the agent prompt template in launch.md lines 61-150: 90 lines of precise structure (YAML frontmatter schema, section headings, behavioral constraints, severity levels, prose format). Or compare to the Enhancement Summary format in synthesize.md lines 56-69: 14 lines of templated structure.

The report that the user actually reads -- the payoff for a 3-5 minute wait -- gets four bullets and no template. This means every flux-drive invocation produces a differently shaped report. Sometimes findings are sorted by severity, sometimes by section, sometimes by agent. Sometimes the report is 5 lines, sometimes 50. The inconsistency makes it harder for users to build a mental model of what to expect from flux-drive.

A template would specify:
1. **Header**: N agents, M findings, K sections with feedback
2. **Critical findings first**: P0 issues, one line each, with convergence count
3. **Key findings**: P1 issues grouped by section
4. **Next steps**: Actionable items (fix P0s, review P1s, check individual reports)
5. **Footer**: Links to individual agent reports in OUTPUT_DIR

Target length: 15-30 lines. Sorting: severity first, convergence second.

#### Phase 4: Cross-AI Escalation -- Decision Fatigue

Phase 4 is 97 lines of specification (cross-ai.md) for a feature that activates in a narrow conditional: Oracle must be available AND must have participated AND must disagree with Claude agents. For most flux-drive runs, Oracle is unavailable and the entire phase reduces to a single suggestion line (Step 4.1: "Want a second opinion? /clavain:interpeer").

When Phase 4 does fully activate, it creates three sequential decision points:

1. **Step 4.1** (line 7): Oracle participation detection -- either a suggestion or silent continuation
2. **Step 4.3** (line 31): Auto-chain to interpeer mine mode -- this happens WITHOUT user consent
3. **Step 4.4** (line 51): Critical decision escalation -- three options requiring tool vocabulary knowledge

From the user's perspective, they just received a synthesis report (Step 3.5) and now face:
- A comparison table they did not ask for (Step 4.2)
- An automated action they were not warned about (Step 4.3's mine mode invocation)
- A decision prompt using terms they do not understand (Step 4.4's "interpeer council")

**Step 4.3's auto-chain is the only unconsented significant action in the spec.** Every other consequential step has a confirmation gate: triage has "Approve/Edit/Cancel" (Step 1.3), document write-back is at least specified (even if the opt-out is missing), and Step 4.4 asks before running council mode. But Step 4.3 says "Disagreements detected. Running interpeer mine mode to extract actionable artifacts..." and proceeds without asking. This breaks the consent pattern established everywhere else.

**Step 4.4's options assume expertise the user does not have.** "Run interpeer council -- full multi-model consensus review on this specific decision" requires the user to know what interpeer is, what "council" mode provides that they do not already have, and whether the additional time (unstated) is worthwhile. The spec provides no context for this decision.

**The suggestion in Step 4.1 is a dead end.** When Oracle was absent, the spec offers: "Want a second opinion? /clavain:interpeer (quick mode) for Claude to Codex feedback." This is a command reference with no explanation. The user does not know what interpeer does, how long it takes, or what "quick mode" produces. They would need to leave flux-drive, read the interpeer documentation, and then invoke a separate command. The suggestion has no affordance.

The solution is consolidation: collapse Phase 4 into a single post-synthesis prompt. Present all escalation options at once, with enough context for each to be evaluable:

```
Additional perspectives available:
1. Cross-AI review found 3 agreements, 2 Oracle-only findings, 1 disagreement
   - Auto-resolve disagreement? (runs comparison analysis, ~1 min)
2. P0 security decision detected
   - Run multi-model council? (Oracle + Claude + Codex, ~5 min)
3. Skip all escalation
```

This gives the user one decision moment with full context, rather than a sequence of prompts with partial information.

#### Workflow Agent Count and Vocabulary

The triage table in Step 1.2 uses "Adaptive" as the category label (SKILL.md line 188 onward), while the existing prior-run outputs use "T1", "T3", and other tier labels. The current SKILL.md has moved away from tier numbering toward category names (Project Agents, Adaptive Reviewers, Cross-AI), which is an improvement -- but the triage example tables on lines 114-145 still use column headers "Agent, Category, Score, Reason, Action" without defining what the Category values mean to a user.

The shift from numbered tiers to named categories is the right direction but incomplete. The scoring examples show "Adaptive" as a category value, which is better than "T3" but still jargon. "Codebase-aware" and "General" would be more descriptive and immediately communicative.

#### Error Communication

Flux-drive's error handling is one of its stronger areas from a UX perspective, with one gap.

**Good**: Step 2.3 (launch.md lines 157-177) specifies retry logic, stub files for failures, and a completion report ("N/M agents completed successfully, K retried, J failed"). This is concrete and actionable.

**Good**: The Oracle error handling (SKILL.md line 229-231) gracefully degrades: "If the Oracle command fails or times out, note it in the output file and continue without Phase 4."

**Gap**: The completion report in Step 2.3 line 177 fires after all agents are done, but it is the first user-visible status since the launch message. Moving failure notifications earlier ("Agent architecture-strategist failed, retrying...") would make the error experience more timely.

**Gap**: When an agent produces a `verdict: error` stub, the synthesis phase (Step 3.1, synthesize.md line 21) counts it as "agent failed" and excludes it from convergence. But the user report (Step 3.5) does not specify whether to report failed agents or silently omit them. If 2 of 6 agents failed and the user only sees "4 agents reviewed your document," they have an incomplete picture.

#### The Dry Run Problem

There is no way to preview what flux-drive will do without committing to a full run. A user who wants to know "which agents would review my file?" must launch flux-drive and either approve the triage (committing to the 3-5 minute wait) or cancel.

A `--dry-run` or `--triage-only` mode that stops after Step 1.3 would let users:
- Understand the agent selection for their document type
- Learn the agent roster through real examples
- Verify that the right domains are covered before investing time
- Use triage as a document quality signal (a document that triggers 8 agents has broad surface area)

This is a P2 because it is an enhancement, not a bug. But it addresses the progressive disclosure problem: new users could use dry-run to learn what flux-drive does before running it.

### Issues Found

**P0-1: Final synthesis report has no template (Step 3.5, synthesize.md lines 119-126)**
The skill's primary user-facing deliverable -- the synthesis report presented after 3-5 minutes of agent work -- has four bullet points of guidance and no format template. Every other output in the spec (agent prompts, Enhancement Summary, YAML frontmatter) is precisely templated. This produces inconsistent reports across invocations. Severity is P0 because this is the value delivery mechanism of the entire skill, and its inconsistency undermines user trust in the tool. This finding has been flagged in two prior flux-drive runs (SKILL/ and Clavain-v3) and remains unaddressed.

**P0-2: Zero progress feedback during 3-5 minute wait (Phase 2/3 boundary)**
Between the launch message (launch.md line 152) and the synthesis report (synthesize.md line 119), the user receives no feedback. The internal polling mechanism (Step 2.3) already detects per-agent completion but never surfaces it. For a CLI tool, 3-5 minutes of terminal silence is indistinguishable from a hang. This is the single largest UX gap in the workflow.

**P1-1: Triage score arithmetic is insider notation (Step 1.3, SKILL.md lines 114-145)**
Score columns showing "2+1=3" expose the scoring algorithm to users who have no context for evaluating it. The confirmation gate becomes performative -- users will always approve because they cannot assess the triage. Replace with human-readable relevance labels.

**P1-2: Phase 4 creates sequential decision fatigue (Steps 4.1 through 4.4)**
Three decision prompts using unfamiliar tool vocabulary (interpeer, mine mode, council) exhaust the user at their lowest attention point (post-wait). Each prompt introduces new concepts without sufficient context. Consolidate into a single escalation prompt.

**P1-3: Edit selection interaction is unspecified (Step 1.3, SKILL.md line 169)**
"If user selects 'Edit selection', adjust and re-present" is the entire spec for a multi-modal interaction. No valid operations defined, no available-but-skipped agent list, no re-presentation format.

**P1-4: Inline annotations are destructive with no opt-out (Step 3.4, synthesize.md lines 72-77)**
Write-back injects blockquote review artifacts directly into the user's document. No choice offered. Repo review path correctly writes to a separate file; file inputs should follow the same pattern by default.

**P1-5: Step 4.3 auto-chains without consent (cross-ai.md lines 31-49)**
Interpeer mine mode is invoked automatically when disagreements are detected. Every other significant action in the spec has a confirmation gate. This one does not. It breaks the consent pattern and introduces processing time the user did not approve.

**P1-6: Completion verification is invisible (Step 2.3, launch.md lines 157-177)**
The orchestrator polls for agent completion, handles retries, and generates stub files for failures, but none of this is surfaced to the user until the final completion report. Individual agent completions and retries should be visible as they happen.

**P2-1: Interpeer suggestion is a dead-end reference (Step 4.1, cross-ai.md lines 7-13)**
When Oracle is absent, the spec suggests `/clavain:interpeer (quick mode)` without explaining what it does, how long it takes, or what the user receives. The user must leave flux-drive, research interpeer separately, and invoke a new command.

**P2-2: Cross-AI summary duplicates Step 3.5 content (Step 4.5, cross-ai.md lines 71-96)**
Phase 4's final summary overlaps with the Step 3.5 report. The user receives two summary reports in sequence with no defined relationship. Should 4.5 replace 3.5? Augment it? The spec does not say.

**P2-3: Category bonus can promote irrelevant agents (Step 1.2, SKILL.md lines 99-110)**
A base-0 agent gets +1 from the Adaptive bonus when project docs exist, reaching score 1. Score-1 agents are included if they cover a thin section. This means an irrelevant agent (base 0, wrong domain) can be launched simply because the project has documentation and some section is short. The bonus should not elevate a base-0 score.

**P2-4: No dry-run or triage-only mode (overall workflow)**
Users cannot preview agent selection without committing to a full run. A `--triage-only` flag that stops after Step 1.3 would support progressive learning and let users verify coverage before investing time.

### Improvements Suggested

**IMP-1: Template the Step 3.5 report with the same rigor as the agent prompt template.**
Specify: header with agent count and finding count, P0 findings first (one line each with convergence), P1 findings grouped by section, next-steps section with concrete actions, footer with links to individual reports. Target 15-30 lines. Sort by severity then convergence. This is the single highest-impact change.

**IMP-2: Surface per-agent completion during the wait.**
Each time the orchestrator detects a findings file via polling, emit: "Agent 3/6 complete: architecture-strategist." On retry: "Agent 5/6 failed, retrying: security-sentinel." This reuses existing detection logic (Step 2.3 already polls) and transforms a silent wait into a visible pipeline. Zero additional computation cost.

**IMP-3: Replace score arithmetic with human-readable labels.**
In the triage table, replace "2+1=3" with "High (codebase-aware)." Replace "Category" column with something like "Mode" showing "codebase-aware" or "general." Keep the scoring algorithm as internal orchestrator logic; surface only the decision and reason.

**IMP-4: Collapse Phase 4 into a single escalation prompt.**
After synthesis, present one consolidated message with all available escalation paths, estimated time for each, and brief description of what each provides. Let the user make all escalation decisions at once. Remove the auto-chain in Step 4.3; replace with a consent-gated option.

**IMP-5: Default to non-destructive write-back for file inputs.**
Write findings to `{OUTPUT_DIR}/summary.md` by default (matching the repo review path). Offer inline annotation as an opt-in: "Write findings to [summary file] or annotate [original file] directly?" This preserves the original document and produces clean version-control diffs.

**IMP-6: Add cost signal to confirmation prompt.**
Below the triage table, add: "Estimated: ~3-5 min, N agents will read your document and relevant codebase files." This converts "Launch N agents?" from an opaque question to an informed one.

**IMP-7: Guard the category bonus at base 0.**
Change the scoring rule so that Adaptive bonuses only apply when the base score is 1 or higher. An agent with base relevance 0 (wrong domain, no relationship) should stay at 0 regardless of project documentation. This prevents irrelevant agents from being promoted into the "maybe" tier.

**IMP-8: Require consent for interpeer mine mode (Step 4.3).**
Replace the auto-chain with: "D disagreements detected between Oracle and Claude agents. Resolve them? [Y/n]." This aligns Step 4.3 with the consent pattern used everywhere else in the spec.

### Overall Assessment

Flux-drive's orchestration pipeline is sophisticated and well-engineered. The triage scoring, parallel dispatch, frontmatter-first synthesis, and convergence tracking are strong system design. But the skill has an information hierarchy inversion: the internal machinery (agent prompts, dispatch routing, YAML schemas) is specified with high precision, while the user-facing surfaces (triage confirmation, wait experience, synthesis report, escalation offers) are specified with low precision.

The two most impactful changes are: (1) template the Step 3.5 report to match the rigor applied to agent prompt templates, and (2) surface per-agent completion ticks during the wait period. Together, these address the skill's core UX deficiency -- the user's experience of the tool does not match the tool's actual capability.

Verdict: **needs-changes**. The pipeline works; the user contract needs tightening.
