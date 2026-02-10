# Phase 4 (Cross-AI Escalation) -- User Flow Analysis

**Date:** 2026-02-09
**Bead:** Clavain-ne6
**Target:** Rewrite from 97 lines to ~30-40 lines
**Scope:** Add consent gate, consolidate Steps 4.3-4.5, keep classification, add Oracle-absent skip

---

## 1. User Flow Overview

Phase 4 activates after Phase 3 synthesis completes. It has two major branches (Oracle present vs. absent) and multiple sub-branches within each.

### Current Spec Flow (97 lines)

```
Phase 3 complete
  |
  v
Step 4.1: Was Oracle in the roster?
  |
  +-- NO --> Print "Want a second opinion? /clavain:interpeer (quick mode)"
  |          --> STOP (dead end)
  |
  +-- YES --> Step 4.2: Compare Oracle vs Claude findings
               |
               v
             Classify: Agreement / Oracle-only / Claude-only / Disagreement
               |
               v
             Step 4.3: Any disagreements?
               |
               +-- YES --> AUTO-RUN interpeer mine mode (NO CONSENT)
               |            |
               |            v
               |          Step 4.4: Any critical decisions?
               |            |
               |            +-- YES --> Offer 3 options:
               |            |            1. Resolve now (synthesize)
               |            |            2. Run interpeer council
               |            |            3. Continue without escalation
               |            |
               |            +-- NO --> Skip to 4.5
               |
               +-- NO --> Step 4.4: Any P0/P1 Oracle-only findings?
                            |
                            +-- YES --> Offer council escalation (same 3 options)
                            +-- NO --> Skip to 4.5
               |
               v
             Step 4.5: Print Cross-AI Summary table
               --> END
```

### Proposed Rewrite Flow (30-40 lines)

```
Phase 3 complete
  |
  v
Was Oracle in the roster?
  |
  +-- NO --> Mention interpeer availability
  |          --> END (Phase 4 skipped)
  |
  +-- YES --> Classify findings (Agreement/Oracle-only/Claude-only/Disagreement)
               |
               v
             Present classification table
               |
               v
             Any disagreements OR critical Oracle-only findings?
               |
               +-- NO --> Print summary, END
               |
               +-- YES --> CONSENT GATE (AskUserQuestion):
                            "D disagreements / K critical findings. Escalate?"
                            |
                            +-- "Resolve" --> Run consolidated interpeer prompt
                            |                  (mine + optional council in one pass)
                            +-- "Skip"    --> Print summary, END
```

---

## 2. All Distinct User Journeys

### Journey 1: Oracle Absent (Most Common Path)

**Trigger:** Oracle not in the roster (either unavailable or scored below threshold).

**Current behavior:** Print a suggestion line referencing `/clavain:interpeer (quick mode)` and stop.

**User experience:** The user has just received the Phase 3 synthesis report. They see a one-line mention of a tool they may never have used. No explanation of what it does, what it costs, or how long it takes. This is a dead-end informational message.

**Frequency:** This is the majority case. Oracle requires Xvfb, Chrome, and a ChatGPT session. Most environments will not have all three.

### Journey 2: Oracle Present, Zero Disagreements, No Critical Findings

**Trigger:** Oracle participated but agreed with Claude agents on everything, and no P0/P1 Oracle-only findings.

**Current behavior:** Steps 4.1 (detect) -> 4.2 (classify) -> 4.3 skipped (no disagreements) -> 4.4 skipped (no critical findings) -> 4.5 (summary table).

**User experience:** The user sees a classification table and a summary table. Both are informational. No decisions required. This is the happy path when Oracle adds confidence without surfacing novel concerns.

### Journey 3: Oracle Present, Disagreements Exist, No Critical Decisions

**Trigger:** Oracle and Claude agents disagree on at least one finding, but none meet the "critical" threshold (no P0, no security/architecture disagreement).

**Current behavior:** Steps 4.1 -> 4.2 -> 4.3 AUTO-RUNS interpeer mine mode (no consent) -> 4.4 skipped (no critical decisions) -> 4.5 (summary table with mine mode artifacts).

