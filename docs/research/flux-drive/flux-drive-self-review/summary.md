## Flux Drive Self-Review: Agent Orchestration Analysis

Reviewed by 5 Claude agents + Oracle (GPT-5.2 Pro, failed — timeout) on 2026-02-09.

**Oracle status:** Timed out after 480s (exit 124). Cross-AI perspective unavailable for this review. The `|| echo` error handler wrote failure notice to output file as designed.

### Key Findings

1. **YAML frontmatter contract is the system's Achilles heel** (P0, 3/5 agents) — The entire synthesis pipeline depends on agents producing machine-parseable YAML, but 16/18 agents have incompatible native output formats. The runtime prompt override ("IGNORE your default format") is probabilistic, not guaranteed. Synthesis already includes a prose fallback, which is a design-time admission of unreliability.

2. **No completeness signal for parallel agents** (P0, 2/5 agents) — File existence is the sole completion predicate, but existence ≠ completeness. A partially-written file passes the check. Concurrency-reviewer recommends atomic write-then-rename or an end-of-file sentinel marker.

3. **3-5 minute silent wait is unacceptable UX** (P0, 2/5 agents) — Users see nothing between "6 agents launched" and the synthesis report. No per-agent completion ticks, no progress bar, no way to distinguish work from hang.

4. **Step 3.5 (final report) is the least specified output** (P0, 1/5 agents) — The skill's primary deliverable to the user has no template. The agent prompt template is 90 lines of precise formatting; the user-facing synthesis is "tell the user top findings."

5. **Dual dispatch maintains a parallel universe for marginal gain** (P1, 3/5 agents) — launch-codex.md is 112 lines duplicating launch.md in a different dialect, with its own error handling, path resolution, and template vocabulary. Codex dispatch is a cost optimization, not a capability difference.

### Issues to Address

- [ ] **P0**: Define a completeness signal — atomic write-then-rename or end-of-file sentinel (concurrency-reviewer, architecture-strategist)
- [ ] **P0**: Add per-agent completion ticks during the wait period (fd-user-experience, concurrency-reviewer)
- [ ] **P0**: Create a synthesis report template with the same rigor as the agent prompt template (fd-user-experience)
- [ ] **P0/P1**: Reduce fragility of YAML frontmatter contract — either add frontmatter examples to agent system prompts, or simplify to prose-only with structured headings (architecture-strategist, code-simplicity, fd-code-quality)
- [ ] **P1**: Merge or reduce launch-codex.md — either fold into launch.md with a conditional, or extract shared output format spec (architecture-strategist, fd-code-quality, code-simplicity)
- [ ] **P1**: Add timeout to foreground retry (concurrency-reviewer)
- [ ] **P1**: Simplify Phase 4 — collapse 97-line cross-AI pipeline into a concise coda (code-simplicity, fd-user-experience)
- [ ] **P1**: Remove thin-section deepening from synthesis — let users re-run flux-drive on updated docs instead (code-simplicity)
- [ ] **P1**: Fix tier vocabulary — remove unused "domain" tier or define it (fd-code-quality, architecture-strategist)
- [ ] **P1**: Add user consent gate before auto-chaining to interpeer mine mode (fd-user-experience)
- [ ] **P1**: Default to summary.md for file inputs too, with opt-in for inline annotations (fd-user-experience)
- [ ] **P1**: Stagger Codex dispatch to avoid API rate limit thundering herd (concurrency-reviewer)
- [ ] **P2**: Consider reducing agent cap from 8 to 5 (code-simplicity)
- [ ] **P2**: Evaluate whether token trimming is necessary with 200K context windows (code-simplicity)
- [ ] **P2**: Guard temp directory cleanup against late-finishing Codex agents (concurrency-reviewer)

### Agent Verdicts

| Agent | Verdict | Issues | Improvements |
|-------|---------|--------|-------------|
| architecture-strategist | needs-changes | 3 P0-P1, 4 P2 | 5 |
| fd-code-quality | needs-changes | 3 P1, 3 P2 | 4 |
| fd-user-experience | needs-changes | 2 P0, 6 P1, 4 P2 | 6+ |
| code-simplicity-reviewer | needs-changes | 3 P1, 5 P2 | 6 |
| concurrency-reviewer | needs-changes | 2 P0, 4 P1, 2 P2 | 5 |
| oracle-council | error (timeout) | — | — |

### Section Heat Map

| Section | Findings | Agents |
|---------|----------|--------|
| Phase 2: Launch (dispatch + prompts) | 12 | all 5 |
| Phase 3: Synthesize (collection + dedup) | 6 | 4/5 |
| Phase 4: Cross-AI Escalation | 5 | 3/5 |
| Phase 1: Triage + Scoring | 4 | 2/5 |
| Agent Output Contract (YAML) | 4 | 3/5 |

### Cross-AI Summary

Oracle (GPT-5.2 Pro) timed out after 480 seconds. No cross-AI comparison available.

**Cross-AI option:** `/clavain:interpeer` (quick mode) for a Claude↔Codex second opinion on specific findings.

### Full Analysis Files

- `architecture-strategist.md` — phase boundaries, dual dispatch, output contract, cross-skill integration
- `fd-code-quality.md` — naming consistency, tier vocabulary, template duplication, convention adherence
- `fd-user-experience.md` — user journey, progress feedback, confirmation UX, escalation discoverability
- `code-simplicity-reviewer.md` — YAGNI analysis, dual dispatch justification, token trimming, Phase 4 complexity
- `concurrency-reviewer.md` — completion signals, race conditions, retry timeouts, rate limiting
- `oracle-council.md` — Oracle timeout failure (480s, exit 124)
