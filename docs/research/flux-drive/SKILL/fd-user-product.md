# User & Product Review: flux-drive Orchestration

## Findings Index

- P0 | P0-1 | "Step 1.3: User Confirmation" | Missing escape hatch for users stuck in triage disagreement loop
- P0 | P0-2 | "Step 2.2b: Domain-aware expansion" | Forced choice with no "show me first" option blinds user to decision quality
- P1 | P1-1 | "Phase 1: Analyze + Static Triage" | Scoring table lacks mental model anchor — users cannot predict agent behavior
- P1 | P1-2 | "Step 3.5: Report to User" | Convergence counts mislead when Stage 2 was skipped
- P1 | P1-3 | "Step 1.0-1.0.4: Domain detection chain" | Silent failures create ghost state — user cannot debug
- P1 | P1-4 | "Step 2.3: Monitor and verify" | Progress reporting disappears for 30s intervals — user has no confidence work is happening
- P1 | P1-5 | "Agent Roster: Cross-AI (Oracle)" | Oracle failure recovery unclear — user doesn't know whether to retry or skip
- IMP | IMP-1 | "Step 1.2: Agent selection" | Triage table should show "what you're getting" not just "why we scored this way"
- IMP | IMP-2 | "Step 3.4: Update the Document" | Write-back default (no) contradicts user mental model of "review improves document"
- IMP | IMP-3 | "Step 1.3: User Confirmation" | Stage assignments in table are uneditable — user must describe changes in prose
- IMP | IMP-4 | "Step 3.6: Create Beads from Findings" | Beads creation is silent unless user knows to check — no confirmation
- IMP | IMP-5 | "Phase 4: Cross-AI Comparison" | Oracle participation is invisible until synthesis — user doesn't know it ran
- IMP | IMP-6 | "Step 2.2b: Domain-aware expansion" | Expansion reasoning is oracle-like — user cannot verify the logic
- IMP | IMP-7 | "Step 1.1: Analyze the Document" | Repo review uses same "document profile" language as single-file review — confusion
- IMP | IMP-8 | "Integration" | No recovery path when user realizes flux-drive was the wrong tool mid-run

Verdict: needs-changes

---

## Summary

The flux-drive orchestration implements a sophisticated multi-agent review system with domain detection, progressive staging, and knowledge compounding — but critical UX gaps undermine user trust and recovery. Two P0 issues block confident use: (1) users stuck in triage disagreement loops have no escape path beyond "Cancel" (which loses all setup work), and (2) the Stage 1→Stage 2 expansion decision forces a blind commit without showing what agents found. Five P1 issues create friction: scoring opacity prevents users from predicting agent behavior, convergence counts mislead when partial agent sets run, silent domain detection failures create ghost state, 30-second progress reporting gaps erode confidence, and Oracle failure recovery is undefined. Eight improvements would raise usability: expose "what you get" alongside scoring logic, flip the write-back default to match user mental models, make stage assignments visually editable, confirm bead creation, surface Oracle participation earlier, show expansion logic not just conclusions, clarify repo vs file review mental models, and provide mid-run escape hatches.

## Issues Found

### P0-1: Missing escape hatch for users stuck in triage disagreement loop
**Severity:** P0
**Location:** Step 1.3: User Confirmation