**User experience:** The user sees the classification table, then suddenly the system announces "Disagreements detected. Running interpeer mine mode..." and begins processing. The user did not ask for this, was not warned, and does not know how long it will take. After mine mode completes, they see a summary. This is the primary consent gap identified by fd-user-experience (P1-5).

### Journey 4: Oracle Present, Disagreements + Critical Decision

**Trigger:** Disagreements exist AND at least one meets the "critical" criteria (P0, security, or architecture topic).

**Current behavior:** Steps 4.1 -> 4.2 -> 4.3 AUTO-RUNS mine mode -> 4.4 OFFERS council escalation (3 options) -> 4.5 (summary).

**User experience:** The most complex path. The user experiences an unconsented auto-chain (mine mode), then immediately faces a decision prompt with three options using vocabulary they may not know ("interpeer council", "multi-model consensus review"). Two decision points in rapid succession, one without consent and one with.

### Journey 5: Oracle Present, No Disagreements, but P0/P1 Oracle-Only Findings

**Trigger:** No direct disagreements, but Oracle raised severe findings (P0/P1) that no Claude agent flagged.

**Current behavior:** Steps 4.1 -> 4.2 -> 4.3 skipped (no disagreements) -> 4.4 OFFERS council (critical decision detected because Oracle flagged P0/P1 that Claude missed).

**User experience:** The user sees the classification table with "Oracle-only: N (review these)" and then gets the council escalation offer. No auto-chain here. This is a reasonable flow but depends on the user understanding what "Oracle-only" means and why council mode might help.

### Journey 6: Oracle Present but Failed/Timed Out

**Trigger:** Oracle was in the roster and launched, but the `oracle` CLI timed out (exit 124) or failed.

**Current behavior:** Per SKILL.md lines 229-231: "If the Oracle command fails or times out, note it in the output file and continue without Phase 4. Do NOT block synthesis on Oracle failures -- treat it as 'Oracle: no findings' and skip Steps 4.2-4.5."

**User experience:** Phase 4 is silently skipped. The user may not even know Oracle was supposed to participate, depending on whether Phase 2 or 3 mentioned it. The oracle-council.md file in OUTPUT_DIR contains the failure notice, but the user is not explicitly told "Oracle failed, skipping cross-AI analysis."

### Journey 7: User Chooses "Resolve Now" at Step 4.4

**Trigger:** Critical decision detected, user picks option 1 ("Resolve now -- I'll synthesize the best recommendation").

**Current behavior:** The spec says "I'll synthesize the best recommendation from available perspectives." This is an inline synthesis by the current Claude session. No external tool invocation.

**User experience:** A reasonable default. The user gets a recommendation without additional wait time.

### Journey 8: User Chooses "Run interpeer council" at Step 4.4

**Trigger:** Critical decision detected, user picks option 2.

**Current behavior:** Invoke interpeer in council mode for just the critical decision. This chains to the interpeer skill, which itself has a multi-phase pipeline: Claude forms opinion -> build Oracle prompt -> user reviews prompt -> execute Oracle -> synthesize.

