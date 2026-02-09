# Flux-Drive Summary: Clavain v0.4.6

> Full repo review — 7 agents across 2 tiers, run 2026-02-09

## Agents Deployed

| Agent | Tier | Verdict |
|-------|------|---------|
| fd-architecture | T1 | needs-changes |
| fd-code-quality | T1 | PASS with issues |
| fd-user-experience | T1 | needs-changes |
| fd-security | T1 | PASS with conditions |
| fd-performance | T1 | needs-changes |
| pattern-recognition-specialist | T3 | needs-changes |
| code-simplicity-reviewer | T3 | needs-changes |

**Overall verdict: needs-changes** — No critical runtime bugs, but documentation drift, token efficiency gaps, security hardening needs, and structural redundancy require attention.

---

## Deduplicated Findings

Issues are deduplicated across agents and re-ranked. Where multiple agents flagged the same issue, the originating agents are listed.

### P0 — Must Fix (4 issues)

| ID | Title | Agents | Files |
|----|-------|--------|-------|
| P0-1 | **Review agent count stale across 5 surfaces** (says 15/20, actual 21) | fd-architecture, fd-code-quality, pattern-recognition | AGENTS.md:40, AGENTS.md:275, README.md:234, README.md:259, docs/plugin-audit.md:21 |
| P0-2 | **CLAUDE.md validation comment says 28 agents, actual 29** | fd-architecture | CLAUDE.md:17 |
| P0-3 | **README disabled-conflicts table lists 5 of 8 disabled plugins** (missing claude-md-management, frontend-design, hookify) | fd-code-quality | README.md:232-238 |
| P0-4 | **using-clavain session injection is ~2,160 tokens per session, non-evictable on compact** | fd-performance | skills/using-clavain/SKILL.md (via session-start.sh hook) |

### HIGH — Security (2 issues)

| ID | Title | Agent | Files |
|----|-------|-------|-------|
| SEC-1 | **GitHub Actions script injection**: PR comment body interpolated directly into JS template literals via `${{ }}` | fd-security | .github/workflows/pr-agent-commands.yml:75,203 |
| SEC-2 | **Codex runs with `danger-full-access` sandbox in CI**, granting unrestricted filesystem + network access, with auth.json readable | fd-security | .github/workflows/sync.yml:84 |

### P1 — Should Fix (14 issues)

| ID | Title | Agents | Files |
|----|-------|--------|-------|
| P1-1 | **CLAUDE.md omits Rust from language-specific reviewers list** | fd-architecture | CLAUDE.md:31 |
| P1-2 | **AGENTS.md scripts/ tree incomplete** — shows 1 of 5 scripts | fd-architecture | AGENTS.md:53-54 |
| P1-3 | **AGENTS.md + README.md .github/workflows/ trees incomplete** — shows 2-4 of 8 workflows | fd-architecture | AGENTS.md, README.md |
| P1-4 | **README flux-drive roster claim inflated** — says "28 agents across 4 tiers", actual fixed roster is 19 | fd-architecture | README.md:58 |
| P1-5 | **5 fd-* agents missing `<example>` blocks** in frontmatter description | fd-code-quality, pattern-recognition | agents/review/fd-*.md |
| P1-6 | **6 skills deviate from "Use when" description pattern** | fd-code-quality | clodex, interpeer, prompterpeer, winterpeer, splinterpeer, brainstorming |
| P1-7 | **3 commands (setup, compound, interpeer) absent from routing tables** | fd-code-quality, fd-user-experience, pattern-recognition | skills/using-clavain/SKILL.md |
| P1-8 | **Execute stage overloaded** — 9 commands in one routing row | fd-user-experience | skills/using-clavain/SKILL.md:39 |
| P1-9 | **/lfg Step 3 silently skips under clodex mode** — no user notification | fd-user-experience | commands/lfg.md:19-27 |
| P1-10 | **Three resolve-* commands indistinguishable by name** — all resolve TODOs from different sources | fd-user-experience, pattern-recognition, code-simplicity | commands/resolve-*.md |
| P1-11 | **/lfg has no error recovery guidance** when steps fail mid-pipeline | fd-user-experience | commands/lfg.md |
| P1-12 | **Flux-drive SKILL.md is 32KB monolith** — Codex dispatch section (4.5KB) is dead weight in Task path | fd-performance | skills/flux-drive/SKILL.md |
| P1-13 | **28 of 29 agents use model: inherit** — no tiering for mechanical/checklist tasks | fd-performance, code-simplicity | agents/review/*.md |
| P1-14 | **/review command lacks run_in_background directive** for agent dispatch | fd-performance | commands/review.md |

