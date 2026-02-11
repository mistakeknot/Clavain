# Flux-Drive Review — Clavain Plugin (v0.4.26)

**Date:** 2026-02-10
**Input:** `/root/projects/Clavain` (directory, repo-review)
**Agents:** fd-architecture, fd-quality, fd-user-product, fd-safety, fd-performance
**Failed:** oracle-council (exit 124 — timeout)
**Verdict:** needs-changes

---

## Key Findings

### Critical (P0)

| ID | Finding | Agent | Section |
|----|---------|-------|---------|
| P0-1 | `/triage` references non-existent `/resolve_todo_parallel` command — user hits dead end after completing triage | fd-user-product | Command References |

### Important (P1)

| ID | Finding | Agent(s) | Convergence |
|----|---------|----------|-------------|
| P1-1 | `upstreams.json` fileMap has 32 stale entries pointing to deleted files — next sync could re-create legacy agents | fd-architecture | 1 |
| P1-2 | Hook count says "3 hooks" everywhere but plugin has 4 events and 5 scripts | fd-architecture, fd-quality | **2** |
| P1-3 | 3-4 overlapping review entry points (`/review`, `/quality-gates`, `/flux-drive`, `/plan-review`) with no selection guidance | fd-architecture, fd-user-product | **2** |
| P1-4 | `generate-command.md` frontmatter uses underscore (`generate_command`) instead of kebab-case | fd-quality | 1 |
| P1-5 | Missing `name-matches-filename` tests for skills and commands (test gap that allowed P1-4) | fd-quality | 1 |
| P1-6 | No guided first-use path — `/setup` sends users directly to `/lfg` (most complex command) | fd-user-product | 1 |
| P1-7 | `/changelog` references non-existent `EVERY_WRITE_STYLE.md` file (upstream remnant) | fd-user-product | 1 |
| P1-8 | 3 skills (`prompterpeer`, `winterpeer`, `splinterpeer`) missing from README — inflates "34 skills" count | fd-user-product, fd-quality | **2** |
| P1-9 | 113-line routing table injected every session with no progressive disclosure (~3k tokens) | fd-user-product | 1 |
| P1-10 | Bats autopilot test creates symlinks for all system binaries — 6.8s (67% of shell test time) | fd-performance | 1 |
| P1-11 | Full flux-drive orchestrator consumes ~14k tokens before any agent work begins | fd-performance | 1 |

### Convergent Findings (2+ agents independently flagged)

Three findings had multi-agent convergence:
1. **Hook count drift** (P1-2) — fd-architecture and fd-quality both identified the "3 hooks" claim as wrong
2. **Review entry point confusion** (P1-3) — fd-architecture and fd-user-product both flagged the 3-4 overlapping review commands
3. **Missing skills in README** (P1-8) — fd-user-product and fd-quality both found the 3 interpeer sub-skills absent from documentation

### Safety Assessment

fd-safety rated the plugin **safe** with no high-severity vulnerabilities. Key notes:
- SAF-01 (MEDIUM): `auto-compound.sh` JSON interpolation is fragile but not exploitable today
- SAF-02 (MEDIUM): Upstream sync supply chain risk mitigated by decision-gate workflow
- SAF-03 (MEDIUM): PR agent workflow `focus` parameter interpolated into heredoc — collaborator-only risk
- No blocking security findings

---

## Improvements Suggested

| ID | Improvement | Agent(s) | Section | Effort |
|----|-------------|----------|---------|--------|
| IMP-1 | Extract `_parse_frontmatter` to `conftest.py` (duplicated 3x in test files) | fd-architecture, fd-quality | Test Infrastructure | Low |
| IMP-2 | Add automated test validating `upstreams.json` fileMap targets exist | fd-architecture | Upstream Sync | Low |
| IMP-3 | fd-* agents lack output format spec — entirely dependent on caller injection | fd-quality, fd-architecture | Agent System Prompts | Medium |
| IMP-4 | Add `/quickstart` command for guided first-use cycle | fd-user-product | First-Run Experience | Medium |
| IMP-5 | Consolidate review entry points with argument-based routing or clearer naming | fd-user-product | Command Naming | Medium |
| IMP-6 | Add "Getting Started in 5 Minutes" section to README | fd-user-product | README | Low |
| IMP-7 | `auto-compound.sh` should use `jq` or `escape_for_json` instead of raw heredoc interpolation | fd-safety, fd-quality | Hook Security | Low |
| IMP-8 | Bats tests run serially; parallel execution (`--jobs 4`) would cut wall time 10s → ~3s | fd-performance | Test Suite | Low |
| IMP-9 | Move scoring examples to sub-file to save ~477 tokens per session | fd-performance | Flux-Drive | Low |
| IMP-10 | Pipeline qmd knowledge queries instead of serial per-agent retrieval | fd-performance | Flux-Drive | Low (prompt clarification) |

---

## Section Heat Map

| Section | Findings | Improvements | Agents Flagging |
|---------|----------|-------------|-----------------|
| Command References / Naming | P0-1, P1-3, P1-4, P1-7 | IMP-5 | 3 |
| Documentation Accuracy | P1-2, P1-8, P1-9 | IMP-6 | 3 |
| Upstream Sync | P1-1 | IMP-2 | 1 |
| Test Coverage | P1-5, P1-10 | IMP-1, IMP-8 | 2 |
| First-Run Experience | P1-6 | IMP-4 | 1 |
| Flux-Drive Token Budget | P1-11 | IMP-9, IMP-10 | 1 |
| Agent System Design | — | IMP-3 | 2 |
| Hook Security | — | IMP-7 | 2 |

**Hottest sections:** Command References/Naming (4 findings, 3 agents) and Documentation Accuracy (3 findings, 3 agents).

---

## Conflicts

No direct conflicts between agent findings. All convergent findings were in agreement on both diagnosis and suggested fix direction.

---

## Files

| File | Size |
|------|------|
| [fd-architecture.md](fd-architecture.md) | 11,726 bytes |
| [fd-quality.md](fd-quality.md) | 11,570 bytes |
| [fd-user-product.md](fd-user-product.md) | 16,422 bytes |
| [fd-safety.md](fd-safety.md) | 18,217 bytes |
| [fd-performance.md](fd-performance.md) | 12,544 bytes |
| [oracle-council.md](oracle-council.md) | 113 bytes (error) |
| [findings.json](findings.json) | consolidated |

---

## Oracle Council

Oracle timed out (exit 124) during cross-AI review. The ~19k token input exceeded the browser-mode processing window within the 480s timeout. Oracle results are not included in the synthesis. Consider re-running Oracle standalone on specific high-convergence findings if cross-AI validation is desired.

<!-- flux-drive:complete -->
