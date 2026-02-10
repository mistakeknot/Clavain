---
agent: user-advocate
review_target: docs/research/flux-drive-v2-architecture.md
date: 2026-02-10
issues:
  - id: C-1
    severity: Critical
    area: evidence
    title: "Compounding ROI assumes daily usage but no data exists on actual flux-drive frequency -- all 11 recorded runs are by a single developer over 3 days"
  - id: C-2
    severity: Critical
    area: evidence
    title: "Project agents described as dead (line 4) without evidence of why they failed -- replacing them with ad-hoc generation repeats the mistake if the root cause was user effort, not mechanism"
  - id: M-1
    severity: Major
    area: value-proposition
    title: "Knowledge layer trust problem -- injecting findings from prior reviews into agent context conflates confidence with staleness, and the user has no way to inspect or override what agents 'remember'"
  - id: M-2
    severity: Major
    area: failure-modes
    title: "Ad-hoc agent quality has no floor -- generated agents that produce shallow or wrong findings are worse than no agent because they dilute convergence signal"
  - id: M-3
    severity: Major
    area: time-to-value
    title: "Transition from 19 to 5 agents changes user mental model without migration path -- users who learned the roster and can predict triage outcomes lose that predictability"
  - id: M-4
    severity: Major
    area: discoverability
    title: "The 'getting smarter' narrative has no user-visible feedback loop -- compounding happens silently, user cannot tell whether review N+1 is better than review N"
  - id: M-5
    severity: Major
    area: segmentation
    title: "Design assumes a single-project power user but the plugin serves multi-project users -- knowledge graduation across projects is a leaky abstraction for developers switching contexts"
  - id: Mi-1
    severity: Minor
    area: time-to-value
    title: "Phase 5 (Compound) adds latency after synthesis with no immediate user-visible benefit -- the payoff is deferred to future runs"
  - id: Mi-2
    severity: Minor
    area: discoverability
    title: "Deep-pass agent triggered manually or after every 5th run -- neither trigger is discoverable without reading architecture docs"
improvements:
  - id: IMP-1
    title: "Instrument actual flux-drive usage frequency across projects before committing to compounding infrastructure"
    section: "Compounding System"
  - id: IMP-2
    title: "Add a knowledge provenance trail visible to the user -- show source review, date, and confirmation count for every injected finding"
    section: "Knowledge Layer"
  - id: IMP-3
    title: "Define a quality gate for ad-hoc agents -- minimum finding density, convergence with core agents, and auto-retirement after N low-value runs"
    section: "Ad-hoc Agents"
  - id: IMP-4
    title: "Create an explicit migration UX -- show users which old agents map to which new core agents, run both in parallel for N runs, then sunset old roster"
    section: "Agent Roster"
  - id: IMP-5
    title: "Make compounding tangible -- show a diff between what this review would have found without knowledge vs. with it"
    section: "Compounding System"
  - id: IMP-6
    title: "Post-mortem the project agent failure before building the replacement -- interview users (even if N=1) about why fd-*.md files were never created"
    section: "Ad-hoc Agents"
verdict: needs-changes
---

## User Context

**Who the affected users are:** Clavain plugin users who invoke `/clavain:flux-drive` to get multi-agent document and codebase reviews. Based on the available evidence (11 flux-drive output directories in `/root/projects/Clavain/docs/research/flux-drive/`, all dated 2026-02-08 to 2026-02-09, all from a single developer reviewing the Clavain repo itself), the current user base is N=1. There is no user research, no telemetry, no survey data, and no support tickets referenced in the proposal or in any project documentation.

**The user problem as stated in the proposal:** Five pain points: bloated agent roster (19 agents), wrong granularity, static roster that does not scale, dead project agents, and no learning between reviews.

---

## User Advocacy Findings

### C-1 (Critical) -- Compounding ROI Assumes Usage That Does Not Exist

**Area:** Evidence quality

**Finding:** The proposal's centerpiece -- "each review makes the next one better" -- requires frequent, repeated use of flux-drive on the same project. The compounding system (Phase 5 immediate agent, async deep-pass agent, two-tier knowledge layer with qmd retrieval, decay management, graduation criteria) is substantial infrastructure. But the evidence for usage frequency is 11 runs over 3 days, all by the plugin author reviewing the plugin itself.

The realistic usage frequency question the user asked is the right one. Consider three user profiles:

- **Monthly user**: Runs flux-drive on a plan before a big milestone. Gets zero compounding benefit because 30 days between runs means no active learning, and findings from the previous month are likely stale (codebase has changed). The compounding infrastructure is pure overhead.
- **Weekly user**: Runs flux-drive on PRDs or design docs weekly. Gets marginal compounding -- maybe 1-2 re-confirmed findings per run. The knowledge layer slowly accumulates entries, but the user never sees a moment where it clearly helped.
- **Daily user (the author)**: Gets strong compounding. But daily flux-drive usage on the same project is a developer-tooling-author pattern, not a general engineering pattern. Most engineers do not review documents daily.

The proposal does not address this distribution. It treats all three profiles identically.

**User impact:** If the median user runs flux-drive 1-3 times per month, the compounding system adds complexity (Phase 5 latency, knowledge files in `.claude/flux-drive/`, qmd retrieval overhead) without delivering the promised "getting smarter" benefit. The user pays the cost on every run but only receives the benefit after many runs they may never make.

**Recommendation:** Before building compounding infrastructure, instrument actual usage. Add a lightweight counter (e.g., increment a number in `.claude/flux-drive/metadata.json` on each run). After 4-8 weeks of the existing v1 system being used, check the distribution. If the median user runs flux-drive fewer than 4 times per month on a given project, compounding at the project level is not worth the investment. Consider cross-project compounding only (the Clavain-global tier), which benefits from aggregate volume even with low per-project frequency.

---

### C-2 (Critical) -- Project Agent Failure Diagnosis Missing

**Area:** Evidence quality

**Finding:** The proposal states "Project agents are dead -- optional `fd-*.md` project agents rarely get created by users" (line 4). This is treated as a fact that motivates replacing static project agents with ad-hoc generation. But the diagnosis stops at the symptom. Why did project agents fail?

The prior research provides some clues. In `/root/projects/Clavain/docs/research/flux-drive/pure-toasting-gizmo/code-simplicity-reviewer.md`, the code-simplicity reviewer noted: "Has zero existing users (no project currently has `fd-*.md` files created this way)" and recommended against the agent-creation automation as "premature abstraction." The reviewer suggested documenting manual creation instead of automating it.

Possible root causes for project agent failure:
1. **Effort barrier**: Users do not want to write custom agent definitions. Even "bootstrap via Codex" requires having Codex set up.
2. **Value unclear**: Users do not understand what a project-specific agent would catch that the adaptive roster misses.
3. **Discovery failure**: Users never learn that project agents are an option.
4. **Quality doubt**: If bootstrapped agents produce generic output, users abandon them after one try.

The proposal replaces the mechanism (static files to ad-hoc generation) but does not address causes 2, 3, or 4. If users did not create project agents because they did not see the value, generating agents automatically does not solve the value problem -- it just shifts who does the work.

**User impact:** If ad-hoc agents are generated automatically but produce mediocre output (a real risk, discussed in M-2), the user gets more noise in their review. The old failure mode (no project agents) was silent. The new failure mode (bad ad-hoc agents diluting good findings) is actively harmful.

**Recommendation:** Post-mortem the project agent feature before replacing it. This can be as simple as the plugin author reflecting on: "I designed project agents and never created them for any project -- why?" If the answer is "effort barrier," ad-hoc generation addresses it. If the answer is "I never needed project-specific review beyond what adaptive agents provide," then ad-hoc generation solves a problem that does not exist.

---

### M-1 (Major) -- Knowledge Layer Trust Problem

**Area:** Value proposition

**Finding:** The user asked: "Will users trust findings that come from 'the system remembered this from 3 reviews ago'?" This is the right question, and the proposal does not answer it.

The knowledge layer injects findings from prior reviews into agent context via qmd semantic retrieval. From the user's perspective, they invoke flux-drive and get a set of findings. Some findings come from the agent's current analysis of the document. Others come from knowledge entries written by a compounding agent during a previous run.

The user cannot distinguish between these two sources. The proposal specifies a `lastConfirmed` date and `convergence` count in the knowledge entry YAML, but these are metadata fields -- they are visible to agents consuming the entries, not to users reading the synthesis report.

Trust breaks down in several scenarios:
- **Stale knowledge**: A finding from 3 reviews ago says "auth middleware swallows context cancellation errors." The middleware was fixed 2 reviews ago but the knowledge entry was not updated because no agent re-examined that file. The finding persists and gets re-injected.
- **Over-confidence from compounding**: If agent N re-confirms a finding because agent N-1 told it to look for it (via knowledge injection), the convergence count inflates artificially. The finding appears high-confidence because it was found repeatedly, but it was found repeatedly because the system kept telling agents to find it.
- **Opacity**: The user receives a finding labeled "P1, convergence 4/5" and has no way to know whether 4 agents independently discovered it or whether 4 agents all found it because they were primed by the knowledge layer.