### MEDIUM — Security (4 issues)

| ID | Title | Agent | Files |
|----|-------|-------|-------|
| SEC-3 | **dispatch.sh whitelists --yolo and --dangerously-bypass-approvals-and-sandbox** for passthrough | fd-security | scripts/dispatch.sh:143 |
| SEC-4 | **Three workflows use pull_request_target** — currently safe but fragile | fd-security | .github/workflows/upstream-impact.yml, upstream-decision-gate.yml, codex-refresh-reminder-pr.yml |
| SEC-5 | **escape_for_json in lib.sh omits control characters** U+0000-U+001F beyond tab/CR/LF | fd-security | hooks/lib.sh:6-14 |
| SEC-6 | **AGENT_MAIL_URL overridable via environment** — registration traffic redirectable | fd-security | hooks/agent-mail-register.sh:20 |

### P2 — Nice to Have (18 issues)

| ID | Title | Agents |
|----|-------|--------|
| P2-1 | codex-first and clodex-toggle are duplicate commands for one toggle | fd-user-experience, pattern-recognition, code-simplicity |
| P2-2 | Inconsistent agent suffix taxonomy (7+ patterns across 21 review agents) | fd-code-quality, pattern-recognition |
| P2-3 | review, quality-gates, plan-review, flux-drive are four overlapping review entry points | code-simplicity |
| P2-4 | Tier 1 fd-* agents duplicate Tier 3 agents for same domains | code-simplicity |
| P2-5 | Four cross-AI skills (interpeer stack) could be one skill with escalation modes | code-simplicity, pattern-recognition |
| P2-6 | /work Phase 4 step numbering jumps from 2 to 4 (step 3 missing) | fd-user-experience |
| P2-7 | /triage broken markdown — code fence leaks into subsequent content | fd-user-experience |
| P2-8 | Setup verification script is cosmetic — loops print "checking" without actual checks | fd-user-experience |
| P2-9 | work vs execute-plan distinction unclear in routing table | fd-user-experience |
| P2-10 | No progressive onboarding — new users face 27 commands immediately | fd-user-experience |
| P2-11 | flux-drive dual dispatch paths (Task vs Codex) maintained in parallel | code-simplicity |
| P2-12 | writing-skills at 520 lines has checklist redundancy with TDD skill | code-simplicity |
| P2-13 | engineering-docs at 419 lines over-specified for documentation capture | code-simplicity |
| P2-14 | concurrency-reviewer at 606 lines — 20KB of inline code examples across 5 languages | fd-performance, code-simplicity |
| P2-15 | Session-start hook uses serial I/O probes (find, curl, pgrep) adding latency | fd-performance |
| P2-16 | /lfg steps 4+5 launch overlapping review agents on same codebase | fd-performance |
| P2-17 | brainstorm (command) vs brainstorming (skill) naming is counterintuitive | pattern-recognition |
| P2-18 | Phantom /clavain:tool-time reference in setup.md (tool-time is a separate plugin) | pattern-recognition |

### LOW — Security (4 issues)

| ID | Title | Agent |
|----|-------|-------|
| SEC-7 | Autopilot flag file has no access control | fd-security |
| SEC-8 | External sync script executed without integrity check | fd-security |
| SEC-9 | Predictable temp file paths in debate.sh | fd-security |
| SEC-10 | Agent Mail MCP server on localhost without authentication | fd-security |

---

## Cross-Agent Agreement Matrix

Issues flagged by 3+ agents carry highest confidence:

| Finding | Agents Agreeing | Confidence |
|---------|----------------|------------|
| Review agent count stale (20→21) | 3 (arch, quality, pattern) | Very High |
| 3 commands missing from routing tables | 3 (quality, UX, pattern) | Very High |
| resolve-* naming confusion | 3 (UX, pattern, simplicity) | Very High |
| codex-first/clodex-toggle duplication | 3 (UX, pattern, simplicity) | Very High |
| fd-* agents missing `<example>` blocks | 2 (quality, pattern) | High |
| Model tiering opportunity | 2 (performance, simplicity) | High |
| using-clavain session injection oversized | 2 (performance, simplicity) | High |
| No /lfg error recovery | 1 (UX) | Moderate |
| GitHub Actions script injection | 1 (security) | High (domain expertise) |

---

## Top 10 Recommended Actions (Priority Order)

### Quick Wins (< 30 minutes each)

1. **Fix review agent counts** — 5 line edits across 3 files. Changes "15" and "20" to "21" everywhere. (P0-1)

2. **Fix CLAUDE.md validation comment** — change "28" to "29", add Rust to language list. (P0-2, P1-1)

3. **Complete README conflicts table** — add 3 missing disabled plugins. (P0-3)

4. **Fix setup.md phantom reference** — remove `/clavain:` prefix from `tool-time`. (P2-18)

5. **Delete clodex-toggle command** — it's a 16-line alias file for codex-first. (P2-1)

6. **Add run_in_background to /review** — one-line addition matching flux-drive convention. (P1-14)

### Medium Effort (1-3 hours each)

7. **Sanitize GitHub Actions interpolations** — replace `${{ }}` in JS blocks with `process.env.*` pattern. (SEC-1)

8. **Tiered model assignment** — assign `model: sonnet` to fd-code-quality, fd-user-experience, pattern-recognition-specialist, shell-reviewer, code-simplicity-reviewer, deployment-verification-agent; `model: haiku` to git-history-analyzer. (P1-13)

9. **Trim using-clavain session injection** — split into essential routing (~40 lines, 1KB) + on-demand full reference. 58% reduction in permanent session overhead. (P0-4)

10. **Add error recovery to /lfg** — document stop-on-failure, retry, and resume-from-step-N instructions. (P1-11)

### Strategic (Multi-session)

- Merge Tier 1/3 agent pairs (architecture, security, performance) into conditional agents
- Split flux-drive SKILL.md into progressive phase files
- Consolidate 3 resolve-* commands into single `/resolve` with auto-detection
- Merge 4 cross-AI skills into single skill with escalation modes
- Extract concurrency-reviewer code examples to references/ directory

---

## Metrics

| Metric | Current | After Quick Wins | After All |
|--------|---------|-----------------|-----------|
| Documentation accuracy | ~85% (stale sub-counts) | ~98% | 100% |
| Security score | Pass with conditions | Improved (SEC-1 fixed) | Hardened |
| Session token overhead | ~2,160 tokens | ~2,160 tokens | ~900 tokens |
| Agent cost per review | ~$0.22 (5 Opus agents) | ~$0.22 | ~$0.09 (3 Sonnet + 2 Opus) |
| Skills | 34 | 34 | 28 (-6 from merges) |
| Commands | 27 | 26 (-clodex-toggle) | 23 (-4 from consolidation) |
| Agents | 29 | 29 | 25 (-4 from Tier merges) |
| /lfg pipeline steps | 7 | 7 | 6 (merge review+quality) |

---

## Individual Reports

- [fd-architecture.md](fd-architecture.md) — Architecture tree accuracy, component count consistency, pipeline coherence
- [fd-code-quality.md](fd-code-quality.md) — Naming conventions, frontmatter schema, routing coverage, documentation drift
- [fd-user-experience.md](fd-user-experience.md) — Command naming, pipeline UX, onboarding, error recovery
- [fd-security.md](fd-security.md) — Hook scripts, dispatch.sh, GitHub Actions, MCP server config
- [fd-performance.md](fd-performance.md) — Token costs, session injection, model tiering, agent dispatch
- [pattern-recognition-specialist.md](pattern-recognition-specialist.md) — Cross-reference consistency, naming patterns, routing completeness
- [code-simplicity-reviewer.md](code-simplicity-reviewer.md) — Redundancy analysis, simplification opportunities, component consolidation
