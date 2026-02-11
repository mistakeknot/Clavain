### Findings Index
- P1 | P1-1 | "Upstream Sync Architecture" | upstreams.json fileMap has 32 stale entries pointing to deleted files
- P1 | P1-2 | "Documentation Consistency" | Hook count in all documentation surfaces says "3 hooks" but plugin has 4 hook events and 5 hook scripts
- P1 | P1-3 | "Review Command Overlap" | Three review entry points (review, quality-gates, flux-drive) have overlapping agent dispatch with no documented selection guidance
- P2 | P2-1 | "auto-compound.sh Omitted from Validation" | auto-compound.sh not listed in CLAUDE.md or AGENTS.md validation checklists
- P2 | P2-2 | "Stop Hook Missing Matcher" | Stop hook in hooks.json has no matcher field unlike other hook events
- IMP | IMP-1 | "Test Infrastructure" | _parse_frontmatter duplicated 3x across test files -- extract to conftest.py
- IMP | IMP-2 | "Upstream FileMap Lifecycle" | No automated test validates that fileMap targets in upstreams.json exist on disk
- IMP | IMP-3 | "Diff Routing and Skill Phase Structure" | flux-drive skill is well-architected but phase file numbering is inconsistent (Step 2.1b appears after Step 2.2c)
Verdict: needs-changes

### Summary (3-5 lines)

The Clavain plugin (v0.4.26) has solid structural foundations: 427 pytest tests pass, all components follow naming conventions, frontmatter contracts are enforced, the 3-layer routing table correctly references all 34 skills, 16 agents, and 24 commands, and the flux-drive multi-agent review system is well-designed with staged dispatch, diff slicing, and knowledge injection. The primary architectural gaps are in the upstream sync layer (32 stale fileMap entries that would cause silent failures on next sync), documentation surface consistency (hook counts are wrong everywhere), and three overlapping review entry points that create user confusion about which to invoke.

### Issues Found

**P1-1: upstreams.json fileMap has 32 stale entries pointing to deleted files**

File: `/root/projects/Clavain/upstreams.json`

The compound-engineering upstream has 12 fileMap entries pointing to agents and commands that were deleted during the fd-* consolidation (architecture-strategist, code-simplicity-reviewer, deployment-verification-agent, python-reviewer, typescript-reviewer, pattern-recognition-specialist, performance-oracle, security-sentinel, spec-flow-analyzer, resolve-parallel, resolve-pr-parallel, resolve-todo-parallel). The oracle upstream has 8 entries for docs that were not synced. The mcp-agent-mail upstream has 7 entries for references that were not synced. The beads upstream has 2 entries for references that were not synced.

Impact: When the sync system (`.github/workflows/sync.yml` or `scripts/pull-upstreams.sh`) next runs, it will attempt to write to these 32 target paths. For the compound-engineering entries, this would re-create the legacy agents that were intentionally consolidated into fd-* agents, undoing the v2 consolidation. For the oracle/mcp-agent-mail/beads entries, it would create reference files that may or may not be useful.

Evidence: Running a script to check each fileMap target against disk shows all 32 missing. The compound-engineering entries are the most dangerous because they map to `agents/review/` and `commands/` -- active directories where re-created files would be picked up by tests and routing.

Smallest fix: Remove the 12 compound-engineering stale entries (agents and commands that map to deleted files). For the oracle/mcp-agent-mail/beads reference entries, either remove them from fileMap or run the sync to populate them -- the sync has apparently never been run for these reference files. Decision: if the references are wanted, run the sync; if not, remove the fileMap entries.

**P1-2: Hook count in all documentation surfaces says "3 hooks" but plugin has 4 hook events and 5 hook scripts** (independently confirmed)

Files: `/root/projects/Clavain/CLAUDE.md` (line 7), `/root/projects/Clavain/AGENTS.md` (line 12), `/root/projects/Clavain/README.md` (line 7), `/root/projects/Clavain/.claude-plugin/plugin.json` (description)

The `hooks/hooks.json` file registers 4 hook events:
1. PreToolUse (autopilot.sh)
2. SessionStart (session-start.sh, agent-mail-register.sh)
3. Stop (auto-compound.sh)
4. SessionEnd (dotfiles-sync.sh)

That is 5 hook scripts across 4 hook events. All documentation surfaces say "3 hooks." This was previously flagged in the v3 flux-drive review (knowledge context confirms this was noted on 2026-02-09) but has not been corrected. The Stop hook with auto-compound.sh appears to have been added after the count was established.

A previous review (knowledge entry, last confirmed 2026-02-09) noted that the count methodology was "defensible but worth noting." However, with the addition of the Stop hook (auto-compound.sh), even counting by events yields 4, not 3. The count is now simply wrong by any methodology.

Smallest fix: Update all 4 documentation surfaces to say "4 hooks" (counting by event type) or "5 hooks" (counting by script). Given that the AGENTS.md hooks section lists hooks by script name, "5 hooks" would be more consistent.

**P1-3: Three review entry points (review, quality-gates, flux-drive) have overlapping agent dispatch with no documented selection guidance**

Files:
- `/root/projects/Clavain/commands/review.md` -- launches fd-architecture, fd-safety, fd-quality, git-history-analyzer, agent-native-reviewer, conditionally fd-correctness and data-migration-expert
- `/root/projects/Clavain/commands/quality-gates.md` -- launches fd-architecture, fd-quality always, then risk-based fd-safety, fd-correctness, fd-performance, fd-user-product, data-migration-expert
- `/root/projects/Clavain/commands/flux-drive.md` -> `/root/projects/Clavain/skills/flux-drive/SKILL.md` -- scored triage from full 6-agent fd-* roster plus Oracle, with staged dispatch

