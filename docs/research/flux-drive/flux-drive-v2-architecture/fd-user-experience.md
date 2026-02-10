---
agent: fd-user-experience
tier: adaptive
issues:
  - id: P1-1
    severity: P1
    section: "Phase 5 — Compound"
    title: "New Phase 5 adds post-review processing with no user consent gate and unclear value signal"
  - id: P1-2
    severity: P1
    section: "Ad-hoc Agent Generation"
    title: "Triage-generated ad-hoc agents are invisible — user cannot inspect, reject, or understand what was created"
  - id: P1-3
    severity: P1
    section: "Knowledge Injection"
    title: "Knowledge entries injected per agent are entirely invisible — no way for user to understand what prior context influenced findings"
  - id: P1-4
    severity: P1
    section: "Deep-Pass UX"
    title: "Deep-pass trigger is undefined from the user perspective — no command, no invocation path, no output format"
  - id: P2-1
    severity: P2
    section: "Phase 1 — Triage"
    title: "5-agent triage table is clearer than 19-agent table but ad-hoc row insertion creates unpredictable table length"
  - id: P2-2
    severity: P2
    section: "Phase 5 — Compound"
    title: "Compounding output ('Learned 3 patterns, updated 2 existing') is noise at the user's lowest attention point"
  - id: P2-3
    severity: P2
    section: "Overall Phase Flow"
    title: "5 phases vs 4 phases is heavier only if user sees Phase 5 — if silent, the perceived flow is unchanged"
improvements:
  - id: IMP-1
    title: "Make Phase 5 silent by default with opt-in summary via flag or post-run query"
    section: "Phase 5 — Compound"
  - id: IMP-2
    title: "Show ad-hoc agents as a distinct row type in the triage table with generated description, allowing rejection"
    section: "Phase 1 — Triage"
  - id: IMP-3
    title: "Add a /clavain:flux-deep command for deep-pass instead of leaving it as undefined manual trigger"
    section: "Deep-Pass UX"
  - id: IMP-4
    title: "Expose knowledge injection as a collapsible debug line per agent, not inline in the main flow"
    section: "Knowledge Injection"
  - id: IMP-5
    title: "Cap total agents (core + ad-hoc + Oracle) at 6 as spec says, and enforce this in the triage table display"
    section: "Phase 1 — Triage"
verdict: needs-changes
---

## UX Review: Flux-Drive v2 Architecture

**Reviewer:** fd-user-experience (CLI/TUI interaction specialist)
**Target file:** `/root/projects/Clavain/docs/research/flux-drive-v2-architecture.md`
**Supporting context:** `/root/projects/Clavain/skills/flux-drive/SKILL.md`, `/root/projects/Clavain/skills/flux-drive/phases/*.md`, prior flux-drive run outputs
**Date:** 2026-02-10

---

## UX Assessment

### User Workflows Affected

The architecture redesign changes every phase of the flux-drive workflow. The user currently runs `/flux-drive <document>`, sees a 19-row triage table, approves, waits 3-5 minutes, and reads a synthesis report with optional cross-AI escalation. The v2 proposal restructures what the user sees at nearly every touchpoint: smaller triage table (positive), ad-hoc agent generation mid-triage (potentially confusing), invisible knowledge injection (questionable), a new Phase 5 with compounding (additional wait or noise), and an undefined deep-pass mechanism.

The core question is whether these changes make the system feel smarter or heavier. The answer depends entirely on what the user actually sees -- most of the v2 machinery should be invisible plumbing, but the architecture document does not draw that line clearly.

### Overall Verdict

The structural changes (5 core agents replacing 19, knowledge layer, compounding) are solid engineering decisions. The UX risk is not in the architecture itself but in how much of it leaks to the user's attention. The current spec does not establish which parts are visible and which are silent. Without that boundary, the v2 system will feel heavier than v1 despite being simpler underneath.

---

## Detailed Analysis by Question

### 1. Triage UX: 5 Core + Ad-hoc vs. 19 Static Agents

