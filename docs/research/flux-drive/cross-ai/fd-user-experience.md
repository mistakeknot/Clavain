# UX Review: Phase 4 Cross-AI Escalation (cross-ai.md)

**Reviewer:** fd-user-experience (CLI/TUI interaction specialist)
**Target file:** `/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md`
**Supporting context:** `/root/projects/Clavain/skills/flux-drive/SKILL.md`, `/root/projects/Clavain/skills/interpeer/SKILL.md`
**Bead:** Clavain-ne6 (rewrite from 97 lines to ~30-40 lines)
**Date:** 2026-02-09

---

## UX Assessment

### User Workflows Affected

Phase 4 sits at the tail end of a flux-drive run. The user has already:
1. Waited through triage and agent selection (Phase 1, ~30 seconds)
2. Approved agent launch (consent gate)
3. Waited 3-5 minutes for parallel agent execution (Phase 2)
4. Read the synthesis report (Phase 3, Steps 3.1-3.5)

By the time Phase 4 activates, the user has invested 4-7 minutes and has already consumed a full synthesis report. Their attention budget is at its lowest. Any new prompts must earn their screen space.

### Overall Verdict

The current Phase 4 spec is a **UX regression** at the point where it matters most -- the user's exit path. The rewrite to ~30-40 lines is the correct instinct. The spec's core value (cross-AI classification of Agreement/Oracle-only/Claude-only/Disagreement) is sound and worth preserving. Everything around it -- the auto-chaining, the sequential prompts, the summary duplication -- degrades the experience.

---

## Specific Issues

### Issue 1: Auto-chain in Step 4.3 violates the consent pattern

**Location:** `cross-ai.md` lines 31-49 (Step 4.3: Auto-Chain to Interpeer Mine Mode)

**Problem:** Step 4.3 is the only place in the entire flux-drive spec where a significant action fires without user consent. The spec says: "Disagreements detected. Running interpeer mine mode to extract actionable artifacts..." and proceeds immediately. Every other consequential action in the workflow has a gate:
- Phase 1 triage: AskUserQuestion with Approve/Edit/Cancel
- Phase 3 write-back: writes to file (should also have a gate, but at least is specified)
- Step 4.4 council escalation: three explicit options

The auto-chain breaks the established pattern. Worse, it introduces processing time the user never agreed to. "Mine mode" involves structuring disagreements, generating artifacts (tests, spec clarifications), and presenting a summary -- this is not trivial. The user's mental model after reading the synthesis report is "review is done, what do I do next?" -- not "more analysis is running."

**Suggestion:** Replace the auto-chain with a single consent-gated option inside a consolidated escalation prompt (see Issue 4 below). The rewrite should have zero auto-invocations of interpeer. Every interpeer escalation path must go through AskUserQuestion.

### Issue 2: Three sequential decision prompts create decision fatigue

**Location:** `cross-ai.md` Steps 4.1 (line 7), 4.3 (line 31), 4.4 (line 51)

**Problem:** Phase 4 presents up to three separate decision moments in sequence:
1. Step 4.1: "Want a second opinion? /clavain:interpeer" (when Oracle absent)
2. Step 4.3: Auto-runs mine mode (no decision, but the user must consume its output before the next prompt)
3. Step 4.4: "Options: 1. Resolve now, 2. Run interpeer council, 3. Continue without escalation"

Each prompt introduces vocabulary the user has not seen in the flux-drive context: "interpeer," "mine mode," "council mode." The interpeer skill has four modes (quick, deep, council, mine), each with distinct semantics. Expecting the user to absorb this taxonomy after a 5-minute wait and a full synthesis report is unrealistic.

This is a textbook progressive-disclosure failure: advanced concepts are front-loaded at the user's lowest attention point instead of being available on demand.

**Suggestion:** Collapse all escalation options into one prompt with one decision moment. Present the cross-AI classification results (the table from Step 4.2) inline, then offer a single AskUserQuestion with concrete, self-documenting options:

```
AskUserQuestion:
  question: "Cross-AI found D disagreements. Escalate?"
  options:
    - label: "Resolve disagreements"
      description: "Extract conflicts into tests/specs (~1 min)"
    - label: "Full council"
      description: "Multi-model consensus on critical decisions (~5 min)"
    - label: "Done"
      description: "Finish review"
```

Each option label is a verb phrase (actionable). Each description states what the user gets and how long it takes. No jargon ("mine mode," "interpeer") leaks into the user-facing surface. The orchestrator maps these to the correct interpeer modes internally.

### Issue 3: The interpeer suggestion in Step 4.1 is a dead-end reference

**Location:** `cross-ai.md` lines 7-14 (Step 4.1: when Oracle was not in roster)

**Problem:** When Oracle was absent, the spec presents:
```
Cross-AI: No Oracle perspective was included in this review.
Want a second opinion? /clavain:interpeer (quick mode) for Claude<->Codex feedback.
```

