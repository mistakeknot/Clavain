# Flux Drive Synthesis — Clavain v2 (Post-Cleanup)

Reviewed by 5 agents (3 codebase-aware T1, 2 generic T3) on 2026-02-08.

## Convergence Map

| Finding | fd-arch | fd-quality | fd-security | simplicity | patterns | Convergence |
|---------|---------|------------|-------------|------------|----------|-------------|
| Hooks underdocumented (count + content) | P0-1, P0-2 | — | — | — | P0-1 | 2/5 |
| agent-native-architecture XML tags | — | P0-1 | — | — | — | 1/5 |
| Prompt injection via upstream sync | — | — | P0-1 | — | — | 1/5 |
| JSON injection in agent-mail-register.sh | — | — | P1-1 | — | — | 1/5 |
| Broad Bash tool access in sync.yml | — | — | P1-2 | — | — | 1/5 |
| engineering-docs duplicate headings | — | P1-1 | — | — | — | 1/5 |
| engineering-docs overweight (489 lines) | — | — | — | P1-1 | — | 1/5 |
| writing-skills overweight (656 lines) | — | — | — | P1-2 | — | 1/5 |
| learnings cmd duplicates engineering-docs | — | — | — | P1-3 | — | 1/5 |
| review.md overweight (455 lines) | — | — | — | P1-4 | — | 1/5 |
| review.md stale .claude/skills/ paths | P1-2 | — | — | — | — | 1/5 |
| AGENTS.md references missing script | P1-3 | — | — | — | — | 1/5 |
| Red Flags table bloat (per-session cost) | — | — | — | P0-1 | — | 1/5 |
| plan-reviewer.md block scalar description | — | — | — | — | P1-1 | 1/5 |
| pr-comment-resolver orphan color field | — | P2-2 | — | — | P1-2 | 2/5 |
| resolve-* commands near-identical | — | — | — | P2-1 | P1-3 | 2/5 |
| argument-hint quoting inconsistency | — | P2-1 | — | — | P1-4 | 2/5 |
| flux-drive hardcodes gurgeh-plugin | — | — | — | — | P1-5 | 1/5 |
| brainstorm.md dual upstream mapping | — | — | — | — | P1-6 | 1/5 |
| trunk-based policy violations in cmds | — | — | — | — | P1-7 | 1/5 |
| escape_for_json duplicated in 2 hooks | — | — | — | — | P2-1 | 1/5 |

## Key Findings

1. **Hooks documentation gap (2/5 agents):** The hook system grew from 1 to 3 scripts across 2 lifecycle events, but all documentation still says "2 hooks" / "only SessionStart." This is the highest-convergence finding.

2. **agent-native-architecture still has XML tags (1/5):** The XML-to-markdown cleanup missed this skill entirely — 9 XML tag pairs remain (`<why_now>`, `<core_principles>`, `<intake>`, etc.).

3. **Upstream sync prompt injection risk (1/5):** The sync workflow auto-merges untrusted upstream content into skill files that become system prompts. No CODEOWNERS, branch protection, or prompt injection scanning.

4. **Overweight skills and commands (1/5):** `writing-skills` (656 lines), `engineering-docs` (489 lines), `review.md` (455 lines), `learnings.md` (200 lines) all exceed recommended sizes. The thin-shim pattern (like `execute-plan.md` at 10 lines) should be the model.

5. **Red Flags table context cost (1/5):** The 16-line rationalization-prevention table in `using-clavain/SKILL.md` is injected into every session. It says the same thing 11 ways — the existing rule statement already covers it.

## Issues to Address

### P0 — Must Fix (4 deduplicated)
- [ ] **Hook count mismatch** — Update all docs from "2 hooks" to "3 hooks, 2 events" (fd-architecture, patterns: 2/5)
- [ ] **AGENTS.md "only SessionStart" claim** — Document SessionEnd hook + all 3 scripts (fd-architecture: 1/5)
- [ ] **agent-native-architecture XML tags** — Convert 9 XML tag pairs to markdown headings (fd-code-quality: 1/5)
- [ ] **Upstream sync prompt injection** — Add CODEOWNERS + branch protection for sync PRs (fd-security: 1/5)