**Current state:** The user sees a table of up to 19 agents with columns for Agent, Category, Score, Reason, and Action (Launch/Skip). Most runs select 3-8 agents, meaning 11-16 rows are "Skip" rows that the user scans and ignores. This is noisy but predictable -- the user knows the roster is fixed.

**v2 proposal:** The user sees a table of 5 core agents (most selecting 3-5), plus any ad-hoc agents that triage detects, plus Oracle. Cap is 6.

**UX impact: Improvement.** A 5-7 row table is categorically easier to scan than a 19-row table. The user's cognitive load drops from "scan 19 rows, identify which 5 matter" to "scan 5-7 rows, all of which matter." The elimination of "Skip" rows is the single largest UX win in this proposal.

**Remaining risk:** Ad-hoc agent insertion makes the table length unpredictable. If triage generates 1-2 ad-hoc agents, the user sees 7-8 rows instead of the expected 5-6. This is fine as long as ad-hoc agents are visually distinguished from core agents. If they appear as identical rows, the user will not know which agents are established and which were just invented for this run.

**Recommendation:** In the triage table, ad-hoc agents should appear with a distinct marker -- for example, a `[generated]` tag in the Category column or a note in the Reason column saying "Generated for this review: [description]." The user should be able to reject individual ad-hoc agents during the "Edit selection" flow. The table should look like:

```
| Agent                  | Category         | Score | Reason                           | Action |
|------------------------|------------------|-------|----------------------------------|--------|
| Architecture & Design  | Core             | 3     | Module boundaries affected       | Launch |
| Safety & Correctness   | Core             | 2     | API adds endpoints               | Launch |
| Quality & Style        | Core             | 2     | Go code changes                  | Launch |
| GraphQL Schema Review  | Generated (new)  | --    | GraphQL schema detected, no core | Launch |
| Oracle                 | Cross-AI         | +1    | Diversity bonus                  | Launch |
```

The `Generated (new)` tag tells the user this agent was just created. The `--` score tells them it was not scored from a static roster. The user can drop it during "Edit selection" if they do not trust a generated agent for this domain.

### 2. Ad-hoc Agent Generation: Visibility and Control

**Current spec gap:** The architecture document says triage "generates new ad-hoc agent prompt on the fly" but does not specify what the user sees when this happens. Does the user see: (a) just a new row in the triage table, (b) the generated agent's focus description, (c) the full prompt, or (d) nothing until synthesis?

**Problem:** If the user cannot see what the ad-hoc agent will do, they cannot make an informed decision at the approval gate. The existing approval flow ("Launch N agents for flux-drive review?") works because the user recognizes agent names from the static roster. A generated agent named "GraphQL Schema Review" is self-documenting; one named "ad-hoc-1" is opaque.

**Recommendations:**

1. **Naming:** Generated agents must have descriptive names derived from the detected domain, not generic labels. "GraphQL Schema Review" or "Accessibility Audit" -- not "ad-hoc-agent-1."

2. **Description:** The triage table should include a 1-line description of what the generated agent will focus on, visible before the approval gate. Example: "Evaluates GraphQL schema design, resolver patterns, and N+1 query risks."

3. **Rejection:** The user must be able to remove a generated agent during "Edit selection." This is already possible with the existing flow but should be explicitly called out for generated agents.

4. **Reuse transparency:** When triage finds a saved ad-hoc agent from a previous run in `.claude/flux-drive/agents/`, the triage table should indicate this with `Generated (saved)` rather than `Generated (new)`. This tells the user the agent has been used before and is not being invented on the spot.

5. **Graduation notice:** When a project-local ad-hoc agent is promoted to Clavain-global, this should NOT happen during a review run. It should happen during the deep-pass or via an explicit user action. Silently graduating agents is invisible infrastructure mutation.

### 3. Knowledge Injection Transparency

**The question:** Should users know what knowledge entries were injected into each agent?

**Answer: No, not by default. But yes, on demand.**