**User experience:** The user is now deep in a nested workflow. They approved flux-drive (Phase 1), waited for agents (Phase 2-3), got auto-chained to mine mode (Step 4.3), and now enter interpeer council mode which has its OWN user review gate (interpeer's Phase 3: "Approve this Oracle prompt?"). This is three levels deep with two separate consent mechanisms.

### Journey 9: User Chooses "Continue without escalation" at Step 4.4

**Trigger:** Critical decision detected, user picks option 3.

**Current behavior:** Proceed to Step 4.5 summary.

**User experience:** Clean exit. The user sees the summary and the review ends.

---

## 3. Flow Permutations Matrix

| # | Oracle Available | Oracle Participated | Oracle Succeeded | Disagreements | Critical Findings | User Decision | Outcome |
|---|-----------------|--------------------|--------------------|---------------|-------------------|---------------|---------|
| 1 | No | No | N/A | N/A | N/A | None needed | Interpeer suggestion, STOP |
| 2 | Yes | Yes | Yes | 0 | None | None needed | Classification table + summary |
| 3 | Yes | Yes | Yes | >0 | None | NONE (auto-chain) | Mine mode auto-runs, then summary |
| 4 | Yes | Yes | Yes | >0 | Yes | 3 options | Mine mode auto-runs, then council offer |
| 5 | Yes | Yes | Yes | 0 | Yes (Oracle-only P0/P1) | 3 options | Classification + council offer |
| 6 | Yes | Yes | No (timeout/fail) | N/A | N/A | None needed | Phase 4 silently skipped |
| 7 | Yes | Yes | Yes | >0 | Yes | "Resolve now" | Mine auto-runs, inline synthesis |
| 8 | Yes | Yes | Yes | >0 | Yes | "Council" | Mine auto-runs, then interpeer council pipeline |
| 9 | Yes | Yes | Yes | >0 | Yes | "Skip" | Mine auto-runs, then summary |
| 10 | Yes | No (scored below cap) | N/A | N/A | N/A | None needed | Same as #1 |
| 11 | Yes | Yes | Partial (empty output) | ? | ? | ? | UNSPECIFIED |

### Dimensions Not Covered

| Dimension | Current Spec | Gap |
|-----------|-------------|-----|
| First-time user vs. returning | No distinction | First-time users lack vocabulary for interpeer/mine/council |
| Multiple critical decisions | Step 4.4 says "a critical decision" (singular) | What if there are 3 separate critical decisions? |
| Oracle returns empty but exits 0 | Not addressed | Empty output parses as "no findings" but is semantically different from "I have no concerns" |
| Partial Oracle output (truncated) | Not addressed | A timeout during write could produce partial content |
| Extremely long Oracle output | Not addressed | Oracle sometimes returns very long responses; classification must handle scale |
| Network failure during mine/council | Not addressed | If interpeer fails mid-chain, there is no recovery spec |

---

## 4. Missing Elements and Gaps

### 4.1 Consent Gaps

**GAP-1: Step 4.3 auto-chains without user consent (CRITICAL)**
- **What is missing:** An AskUserQuestion gate before invoking interpeer mine mode.
- **Impact:** This is the ONLY significant unconsented action in the entire flux-drive spec. Every other consequential action (agent launch in Step 1.3, document write-back in Step 3.4, council escalation in Step 4.4) has a confirmation gate. Step 4.3 breaks the consent pattern.
- **Current ambiguity:** The spec says "Disagreements detected. Running interpeer mine mode to extract actionable artifacts..." with no option to decline.
- **What the rewrite must do:** Replace auto-chain with a consent gate. The bead already calls for this.

**GAP-2: No consent for the entire Phase 4 classification exercise**
- **What is missing:** The user is never asked "Would you like cross-AI analysis?" The classification just happens.
- **Impact:** Low. Classification is read-only analysis (comparing findings). The issue is not consent but information overload -- the user just received Phase 3 synthesis and now gets more tables.
- **Recommendation for rewrite:** The consent gate should wrap the entire escalation offer, not just mine mode. Present classification results as context within the consent prompt, not as a separate preceding step.

### 4.2 Dead-End Flows

**GAP-3: Oracle-absent suggestion is a dead end (P2)**
- **What is missing:** When Oracle is absent, the spec prints "/clavain:interpeer (quick mode)" with no context. The user must know what interpeer is, leave flux-drive, and invoke a separate command.
- **Impact:** The suggestion is effectively a no-op. Users who do not already know interpeer will ignore it. Users who do know interpeer do not need the suggestion.
- **Recommendation for rewrite:** Either make the suggestion actionable (offer to run interpeer quick mode inline) or drop it entirely. A 30-40 line Phase 4 should not spend lines on dead-end suggestions.

**GAP-4: No path from classification back to synthesis**
- **What is missing:** If the classification reveals Oracle-only findings (blind spots) that are NOT critical (not P0, not security), there is no mechanism to incorporate them. They appear in the classification table and the summary, but they do not feed back into the Issues to Address checklist from Phase 3.
- **Impact:** Oracle-only findings at P2/P3 severity are presented but never actionable. They exist only in the cross-AI summary (Step 4.5) which is a separate artifact from the Phase 3 synthesis.
- **Recommendation for rewrite:** Fold Oracle-only findings into the Phase 3 synthesis output. The classification should augment the existing findings, not create a parallel summary.

### 4.3 Error Handling Gaps

**GAP-5: Oracle timeout behavior is specified in SKILL.md but not in cross-ai.md**
- **What is missing:** cross-ai.md does not mention what happens if Oracle failed. The error handling lives in SKILL.md (lines 229-231): "treat it as 'Oracle: no findings' and skip Steps 4.2-4.5." But cross-ai.md itself has no conditional for this case.
- **Impact:** The spec files are inconsistent. A reader of cross-ai.md alone would not know that Phase 4 can be silently skipped.
- **Recommendation for rewrite:** The rewritten Phase 4 should start with "If Oracle failed or produced no findings, skip this phase" as an explicit guard clause.

**GAP-6: What if interpeer mine mode fails?**
- **What is missing:** Step 4.3 invokes interpeer mine mode inline ("do not dispatch a subagent -- this runs in the main session"). If mine mode fails (e.g., cannot structure the disagreement, hits an error), there is no fallback.
- **Impact:** The user is stuck mid-chain with no recovery path. Phase 4 would hang or produce an error with no graceful degradation.
- **Recommendation for rewrite:** Since the rewrite adds a consent gate, this is less critical -- the user chose to escalate. But the rewrite should specify: "If escalation fails, present what classification data is available and end Phase 4."

**GAP-7: What if interpeer council mode fails?**
- **What is missing:** Step 4.4 option 2 invokes interpeer council mode, which itself calls Oracle again. Oracle could fail a second time (it already timed out once in the self-review). The spec does not address Oracle failing during council.
- **Impact:** The user chose council mode because of a critical decision, Oracle fails again, and there is no specified degradation path. The interpeer skill has its own error handling (retry, switch modes, fall back to quick), but the flux-drive spec does not reference or rely on it.
- **Recommendation for rewrite:** Trust interpeer's error handling. The rewrite does not need to re-specify it. Just ensure the consent prompt mentions the time cost ("~5 min") so the user can make an informed choice.

**GAP-8: Oracle returns empty output (exits 0, writes 0 bytes)**
- **What is missing:** The Oracle error handling checks for failure exit codes. But Oracle can succeed (exit 0) while producing empty output -- for example, if the ChatGPT session expired mid-response or if the browser captured no text.
- **Impact:** Step 4.2 would classify zero findings as "Oracle found nothing." This is semantically different from "Oracle agrees everything is fine" but the spec treats them identically. An empty Oracle response could mask a tool failure.
- **Recommendation for rewrite:** Add "If oracle-council.md is empty or under 50 bytes, treat as Oracle failure, not as Oracle having zero findings."

### 4.4 Specification Ambiguities

**GAP-9: "Critical" decision criteria are subjective**
- **What is missing:** Step 4.4 defines critical decisions by three indicators: P0 from any source, disagreement on architecture/security, Oracle flagged security that Claude missed. These are listed as indicators, not as strict criteria. The spec does not say how many indicators must be present or who decides.
- **Impact:** The orchestrating LLM must exercise judgment. Different runs with the same findings may or may not trigger the council offer. This is acceptable for an LLM-driven workflow but should be explicitly acknowledged.
- **Recommendation for rewrite:** Keep the criteria as guidelines (they work fine for LLM judgment). But in the consent prompt, show the user what triggered the escalation offer so they can evaluate it themselves.

**GAP-10: Step 4.5 summary duplicates Phase 3 report**
- **What is missing:** Step 4.5 generates a "Cross-AI Review Summary" with its own table format. Step 3.5 already generated a synthesis report. The spec does not define the relationship.
- **Impact:** The user receives two summary artifacts in sequence. Do they replace each other? Is 4.5 an addendum to 3.5? Should 4.5 be merged into the synthesis output file? The spec is silent.
- **Recommendation for rewrite:** Eliminate Step 4.5 as a separate output. The classification data should be folded into the Phase 3 synthesis (either inline or as an appendix to summary.md). One summary, not two.

**GAP-11: "Disagreement" vs. "Oracle-only" vs. "Claude-only" classification is fuzzy**
- **What is missing:** The table in Step 4.2 defines four categories but does not specify how to classify findings that are similar-but-not-identical. If Oracle says "SQL injection risk in auth handler" and a Claude agent says "input validation missing in auth handler," is that Agreement, Disagreement, or one of each?
- **Impact:** Classification quality depends entirely on the LLM's judgment in matching findings across models. This is inherently fuzzy and the spec should acknowledge it rather than presenting it as a clean four-way split.
- **Recommendation for rewrite:** Keep the four categories but frame them as approximate: "Classify findings into the following categories (use best judgment for partial overlaps)."

**GAP-12: interpeer mine mode invocation details are unspecified**
- **What is missing:** Step 4.3 says "invoke interpeer in mine mode inline" and lists three sub-steps, but does not specify how to invoke interpeer. Is it a skill invocation? A function call? Direct execution of the mine mode steps? The "(do not dispatch a subagent -- this runs in the main session)" note suggests direct execution, but the interpeer skill has prerequisites (prior Oracle/GPT output must exist in context).
- **Impact:** The implementer must decide whether to use `Task` tool to invoke interpeer or to inline the mine mode logic. These produce different results: Task creates a subagent with limited context, while inlining means manually following interpeer's mine mode steps.
- **Recommendation for rewrite:** Clarify that mine mode steps are executed inline by the orchestrator, not via subagent dispatch. The orchestrator already has both Oracle and Claude findings in context (from Step 4.2), so the interpeer mine mode prerequisite ("prior Oracle/GPT output exists in context") is satisfied.

### 4.5 Missing from the Rewrite Plan

**GAP-13: The rewrite plan says "add skip condition in SKILL.md when Oracle absent" but does not specify what SKILL.md should say**
- **What is missing:** The bead specifies that SKILL.md should have a skip condition, but does not define the wording or placement.
- **Impact:** The SKILL.md currently says "Read `phases/cross-ai.md`" for Phase 4. The skip condition needs to be in SKILL.md (before the file read) so that the orchestrator does not even load the phase file when Oracle is absent.
- **Recommendation:** Add to SKILL.md Phase 4 section: "If Oracle was not in the roster or Oracle failed, skip Phase 4. Optionally mention `/clavain:interpeer` for cross-AI options."

**GAP-14: Consolidated prompt scope is undefined**
- **What is missing:** The bead says "simplify Steps 4.3-4.5 auto-chain into a single consolidated prompt." But what exactly goes into this prompt? Does it offer mine mode, council mode, or both? Does it include the classification table? Does it present different options depending on severity?
- **Impact:** Without defining the consolidated prompt, the rewrite could produce anything from a simple "Escalate? [Y/N]" to a complex multi-option menu that reproduces the same decision fatigue the rewrite is trying to fix.
- **Recommendation:** Define the prompt explicitly. See Section 6 below for a proposed template.

---

## 5. Critical Questions Requiring Clarification

### Critical (Blocks Implementation)

**Q1: Should the consolidated prompt offer mine mode, council mode, or both?**
- Why it matters: The original spec chains mine -> council sequentially. The rewrite collapses them. If the consolidated prompt offers both as separate options, the user faces the same vocabulary problem. If it offers only one ("Escalate?"), the user loses granularity.
- Assumption if unanswered: Offer a single "Investigate disagreements" option that runs mine mode inline. Council mode is not offered from flux-drive; users who want it invoke interpeer separately.
- Example: User sees "3 disagreements found. [Investigate] [Skip]" vs. "3 disagreements found. [Quick resolve] [Full council (~5 min)] [Skip]"

**Q2: What happens when the user declines escalation?**
- Why it matters: If the user says "Skip" at the consent gate, should they still see the classification table? Or does declining mean Phase 4 produces no output at all?
- Assumption if unanswered: The classification table is always presented (it is read-only analysis with no cost). The consent gate only gates the interpeer invocation.
- Example: User declines -> still sees "Agreements: 5, Oracle-only: 2, Disagreements: 1" but does not run mine mode.

**Q3: Should Oracle-only findings be folded into the Phase 3 synthesis output?**
- Why it matters: Currently, Oracle-only findings live only in the Phase 4 summary. If Phase 4 is simplified, these findings might be lost -- they exist in oracle-council.md but are not surfaced in the Issues to Address checklist.
- Assumption if unanswered: Yes. Oracle is just another agent. Its unique findings should be in the synthesis, marked as "Oracle-only (review for blind spots)."
- Impact: This changes Phase 3 behavior, not just Phase 4. Phase 3 synthesis (Step 3.3) would need to handle Oracle's output the same as any other agent, with a tag noting it came from a different model family.

### Important (Significantly Affects UX)

**Q4: Should the Oracle-absent path mention interpeer at all?**
- Why it matters: The current spec's interpeer suggestion is a dead-end reference (GAP-3). The rewrite targets 30-40 lines. Spending 2-3 lines on a suggestion that is rarely actionable may not be worth the space.
- Assumption if unanswered: One line: "For cross-AI perspectives, see `/clavain:interpeer`." No elaboration.

**Q5: Where does the classification output go?**
- Why it matters: Currently, Step 4.5 produces a markdown block. The rewrite eliminates 4.5. Does the classification appear only in the terminal output? Is it appended to `{OUTPUT_DIR}/summary.md`? Written to a separate file?
- Assumption if unanswered: Appended to `{OUTPUT_DIR}/summary.md` under a "Cross-AI Comparison" heading.

**Q6: How should the rewrite handle multiple critical decisions?**
- Why it matters: Step 4.4 says "if any finding represents a critical architectural or security decision" (singular "a"). But there could be 3 critical decisions. Does the user get one consent prompt covering all of them, or one per critical decision?
- Assumption if unanswered: One consolidated prompt covering all critical findings. The prompt lists them: "2 critical decisions detected: [brief descriptions]. Escalate? [Y/N]"

### Nice-to-Have (Improves Clarity)

**Q7: Should the rewrite preserve the four-category classification table?**
- Why it matters: The classification table (Agreement/Oracle-only/Claude-only/Disagreement) is 10 lines of the current spec. In a 30-40 line target, it would be 25-33% of the content. An alternative is to simplify to two categories: "Confirmed" (agreement) and "Needs review" (everything else).
- Assumption if unanswered: Keep all four categories. The classification is the core value of Phase 4 per the bead description.

**Q8: Should the rewrite specify the Oracle failure threshold (GAP-8)?**
- Why it matters: Empty Oracle output is an edge case that produces misleading classification ("Oracle found nothing"). A 50-byte threshold is arbitrary but better than nothing.
- Assumption if unanswered: Add a one-line guard: "If oracle-council.md is empty or contains only the error handler's output, treat as Oracle failure."

---

## 6. Recommended Consolidated Prompt Template

Based on the analysis above, the rewritten Phase 4 consent gate should look like this:

```
AskUserQuestion:
  question: |
    Cross-AI comparison: A agreements, B Oracle-only, C Claude-only, D disagreements.
    [If D > 0:] Investigate D disagreement(s)? (~1-2 min, runs conflict analysis inline)
    [If critical:] Critical finding detected: [brief]. Run multi-model council? (~5 min)
  options:
    - label: "Investigate"
      description: "Run disagreement analysis (mine mode) inline"
    [If critical, add:]
    - label: "Council"
      description: "Full multi-model review for critical decision (~5 min)"
    - label: "Skip"
      description: "End review with current findings"
```

Key properties of this design:
1. Classification is presented as context within the prompt, not a separate step
2. One decision point, not three sequential ones
3. Time estimates are included so the user can evaluate the cost
4. Options are labeled with plain language, not tool vocabulary
5. "Skip" is always available and is the last option (default safe exit)

---

## 7. Recommended Rewrite Structure (30-40 Lines)

```
# Phase 4: Cross-AI Comparison (Optional)

## Guard Clause (2 lines)
- If Oracle was not in the roster or oracle-council.md is empty/failed: skip Phase 4.
- Optionally note interpeer availability for manual cross-AI review.

## Classification (8-10 lines)
- Read oracle-council.md
- Compare Oracle findings against Phase 3 synthesis
- Classify into: Agreement, Oracle-only, Claude-only, Disagreement
- Fold Oracle-only findings into the synthesis (append to summary.md)

## Consent Gate (10-12 lines)
- Present classification summary in a single AskUserQuestion
- Offer "Investigate" (mine mode inline) if disagreements exist
- Offer "Council" (interpeer council) if critical findings exist
- Offer "Skip" always
- If user declines: Phase 4 ends with classification data already folded into synthesis

## Escalation (8-10 lines)
- If "Investigate": Run interpeer mine mode steps inline
  - Structure disagreements as conflicts
  - Generate resolution evidence (tests, spec clarifications)
  - Present summary
- If "Council": Invoke interpeer council mode for the critical decision
- If escalation fails: present available classification data, end Phase 4

Total: ~30-34 lines
```

---

## 8. SKILL.md Skip Condition

The following should be added to the Phase 4 section of SKILL.md (currently at line 249):

**Current:**
```
## Phase 4: Cross-AI Escalation (Optional)

**Read the cross-AI phase file now:**
- Read `phases/cross-ai.md` (in the flux-drive skill directory)
```

**Proposed:**
```
## Phase 4: Cross-AI Comparison (Optional)

If Oracle was not in the roster or oracle-council.md does not exist / is empty,
skip Phase 4. Mention `/clavain:interpeer` for manual cross-AI options.

Otherwise, read `phases/cross-ai.md`.
```

This prevents the orchestrator from loading and parsing a 30-40 line phase file when the precondition (Oracle participated successfully) is not met.

---

## 9. Edge Cases Checklist

| Edge Case | Currently Handled | Rewrite Must Handle |
|-----------|-------------------|---------------------|
| Oracle absent from environment | Yes (SKILL.md line 212-216) | Yes (SKILL.md skip condition) |
| Oracle in roster but timed out | Yes (SKILL.md line 229-231) | Yes (guard clause in Phase 4) |
| Oracle in roster but scored below cap | Implicit (not selected) | Same as "Oracle absent" path |
| Oracle exits 0 but output is empty | NOT HANDLED | Guard clause: treat as failure |
| Oracle output is truncated (partial) | NOT HANDLED | Best-effort classification; note uncertainty |
| Oracle agrees with everything | Handled (Journey 2) | Same: classification + summary, no escalation |
| Multiple critical decisions | AMBIGUOUS (singular language) | Consolidated prompt covers all |
| User declines escalation | NOT HANDLED (auto-chain) | Consent gate: "Skip" option |
| Mine mode fails mid-execution | NOT HANDLED | Graceful degradation: present classification, end |
| Council mode fails (Oracle fails again) | NOT HANDLED (deferred to interpeer) | Trust interpeer error handling |
| Zero Oracle-only findings (all overlap) | Handled (Journey 2) | Same: no escalation needed |
| Oracle raises >10 unique findings | NOT HANDLED (no scale guidance) | Classification still works; mine mode has triage cap of 3-5 |
| User has never heard of interpeer | NOT HANDLED (jargon in prompts) | Plain language in consent gate options |

---

## 10. Files Referenced

| File | Path | Relevance |
|------|------|-----------|
| Phase 4 spec (current) | `/root/projects/Clavain/skills/flux-drive/phases/cross-ai.md` | Primary target for rewrite |
| SKILL.md | `/root/projects/Clavain/skills/flux-drive/SKILL.md` | Skip condition and integration section need updating |
| Interpeer SKILL.md | `/root/projects/Clavain/skills/interpeer/SKILL.md` | Downstream integration: mine mode and council mode specs |
| Synthesize phase | `/root/projects/Clavain/skills/flux-drive/phases/synthesize.md` | Phase 3 output is Phase 4 input; Oracle-only findings may need folding into Step 3.3 |
| Self-review: fd-user-experience | `/root/projects/Clavain/docs/research/flux-drive/flux-drive-self-review/fd-user-experience.md` | Prior analysis identifying consent gap (P1-5) and decision fatigue (P1-2) |
| Self-review: code-simplicity | `/root/projects/Clavain/docs/research/flux-drive/flux-drive-self-review/code-simplicity-reviewer.md` | Prior analysis identifying Phase 4 as YAGNI violation (P1-3) |
| Self-review: summary | `/root/projects/Clavain/docs/research/flux-drive/flux-drive-self-review/summary.md` | P1 items: simplify Phase 4, add consent gate |
| Bead description | `/root/projects/Clavain/docs/research/create-tier-3-beads-simplify.md` | Clavain-ne6 task definition |