**User impact:** If users learn that some findings are "recycled" from prior runs, they may discount the entire synthesis. Trust in automated review systems is binary -- either the user trusts the findings or they ignore them. Partially-trusted systems waste everyone's time.

**Recommendation:** Make knowledge provenance visible. When a finding in the synthesis report was influenced by a knowledge entry, annotate it: "Also flagged in review on 2026-02-08 (confirmed 3 times)." This lets users evaluate staleness themselves. Additionally, prevent the circular confirmation problem by marking knowledge-injected findings separately from independently-discovered findings in convergence tracking. A finding confirmed by 4 agents who were all told to look for it has convergence 1, not convergence 4.

---

### M-2 (Major) -- Ad-hoc Agent Quality Has No Floor

**Area:** Failure modes

**Finding:** The proposal says triage "generates new ad-hoc agent prompt on the fly" when an unmatched domain is detected. This is the most appealing feature in the proposal ("flux-drive generates custom reviewers for your project") and also the riskiest.

An ad-hoc agent is a system prompt generated by triage, saved to `.claude/flux-drive/agents/`, and dispatched alongside core agents. Its quality depends entirely on the triage phase's ability to write a good review agent system prompt in real time.

Quality risks:
- **Shallow prompts**: Triage has limited context about the domain it is generating for. A "GraphQL schema design" ad-hoc agent prompt written by triage (which is running within flux-drive, not a domain expert) will likely produce generic advice comparable to asking Claude directly about GraphQL.
- **Convergence dilution**: Ad-hoc agents participate in convergence tracking alongside core agents. A mediocre ad-hoc agent that flags obvious issues inflates convergence counts for those issues while failing to surface domain-specific insights. This is worse than having no agent for that domain, because the convergence signal now includes noise.
- **Reuse without validation**: "Saved to `.claude/flux-drive/agents/` in the project repo. Reused if triage matches them in future runs." A bad ad-hoc agent gets reused indefinitely. There is no mechanism for a user to evaluate whether a saved ad-hoc agent is producing value.
- **Graduation risk**: "Graduate to Clavain-global if used across multiple projects." A mediocre agent that gets reused in 2+ projects (perhaps because its domain is broad, like "documentation quality") graduates to affect all users.

The proposal's open question #2 acknowledges this: "What triggers promotion from project-local to Clavain-global? 'Used in 2+ projects' is simple but might be too aggressive." But the question focuses on the graduation threshold, not on whether the generated agent is any good.

**User impact:** A user who sees "6 agents reviewed your document" expects 6 useful perspectives. If 1 of those is a mediocre ad-hoc agent, the user gets 5 useful perspectives plus noise. Over time, if the user notices that some agents consistently produce generic findings, they stop trusting the number and start skipping agent reports. This undermines the core value proposition of multi-agent review.

**Recommendation:** Define a quality gate for ad-hoc agents. Possible signals: (1) finding density -- if an ad-hoc agent produces fewer findings than the average core agent on the same document, flag it for review; (2) uniqueness -- if all ad-hoc agent findings are duplicated by core agents, the ad-hoc agent added no value; (3) user signal -- after synthesis, let the user mark findings as "useful" or "noise" (lightweight feedback). Auto-retire ad-hoc agents that fail quality checks for 3 consecutive runs. Do not graduate agents that have not passed quality checks in at least 3 distinct projects.

---

### M-3 (Major) -- Transition Pain Is Unaddressed

**Area:** Time to value

**Finding:** The proposal replaces 19 specialized agents with 5 core agents. For the current user base (even if N=1), this is a significant change to the mental model.

A user who has run flux-drive multiple times has learned:
- Which agents get selected for which documents (the triage scoring table is presented every run)
- What each agent's domain is (they read agent reports named `architecture-strategist.md`, `security-sentinel.md`, etc.)
- What output to expect (each agent produces domain-specific findings)

After the transition:
- 5 agents cover the same ground but with merged domains. "Safety & Correctness" now covers security + data integrity + concurrency + deployment. The user loses the ability to know whether a finding came from security expertise or concurrency expertise.
- Triage output changes from 19 scored agents (with familiar names) to 5 scored agents (with new names).
- Agent reports change from `security-sentinel.md` to `safety-and-correctness.md` with findings that span 4 former domains.

The proposal's open question #5 acknowledges the risk: "Will 5 merged agents actually perform as well as 19 specialists?" But it only considers quality, not the user's experience of the transition.

**User impact:** The transition is a one-time disruption, but it happens at the worst possible time -- when the user is trying to evaluate whether v2 is better. If the first v2 run produces a "Safety & Correctness" report that is shallower on security than the old `security-sentinel.md` was, the user concludes v2 is a regression, even if the merged agent caught things the specialist missed. First impressions of changed tools are disproportionately influential.