Knowledge injection is plumbing. The user cares about findings, not about what context informed them. Showing "Injected 3 knowledge entries into Safety & Correctness agent" in the main flow is noise at the same level as showing the agent's system prompt -- technically true, operationally irrelevant.

However, there are two scenarios where visibility matters:

1. **Debugging false positives.** If the Safety agent flags something as a P0 based on a stale knowledge entry from 6 months ago, the user needs to trace why. Without knowledge visibility, they cannot distinguish "the agent found this independently" from "the agent was primed to find this by injected context."

2. **Trust calibration.** A sophisticated user running flux-drive on a mature project may want to know what the system "remembers" about their codebase. This is trust-building for the compounding system.

**Recommendation:** Knowledge injection should be invisible in the main flow. In the per-agent output files (`{OUTPUT_DIR}/{agent-name}.md`), add a `knowledge_injected` key to the YAML frontmatter:

```yaml
---
agent: safety-correctness
tier: core
knowledge_injected:
  - "auth-middleware-cancellation (confidence: high, last confirmed: 2026-02-08)"
  - "n-plus-one-resolver-pattern (confidence: medium, last confirmed: 2026-01-15)"
issues:
  ...
---
```

This is invisible during the main synthesis flow but available for anyone who reads the raw agent output. The synthesis report in Phase 3 does not mention knowledge injection. The per-agent files do.

### 4. Compounding Feedback (Phase 5 UX)

**The question:** After Phase 5, should the user see what was compounded?

**Answer: Almost never.**

By the time Phase 5 runs, the user has completed their review workflow. They have read the synthesis, optionally escalated via cross-AI, and mentally moved on to "what do I fix?" Interrupting this exit path with "Learned 3 new patterns, updated 2 existing" is the definition of noise at the wrong time.

**When it matters:** The only scenario where compounding feedback is useful is when a user is actively evaluating whether the knowledge system works. This is a meta concern, not a review concern. It belongs in a separate introspection command, not in the review flow.

**Recommendations:**

1. **Phase 5 should be silent by default.** It runs after synthesis, writes to the knowledge layer, and produces no user-visible output. The user's last interaction is Phase 3 (synthesis report) or Phase 4 (cross-AI), exactly as in v1.

2. **Opt-in verbosity.** Add a `--verbose` or `--show-learning` flag to `/flux-drive` that makes Phase 5 emit a summary. Default off.

3. **Separate introspection.** Provide a `/clavain:flux-knowledge` or `/clavain:flux-status` command that shows the current state of the knowledge layer: how many entries, last compounded date, top patterns, staleness warnings. This serves the "is the system learning?" question without polluting the review flow.

4. **If Phase 5 must produce output**, constrain it to a single line appended to the synthesis report: "Knowledge layer updated (3 new, 2 confirmed, 1 archived)." One line. No details. No decision prompt.

### 5. Deep-Pass UX

**Current spec:** "Triggered manually or on a schedule (e.g., after every 5th flux-drive run)."

**Problem:** There is no user-facing invocation path. "Triggered manually" means what? The user types what? There is no command, no flag, no prompt. The deep-pass agent is described as a background process that scans `docs/research/flux-drive/` across multiple reviews, but the user has no way to start it, no way to see its output, and no way to know when it has run.

**This is the largest UX gap in the v2 proposal.** Every other component has a clear invocation path: `/flux-drive <doc>` starts a review, triage presents a table, agents write to `{OUTPUT_DIR}/`. The deep-pass has none of this.

**Recommendations:**

1. **Create a command.** `/clavain:flux-deep` (or `/clavain:flux-drive --deep`) that triggers the deep-pass explicitly. The user runs it when they want to, not on an opaque schedule.

2. **Output location.** Deep-pass findings go to a fixed location: `.claude/flux-drive/deep-pass/YYYY-MM-DD.md`. The user knows where to look.

3. **Output format.** The deep-pass report should follow a recognizable structure:
   - Cross-review patterns found (with links to the original runs)
   - Agent blind spots detected (e.g., "Security agent missed X in 3/5 recent runs")
   - Knowledge entries archived due to staleness
   - Knowledge entries promoted from project-local to global