This is a passive suggestion, not an actionable offer. The user must:
1. Understand what "interpeer" is (never explained in flux-drive context)
2. Know what "quick mode" provides (Claude-to-Codex review)
3. Leave flux-drive mentally to invoke a separate command
4. Decide without knowing how long it takes or what the output looks like

The spec then says "Then stop." -- so this message is literally the last thing the user sees from flux-drive when Oracle is absent, which is the common case. The user's final experience of flux-drive is a cryptic suggestion they cannot act on without further research.

**Suggestion:** Two options for the rewrite:

Option A (preferred): Skip Phase 4 entirely when Oracle was not in the roster. The SKILL.md already says "If neither check passes, skip Cross-AI entirely" for Oracle availability. Extend this: if Oracle did not participate in the roster, Phase 4 has nothing to compare. The interpeer suggestion can live in the Step 3.5 synthesis report as a footer note ("For cross-AI perspective: /clavain:interpeer") where it serves as progressive disclosure rather than a dead end.

Option B: If the rewrite keeps the suggestion, make it an AskUserQuestion with a concrete description: "Run Claude vs Codex comparison? (~30 seconds, quick second opinion)" with Accept/Skip. This turns the dead-end reference into an actionable gate.

### Issue 4: The Step 4.5 summary duplicates Step 3.5 with no defined relationship

**Location:** `cross-ai.md` lines 71-96 (Step 4.5: Final Cross-AI Summary)

**Problem:** After Step 3.5 presents the synthesis report (agent count, top findings, section heat map, file locations), Step 4.5 presents a second summary with a different format:
```
## Cross-AI Review Summary
**Model diversity:** Claude agents (N) + Oracle (GPT-5.2 Pro)
| Finding Type | Count | Confidence |
...
```

The user receives two summaries in sequence. The spec never defines the relationship:
- Does 4.5 replace 3.5? (Then 3.5 was premature.)
- Does 4.5 augment 3.5? (Then they should be one document.)
- Is 4.5 a separate deliverable? (Then where does it go? Step 3.5 already told the user where reports are saved.)

On an 80-column terminal, the Step 4.5 template alone is 20+ lines of markdown table output. After a 5+ minute workflow, the user has already consumed the synthesis report. A second summary with a different shape forces them to mentally reconcile two information hierarchies.

**Suggestion:** In the rewrite, fold cross-AI results into the Step 3.5 report as an addendum section rather than producing a separate summary. The synthesis report in Step 3.5 already organizes findings by section and convergence. Cross-AI classification (Agreement/Oracle-only/Claude-only/Disagreement) is metadata about those same findings -- it belongs in the same document, not a separate output step.

Concretely: after Step 3.4 writes back and before Step 3.5 presents the report, append a "Cross-AI Dimension" section to the synthesis if Oracle participated. Then Step 3.5 presents one unified report. Phase 4 becomes purely about the escalation decision, not about presenting more information.

### Issue 5: The cross-AI classification table is valuable but buried

**Location:** `cross-ai.md` lines 18-29 (Step 4.2: Compare Model Perspectives)

**Problem:** The four-category classification (Agreement, Oracle-only, Claude-only, Disagreement) is the genuine value of Phase 4. It transforms raw findings into a decision-support matrix. But in the current spec, this table is an intermediate step that leads to auto-chaining (Step 4.3) rather than being presented directly to the user.

The user never gets to simply see "3 agreements, 2 Oracle-only, 0 disagreements" and decide what to do with that information. Instead, the spec immediately acts on it: "If any disagreements were found in Step 4.2 [then auto-chain]." The classification is treated as control flow logic rather than user-facing output.

**Suggestion:** In the rewrite, present the classification table directly to the user as part of the synthesis report (see Issue 4 suggestion). Let the user absorb the cross-AI comparison before any escalation prompt. The numbers themselves are the most useful output of Phase 4 -- a user who sees "0 disagreements, 2 Oracle-only" knows immediately that Oracle found blind spots worth reviewing but there is no conflict to resolve. No further prompts needed.

### Issue 6: Step 4.4's options assume expertise the user does not have

**Location:** `cross-ai.md` lines 51-69 (Step 4.4: Offer Interpeer Council)

**Problem:** The three options presented are:
1. "Resolve now -- I'll synthesize the best recommendation"
2. "Run interpeer council -- full multi-model consensus review"
3. "Continue without escalation"

Option 1 is clear. Option 3 is clear. Option 2 requires the user to know:
- What "interpeer council" is (a multi-model review process)
- What models are involved (GPT-5.2 Pro, Claude, possibly Gemini)
- How long it takes (unstated -- the interpeer spec says "Slowest")
- What they get that they do not already have (unstated)
- Whether the additional time is worthwhile for this specific decision (no context provided)

The spec provides no guidance on when Option 2 is better than Option 1. A user who has never used interpeer will always choose Option 1 (fastest, clearest) or Option 3 (done). Option 2 is effectively inaccessible to new users.

**Suggestion:** If the rewrite keeps a council escalation option, the AskUserQuestion description must be self-contained:
```
- label: "Multi-model council"
  description: "GPT + Claude + Codex debate this decision independently, then synthesize (~5 min)"
```
Name the models. State the time. Describe the mechanic ("debate independently, then synthesize") so the user understands the value proposition without knowing what "council mode" means.