### P1 — Should Fix (14 deduplicated)
- [ ] **JSON injection in agent-mail-register.sh** — Use jq for JSON construction (fd-security: 1/5)
- [ ] **Broad Bash access in sync.yml** — Narrow allowedTools to read-only git ops (fd-security: 1/5)
- [ ] **engineering-docs duplicate headings** — Remove 3 duplicate heading pairs from conversion (fd-code-quality: 1/5)
- [ ] **engineering-docs overweight** — Extract process details to sub-files, cut to <200 lines (simplicity: 1/5)
- [ ] **writing-skills overweight** — Extract TDD tutorial to reference sub-file (simplicity: 1/5)
- [ ] **learnings cmd duplicates engineering-docs** — Convert to thin shim (simplicity: 1/5)
- [ ] **review.md overweight + stale paths** — Strip stakeholder analysis, fix .claude/skills/ paths (simplicity + fd-architecture: 2/5)
- [ ] **AGENTS.md references missing sync-upstreams.sh** — Fix or remove reference (fd-architecture: 1/5)
- [ ] **plan-reviewer.md block scalar** — Switch to inline quoted description (patterns: 1/5)
- [ ] **resolve-* commands near-identical** — Consolidate shared sections (simplicity + patterns: 2/5)
- [ ] **flux-drive hardcodes gurgeh-plugin** — Add fallback for absent plugin (patterns: 1/5)
- [ ] **brainstorm.md dual upstream mapping** — Remove from one upstream (patterns: 1/5)
- [ ] **trunk-based policy violations** — Remove branch/worktree refs from work.md and review.md (patterns: 1/5)
- [ ] **Red Flags table bloat** — Cut or consolidate to 3-4 lines (simplicity: 1/5)

### P2 — Nice to Have (10 deduplicated)
- [ ] argument-hint quoting inconsistency (2/5)
- [ ] pr-comment-resolver orphan color field (2/5)
- [ ] Architecture diagrams omit 2 hook scripts (1/5)
- [ ] Validation scripts only check 1 of 3 hooks (1/5)
- [ ] escape_for_json duplicated in 2 hooks (1/5)
- [ ] allowed-tools format varies across commands (1/5)
- [ ] CREATION-LOG.md orphan in systematic-debugging (1/5)
- [ ] learnings-researcher model: haiku undocumented (1/5)
- [ ] codex-delegation missing from routing table Layer 2 (1/5)
- [ ] dotfiles-sync.sh hardcodes absolute path (1/5)

## Agent Reports

| Agent | Tier | Verdict | P0 | P1 | P2 | Report |
|-------|------|---------|----|----|-----|--------|
| fd-architecture | T1 | needs-changes | 2 | 3 | 3 | [fd-architecture.md](fd-architecture.md) |
| fd-code-quality | T1 | needs-changes | 1 | 1 | 2 | [fd-code-quality.md](fd-code-quality.md) |
| fd-security | T1 | needs-changes | 1 | 2 | 2 | [fd-security.md](fd-security.md) |
| code-simplicity-reviewer | T3 | needs-changes | 1 | 4 | 3 | [code-simplicity-reviewer.md](code-simplicity-reviewer.md) |
| pattern-recognition-specialist | T3 | needs-changes | 1 | 7 | 6 | [pattern-recognition-specialist.md](pattern-recognition-specialist.md) |

## Comparison with v1 Review

| Metric | v1 (pre-cleanup) | v2 (post-cleanup) |
|--------|------------------|-------------------|
| Agents | 6 | 5 |
| Total issues (raw) | 29 | 28 |
| Deduplicated issues | 29 | 28 |
| P0 issues | 3 | 4 |
| P1 issues | 11 | 14 |
| P2 issues | 15 | 10 |
| Verdicts | 6x needs-changes | 5x needs-changes |

The v1 findings were mostly surface-level (stale counts, typos, Rails content, broken file paths). The v2 findings go deeper: architectural documentation gaps (hooks), security concerns (sync pipeline), and complexity/duplication issues. This is expected — the easy wins are done, now the structural issues are visible.