4. **Counter display.** When Phase 5 (immediate compounding) runs silently, it increments a counter. If `/flux-drive` is invoked and the counter shows >5 runs since the last deep-pass, the Phase 3 synthesis report appends a single line: "Consider running `/clavain:flux-deep` -- 7 reviews since last deep analysis." This is a gentle nudge, not a gate.

5. **No auto-trigger in v2.** The "after every 5th run" idea introduces non-deterministic behavior. The user runs `/flux-drive` expecting a standard 3-5 minute review and instead gets an extended run because the system decided to run a deep-pass. This violates the principle of predictable command behavior. If deep-pass becomes automatic later, it should run as a truly background process (via a hook or cron), not injected into the review flow.

### 6. Overall Flow: Is 5 Phases Too Many?

**The key insight: the user should not perceive 5 phases.**

In v1, the user perceives 3 interaction moments:
1. **Triage table + approval** (Phase 1 -- active interaction)
2. **Waiting** (Phase 2 -- passive)
3. **Reading synthesis + optional cross-AI decision** (Phase 3-4 -- active interaction)

In v2, if designed correctly, the user should perceive the same 3 moments:
1. **Triage table + approval** (Phase 1 -- active, but faster with 5-7 rows)
2. **Waiting** (Phase 2 -- passive, knowledge injection is invisible)
3. **Reading synthesis + optional cross-AI decision** (Phase 3-4 -- active, unchanged)

Phase 5 (compounding) runs silently after Phase 3-4 completes. The user does not see it, does not wait for it, and does not interact with it. From their perspective, the flow is identical to v1 but with a faster triage step.

**The risk:** If any of the v2 machinery leaks into the user's attention -- "Generating ad-hoc agent...", "Injecting 4 knowledge entries...", "Compounding 3 new patterns..." -- the flow will feel heavier than v1 despite being architecturally simpler. The spec must explicitly mark which outputs are user-facing and which are silent.

**Phase-by-phase perceived weight comparison:**

| Phase | v1 User Perception | v2 User Perception (if designed correctly) |
|-------|-------------------|-------------------------------------------|
| Triage | Scan 19-row table, approve | Scan 5-7 row table, approve (faster) |
| Launch | "N agents launching, wait 3-5 min" | Identical (knowledge injection is invisible) |
| Synthesize | Read report, see findings | Identical |
| Cross-AI | Optional escalation prompt | Identical |
| Compound | Does not exist | Silent (user does not see it) |

**Net UX delta: Improvement**, as long as the silence boundary is enforced.

---

## Summary

**Overall UX impact: Improvement**, conditional on keeping the new machinery invisible.

The v2 architecture makes two changes the user will directly appreciate: a dramatically shorter triage table (5-7 rows vs. 19) and richer findings from knowledge-injected agents. Everything else -- compounding, deep-pass, ad-hoc generation mechanics, knowledge retrieval -- is infrastructure that the user should not have to think about during a review.

**Top 3 changes for better user experience:**

1. **Enforce a silence boundary for Phase 5.** The compounding system must be invisible by default. No output, no prompts, no decisions. Provide a separate `/clavain:flux-knowledge` command for users who want to inspect the knowledge layer. If Phase 5 must signal anything, limit it to a single line in the synthesis report.

2. **Make ad-hoc agents visually distinct and rejectable.** In the triage table, generated agents should carry a `Generated (new)` or `Generated (saved)` category label, a descriptive name, and a 1-line focus description. The user must be able to drop them during "Edit selection." Never show a generic name like "ad-hoc-1."

3. **Create `/clavain:flux-deep` as the explicit deep-pass invocation.** Do not leave the deep-pass as an undefined manual trigger. Give it a command, an output location, and a predictable format. Use a gentle counter-based nudge ("7 reviews since last deep analysis") rather than auto-triggering it inside a review run.