All three commands dispatch overlapping subsets of the same fd-* agents but use different selection heuristics:
- `review` has a hardcoded roster of 5 always-launch agents (including non-fd agents like git-history-analyzer)
- `quality-gates` uses file-path-based risk classification with a 5-agent cap
- `flux-drive` uses scored triage with category bonuses, staged dispatch, and an 8-agent cap

The routing table in `using-clavain/SKILL.md` places all three in the "Review" stage but gives no guidance on which to choose. The `lfg` command chains to both `flux-drive` (for plan review in Step 3) and `quality-gates` (for code review in Step 6), which is correct differentiation, but a user who just says "review this" has no clear signal about which command to use.

The `work` command (line 135) delegates review to `/quality-gates`, providing one documented path, but this creates an implicit hierarchy (work -> quality-gates, lfg -> flux-drive + quality-gates) that is not surfaced in the routing table.

Smallest fix: Add a "When to use which review command" section to the routing table in `using-clavain/SKILL.md`:
- `/review` -- PR-focused review (takes PR number, GitHub URL)
- `/quality-gates` -- Quick code review on working changes (auto-selects from git diff)
- `/flux-drive` -- Deep document/repo/diff review with scored triage, staged dispatch, knowledge context

**P2-1: auto-compound.sh omitted from validation checklists**

Files: `/root/projects/Clavain/CLAUDE.md` (lines 19-23), `/root/projects/Clavain/AGENTS.md` (lines 196-201, 218-225)

Both CLAUDE.md and AGENTS.md list explicit `bash -n` syntax check commands for session-start.sh, autopilot.sh, agent-mail-register.sh, dotfiles-sync.sh, and lib.sh. The auto-compound.sh script is missing from both lists. The structural tests DO cover it (test_scripts.py dynamically finds all .sh files), but the manual validation checklists in documentation are incomplete.

Smallest fix: Add `bash -n hooks/auto-compound.sh` to both CLAUDE.md Quick Commands and AGENTS.md Validation Checklist sections.

**P2-2: Stop hook in hooks.json has no matcher field**

File: `/root/projects/Clavain/hooks/hooks.json` (lines 41-53)

The Stop hook registration lacks a `matcher` field, unlike PreToolUse (matcher: `Edit|Write|MultiEdit|NotebookEdit`) and SessionStart (matcher: `startup|resume|clear|compact`). While this may be intentional (Stop hooks may not support matchers in the Claude Code hook API), it is inconsistent with the other hook registrations and is not documented. The SessionEnd hook also lacks a matcher, but the AGENTS.md documentation does not discuss when Stop hooks fire.

Smallest fix: Add a comment in hooks.json or document in AGENTS.md that Stop and SessionEnd events do not use matchers (if that is the API constraint), or add an appropriate matcher if the API supports it.

### Improvements Suggested

**IMP-1: Extract _parse_frontmatter to conftest.py to eliminate 3x test duplication**

Files:
- `/root/projects/Clavain/tests/structural/test_agents.py` (line 9)
- `/root/projects/Clavain/tests/structural/test_skills.py` (line 10)
- `/root/projects/Clavain/tests/structural/test_commands.py` (line 10)

The `_parse_frontmatter(path)` function is identically defined in all three test files. It should be extracted to `conftest.py` (which already exists with shared fixtures) or to a `helpers.py` module. This is accidental copy-paste drift, not intentional duplication for isolation -- the function is identical in all three files.

**IMP-2: Add automated test validating upstreams.json fileMap targets exist**

File: `/root/projects/Clavain/tests/structural/`

The structural test suite validates routing table references, hook script existence, and frontmatter contracts, but there is no test that verifies `upstreams.json` fileMap targets resolve to existing files on disk. This is how 32 stale entries accumulated undetected. A test like `test_upstream_filemap_targets_exist` in a new `test_upstreams.py` (or in `test_cross_references.py`) would catch this class of drift immediately.

Note: The test would need to distinguish between "should exist now" entries (active skills, agents, commands) and "will be created on sync" entries (reference docs that have never been synced). One approach: test only entries where the target directory exists (e.g., agents/review/ exists, so entries targeting agents/review/foo.md should resolve).

**IMP-3: flux-drive skill phase step numbering is inconsistent**

File: `/root/projects/Clavain/skills/flux-drive/phases/launch.md`

Step 2.1b ("Prepare diff content for agent prompts") appears in the file after Steps 2.2, 2.2b, and 2.2c. The file reads: 2.0, 2.1, 2.1a, 2.2, 2.2b, 2.2c, then 2.1b. A reader following the "progressive loading" directive would encounter steps out of order. The intent is that 2.1b is a preparation step that should be read before 2.2, but its placement after 2.2c is confusing.

The flux-drive skill architecture is otherwise well-structured: the split into `SKILL.md` (routing/triage), `phases/launch.md` (dispatch), `phases/synthesize.md`, `phases/cross-ai.md`, and `phases/shared-contracts.md` keeps each concern in its own file with clear contracts between phases. The diff-routing configuration in `config/flux-drive/diff-routing.md` is a good separation of policy from mechanism.

### Overall Assessment

Clavain's component architecture is fundamentally sound -- the 3-layer routing, fd-* agent consolidation, flux-drive staged dispatch system, and test infrastructure are well-designed and consistently maintained. The main structural risks are in the upstream sync layer (stale fileMap entries that could silently undo the agent consolidation on next sync) and documentation surfaces that have drifted from reality after hook additions. Both are fixable with targeted changes.
<!-- flux-drive:complete -->