**Recommendation:** Build a transition bridge. Options: (1) run v1 and v2 in parallel for a few runs, producing both old-format and new-format reports so the user can compare; (2) in the v2 synthesis report, annotate each finding with which v1 agent would have produced it ("Finding from Safety & Correctness [formerly: security-sentinel domain]"); (3) keep old agent names as sub-labels within merged agents, at least for the first N runs. The goal is to let users verify that they are not losing coverage during the transition.

---

### M-4 (Major) -- The "Getting Smarter" Narrative Is Invisible

**Area:** Discoverability

**Finding:** The user asked: "Does the user actually *feel* this improvement? What would make it tangible?" The proposal does not address this.

The compounding system works silently. The immediate compounding agent runs after synthesis, extracts findings, and writes them to knowledge files. The async deep-pass agent runs periodically and consolidates patterns. None of this is visible to the user during a flux-drive run.

From the user's perspective, they run flux-drive on day 1 and get findings. They run it on day 15 and get findings. Are the day-15 findings better because of compounding? They have no way to tell. The findings are different because the document is different. Any improvement from compounding is confounded with document changes.

This matters because the "getting smarter" narrative is the proposal's headline. If the user cannot perceive the improvement, the feature exists only on paper. It is an investment that the user must take on faith.

**User impact:** Features that users cannot perceive get no credit for existing. The compounding system could be working perfectly, and users would still describe flux-drive as "a multi-agent review tool" rather than "a review tool that learns." Invisible features do not drive adoption or retention.

**Recommendation:** Make the compounding visible. At the start of each run, after triage, show a brief knowledge context summary: "This review will benefit from 7 knowledge entries from 3 prior reviews on this project." In the synthesis report, annotate findings that were informed by knowledge: "This issue was first identified on 2026-02-08 and has been confirmed in 3 reviews." At the end, show what was learned: "This review added 2 new knowledge entries and confirmed 3 existing ones." This turns compounding from a background process into a visible learning loop.

Even better: show a counterfactual. "Knowledge injection surfaced 2 findings that would not have appeared without prior review history." This directly demonstrates the value of compounding. If the counterfactual is empty ("Knowledge injection did not change any findings this run"), that is honest feedback that the compounding system is not yet adding value, which is also useful information.

---

### M-5 (Major) -- Multi-project Users Get a Leaky Abstraction

**Area:** User segmentation

**Finding:** The two-tier knowledge system (project-local + Clavain-global) assumes users primarily work within one project at a time. But a developer using Clavain likely works across multiple projects -- that is the point of a general-purpose engineering plugin.

The project-local tier stores knowledge in `.claude/flux-drive/knowledge/` within each project. A developer reviewing plans in Project A and specs in Project B builds separate knowledge bases. The Clavain-global tier aggregates patterns that appear in 2+ projects.

Problems for multi-project users:
- **Context bleed via global tier**: A finding graduated from Project A ("middleware swallows cancellation") gets injected into Project B reviews. If Project B has no middleware, this is noise. The qmd semantic retrieval is supposed to filter by relevance, but "middleware" is a common enough term that irrelevant entries may match.
- **Graduation threshold is project-count-based, not quality-based**: A finding observed in 2 projects graduates, even if both projects are structurally similar (same team, same framework). This is correlation masquerading as generalization.
- **Knowledge file management**: Developers switching between projects accumulate `.claude/flux-drive/knowledge/` directories in each project. These are git-tracked (the proposal says "git-diffable"). Code reviewers of those projects now see flux-drive knowledge files in PRs, which are artifacts of the review tool, not the project.

**User impact:** Multi-project users get noise from knowledge that leaked across project boundaries. Knowledge files in git repos create maintenance burden for teams that did not opt into flux-drive. The graduation system spreads patterns without validating that they generalize.

**Recommendation:** Gate global knowledge injection behind explicit user opt-in. Default to project-local knowledge only. For the global tier, require the user to confirm graduation: "This finding has appeared in 2 projects. Make it available to all projects? [Y/n]." For the file storage problem, consider `.claude/flux-drive/` being gitignored by default, with an opt-in to track it. Knowledge should be a tool for the developer, not an artifact that ships with the code.

---

### Mi-1 (Minor) -- Phase 5 Adds Latency With Deferred Payoff

**Area:** Time to value