If the user selects "Edit selection" but cannot articulate the change they want (common when they don't understand the scoring), they are trapped in a loop: "Edit selection" → re-present table → "Edit selection" again → ...

The only exit is "Cancel", which abandons all triage work and forces a restart from scratch. The user loses:
- Domain detection results (Step 1.0.1-1.0.4)
- Document profile analysis (Step 1.1)
- Agent scoring computation (Step 1.2)

**User impact:** A confused user at Step 1.3 has no recovery path that preserves partial progress. They must either commit blindly ("Approve" without understanding) or abandon the entire run.

**Fix:** Add a fourth option in Step 1.3's AskUserQuestion:
```yaml
- label: "Explain scoring"
  description: "Show how each agent was scored and why stages were assigned"
```

When selected, the orchestrator re-presents the triage table with expanded columns:
- Base score breakdown (why 0/1/2/3)
- Domain boost explanation (which domain profile bullets matched)
- Final score = sum
- Stage cutoff logic (top 40% → Stage 1)

Then loop back to the original three options (Approve / Edit / Cancel).

### P0-2: Forced choice with no "show me first" option blinds user to decision quality
**Severity:** P0
**Location:** Step 2.2b: Domain-aware expansion decision

The expansion decision gate (after Stage 1 completes) presents options like:
- "Launch [specific agents] (Recommended)"
- "Launch all Stage 2 (N agents)"
- "Stop here"

But the user has ZERO visibility into what Stage 1 agents actually found. The prompt says "[findings summary]" but the spec never defines what that summary contains.

**User scenario:**
1. Stage 1 completes (fd-architecture, fd-safety)
2. Orchestrator reads their Findings Indexes
3. Orchestrator computes expansion scores (adjacency + severity signals)
4. Orchestrator presents recommendation: "Launch fd-correctness + fd-performance?"
5. User thinks: "Why? What did Stage 1 find that makes these agents relevant?"

The spec says "Stage 1 complete. [findings summary]. [expansion reasoning]" but never shows the user the Findings Indexes or verdict lines. The user is choosing blind.

**User impact:** Users cannot assess whether the orchestrator's recommendation is sensible. They either trust it blindly (reduces to "always expand") or reject it blindly (reduces to "never expand"). The expansion decision becomes noise.

**Fix:** Before presenting the expansion options, show a findings snapshot:

```markdown
## Stage 1 Results

**fd-architecture** (3 findings):
- P1: Module boundaries between auth and session are leaky
- P1: Circular dependency between handlers and middleware
- IMP: Extract shared types to reduce coupling

**fd-safety** (1 finding):
- P0: Session tokens stored in localStorage (XSS risk)

Expansion analysis: fd-safety found a P0 in auth → adjacent agents fd-correctness and fd-architecture should validate session lifecycle (race conditions, token refresh logic).

Options:
- Launch fd-correctness + fd-architecture (Recommended)
- Launch all Stage 2 (5 agents)
- Stop here
```

This gives the user CONTEXT for the decision, not just a blind recommendation.

### P1-1: Scoring table lacks mental model anchor — users cannot predict agent behavior
**Severity:** P1
**Location:** Phase 1: Analyze + Static Triage (Step 1.2)

The triage table shows:

| Agent | Category | Score | Stage | Reason | Action |
|-------|----------|-------|-------|--------|--------|

"Reason" is a prose explanation of WHY the agent scored this way, but users need to know WHAT the agent will do. The spec never tells the user:
- What sections will fd-architecture focus on?
- Will fd-safety only check auth code or also deployment config?
- Does fd-quality review naming conventions or test coverage or both?

**User scenario:**
User sees: "fd-architecture: score 6, Stage 1, Reason: Core domain match — plan touches module boundaries and coupling"

User thinks: "Okay but what will it actually check? Will it validate my layering diagram? Will it flag my circular imports? Will it review the refactor sequence?"

The Reason column explains the SCORE but not the AGENT'S SCOPE.

**User impact:** Users cannot predict what each agent will produce. They approve the roster blind, then are surprised when an agent flags something they didn't expect OR misses something they assumed was in scope.

**Fix:** Add a "Focus" column to the triage table that summarizes what each agent will check:

| Agent | Score | Stage | Focus | Action |
|-------|-------|-------|-------|--------|
| fd-architecture | 6 | 1 | Module boundaries, coupling patterns, refactor sequence risks | Launch |
| fd-safety | 5 | 1 | Auth flow, credential storage, deployment rollback plan | Launch |

This borrows from Step 2.1's "Your Focus Area" agent prompt section — surface it earlier so users know what they're getting.

### P1-2: Convergence counts mislead when Stage 2 was skipped
**Severity:** P1
**Location:** Step 3.5: Report to User

The synthesis report shows convergence as "(3/5 agents)" but this count is ONLY VALID when all 5 agents ran. If Stage 2 was skipped:
- 2 Stage 1 agents ran
- 3 Stage 2 agents were SELECTED but NEVER LAUNCHED

A finding from "2/2 Stage 1 agents" has 100% convergence within the active set, but reporting it as "2/5 agents" makes it look weak (40% convergence).

**User impact:** Users misinterpret finding confidence. A unanimous Stage 1 finding (2/2) is reported as minority opinion (2/5), causing users to deprioritize it.

**Fix:** Adjust convergence denominators to reflect active agents only:
- If early stop: "2/2 Stage 1 agents (3 agents skipped)"
- If full run: "3/5 agents"

The spec already says 'Report in the summary: "Early stop after Stage 1: N agents ran, M agents skipped"' but it doesn't fix the convergence counts in the Issues list.

### P1-3: Silent failures create ghost state — user cannot debug
**Severity:** P1
**Location:** Step 1.0-1.0.4: Domain detection chain

The domain detection chain (1.0.1 → 1.0.2 → 1.0.3 → 1.0.4) has multiple failure modes:
- Script exit 2 (error)
- Domain profile files missing
- Agent generation failures

For each failure, the spec says "log warning" or "skip silently" but never tells the user HOW to fix it. The user sees:
- "No domains detected" (is this expected or a bug?)
- "Agent generation skipped" (why? can I fix it?)
- "Domain detection unavailable" (should I retry? is something broken?)

**User scenario:**
1. User runs flux-drive on a Rust game project
2. Domain detection script fails (exit 2) because tree-sitter binary is missing
3. Orchestrator logs: "Domain detection unavailable (detect-domains.py error). Proceeding with core agents only."
4. User thinks: "Is this normal? Do I need to install something? Will this affect review quality?"

No guidance provided.

**User impact:** Users cannot distinguish expected behavior (no domains detected for a generic project) from broken behavior (script crashed). Silent failures accumulate as ghost state — users don't know if domain detection is working or disabled.

**Fix:** Add a troubleshooting note to the error message:

```
⚠️ Domain detection unavailable (detect-domains.py error).
   → Check: python3 --version (need 3.9+), tree-sitter CLI installed
   → Run manually: python3 ${CLAUDE_PLUGIN_ROOT}/scripts/detect-domains.py {PROJECT_ROOT}
   → If this is expected (no Python), disable with: echo 'override: true\ndomains: []' > .claude/flux-drive.yaml
Proceeding with core agents only.
```

### P1-4: Progress reporting disappears for 30s intervals — user has no confidence work is happening
**Severity:** P1
**Location:** Step 2.3: Monitor and verify agent completion

The monitoring loop polls every 30 seconds. If 5 agents are running and all complete within 25 seconds, the user sees:

```
Agent dispatch complete. Monitoring 5 agents...
⏳ fd-architecture
⏳ fd-safety
⏳ fd-quality
⏳ fd-correctness
⏳ fd-performance
```

[25 seconds of silence]

```
✅ fd-architecture (23s)
✅ fd-safety (25s)
✅ fd-quality (22s)
✅ fd-correctness (24s)
✅ fd-performance (21s)
[5/5 agents complete]
```

For those 25 seconds, the user has NO feedback. They don't know:
- Are agents actually running or did dispatch fail?
- Is the orchestrator stuck or just waiting?
- Should I cancel and retry?

**User impact:** Users lose confidence during the silent interval. Some will cancel and retry prematurely, interrupting successful runs.

**Fix:** Add a heartbeat message every 10 seconds:

```
Agent dispatch complete. Monitoring 5 agents...
⏳ fd-architecture
⏳ fd-safety
⏳ fd-quality
⏳ fd-correctness
⏳ fd-performance

[10s] Still running... (0/5 complete)
[20s] Still running... (0/5 complete)

✅ fd-architecture (23s)
...
```

This is low-cost (one line of output per 10s) and high-value (proves the orchestrator is alive).

### P1-5: Oracle failure recovery unclear — user doesn't know whether to retry or skip
**Severity:** P1
**Location:** Agent Roster: Cross-AI (Oracle)

When Oracle fails, the spec says:

> If the Oracle command fails or times out, note it in the output file and continue without Phase 4. Do NOT block synthesis on Oracle failures — treat it as "Oracle: no findings" and skip Steps 4.2-4.5.

But the user never sees this decision. The error handling creates `oracle-council.md` with `verdict: error`, but:
1. The user is not told Oracle failed until synthesis (Phase 3)
2. The synthesis report treats Oracle as "participated but found nothing" vs "crashed and was skipped"
3. The user doesn't know if they should retry Oracle manually or just accept the incomplete review

**User scenario:**
1. User approves roster including Oracle
2. Oracle times out after 30 minutes (login expired)
3. Orchestrator writes error stub, continues to synthesis
4. User sees synthesis report: "5/6 agents completed successfully, 1 failed"
5. User thinks: "Should I fix Oracle and re-run? Or is 5/6 good enough?"

No guidance provided.

**User impact:** Users don't know whether Oracle failures are recoverable or expected. They either waste time retrying non-recoverable failures (e.g., network down) or accept incomplete reviews when a simple fix (e.g., re-login) would have worked.

**Fix:** When Oracle fails, report it immediately after the failure (not just in synthesis):

```
⚠️ Oracle failed (exit 124: timeout after 1800s)
   → Likely cause: ChatGPT login expired or Cloudflare challenge
   → Fix: Open NoVNC at http://100.69.187.66:6080/vnc.html, run oracle-login, retry flux-drive
   → Continue without Oracle? [Yes (Recommended) / Retry Oracle / Cancel]
```

This gives the user agency: retry if fixable, skip if not.

## Improvements Suggested

### IMP-1: Triage table should show "what you're getting" not just "why we scored this way"
**Location:** Step 1.2: Select Agents from Roster

The current triage table optimizes for scoring transparency (Base + Domain Boost + Project + DA = Total) but users care more about OUTCOMES than INPUTS.

**Current table:**
| Agent | Category | Base | Domain Boost | Project | Total | Stage | Action |

**User question:** "What will fd-architecture do?"

**Current answer:** "Score 6 because base 3 + domain boost 2 + project 1."

**What user actually needs:** "fd-architecture will check: module boundaries, coupling patterns, circular dependencies, and refactor sequence risks."

**Recommendation:** Replace the scoring breakdown columns (Base, Domain Boost, Project) with a single "Focus" column. Move scoring details to the "Explain scoring" option (see P0-1).

**New table:**
| Agent | Score | Stage | Focus | Action |
|-------|-------|-------|-------|--------|
| fd-architecture | 6 | 1 | Module boundaries, coupling, refactor risks | Launch |
| fd-safety | 5 | 1 | Auth flow, secrets, rollback plan | Launch |

Users get outcome clarity by default, with scoring details available on demand.

### IMP-2: Write-back default (no) contradicts user mental model of "review improves document"
**Location:** Step 3.4: Update the Document

After synthesis, the orchestrator asks:

```yaml
AskUserQuestion:
  question: "Summary written to {OUTPUT_DIR}/summary.md. Add inline annotations to the original document?"
  options:
    - label: "No, summary only (Recommended)"
    - label: "Yes, add inline annotations"
```

The default is "No" because the spec authors value "keep original clean" over "review improves document."

But most users' mental model is:
- I ran a review → the review found issues → the review should UPDATE THE DOCUMENT with those issues

Recommending "No" contradicts this expectation. Users think: "Why did I run a review if it doesn't improve my document?"

**User impact:** Users feel the review was incomplete or failed to deliver value because their document is unchanged.

**Recommendation:** Flip the default:

```yaml
- label: "Yes, add inline annotations (Recommended)"
  description: "Insert findings as blockquotes in the original document"
- label: "No, summary only"
  description: "Keep the original document unchanged"
```

This matches user expectations. Advanced users who want separation can opt out.

**Edge case:** For diffs and repo reviews, there is no single "document" to annotate — summary-only is the only option. Keep summary-only as default for those input types, but flip it for single-file reviews.

### IMP-3: Stage assignments in table are uneditable — user must describe changes in prose
**Location:** Step 1.3: User Confirmation

When the user selects "Edit selection", the orchestrator says:

> If user selects "Edit selection", adjust and re-present.

But HOW does the user communicate the adjustment? The spec doesn't say. Likely:
1. User selects "Edit selection"
2. Orchestrator asks: "What changes do you want?"
3. User types: "Move fd-performance from Stage 2 to Stage 1"
4. Orchestrator parses prose, updates table, re-presents

This is high-friction. Users must:
- Remember agent names exactly
- Know the stage numbers (1 vs 2)
- Describe the change in prose
- Hope the orchestrator parses correctly

**Recommendation:** Make stage assignments interactive. After "Edit selection", present a checklist:

```yaml
AskUserQuestion:
  question: "Adjust agent selection:"
  options:
    - label: "Move agent between stages"
      description: "Select agent → reassign Stage 1/Stage 2"
    - label: "Remove agent from roster"
      description: "Deselect an agent"
    - label: "Add agent to roster"
      description: "Promote an agent from expansion pool or add skipped agent"
    - label: "Done editing"
      description: "Return to approval screen"
```

For "Move agent between stages", present a nested question:
```yaml
AskUserQuestion:
  question: "Which agent?"
  options:
    - label: "fd-architecture (currently Stage 1)"
    - label: "fd-safety (currently Stage 1)"
    - label: "fd-quality (currently Stage 2)"
    ...
```

Then:
```yaml
AskUserQuestion:
  question: "Move fd-quality to which stage?"
  options:
    - label: "Stage 1"
    - label: "Stage 2"
    - label: "Remove from roster"
```

This is 3 clicks instead of typing prose and hoping for correct parsing.

### IMP-4: Beads creation is silent unless user knows to check — no confirmation
**Location:** Step 3.6: Create Beads from Findings

Step 3.6 creates beads from P0/P1/P2 findings, then appends a summary to the Step 3.5 report:

```markdown
### Beads Created
| Bead ID | Priority | Title |
| 123 | P0 | [fd] Session tokens in localStorage |
```

But this section is APPENDED after the user has already seen the main report. If the user stops reading after "Files" or "Diff Slicing Report", they miss the beads notification entirely.

**User impact:** Users don't realize beads were created. They manually create duplicate beads later, or they forget about findings because they expect beads but didn't see the confirmation.

**Recommendation:** Report bead creation BEFORE the final report, as a separate user-facing message:

```
✅ Created 3 beads from findings:
   - Bead 123 (P0): [fd] Session tokens in localStorage
   - Bead 124 (P1): [fd] Circular dependency in auth middleware
   - Bead 125 (P1): [fd] Missing rollback plan for cache schema change

Use `bd list --status=open` to see all.

Proceeding to synthesis report...
```

This ensures the user sees bead creation as a discrete outcome, not as a footnote in a long report.

### IMP-5: Oracle participation is invisible until synthesis — user doesn't know it ran
**Location:** Phase 4: Cross-AI Comparison (Optional)

Oracle launches in Stage 1 or Stage 2 (if it was selected during triage), but the user never sees a status update like:

```
✅ fd-architecture (47s)
✅ oracle-council (1847s)
```

Oracle runs via Bash (not Task), so it doesn't participate in the Step 2.3 polling loop. The user only learns Oracle ran when they see the synthesis report or check the output directory manually.

**User scenario:**
1. User approves roster including Oracle
2. Stage 1 launches: fd-architecture, fd-safety, oracle-council
3. Polling loop reports: "✅ fd-architecture (47s), ✅ fd-safety (52s), [2/3 agents complete]"
4. User thinks: "Where's the third agent?"
5. 30 minutes pass
6. User cancels flux-drive, thinking it's stuck
7. Oracle was actually running the whole time

**User impact:** Users cancel Oracle mid-run because they don't see progress updates. The 30-minute timeout feels like a hang, not intentional work.

**Recommendation:** Add Oracle to the monitoring loop. After launching Oracle via Bash (`run_in_background: true`), poll for `oracle-council.md` (not `.md.partial` — Oracle writes directly to `.md` on success):

```
Agent dispatch complete. Monitoring 3 agents...
⏳ fd-architecture
⏳ fd-safety
⏳ oracle-council (cross-AI via GPT-5.2 Pro, est. 10-30 min)

[30s] Still running... (0/3 complete)
[60s] ✅ fd-architecture (47s)
      ✅ fd-safety (52s)
      ⏳ oracle-council (cross-AI via GPT-5.2 Pro, est. 10-30 min)
      [2/3 agents complete]
...
[1800s] ✅ oracle-council (1847s)
        [3/3 agents complete]
```

The key change: include Oracle in the initial agent count (3 not 2) and show it in the pending list with an ETA note.

### IMP-6: Expansion reasoning is oracle-like — user cannot verify the logic
**Location:** Step 2.2b: Domain-aware expansion decision

The expansion decision uses an algorithm:

```
expansion_score = 0
if any P0 in adjacent agent's domain: +3
if any P1 in adjacent agent's domain: +2
if disagreement in this agent's domain: +2
if domain injection criteria exist: +1
```

Then the orchestrator presents a recommendation like:

> Stage 1 found a P0 in game design (death spiral in storyteller). fd-correctness is adjacent to fd-game-design and has domain criteria for simulation state consistency — it could validate whether this is a code bug or design issue. Launch fd-correctness + fd-performance for Stage 2?

But the user cannot verify:
- Is fd-correctness actually adjacent to fd-game-design? (check the adjacency map)
- Did fd-performance also score high, or was it included arbitrarily?
- What was the expansion score for each agent?

The reasoning is a BLACK BOX. The user either trusts it or doesn't.

**User impact:** Users who want to understand the recommendation (to learn the system or challenge a bad call) have no transparency. They must either accept on faith or reject and lose the orchestrator's value.

**Recommendation:** Show the expansion score table before the options:

```markdown
## Expansion Analysis

| Agent | Expansion Score | Reason |
|-------|----------------|--------|
| fd-correctness | 5 | P0 in adjacent domain (game-design) +3, domain criteria (simulation) +1, P1 in adjacent domain +2 |
| fd-performance | 3 | P0 in adjacent domain (game-design) +3 |
| fd-quality | 1 | Domain criteria (game) +1 |

Recommendation: Launch fd-correctness + fd-performance (scores ≥3).

Options:
- Launch fd-correctness + fd-performance (Recommended)
- Launch all Stage 2 (5 agents)
- Stop here
```

This makes the recommendation INSPECTABLE. Users can verify the logic and challenge the adjacency map if it's wrong.

### IMP-7: Repo review uses same "document profile" language as single-file review — confusion
**Location:** Step 1.1: Analyze the Document

The spec uses "Document Profile" for both:
- Single-file reviews (plan, spec, README)
- Repo reviews (directory input)

For repo reviews, the "document" is the entire codebase, which is confusing. Users expect:
- Document = a file
- Repo = a directory

The profile structure is the same, but calling it "Document Profile" for a repo review creates cognitive dissonance.

**User impact:** Users scanning the profile wonder: "Why does it say 'Document Profile' when I passed a directory? Did I invoke flux-drive wrong?"

**Recommendation:** Rename based on input type:
- `INPUT_TYPE = file` → "Document Profile"
- `INPUT_TYPE = directory` → "Repository Profile"
- `INPUT_TYPE = diff` → "Diff Profile" (already uses this name)

Or use a unified name: "Review Profile" (covers all input types).

### IMP-8: No recovery path when user realizes flux-drive was the wrong tool mid-run
**Location:** Integration

The spec has two cancellation points:
1. Step 1.3: User Confirmation → "Cancel" stops before launch
2. Step 2.2b: Domain-aware expansion → "Stop here" skips Stage 2

But there's no "cancel and pivot" option. If the user realizes mid-run that flux-drive was overkill (e.g., they just wanted a quick architecture check, not a 6-agent deep-dive), they must:
- Cancel the run (lose all agent work completed so far)
- Manually invoke the one agent they actually wanted

**User scenario:**
1. User runs flux-drive on a 50-line README
2. Triage selects 5 agents
3. User approves (didn't realize it would be this heavy)
4. Stage 1 completes (fd-architecture, fd-quality)
5. Expansion decision: "Launch 3 more agents?"
6. User thinks: "This is overkill for a README. I just wanted architecture feedback."

Options:
- "Launch 3 more agents"
- "Stop here"

Neither option is: "Stop and keep only fd-architecture's findings."

**User impact:** Users cannot downscope mid-run. They either commit to the full review or abandon all work (including completed agents).

**Recommendation:** Add a "Keep Stage 1 only, skip synthesis" option at the expansion decision point:

```yaml
AskUserQuestion:
  question: "Stage 1 complete. [findings summary]. [expansion reasoning]"
  options:
    - label: "Launch [agents] (Recommended)"
    - label: "Launch all Stage 2"
    - label: "Stop here — synthesize Stage 1 findings"
      description: "Proceed to synthesis with Stage 1 agents only"
    - label: "Cancel — keep Stage 1 outputs only"
      description: "Skip synthesis, keep individual agent .md files in {OUTPUT_DIR}/"
```

The "Cancel" option skips synthesis but preserves Stage 1 agent outputs. The user can manually read `fd-architecture.md` without waiting for a full synthesis report they don't need.

## Overall Assessment

flux-drive implements a sophisticated orchestration pattern (triage → staged dispatch → synthesis → compounding) but exposes rough edges in the user journey: two P0 gaps (no escape hatch from triage loops, blind expansion decisions) block confident first-time use, five P1 issues (scoring opacity, misleading convergence, silent failures, progress gaps, Oracle recovery) create friction at key decision points, and eight improvements (outcome-focused tables, write-back defaults, interactive editing, bead confirmations, Oracle visibility, expansion transparency, naming clarity, mid-run pivots) would lift usability to match the orchestration's technical sophistication. The skill is usable but demands user trust where transparency would serve better.

<!-- flux-drive:complete -->