### Issue 7: No skip condition in SKILL.md for absent Oracle

**Location:** `/root/projects/Clavain/skills/flux-drive/SKILL.md` lines 248-251 (Phase 4 section)

**Problem:** The SKILL.md Phase 4 section says:
```
## Phase 4: Cross-AI Escalation (Optional)

**Read the cross-AI phase file now:**
- Read `phases/cross-ai.md` (in the flux-drive skill directory)
```

The word "Optional" is in the heading, but there is no skip condition. The orchestrator must read cross-ai.md to discover (in Step 4.1) that it should stop if Oracle was absent. This wastes a file read and creates a control flow that goes: read file -> check condition -> stop.

The SKILL.md already has Oracle availability detection in the roster section (lines 212-216). It knows whether Oracle participated before reaching Phase 4.

**Suggestion:** Add a skip condition directly in SKILL.md before the file-read instruction:

```markdown
## Phase 4: Cross-AI Escalation (Optional)

**Skip this phase if Oracle was not in the review roster.**

If Oracle participated, read `phases/cross-ai.md` now.
```

This saves a file read, makes the flow explicit, and prevents the orchestrator from loading 30-40 lines of instructions it will immediately discard. The bead (Clavain-ne6) already calls for this.

### Issue 8: Terminal width concerns for the classification table

**Location:** `cross-ai.md` lines 22-29 (Step 4.2 table)

**Problem:** The classification table has four columns: Category, Definition, Count. The "Definition" column contains phrases like "Oracle found something no Claude agent raised" (43 characters). Combined with the Category column (15 characters) and table formatting characters, a single row exceeds 80 characters:

```
| Oracle-only    | Oracle found something no Claude agent raised | Potential blind spot |
```

That line is 83 characters. On an 80-column terminal (the minimum supported width in this project's conventions), it wraps mid-cell, breaking the table rendering. Most terminal markdown renderers do not gracefully handle wrapped table rows -- the user sees misaligned columns.

**Suggestion:** In the rewrite, shorten the definition column or restructure as a list:
```
Cross-AI Classification:
- 3 agreements (high confidence)
- 2 Oracle-only findings (potential blind spots)
- 1 Claude-only finding (codebase-specific context)
- 0 disagreements
```

A list format is inherently width-flexible, renders correctly at any terminal width, and is easier to scan than a table with one data row per category. It also eliminates the "Count" column since the count is inline.

---

## Summary

### Overall UX Impact: Regression (current spec) -> Improvement (if rewrite follows recommendations)

The current 97-line Phase 4 degrades the user experience at the worst possible moment: after a 5+ minute investment when the user wants to act on findings, not consume more analysis. The rewrite to 30-40 lines is the correct scope.

### Top 3 Changes for Better User Experience

**1. Replace all auto-chaining with a single consent-gated escalation prompt.**
The rewrite must have exactly one AskUserQuestion after presenting cross-AI classification results. Zero auto-invocations of interpeer. Every escalation path (disagreement resolution, council, skip) appears as an option in that single prompt with time estimates and plain-language descriptions. No interpeer jargon in user-facing text.

**2. Fold cross-AI classification into the Step 3.5 synthesis report instead of producing a separate summary.**
The user should receive one report, not two. Cross-AI results (Agreement/Oracle-only/Claude-only/Disagreement counts) are metadata about the same findings already in the synthesis. Append them as a section within the existing report. Phase 4 then becomes purely a decision point ("escalate or done?"), not an information-delivery step.

**3. Add the skip condition in SKILL.md so Phase 4 never loads when Oracle is absent.**
The common case (Oracle unavailable) should cost zero: no file read, no dead-end interpeer suggestion, no "Optional" phase that runs only to tell the user there is nothing to do. The interpeer suggestion belongs as a footer note in the Step 3.5 report, not as Phase 4's only output in the Oracle-absent path.

### Rewrite Target Structure (~30-40 lines)

Based on the analysis above, the rewritten cross-ai.md should follow this structure:

```
Phase 4: Cross-AI Escalation

(SKILL.md already gates: only entered when Oracle participated)

Step 4.1: Classify findings
- Compare oracle-council.md against synthesis
- Categorize: Agreement / Oracle-only / Claude-only / Disagreement
- Append classification as a section in the synthesis report or summary.md

Step 4.2: Present escalation options (if disagreements or P0 Oracle-only findings exist)
- Single AskUserQuestion with:
  - "Resolve disagreements" (maps to interpeer mine, ~1 min)
  - "Multi-model council" (maps to interpeer council, ~5 min) -- only if P0/security
  - "Done" (finish review)
- If no disagreements and no P0 Oracle-only findings, skip prompt entirely

Step 4.3: Execute chosen escalation
- Run selected interpeer mode inline
- Append results to synthesis report
```

This reduces five steps to three, eliminates the auto-chain, consolidates the summary, and costs zero user attention when there is nothing to escalate.