**Finding:** The current flux-drive workflow already has a UX problem with its 3-5 minute silent wait (flagged as P0 in the self-review at `/root/projects/Clavain/docs/research/flux-drive/flux-drive-self-review/summary.md`). Phase 5 (Compound) adds another step after synthesis where the compounding agent reads the synthesis output, decides what to remember, and writes knowledge entries.

The user gets no immediate value from Phase 5. Its value is deferred to future runs. But the user experiences Phase 5 as additional wait time after they have already waited 3-5 minutes for agents and synthesis.

**User impact:** After waiting 3-5 minutes, the user wants to read findings and act. Adding a visible "Compounding..." step after synthesis makes the workflow feel longer without providing immediate gratification. If the compounding step is silent (runs in background), it may silently fail without the user noticing, leading to a "why didn't compounding work?" problem later.

**Recommendation:** Run Phase 5 in the background after presenting the synthesis report. The user gets their findings immediately; compounding happens asynchronously. Show a brief notification when compounding completes: "Saved 2 knowledge entries for future reviews." This way the user sees the compounding activity without waiting for it.

---

### Mi-2 (Minor) -- Deep-pass Trigger Is Not Discoverable

**Area:** Discoverability

**Finding:** The async deep-pass agent "scans `docs/research/flux-drive/` output directories across multiple reviews" and runs "manually or on a schedule (e.g., after every 5th flux-drive run)." Neither trigger is discoverable.

A manual trigger means the user must know the deep-pass exists and remember to invoke it. A counter-based trigger (after every 5th run) requires infrastructure to count runs, which is not specified in the proposal. The deep-pass is described as doing valuable work (cross-review patterns, systematic blind spots, decay management), but the user has no natural moment to encounter it.

**User impact:** The deep-pass is likely to be forgotten or never discovered. Its benefits (cross-review patterns, blind spot detection, decay) silently degrade if it never runs.

**Recommendation:** Integrate the deep-pass trigger into the normal flux-drive workflow. After every Nth run (proposal suggests 5), add a one-line prompt at the end of the synthesis report: "5 reviews accumulated since last deep-pass. Run cross-review analysis? [Y/n]." This makes the feature discoverable at a natural decision point and avoids requiring the user to remember a separate command.

---

## Evidence Scorecard

- **Problem validation: moderate** -- The 5 pain points are plausible and internally consistent. The "bloated roster" and "wrong granularity" claims are supported by prior flux-drive self-review data. However, "project agents are dead" is stated without root cause analysis. "No learning between runs" is an observation, not a validated user pain point.
- **Solution validation: weak** -- No prototype, no A/B test, no user feedback on the proposed design. The compounding system is designed from first principles without testing whether users want or would benefit from cross-run learning. The merged agent quality question (open question #5) is acknowledged but unresolved.
- **User research quality: assumed** -- There are zero user interviews, zero surveys, zero analytics, and zero support tickets referenced anywhere in the proposal or the broader project. All 11 flux-drive runs in the research directory are by the plugin author. The proposal designs for an imagined user rather than an observed one.

---

## Summary

**Overall user impact:** Medium. The roster simplification (19 to 5 agents) solves a real maintenance problem and could improve review quality through richer agent context. The ad-hoc generation concept is compelling. But the compounding system -- the proposal's headline feature -- has an unclear user payoff that depends on usage frequency patterns that have not been measured.

**Top 3 gaps in user understanding:**

1. **No usage frequency data.** The compounding system's value proposition depends entirely on how often users run flux-drive on the same project. Without measurement, the entire knowledge layer could be infrastructure that benefits one user (the author) and adds complexity for everyone else.

2. **No root cause analysis for project agent failure.** The proposal replaces a feature that "rarely gets used" without understanding why. Ad-hoc generation may repeat the same failure (users do not value project-specific review) through a different mechanism.

3. **No visibility into compounding benefits.** The "getting smarter" narrative is the proposal's differentiator, but nothing in the design makes this improvement perceptible to users. A feature whose value is invisible is a feature whose value is zero from the user's perspective.

**Readiness assessment:** Needs more research before building the compounding/knowledge layer. The roster simplification (5 core agents, ad-hoc generation) could proceed as a standalone change with lower risk and faster time-to-value. The compounding system should be deferred until: (a) usage frequency is measured, (b) the project agent failure is post-mortemed, and (c) a prototype demonstrates that users can perceive the "getting smarter" benefit.

Recommended decomposition:
- **Build now:** 5 core agents with merged domains (low risk, addresses maintenance pain)
- **Build now:** Ad-hoc agent generation with quality gates (compelling value, moderate risk)
- **Defer:** Knowledge layer and compounding system (high investment, unvalidated payoff)
- **Defer:** Deep-pass agent (depends on compounding system existing and having value)
